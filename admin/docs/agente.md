# El asistente del panel

El panel tiene un **asistente**: un agente de IA (Claude, de Anthropic) que, una vez se ingresa, aparece en un botón
flotante. Se le escribe en español y responde con datos de la base: busca personas, resume los indicadores, revisa
los pendientes, prepara reuniones, muestra cosas en el mapa, abre vistas y fichas y propone cambios (una nota, un
acercamiento, una ficha nueva…) que la persona aprueba antes de que se guarden. Con **Mnemo** conectado, también
trabaja en el espacio del administrador en Mnemo: documentos, calendario, formularios y memoria.

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

A = administrador, K = coordinador, P = planillero. Las de Mnemo (`mnemo_…`) se describen [más abajo](#mnemo).

## Cómo se usa

- **El botón.** Abajo a la derecha (en el mapa, junto a sus controles), para quien tiene el asistente habilitado y la
  cuenta al día (clave cambiada y compromiso aceptado). Abre el panel del asistente; en el celular ocupa la pantalla
  bajo la barra superior. **Escape** lo cierra. Si falta la clave de Anthropic, el administrador ve el botón con la
  explicación de qué variable falta; los demás no ven nada.
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
  más barato).
- **Tope diario.** El panel muestra cuántos mensajes quedan hoy. Al llegar al tope, se sigue al día siguiente (hora de
  Colombia). Aprobar o rechazar una tarjeta no cuenta como mensaje.

## Ajustes

En **Ajustes → Asistente**. Son ajustes de permisos: solo los cambia el administrador; el coordinador los ve en solo
lectura. Rigen desde el siguiente mensaje, sin desplegar.

| Ajuste | Por defecto | Qué decide |
|---|---|---|
| Quiénes lo usan (`agente.roles`) | Administrador y coordinadores | Qué roles ven el asistente. Sin ningún rol marcado queda apagado para todos, también para el administrador |
| Proponer cambios en la base (`agente.escritura`) | Sí | Si se ofrecen las herramientas que escriben (siempre con aprobación). Apagado, el asistente solo consulta |
| Los coordinadores también usan Mnemo (`agente.mnemo_coordinadores`) | No | Si los coordinadores usan las herramientas de Mnemo, con el token del administrador |
| Días que se guardan las conversaciones (`agente.retencion_dias`) | 30 | De 1 a 365, contados desde el último mensaje. Bajarlo acorta también las que ya existen |
| Mensajes por día (`agente_mensajes_diarios`) | 300 administrador, 150 coordinador, 40 planillero, 40 consultor | Mensajes por persona y día, de 1 a 5000. Para que un rol no lo use se lo quita de «Quiénes lo usan» |

Un planillero o consultor habilitado usa el asistente con lo mismo que tiene en el panel: su alcance, su presupuesto
diario de personas (lo que el asistente consulta cuenta) y su límite de búsquedas por minuto. El permiso que lo deja
entrar es `agente.usar` (`app/acceso.py`); el ajuste es el que lo enciende.

## Mnemo

**Qué aporta.** Mnemo es el espacio de trabajo personal de la administración. Con el token del administrador, el
asistente puede buscar y leer sus documentos, consultar el calendario y crear o mover eventos, consultar formularios y
guardar borradores, crear, cambiar y exportar documentos del lienzo, proponer recuerdos y pedir que algo se comparta o
se publique (eso lo aprueba el administrador en Mnemo, con un enlace que el asistente le da). Por ejemplo: «agenda en
mi calendario de Mnemo la reunión del jueves en San Miguel del Tigre» o «¿qué dice mi documento de la estrategia de
veredas?».

**Cómo crear el token.**

1. En Mnemo, con la cuenta del administrador: **Tu cuenta → Agentes conectados → Crear un token**.
2. **Nombre**: algo reconocible, como «Panel Trabajemos juntos» (sale en la lista y en el registro de llamadas).
3. **Qué puede hacer**, lo justo para la lista de herramientas por defecto:
   - *Leer*: «Leer tu información» (`mnemo:read`). No marque «Leer las respuestas de tus formularios»
     (`mnemo:forms.responses`): son datos de otras personas y llegarían al modelo.
   - *Escribir*: «Crear y editar eventos, documentos del lienzo y borradores de formularios»
     (`mnemo:workspace.write`) y «Proponer recuerdos nuevos» (`mnemo:memory.write`).
   - *Pedirte aprobación*: «Pedirte compartir…» (`mnemo:share`) y «Pedirte publicar…» (`mnemo:publish`).
   - Estudio, negocio y borrar no los usa el panel. Con solo `mnemo:read`, el asistente solo lee: lo demás le responde
     que al token le faltan alcances.
