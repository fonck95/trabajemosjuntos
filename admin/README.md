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
| **Calidad de datos** | Cola de coincidencias por nombre para confirmar o descartar lado a lado; barrios y veredas sin punto para ubicarlos con un clic en el mapa; nombres escritos que no se reconocen, para crearlos o agregarlos como alias. |
| **Importar y exportar** | Subir los Excel (se reconocen por sus columnas) cuantas veces se quiera; historial de importaciones; exportar la base única. |
| **Ajustes** | Campos propios del perfil (texto, número, sí/no, lista, fecha), catálogo de necesidades, grupos y roles, y auditoría completa. |

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
- **La importación nunca pisa lo editado**: solo completa campos vacíos, y tampoco pisa lo que se edite en el panel
  mientras corre. Los trámites se identifican por su ID o, si no lo tienen, por ficha, fecha, tipo y nombre. Las
  personas suprimidas no se vuelven a crear. El barrio o vereda elegido a mano en una ficha se conserva, y si ese
  lugar cambia de punto la persona se mueve con él; un punto puesto a mano en el mapa no se mueve.

## Seguridad

- Usuario y clave en las variables `ADMIN` y `password` (también `admin` / `PASSWORD`), comparadas en tiempo constante.
- Sesión con token aleatorio en cookie `HttpOnly`, `SameSite=Strict` y `Secure` en producción; en MongoDB solo
  queda el hash y la sesión caduca sola (índice TTL). CSRF obligatorio en todo lo que cambia datos.
- Límite de ingreso: 5 intentos fallidos por IP bloquean esa IP hasta 15 minutos; con muchos fallos en total cada
  intento espera un retroceso corto y creciente (como mucho 60 s). El navegador que ya ingresó guarda una marca
  firmada con la credencial vigente (sin datos) y no compite por ese turno: una inundación desde muchas IPs no deja
  fuera al administrador. La IP sale de la cabecera que pone el borde de Railway, no de la que el cliente puede
  falsificar.
- Las sesiones se invalidan solas si cambian `ADMIN` o `password`. Las peticiones a la API sin sesión se rechazan
  antes de leer el cuerpo (no se procesan cargas de archivos anónimas).
- El ingreso fallido no guarda lo que se escribió en el campo usuario.
- Cabeceras: CSP estricta sin scripts de terceros (MapLibre va incluido en el repositorio), `X-Frame-Options: DENY`,
  `noindex`, `no-store` en la API, HSTS en producción. Sin documentación pública de la API.
- Auditoría de cada ingreso, edición, fusión, exportación e importación (usuario, fecha, IP y qué cambió).
- Las búsquedas no quedan en los registros: uvicorn arranca con `--no-access-log`, porque su log de acceso imprime
  la URL completa (`/api/buscar?q=<cédula>`, `/api/personas?q=<teléfono>`, `/api/exportar.xlsx?q=...`) y Railway
  guarda la salida del servicio. Según Railway, sus registros HTTP del borde guardan solo la ruta, sin `?q=...`.
- Exportaciones protegidas contra inyección de fórmulas en Excel; omiten a quien marcó «No autorizó».

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

## Desplegar en Railway

El sitio público (Home, atlas, propuesta) sigue siendo estático. El panel es **otro servicio** del mismo repositorio:

