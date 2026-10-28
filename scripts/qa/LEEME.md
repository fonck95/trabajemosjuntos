# QA del atlas en Chromium sin pantalla

Herramientas para probar las vistas del atlas en un navegador real sin depender de la red: `scripts/qa/comun.mjs` (equipo D) y los guiones que la usan (sección 3): `torre_qa.mjs` y `sismo_qa.mjs` (D), `recorrido_qa.mjs` y `equipos_qa.mjs` (C), `bim_qa.mjs` (F) y `scripts/sismo/qa_worker.mjs` (A). Contrato: `data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md`, secciones 2.1, 12.1, 13 y 17.7.

El sitio carga three.js y GSAP de CDN (`cdn.jsdelivr.net`, `cdnjs.cloudflare.com`) y las tipografías de Google Fonts. En el entorno de QA esos sitios pueden estar bloqueados, así que `comun.mjs` desvía esas peticiones a una carpeta local (`--vendor`) y corta cualquier otra petición externa. Nada de lo que piden los criterios de aceptación puede depender de archivos que solo estén en la carpeta temporal de una sesión: esta guía dice cómo armarlos en cualquier máquina.

## 1. Preparar three, GSAP y Playwright

Se necesitan Node 18 o más reciente y acceso al registro de npm (o los `.tgz` copiados de otra máquina).

```bash
# carpeta de copias locales (fuera del repositorio; el nombre es libre)
mkdir -p ~/atlas-vendor && cd ~/atlas-vendor
npm pack three@0.160.0 gsap@3.12.5          # descarga three-0.160.0.tgz y gsap-3.12.5.tgz
mkdir three gsap
tar xzf three-0.160.0.tgz -C three --strip-components=1
tar xzf gsap-3.12.5.tgz -C gsap --strip-components=1
ls three/build/three.module.js three/examples/jsm/controls/OrbitControls.js gsap/dist/gsap.min.js   # deben existir
```

Las versiones deben ser exactamente las del importmap y del `<script>` de `web/atlas.html` (three 0.160.0 y GSAP 3.12.5); si no coinciden, `comun.mjs` avisa en la consola. Sirve también una carpeta `node_modules` de un `npm install three@0.160.0 gsap@3.12.5`: la estructura es la misma (`<carpeta>/three/…`, `<carpeta>/gsap/…`).

Tipografías (opcional): si la carpeta trae `fonts.css` (la hoja de Google Fonts guardada) y sus `.woff2` en `fonts/`, se usan; si no, se sirve una hoja vacía y el navegador usa las tipografías de respaldo (las capturas cambian un poco, la QA no).

Playwright con Chromium:

```bash
npm install -g playwright@1.63      # o en una carpeta cualquiera: npm install playwright
npx playwright install chromium     # descarga Chromium (unos 150 MB); en Linux sin dependencias: npx playwright install --with-deps chromium
export PLAYWRIGHT_MODULE="$(npm root -g)/playwright"   # carpeta del módulo; sin esta variable se usa import('playwright')
```

Si el navegador ya está instalado en otra carpeta, se indica con `PLAYWRIGHT_BROWSERS_PATH`. WebGL corre por software (SwiftShader, banderas en `ARGS_CHROMIUM` de `comun.mjs`): no hace falta GPU.

## 2. Prueba de humo

```bash
python3 scripts/build_data.py                      # deja web/data y web/js/data.js al día
node scripts/qa/comun.mjs --vendor ~/atlas-vendor --vistas dinero,torre,ciudad --temas claro,oscuro --telefono
```

Abre cada vista en escritorio (1400 × 900) y teléfono (390 × 844, táctil), en tema claro y oscuro; espera el lienzo 3D, revisa la consola y el desborde horizontal y guarda una captura por caso. Sale con código 1 si algo falla.

Opciones comunes a todos los guiones que usan `comun.mjs`:

