# 09 · Motor 3D, modelos profesionales y diseño

> Cómo está construido el atlas 3D (`web/`) para manejar modelos de arquitectura e ingeniería sin que la página se vuelva pesada, y cómo agregar modelos nuevos.

## 1. Optimizaciones del motor (`web/js/core.js`)

| Técnica | Qué hace | Por qué importa |
|---|---|---|
| **Un solo WebGLRenderer compartido** | El lienzo se mueve a la vista activa; cada vista tiene su escena, cámara y controles | Los navegadores limitan los contextos WebGL (≈16). Con siete vistas se ahorran seis contextos y su memoria de GPU |
| **Renderizado bajo demanda** | Solo se dibuja cuando algo cambia: cámara, animación, interacción o tema. Cada animación declara si necesita el siguiente cuadro | Una vista quieta consume 0 % de GPU; la batería del teléfono dura más |
| **Pausa automática** | No se dibuja si la pestaña está oculta o el escenario salió de pantalla (IntersectionObserver) | Cero trabajo en segundo plano |
| **Resolución adaptativa** | Mide el tiempo de cada cuadro; si pasa de ~22 ms baja el pixel ratio en pasos de 0,25 y lo recupera con holgura | Mantiene la fluidez en equipos modestos sin sacrificar nitidez en los potentes |
| **Sombras manuales** | `shadowMap.autoUpdate = false`; las sombras se recalculan solo cuando algo se mueve | El mapa de sombras es una pasada completa de la escena |
| **Iluminación por entorno (PMREM)** | Un mapa de entorno precalculado (RoomEnvironment) para materiales PBR, con tono ACES en las vistas de modelos | Los modelos con metal y vidrio se ven físicamente creíbles |
| **Geometría compartida e instancias** | Todas las cajas comparten una geometría; árboles, postes, módulos solares y partículas son `InstancedMesh` | Cientos de objetos en una sola llamada de dibujo |
| **Matrices congeladas** | Los objetos estáticos tienen `matrixAutoUpdate = false` | three.js deja de recalcular miles de matrices por cuadro |
| **Selección optimizada** | El raycasting del cursor se agrupa por cuadro de animación | Mover el ratón no dispara cálculos de más |
| **Liberación de memoria** | `disposeObject` libera geometrías, materiales y texturas al cambiar de modelo | Evita fugas de memoria en el visor |
| **Panel de rendimiento** | Botón "Rendimiento" en cada escenario: cuadros por segundo, milisegundos, resolución, llamadas de dibujo, triángulos, geometrías y texturas | Mide en vez de suponer |

## 2. Carga de modelos (`web/js/assets.js`)

- **GLTFLoader** con **Draco** (decodificador WebAssembly o JavaScript, según lo que permita el navegador), **Meshopt** y **KTX2/Basis** (texturas comprimidas que se quedan comprimidas en la GPU). Los decodificadores están en `web/vendor/`, así funcionan sin depender de otro servidor.
- **Detección de WebAssembly**: si el entorno lo bloquea, Draco usa su versión JavaScript y el modelo carga igual.
- **Caché por URL**: un modelo se descarga y decodifica una sola vez; las vistas lo reutilizan con copias que comparten geometría.
- **Nivel de detalle progresivo** (`progressiveLOD`): primero aparece el modelo liviano y luego el detallado; three.js cambia entre ellos según la distancia de la cámara.
- **Instancias desde un GLB** (`instancedFromModel`): un modelo (por ejemplo, el módulo solar) se convierte en mallas instanciadas con miles de posiciones.
- **Métricas** (`stats`): triángulos, mallas, instancias, materiales, texturas, memoria estimada de GPU y extensiones glTF usadas.

## 3. Modelos del atlas (`scripts/modelos/build_models.mjs`)

Se generan con three.js y se optimizan con gltf-transform, igual que se haría con un modelo de Revit o SketchUp:

| Modelo | Sin comprimir | Publicado | Técnicas |
|---|---:|---:|---|
| Hospital, nivel de detalle alto | 374 KB | 49 KB | 106 módulos solares como instancias GPU (`EXT_mesh_gpu_instancing`), Draco, geometría unida por material |
| Hospital, nivel de detalle bajo | 105 KB | 32 KB | Versión simplificada hecha a propósito (sin marcos ni equipos de cubierta) |
| Contenedor de baterías de 20 pies | 76 KB | 6 KB | Draco; corrugado, puertas, aire acondicionado y rejillas |
| Módulo solar de 550 Wp | 27 KB | 23 KB | 62 triángulos: las celdas son una textura, no geometría |