1. En el proyecto de Railway: **+ New → Database → MongoDB** (si aún no existe).
2. **+ New → GitHub Repo →** `trabajemosjuntos`. En *Settings* del servicio nuevo:
   - *Source* → **Root Directory = `admin`**. Railway solo baja esa carpeta y Railpack la construye con Python 3.12
     (`.python-version`, `requirements.txt`). El arranque sale de **`admin/railpack.json`** (`deploy.startCommand`:
     uvicorn con `--no-access-log`); `admin/Procfile` trae el mismo comando de respaldo. Deje vacío
     *Deploy → Custom Start Command*: si lo llena, reemplaza ese arranque y tendría que llevar también `--no-access-log`.
   - *Deploy* → **Healthcheck Path = `/salud`**. Railway solo pasa el tráfico al despliegue nuevo cuando `/salud`
     responde 200, es decir, cuando el panel ya se conectó a MongoDB; si no, ese despliegue falla y el anterior sigue
     atendiendo. En un servicio nuevo este chequeo solo se activa ahí.

   `admin/railway.json` (*Config as Code*) no basta: Railway no lo busca dentro del Root Directory, ya no deja activar
   *Config as Code* en servicios nuevos y deja de leer esos archivos el **1 de diciembre de 2026**. Solo lo usa un
   servicio creado antes que ya tenga `/admin/railway.json` en *Settings → Config-as-code → Railway Config File*
   (lleva el mismo arranque y el chequeo en `/salud`); aun así, configure el *Healthcheck Path* para cuando Railway
   deje de leerlo.
3. En *Variables* del servicio del panel:
   - `ADMIN` = usuario, `password` = clave (larga: 12 caracteres o más).
   - `MONGODB_URI` = `${{MongoDB.MONGO_URL}}` (referencia al plugin) o la URI de Atlas. Es obligatoria: en Railway el
     panel no usa un MongoDB local por defecto, así que sin ella no arranca y el registro del despliegue lo indica.

   Si estas variables quedaron en el servicio del sitio estático, cópielas al del panel (o conviértalas en
   *Shared Variables*): el sitio estático no las usa.
4. *Settings → Networking → Generate Domain*. Abra la dirección, ingrese y suba los dos Excel en **Importar y exportar**.
5. Compruebe en el detalle del despliegue que figuren el chequeo de salud en `/salud` y el comando con
   `--no-access-log`, y que en *Deploy Logs* no aparezcan líneas `GET /api/...` al buscar.

## Trabajar en local

```bash
cd admin
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # y complete ADMIN, password y MONGODB_URI
uvicorn app.main:app --reload --no-access-log
```

Un MongoDB local sirve con `docker run -d -p 27017:27017 mongo:7`. Comandos útiles (los Excel, fuera del repositorio o
en `admin/var/`, que Git ignora):

```bash
python -m app.cli importar var/tramites.xlsx var/cedulas.xlsx
python -m app.cli georreferenciar
python -m app.cli nomenclator
python -m app.cli resumen
```

Pruebas (solo con datos inventados; las de la API necesitan MongoDB):

```bash
python -m pytest -q tests
```

## Estructura

| Ruta | Contenido |
|---|---|
| `app/main.py` | Aplicación FastAPI, cabeceras y estáticos |
| `app/config.py`, `app/seguridad.py`, `app/db.py` | Variables de entorno, autenticación y sesiones, MongoDB (índices, nomenclátor, fusión, completitud) |
| `app/api/` | Endpoints: tablero y mapa, personas, reuniones, calidad, sistema (sesión, importación, exportación, catálogos, auditoría) |
| `app/pipeline/` | Lectura de los Excel, normalización, direcciones, cruce por nombre, georreferenciación e importación |
| `geo/` | Geografía pública: límite municipal (DANE MGN 2025), nomenclátor de veredas, barrios y centros poblados, grilla de calles (OSM) y los scripts que los generan |
| `web/` | Interfaz (HTML, CSS y módulos JS sin compilación) con MapLibre GL incluido |
| `tests/` | Pruebas con personas inventadas |
| `railpack.json`, `Procfile` | Arranque en Railway (uvicorn sin log de acceso); `railway.json` solo para servicios con *Config as Code* |

Geografía: © colaboradores de OpenStreetMap (ODbL); DANE (MGN y DIVIPOLA); Gobernación de Antioquia (catastro);
MinEducación (sedes). Mapas base: OpenFreeMap / OpenMapTiles, Esri World Imagery; relieve: Mapzen Terrain Tiles.