| Opción | Por omisión | Qué hace |
|---|---|---|
| `--vendor <carpeta>` | variable `QA_VENDOR` | Copias locales de three y GSAP (sección 1) |
| `--raiz web\|site\|.` | `web` | Qué se sirve: `web/` tal cual, `site/` (después de `python3 scripts/build_site.py`) o cualquier carpeta del repositorio (`.` sirve la raíz, útil para probar los fixtures de `scripts/fixtures/`) |
| `--base /subruta/` | `/` | Sirve el sitio bajo una subruta, como GitHub Pages (`/trabajemosjuntos/`) |
| `--salida <carpeta>` | carpeta temporal del sistema (`atlas_qa`) | Capturas e informes; nunca dentro del repositorio |
| `--puerto <n>` | libre | Puerto del servidor local |
| `--url <sitio>` | — | No levanta servidor: usa el sitio ya servido en esa dirección (Caddy con el `Caddyfile` del repositorio, un despliegue) |

`web/atlas.html` no trae `<!doctype>`, `<head>` ni `<body>` (se publica también como Artifact, que los agrega): el servidor de QA lo envuelve igual que `scripts/build_site.py`, para que el navegador no lo lea en modo «quirks». El Home (`web/index.html`) y la propuesta (`web/propuesta.html`) son documentos completos y pasan tal cual; el Home manda a `atlas.html` los enlaces viejos con vista en el «hash» (`index.html?qa=1#torre`, `#dinero`…).

## 3. Guiones de QA

Todos usan las opciones de la sección 2, salen con código 1 si algo falla y dejan capturas e informe (JSON) en `--salida`. Antes de correrlos: `flock /tmp/torre_build.lock python3 scripts/build_data.py` (con `flock` si otros procesos pueden estar regenerando datos a la vez) y, para probar el sitio empaquetado, `python3 scripts/build_site.py`. Con WebGL por software, la QA completa de la torre tarda del orden de una hora; `--solo` elige partes.

| Guion | Dueño | Qué prueba | Partes (`--solo`) |
|---|---|---|---|
| `scripts/qa/torre_qa.mjs` | D | QA global de la vista de la torre (13.4, 13.6, 17.7) y del resto del sitio: datos publicados (límites del 10.1, campos internos, huellas `insumos_sha1` de toda la cadena, la estructura publicada da el mismo cálculo bit a bit que la completa); todos los modos (Hoy, Con la torre, Proyecto tipo, Pisos por servicio, Laboratorio, Recorrer por dentro, Simulador sísmico con un cálculo real, Modelo BIM) en claro, oscuro, escritorio y teléfono con presupuesto de dibujo, desborde, textos sin rutas, tarjetas de abajo y la Res. 1732 solo como revocada; el simulador del 13.4 (nido_2015 y local_hip, cubierta dibujada en todos los pasos, respaldo sin Worker, «Cancelar» ≤ 300 ms); cambios de modo a mitad de un cálculo o de un vuelo; las otras 9 vistas; el sitio publicado (subruta o `--url`: archivos partidos, Worker de módulo, descarga de los IFC) y la prueba de humo de rendimiento en teléfono con la CPU ×4 | `datos,modos,sismo,carrera,vistas,publicado,rendimiento`; `--rapido`: solo claro-escritorio y oscuro-teléfono |
| `scripts/qa/sismo_qa.mjs` | D | Simulador sísmico a fondo (8 y 13.4): trabajador simulado con los fixtures del Anexo A en claro, oscuro y teléfono; motor real; respaldo sin Worker con el cubo de prueba; vista sin modelo estructural publicado; correcciones de la revisión (regiones vivas, foco, cancelar, salir a mitad, reproducción fuera de pantalla, búferes de WebGL). Sirve la raíz del repositorio | `simulado,real,respaldo,sin_estructura,revision` |
| `scripts/qa/recorrido_qa.mjs` | C | Recorrido en primera persona (6, 13.3, 16.6): niveles (y la barra en anchos intermedios), alcance, «Ir a» cada unidad, guion de teclas, juego (escalera de evacuación por su puerta, salto, dinteles, pararse sobre equipos, modo espectador y pantalla completa), flujos, teclado, presupuesto por nivel y salida | `niveles,alcance,unidades,guion,juego,flujo,teclado,presupuesto,salida` |
| `scripts/qa/equipos_qa.mjs` | C | Catálogo 3D de equipos (5, 16.5): API, grilla de modelos, capas por piso, teléfono. Sirve la raíz del repositorio | `api,grilla,piso,telefono` |
| `scripts/qa/bim_qa.mjs` | F | Modo «Modelo BIM» (17.5, 17.7): terreno y cimentación, vistas, cortes, refuerzo, 5D, 4D, colores del sismo, selección, descarga del IFC y salida | `terreno,vistas,sismo,seleccion,ifc,salida,movimiento` |
| `scripts/sismo/qa_worker.mjs` | A | Motor sísmico en Chromium (7.5, 7.7, 13.1): protocolo del Worker de módulo en la raíz y en `/trabajemosjuntos/`, cancelar, respaldo bit a bit, tiempos (teléfono con CPU ×4) y memoria | `--rapido`, `--sin-vista` |
| `scripts/qa/comun.mjs` | D | Prueba de humo de varias vistas (sección 2) | `--vistas`, `--temas`, `--telefono` |

