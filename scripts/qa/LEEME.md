# QA del atlas en Chromium sin pantalla

Herramientas para probar las vistas del atlas en un navegador real sin depender de la red: `scripts/qa/comun.mjs` (equipo D) y los guiones que la usan, `scripts/qa/torre_qa.mjs` (D), `scripts/qa/recorrido_qa.mjs` (C) y `scripts/sismo/qa_worker.mjs` (A). Contrato: `data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md`, secciones 2.1, 12.1 y 13.

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

Las versiones deben ser exactamente las del importmap y del `<script>` de `web/index.html` (three 0.160.0 y GSAP 3.12.5); si no coinciden, `comun.mjs` avisa en la consola. Sirve también una carpeta `node_modules` de un `npm install three@0.160.0 gsap@3.12.5`: la estructura es la misma (`<carpeta>/three/…`, `<carpeta>/gsap/…`).

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

`web/index.html` no trae `<!doctype>`, `<head>` ni `<body>` (se publica también como Artifact, que los agrega): el servidor de QA lo envuelve igual que `scripts/build_site.py`, para que el navegador no lo lea en modo «quirks».

## 3. Uso como biblioteca

```js
import { opciones, servidor, navegador, abrir, esperar, irAVista, desborde, textosInternos, captura, informe } from '../qa/comun.mjs';

const op = opciones();                                  // lee --vendor, --raiz, --base, --salida, --puerto (y las demás --clave valor)
const srv = await servidor(op);                         // { url, puerto, cerrar() }
const nav = await navegador(op);                        // Chromium de Playwright con WebGL por software
const { page, registro, cerrar } = await abrir(nav, op, {
  url: `${srv.url}?qa=1#torre`,                         // la marca de QA va en la consulta, no en el «hash» (8.7)
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

**Fallas esperadas mientras se integra.** `torre.js` carga los módulos nuevos con `import('./torre/recorrido.js').catch(() => import('./torre/_relleno.js'))` (y lo mismo con `sismo.js`, `habilitacion.js` y `contraste.js`). Mientras un equipo no suba su módulo, el navegador registra un 404 y la vista usa el relleno «en construcción»; esos 404 se declaran en `esperados`. Los datos de los modos nuevos (`web/data/torre_*.json`, `web/data/sismo_*.json`) solo se piden cuando el módulo real está; si `build_data.py` todavía no los escribe, el modo recibe `null`.

## 4. Ganchos de la vista de la torre (`?qa=1`)

Con `index.html?qa=1#torre`, `torre.js` publica `window.__torreQA` (8.7): `modo()` (modo actual), `modo(m, op)` (cambia de modo y devuelve una promesa), `stats()` (`{ llamadas, triangulos }` de un cuadro), `recorrido.{ irA, estado, libre }`, `sismo.{ calcular, ultimo, motor, cubiertaDibujada }`, y para la QA de integración `relleno(m)` (si el modo usa el relleno), `listo()` (si llegaron los datos de la vista) y `exterior()` (qué oculta del modelo el modo en curso). Sin `?qa` no existe.
