# El asistente del panel

El panel tiene un **asistente**: un agente de IA que, una vez se ingresa, aparece en un botón flotante. Se le escribe
en español y responde con datos de la base: busca personas, resume los indicadores, revisa los pendientes, prepara
reuniones, muestra cosas en el mapa, abre vistas y fichas y propone cambios (una nota, un acercamiento, una ficha
nueva…) que la persona aprueba antes de que se guarden.

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
| Administrador y coordinador | Indicadores del tablero (también de una zona o con filtros), buscar y ver habitantes, fichas parecidas, reuniones (listar, ver, crear, agregar asistentes), pendientes de calidad (solicitudes por vencer, situaciones, conflictos, coincidencias, lugares sin punto), su trabajo, el equipo (indicadores y avance por zona, sin sesiones ni IP), barrios y veredas, catálogos, el mapa y cualquier vista. Propone crear y editar fichas, notas, acercamientos, autorizaciones, ubicación y teléfonos. Con Mnemo, el administrador (y el coordinador, si se le permite): documentos, calendario, formularios y memoria |
| Planillero | Buscar y ver habitantes (en su zona y con su presupuesto diario), parecidas, sus reuniones y las abiertas al equipo, su trabajo y sus pendientes, barrios y veredas, catálogos y sus vistas. Propone crear y editar fichas, notas, acercamientos (visita o reunión), autorizaciones, ubicación, teléfonos, reuniones y asistentes. Sin tablero, mapa ni equipo |
| Consultor | Su cola de llamadas y su trabajo, buscar por nombre (3 letras o más) o por un número completo de 10 dígitos, y ver las fichas de las personas que tiene en curso. Propone acercamientos (llamada, WhatsApp, SMS…), autorizaciones y teléfonos |

Nunca, para nadie: exportar o descargar, importar, unir o suprimir fichas, crear usuarios o cambiar claves y roles,
cambiar ajustes, ver los datos sensibles o las listas de origen, ni la cédula o el teléfono completos. Para eso está el
panel: el asistente lo explica y dice dónde hacerlo.

Las herramientas del panel (`app/agente/herramientas/`):

| Herramienta | Tipo | Quién | Qué hace |
|---|---|---|---|
| `buscar_personas`, `ver_persona` | lectura | todos | Habitantes y fichas, con la proyección de cada rol |
| `personas_parecidas` | lectura | A, K, P | Posibles duplicados por nombre, cédula o teléfono |
| `crear_persona`, `editar_persona`, `agregar_nota`, `ubicar_persona` | escritura | A, K, P | Ficha nueva (avisa si hay parecidas), cambios con «antes → después», notas y ubicación |
| `registrar_acercamiento`, `registrar_autorizacion`, `agregar_telefono` | escritura | todos | Lo que la persona del equipo dicta: nunca inventa evidencias, autorizaciones ni números |
| `indicadores`, `equipo` | lectura | A, K | Tablero compacto (sin listas ni sensibles) e indicadores del equipo |
| `listar_reuniones`, `ver_reunion` | lectura | A, K, P | Agenda y asistentes |
| `crear_reunion`, `agregar_asistente` | escritura | A, K, P | Reunión nueva y asistentes |
| `pendientes`, `mi_trabajo`, `buscar_lugar`, `catalogos` | lectura | todos | Insignias y colas, listas de trabajo, nomenclátor de barrios y veredas, catálogos no sensibles |
| `mapa` | interfaz | A, K | Vuela a un lugar, filtra, cambia capas y mapa base, resalta personas, abre una zona |
| `abrir_vista` | interfaz | todos | Abre una vista o una ficha que su rol puede ver |