Orden sugerido para una QA completa:

```bash
export PLAYWRIGHT_MODULE="$(npm root -g)/playwright" V=~/atlas-vendor
flock /tmp/torre_build.lock python3 scripts/build_data.py && python3 scripts/build_site.py
node scripts/qa/torre_qa.mjs --vendor $V                 # global (incluye el sitio en /trabajemosjuntos/ y el rendimiento)
node scripts/qa/sismo_qa.mjs --vendor $V
node scripts/qa/recorrido_qa.mjs --vendor $V
node scripts/qa/bim_qa.mjs --vendor $V
node scripts/qa/equipos_qa.mjs --vendor $V
node scripts/sismo/qa_worker.mjs --vendor $V
```

**El sitio como en Railway (Caddy).** Railway sirve `site/` con el `Caddyfile` del repositorio a través de Railpack, que reemplaza `{{.StaticFileRoot}}` y quita los bloques `{{if .IndexFallback}}…{{end}}`. Para probarlo en local con un binario de Caddy 2: hacer esos dos reemplazos en una copia del `Caddyfile` (fuera del repositorio), `PORT=8137 caddy run --config <copia> --adapter caddyfile` y luego `node scripts/qa/torre_qa.mjs --vendor $V --solo publicado --url http://127.0.0.1:8137/`. Sin Caddy, `--solo publicado` sin `--url` sirve `site/` bajo `/trabajemosjuntos/` con el servidor de `comun.mjs` (mismos tipos MIME y `nosniff`).

**Otras verificaciones (sin navegador).** Datos y motor: `python3 scripts/torre/validar_plantas.py`, `python3 scripts/torre/validar_inventario.py`, `python3 scripts/torre/test_torre.py`, `python3 scripts/torre/validar_contraste.py`, `python3 scripts/torre/verificar_cifras_docs.py` (13.2 y 13.5); `node scripts/sismo/test_motor.mjs`, `python3 scripts/sismo/estructura_torre.py --verificar`, `node scripts/sismo/validar_resultado.mjs <resultado.json>`, `python3 scripts/sismo/validar_opensees.py` en el entorno de validación de `scripts/sismo/requisitos_validacion.txt` (13.1); `python3 scripts/bim/validar_ifc.py` (con ifcopenshell) y `python3 scripts/bim/interferencias.py` (17.7); `node scripts/verificar_sim.mjs` (simulación de la microrred).

## 4. Uso como biblioteca

