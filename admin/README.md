# Panel de administración · Base única de habitantes de Yondó

Aplicación privada (con usuario y clave) para administrar la base de habitantes que se arma cruzando:

1. **Trámites por vereda**: una fila por solicitud (ID, Número de ficha, Fecha, «TRÁMITE - NOMBRE», Dirección, Correo, Teléfono, Paquete).
2. **Base unificada con cédula**: una fila por cédula, con listas de origen, puesto de votación, edad y sexo.
3. **Base general de la campaña**: CC, nombre, varios contactos, dirección, barrio, grupo (votante, líderes,
   coordinadores, candidato al concejo, listas), líder («cédula - nombre» de quien la trajo), líder confirmado y votos,
   puesto, mesa, fecha de nacimiento y profesión; o las columnas de los 17 campos principales de la ficha.

El panel las **cruza por nombre**, **normaliza las direcciones**, **georreferencia** a cada persona, muestra un
**mapa 3D del municipio con mapa de calor** y permite **enriquecer los perfiles reunión a reunión**.

> **Ningún dato personal va al repositorio** (es público). Los Excel se suben por el panel, se procesan en memoria
> y se descartan; los datos quedan solo en MongoDB (los registros del servicio no guardan lo que se busca). En
> `admin/geo/` solo hay geografía pública. Git ignora hojas de cálculo (`.xlsx`, `.xlsm`, `.xlsb`, `.xls`, `.ods`) en
> cualquier carpeta, los CSV de `admin/` y de la raíz y los `.env` (salvo `.env.example`), y el CI falla si alguno
> llega a versionarse; aun así, guarde los Excel fuera del clon del repositorio o en `admin/var/`.

## Qué hace

