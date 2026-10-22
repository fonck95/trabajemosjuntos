# Especificación de edificios (`data/edificios/<id>.json`)

Cada dependencia pública se describe con un archivo JSON. El generador `scripts/modelos/build_edificios.mjs`
lo convierte en un modelo 3D (GLB) con dos capas: **existente** (réplica del edificio real) y
**adecuaciones** (lo que propone el proyecto de microrred: solar, baterías, domótica, obras civiles).

## Sistema de coordenadas

- `lat`, `lon`: **ancla** del edificio en WGS84 (centro aproximado de la huella principal), con 6 decimales.
- Todas las posiciones son **metros** relativos al ancla: `x` hacia el **este**, `y` hacia el **norte**.
- `rumbo_eje`: grados en sentido horario desde el norte (0 = eje largo norte–sur, 90 = este–oeste).
- Alturas en metros sobre el terreno. Un piso típico en Yondó mide 3,0–3,5 m; la cámara de Street View está a ≈2,5 m.
- Conversión: `lat = lat0 + y / 111320`, `lon = lon0 + x / (111320 · cos(lat0))`.

## Estructura

```jsonc
{
  "id": "alcaldia",                       // igual al id del nodo en data/microrred.json cuando exista
  "nombre": "Palacio Municipal de Yondó",
  "nodo_microrred": "alcaldia",           // o null si es una dependencia nueva
  "direccion": "Calle 50 # 50-26",        // si se encontró
  "lat": 7.005123, "lon": -73.910456,
  "ubicacion": { "confianza": "alta|media|baja", "metodo": "cómo se confirmó (letrero en Street View, web oficial, OSM…)" },
  "fuentes": [
    { "tipo": "street_view", "pano": "ID", "fecha": "2013-11", "rumbo": 160, "nota": "fachada principal, letrero visible" },
    { "tipo": "satelite", "fuente": "Esri World Imagery z19", "nota": "huella y cubierta" },
    { "tipo": "web", "url": "https://…", "nota": "foto de 2024, cubierta nueva" }
  ],
  "volumenes": [
    {
      "id": "bloque_a", "nombre": "Bloque principal",
      // Rectángulo (preferido; descomponer formas en L/U/patios en varios rectángulos):
      "centro": [0, 0], "largo": 24.0, "ancho": 12.0, "rumbo_eje": 15,
      // o polígono (solo con techo "plano" o "ninguno"): "poligono": [[x,y], …]
      "base": 0,                    // altura de arranque (para volúmenes sobre otros)
      "altura_alero": 7.0,          // del piso al borde superior del muro
      "pisos": 2,
      "techo": {
        "tipo": "dos_aguas|cuatro_aguas|una_agua|plano|curvo|ninguno",
        "pendiente": 15,             // grados (dos/cuatro/una agua)
        "cumbrera": "largo|corto",   // dos_aguas: la cumbrera corre a lo largo del eje largo (lo usual) o del corto
        "caida": "N|S|E|O",          // una_agua: hacia dónde cae el agua
        "flecha": 1.5,               // curvo: altura del arco
        "voladizo": 0.6,
        "parapeto": 0.8,             // plano: altura del antepecho
        "material": "zinc|teja_barro|fibrocemento|termoacustica|concreto|policarbonato",
        "color": "#8a8f94"
      },
      "fachada": {
        "material": "pañete_pintado|ladrillo_visto|bloque|metal|vidrio|muro_cortina|panel_compuesto|concreto_visto",
        "lados_material": { "N": "muro_cortina", "O": { "material": "panel_compuesto", "color": "#676d73" } }, // obra nueva (ver abajo)
        "color": "#f2efe6", "zocalo": { "color": "#7a2b2b", "altura": 0.9 },
        "ventanas": { "tipo": "ventana|celosia|calado|vitrina|reja|franja", "ancho": 1.5, "alto": 1.2, "antepecho": 1.0,
                      "separacion": 3.0, "lados": ["largo", "corto"] },
        "puertas": [ { "lado": "N|S|E|O", "pos": 0.5, "ancho": 2.0, "alto": 2.4 } ],
        "corredor": { "lado": "N|S|E|O", "profundidad": 2.5, "sep_columnas": 3.5 },   // corredor con columnas (opcional)
        "letrero": { "lado": "N|S|E|O", "texto": "ALCALDÍA MUNICIPAL", "color": "#123a7a" } // opcional
      }
    }
  ],
  "elementos": [   // lo que da carácter al lugar y se ve en Street View
    { "tipo": "cerramiento", "poligono": [[x,y],…], "altura": 2.2, "material": "muro|reja|malla", "color": "#ddd" },
    { "tipo": "tanque_elevado", "centro": [x,y], "altura": 12, "diametro": 4 },
    { "tipo": "arbol", "centro": [x,y], "altura": 9, "copa": 7 },
    { "tipo": "cancha", "centro": [x,y], "largo": 28, "ancho": 15, "rumbo_eje": 0, "cubierta": false },
    { "tipo": "parqueadero|patio|anden|zona_verde", "poligono": [[x,y],…] },
    { "tipo": "cubierta_ligera", "centro": [x,y], "largo": 8, "ancho": 5, "rumbo_eje": 0, "altura": 3.2 },
    { "tipo": "asta|poste|torre|antena|planta_electrica|aire_acondicionado", "centro": [x,y], "altura": 8 }
  ],
  "adecuaciones": {
    "kwp_plan": 50,                    // de data/microrred.json
    "fv": [
      // Arreglo sobre un faldón de un volumen (el generador lo acomoda en la cubierta):
      { "volumen": "bloque_a", "faldon": "N|S|E|O|plano", "filas": 4, "columnas": 18,
        "orientacion_modulo": "vertical|horizontal", "inclinacion": 10, "azimut": 180 },
      // o marquesina solar sobre parqueadero:
      { "tipo": "marquesina", "centro": [x,y], "largo": 20, "ancho": 10, "rumbo_eje": 0, "altura": 3.5, "filas": 4, "columnas": 18 }
    ],
    "kwp_factible": 48.4,             // módulos × 0,55 kWp
    "bess": { "kwh": 120, "kw": 60, "tipo": "gabinete|contenedor_10|contenedor_20", "centro": [x,y], "largo": 6.1, "ancho": 2.4, "rumbo_eje": 0 },
    "inversores": { "n": 2, "kw": 30, "volumen": "bloque_a", "lado": "S" },
    "domotica": ["medidor bidireccional", "gateway IoT", "sensores de ocupación", "control de aires", "telegestión de luminarias"],
    "obras_civiles": ["cambio de cubierta de fibrocemento por termoacústica antes del montaje", "puesta a tierra y pararrayos"],
    "cargador_ve": { "centro": [x,y] },
    "notas": "por qué cabe o no cabe la potencia planeada; sombras de árboles; estado de la cubierta"
  },
  "incertidumbres": ["la altura del bloque B se estimó por número de pisos", "…"],
  "verificacion": { "trace": "data/geo/img/<id>_trace.png", "vistas": ["data/geo/img/<id>_sv_*.jpg"] }
}
```