```js
import { opciones, servidor, navegador, abrir, esperar, irAVista, desborde, textosInternos, captura, informe } from '../qa/comun.mjs';

const op = opciones();                                  // lee --vendor, --raiz, --base, --salida, --puerto (y las demás --clave valor)
const srv = await servidor(op);                         // { url, puerto, cerrar() }
const nav = await navegador(op);                        // Chromium de Playwright con WebGL por software
const { page, registro, cerrar } = await abrir(nav, op, {
  url: `${srv.url}atlas.html?qa=1#torre`,               // la marca de QA va en la consulta, no en el «hash» (8.7)
  tema: 'oscuro',                                       // 'claro' | 'oscuro'
  telefono: true,                                       // 390 × 844, táctil, ×2
  esperados: [/\/js\/scenes\/torre\/recorrido\.js$/],   // URL que pueden fallar sin contar como error
  // sinWorker: true,                                   // la página no tiene Worker (respaldo del simulador, 7.5)
  // movimientoReducido: true,                          // prefers-reduced-motion
});
await esperar(page, () => window.__torreQA?.listo());   // espera una condición en la página
const d = await desborde(page);                         // { ok, scrollWidth, innerWidth, culpables }
const internos = await textosInternos(page, '#v-torre');// texto visible con «.json», «data/» o «→ clave» (13.4 y 13.6)
await captura(page, op, 'torre-oscuro-telefono');
const ok = informe(registro, 'torre oscuro teléfono');  // imprime y devuelve true si no hubo errores ni fallas
await cerrar(); await nav.close(); await srv.cerrar();
```

`registro` junta los errores y avisos de la consola, las excepciones de la página, las peticiones locales fallidas o con respuesta ≥ 400 y, aparte, las fallas esperadas. Una petición cancelada (`ERR_ABORTED`, por ejemplo al cambiar de vista con una carga en curso) cuenta como aviso.

**Módulos que faltan.** `torre.js` carga los módulos de los modos con `import('./torre/recorrido.js').catch(() => import('./torre/_relleno.js'))` (y lo mismo con `sismo.js`, `bim.js`, `habilitacion.js` y `contraste.js`). Si un módulo no está (404), la vista usa el relleno «en construcción» y ese 404 se puede declarar en `esperados`; hoy todos están, así que los guiones no declaran ninguno. Si un archivo de `web/data` no está publicado, el modo recibe `null` y lo dice.

## 5. Ganchos de la vista de la torre (`?qa=1`)

Con `atlas.html?qa=1#torre`, `torre.js` publica `window.__torreQA` (8.7): `modo()` (modo actual), `modo(m, op)` (cambia de modo y devuelve una promesa), `stats()` (`{ llamadas, triangulos }` de un cuadro; el primer cuadro después de un cambio puede incluir el mapa de sombras, que se dibuja una sola vez: para el presupuesto se mide el siguiente), `recorrido.{ irA, estado, libre }`, `sismo.{ calcular, ultimo, motor, cubiertaDibujada }`, `bim.api()` (la API del modo BIM ya montado: `estado()`, `pestana(id)`, `comportamiento(campo)`…), y para la QA de integración `relleno(m)` (si el modo usa el relleno), `listo()` (si llegaron los datos de la vista), `exterior()` (qué oculta del modelo el modo en curso), `seleccionables()` (objetos que reciben clics del Stage: 0 en los modos con módulo propio), `pisos()` («Pisos por servicio»: `{ pisos, planta, sep, elegido, grupos }`) y `datos(archivo)` (promesa con un archivo de `web/data` tal como lo recibe cada modo, con las partes ya juntas; `null` si no está publicado). Sin `?qa` no existe.

**Archivos de datos partidos por tamaño.** Si un archivo de la torre pasa su límite del 10.1, `build_data.py` lo parte: el principal (`torre_plantas.json`, `torre_inventario.json`, `torre_habilitacion.json`) queda con `partes: { archivos, nota }` y cada parte (`torre_plantas_P1.json`, `torre_inventario_P2.json`, `torre_inventario_implementos.json`, `torre_habilitacion_1.json`…) trae trozos de listas, que se concatenan en el orden de `archivos`, y de diccionarios, que se suman. La planta y las unidades del inventario se parten por nivel (EXT, P1-P4, BT, CUB); la matriz, por grupos de servicios. `torre.js` las junta antes de pasar los datos a cada modo, así que C y E reciben el mismo esquema que con un solo archivo; un guion que lea `web/data` directamente debe juntarlas igual. `validar_inventario.py --web` revisa un solo archivo: `build_data.py` corre esa misma validación sobre la forma completa e imprime el resultado.