```bash
cd scripts/modelos
npm install
npm run build        # escribe web/models/*.glb y manifest.json
```

## 4. Réplicas de las sedes reales (`scripts/modelos/build_edificios.mjs`)

Cada dependencia pública de la microrred tiene una réplica 3D construida a partir de un levantamiento con imágenes. Ese levantamiento queda escrito en `data/edificios/<id>.json`, con el formato de `data/edificios/ESPECIFICACION.md`.

### Cómo se levanta un edificio

1. **Ubicación.** Se cruzan la web de la alcaldía, SECOP, OpenStreetMap y los letreros visibles en Street View. Cada sede declara su confianza: alta, media o baja.
2. **Huella.** Se mide sobre la imagen satelital Esri World Imagery (zoom 19 ≈ 0,30 m por píxel). `scripts/geo/trace.py` superpone los rectángulos medidos sobre el satélite, y se itera hasta que coinciden con los bordes de la cubierta.
3. **Alturas, cubierta y fachada.** Salen de los panoramas de Google Street View (`scripts/geo/cobertura.py`, `sv_pano.py`). Hay 2.100 panoramas en el casco urbano, casi todos de 2013–2014; se contrastan con el satélite, que es más reciente, y con fotos web.
4. **Comparación con la foto.** `scripts/modelos/render_vista.mjs` dibuja el modelo desde la misma posición, rumbo y campo visual del panorama. Luego genera una imagen lado a lado y una mezcla al 50 % para corregir siluetas, pendientes, puertas, ventanas y colores.
5. **Verificación independiente.** Un segundo revisor vuelve a medir y compara con panoramas distintos.
6. **Adecuaciones del proyecto.** Se diseñan sobre la cubierta real:
   - cuántos módulos de 550 Wp caben de verdad (con retiros);
   - dónde van las baterías, los inversores y la domótica;
   - qué obras previas hacen falta: cambio de cubiertas de fibrocemento, refuerzos, puesta a tierra.

Las imágenes de Google y Esri se usan solo como referencia de levantamiento: están en `data/geo/img/`, que git ignora. En la web cada sede enlaza a su panorama en Google Maps.

### Qué produce el generador

- **Capa `existente`:**
  - Muros con textura en metros. En LOD0 los vanos se recortan en el muro y llevan jambas de 12 cm (menos en paños delgados) y un fondo oscuro.
  - Ventanas con marco, parteluces cada ~0,75 m, travesaño si son altas, vidrio hundido, alféizar y dintel. Las de tipo `reja` llevan barrotes cada 12 cm y dos pletinas; las celosías y calados, un paño de bloque con huecos de 15 cm.
  - Puertas con marco y hojas de tableros (dos hojas si pasan de 1,3 m) con manija. Los portones de más de 2,6 m son cortinas enrollables de lamas.
  - Zócalo y bandas de entrepiso, interrumpidos en los vanos y envolviendo las esquinas.
  - Corredores y estructuras abiertas con columnas de basa y capitel, vigas y piso elevado. En corredores anchos no se ponen las columnas que quedarían pegadas a un muro.
  - Cubiertas a dos aguas, a cuatro aguas, a una agua, curvas o planas, con texturas de zinc, fibrocemento, termoacústica o teja. Llevan:
    - tapa de alero y tablas de borde;
    - caballetes en cumbreras y limatesas;
    - cielo raso bajo el alero en edificios cerrados;
    - canal redonda en los aleros y bajantes por el muro, que esquivan vanos y tramos tapados;
    - antepecho con remate en las cubiertas planas.
  - Letreros en relieve con tildes compuestas.
  - Entorno:
    - suelos escalonados (predio, zona verde, parqueadero, patio, plaza, andén y cancha, cada uno 2,5 cm sobre el anterior) con sardinel;
    - rejas con sobrecimiento, parales, pasamanos y barrotes; mallas eslabonadas con tubos y paño transparente; muros con columnetas y remate;
    - árboles de copa con varios lóbulos en tres verdes (instanciados);
    - tanques elevados, astas, torres arriostradas y postes con cruceta, aisladores y luminaria (con caja de medidor si la especificación la menciona);
    - condensadoras de aire acondicionado con ventilador, rejilla y ménsulas (o patas si están sobre una losa);
    - plantas eléctricas.