## Lo que entiende el generador (detalles)

- `pisos` vale 1 si no se indica (coliseos y bodegas: 1 piso alto). Con 2 o más pisos dibuja bandas de entrepiso.
- Volúmenes con `poligono`: muros extruidos y techo plano con antepecho; **no** llevan ventanas ni puertas (usar rectángulos siempre que se pueda).
- `"abierto": true` en un volumen rectangular: pórtico, corredor exento, kiosco o parqueadero cubierto. Lleva columnas en el perímetro
  (`sep_columnas`, por defecto 3,5 m; `columna`, lado en m, por defecto 0,25) con viga de amarre y la cubierta del volumen; sin muros ni ventanas.
  Puede tener `base` (por ejemplo, un pórtico sobre una plataforma) y una altura de alero baja.
- `ventanas.tipo`: `ventana` (vidrio con marco), `vitrina` (vidrio casi de piso a techo), `reja` (vidrio con barrotes), `celosia`/`calado` (bloque de ventilación).
  `lados`: `largo`, `corto`, `todos` o cardinales (`N`, `S`, `E`, `O`). Las ventanas del primer piso no se dibujan sobre las puertas.
- `puertas[].pos`: 0 = extremo izquierdo y 1 = derecho, **mirando la fachada desde afuera**. Más de 2,6 m de ancho se dibuja como portón metálico.
- `letrero`: el texto se escribe en mayúsculas con tildes; se centra sobre la primera puerta de ese lado.
- `elementos`: `cerramiento` acepta `poligono` (cerrado) o `linea` (abierto); `material` `muro` | `reja` | `malla`. `cancha` acepta `superficie: "concreto"`,
  `cubierta: true` con `altura`, `material_cubierta`, `color_cubierta`. Tipos soportados: cerramiento, tanque_elevado, arbol, cancha, parqueadero, patio,
  anden, zona_verde, plaza, cubierta_ligera, asta, poste, torre, antena, planta_electrica, aire_acondicionado, pozo; y para obra nueva
  marquesina_acceso, bahia_ambulancias, puente, equipo_cubierta, jardinera, banca, luminaria y letrero_institucional (ver abajo).
