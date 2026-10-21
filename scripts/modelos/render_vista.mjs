// Render de verificación de una réplica: desde la posición de un panorama de Street View (para comparar
// con la foto real) o en órbita (para revisar el modelo). Usa Chromium sin pantalla con SwiftShader.
//
// Uso:
//   node render_vista.mjs <id> --pano PANO_ID --rumbo R [--pitch P] [--fov F] [--sv foto.jpg] --out salida.png [--capa existente|todo]
//   node render_vista.mjs <id> --orbita AZ,EL,DIST [--mira x,y,z] [--fov F] --out salida.png [--capa existente|todo]
// Con --sv escribe además salida_comparacion.png (foto | modelo) y salida_mezcla.png (50 % / 50 %).
// --fov es horizontal en grados, igual que scripts/geo/sv_pano.py (W = 1400, H = 900).
import { createServer } from 'node:http';
import { readFileSync, existsSync, statSync, writeFileSync, mkdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { extname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const ROOT = resolve(HERE, '../..');
const args = process.argv.slice(2);
const id = args[0];
const opt = (k, d) => { const i = args.indexOf(`--${k}`); return i >= 0 ? args[i + 1] : d; };
if (!id || !opt('out')) { console.error('uso: node render_vista.mjs <id> (--pano ID --rumbo R | --orbita AZ,EL,DIST) --out salida.png'); process.exit(1); }
const DATA = process.env.EDIFICIOS_DIR || join(ROOT, 'data/edificios');
// Por defecto compila en una carpeta temporal por edificio (data/geo/img/_modelos/<id>, ignorada por git) para que
// varios levantamientos simultáneos no se pisen el manifest; la compilación final va a web/models/edificios.
const OUTDIR = process.env.EDIFICIOS_OUT || join(ROOT, 'data/geo/img/_modelos', id);
const specPath = join(DATA, `${id}.json`), glbPath = join(OUTDIR, `${id}_lod0.glb`);
const spec = JSON.parse(readFileSync(specPath, 'utf8'));

// reconstruye el modelo si la especificación es más nueva que el GLB
mkdirSync(OUTDIR, { recursive: true });
if (!existsSync(glbPath) || statSync(glbPath).mtimeMs < statSync(specPath).mtimeMs) {
  const r = spawnSync('node', ['build_edificios.mjs', id], { cwd: HERE, encoding: 'utf8', env: { ...process.env, EDIFICIOS_DIR: DATA, EDIFICIOS_OUT: OUTDIR } });
  process.stdout.write((r.stdout || '').split('\n').filter((l) => !/^(instance|prune)/.test(l)).join('\n'));
  if (r.status) { console.error(r.stderr); process.exit(1); }
}

const W = 1400, H = 900, CAM_H = 2.5;
const k = 111320, cosl = Math.cos((spec.lat * Math.PI) / 180);
let cam, look, vfov;
const hfov = +opt('fov', 80);
vfov = (2 * Math.atan(Math.tan((hfov * Math.PI) / 360) * (H / W)) * 180) / Math.PI;
if (opt('pano')) {
  // posición del panorama (caché local para no consultar cada vez)
  const cachePath = join(ROOT, 'data/geo/img/pano_cache.json');
  const cache = existsSync(cachePath) ? JSON.parse(readFileSync(cachePath, 'utf8')) : {};
  const pid = opt('pano');
  if (!cache[pid]) {
    const r = spawnSync('python3', ['-c', `from streetlevel import streetview\np=streetview.find_panorama_by_id(${JSON.stringify(pid)})\nprint(p.lat, p.lon, p.date)`], { encoding: 'utf8' });
    const [la, lo] = (r.stdout || '').trim().split(/\s+/).map(Number);
    if (!Number.isFinite(la)) { console.error('no se encontró el panorama', pid, r.stderr); process.exit(1); }
    cache[pid] = [la, lo]; writeFileSync(cachePath, JSON.stringify(cache));
  }
  const [la, lo] = cache[pid];
  const x = (lo - spec.lon) * k * cosl, y = (la - spec.lat) * k;
  const r = (+opt('rumbo', 0) * Math.PI) / 180, p = (+opt('pitch', 5) * Math.PI) / 180;
  cam = [x, CAM_H, -y];
  look = [x + Math.sin(r) * Math.cos(p) * 10, CAM_H + Math.sin(p) * 10, -y - Math.cos(r) * Math.cos(p) * 10];
  console.log(`cámara en x=${x.toFixed(1)} m (este), y=${y.toFixed(1)} m (norte) respecto al ancla; distancia ${Math.hypot(x, y).toFixed(1)} m`);
} else {
  const [az, el, dist] = (opt('orbita', '210,30,60')).split(',').map(Number);
  const m = (opt('mira', '0,3,0')).split(',').map(Number);
  const a = (az * Math.PI) / 180, e = (el * Math.PI) / 180;
  cam = [m[0] + Math.sin(a) * Math.cos(e) * dist, m[1] + Math.sin(e) * dist, m[2] - Math.cos(a) * Math.cos(e) * dist];
  look = m;
}

// servidor estático mínimo desde la raíz del repo
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.glb': 'model/gltf-binary', '.wasm': 'application/wasm', '.png': 'image/png' };
const server = createServer((req, res) => {
  const u = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const f = u.startsWith('/__out/') ? join(OUTDIR, u.slice(7)) : join(ROOT, u);
  if (!f.startsWith(ROOT) && !f.startsWith(OUTDIR)) { res.writeHead(403).end(); return; }
  try { const b = readFileSync(f); res.writeHead(200, { 'content-type': MIME[extname(f)] || 'application/octet-stream' }).end(b); } catch { res.writeHead(404).end(); }
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const port = server.address().port;
const { chromium } = await import(pathToFileURL('/opt/node-tools/node_modules/playwright/index.mjs').href);
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: W, height: H } });
const errs = []; page.on('console', (m) => m.type() === 'error' && errs.push(m.text())); page.on('pageerror', (e) => errs.push(String(e)));
const qs = new URLSearchParams({ glb: `/__out/${id}_lod0.glb`, cam: cam.join(','), look: look.join(','), fov: vfov.toFixed(3), w: W, h: H, capa: opt('capa', 'todo') });
await page.goto(`http://127.0.0.1:${port}/scripts/modelos/render.html?${qs}`);
await page.waitForFunction(() => window.__listo || window.__error, null, { timeout: 120000 });
const err = await page.evaluate(() => window.__error);
if (err) { console.error('error al cargar el modelo:', err, errs); }
const out = resolve(opt('out'));
await page.screenshot({ path: out });
await browser.close(); server.close();
if (errs.length) console.warn('consola:', errs.slice(0, 5).join(' | '));
console.log('render:', out);
const sv = opt('sv');
if (sv) {
  const base = out.replace(/\.png$/i, '');
  const py = `from PIL import Image\nimport sys\na=Image.open(sys.argv[1]).convert('RGB').resize((${W},${H}))\nb=Image.open(sys.argv[2]).convert('RGB').resize((${W},${H}))\nc=Image.new('RGB',(${W * 2},${H}))\nc.paste(a,(0,0)); c.paste(b,(${W},0)); c.save(sys.argv[3])\nImage.blend(a,b,0.5).save(sys.argv[4])`;
  const r = spawnSync('python3', ['-c', py, resolve(sv), out, `${base}_comparacion.png`, `${base}_mezcla.png`], { encoding: 'utf8' });
  if (r.status) console.error(r.stderr); else console.log('comparación:', `${base}_comparacion.png`, '· mezcla:', `${base}_mezcla.png`);
}