- **Capa `adecuaciones`:**
  - Módulos de 550 Wp con marco de aluminio, celdas por textura y caja de conexiones, en un solo lote instanciado (`solar/modulos`). Van 14 cm sobre el faldón, sobre rieles de aluminio y anclajes hasta la cubierta (`solar/soportes`). En losa van en racks con patas y lastres.
  - Marquesinas solares con columnas (placa y dado), vigas, correas bajo cada fila, riostras y canal. Si son bajas (estructura en tierra), llevan dos patas por pórtico.
  - Baterías: gabinetes con zócalo, dos puertas, manijas, rejillas, señal de riesgo eléctrico y aire acondicionado en el de conversión, o contenedores de 10 y 20 pies con corrugado, puertas, barras de cierre, aires, rejillas, rótulos, caja de cables y baliza. En los dos casos, losa y bolardos.
  - Inversores de muro con disipadores, pantalla y seccionador de CC.
  - Cargador de vehículo eléctrico con bahía pintada.
  - Cubierta nueva cuando hay que reemplazar la existente.
  - **Conexión** (nodo `adecuaciones/conexion`, ver abajo).
- **Instancias por capa.** El generador crea las instancias GPU (`EXT_mesh_gpu_instancing`) dentro de cada capa (módulos y árboles), para que el botón "Hoy / Con el proyecto" pueda apagar una capa completa. La función `instance()` de gltf-transform no sirve aquí porque las mueve a la raíz.
- **Pocas llamadas de dibujo.** Los colores de la especificación van por vértice (`COLOR_0`). Así, todas las superficies del mismo acabado comparten un material:
  - `pintura`: pañete, zócalos, bandas, puertas, cercas;
  - `pintura_satin`: letreros y equipos;
  - `metal_pintado`: marcos, rejas, canales, estructuras;
  - un material por tipo de muro con textura y uno por tipo de cubierta.
  - Cada nodo queda con una primitiva por material: entre 33 y 48 llamadas por sede en LOD0 y entre 23 y 34 en LOD1.
- **Dos niveles de detalle.**
  - `_lod0` lleva vanos recortados, carpintería, barrotes, canales, bajantes, rieles y codos de los ductos.
  - `_lod1` (la web lo usa a más de 140 m) lleva los vanos como paneles 4 cm delante del muro, los módulos como planos con textura, rejas simplificadas y ductos más gruesos sin codos.
  - Los dos van comprimidos con Draco (posiciones de 16 bits) y tienen copia `.glb.json`. Presupuesto medido: LOD0 hasta unos 100 000 triángulos y 300 KB por sede; LOD1 hasta 12 000 triángulos.

#### La conexión eléctrica (`adecuaciones/conexion`)

La ruta de la energía se dibuja en ámbar `#f08a00` y la de datos en violeta `#6250d6` (el `--data` de la web). Los dos colores son algo emisivos para que se lean en la sombra. Los ductos miden 20 cm de diámetro en LOD0 y 24 cm en LOD1, para que se vean a 100 m. Hijos del nodo:

| Nodo | Contenido |
|---|---|
| `ruta_potencia` | Ductos de CC desde cada arreglo, ductos de CA y acometida. Detalle en la lista de abajo. |
| `ruta_datos` | Cable de la pasarela, muro arriba y bajo el alero, hasta la antena. |
| `punto_conexion` | Tablero general (gris con franja ámbar y señal de riesgo), medidor bidireccional con pantalla, y capacete con aislador cuando la acometida está en la fachada. |
| `gateway` | Pasarela IoT (franja violeta, antena de látigo) y mástil con antena sobre el borde de la cubierta. |

El recorrido de `ruta_potencia`:

- **Corriente continua.** Sale de cada arreglo y va por la cubierta: primero a lo largo del faldón y luego pendiente abajo, o sobre la cumbrera. Llega al borde y baja por el muro hasta la bandeja de los inversores. Si el arreglo está sobre una estructura abierta, baja por la columna más cercana; si es una marquesina, por una de sus columnas, y sigue enterrado.
- **Corriente alterna.** Va de los inversores a las baterías y de ahí al tablero, o directo al tablero si no hay baterías. Del tablero sale también al cargador de vehículo eléctrico.
- **Acometida.** Va del medidor a la red.

Los tramos enterrados se dibujan sobre el suelo, en "L" y paralelos a los muros.

El punto de red sale de la especificación:

- Si hay un `poste` a menos de 40 m de un muro, el tablero va en el muro que lo mira, con acometida subterránea y bajante por el poste.
- Si no hay poste, el tablero va en la fachada del volumen de los inversores que da a la calle más cercana a los equipos (calles de OpenStreetMap en `data/geo/calles.json`). Ahí lleva acometida con capacete bajo el alero.

La elección queda en `extras.nota` del nodo `conexion`. El nodo también trae en sus `extras` los colores y los puntos.