- `pozo`: `{ "tipo": "pozo", "centro": [x,y], "diametro_pulgadas": 8, "rumbo": 90, "nombre": "Pozo 1" }`: pozo profundo con bomba sumergible (losa, revestimiento, cabezal, descarga con cheque y compuerta, manómetro y tablero de arranque con variador bajo cubierta). `rumbo` orienta la descarga (grados desde el norte).
- `adecuaciones.cubierta_nueva` (opcional): `{ "material": "termoacustica", "color": "#e9e7e1", "volumenes": ["bloque_a"] }`. Si no se indica, pero
  `obras_civiles` menciona un cambio de cubierta, se reemplazan las cubiertas inclinadas de zinc o fibrocemento por termoacústica.
  Solo los volúmenes reemplazados cambian de cubierta en la vista "Con el proyecto"; las demás cubiertas, las de los corredores y las de los
  elementos (`cubierta_ligera`, canchas cubiertas) se conservan. Indica `volumenes` explícitamente cuando no todas las cubiertas se cambian.
- `fv[].faldon` elige la cara de la cubierta cuya normal apunta más hacia ese punto cardinal; en techos curvos, `N`/`S` (o `E`/`O`) eligen la mitad de la bóveda.
  En techo plano, `inclinacion` y `azimut` (grados desde el norte hacia donde mira el panel).
- `kwp_factible` debe ser igual a módulos × 0,55; el generador avisa si no coincide.
- `estado` (en un volumen, en un elemento o en toda la especificación): `"existe"` (por defecto), `"demoler"` (se ve en "Hoy" y desaparece "Con el proyecto"; va al nodo `existente/a_demoler` con `extras.demoler`) o `"nuevo"` (obra nueva: solo "Con el proyecto"; va al nodo `adecuaciones/obra_nueva`). Lo que se demuele no tapa muros de la obra nueva ni al revés, así una torre nueva puede ocupar el lugar de las alas que reemplaza. Los arreglos `fv` pueden ir sobre volúmenes nuevos.
- Detalle que se genera sin pedirlo:
  - Vanos recortados con jambas, carpintería (marco, parteluces, vidrio hundido; barrotes en `reja`), alféizar y dintel.
  - Puertas con marco y tableros, y cortina enrollable en portones.
  - Tapa de alero, caballetes, cielo raso bajo el alero, canal y bajantes, y remate de antepechos.
  - Columnas con basa y capitel.
  - Rieles y anclajes de los módulos, y estructura de las marquesinas.
  - Señales, rejillas y bolardos en las baterías.

  Nada de eso cambia medidas ni posiciones de la especificación. Si una ventana queda tapada por otro volumen o por una columna
  delante, no se dibuja. Las marquesinas de menos de 1,5 m de `altura` se arman como estructura en tierra, con dos patas por pórtico y 10° si no
  se indica `inclinacion`.
