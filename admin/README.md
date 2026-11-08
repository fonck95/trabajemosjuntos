# Panel de administración · Base única de habitantes de Yondó

Aplicación privada (con usuario y clave) para administrar la base de habitantes que se arma cruzando:

1. **Trámites por vereda**: una fila por solicitud (ID, Número de ficha, Fecha, «TRÁMITE - NOMBRE», Dirección, Correo, Teléfono, Paquete).
2. **Base unificada con cédula**: una fila por cédula, con listas de origen, puesto de votación, edad y sexo.

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
| **Habitantes** | Directorio con búsqueda (nombre, cédula, teléfono, dirección, ficha), 10 filtros combinables, orden por completitud o contacto, exportación a Excel de lo filtrado. |
| **Ficha** | Datos editables, necesidades/intereses/roles, campos propios, autorización de datos, ubicación con minimapa y ajuste manual del punto, historial (reuniones, notas, trámites), origen de cada dato y registro de cambios. Unir fichas duplicadas y suprimir datos (derecho de supresión). |
| **Reuniones** | Agenda con asistentes y personas nuevas por reunión. **Modo reunión**: buscar y agregar asistentes en segundos, registrar personas nuevas (con aviso de posibles duplicados) y «Completar» el perfil de cada asistente ahí mismo (cédula, celular, ocupación, hogar, necesidades, autorización y lo que pidió, que queda en su historial). Exporta asistentes a CSV. |
| **Calidad de datos** | Cola de coincidencias por nombre para confirmar o descartar lado a lado (con su motivo y la ficha que se conserva); conflictos de cédula (misma cédula con otro nombre, cédula anterior, posible error de digitación, cédula dictada al consultor) que nunca se mezclan solos; solicitudes de los titulares con sus plazos legales; personas reportadas como fallecidas o fuera de Yondó, para confirmar o revertir; barrios y veredas sin punto para ubicarlos con un clic en el mapa; nombres escritos que no se reconocen, para crearlos o agregarlos como alias. |
| **Importar y exportar** | Subir los Excel (trámites, base con cédula y planillas de campo; se reconocen por sus columnas) cuantas veces se quiera, con «Capturado por» para las planillas y la plantilla para descargar; historial de importaciones, con la confirmación de las autorizaciones declaradas en planilla; exportar la base única. |
| **Ajustes** | Política de contacto y horario, aviso de privacidad y Responsable, datos sensibles, presupuestos diarios y sesiones, el asistente (su conexión con Mnemo, quiénes lo usan, si propone cambios, Mnemo para coordinadores, días que se guardan las conversaciones y mensajes por día), puestos de votación y elección vigente, campos propios del perfil (texto, número, sí/no, lista, fecha; sensibles o no), catálogo de necesidades, grupos y roles, y auditoría con filtros. La política de contacto, los presupuestos, las sesiones y el asistente solo los cambia el administrador (y solo él conecta Mnemo); el coordinador los ve en solo lectura. |
| **Asistente** | Un botón flotante abre, en cualquier vista, un asistente de IA que usa los modelos y los créditos de la cuenta de Mnemo que el administrador conecta en **Ajustes → Asistente** (inicia sesión en Mnemo y da permiso: no se copian claves) y trabaja con la sesión de quien pregunta: busca personas, resume indicadores y pendientes, prepara reuniones, muestra cosas en el mapa (vuela a un lugar, filtra, resalta personas) y abre vistas y fichas. Lo que escribe en la base (notas, acercamientos, fichas, reuniones…) lo propone en una tarjeta con los valores exactos y solo se guarda si se aprueba. Con la misma conexión, también trabaja con los documentos, el calendario y los formularios de la administración. Por defecto lo usan el administrador y los coordinadores; planilleros y consultores, si el administrador los habilita. Ver [`docs/agente.md`](docs/agente.md). |

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
  lecturas y auditoría que en la interfaz. No hay herramientas para exportar, importar, unir, suprimir, usuarios ni
  ajustes, y toda escritura espera la aprobación de la persona. Su respuesta se pinta como texto, nunca como HTML, y
  el registro solo guarda el tipo de cada error, nunca lo conversado.

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
nunca datos sensibles ni listas, y nada de quien marcó «No autorizó». Sus conversaciones se borran solas a los días
fijados en **Ajustes** (30 por defecto) y **Suprimir datos** borra también las conversaciones donde aparecía la
persona. Es una transmisión internacional de datos personales: antes de encenderlo para el equipo, revise con un
abogado el aviso de privacidad y la autorización ([`docs/agente.md`](docs/agente.md)).

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
   `MNEMO_MODELO`, `MNEMO_HERRAMIENTAS`, `AGENTE_ESFUERZO` y, para el modo directo sin Mnemo, `ANTHROPIC_API_KEY` y
   `AGENTE_MODELO` (todas en [`docs/agente.md`](docs/agente.md)). `MNEMO_TOKEN` ya no se usa. Sin Mnemo conectado (ni
   clave) el panel funciona igual, sin asistente.
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
| `app/api/` | Endpoints: tablero y mapa, personas, reuniones, calidad (coincidencias, conflictos, solicitudes, situaciones, lugares), ajustes (ajustes, puestos, plantilla), sistema (sesión, importación, exportación, catálogos, auditoría) |
| `app/api/agente.py` | Rutas del asistente: estado, conversaciones, mensajes y aprobaciones (respuesta en flujo NDJSON) |
| `app/agente/` | El asistente: el turno con el modelo (`bucle.py`), de dónde sale el modelo (`proveedores.py`: Mnemo con `modelo_mnemo.py`, o Anthropic en modo directo con `llm.py`), las conversaciones (`conversaciones.py`), sus instrucciones (`sistema.py`), quién lo usa (`politica.py`), las llamadas a la API con la sesión del usuario (`interno.py`), lo mínimo que llega al modelo (`minimizar.py`), las herramientas (`herramientas/`), el cliente MCP de Mnemo (`mnemo_cliente.py`) y la conexión con Mnemo (`mnemo_conexion.py`: OAuth y los tokens cifrados con `cifrado.py`) |
| `app/pipeline/` | Registro de fuentes, lectura de los Excel (también la planilla de campo), normalización, direcciones, cruce por nombre, georreferenciación e importación |
| `geo/` | Geografía pública: límite municipal (DANE MGN 2025), nomenclátor de veredas, barrios y centros poblados, grilla de calles (OSM), catálogo de puestos de votación (DIVIPOL 2026) y los scripts que los generan |
| `web/` | Interfaz (HTML, CSS y módulos JS sin compilación) con MapLibre GL incluido |
| `web/js/agente.js`, `web/css/agente.css`, `web/js/agente-mapa.js` | El botón y el panel del asistente, y su puente con la vista del mapa |
| `docs/` | Usuarios, sesiones y permisos (`usuarios.md`), acercamientos (`acercamientos.md`), zonas del mapa (`mapa-zonas.md`) y el asistente (`agente.md`: qué hace, cómo se conecta con Mnemo, privacidad, costos, configuración y pruebas) |
| `tests/` | Pruebas con personas inventadas |
| `railpack.json`, `Procfile` | Arranque del panel en un servicio aparte (uvicorn sin log de acceso ni cabecera `server`); `railway.json` solo para servicios con *Config as Code* |

Geografía: © colaboradores de OpenStreetMap (ODbL); DANE (MGN y DIVIPOLA); Gobernación de Antioquia (catastro);
MinEducación (sedes); Registraduría Nacional (DIVIPOL y Divipole georreferenciada, datos.gov.co, CC BY-SA 4.0). Mapas base: OpenFreeMap / OpenMapTiles, Esri World Imagery; relieve: Mapzen Terrain Tiles.
