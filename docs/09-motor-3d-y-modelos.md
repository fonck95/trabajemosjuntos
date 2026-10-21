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

## 4. Agregar un modelo profesional

1. Exportar a **glTF binario (.glb)** desde Revit (complemento glTF o vía IFC → Blender), SketchUp, Rhino o Blender, en metros y con +Y arriba.
2. Optimizar:
   ```bash
   npx @gltf-transform/cli optimize entrada.glb salida_lod0.glb --compress draco --texture-compress ktx2
   npx @gltf-transform/cli simplify salida_lod0.glb salida_lod1.glb --ratio 0.25 --error 0.01
   ```
3. Copiar a `web/models/` y agregarlo a `web/models/manifest.json` para verlo en la vista **Modelos 3D**, donde se puede revisar su costo antes de usarlo.
4. Usarlo en una escena con `progressiveLOD([{ url: 'models/salida_lod0.glb', distance: 0 }, { url: 'models/salida_lod1.glb', distance: 85 }])`.

Presupuesto recomendado para que funcione en teléfonos: menos de 300.000 triángulos visibles, menos de 50 llamadas de dibujo y texturas de 2048 px como máximo, en KTX2.

## 5. Diseño y transiciones

- **Estética del logo "¡Trabajemos juntos!"**: titulares en tipografía condensada negra (Anton) que atraviesan un globo de diálogo de contorno rojo, con la cola del globo hacia abajo; pestaña activa con el mismo globo; paleta blanco, negro y rojo en tema claro y oscuro.
- **GSAP**: el globo se dibuja de izquierda a derecha, el titular entra palabra por palabra, las tarjetas se escalonan, las cifras cuentan hasta su valor, la cámara vuela a su posición, las columnas de datos crecen con retraso escalonado y las vistas se cruzan con un fundido corto. Con "reducir movimiento" activado en el sistema, todo aparece sin animación.