- Volúmenes que se tocan o se solapan:
  - Un muro (o tramo) que cae dentro de otro volumen cerrado no se dibuja, ni sus vanos.
  - Si dos muros quedan en el mismo plano mirando al mismo lado, se conserva el del volumen que aparece primero en `volumenes`.
  - Si dos cubiertas vecinas están a la misma altura y sus aleros se solapan, la del volumen posterior se levanta 4 cm (u 8) y su alero se acorta
    6 cm (o 12), para que no queden coplanares.
  - Las columnas de corredores anchos que quedarían pegadas a un muro no se ponen, y la viga se apoya en el muro. Las pilastras (volúmenes
    abiertos angostos) sí se ponen.
  - Los tramos de `cerramiento` que pasan a menos de 30 cm de un volumen, o por una columna, se cortan.
- Suelos: cada tipo tiene su altura fija, de la más baja a la más alta: `predio` (3 cm), `zona_verde`, `parqueadero`, `patio`, `plaza`, `anden`
  y `cancha` (18 cm), cada uno 2,5 cm sobre el anterior. Si dos se superponen, se ve el de más arriba. Los pisos de corredores y pórticos
  van a 21 cm.
- Conexión del proyecto (nodo `adecuaciones/conexion`):
  - La ruta de potencia va en ámbar: arreglos → muro → inversores → baterías → tablero/medidor → red. La de datos va en violeta:
    pasarela → antena.
  - Si hay un `poste` a menos de 40 m de un muro, es el punto de conexión a la red. Si no, la acometida va en la fachada del volumen de
    `inversores.volumen` que da a la calle más cercana a los equipos.
  - El tablero se pone en el primer tramo de muro libre (sin vanos, bajantes ni columnas delante) cerca de ese punto.
  - Para que la conexión salga bien, conviene que la especificación traiga los `poste` de la red que se ven en Street View.

## Obra nueva: fachadas contemporáneas, equipos y paisajismo

Para diseñar edificios nuevos (por ejemplo, una torre de servicios hospitalarios de 4–5 pisos) el generador entiende estas opciones.
Todas son opcionales y solo cambian los volúmenes y elementos que las usan: las réplicas existentes se generan igual que antes (los
GLB de las sedes levantadas quedan idénticos byte a byte). Conviene usarlas con `"estado": "nuevo"`.

Las especificaciones de prueba están en `data/edificios/pruebas/` (la compilación normal no las lee, así que no van a la web):
`prueba_torre` (torre de 5 pisos con podio, núcleo, cubierta con equipos y pérgola, marquesina, bahía y paisajismo),
`prueba_puente` (bloque nuevo de ladrillo con dos puentes hacia uno existente, marquesina en voladizo y letrero en fachada) y
`prueba_cortina` (caja de vidrio con lamas y un anexo de concreto). Se compilan aparte:
`cd scripts/modelos && EDIFICIOS_DIR=../../data/edificios/pruebas/ EDIFICIOS_OUT=/tmp/pruebas/ node build_edificios.mjs`.

### Fachadas (`volumenes[].fachada`)

- **Materiales nuevos** (en `material` o por lado en `lados_material`), con texturas a escala real (UV en metros):
  - `muro_cortina`: vidrio por módulos en tres tonos apenas distintos (oscuro y algo reflejante: metalicidad 0,55 y rugosidad 0,07;
    con el mapa de entorno de la web refleja el cielo), parales de aluminio de 10 cm cada `modulo` m, travesaños de 7 cm en los bordes
    de las enjutas, enjuta opaca de `enjuta` m centrada en cada losa, base opaca de 18 cm, banda opaca bajo la coronación, esquineros
    y puertas de vidrio (ver abajo). Las ventanas de ese lado no se dibujan: el muro es el vidrio.
    ```json
    "muro_cortina": { "modulo": 1.6, "enjuta": 1.1, "color_vidrio": "#2b4250", "color_perfil": "#c6cbce", "color_enjuta": "#4d5961" }
    ```
  - `panel_compuesto`: panel de aluminio compuesto (ACM) con juntas de ~2 cm y una variación mínima de tono entre paneles; el tamaño
    del panel va en `"panel": { "ancho": 1.5, "alto": 0.75 }` (valores por defecto).
  - `concreto_visto`: concreto con formaleta de tablas de 12 cm, empates escalonados y huecos de tensores cada 60 cm.
  - `ladrillo_visto` mejorado (tolete de 24,5 × 6,5 cm, junta rehundida de 1 cm, tono y matiz por pieza): se usa cuando el lado viene
    de `lados_material` o la fachada trae `"ladrillo": {}`. Sin eso, `ladrillo_visto` conserva la textura de siempre (réplicas verificadas).