| Módulo | Qué ofrece |
|---|---|
| **Panel** | Indicadores: habitantes, % con cédula, % georreferenciados y con dirección exacta, contactables, alcanzados en reuniones, completitud media del perfil, autorizaciones de datos, coincidencias por revisar. Ranking por barrio/vereda, calidad de la ubicación, zona, trámites por mes, pirámide de edad y sexo, necesidades, listas de origen y actividad. |
| **Mapa 3D** | Relieve real del terreno, edificios 3D, columnas hexagonales extruidas (altura y color = personas), mapa de calor, puntos individuales al acercarse, polígonos de las 62 veredas catastrales, límite municipal del DANE y reuniones. Filtros (zona, fuente, precisión, asistencia, necesidad, lista), tamaño de hexágono, mapa base (oscuro, claro, satélite), recorridos al casco urbano y a San Miguel del Tigre, giro automático. Al tocar un hexágono: cuántos, de qué barrios y el enlace a la lista. |
| **Habitantes** | Directorio con búsqueda (nombre, cédula, teléfono, dirección, ficha) cuyas columnas son los **datos principales** de la ficha: nombre, cédula, sexo y edad (con la fecha de nacimiento), teléfono y correo, dirección, barrio y zona, líder o votante y «Liderado por» (A y K), perfil profesional y ocupación (con estado civil y jefe de hogar), lo que falta de ellos y la completitud; hasta 1800 px de ancho van en tarjetas con cada dato bajo su título. Los primeros filtros son también los de esos datos (cédula, sexo, edad, teléfono, correo, dirección, barrio o vereda, zona, tipo y «Liderado por» —también «Sin líder»— para A y K, perfil profesional y ocupación por texto, estado civil y jefe de hogar); el puesto, la mesa, el abordaje, la autorización y los demás van plegados en **Más filtros**. Orden por completitud o contacto y exportación a Excel de lo filtrado. A y K filtran además por reunión (las intervenidas en ella) y abren la lista de **Líderes y concejales** con cuántas personas lidera cada uno y cuántas son votantes. **Nuevo votante** (A, K y P) registra a alguien con Votante marcado y la barra para buscar a su líder. P ve en las filas solo los datos principales que no identifican (sin correo, dirección ni fecha exacta, que están en la ficha) y nada político: el tipo y el «Liderado por» los ve en la ficha de las personas de su zona y de las que registra. |
| **Ficha** | Arriba, los **17 datos principales**: nombre, cédula, sexo, edad, teléfono, fecha de nacimiento, correo, dirección, barrio o vereda, zona urbana o rural (sale del barrio), tipo de persona (concejal, líder, votante), «Liderado por», perfil profesional, ocupación, estado civil y jefe de hogar; debajo, la votación y los demás datos. Necesidades/intereses/roles, campos propios, autorización de datos, ubicación con minimapa y ajuste manual del punto, historial (reuniones, notas, trámites), origen de cada dato y registro de cambios. Unir fichas duplicadas y suprimir datos (derecho de supresión). El tipo y quién lidera a la persona (uno o varios **líderes o concejales**, con una barra para buscar otro y el aviso si la capta más de uno) los ven y los cambian A y K en toda la base; P los ve en las personas de su zona y en las que registra, marca un tipo y asigna un líder (lo busca en toda la campaña por nombre, con 3 letras o más, o por la cédula completa), pero no quita ninguno: quitar un tipo o un líder es de A y K. Solo A y K ven a cuántas lidera ella si es líder o concejal y la **traza de las reuniones**: cada cambio con la reunión en que se hizo y, por reunión, si se la intervino y si asistió. Ver [`docs/reuniones-y-lideres.md`](docs/reuniones-y-lideres.md). |
| **Reuniones** | Agenda con asistentes y personas nuevas por reunión, con **hora de inicio y de fin** (y el chip «En curso»): lo que el equipo le hace a una persona mientras dura (editarla, completarla, darla de alta…) queda con la traza de la reunión por coincidir en el tiempo, aunque no sea asistente, y el modo reunión lista a quienes se intervino sin registrar su asistencia. **Modo reunión**: buscar y agregar asistentes en segundos, registrar personas nuevas (con aviso de posibles duplicados) y «Completar» el perfil de cada asistente ahí mismo (cédula, celular, ocupación, hogar, necesidades, autorización y lo que pidió, que queda en su historial). Exporta asistentes a CSV. |
| **Calidad de datos** | Coincidencias por nombre agrupadas por persona para revisarlas en bloque: cada grupo junta las fichas que serían la misma (A~B y B~C son un grupo), con las señales a favor y en contra (teléfono, correo o fecha en común, sexo o nombre de pila distinto…), un nivel de confianza («muy probables», «probables», «dudosas», «bloqueadas»), la comparación lado a lado con la fuente de cada dato y la vista previa de la ficha unida; se unen o separan varios grupos de una vez (también «unir todas las muy probables»), marcando las fichas que no son la misma; conflictos de cédula (misma cédula con otro nombre, cédula anterior, posible error de digitación, cédula dictada al consultor) que nunca se mezclan solos; solicitudes de los titulares con sus plazos legales; personas reportadas como fallecidas o fuera de Yondó, para confirmar o revertir; barrios y veredas sin punto para ubicarlos con un clic en el mapa; nombres escritos que no se reconocen, para crearlos o agregarlos como alias. |
| **Importar y exportar** | Subir los Excel (trámites, base con cédula, base general de la campaña y planillas de campo; se reconocen por sus columnas) cuantas veces se quiera, con «Capturado por» para las planillas y la plantilla para descargar; historial de importaciones, con la confirmación de las autorizaciones declaradas en planilla; exportar la base única. **Planillas por foto**: cuando una planilla de campo no se pudo llenar en el panel, se fotografía (cámara o galería, de a una o en tanda) y se sube a la bandeja del panel, que la lee de fondo con el modelo (con Mnemo, el que la cuenta tiene para leer imágenes: Ajustes → Modelos → Plantel, «leer imágenes», en Mnemo) y la guarda cifrada; A y K la revisan con la foto al lado de la grilla (corrigen celdas, descartan filas), la cotejan con la base (qué fila crea una ficha, cuál completa otra, cuál choca, cuál dice «No autoriza») y la cargan con el folio del papel y «Capturado por»; las autorizaciones quedan declaradas hasta confirmarlas con el papel. Cada planilla tiene su enlace (`/importar?planilla=<id>`). Solo el administrador y los coordinadores suben, cotejan y cargan fotos (cuáles de los dos, en **Ajustes → Planillas físicas por foto**), con el compromiso de confidencialidad 2026-11-v2, que lo permite; los planilleros entregan el papel y quedan como «Capturado por». Ver [`docs/agente.md`](docs/agente.md#planillas-físicas-por-foto). |
| **Ajustes** | Política de contacto y horario, aviso de privacidad y Responsable, datos sensibles, presupuestos diarios y sesiones, el asistente (su conexión con Mnemo, quiénes lo usan, si propone cambios, Mnemo para coordinadores, días que se guardan las conversaciones, mensajes por día, la respuesta inmediata y su voz: la del navegador o una voz clonada en Mnemo, con «Probar voz»), puestos de votación y elección vigente, campos propios del perfil (texto, número, sí/no, lista, fecha; sensibles o no), catálogo de necesidades, grupos y roles, y auditoría con filtros. Las **planillas físicas por foto** (si las suben el administrador, los coordinadores o los dos, cuántas horas se guardan, si se leen otros formatos y, si el compromiso vigente no lo permite, el botón para pasar al 2026-11-v2), los **agentes externos por MCP** (quiénes crean claves de datos, si proponen cambios, llamadas y personas por día) y los **datos políticos en el asistente y por MCP** (dos casillas, encendidas por defecto). La política de contacto, los presupuestos, las sesiones, el asistente, las planillas por foto, los agentes por MCP y los datos políticos solo los cambia el administrador (y solo él conecta Mnemo); el coordinador los ve en solo lectura. |
| **Asistente** | Un botón flotante abre, en cualquier vista, un asistente de IA que usa los modelos y los créditos de la cuenta de Mnemo que el administrador conecta en **Ajustes → Asistente** (inicia sesión en Mnemo y da permiso: no se copian claves) y trabaja con la sesión de quien pregunta: busca personas (con los datos políticos que el panel le muestra a cada rol: tipo de persona, «Liderado por», listas y la lista de líderes con sus conteos, salvo que el administrador los apague), resume indicadores y pendientes, hace **análisis avanzados** con su gráfico en el chat (cobertura por puesto y ritmo a una meta, barrios desatendidos, horas que más contestan, intentos, el equipo, calidad de captura, qué explica un cambio, efecto de las reuniones) y un **diagnóstico** de qué priorizar con enlaces a Habitantes, siempre con agregados que ocultan las cifras pequeñas; atiende las colas de **Calidad de datos** (duplicados, conflictos de cédula, situaciones, solicitudes de los titulares sin decir de quién son, lugares sin reconocer) y el historial de cada persona; lee las **planillas físicas por foto** que el administrador o un coordinador le adjuntan con la cámara del chat, pregunta lo dudoso y las coteja con la base; prepara reuniones, muestra cosas en el mapa (vuela a un lugar, filtra, resalta personas) y abre vistas y fichas. Cada pregunta recibe primero una **respuesta inmediata** (una o dos frases con la idea general) mientras prepara la completa o la presentación; con la presentación abierta y su voz encendida, la sala la oye antes del plan. Lo que escribe en la base (notas, acercamientos, fichas, reuniones, el tipo de persona y el líder, la carga de una planilla fotografiada, la unión de fichas duplicadas con su vista previa…) lo propone en una tarjeta con los valores exactos y solo se guarda si se aprueba; nunca exporta, suprime datos, confirma autorizaciones ni toca usuarios o ajustes. Un agente externo (Claude Desktop u otro cliente MCP) puede leer, analizar o **proponer** cambios con una **clave de datos** de Mi cuenta (leer personas, solo el administrador; 30 días; solo en la cabecera): cada propuesta se aprueba en **Mi cuenta → Agentes por MCP**, y el menú cuenta las que esperan. Con la misma conexión, también trabaja con los documentos, el calendario y los formularios de la administración, y puede narrar la presentación y leer sus respuestas en voz alta con una **voz clonada en Mnemo** (si no llega, con la del navegador). Por defecto lo usan el administrador y los coordinadores; planilleros y consultores, si el administrador los habilita. Ver [`docs/agente.md`](docs/agente.md). |
| **Presentación** | La propuesta 2028–2031 del sitio público dentro del panel (todos los roles), con su capítulo y paso a la vista, pantalla completa (sin el menú y con el asistente a la vista) y una ventana aparte para el proyector: el asistente la recorre, la explica con los datos de cada paso y pone en pantalla una frase corta (nunca datos de habitantes). Para explicar arma un **plan en flujo**: el panel lo escribe y la sala lo ve y lo oye desde su primer paso, a los pocos segundos, mientras el resto se escribe ([`docs/velocidad.md`](docs/velocidad.md)). La **pantalla en off** es la misma presentación sin controles para el proyector: solo cambia cuando se le pide algo al asistente o a un agente externo por MCP (con la clave de la presentación, en Mi cuenta, que no ve datos de personas). Ver [`docs/agente.md`](docs/agente.md#pantalla-en-off-y-agentes-por-mcp). Con el panel desplegado aparte, la variable `SITIO_URL` dice dónde está el sitio. Ver [`docs/agente.md`](docs/agente.md#cómo-se-usa). |

**Nueva persona y Completar.** Los dos formularios van en el orden de los datos principales: nombre, cédula, sexo,
edad, teléfono, fecha de nacimiento, correo, dirección, barrio o vereda, zona (sale del barrio), líder, votante y
concejal con «Liderado por» (la barra para buscar al líder o concejal), perfil profesional, ocupación, estado civil y
jefe de hogar. Después van, plegados, el puesto y la mesa de votación y las necesidades (y en Completar, «Más datos»);
la autorización sigue a la vista. En Completar lo que ya tiene se ve fijo y solo se escribe lo que falta (completar
nunca reemplaza: un valor distinto queda como alterno, y un tipo o un líder que ya tiene no se quitan). El tipo y el
«Liderado por» los ponen A, K y P: P, al registrar a alguien siempre y en Completar solo si la persona es de su zona o
la registró él (si no, el formulario no trae ese bloque). A y K buscan al líder por nombre o cédula en la lista
completa; P, por nombre (3 letras o más) o por la cédula completa, en toda la campaña. Mientras se escribe el alta,
**«¿Es alguna de estas?»** busca por el nombre y también por la cédula sola: la misma cédula (actual o anterior) para
todos los roles y, para A y K, las que empiezan por lo escrito (5 dígitos o más); P no recorre la base por partes de un
número. Si P elige **Es esta** y esa ficha no es de su zona, lo demás se completa igual y un aviso dice que el tipo y
el líder no se marcaron.

**Fechas, horas y listas en cualquier dispositivo** (`web/js/campos.js`). Las fechas se escriben como **dd/mm/aaaa** y
las horas como **hh:mm** (24 horas) con el teclado numérico, igual en Android, iPhone, Windows o Mac y sin importar el
idioma del teléfono: las barras y los dos puntos se ponen solos, se acepta «7/3/85», «07031985» o una fecha pegada
como 1985-03-07, y una hora como «930», «15:30» o «3:30 pm». El ícono de al lado abre el calendario o el reloj del
sistema para quien prefiera tocar. Lo que no es una fecha (31/02, un mes 13, una fecha futura de nacimiento) se dice
al salir del campo y el formulario no se envía con eso. Al servidor sigue llegando AAAA-MM-DD y HH:MM. En el celular y
en pantallas táctiles, las listas de **2 a 15 opciones** se ven como chips que se eligen con un toque (tocar otra vez
la elegida la quita, si el campo puede quedar vacío; en las barras de filtros cada filtro ocupa una sola fila que se
desliza de lado); las más largas (barrios y veredas, líderes) siguen como lista, y en el computador con ratón todo se ve
como lista. Un formulario no se guarda con una fecha mal escrita: el campo dice qué falla (las vistas que guardan con
un clic, sin enviar el formulario, preguntan a `fechaMalEscrita` de `ui.js`). Para dejar un campo como estaba: `data-nativo` en una fecha u hora y
`data-lista` en una lista; `data-vacio="…"` muestra la opción vacía como un chip (p. ej. «Vigentes») y
`data-chip-corto` pone la sigla en el chip (CC, TI, CE…). Las fechas que antes se mostraban crudas (aaaa-mm-dd en el
mapa, en «Otros valores» y en los conflictos, y las semanas «2026-S46» de los indicadores) se leen como «7 mar 1985» o
«9–15 nov 2026».

## Cómo se cruzan y se ubican los datos

- **Agrupar trámites por persona.** Nombre normalizado (mayúsculas, sin tildes, sin signos). Dos escrituras parecidas
  («FABIO MAURICO» / «FABIO MAURICIO») se unen solo si además comparten teléfono, correo o ficha.
- **Cruce por nombre con la base de cédulas** (`app/pipeline/cruce.py`). Cada palabra pesa según lo rara que es (un
  «MARIA» pesa poco; un «ZAPATEIRO», mucho), se toleran errores de digitación (Jaro-Winkler) y variantes fonéticas
  (JHON/JOHN, NUVIA/NUBIA, YANETH/JANETH), y no importa el orden de nombres y apellidos. Un nombre de pila distinto
  resta (hermanos, madre e hija). Compartir teléfono o correo confirma un nombre parecido, pero no vuelve parecido un
  nombre distinto: en una familia todos dan el mismo celular. Lo seguro se une solo; lo dudoso va a **Calidad de datos**.
  Dos nombres de pila distintos no se unen aunque compartan ficha o celular, y un mismo nombre con fichas y teléfonos
  distintos queda como dos personas que también pasan por revisión. Si dos cédulas apuntan a la misma ficha, ninguna se
  une sola: las dos van a revisión.
- **Revisión en bloque** (`app/unificacion.py`, `GET /api/coincidencias/grupos` y `POST /api/coincidencias/lote`, solo
  administrador y coordinador). Las coincidencias pendientes se agrupan en componentes conexos: si A se parece a B y B
  a C, unir es unir las tres, así que se deciden juntas. Las señales se calculan sobre las fichas de ahora (no sobre el
  puntaje guardado, que se calculó contra la ficha de entonces): a favor, un teléfono o un correo en común (también de
  los trámites), la cédula de una entre las anteriores de la otra, la misma fecha de nacimiento exacta y, con menos
  peso, la misma dirección o barrio, la misma ficha del hogar (también la comparten los parientes), una edad parecida,
  el mismo puesto, el nombre y que una sola tenga cédula; en contra, sexo distinto, edades o fechas que no casan, otro
  nombre de pila (DANIEL/DANIELA, JUAN/CARLOS, con las mismas reglas del cruce), un homónimo sin nada en común y dos
  filas de la misma base sin cédula. Cada grupo queda en un nivel: **muy probable** (nada en contra y un nombre muy
  parecido con una señal fuerte, o dos señales fuertes), **probable** (también, como mucho, si una ficha no autorizó
  y otra sí o está pendiente: al unir gana el «no» y se borran los datos sensibles de la otra, así que nunca entra en
  «Unir las N muy probables»), **dudoso** (algo en contra, también entre dos fichas del grupo sin coincidencia
  directa, o más de 6 fichas) o **bloqueado** (dos cédulas distintas o un par que una persona ya marcó como distinto,
  aunque una de las dos se haya unido después). El mismo par en los dos órdenes (el de la importación y el reporte de alguien del equipo) se
  evalúa junto: cuentan los motivos y las notas de los dos. La ficha que se conserva es la que tiene cédula (si no, la
  más completa) y la vista previa muestra qué valor queda en cada campo y cuáles pasan a alternos. La ubicación pasa
  entera, con su dirección, de la ficha mejor ubicada (punto marcado a mano, placa del casco, barrio elegido a mano,
  centro del lugar; a igual rango, la que tiene dirección): la dirección de la conservada puede pasar a alternos, porque
  la ficha unida se vuelve a ubicar con la dirección que queda. La edad declarada llega con la fecha en que se declaró.
  Al resolver en lote,
  cada grupo se vuelve a validar entero antes de tocarlo (pares todavía pendientes, una sola cédula, ningún rechazo
  anterior, las fichas que quedan conectadas sin las excluidas), las fichas se unen en estrella en la que se conserva,
  las marcadas como «no es la misma» quedan como personas distintas, y la ubicación se recalcula una sola vez al final.
  Unir en lote toma el mismo turno que la importación: no corren a la vez.
- **Normalización de direcciones** (`app/pipeline/direcciones.py`). «BARRIO TRES DE OCTUBRE CALLE 49 # 45  12» →
  `CL 49 # 45-12, B. TRES DE OCTUBRE`; «CLL 52 N 4610» → `CL 52 # 46-10`; «VEREDA X-10» y «K-5» se reconocen; corrige
  palabras pegadas («ESPERANZAMANZANA»), manzana/lote, fincas y referencias («FRENTE AL PARQUE»). Las referencias
  («FRENTE A…», «DONDE…») y el nombre de la finca no cuentan como lugar, y una placa del casco decide entre un barrio
  y una vereda que se llaman igual.
- **Georreferenciación** (`app/pipeline/geocodificador.py`), de lo más preciso a lo menos:
  1. *Dirección con placa en el casco urbano*: una grilla de nomenclatura armada con los cruces de calles y carreras
     de OpenStreetMap (`geo/grilla_casco.json`) se ajusta localmente y ubica la placa, incluso en calles que OSM no
     tiene con nombre.
  2. *Barrio, vereda, caserío o centro poblado* del nomenclátor (`geo/gazetteer.json`: 62 veredas catastrales de la
     Gobernación de Antioquia con polígono, centros poblados del DANE, OSM, sedes educativas). En las veredas se usa
     el núcleo poblado (caserío o escuela) y no el centro del polígono.

     El **barrio o vereda de su propia columna** («Barrio o vereda» de la base general y de la planilla de campo) se
     pega al final de la dirección y queda además aparte, en el origen de la fila (`origen[].datos.lugar_texto`, con
     su fuente). Una descripción («AL LADO DE LA ESTACION 3», «CERCA DEL MANANTIAL VIA PRINCIPAL», «ESTADERO LAS
     MIRLAS») puede tapar lo que sigue, así que `georreferenciar` lo usa (`importar.barrio_declarado`,
     `Nomenclator.con_declarado`): si la dirección sola no da lugar, o da uno que no es el declarado ni está dentro de
     él, el declarado cuenta como escrito al final con su palabra clave («VEREDA X-10», «BARRIO EL PRADO»,
     «CORREGIMIENTO SAN MIGUEL DEL TIGRE»: `PALABRA_TIPO`) y deciden las reglas de siempre. La placa del casco sigue
     eligiendo entre homónimos («LA PAZ» barrio o vereda), un lugar de la dirección que está dentro del declarado (un
     barrio de un centro poblado, una vereda del corregimiento) sigue ganando y lo puesto a mano (`geo_manual`) no se
     toca. El barrio de una fila solo acompaña a la dirección de esa fila: si la dirección de la ficha vino de otra
     fuente o alguien la cambió en el panel, deja de contar. Un barrio declarado que el nomenclátor no reconoce queda
     como lugar escrito (`lugar_texto`) y aparece en Calidad de datos para crearlo o agregarlo como alias. La base con
     cédula y los trámites no traen una columna de barrio: su dirección se ubica sola, como antes.
  3. Barrios sin coordenada pública: la mediana de las direcciones con placa que caen en ellos; si no hay, el
     administrador los ubica una vez en **Calidad de datos → Barrios y veredas** y todas sus personas quedan ubicadas.

  Cada coordenada guarda su precisión. El mapa dispersa visualmente los puntos de barrio o vereda para el mapa de
  calor, sin tocar el dato guardado. Los barrios que no tienen coordenada pública aparecen en el panel como «lugares
  sin punto» y se resuelven ubicándolos una vez en el mapa.
- **La cédula manda** (`app/pipeline/fuentes.py`, `importar.py`). Cada fila de una fuente con cédula (base unificada o
  planilla de campo) sigue una cascada: la fila ya vinculada a una ficha la actualiza sin comparar nombres; una cédula
  que ya existe solo completa esa ficha si el nombre coincide (si no, queda un *conflicto de cédula* y no se mezcla
  nada); una cédula anterior de otra ficha también va a conflicto; el resto se cruza por nombre en lote, y una fila sin
  cédula solo se une sola a una ficha con cédula si además comparten teléfono o correo. Dos cédulas distintas nunca se
  unen, y una cédula que ya existe nunca cambia por importación. Una cédula a un dígito de otra con casi el mismo nombre
  deja un aviso de posible digitación.
- **Base general de la campaña** (`app/pipeline/lectores.py:leer_general`, fuente «general»). Se reconoce por el
  documento (CC o Cédula), el nombre (también «NOMBRE COMPLETPO») y una columna de la campaña (Líder, Liderado por,
  Votante, Concejal, Grupo o Tipo), y sigue la misma cascada de la cédula: una persona que ya estaba en otra base se
  completa, no se duplica. Repara los textos mal codificados («LÃ­deres» → «Líderes»), suma todas las columnas de
  teléfono aunque se repitan, quita los espacios invisibles de la cédula y salta las filas vacías. Del **Grupo** salen
  el tipo de persona (Votante → votante; Líderes y Coordinadores → líder; Candidato al concejo → concejal; «Líder
  confirmado» = sí → líder) y lo demás va a listas (Familias en acción, Eventos, Bd externa…). **Líder** con «cédula -
  nombre» (o la columna Liderado por) es quien trajo a la persona: se enlaza por la cédula; si ese líder no tiene fila,
  entra como una fila más (si no estaba en la base, se crea su ficha), y queda marcado como líder. No se enlaza si su
  ficha tiene otro nombre (una cédula mal escrita: queda un conflicto de cédula) ni si alguna de las dos no autorizó.
  Profesión → perfil profesional; votos, municipio, elección y una fecha de nacimiento que no es una fecha quedan en el
  origen de la fila. La importación nunca quita un tipo ni vuelve a marcar uno que alguien cambió a mano, y no vuelve a
  poner un líder que alguien quitó (`lideres_quitados`). Para P y C esta base se ve como «otra base».
- **Nada se pierde**: cada campo guarda de qué fuente vino (`procedencia`). Un campo vacío se llena; uno con otro valor
  solo lo reemplaza una fuente de más confianza (planilla sobre base con cédula, base con cédula sobre trámites) y
  nunca lo que puso una persona en el panel; el valor que no queda pasa a `alternos`. Todos los teléfonos de todas las
  fuentes se suman a la lista de la persona: un número marcado como equivocado o retirado no se reactiva al reimportar.
  Todo se decide en la escritura, con condiciones sobre lo guardado: lo que se edite en el panel mientras corre la
  importación no se pisa. Los trámites se identifican por su ID o, si no lo tienen, por ficha, fecha, tipo y nombre.
  Las personas suprimidas no se vuelven a crear (por ninguna de sus cédulas), y a quien no autorizó no se le agrega
  ningún dato. El barrio o vereda elegido a mano en una ficha se conserva, y si ese lugar cambia de punto la persona
  se mueve con él; un punto puesto a mano en el mapa no se mueve. Una sola importación corre a la vez.
- **Planilla de campo**: la plantilla (`GET /api/plantillas/planilla.xlsx`, botón en **Importar y exportar**) trae
  listas desplegables, la hoja «Puestos» con el catálogo vigente y la hoja «Aviso» con el aviso de privacidad para
  imprimir. Se escribe la cédula dos veces: si no coinciden, la fila entra sin cédula y queda un aviso. Las
  autorizaciones «declaradas en planilla» valen para la ficha pero no habilitan llamadas hasta que el administrador
  las confirme con la evidencia física.
- **Puestos de votación** (`geo/puestos_yondo.json`): catálogo DIVIPOL de las presidenciales de 2026 (7 puestos,
  50 mesas, 16.121 habilitados), validado con el Boletín 98 de la Registraduría. «CABECERA MUNICIPAL» es ambigua
  (dos puestos) y queda «por confirmar»; lo que viene de la base con cédula o de fichas viejas también, porque no se
  sabe de qué elección es. Para otra elección se cargan sus puestos y se cambia la elección vigente en **Ajustes**.

## Seguridad

- Usuario y clave en las variables `ADMIN` y `password` (también `admin` / `PASSWORD`), comparadas en tiempo constante.
- Sesión con token aleatorio en cookie `HttpOnly`, `SameSite=Strict` y `Secure` en producción; en el servicio único
  va con `Path=/panel/`, así el navegador no la manda al sitio público. En MongoDB solo queda el hash y la sesión
  caduca sola (índice TTL). CSRF obligatorio en todo lo que cambia datos.
- Límite de ingreso: 5 intentos fallidos por IP bloquean esa IP hasta 15 minutos; con muchos fallos en total cada
  intento espera un retroceso corto y creciente (como mucho 60 s). El navegador que ya ingresó guarda una marca
  firmada con la credencial vigente (sin datos) y no compite por ese turno: una inundación desde muchas IPs no deja
  fuera al administrador. La IP sale de la cabecera que pone el borde de Railway, no de la que el cliente puede
  falsificar.
- Las sesiones se invalidan solas si cambian `ADMIN` o `password`. Las peticiones a la API sin sesión se rechazan
  antes de leer el cuerpo (no se procesan cargas de archivos anónimas).
- El ingreso fallido no guarda lo que se escribió en el campo usuario.
- Cabeceras: CSP estricta sin scripts de terceros (MapLibre va incluido en el repositorio), `X-Frame-Options: DENY`,
  `noindex`, `no-store` en la API, HSTS en producción. Sin documentación pública de la API. uvicorn arranca con
  `--no-server-header`: ninguna respuesta anuncia `server: uvicorn`.
- Auditoría de cada ingreso, edición, fusión, exportación e importación (usuario, fecha, IP y qué cambió).
- Las búsquedas no quedan en los registros: uvicorn arranca con `--no-access-log`, porque su log de acceso imprime
  la URL completa (`/api/buscar?q=<cédula>`, `/api/personas?q=<teléfono>`, `/api/exportar.xlsx?q=...`) y Railway
  guarda la salida del servicio. Según Railway, sus registros HTTP del borde guardan solo la ruta, sin `?q=...`.
- Exportaciones protegidas contra inyección de fórmulas en Excel; omiten a quien marcó «No autorizó».
- El asistente ([`docs/agente.md`](docs/agente.md)): los tokens de la conexión con Mnemo (cifrados en la base, con una
  clave que sale de `ADMIN` y `password`) y la clave de Anthropic del modo directo solo viven en el servidor; el
  navegador nunca los ve ni habla con Anthropic o Mnemo (CSP `connect-src 'self'`): para conectar, solo navega a la
  página de permisos de Mnemo y vuelve (OAuth con PKCE y el `state` atado a la sesión). Las herramientas del panel
  llaman por dentro a la misma API con la sesión de quien conversa: los mismos permisos, alcances, presupuestos,
  lecturas y auditoría que en la interfaz. No hay herramientas para exportar, suprimir, confirmar autorizaciones,
  usuarios ni ajustes; importar y unir, solo de una forma (cargar una planilla fotografiada después de cotejarla y unir
  duplicados con la vista previa, A y K), y toda escritura espera la aprobación de la persona. Su respuesta se pinta
  como texto, nunca como HTML, y el registro solo guarda el tipo de cada error, nunca lo conversado. La voz clonada solo
  dice lo que el panel generó (la narración por referencia al plan guardado y las frases de una respuesta con una firma
  HMAC del servidor; nunca un texto libre del navegador), la hacen sonar solo los roles que elige el administrador y no
  se guarda ni se registra lo dicho.
- Las fotos de planillas: la subida pide la sesión, el permiso `importar` (solo A y K: planilleros y consultores
  reciben 403), el rol y un compromiso de confidencialidad que lo permita antes de leer el cuerpo, con su propio límite
  de tamaño y sus cupos; solo JPEG o PNG con la firma igual al tipo, sin metadatos (EXIF, GPS, comentarios) ni nada
  después del fin de la imagen; se guardan cifradas (AES-GCM, con una llave que sale de `ADMIN` y `password`: un
  respaldo de la base no las abre) y solo las ven A y K; en el chat solo se adjuntan las propias.
- Los agentes por MCP con datos: la clave de datos solo va en `Authorization: Bearer`, vence a los 30 días y se vuelve a
  comprobar en cada petición; cada llamada usa una sesión interna de la persona que nunca sale del servidor, con sus
  permisos, sus lecturas y la auditoría (`via: "mcp"`); lo que el agente propone se aprueba con la sesión de quien
  aprueba, una propuesta a la vez.

## Protección de datos personales (Ley 1581 de 2012)

La base tiene datos personales y algunos **sensibles** (afiliación política, condición de víctima, salud). Exigen
autorización previa, expresa e informada del titular, una finalidad informada y atender consultas, correcciones y
supresiones. Para eso están el campo **Autorización de datos** (con fecha) de cada ficha, el indicador del panel y la
opción **Suprimir datos**, que vacía la ficha y todas las fichas que se unieron con ella, borra sus coincidencias y el
detalle de su auditoría, y deja solo huellas cifradas (HMAC con una clave aleatoria guardada en la base) de su
cédula, sus trámites y su ficha o celular junto con el nombre, para que las próximas importaciones no la vuelvan a
crear. Nunca se guarda el nombre solo: otra persona con el mismo nombre sigue entrando. Los datos que provienen de
bases oficiales (por ejemplo, las del SISBÉN) solo pueden usarse
para la finalidad con la que se recogieron; revise con un abogado el uso que se le dará a la base antes de operarla.

El **asistente** le manda al modelo, que corre fuera del panel (en Mnemo y el proveedor de modelos de esa cuenta, o en
Anthropic en modo directo; posiblemente en el exterior), lo mínimo de cada persona: cédula y teléfonos enmascarados,
nunca datos sensibles (salud, etnia, discapacidad, víctima) y nada de quien marcó «No autorizó». Los **datos
políticos** (el tipo de persona, el «Liderado por», las listas y los líderes con sus conteos: afiliación política, un
dato sensible del art. 5) le llegan solo como el panel se los muestra a cada rol (A y K, todo; P, el tipo y el líder
en las fichas de su zona, y solo suma; C, nada), y solo mientras **Ajustes → Datos políticos en el asistente y por
MCP** esté encendido (lo está por defecto); sus instrucciones le prohíben deducir o adivinar la afiliación de nadie o
usarla para excluir o presionar, y todo cambio del tipo o del líder pasa por una tarjeta. Sus conversaciones se borran
solas a los días fijados en **Ajustes** (30 por defecto) y **Suprimir datos** borra también las conversaciones donde
aparecía la persona. Con la voz clonada de Mnemo, a Mnemo y, a través de Mnemo, a su proveedor de voz (fal.ai y el
modelo de voz elegido) va solo el texto de cada frase que se dice (la narración, o las frases de una respuesta de una
conversación sin datos de habitantes); ni el panel ni Mnemo lo guardan (el proveedor de voz, según sus términos). Es
una transmisión internacional de datos personales: antes de encenderlo para el equipo, revise con un abogado el aviso
de privacidad y la autorización ([`docs/agente.md`](docs/agente.md)).

Hay una **excepción documentada**: la foto de una **planilla física** (nombres, cédulas, teléfonos, fechas de
nacimiento, firmas) va **entera** al proveedor del modelo, en una llamada de lectura aparte, sin herramientas ni
conversación; al asistente le llega lo leído enmascarado. Por defecto solo se lee la planilla de campo del panel (sin
columnas sensibles), una foto de una cédula se rechaza y se borra, y el aviso de la cámara pide tapar las columnas de
salud, etnia, víctima o políticas y borrar la foto del teléfono. La foto y lo leído se guardan cifrados y se borran a las horas
de **Ajustes** (24 por defecto) o al cargar la hoja; queda el SHA-256 de la foto y el folio del papel. Lo leído de
quien marcó «No autoriza» se reduce a su nombre, cédula y barrio, el de quien pidió la supresión no se guarda, y las
autorizaciones leídas quedan «declaradas en planilla» (no habilitan el contacto) hasta que A o K las confirmen con el
papel. Las fotos las toman y las suben solo el administrador y los coordinadores. **Antes de encender las planillas
por foto con datos reales** hace falta la revisión jurídica del aviso de privacidad (la transmisión de imágenes
completas). La versión nueva del compromiso de confidencialidad (2026-11-v2, la de defecto) ya deja fotografiar
planillas físicas, solo para subirlas por el panel y nunca cédulas ni otros documentos, y pide borrar la foto del
teléfono después de subirla; con una versión anterior, nadie sube fotos. Con una **clave de datos por MCP**, lo que
lee el agente externo sale del panel hacia el cliente que elige la persona: leer personas es solo del administrador,
cada entrega queda registrada, hay topes diarios, no sale nada de quien no autorizó y los datos políticos salen solo
con su casilla de MCP encendida; el aviso también tiene que cubrirlo
([`docs/agente.md`](docs/agente.md#agentes-por-mcp-con-datos)).

## Desplegar en Railway

**Un solo servicio (lo habitual).** El servicio del sitio público sirve también el panel: la raíz del repositorio
tiene `railpack.json`, que instala `requirements.txt`, construye el sitio (`scripts/build_data.py` y
`scripts/build_site.py` con `PANEL_URL=/panel/`) y arranca `admin/servidor.py`:

| Dirección | Qué sirve |
|---|---|
| `/` , `/atlas`, `/propuesta` | El sitio público, con sus propias cabeceras y su CSP (`script-src 'self'` más los hashes de sus scripts en línea; `blob:` para las texturas del visor 3D). three y GSAP van como copias locales en `web/vendor/`: ningún script de un CDN de terceros. `/atlas/` redirige a `/atlas` |
| `/panel/` | El panel, con su propia CSP y la cookie de sesión acotada a `/panel/`: ingreso con `ADMIN` y `password`; al pie del Home, el enlace **Ingreso del equipo** lleva aquí |
| `/health` | Siempre 200: el sitio no depende de MongoDB ni del panel |

Pasos, en el servicio que ya publica el sitio:

1. En el proyecto: **+ New → Database → MongoDB** (si aún no existe).
2. En *Variables* del servicio del sitio: `ADMIN` = usuario, `password` = clave (12 caracteres o más) y
   `MONGODB_URI` = `${{MongoDB.MONGO_URL}}` (referencia al plugin) o la URI de Atlas.
   El asistente no necesita variables: el administrador lo conecta con su cuenta de Mnemo en **Ajustes → Asistente**
   (inicia sesión en Mnemo y da permiso). Opcionales: `MNEMO_MCP_URL` (la dirección que se sugiere al conectar),
   `MNEMO_MODELO`, `MNEMO_HERRAMIENTAS`, `AGENTE_ESFUERZO` y, para el modo directo sin Mnemo, `ANTHROPIC_API_KEY`,
   `AGENTE_MODELO` y `AGENTE_MODELO_ADELANTO` (todas en [`docs/agente.md`](docs/agente.md)). `MNEMO_TOKEN` ya no se
   usa. Sin Mnemo conectado (ni clave) el panel funciona igual, sin asistente.
   Antes de desplegar una versión nueva, saque una copia (`mongodump`): el arranque migra la base (ver más abajo).
3. Deje vacío *Settings → Deploy → Custom Start Command* (el arranque sale de `railpack.json`, con
   `--no-access-log` y `--no-server-header`) y, si tiene *Healthcheck Path*, que sea `/health`.
4. Despliegue (un *push* a `main` lo hace solo). Abra `https://<su-dominio>/panel/`, ingrese y suba los dos Excel en
   **Importar y exportar**.

Si faltan variables o MongoDB no responde, el sitio sigue en línea: `/panel/` muestra un aviso con lo que falta y el
panel se conecta solo cuando MongoDB aparece (vea *Deploy Logs*); con Atlas (`mongodb+srv://`), si el DNS falla al
arrancar, vuelve a intentar crear el panel. Con MongoDB caído, la API del panel responde 503 al instante
(cortacircuitos) y la API del panel tiene su propio límite de peticiones simultáneas: no frena el sitio. Las páginas y
archivos del panel no cuentan para ese límite, y el ingreso cuenta solo cuando su cuerpo llegó entero (si no llega en
10 s, 408): conexiones anónimas a medio enviar no dejan fuera al administrador. En *Deploy Logs* no
deben aparecer líneas `GET /api/...` al buscar.

**Aislamiento máximo (opcional).** En el servicio único, sitio y panel comparten origen: cada uno lleva su CSP y la
cookie solo viaja a `/panel/`, pero la ruta de una cookie no separa orígenes. Para que el panel quede en otro origen,
llévelo a un servicio aparte con dominio propio: cree otro servicio del mismo repositorio con **Root Directory =
`admin`** (Railpack lee `admin/railpack.json`, que arranca `app.main` con `--no-access-log` y `--no-server-header`,
el panel solo en la raíz, y `admin/Procfile` de respaldo), con *Healthcheck Path* = `/salud`, las mismas variables y
su dominio (el de Railway o uno propio, como `panel.<su-dominio>`). En el servicio del sitio defina `PANEL_URL` =
esa dirección `https://…`, para que el Home enlace allá, y quite `ADMIN`, `password` y `MONGODB_URI` (y las del
asistente), para que el sitio no tenga acceso a la base ni a las claves. En GitHub Pages (sin panel) el enlace solo
aparece si existe la variable de repositorio `PANEL_URL`.

## Trabajar en local

```bash
cd admin
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # y complete ADMIN, password y MONGODB_URI
uvicorn app.main:app --reload --no-access-log --no-server-header
```

Para probar el asistente con un modelo real, conecte un Mnemo en **Ajustes → Asistente** (en local se acepta
`http://127.0.0.1`; `MNEMO_MCP_URL` en el `.env` lo sugiere) o, para el modo directo, agregue al `.env` una clave propia
en `ANTHROPIC_API_KEY`. Sin nada de eso el panel funciona igual, y las pruebas del asistente usan un modelo y un Mnemo
simulados ([`docs/agente.md`](docs/agente.md)).

Un MongoDB local sirve con `docker run -d -p 27017:27017 mongo:7` (hace falta 4.2 o más). Comandos útiles (los
Excel, fuera del repositorio o en `admin/var/`, que Git ignora):

```bash
python -m app.cli migrar
python -m app.cli importar var/tramites.xlsx var/cedulas.xlsx
python -m app.cli importar var/planilla.xlsx --capturado-por 5
python -m app.cli georreferenciar
python -m app.cli nomenclator
python -m app.cli resumen
```

Pruebas (solo con datos inventados; las de la API necesitan MongoDB):

```bash
python -m pytest -q tests
```

Para probar el servicio único como en Railway (sitio en `/` y panel en `/panel/`), desde la raíz del repositorio:

```bash
python3 scripts/build_data.py && PANEL_URL=/panel/ python3 scripts/build_site.py
uvicorn servidor:app --app-dir admin --port 8000 --no-access-log --no-server-header
```

## Migración del esquema

Cada arranque (`db.inicializar`, en el panel, la consola y las pruebas) lleva la base a la versión de esquema vigente
(`app/migraciones.py`) antes de que el panel quede listo: arma la lista de teléfonos de cada persona (con los
números que el administrador había quitado marcados como retirados), la procedencia de cada dato, el punto, la edad
aproximada, la votación (por confirmar), los eventos de autorización y los acercamientos de las reuniones. Se puede
repetir sin daño, un solo proceso migra a la vez y un error en una ficha se anota (`meta.migracion.errores`) sin cortar
la migración. Además, en cada arranque se reconcilia lo que un código anterior haya escrito durante un despliegue o una
vuelta atrás. Mientras migra, la API responde 503.

Medido en local (MongoDB 8.0, datos inventados): migrar 12 000 fichas tarda unos 12 s y la reconciliación de cada
arranque, menos de medio segundo; importar 12 000 trámites y 700 cédulas, unos 16 s (5 s al repetir la misma
importación). En el panel desplegado aparte (chequeo de salud de 60 s), corra antes `python -m app.cli migrar` con la
misma `MONGODB_URI`. La medición se repite con
`PRUEBAS_LENTAS=1 python -m pytest -q tests/test_migracion.py -k medicion -s`.

## Estructura

| Ruta | Contenido |
|---|---|
| `servidor.py` | Servidor único de Railway: el sitio público (`site/`) en la raíz, con sus cabeceras y su CSP, el panel en `/panel/` y `/health` |
| `app/main.py` | Aplicación FastAPI, cabeceras y estáticos |
| `app/config.py`, `app/seguridad.py`, `app/db.py` | Variables de entorno, autenticación y sesiones, MongoDB (índices, nomenclátor, puestos, unión de fichas, supresión, completitud) |
| `app/modelo.py`, `app/migraciones.py` | Catálogos y reglas de la ficha (teléfonos, votación, autorización, procedencia); migración idempotente y reconciliación |
| `app/trazas.py` | La traza de las reuniones en la auditoría de las personas (qué reunión va con cada cambio) |
| `app/api/` | Endpoints: tablero y mapa, personas, líderes (`lideres.py`), reuniones, calidad (coincidencias, conflictos, solicitudes, situaciones, lugares), ajustes (ajustes, puestos, plantilla), sistema (sesión, importación, exportación, catálogos, auditoría) |
| `app/api/agente.py` | Rutas del asistente: estado, conversaciones, mensajes (también con fotos de planillas) y aprobaciones (respuesta en flujo NDJSON), preguntas por voz y la voz clonada (las voces de Mnemo y cada frase en flujo NDJSON) |
| `app/analitica.py`, `app/api/analitica.py` | Los análisis avanzados del asistente: un análisis por tipo, el diagnóstico y la protección de las cifras pequeñas (`GET /api/analitica`) |
| `app/planillas.py`, `app/api/planillas.py` | Las planillas físicas por foto: la bandeja (subir, leer de fondo, revisar, cotejar, cargar), cifrada y con su retención (`/api/planillas…`) |
| `app/api/mcp.py`, `app/sesion_interna.py` | El servidor MCP (la presentación y los datos por alcance), las propuestas que se aprueban en Mi cuenta y la sesión interna de cada llamada |
| `app/agente/` | El asistente: el turno con el modelo (`bucle.py`), de dónde sale el modelo (`proveedores.py`: Mnemo con `modelo_mnemo.py`, o Anthropic en modo directo con `llm.py`), las conversaciones (`conversaciones.py`), sus instrucciones (`sistema.py`), quién lo usa (`politica.py`), las llamadas a la API con la sesión del usuario (`interno.py`), lo mínimo que llega al modelo (`minimizar.py`), las herramientas (`herramientas/`), el cliente MCP de Mnemo (`mnemo_cliente.py`), la conexión con Mnemo (`mnemo_conexion.py`: OAuth y los tokens cifrados con `cifrado.py`), las preguntas por voz (`dictado.py`), la voz clonada de Mnemo (`voz.py`), la lectura de las fotos de planillas (`lector_planillas.py`) y el gráfico del chat (`grafico.py`) |
| `app/pipeline/` | Registro de fuentes, lectura de los Excel (también la planilla de campo), normalización, direcciones, cruce por nombre, georreferenciación e importación |
| `geo/` | Geografía pública: límite municipal (DANE MGN 2025), nomenclátor de veredas, barrios y centros poblados, grilla de calles (OSM), catálogo de puestos de votación (DIVIPOL 2026) y los scripts que los generan |
| `web/` | Interfaz (HTML, CSS y módulos JS sin compilación) con MapLibre GL incluido |
| `web/js/agente.js`, `web/css/agente.css`, `web/js/agente-mapa.js`, `web/js/agente-presentacion.js` | El botón y el panel del asistente (también la cámara de las fotos de planillas), y sus puentes con las vistas del mapa y de la presentación (`web/js/vistas/presentacion.js`, con el guion en `app/agente/guion.py`) |
| `web/js/agente-graficos.js` | Los gráficos del chat (barras, columnas, apilada y serie), validados con el mismo contrato del servidor |
| `web/js/vistas/importar.js`, `web/css/planillas.css` | Importar y exportar, con la vista **Planillas por foto** (la foto al lado de la grilla, cotejar, cargar y confirmar con el papel) |
| `web/js/voz-clonada.js`, `web/js/voz-panel.js`, `web/js/locutor.js` | La voz clonada de Mnemo en el navegador (el audio por partes con Web Audio, con la voz del navegador de respaldo), la voz única de cada ventana (la narración del plan, las respuestas habladas y la prueba de Ajustes) y las respuestas habladas del asistente |
| `docs/` | Usuarios, sesiones y permisos (`usuarios.md`), acercamientos (`acercamientos.md`), reuniones con horario, su traza y los líderes (`reuniones-y-lideres.md`), zonas del mapa (`mapa-zonas.md`) y el asistente (`agente.md`: qué hace, las planillas por foto, los análisis, los agentes por MCP con datos, cómo se conecta con Mnemo, su voz clonada, privacidad, costos, configuración y pruebas) |
| `tests/` | Pruebas con personas inventadas |
| `railpack.json`, `Procfile` | Arranque del panel en un servicio aparte (uvicorn sin log de acceso ni cabecera `server`); `railway.json` solo para servicios con *Config as Code* |

Geografía: © colaboradores de OpenStreetMap (ODbL); DANE (MGN y DIVIPOLA); Gobernación de Antioquia (catastro);
MinEducación (sedes); Registraduría Nacional (DIVIPOL y Divipole georreferenciada, datos.gov.co, CC BY-SA 4.0). Mapas base: OpenFreeMap / OpenMapTiles, Esri World Imagery; relieve: Mapzen Terrain Tiles.