A = administrador, K = coordinador, P = planillero. Las de Mnemo (`mnemo_…`) se describen [más abajo](#conectar-con-mnemo).

## Cómo se usa

- **El botón.** Abajo a la derecha (en el mapa, junto a sus controles), para quien tiene el asistente habilitado y la
  cuenta al día (clave cambiada y compromiso aceptado). Abre el panel del asistente; en el celular ocupa la pantalla
  bajo la barra superior. **Escape** lo cierra. Si el asistente no tiene un modelo que usar (Mnemo sin conectar, la
  conexión caída o sin permiso para usar sus modelos), el administrador ve el botón con lo que falta y un enlace a
  **Ajustes → Asistente**; los demás no ven nada.
- **Escribir.** Se escribe y se pulsa **Enviar**; **Detener** corta la respuesta en curso. La respuesta llega por
  partes: notas de progreso en gris (qué está haciendo), una marca por cada herramienta con su resultado («12
  personas», «Nota guardada») y el texto. Una conversación vacía muestra sugerencias para el rol.
- **Sabe dónde está.** Con cada mensaje viaja la vista abierta: la ruta, la ficha o la reunión que se está viendo, los
  filtros de la dirección y el encuadre del mapa. Por eso «¿qué le falta a esta ficha?» funciona. Es solo una pista:
  las herramientas vuelven a leer todo con los permisos de la persona.
- **Aprobar.** Cuando el asistente propone escribir, aparece una tarjeta con lo que va a hacer y los valores exactos
  (al editar, «antes → después») y los botones **Aprobar** y **Rechazar**. Nada se guarda sin aprobar. Lo rechazado no
  lo vuelve a proponer salvo que se le pida, y escribir otro mensaje sin decidir cuenta como rechazo. Lo aprobado queda
  en la auditoría a nombre de quien aprobó, como si lo hubiera hecho en el formulario. Si la ficha cambió entre la
  tarjeta y la aprobación (otra persona la editó), no escribe nada y lo avisa: la tarjeta guarda una huella de lo que
  mostró, nunca los valores. Sobre quien no autorizó el tratamiento no propone cambios (salvo registrar su
  autorización), ni siquiera para el administrador.
- **El mapa** (administrador y coordinador). «Muéstrame en el mapa a las personas de La Paz sin cédula»: abre el mapa
  si hace falta, vuela al lugar, aplica los filtros y las capas y resalta los puntos. En el celular el panel se pliega
  para que se vea el cambio. Los nombres de las etiquetas del mapa los pone el navegador: al modelo solo le vuelve un
  resumen («1.234 personas, 980 ubicadas»). Los filtros que el asistente pone sin selector en el mapa se ven en el
  aviso **Filtros del asistente · Quitar**; la vereda a la que vuela queda marcada hasta que se le pide limpiar el
  mapa; y si se abre otra vista mientras el mapa carga, lo que esperaba aplicarse se descarta con un aviso.
- **Enlaces.** Las personas y reuniones que nombra enlazan a su ficha dentro del panel (`/personas/123`,
  `/reuniones/45`). Las aprobaciones de Mnemo abren Mnemo en otra pestaña. Ningún otro enlace se vuelve clicable.
- **Conversaciones.** **Nueva conversación** empieza otra; **Conversaciones** lista las 30 más recientes para abrirlas
  o borrarlas. Cada una es solo de su dueño: ni el administrador ve las de los demás. Se borran solas tras los días
  de **Ajustes** sin usarse. Una conversación muy larga deja de admitir mensajes: hay que empezar otra (también sale
  más barato). Cada conversación sigue con el modelo con que empezó (Mnemo o el modo directo): si ese ya no está, el
  asistente ofrece **Nueva conversación**.
- **Tope diario.** El panel muestra cuántos mensajes quedan hoy. Al llegar al tope, se sigue al día siguiente (hora de
  Colombia). Aprobar o rechazar una tarjeta no cuenta como mensaje.

## Ajustes

En **Ajustes → Asistente**. Arriba dice si el asistente está encendido y con qué modelo, y está la **Conexión con
Mnemo** (ver [Conectar con Mnemo](#conectar-con-mnemo)): solo el administrador la conecta o la desconecta; el coordinador
ve su estado. Lo demás son ajustes de permisos: solo los cambia el administrador; el coordinador los ve en solo
lectura. Rigen desde el siguiente mensaje, sin desplegar.

| Ajuste | Por defecto | Qué decide |
|---|---|---|
| Quiénes lo usan (`agente.roles`) | Administrador y coordinadores | Qué roles ven el asistente. Sin ningún rol marcado queda apagado para todos, también para el administrador |
| Proponer cambios en la base (`agente.escritura`) | Sí | Si se ofrecen las herramientas que escriben (siempre con aprobación). Apagado, el asistente solo consulta |
| Los coordinadores también usan las herramientas de Mnemo (`agente.mnemo_coordinadores`) | No | Si los coordinadores usan las herramientas de Mnemo (documentos, calendario, formularios y memoria), con la cuenta de Mnemo del administrador. Los modelos los usan todos los roles habilitados |
| Días que se guardan las conversaciones (`agente.retencion_dias`) | 30 | De 1 a 365, contados desde el último mensaje. Bajarlo acorta también las que ya existen |
| Mensajes por día (`agente_mensajes_diarios`) | 300 administrador, 150 coordinador, 40 planillero, 40 consultor | Mensajes por persona y día, de 1 a 5000. Para que un rol no lo use se lo quita de «Quiénes lo usan» |

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
   «Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar y marque esa casilla».
4. Mnemo lo trae de vuelta a Ajustes, que muestra **Conectado como** la cuenta (nombre y correo), desde cuándo, la
   dirección y los permisos. Si canceló en Mnemo, lo dice y no conecta nada.

Lo que pide el panel: `openid`, `profile` y `email` (solo para mostrar con qué cuenta se conectó), `mnemo:model` y los
permisos que necesitan las herramientas de Mnemo que ofrece (con la lista por defecto, `mnemo:read`,
`mnemo:workspace.write`, `mnemo:memory.write`, `mnemo:share` y `mnemo:publish`). Nunca `mnemo:forms.responses`: las
respuestas de los formularios son datos de otras personas y llegarían al modelo. Con solo `mnemo:read`, las herramientas
de Mnemo solo leen: lo demás responde que a la conexión le faltan permisos.

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
| Conectado, con el aviso «sin permiso para usar sus modelos» | En Mnemo no quedó marcado «Usar tus modelos de IA y tus créditos» (o esa versión de Mnemo todavía no lo tiene) | **Volver a conectar** y marcarlo |
| Conexión caída: Mnemo ya no la acepta | Se revocó en Mnemo, venció (30 días sin usarse, o un año desde el último permiso) o la cuenta se desactivó | **Volver a conectar** |
| Conexión caída: cambió la clave del administrador | Cambiaron `ADMIN` o `password` y lo guardado ya no se puede descifrar | **Volver a conectar**; la conexión vieja puede seguir en Mnemo: revóquela ahí |
| Conexión caída: Mnemo respondió algo inesperado | La renovación del acceso falló | **Volver a conectar** |

**Lo que Mnemo necesita.**

- El inicio de sesión para agentes (OAuth) activo: en el despliegue de Mnemo, `PUBLIC_BASE_URL` (su dirección
  pública). Sin ella, conectar responde «Mnemo no tiene OAuth: falta PUBLIC_BASE_URL en su despliegue.»
- Una versión con la herramienta `mnemo_model_complete` y el permiso «Usar tus modelos de IA y tus créditos». Con una
  anterior, la conexión queda sin permiso para usar sus modelos (Ajustes lo avisa) y el asistente no tiene modelo,
  salvo el modo directo.
- Que la cuenta pueda responder: un plan que incluya el chat o una clave propia de un proveedor de modelos configurada
  en Mnemo, y créditos. Si no, el asistente lo dice al responder (sin plan, sin créditos o sin un modelo disponible).

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
administrador, los coordinadores solo si él lo permite en **Ajustes**, y planilleros y consultores nunca. Se decide en
cada mensaje: apagar el ajuste vale también para las conversaciones abiertas. Usar los modelos es distinto: lo hacen
todos los roles habilitados, y no lee ni escribe nada del Mnemo del administrador.

**Cómo se controla.**

- Toda escritura en Mnemo pasa primero por la tarjeta de aprobación del panel, que muestra los argumentos exactos. Lo
  que Mnemo no hace sin permiso (compartir, publicar) pide además su propia aprobación en Mnemo, con la sesión del
  administrador: el asistente devuelve el enlace y no da nada por hecho antes de que se apruebe.
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
Por eso, si cambian `ADMIN` o `password`, la conexión queda caída y hay que volver a conectar. El panel renueva el
acceso solo, con una sola renovación a la vez aunque corran varios procesos (Mnemo revoca la conexión entera si le
llega un token de renovación ya usado). Los tokens nunca llegan al navegador, a las respuestas ni a los registros. La
auditoría guarda `mnemo_conectar`, `mnemo_desconectar` y `mnemo_caida` (esta, del sistema), sin tokens.

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

- Lo que escribe la persona y el contexto de la vista (ruta, número de la ficha o la reunión abierta, filtros de la
  dirección y encuadre del mapa).
- El nombre y el rol de quien conversa, en las instrucciones del asistente.
- Lo que devuelven las herramientas, recortado: de cada habitante, lo necesario para la tarea (nombre, barrio o
  vereda, sexo y edad, si es menor, estudios, ocupación y hogar, puesto y mesa, autorización y abordaje, qué le falta
  a la ficha…), con la cédula y los teléfonos enmascarados («···123», «···2233») también para el administrador, y las
  notas, la dirección y las observaciones recortadas y con los números largos y los correos tapados. Indicadores
  agregados y reuniones.
- Con Mnemo, lo que lee del espacio del administrador.
- En cada ronda, las instrucciones del asistente, las herramientas que ofrece el panel y la conversación: con Mnemo, eso
  es lo que reciben Mnemo y su proveedor de modelos.

**Qué nunca va al modelo.**

- Los datos sensibles (salud, etnia, discapacidad, condición de víctima), las listas de origen y quién es líder, ni
  las etiquetas o campos propios marcados como sensibles.
- La cédula y los teléfonos completos, el correo, el punto exacto, la fecha de nacimiento exacta, el número de ficha,
  los trámites, la procedencia y el historial de cada dato, ni quién registró qué.
- De quien marcó **No autorizó**, nada más que quién es y que no autorizó, ni siquiera para el administrador: para
  verla, se abre la ficha en el panel.
- En una búsqueda por número (cédula, teléfono o ficha), las filas van sin los dígitos enmascarados: la API compara
  la cédula por su comienzo, y juntar ese comienzo con los últimos dígitos dejaría reconstruirla.
- La clave de Anthropic, los tokens de la conexión con Mnemo, las claves de los usuarios, las sesiones ni las IP.

**Retención.** Las conversaciones se guardan en MongoDB (`agente_conversaciones` y `agente_mensajes`) y se borran
solas a los días de **Ajustes** desde su último mensaje (30 por defecto). Bajar ese plazo acorta también las que ya
existen: las que ya lo pasaron se borran en cuanto MongoDB lo revisa (cada minuto). Su dueño las puede borrar antes.
El uso (`agente_uso`: mensajes, tokens y créditos por persona y día, sin contenido) se guarda 180 días.

**Supresión.** Cada conversación anota de qué personas recibió datos el modelo. Al **suprimir** a una persona, se
borran enteras las conversaciones donde aparecía (y la reconciliación de cada arranque repasa las que hayan quedado).

**Transferencia al proveedor del modelo.** Mandar datos personales a Mnemo y al proveedor de modelos de esa cuenta
(o a Anthropic, en modo directo), terceros posiblemente en el exterior, es una transmisión internacional de datos
(Ley 1581 de 2012, art. 26, y el contrato de transmisión del Decreto 1377 de 2013). Antes de encender el asistente para
el equipo con datos reales:

1. Revise con un abogado el **aviso de privacidad** y la **autorización**: deben informar esta finalidad y que
   proveedores tecnológicos, posiblemente en el exterior, procesan los datos, y lo que exijan las orientaciones de la
   SIC sobre inteligencia artificial y datos personales.
2. Revise los términos vigentes de Mnemo y del proveedor de modelos que use la cuenta (cuánto guardan lo que reciben,
   dónde y para qué) y acepte o firme sus acuerdos de tratamiento de datos. En modo directo, los de Anthropic (a la
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
ninguna de las dos cosas: solo el razonamiento adaptativo.

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

**Topes.**

- Por persona y día, los mensajes de **Ajustes** (429 al pasarse).
- Por turno: 12 rondas y 240 segundos; al llegar, termina la ronda en curso y avisa (se le puede pedir que siga).
  Ningún turno pasa de 10 minutos y cada ronda escribe como mucho 32.000 tokens (16.000 con Mnemo). Cada herramienta
  del panel tiene 60
  segundos; las de Mnemo, 80 las de lectura y 140 las de escritura (algunas gastan modelo en Mnemo), porque cortarlas
  antes las cancelaría a medias allá. Las imágenes de Mnemo van como mucho dos por resultado y 8 MB por ronda (con
  Mnemo como modelo, 1,5 MB por ronda).
- Con Mnemo como modelo, cada ronda tiene en Mnemo unos 170 segundos y cada petición como mucho 3,9 MB: si no cabe,
  las imágenes de los mensajes viejos se cambian por una marca y, si aún no cabe, hay que empezar otra conversación.
  Cuando Mnemo pide esperar (su tope por minuto), el panel reintenta solo, sin pasarse del tope del turno.
- Por conversación: con más de 300.000 tokens de entrada en su última ronda o 400 mensajes no admite más: hay que
  empezar otra.
- Un turno a la vez por persona y por conversación, y como mucho 4 a la vez por proceso del servidor («El asistente
  está atendiendo muchas conversaciones a la vez»). En el servicio único, los turnos tienen 4 cupos propios: no le
  quitan cupos a la API del panel.

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
| `AGENTE_ESFUERZO` | `medium` por defecto; `low`, `medium`, `high`, `xhigh` o `max` (otro valor usa `medium` y lo avisa en el registro). Vale con Mnemo y en modo directo |

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
  a mitad de la conversación. Si la sesión se cierra o vence, la siguiente herramienta falla y el turno termina.
- **No hay herramientas para lo delicado**: exportar, importar, unir, suprimir, usuarios y claves, ajustes, datos
  sensibles.
- **Escrituras.** Solo con aprobación, y con una clave de idempotencia por llamada: aprobar dos veces o reintentar no
  duplica nada.
- **Lo que viene de la base o de Mnemo son datos, no instrucciones.** Las notas, los documentos y los formularios los
  escribe gente y pueden traer órdenes escondidas; el asistente no las sigue, y aunque lo hiciera no puede saltarse los
  permisos ni escribir sin aprobación.
- **La respuesta se pinta como texto**, nunca como HTML: solo enlaza rutas del panel y el origen de Mnemo, y las
  acciones que puede pedirle al navegador son una lista cerrada (abrir una ruta del panel, recargar la vista, refrescar
  las insignias, mover el mapa).
- **El flujo.** `POST` con CSRF y respuesta en flujo NDJSON (una línea JSON por evento, con un latido cada 15 s), sin
  GZip en esas dos rutas (lo retendría hasta el final) y con cupos propios en el servicio único.
- **Registros.** Solo el tipo de cada error: nunca lo que se escribió, lo que respondió el modelo ni datos de personas.
- **En el navegador** no queda nada de la conversación: solo `sessionStorage` `yj_agente` (si el panel estaba abierto
  y qué conversación), que se borra al cerrar sesión. El widget sabe qué vista está abierta por el evento `vista` que
  emite `app.js` al terminar de pintar cada una.

## Arquitectura

| Archivo | Qué hace |
|---|---|
| `app/api/agente.py` | Las rutas: `GET /api/agente/estado`, `GET /api/agente/conversaciones`, `GET` y `DELETE /api/agente/conversaciones/{id}`, `POST /api/agente/mensajes` y `POST /api/agente/confirmaciones` |
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
| `web/js/agente.js`, `web/css/agente.css` | El botón y el panel del asistente |
| `web/js/agente-mapa.js` | El puente entre el asistente y la vista del mapa |
| `web/js/api.js` (`flujo`) | Lee la respuesta NDJSON con el CSRF de la sesión |
| `app/api/ajustes.py`, `web/js/vistas/ajustes.js` | Los ajustes del asistente y, en la vista, la conexión con Mnemo (conectar, la vuelta y desconectar) |

**Un turno, paso a paso.**

1. El navegador manda `POST /api/agente/mensajes` con `{conversacion, texto, contexto}`.
2. Antes de abrir el flujo, el servidor responde con JSON normal lo que impide el turno: 503 `sin_configurar` (no hay
   modelo: ni Mnemo conectado con permiso para usar sus modelos ni clave de Anthropic) o `saturado` (ya hay 4 turnos
   en este proceso; trae `Retry-After`), 403 `agente_apagado` (su rol no está habilitado), 429 `volumen` (tope diario),
   409 `ocupada` (ya hay un turno suyo en curso), `larga` (conversación demasiado larga) o `proveedor` (la
   conversación es de un modelo que ya no está: hay que empezar otra), y 404 si la conversación no es suya o no
   existe.
3. Abre el flujo y pide una ronda al modelo de la conversación (a Mnemo, con `mnemo_model_complete`, o a Anthropic) con
   las instrucciones y las herramientas congeladas, el historial y el mensaje nuevo precedido del contexto de la
   vista. Mientras llega, emite el texto por partes (y, con Anthropic, el progreso) y el inicio de cada herramienta.
4. Ejecuta las herramientas en orden: las de lectura y de interfaz en el acto (con la API interna); las de escritura
   quedan pendientes, emite una tarjeta por cada una y termina con `fin` `confirmacion`.
5. Al aprobar o rechazar, `POST /api/agente/confirmaciones` con `{conversacion, decisiones: [{id, aprobar}]}` ejecuta
   lo aprobado (con su clave de idempotencia), devuelve al modelo todos los resultados juntos y sigue el turno.
6. Termina con `fin` y el uso del día.

**Eventos** (una línea JSON por evento, con `tipo`):

| Evento | Qué lleva |
|---|---|
| `inicio` | `conversacion`, `titulo`. Siempre el primero |
| `progreso`, `texto` | Trozos de una nota de progreso o de la respuesta |
| `texto_ronda` | `texto`: el texto final de la ronda en curso cuando no coincide con lo que llegó por partes (con Mnemo, los trozos son un adelanto). Reemplaza el de la ronda |
| `herramienta` | `id`, `nombre`, `etiqueta`, `estado` (`inicio`, `ok`, `error`, `pendiente`, `aprobada`, `rechazada`) y `resumen` |
| `accion` | Una acción para el navegador: `navegar` (una ruta del panel), `recargar`, `insignias` o `mapa` (acciones del mapa) |
| `confirmar` | La tarjeta de una escritura: `id`, `titulo`, `detalle` (pares etiqueta y valor) y `aviso` |
| `descartar` | La ronda se repite tras un error pasajero: se borra lo que se pintó de ella |
| `aviso` | `texto` y `nivel` (`info` o `alerta`): un rechazo del modelo, el paso a un modelo de respaldo |
| `latido` | Cada 15 s sin otros eventos, para mantener viva la conexión |
| `error` | `mensaje` y `codigo` (ver abajo); siempre lo sigue `fin` |
| `fin` | `motivo` (`listo`, `confirmacion`, `pasos`, `rechazo` o `error`) y `limite` (`usados`, `maximo`). Siempre el último |

**Códigos que el widget trata aparte**, además de mostrar el mensaje (vengan antes del flujo o en un `error`):

| Código | Qué hace el widget |
|---|---|
| `proveedor`, `larga`, `llm_peticion`, `borrada`, `no_existe` | Ofrece **Nueva conversación**: esta ya no sirve (si el mensaje no llegó, la nueva lo trae escrito) |
| `mnemo_conexion`, `sin_configurar`, `agente_apagado` | Vuelve a leer el estado: al administrador le explica qué falta, con un enlace a Ajustes |
| `mnemo_plan`, `mnemo_creditos`, `mnemo_sin_modelo`, `volumen`, `permiso`, `sin_pendientes` | No ofrece **Reintentar**: repetir el mismo mensaje no lo arregla |

Los de Mnemo como modelo: `mnemo_conexion` (la conexión se cayó o Mnemo la rechazó tras renovarla), `mnemo_plan` (el
plan no incluye el chat), `mnemo_creditos` (no quedan créditos), `mnemo_sin_modelo` (la cuenta no tiene un modelo que
responda), `larga` (la conversación no cabe en la ventana del modelo) y `llm_peticion` (otro rechazo de la petición).

**En MongoDB**: `agente_conversaciones` (dueño, título, modelo con que empezó, instrucciones y herramientas
congeladas, personas vistas, lo pendiente de aprobar, candado del turno y fecha de borrado), `agente_mensajes` (un
documento por mensaje, con su número de orden), `agente_uso` (mensajes, tokens y créditos por persona y día) y, en
`meta`, `mnemo_conexion` (la conexión con Mnemo, con los tokens cifrados). Los índices TTL borran lo vencido.

## Probar en local

Sin Mnemo conectado ni `ANTHROPIC_API_KEY` el panel funciona igual: el administrador ve el botón con la explicación de
qué falta. Las pruebas nunca llaman a Anthropic ni a Mnemo: el modelo de Anthropic va simulado con el SDK de verdad y
un transporte falso, y Mnemo con un servidor MCP y un OAuth falsos (`tests/ayudas_mcp.py`). Necesitan MongoDB, como las
demás:

```bash
cd admin
python -m pytest -q tests/test_agente_*.py
```

`tests/ayudas_agente.py` trae lo necesario para escribir una: `encender(app, *respuestas)` pone una clave inventada y
la Messages API simulada; `sse(...)` arma una respuesta del modelo con bloques `T` (texto), `TH` (progreso) y `TU`
(una herramienta); `conectar_mnemo(app)` guarda una conexión con un Mnemo falso, cifrada como la deja Ajustes; `enviar`
y `decidir` hacen un turno por la API y devuelven los eventos. `tests/test_agente_navegador.py` conecta Mnemo de punta
a punta en Chromium (Ajustes, la página de permisos de un Mnemo falso y la vuelta).

```python
from ayudas_agente import T, encender, enviar, sse


def test_un_turno_con_el_modelo_simulado(sesion):
    api = encender(sesion.app, sse(T("Hola. ¿En qué le ayudo?")))
    r, eventos = enviar(sesion, "Hola")
    assert eventos[0]["tipo"] == "inicio" and eventos[-1]["tipo"] == "fin"
    assert api.peticiones[0]["json"]["model"] == "claude-opus-5-5"  # lo que se le habría mandado a Anthropic
```

La prueba de punta a punta contra un Mnemo de verdad levantado en local (`tests/test_agente_mnemo.py`) se salta sin
`MNEMO_E2E_DIR` (un checkout de Mnemo con sus dependencias instaladas).

Para probarlo con un modelo real, arranque como siempre y conecte un Mnemo desde **Ajustes → Asistente**: el de
producción o uno local con `PUBLIC_BASE_URL` (en local el panel acepta `http://127.0.0.1` y `http://localhost`, por
ejemplo `MNEMO_MCP_URL=http://127.0.0.1:8080/mcp`). Para el modo directo, ponga una clave propia en `admin/.env`
(`ANTHROPIC_API_KEY=…`; Git ignora los `.env`).

```bash
uvicorn app.main:app --reload --no-access-log --no-server-header
```