- **`lados_material`**: acabado por lado. Las claves son `N|S|E|O`, `largo`, `corto` o `todos`; el valor es el nombre del material o
  `{ "material": …, "color": … }`. Los lados que no aparecen usan `material` y `color`:
  `"lados_material": { "N": "muro_cortina", "E": "muro_cortina", "O": { "material": "panel_compuesto", "color": "#676d73" } }`.
  Un lado con un material de siempre (`pañete_pintado`, `bloque`…) se dibuja como antes, con zócalo y bandas.
- En los lados con acabado nuevo no hay zócalo pintado ni bandas de entrepiso. Las ventanas llevan el vidrio del muro cortina, marco
  oscuro (`ventanas.color_marco`, por defecto `#3b4043`) y alféizar y dintel de aluminio; las puertas de hasta 2,6 m son de aluminio y vidrio.
- **Puertas en el muro cortina**: vestíbulo hundido 40 cm con retornos de aluminio, marco exterior, hojas corredizas automáticas (dos,
  o cuatro con paños fijos si el vano pasa de 3,2 m) y cabezal del operador.
- **Antepecho de la cubierta plana** en volúmenes con acabado nuevo: cada lado con su acabado (sobre el muro cortina, panel del color
  del perfil) y remate metálico. `"coronacion": { "material": "panel_compuesto", "color": "#e3e4e2" }` lo fija para todos los lados.
- **`ventanas.tipo: "franja"`**: ventana corrida por piso, de punta a punta menos `margen` (0,6 m por defecto), con parales cada 1,5 m;
  se corta en las puertas del primer piso y en los tramos tapados por otros volúmenes. Usa `alto` y `antepecho`:
  `"ventanas": { "tipo": "franja", "alto": 2.2, "antepecho": 1.1, "lados": ["S", "O"] }`.
- **`losas_expresadas`**: borde de losa que sobresale `voladizo` m en cada entrepiso (y en la cubierta con `"cubierta": true`), de
  `espesor` m, por los tramos visibles de los `lados` indicados (todos por defecto). Reemplaza las bandas de entrepiso y les deja paso
  a los puentes y, en la obra nueva, a los ductos verticales de la conexión:
  `"losas_expresadas": { "voladizo": 0.45, "espesor": 0.4, "color": "#f3f2ee", "cubierta": true }`.
- En un lado de muro cortina, lo que la conexión monta en el muro (tablero, medidor, pasarela, inversores y sus ductos) va 12 cm más
  afuera, delante de los parales.
- **`parasoles`** (un objeto o una lista), instanciados (una caja unitaria por color):
  - `"tipo": "vertical"`: aletas de `espesor` (6 cm), `profundidad` m y cada `separacion` m, desde la base (o 1,2 m sobre el volumen
    que tapa el muro; `desde` las sube) hasta casi el remate del antepecho, con ménsulas bajo cada losa. En el muro cortina van sobre
    los parales (la separación se redondea a un múltiplo del módulo). Se interrumpen sobre las puertas y donde llega un puente.
  - `"tipo": "horizontal"`: lamas de 4 cm inclinadas `inclinacion` (15°) en la parte alta de cada piso, cada `separacion` m y por encima
    de `antepecho` (1 m sobre el piso), sostenidas por platinas verticales cada ~3 m.
  ```json
  "parasoles": [ { "tipo": "vertical", "profundidad": 0.7, "separacion": 1.0, "color": "#b5895c", "lados": ["O"] },
                 { "tipo": "horizontal", "profundidad": 0.8, "separacion": 0.75, "color": "#c9ced2", "lados": ["S"] } ]
  ```
