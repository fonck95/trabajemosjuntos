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
        "material": "pañete_pintado|ladrillo_visto|bloque|metal|vidrio",
        "color": "#f2efe6", "zocalo": { "color": "#7a2b2b", "altura": 0.9 },
        "ventanas": { "tipo": "ventana|celosia|calado|vitrina|reja", "ancho": 1.5, "alto": 1.2, "antepecho": 1.0,
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
  anden, zona_verde, plaza, cubierta_ligera, asta, poste, torre, antena, planta_electrica, aire_acondicionado.
- `adecuaciones.cubierta_nueva` (opcional): `{ "material": "termoacustica", "color": "#e9e7e1", "volumenes": ["bloque_a"] }`. Si no se indica, pero
  `obras_civiles` menciona un cambio de cubierta, se reemplazan las cubiertas inclinadas de zinc o fibrocemento por termoacústica.
  Solo los volúmenes reemplazados cambian de cubierta en la vista "Con el proyecto"; las demás cubiertas, las de los corredores y las de los
  elementos (`cubierta_ligera`, canchas cubiertas) se conservan. Indica `volumenes` explícitamente cuando no todas las cubiertas se cambian.
- `fv[].faldon` elige la cara de la cubierta cuya normal apunta más hacia ese punto cardinal; en techos curvos, `N`/`S` (o `E`/`O`) eligen la mitad de la bóveda.
  En techo plano, `inclinacion` y `azimut` (grados desde el norte hacia donde mira el panel).
- `kwp_factible` debe ser igual a módulos × 0,55; el generador avisa si no coincide.

## Herramientas de comparación

- `node scripts/modelos/render_vista.mjs <id> --pano <PANO> --rumbo R --pitch P --fov F --sv data/geo/img/<id>_foto.jpg --out data/geo/img/<id>_cmp.png --capa existente`
  compila el modelo (si la especificación cambió) y lo dibuja desde la posición de ese panorama con la misma cámara que `sv_pano.py`; deja
  `<out>_comparacion.png` (foto | modelo) y `<out>_mezcla.png` (50 % / 50 %) para comparar siluetas, alturas, pendientes y colores.
- `node scripts/modelos/render_vista.mjs <id> --orbita AZ,EL,DIST [--mira x,y,z] --out data/geo/img/<id>_orbita.png [--capa existente|todo]` vista aérea.
- Compila en `data/geo/img/_modelos/<id>/`; la versión final para la web se genera con `cd scripts/modelos && node build_edificios.mjs`.

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
