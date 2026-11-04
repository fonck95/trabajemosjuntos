# Bibliotecas incluidas en el sitio

`web/*.html` sigue pidiendo three y GSAP a cdnjs y jsdelivr, porque `web/atlas.html` también se publica como Artifact de
Claude, que solo admite scripts de esos CDN. `scripts/build_site.py` cambia esas URL en `site/` por estas copias: en
Railway el sitio comparte origen con el panel (`/panel/`), así que ahí solo corre código del repositorio y la CSP del
sitio no admite scripts de terceros.

| Carpeta | Qué es | Origen | Licencia |
|---|---|---|---|
| `gsap-3.12.5/gsap.min.js` | GSAP 3.12.5 | `dist/gsap.min.js` de `https://registry.npmjs.org/gsap/-/gsap-3.12.5.tgz`; idéntico byte a byte al de cdnjs | Licencia estándar de GSAP (https://gsap.com/standard-license), que permite usarlo y alojarlo sin costo; el aviso va en la cabecera del archivo |
| `three-0.160.0/` | three.js 0.160.0: `build/three.module.js`, los 28 módulos de `examples/jsm/` que usa `web/js` (con lo que ellos importan) y `examples/fonts/helvetiker_bold.typeface.json` (letras 3D de la propuesta) | `https://registry.npmjs.org/three/-/three-0.160.0.tgz`, sin cambios | MIT (`three-0.160.0/LICENSE`); la fuente, MgOpen (`three-0.160.0/examples/fonts/LICENSE`) |
| `draco/`, `basis/` | Decodificadores de Draco y Basis (KTX2) que cargan `DRACOLoader` y `KTX2Loader` desde `web/js/assets.js`. El transcodificador de Basis necesita evaluar código (embind usa `new Function`) y la CSP del sitio en Railway no lo deja (`'wasm-unsafe-eval'` solo cubre WebAssembly): ahí `assets.js` no registra `KTX2Loader` y un GLB que exige KTX2 termina en un aviso. Sí se usa en el Artifact y en GitHub Pages | Ya estaban. `basis/` es igual al de `examples/jsm/libs/basis/` de three 0.160.0; `draco/` es otra compilación del decodificador de Draco | Apache 2.0 |

Los dos paquetes se comprobaron contra `dist.integrity` del registro de npm (`https://registry.npmjs.org/three/0.160.0`
y `https://registry.npmjs.org/gsap/3.12.5`):

- `three-0.160.0.tgz`: `sha512-DLU8lc0zNIPkM7rH5/e1Ks1Z8tWCGRq6g8mPowdDJpw1CFBJMU7UoJjC6PefXW7z//SSl0b2+GCw14LB+uDhng==`
- `gsap-3.12.5.tgz`: `sha512-srBfnk4n+Oe/ZnMIOXt3gT605BX9x5+rh/prT2F1SsNJsU1XuMiP0E2aptW481OnonOGACZWBqseH5Z7csHxhQ==`

## Regenerar

Si `web/js` empieza a importar otro módulo de `three/addons/`, `python3 scripts/build_site.py` falla y dice cuál falta.
Para rehacer la copia (fuera del repositorio, en una carpeta vacía):

```bash
curl -sSfLO https://registry.npmjs.org/three/-/three-0.160.0.tgz
curl -sSf https://registry.npmjs.org/three/0.160.0 | python3 -c "import json,sys; print(json.load(sys.stdin)['dist']['integrity'])"
echo "sha512-$(openssl dgst -sha512 -binary three-0.160.0.tgz | base64 -w0)"   # debe ser igual a la línea anterior
mkdir three && tar -xzf three-0.160.0.tgz -C three
python3 <repositorio>/scripts/build_site.py --three-desde three/package
```

`--three-desde` borra `web/vendor/three-0.160.0/` y copia `LICENSE`, `build/three.module.js`, el cierre de los imports
de `three/addons/` de `web/js` (estáticos y dinámicos, siguiendo los imports relativos dentro de `examples/jsm/`) y la
fuente. Para GSAP: el mismo paso con `gsap-3.12.5.tgz` y copiar `package/dist/gsap.min.js` a `gsap-3.12.5/`. Si cambia
una versión, cambie también las URL de `web/*.html` y la tabla `CDN` de `scripts/build_site.py`.