- **Núcleos de circulación** (escaleras y ascensores): van como volúmenes propios, por ejemplo en `concreto_visto` y más altos que la
  torre. Los muros que quedan dentro del otro volumen no se dibujan; en las fachadas nuevas, lo tapado por un volumen vecino con
  cubierta plana sube hasta el remate de su antepecho, así vidrio, ventanas y parasoles empiezan por encima de él.
- Límites: los acabados nuevos están pensados para volúmenes rectangulares con cubierta plana (en los hastiales de cubiertas inclinadas
  la textura queda a escala de 1 m y del color de `material`); los volúmenes con `poligono` no los usan.

### Elementos de obra nueva (`elementos`)

Se dibujan después de los demás elementos (ya se conocen los suelos y las cubiertas) y van a la capa de su `estado`.

- `marquesina_acceso`: losa delgada (borde de panel `color`, cielo raso `color_cielo` con luminarias empotradas) a `altura` m (3,8)
  y de `espesor` m (0,3), sobre columnas de acero de `diametro_columnas` (0,2 m) cada `sep_columnas` (5 m) en el `frente` (si no se
  indica, el lado más lejano de los volúmenes), o con `"apoyo": "voladizo"` y tensores al muro:
  `{ "tipo": "marquesina_acceso", "centro": [-4, -19.6], "largo": 14, "ancho": 5.2, "rumbo_eje": 90, "altura": 3.9 }`.
- `bahia_ambulancias`: marquesina alta (4,6 m libres; `"cubierta": false` la quita) con columnas gruesas y franjas de protección,
  recuadro amarillo, franja achurada de descargue contra el muro, `rotulo` en el piso ("AMBULANCIAS" por defecto) y bolardos contra el
  muro con un claro frente a cada puerta: `{ "tipo": "bahia_ambulancias", "centro": [24.5, -10], "largo": 12, "ancho": 9, "rumbo_eje": 0 }`.
- `puente`: puente cubierto y acristalado entre `desde` y `hasta`, con el piso a `altura` m; `ancho` (3 m), `alto` libre (3 m), enjuta
  baja, parales y pasamanos; `"estructura": "cercha"` (cerchas laterales, por defecto) o `"viga"` (vigas bajo la losa) y columnas en
  `apoyos`. Los extremos entran 30 cm en los volúmenes que tocan; un extremo libre lleva cierre de vidrio:
  `{ "tipo": "puente", "desde": [-10, 4], "hasta": [3, 4], "altura": 3.5, "apoyos": [[-3.5, 4]] }`.
- `equipo_cubierta`: se apoya en la cubierta más alta bajo `centro` (o en `base`) sobre su base de concreto. `equipo`: `uma`
  (manejadora de aire con juntas, manijas, toma con rejilla y caperuza, extractor y ductos), `chiller` (enfriador con rejillas de
  serpentín, ventiladores y tuberías), `tanque` (cilindro con tapa, refuerzos, escalera y tubería), `cuarto_maquinas` (caja con losa,
  puerta y rejilla; `material` puede ser `concreto_visto`) o `pantalla` (cerramiento de lamas a 45° sobre postes, abierto arriba, de
  `altura` m): `{ "tipo": "equipo_cubierta", "equipo": "pantalla", "centro": [5, 8], "largo": 18, "ancho": 13, "rumbo_eje": 90, "altura": 2.6 }`.
- `jardinera`: elevada (`alto` 0,45 m), de concreto o `"material": "metal"`, con tierra y arbustos instanciados (`"plantas": false` los quita).
- `banca`: apoyos de concreto y listones de madera (`"respaldo": true` agrega espaldar); `rumbo` es hacia dónde mira quien se sienta.
- `luminaria`: poste peatonal de `altura` m (4,5) con brazo y luminaria plana encendida; `rumbo` orienta el brazo.
  `banca` y `luminaria` aceptan `"centros": [[x,y], …]` para poner varias iguales.