`manifest.json` trae por sede `conexion: { tablero: [x,y,z], gateway: [x,y,z], red: [x,y,z], nota }`. Son metros en el marco del GLB (x este, y arriba, z sur) y sirven para poner etiquetas en la web.

#### Sin parpadeo: control de caras coplanares

glTF no tiene `polygonOffset`, así que la separación es geométrica:

- **Suelos.** Están escalonados 2,5 cm, desde el predio a 3 cm hasta la cancha a 18 cm, y la pintura va a media altura entre dos niveles. Los bordes de cada nivel se retranquean para que no coincidan con muros.
- **Fachadas.** Lo adosado a un muro sobresale 2 cm o más y no tiene cara trasera.
- **Muros tapados.** Los muros, vanos y remates que caen dentro de otro volumen, o detrás de una columna, no se dibujan.
- **Cubiertas vecinas.** Si dos cubiertas están a la misma altura y sus aleros se solapan, una se levanta 4 u 8 cm y acorta su alero.
- **Módulos.** Van 14 cm sobre el faldón; los anclajes y lastres entran 2 cm en la cubierta.

`scripts/modelos/check_coplanar.mjs` revisa cada GLB, con sus instancias. Informa los pares de triángulos de mallas o colores distintos que son paralelos (±2°), están a menos de 1 cm y se solapan más de 4 cm² con más de 1 cm de ancho. No cuenta las caras opuestas de una sola cara, las caras inferiores apoyadas en el suelo ni el par `cubierta_actual` reemplazada / `adecuaciones`. También resume triángulos, llamadas de dibujo y peso. Con las especificaciones de octubre de 2026, el área coplanar de las 24 versiones pasó de 5 316 m² a 1 m², repartido en solapes sueltos de menos de 0,3 m², casi siempre de menos de 0,1 m².

```bash
cd scripts/modelos
node build_edificios.mjs                 # todas las sedes → web/models/edificios/ + manifest.json
node build_edificios.mjs hospital        # solo una
node check_coplanar.mjs                  # revisa web/models/edificios/*.glb (o las rutas que se le den)
node render_vista.mjs hospital --orbita 210,30,70 --out /tmp/h.png --capa todo
```

### Escena urbana (vista "Sedes reales")

- Las réplicas se ubican en su posición real respecto al centro del casco urbano (7,0065 N; −73,9115 O).
- Las calles, caños y cuerpos de agua vienen de OpenStreetMap (`scripts/geo/osm_calles.py`, ODbL).
- Las casas del contexto se extruyen a partir de las huellas de Microsoft Global ML Building Footprints (`scripts/geo/huellas.py`, ODbL), con alturas de uno o dos pisos.
- La capa de datos MinTIC conecta cada sede con el centro de control en la alcaldía.

## 5. Agregar un modelo profesional

1. Exportar a **glTF binario (.glb)** desde Revit (complemento glTF o vía IFC → Blender), SketchUp, Rhino o Blender, en metros y con +Y arriba.
2. Optimizar:
   ```bash
   npx @gltf-transform/cli optimize entrada.glb salida_lod0.glb --compress draco --texture-compress ktx2
   npx @gltf-transform/cli simplify salida_lod0.glb salida_lod1.glb --ratio 0.25 --error 0.01
   ```
3. Copiar a `web/models/` y agregarlo a `web/models/manifest.json` para verlo en la vista **Modelos 3D**, donde se puede revisar su costo antes de usarlo.
4. Usarlo en una escena con `progressiveLOD([{ url: 'models/salida_lod0.glb', distance: 0 }, { url: 'models/salida_lod1.glb', distance: 85 }])`.

Presupuesto recomendado para que funcione en teléfonos: menos de 300.000 triángulos visibles, menos de 50 llamadas de dibujo y texturas de 2048 px como máximo, en KTX2.

## 6. Diseño y transiciones

- **Estética del logo "¡Trabajemos juntos!"**: titulares en tipografía condensada negra (Anton) que atraviesan un globo de diálogo de contorno rojo, con la cola del globo hacia abajo; pestaña activa con el mismo globo; paleta blanco, negro y rojo en tema claro y oscuro.
- **GSAP**: el globo se dibuja de izquierda a derecha, el titular entra palabra por palabra, las tarjetas se escalonan, las cifras cuentan hasta su valor, la cámara vuela a su posición, las columnas de datos crecen con retraso escalonado y las vistas se cruzan con un fundido corto. Con "reducir movimiento" activado en el sistema, todo aparece sin animación.
