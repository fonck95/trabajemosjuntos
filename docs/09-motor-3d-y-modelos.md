# 09 · Motor 3D, modelos profesionales y diseño

> Cómo está construido el atlas 3D (`web/`) para manejar modelos de arquitectura e ingeniería sin que la página se vuelva pesada, y cómo agregar modelos nuevos.

## 1. Optimizaciones del motor (`web/js/core.js`)

| Técnica | Qué hace | Por qué importa |
|---|---|---|
| **Un solo WebGLRenderer compartido** | El lienzo se mueve a la vista activa; cada vista tiene su escena, cámara y controles | Los navegadores limitan los contextos WebGL (≈16). Con diez vistas se ahorran nueve contextos y su memoria de GPU |
| **Renderizado bajo demanda** | Solo se dibuja cuando algo cambia: cámara, animación, interacción o tema. Cada animación declara si necesita el siguiente cuadro | Una vista quieta consume 0 % de GPU; la batería del teléfono dura más |
| **Pausa automática** | No se dibuja si la pestaña está oculta o el escenario salió de pantalla (IntersectionObserver) | Cero trabajo en segundo plano |
| **Tres niveles de calidad** | Alta, media y baja. El motor elige uno según el equipo y el panel "Rendimiento" deja fijarlo a mano (ver [Calidad de imagen](#calidad-de-imagen)) | Un celular no paga el posproceso de un computador de escritorio |
| **Resolución adaptativa** | Mide el tiempo de cada cuadro; si pasa de ~22 ms baja el pixel ratio en pasos de 0,25 y lo recupera con holgura. El tope es ×2 en alta y media y ×1,5 en baja | Mantiene la fluidez en equipos modestos sin sacrificar nitidez en los potentes |
| **Posproceso solo en alta** | `web/js/post.js` se descarga solo cuando la calidad es alta | Las otras calidades no cargan ni compilan nada de más |
| **Sombras manuales** | `shadowMap.autoUpdate = false`; las sombras se recalculan solo cuando algo se mueve | El mapa de sombras es una pasada completa de la escena |
| **Sombras ajustadas a la vista** | En alta y media el volumen de la sombra se ajusta a lo que se mira, y los sesgos van en proporción al téxel | De cerca la sombra es nítida y pegada al objeto; de lejos no aparecen rayas (acné) |
| **Cielo de día como entorno (PMREM)** | Un cielo procedimental (`cieloEntorno`) ilumina los materiales PBR. Se genera en la CPU y se prefiltra una sola vez | Techos más claros que muros, el lado del sol más cálido y reflejos de exterior creíbles en metal y vidrio |
| **Geometría compartida e instancias** | Todas las cajas comparten una geometría; árboles, postes, módulos solares y partículas son `InstancedMesh` | Cientos de objetos en una sola llamada de dibujo |
| **Matrices congeladas** | Los objetos estáticos tienen `matrixAutoUpdate = false` | three.js deja de recalcular miles de matrices por cuadro |
| **Selección optimizada** | El raycasting del cursor se agrupa por cuadro de animación | Mover el ratón no dispara cálculos de más |
| **Liberación de memoria** | `disposeObject` libera geometrías, materiales y texturas al cambiar de modelo | Evita fugas de memoria en el visor |
| **Panel de rendimiento** | Botón "Rendimiento" en cada escenario: cuadros por segundo, milisegundos, resolución, calidad y por qué se eligió, llamadas de dibujo (las del posproceso aparte), triángulos, geometrías y texturas. Abajo, el selector de calidad | Mide en vez de suponer, y deja probar cada calidad en el mismo equipo |
| **Plano cercano adaptativo** | `adaptDepth()` pone el plano cercano en ~1,2 % de la distancia de la cámara a su objetivo | Con 0,1 m fijo y la cámara a 1 km la precisión de profundidad cae a ~0,6 m: techos, paneles, ventanas y pisos titilan (z-fighting). Así baja a milímetros |
| **Sin cuadros en blanco** | Al cambiar el tamaño del lienzo o la resolución se redibuja en el mismo cuadro (`redraw`); la resolución adaptativa deja de subir tras dos bajadas | El navegador borra el lienzo al redimensionarlo: antes quedaba un destello |
| **Histéresis en el nivel de detalle** | `progressiveLOD` cambia de nivel con un margen del 15 % | Cerca del umbral el modelo no salta de un nivel a otro con cada movimiento |
| **Cámara que se adapta** | `fitFactor`/`fitPos` alejan la cámara según el ancho real del contenedor; `frameBox` encuadra una caja proyectando sus 8 esquinas; `closeUp` busca un rumbo con línea de vista libre hacia un punto | Las escenas caben en el teléfono y los edificios alargados o en patios se ven completos |
| **Etiquetas sin encimarse** | `declutterLabels` (opción `declutter` de la escena) sube lo justo las etiquetas que chocan; las de conexión quedan fijas | Las etiquetas se leen en la vista general y en el teléfono |
| **Reloj real en GSAP** | `gsap.ticker.lagSmoothing(0)` | En equipos lentos un vuelo de cámara de 1,5 s ya no tarda 20 s |

### Calidad de imagen

#### Niveles

| Nivel | Qué tiene | En Auto se elige para |
|---|---|---|
| **Alta** | Posproceso: bordes suavizados (MSAA) y oclusión ambiental (GTAO), que oscurece un poco los rincones y los contactos entre piezas. Sombras como en media. Resolución hasta ×2 | Computadores de escritorio |
| **Media** | Render directo, sin posproceso. Mapa de sombras del tamaño que pide la escena, ajustado a lo que se mira. Resolución hasta ×2 | GPU por software (SwiftShader, llvmpipe), pantallas táctiles más grandes, equipos de 4 núcleos o 4 GB de memoria o menos, pantallas muy densas (más de ×2,5) |
| **Baja** | Render directo. Mapa de sombras a la mitad (mínimo 1024 px), sin ajustarse a la vista. Resolución hasta ×1,5 | Celulares y tabletas pequeñas, equipos de 2 núcleos o 2 GB de memoria o menos |

- **Auto se corrige solo.** Si en alta los cuadros siguen por encima de ~30 ms con la resolución ya al mínimo (tres mediciones seguidas), baja a media. También baja a media si el navegador no tiene WebGL 2 o si `post.js` no carga.
- **Selector manual.** El panel "Rendimiento" tiene los botones Auto, Alta, Media y Baja. La elección se guarda en el navegador (`localStorage`, clave `atlas-calidad`); Auto la borra y vuelve a la detección. El panel dice si la calidad fue elegida o automática, y por qué.
- **Al cambiar de nivel** la resolución vuelve al máximo del nivel y la resolución adaptativa empieza de nuevo.

#### Posproceso (`web/js/post.js`, solo en alta)

Una sola cadena sirve a todas las vistas y respeta el renderizado bajo demanda.

1. La escena se dibuja en un render target con MSAA (4 muestras; 2 en pantallas densas) y textura de profundidad. Ese render target se comporta como el lienzo: el tono de cada vista y el sRGB se aplican igual. Así las transparencias se ven igual que en media y baja.
2. Entre lo opaco y lo transparente se calcula la oclusión ambiental con la profundidad ya dibujada. No hace falta otra pasada de geometría: las normales salen de la profundidad. El resultado se multiplica sobre lo opaco.
3. Después se dibujan las líneas, los halos, los vidrios y las partículas, limpios. El fondo no se oscurece, porque donde no hay geometría no hay oclusión.
4. Una pasada final copia la imagen al lienzo, que sigue transparente sobre el fondo de la página.

El radio de la oclusión crece con la distancia de la cámara: detalle fino de cerca, contacto amplio de lejos. Tiene un tope según la escala de la vista. En pantallas densas se calcula a media resolución. El panel cuenta aparte las llamadas de dibujo del posproceso.

#### Cielo, niebla y oclusión por vista (opciones de `Stage`)

- **`sky: true`**: cúpula de cielo en degradé, del horizonte al cenit, con los colores del tema claro u oscuro. Va en el plano lejano: no tapa nada y la oclusión no la toca. Lleva un tramado fino para que no se vean bandas.
- **`fog`**: niebla del mismo color del horizonte, para que el borde del piso se disuelva. `true` la empieza en el 60 % del plano lejano de la cámara; `{ near, far }` la fija en metros de la escena. El color es el mismo en las tres calidades.
- **`ao`**: oclusión ambiental en alta. `false` la apaga; `{ radius, intensity }` la ajusta.
- Hoy usa cielo y niebla la vista "Sedes reales" (`scenes/ciudad.js`). Las demás muestran el fondo de la página detrás del lienzo.

#### Luz y entorno

- **Entorno.** `cieloEntorno` arma un cielo de día de 256 × 128 en media precisión: cenit frío, horizonte claro, suelo cálido oscuro y un sol cálido con halo en la dirección del sol de las escenas (30, 50, 20). Se prefiltra con PMREM una sola vez, en dos intensidades: tenue (0,36) para las vistas con tono ACES y plena para las demás.
- **Vistas con tono ACES** (modelos, torre, hospital, sedes reales y parque): entorno tenue, luz hemisférica de 0,3 y sol cálido (`#fff4e6`) de 2,1. ACES comprime los claros; así muros, techos y sombras se distinguen aunque los materiales sean casi blancos.
- **Vistas sin tono**: entorno pleno, luz hemisférica de 0,55 y sol blanco de 1,35. Las vistas sin entorno (microrred, dinero, periodos y ruta) usan hemisférica de 1,1 y sol de 1,6.

#### Sombras ajustadas

La escena fija el volumen máximo de la sombra, el tamaño del mapa y, si quiere, el sesgo normal. Si los cambia después (otro modelo, otra hora), esos valores pasan a ser la nueva base. El motor ajusta tres cosas antes de cada cuadro:

- **Tamaño del mapa** según la calidad: en alta y media, el de la escena; en baja, la mitad. Siempre queda entre 1024 y 4096 px.
- **Volumen, en alta y media**: se ajusta a lo que se ve. Las cuatro esquinas de la pantalla se proyectan sobre el piso alrededor del punto que se mira. El tamaño cambia en pasos de √2 y el centro se mueve por tramos, así el mapa se recalcula solo de vez en cuando y no en cada cuadro. De cerca, cada téxel mide centímetros. Si una esquina ve el horizonte, se usa el volumen completo.
- **Sesgos en proporción al téxel**: sin rayas cuando el téxel es grande ni sombras despegadas de cerca.

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

1. **Ubicación.** Se cruzan la web de la alcaldía, SECOP, OpenStreetMap, las fichas de Google y los letreros visibles en Street View. Cada sede declara su confianza: alta, media o baja. Las coordenadas de los inventarios no se dan por buenas: la planta de agua estaba 270 m corrida (sobre una piscícola) y el «CPSAM» resultó ser el Centro Vida; el hogar real funciona en las alas occidentales del predio del hospital.
2. **Huella.** Se mide sobre la imagen satelital Esri World Imagery (zoom 19 ≈ 0,30 m por píxel, enero de 2020) y sobre la de Google (zoom 20–21 ≈ 0,15–0,07 m por píxel, más reciente). `scripts/geo/trace.py` (Esri) y `scripts/geo/gtrace.py` (Google o Esri, con retícula de 5 m) superponen los rectángulos medidos, y se itera hasta que coinciden con los bordes de la cubierta. Entre las dos fuentes hay desfases de ~2 m: cada especificación dice sobre cuál se midió.
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

#### Obra nueva: edificios contemporáneos

Para proponer edificios nuevos (la torre de servicios de primer nivel del hospital, por ejemplo) la especificación tiene opciones de obra nueva. Se documentan en `data/edificios/ESPECIFICACION.md` («Obra nueva»). Son opcionales: con ellas apagadas, los GLB de las sedes levantadas salen idénticos byte a byte.

- **Fachadas por lado** (`fachada.lados_material`) con materiales nuevos a escala real:
  - **Muro cortina** (`muro_cortina`): vidrio oscuro y algo reflejante, en tres tonos apenas distintos por módulo. Lleva parales y travesaños de aluminio, enjutas opacas en cada losa, base y banda bajo la coronación, y esquineros. Cada esquina la pone el lado que la tiene a su derecha, para no duplicar piezas.
  - **Puertas en el muro cortina**: vestíbulo hundido, marco y hojas corredizas automáticas con cabezal del operador.
  - **Otros acabados**: panel de aluminio compuesto con juntas (`panel_compuesto`), concreto con formaleta de tablas (`concreto_visto`) y ladrillo tolete con junta rehundida y tono por pieza (`ladrillo_visto` con `fachada.ladrillo` o por lado).
  - **Coronación**: el antepecho de la cubierta plana toma el acabado de cada lado, con remate metálico.
- **Ventanas corridas** (`ventanas.tipo: "franja"`), que se cortan en puertas y tramos tapados.
- **Losas expresadas** (`losas_expresadas`): bordes de losa en voladizo por piso y en la cubierta, en vez de las bandas de entrepiso. Se dibujan después de la conexión, para cortarlos donde suben sus ductos; en un muro cortina, el tablero y los ductos van delante de los parales.
- **Parasoles** (`fachada.parasoles`): aletas verticales con ménsulas o lamas horizontales inclinadas con platinas. Son instancias GPU de una caja unitaria por color, en el nodo `<capa>_parasoles`. En el muro cortina van sobre los parales.
- **Elementos**:
  - `marquesina_acceso`: losa delgada con cielo raso y luminarias empotradas, sobre columnas esbeltas o en voladizo con tensores.
  - `bahia_ambulancias`: marquesina alta, demarcación, rótulo en el piso y bolardos que respetan las puertas.
  - `puente`: acristalado, con cerchas o vigas y columnas intermedias. Las losas expresadas y los parasoles le dejan paso.
  - `equipo_cubierta`: manejadoras, enfriadores, tanques, cuarto de máquinas y pantalla de lamas, sobre la cubierta más alta bajo su centro.
  - Paisajismo: `jardinera` (con arbustos instanciados), `banca` y `luminaria`.
  - `letrero_institucional`: letras grandes con tildes sobre el antepecho, en la fachada o libres.
- **Pérgola solar** (`fv` con `"tipo": "pergola"`): pórticos de acero sobre la losa con los módulos encima. Los equipos de la cubierta quedan debajo.
- **Núcleos de escaleras y ascensores** como volúmenes propios. La lógica de muros tapados oculta lo que queda dentro de la torre. En las fachadas nuevas, lo tapado por un podio con antepecho sube hasta su remate, así el vidrio y las ventanas empiezan encima.
- **Tildes**: en `letrero_institucional` y en el rótulo de la bahía, `textGeo` pone las tildes sobre la altura real de las mayúsculas de la fuente (1,013 × tamaño). El `letrero` de las réplicas sigue suponiendo 0,72 × tamaño, y con eso la tilde aguda queda dentro de la letra (pasa en BIBLIOTECA MUNICIPAL MARÍA CANO, INSTITUCIÓN EDUCATIVA LUIS EDUARDO DÍAZ y REGISTRADURÍA). Se dejó así para que esos modelos verificados no cambien; pasar `true` como cuarto argumento en ese llamado lo corrige.
- **Llamadas de dibujo**:
  - Bancas, luminarias y bolardos que se repiten menos de 10 veces se funden en la malla del entorno de su capa.
  - Parasoles, arbustos, árboles y módulos van instanciados.
  - Bancas, luminarias, bolardos y arbustos no van en el LOD1.

Las especificaciones de prueba están en `data/edificios/pruebas/`; la compilación normal no las lee. Presupuesto de `prueba_torre`: torre de 5 pisos (32 × 22 m), podio de 2 pisos, núcleo, cubierta con equipos y pérgola de 48,4 kWp, marquesina, bahía y paisajismo.

| | Triángulos dibujados (con instancias) | Llamadas de dibujo | Peso |
|---|---|---|---|
| LOD0 | 55 140 (meta: menos de 250 000) | 41 | 243 KB |
| LOD1 | 12 716 (meta: menos de 30 000) | 32 | 184 KB |

`check_coplanar.mjs` no encuentra caras coplanares en ninguna de las tres pruebas (LOD0 y LOD1).

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
node render_vista.mjs hospital --orbita 210,30,70 --out /tmp/h.png --capa todo --entorno   # cielo y luces de las vistas ACES de la web
```

### Escena urbana (vista "Sedes reales")

- Las réplicas se ubican en su posición real respecto al centro del casco urbano (7,0065 N; −73,9115 O).
- Las calles, caños y cuerpos de agua vienen de OpenStreetMap (`scripts/geo/osm_calles.py`, ODbL).
- Las casas del contexto se extruyen a partir de las huellas de Microsoft Global ML Building Footprints (`scripts/geo/huellas.py`, ODbL), con alturas de uno o dos pisos.
- La Laguna del Miedo (captación del acueducto) se agrega desde la relación completa de OpenStreetMap (`data/geo/osm_laguna_del_miedo.xml`).
- La capa de datos MinTIC conecta cada sede con el centro de control en la alcaldía: trazo de ancho fijo en pantalla (`Line2`) con guiones que avanzan hacia la alcaldía; el enlace de la sede elegida se resalta.
- **Recorrido:** barra sobre el escenario (‹ ›, Todo, Girar, Hoy/Proyecto), flechas del teclado, Esc y doble clic. Las sedes se ordenan por cercanía desde la alcaldía; cada una se encuadra por su volumen (`solidBox` + `frameBox`) conservando el rumbo, con un anillo de selección.
- **Conexión de cada sede:** una etiqueta junta tablero con medidor bidireccional, gateway IoT y acometida (vienen de `manifest.json → conexion`); el poste de la red va aparte si queda lejos. Tocarla, o «Ver la conexión de cerca» en la ficha, lleva la cámara a un punto con línea de vista libre (`closeUp`).
- **21 sedes** levantadas y verificadas, entre ellas las del acueducto fuera del casco urbano (PTAP, planta veredal, tanque elevado y captación con sus barcazas en la Laguna del Miedo).
- **Cielo y niebla:** cúpula de cielo con los colores del tema y niebla del color del horizonte que empieza en el 60 % del radio del piso (el piso mide 1,5 km de radio o más). El borde del piso se disuelve en el cielo.

### Vista "Torre del hospital"

Contrato: `data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md` (secciones 5, 6, 8, 16 y 17). Documentos de contenido: `docs/11` (la torre), `docs/14` (simulador sísmico), `docs/15` (dotación y habilitación) y `docs/16` (modelo BIM).

#### Modos y máquina de estados

- **Modos:** "Hoy" (las alas del antiguo Centro Vida), "Con la torre" (el modelo de `data/edificios/torre_hospital.json`, con la capa "Proyecto tipo": una placa de 320,6 m² a escala, la del puesto tipo del DNP), "Pisos por servicio" (los cuatro pisos separados con la planta real del anteproyecto, coloreada por grupo de la Res. 1633), "Laboratorio" (abre el recorrido parado en la puerta del laboratorio del piso 2, mirando hacia adentro; la maqueta aérea anterior se retiró), "Recorrer por dentro", "Simulador sísmico" y "Modelo BIM".
- **Un modo a la vez** (`web/js/scenes/torre.js`, dueño único): los módulos de cada modo (`web/js/scenes/torre/*.js`) se cargan de forma perezosa al entrar y, si fallan, cae el relleno «en construcción» (`_relleno.js`). Cada modo recibe en su `ctx` solo sus contenedores (`torre.panel.<modo>`, `torre.hud.<modo>`, `torre.ficha.modo`), los muestra u oculta él mismo y nunca escribe en el contenedor padre.
- **Salir siempre igual:** `salir({ porUsuario })` vacía sus contenedores, devuelve lo que ocultó del exterior, quita su malla de la escena, restaura el campo de visión, los controles y los objetos seleccionables (`st.pickables` se vacía mientras el recorrido está activo, porque este hace su propio *raycast*), y no deja oyentes. Un cambio pedido mientras otro modo carga, calcula o vuela la cámara gana (contador de turno), así no quedan contenidos ni cámaras cruzados. `alReanudar` y `alDetener` repiten el ajuste del modo cuando la vista vuelve a arrancar o se detiene (`core.js` no se tocó).
- **Textos:** todo texto de los datos pasa por `textos.limpio` (`web/js/scenes/torre/textos.js`), que cambia rutas y claves internas por palabras («el inventario», «la revisión de la Res. 3100»); la frase «servicio habilitado» no aparece: el estado se llama «cumplimiento en dotación e infraestructura».

#### Recorrido en primera persona (`recorrido.js`, `controles_fp.js`, `planta3d.js`, `minimapa.js`, `inventario.js`, `habilitacion.js`)

- **Qué se recorre:** toda la torre, un nivel armado a la vez: exteriores (plaza, patio de urgencias, bahía de ambulancias con marquesina solar, galería), pisos 1 a 4, escaleras caminables, ascensores con botones de piso, bloque técnico y cubierta técnica con los paneles solares.
- **Controles:** teclado con `ev.code` (sirve con cualquier distribución) y solo con el foco dentro del recuadro; arrastrar para mirar, *Pointer Lock* opcional en escritorio («Mirar con el ratón» o doble clic) y, en pantallas táctiles, arrastre y joystick virtual; selección por clic corto (un arrastre no selecciona). R/F o RePág/AvPág saltan al vestíbulo de ascensores del nivel de arriba o de abajo.
- **Cámara:** campo de visión vertical de ≈ 75° horizontales (se abre en recuadros verticales, como el teléfono); la cámara se conduce a través del objetivo de `OrbitControls` (ojos a 1,60 m y objetivo medio metro adelante, sin desactivar los controles), con el plano cercano en 0,05 m.
- **Colisión:** rejilla de celdas de 0,10 m por nivel con muros, columnas, muros estructurales y equipos grandes inflados 0,30 m, y deslizamiento por ejes; en las escaleras el piso es el tramo o descanso más cercano a los pies, así que se sube y se baja caminando y el nivel cambia cuando los ojos pasan la losa. La QA comprueba que un caminante de radio 0,30 m llega a cada recinto desde las entradas.
- **Minimapa** en un `<canvas>` 2D con los colores del grupo de cada recinto y el caminante como flecha (lleva `aria-hidden`; su alternativa accesible es la lista «Ir a…»).
- **Capas:** dotación, equipamiento fijo, infraestructura (lavamanos, tomas de gases, extintores, señales) y laboratorio en comodato; faltantes del cierre de brechas como unidades fantasma; «Comparar con el proyecto tipo» (los colores los pasa `torre.js`, así el recorrido no importa el módulo del contraste).
- **Inspección:** todo objeto visible abre su ficha (exigencia y numeral, clase de riesgo y registro, precio y tipo de precio, mantenimiento, anclaje y contenido desplegable); el inventario completo se busca y se filtra por nivel, servicio, recinto, capa, clase y estado, con «Ir a», que lleva al caminante frente a la unidad y la resalta.
- **Presupuesto medido por nivel** (QA en Chromium, calidad media, 1400 × 900, 25-oct-2026): de 10 a 37 llamadas de dibujo (límite 45) y de 10.106 a 30.662 triángulos (límite 150.000) por nivel; cada nivel se arma en 20 a 80 ms (límite 300 ms). Los 147 modelos del catálogo dan geometría en sus dos niveles de detalle.

#### Catálogo de equipos 3D (`web/js/equipos3d.js`)

- **Lista cerrada** de modelos procedurales (cajas, cilindros y perfiles extruidos, sin texturas) para todos los `modelo3d` del inventario, con las medidas del catálogo (o las nominales del contrato, marcadas como estimación).
- **Dos niveles de detalle:** LOD0 hasta 600 triángulos (1.500 en los equipos grandes) y LOD1 de cuatro cajas como máximo (48 triángulos). En calidad baja todo el piso va en LOD1 y los objetos pequeños solo se dibujan en el recinto donde está el caminante; en alta, si el LOD0 de todo el piso no cabe en el presupuesto, los modelos que más pesan pasan a LOD1.
- **Agrupación:** `InstancedMesh` por modelo cuando hay 4 unidades o más; el resto se funde en una malla con una tabla de rangos para saber qué unidad se tocó. Las geometrías de cada pieza se normalizan antes de fundirlas (no indexadas, sin coordenadas de textura, con color y normales), así `mergeGeometries` nunca devuelve `null`.
- **Malla fantasma** (translúcida) para lo que falta y caja de resaltado para «Ir a».

#### Simulador sísmico en pantalla (`sismo.js`, `estructura3d.js`, `graficas.js`)

- **Lo que se dibuja es lo calculado:** cada columna, viga y muro es una línea gruesa (`LineSegments2`) de 8 tramos cuya posición sale de los desplazamientos del diafragma rígido de cada nivel (ux, uy, rz en el centro de masa), de los giros de los nudos y de los polinomios de Hermite; la rotación plástica de una rótula se resta del giro del nudo para que el quiebre se vea. La exageración (×1 a ×200) se dice en medidas reales.
- **Sin reservar memoria en cada paso:** la geometría se crea una vez y en cada paso se escriben los arreglos existentes (`instanceStart.data.array.set(…)` y `needsUpdate`), nunca `setPositions()`, que en three 0.160 crea búferes nuevos.
- **Colores** de demanda/capacidad (≤ 0,5; 0,5-0,8; 0,8-1,0; > 1,0) desde los tokens del tema; rótulas como esferas con anillo del nivel de desempeño; mampostería con el color de su daño; equipos sueltos con un anillo de lo que deslizaron; deriva vectorial por nivel.
- **Reproducción por pasos calculados:** el deslizador y el botón de reproducir recorren las salidas del motor (cada 0,02 s); no hay interpolación ni animación inventada.

#### Trabajador de módulo y publicación

- El motor corre en un **Web Worker de módulo** (`new Worker(new URL('../../sismo/trabajador.js', import.meta.url), { type: 'module' })`). Dentro del trabajador no se usa el importmap: los módulos del motor (`web/js/sismo/`) se importan con rutas relativas y extensión `.js`, y no dependen de three ni del DOM. Las URL de los datos se arman con `import.meta.url`, así funciona igual en la raíz y en una subruta.
- **Cancelar** es `worker.terminate()` (la vista vuelve a pedir un trabajador nuevo). Si no hay `Worker` (por ejemplo, en un Artifact), el **respaldo** corre `motor.js` en el hilo principal por tramos de unos 12 ms y da los mismos resultados, bit a bit.
- **Publicación:** GitHub Pages (subruta del repositorio) y Railway con Caddy sirven `site/`, que arman `scripts/build_data.py` y `scripts/build_site.py`, sin pasos nuevos en CI. Los datos de cada modo (`web/data/torre_*.json`, `sismo_*.json` y `torre_bim*.json`) se cargan solo al entrar al modo, nunca con `data.js`, y `build_data.py` no los escribe si un insumo cambió después de generarlos.

#### Modo «Modelo BIM» (`bim.js`, `bim3d.js`, `bim_refuerzo.js`, `bim_despiece.js`)

- El modelo federado (documento 16) se arma por disciplina y nivel, fundido en **una malla por disciplina y una de aristas**, con un índice de elemento por vértice y dos texturas de estado por elemento: ocultar, aislar, resaltar, colorear con el simulador o avanzar el 4D cambia unos bytes de una textura, sin crear mallas ni llamadas de dibujo.
- **Cortes** horizontales por nivel y verticales por eje con planos de recorte y tapa rayada calculada con la geometría de cada elemento (el renderizador no tiene búfer de esténcil).
- **Refuerzo** solo del elemento o del eje elegido, con barras instanciadas, y su despiece en 2D (SVG); descarga de los dos IFC4.
- QA del 25-oct-2026 en claro, oscuro y teléfono: el modelo de 4.583 elementos carga en ≈ 2 s y se dibuja con 18 llamadas; el árbol, el buscador, aislar la cimentación (254 elementos), la descarga de los IFC (7,30 MB y 12,26 MB) y la salida a los demás modos quedan en verde.

#### Herramientas de QA

`scripts/qa/LEEME.md` dice cómo armar en cualquier máquina las copias locales de three@0.160.0 y gsap@3.12.5 (`npm pack`) y Playwright con Chromium. `scripts/qa/comun.mjs` sirve el sitio, desvía los CDN a esas copias y revisa consola, desborde y textos internos; lo usan `torre_qa.mjs` (QA global de la vista), `recorrido_qa.mjs`, `equipos_qa.mjs`, `bim_qa.mjs` y `scripts/sismo/qa_worker.mjs`. Cifras medidas del simulador (25-oct-2026): en escritorio, iniciar en 23 ms, sintetizar el movimiento en 92 ms y analizar 40 s con Δt = 0,005 s en 930 ms; en un teléfono simulado con la CPU 4 veces más lenta, 1,9 s con la calidad baja; memoria pico de 33,4 MB (límite 80 MB); cancelar en menos de 300 ms; y los mismos resultados en la raíz, en la subruta y sin trabajador.

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