- `letrero_institucional`: letras grandes en relieve, con tildes, de `altura` m (altura de las mayúsculas) y `profundidad` m. Con
  `volumen` y `lado` van de pie sobre el antepecho con una canaleta (`"sobre": "parapeto"`, por defecto) o en la fachada
  (`"sobre": "fachada"`, a la altura `y`); `pos` (0–1) las corre a lo largo del lado. Sin volumen van libres en `centro`, mirando hacia
  `rumbo`, con la base a `base` m (por ejemplo, sobre el borde de una marquesina):
  `{ "tipo": "letrero_institucional", "texto": "HOSPITAL HÉCTOR ABAD GÓMEZ", "volumen": "torre", "lado": "S", "altura": 1.1 }`.

Las bancas, luminarias y bolardos que se repiten menos de 10 veces se funden en la malla del entorno (no suman llamadas de dibujo);
bancas, luminarias, bolardos y arbustos no van en el LOD1.

### Pérgola solar (`adecuaciones.fv[]` con `"tipo": "pergola"`)

Arreglo sobre una estructura de acero apoyada en una cubierta plana, para que los equipos de la cubierta queden debajo: columnas cada
~6,5 m con dado, placa y riostras, vigas en la pendiente, vigas de amarre, correas bajo cada fila y canal en el borde bajo. La base es
la cubierta del `volumen` (o la más alta bajo `centro`); `altura` es la del plano de los módulos sobre ella (la luz libre bajo las vigas
es ~0,75 m menor); `inclinacion` 3° por defecto; módulos horizontales salvo `"orientacion_modulo": "vertical"`:
`{ "tipo": "pergola", "volumen": "torre", "centro": [5, 8], "largo": 19, "ancho": 13.5, "rumbo_eje": 90, "altura": 4.3, "filas": 11, "columnas": 8 }`.

## Herramientas de comparación

- `node scripts/modelos/render_vista.mjs <id> --pano <PANO> --rumbo R --pitch P --fov F --sv data/geo/img/<id>_foto.jpg --out data/geo/img/<id>_cmp.png --capa existente`
  compila el modelo (si la especificación cambió) y lo dibuja desde la posición de ese panorama con la misma cámara que `sv_pano.py`; deja
  `<out>_comparacion.png` (foto | modelo) y `<out>_mezcla.png` (50 % / 50 %) para comparar siluetas, alturas, pendientes y colores.
- `node scripts/modelos/render_vista.mjs <id> --orbita AZ,EL,DIST [--mira x,y,z] --out data/geo/img/<id>_orbita.png [--capa existente|todo]` vista aérea.
  Con `--entorno` usa el mapa de entorno y las luces de la web (RoomEnvironment): vidrios y metales se ven como en el visor.
- Compila en `data/geo/img/_modelos/<id>/`; la versión final para la web se genera con `cd scripts/modelos && node build_edificios.mjs`.
- `cd scripts/modelos && node check_coplanar.mjs [carpeta o .glb]` busca caras coplanares que parpadearían (z-fighting) y resume triángulos,
  llamadas de dibujo y peso de cada GLB. Si una especificación nueva deja muros o cubiertas en el mismo plano, el informe dice dónde.

## Reglas de calidad

1. **La huella sale del satélite** (`scripts/geo/trace.py` superpone la especificación sobre la imagen; iterar hasta que coincida
   con bordes de cubierta, ±0,5 m). Medir con la escala de la imagen (z19 ≈ 0,296 m/píxel en Yondó).
2. **Alturas, pisos, fachada, colores y cubierta salen de Street View** (`scripts/geo/cobertura.py` y `sv_pano.py`). Las fotos de 2013–2014
   pueden estar desactualizadas: contrastar con el satélite (más reciente) y con fotos web; anotar diferencias en `incertidumbres`.
3. **Nada inventado**: si algo no se ve, se deja el valor típico y se declara en `incertidumbres`.
4. Las adecuaciones se diseñan sobre la cubierta real: faldones con mejor orientación (norte–sur en esta latitud da igual; evitar sombras),
   retiros de 0,5 m a bordes y cumbrera, módulos de 2,28 × 1,13 m (550 Wp). Si la cubierta no alcanza para `kwp_plan`, decirlo y proponer
   marquesina o reducción.
5. Las imágenes de Google y Esri se usan solo como referencia de levantamiento: **no se publican** (están en `data/geo/img/`, ignorado por git).
   En la web se enlaza al panorama de Google Maps.
