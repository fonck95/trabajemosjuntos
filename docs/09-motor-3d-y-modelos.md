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

- **Capa `existente`:** muros con textura en metros; ventanas con marco y alféizar; puertas; zócalo y bandas de entrepiso; corredores con columnas.
  - Cubiertas: a dos aguas, a cuatro aguas, a una agua, curvas o planas, con voladizos y texturas de zinc, fibrocemento, termoacústica o teja.
  - Letreros en relieve con tildes compuestas.
  - Entorno: rejas, muros, tanques elevados, árboles instanciados, canchas, parqueaderos, astas, torres, plantas eléctricas.
- **Capa `adecuaciones`:**
  - módulos solares instanciados sobre el faldón elegido o en racks sobre losa;
  - marquesinas solares;
  - baterías (gabinetes o contenedores de 10 y 20 pies);
  - inversores, medidor bidireccional, pasarela IoT y ductos;
  - cargador de vehículo eléctrico;
  - cubierta nueva cuando hay que reemplazar la existente.
- **Instancias por capa.** El generador crea las instancias GPU (`EXT_mesh_gpu_instancing`) dentro de cada capa, para que el botón "Hoy / Con el proyecto" pueda apagar una capa completa. La función `instance()` de gltf-transform no sirve aquí porque las mueve a la raíz.
- **Dos niveles de detalle.** `_lod0` lleva marcos, módulos individuales y barrotes; `_lod1` lleva módulos como planos con textura y rejas simplificadas. Ambos van comprimidos con Draco y tienen copia `.glb.json`.

```bash
cd scripts/modelos
node build_edificios.mjs                 # todas las sedes → web/models/edificios/ + manifest.json
node build_edificios.mjs hospital        # solo una
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