4. **Caduca en**: 90 días (el recomendado). Anote la fecha: al vencer, el asistente avisa que el token no es válido y
   hay que crear otro.
5. **Crear token**. Copie el token (`mnemo_pat_…`, solo se ve esta vez) y la URL de Mnemo para agentes que aparece al
   lado (`https://…/mcp`).
6. En Railway (ver [Configuración](#configuración-en-railway)): `MNEMO_MCP_URL` = esa URL y `MNEMO_TOKEN` = el token.

| Variable | Valor |
|---|---|
| `MNEMO_MCP_URL` | La dirección del servidor MCP de Mnemo: `https://<su Mnemo>/mcp`. Solo `https://` (en local también `http://127.0.0.1` o `http://localhost`); otra cosa se ignora con un aviso en el registro y el asistente queda sin Mnemo |
| `MNEMO_TOKEN` | El token personal (`mnemo_pat_…`) |
| `MNEMO_HERRAMIENTAS` | Opcional. Vacía, la lista por defecto: `search`, `fetch`, `mnemo_get_briefing`, `mnemo_list_items`, `mnemo_view_image`, `mnemo_list_events`, `mnemo_create_event`, `mnemo_update_event`, `mnemo_query_forms`, `mnemo_save_form_draft`, `mnemo_create_document`, `mnemo_update_document`, `mnemo_export_document`, `mnemo_save_memory`, `mnemo_list_shared_with_me`, `mnemo_request_publish`, `mnemo_request_share`, `mnemo_check_approval` y `mnemo_get_job`. Se cambia por nombres separados por comas, o `*` para todas las que permita el token (las 30 pesan mucho en cada mensaje) |

**Quién lo usa y por qué.** El token es personal: quien lo usa actúa en Mnemo *como el administrador*, en sus
documentos, su calendario y su memoria, y Mnemo no distingue quién del panel pidió cada cosa. Por eso lo usa el
administrador, los coordinadores solo si él lo permite en **Ajustes**, y planilleros y consultores nunca. Se decide en
cada mensaje: apagar el ajuste vale también para las conversaciones abiertas.

**Cómo se controla.**

- Toda escritura en Mnemo pasa primero por la tarjeta de aprobación del panel, que muestra los argumentos exactos. Lo
  que Mnemo no hace sin permiso (compartir, publicar) pide además su propia aprobación en Mnemo, con la sesión del
  administrador: el asistente devuelve el enlace y no da nada por hecho antes de que se apruebe.
- En **Agentes conectados**, Mnemo muestra el registro de llamadas del token. Revocarlo ahí corta el acceso al
  instante, sin tocar el panel.
- Mnemo limita cada token a 60 lecturas y 20 escrituras por minuto, compartidas por todo el panel.
- Si Mnemo no responde al empezar una conversación, esa conversación sigue sin sus herramientas (con un aviso); si
  falla después, la herramienta devuelve el error y el asistente lo explica.
- Lo que viene de Mnemo (documentos, formularios) son datos, no instrucciones. Y el asistente no copia datos de
  habitantes a Mnemo salvo que se le pida expresamente: el compromiso de confidencialidad sigue valiendo.

## Privacidad y protección de datos (Ley 1581 de 2012)

El modelo corre en los servidores de Anthropic: todo lo que el asistente le manda sale del panel. Por eso se le manda
lo mínimo, y siempre después de la proyección por rol de la API (`app/agente/minimizar.py`).

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

**Qué nunca va al modelo.**

- Los datos sensibles (salud, etnia, discapacidad, condición de víctima), las listas de origen y quién es líder, ni
  las etiquetas o campos propios marcados como sensibles.
- La cédula y los teléfonos completos, el correo, el punto exacto, la fecha de nacimiento exacta, el número de ficha,
  los trámites, la procedencia y el historial de cada dato, ni quién registró qué.
- De quien marcó **No autorizó**, nada más que quién es y que no autorizó, ni siquiera para el administrador: para
  verla, se abre la ficha en el panel.
- En una búsqueda por número (cédula, teléfono o ficha), las filas van sin los dígitos enmascarados: la API compara
  la cédula por su comienzo, y juntar ese comienzo con los últimos dígitos dejaría reconstruirla.
- La clave de Anthropic, el token de Mnemo, las claves de los usuarios, las sesiones ni las IP.

**Retención.** Las conversaciones se guardan en MongoDB (`agente_conversaciones` y `agente_mensajes`) y se borran
solas a los días de **Ajustes** desde su último mensaje (30 por defecto). Bajar ese plazo acorta también las que ya
existen: las que ya lo pasaron se borran en cuanto MongoDB lo revisa (cada minuto). Su dueño las puede borrar antes.
El uso (`agente_uso`: mensajes y tokens por persona y día, sin contenido) se guarda 180 días.

**Supresión.** Cada conversación anota de qué personas recibió datos el modelo. Al **suprimir** a una persona, se
borran enteras las conversaciones donde aparecía (y la reconciliación de cada arranque repasa las que hayan quedado).

**Transferencia al proveedor del modelo.** Mandar datos personales a Anthropic, en el exterior, es una transmisión
internacional de datos a un tercero (Ley 1581 de 2012, art. 26, y el contrato de transmisión del Decreto 1377 de
2013). Antes de encender el asistente para el equipo con datos reales:

1. Revise con un abogado el **aviso de privacidad** y la **autorización**: deben informar esta finalidad y que un
   proveedor tecnológico en el exterior procesa los datos, y lo que exijan las orientaciones de la SIC sobre
   inteligencia artificial y datos personales.
2. Revise los términos comerciales vigentes de Anthropic (cuánto guarda lo que recibe, dónde y para qué; a la fecha de
   este documento, sus términos comerciales dicen que no entrena modelos con los datos de la API) y acepte o firme su
   acuerdo de tratamiento de datos.
3. Empiece con el administrador y los coordinadores (lo que viene por defecto) y habilite a planilleros y consultores
   después de la revisión y de explicarles qué se le puede pedir.

Los datos de bases oficiales (como las del SISBÉN) siguen sirviendo solo para la finalidad con que se recogieron,
también a través del asistente.

## Límites y costos

**Modelo y esfuerzo.** Por defecto usa `claude-opus-5-5` (Claude Opus 5.5) con esfuerzo `medium`. `AGENTE_MODELO`
cambia el modelo (por ejemplo `claude-sonnet-5-5`, más barato y rápido, o `claude-fable-5-1`, el más capaz y más caro)
y `AGENTE_ESFUERZO` cuánto razona antes de responder: `low`, `medium`, `high`, `xhigh` o `max`. Más esfuerzo es más
razonamiento, más tokens, más espera y más costo; `medium` alcanza para el trabajo del panel. Con Claude Opus 5.5,
Claude Sonnet 5.5 y Claude Fable 5.1 el panel muestra notas de progreso; con esos y con Claude Opus 5, si el modelo
declina una petición, Anthropic la pasa a un modelo de respaldo (el panel lo avisa). Con otro modelo, ninguna de las
dos cosas: solo el razonamiento adaptativo.

**Cómo se forma el costo.** Cada ronda (cada vez que el modelo responde o pide una herramienta) vuelve a mandar las
instrucciones, la lista de herramientas y la conversación entera. La parte repetida sale de la caché de Anthropic (dura
unos minutos), que cobra una fracción: por eso las instrucciones y las herramientas se congelan al crear la
conversación. Una pregunta que necesita una herramienta son al menos dos rondas. Las conversaciones largas cuestan
más por mensaje: conviene empezar otra al cambiar de tema.

Precios de lista en dólares por millón de tokens, a noviembre de 2026 (confírmelos en la página de precios de
Anthropic):

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
  Ningún turno pasa de 10 minutos y cada ronda escribe como mucho 32.000 tokens. Cada herramienta del panel tiene 60
  segundos; las de Mnemo, 80 las de lectura y 140 las de escritura (algunas gastan modelo en Mnemo), porque cortarlas
  antes las cancelaría a medias allá. Las imágenes de Mnemo van como mucho dos por resultado y 8 MB por ronda.
- Por conversación: con más de 300.000 tokens de entrada en su última ronda o 400 mensajes no admite más: hay que
  empezar otra.
- Un turno a la vez por persona y por conversación, y como mucho 4 a la vez por proceso del servidor («El asistente
  está atendiendo muchas conversaciones a la vez»). En el servicio único, los turnos tienen 4 cupos propios: no le
  quitan cupos a la API del panel.

## Configuración en Railway

En *Variables* del servicio que sirve el panel (el del sitio, en el servicio único):

| Variable | Obligatoria | Valor |
|---|---|---|
| `ANTHROPIC_API_KEY` | Para encenderlo | Una clave de la consola de Anthropic. Sin ella el panel funciona igual y el asistente no aparece (el administrador ve qué falta) |
| `AGENTE_MODELO` | No | `claude-opus-5-5` por defecto |
| `AGENTE_ESFUERZO` | No | `medium` por defecto; `low`, `medium`, `high`, `xhigh` o `max` (otro valor usa `medium` y lo avisa en el registro) |
| `MNEMO_MCP_URL`, `MNEMO_TOKEN` | Solo para Mnemo | Ver [Mnemo](#mnemo) |
| `MNEMO_HERRAMIENTAS` | No | Ver [Mnemo](#mnemo) |

Pasos:

1. En la consola de Anthropic, cree una clave para el panel (mejor en un espacio de trabajo propio, con límite de
   gasto). Se ve una sola vez.
2. Póngala en `ANTHROPIC_API_KEY` en Railway y despliegue el cambio. Nunca en el repositorio ni en un archivo que se
   suba.
3. En **Ajustes → Asistente**, revise quiénes lo usan, los topes y la retención.

Para rotar la clave: cree otra, cámbiela en Railway y revoque la vieja en la consola (revocarla corta el asistente al
instante). Lo mismo con el token de Mnemo, desde Mnemo.

## Seguridad

- **La clave y el token no salen del servidor.** Viven en variables de entorno; no llegan al navegador, ni a las
  respuestas, ni a los registros (no aparecen en el `repr` de la configuración ni en los mensajes de error). El
  navegador solo habla con el panel: la CSP (`connect-src 'self'`) no lo deja llamar a Anthropic ni a Mnemo.
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
| `app/agente/bucle.py` | El turno: comprobaciones previas, candados, rondas con el modelo, ejecución de herramientas, aprobaciones y eventos NDJSON |
| `app/agente/llm.py` | El cliente de Anthropic (se crea al primer uso) y la forma de cada petición |
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
| `app/api/ajustes.py`, `web/js/vistas/ajustes.js` | Los ajustes del asistente |

**Un turno, paso a paso.**

1. El navegador manda `POST /api/agente/mensajes` con `{conversacion, texto, contexto}`.
2. Antes de abrir el flujo, el servidor responde con JSON normal lo que impide el turno: 503 `sin_configurar` (falta
   la clave) o `saturado` (ya hay 4 turnos en este proceso; trae `Retry-After`), 403 `agente_apagado` (su rol no está
   habilitado), 429 `volumen` (tope diario), 409 `ocupada` (ya hay un turno suyo en curso) o `larga` (conversación
   demasiado larga), y 404 si la conversación no es suya o no existe.
3. Abre el flujo y llama al modelo con las instrucciones y las herramientas congeladas de la conversación, el
   historial y el mensaje nuevo precedido del contexto de la vista. Mientras llega, emite progreso, texto y el inicio de
   cada herramienta.
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
| `herramienta` | `id`, `nombre`, `etiqueta`, `estado` (`inicio`, `ok`, `error`, `pendiente`, `aprobada`, `rechazada`) y `resumen` |
| `accion` | Una acción para el navegador: `navegar` (una ruta del panel), `recargar`, `insignias` o `mapa` (acciones del mapa) |
| `confirmar` | La tarjeta de una escritura: `id`, `titulo`, `detalle` (pares etiqueta y valor) y `aviso` |
| `descartar` | La ronda se repite tras un error pasajero: se borra lo que se pintó de ella |
| `aviso` | `texto` y `nivel` (`info` o `alerta`): un rechazo del modelo, el paso a un modelo de respaldo |
| `latido` | Cada 15 s sin otros eventos, para mantener viva la conexión |
| `error` | `mensaje` y `codigo`; siempre lo sigue `fin` |
| `fin` | `motivo` (`listo`, `confirmacion`, `pasos`, `rechazo` o `error`) y `limite` (`usados`, `maximo`). Siempre el último |

**En MongoDB**: `agente_conversaciones` (dueño, título, instrucciones y herramientas congeladas, personas vistas, lo
pendiente de aprobar, candado del turno y fecha de borrado), `agente_mensajes` (un documento por mensaje, con su
número de orden) y `agente_uso` (mensajes y tokens por persona y día). Los índices TTL borran lo vencido.

## Probar en local sin clave

Sin `ANTHROPIC_API_KEY` el panel funciona igual: el administrador ve el botón con la explicación de qué falta. Las
pruebas nunca llaman a Anthropic ni a Mnemo: el modelo va simulado con el SDK de verdad y un transporte falso, y Mnemo
con un servidor MCP falso. Necesitan MongoDB, como las demás:

```bash
cd admin
python -m pytest -q tests/test_agente_*.py
```

`tests/ayudas_agente.py` trae lo necesario para escribir una: `encender(app, *respuestas)` pone una clave inventada y
la Messages API simulada; `sse(...)` arma una respuesta del modelo con bloques `T` (texto), `TH` (progreso) y `TU`
(una herramienta); `enviar` y `decidir` hacen un turno por la API y devuelven los eventos.

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

Para probarlo con el modelo real, ponga una clave propia en `admin/.env` (`ANTHROPIC_API_KEY=…`; Git ignora los
`.env`) y arranque como siempre:

```bash
uvicorn app.main:app --reload --no-access-log --no-server-header
```

Con un Mnemo local, `MNEMO_MCP_URL=http://127.0.0.1:8080/mcp` y un token creado en él.
