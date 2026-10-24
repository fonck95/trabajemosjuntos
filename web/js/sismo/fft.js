// Transformada rápida de Fourier (FFT) radix-2 propia, determinista y sin dependencias (contrato, 7.4).
// Módulo puro: sin DOM ni three.
//
// Convención (la de numpy.fft y la de Boore, 2003):
//   directa  X_k = Σ_{n=0}^{N−1} x_n · e^{−2πi·k·n/N}
//   inversa  x_n = (1/N) · Σ_{k=0}^{N−1} X_k · e^{+2πi·k·n/N}
// La amplitud de Fourier de una señal muestreada cada Δt (unidades de la señal × s) es |Δt·X_k| en
// f_k = k/(N·Δt). Las funciones reales (rfft, irfft) trabajan con los N/2 + 1 coeficientes k = 0…N/2: como la
// señal es real, X_{N−k} = conj(X_k) y el resto no aporta información.
//
// Algoritmo: Cooley-Tukey iterativo con decimación en el tiempo (permutación por inversión de bits y
// mariposas de tamaño 2, 4, …, N). La FFT real de N puntos se hace con una FFT compleja de N/2 puntos
// (pares en la parte real, impares en la imaginaria) y un paso de separación; así cuesta la mitad.
// Los factores e^{−2πik/N} se calculan una vez por tamaño con Math.cos y Math.sin (sin recurrencias que
// acumulen error) y se guardan en caché.

const TABLAS = new Map();   // N → { c, s } con cos(2πk/N) y sen(2πk/N) para k = 0…N/2

function esPotencia2(n) {
  return Number.isInteger(n) && n >= 1 && (n & (n - 1)) === 0;
}

/** Menor potencia de 2 que es ≥ m (m ≥ 1). */
export function siguientePotencia2(m) {
  let n = 1;
  while (n < m) n *= 2;
  return n;
}

function tablas(N) {
  let t = TABLAS.get(N);
  if (!t) {
    const h = N >> 1;
    const c = new Float64Array(h + 1), s = new Float64Array(h + 1);
    for (let k = 0; k <= h; k++) {
      const ang = (2 * Math.PI * k) / N;
      c[k] = Math.cos(ang);
      s[k] = Math.sin(ang);
    }
    t = { c, s };
    TABLAS.set(N, t);
  }
  return t;
}

/**
 * FFT compleja en el lugar sobre (re, im), de largo M (potencia de 2). `signo` = −1 directa, +1 inversa
 * (sin el factor 1/M). `tab` y `paso` permiten usar la tabla de un tamaño mayor N = M·paso.
 */
function fftCompleja(re, im, M, signo, tab, paso) {
  // permutación por inversión de bits
  for (let i = 1, j = 0; i < M; i++) {
    let bit = M >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      let x = re[i]; re[i] = re[j]; re[j] = x;
      x = im[i]; im[i] = im[j]; im[j] = x;
    }
  }
  const c = tab.c, s = tab.s;
  for (let tam = 2; tam <= M; tam <<= 1) {
    const mitad = tam >> 1;
    const zancada = (M / tam) * paso;   // e^{∓2πi·j/tam} = tabla[j·zancada]
    for (let ini = 0; ini < M; ini += tam) {
      for (let j = 0; j < mitad; j++) {
        const k = j * zancada;
        const wr = c[k], wi = signo * s[k];
        const a = ini + j, b = a + mitad;
        const tr = wr * re[b] - wi * im[b];
        const ti = wr * im[b] + wi * re[b];
        re[b] = re[a] - tr; im[b] = im[a] - ti;
        re[a] += tr; im[a] += ti;
      }
    }
  }
}

/** FFT compleja directa en el lugar (largo potencia de 2). */
export function fft(re, im) {
  const M = re.length;
  if (!esPotencia2(M) || im.length !== M) throw new Error(`fft: largo ${M} no es potencia de 2 o re/im difieren`);
  fftCompleja(re, im, M, -1, tablas(M), 1);
}

/** FFT compleja inversa en el lugar, con el factor 1/M. */
export function ifft(re, im) {
  const M = re.length;
  if (!esPotencia2(M) || im.length !== M) throw new Error(`ifft: largo ${M} no es potencia de 2 o re/im difieren`);
  fftCompleja(re, im, M, +1, tablas(M), 1);
  for (let i = 0; i < M; i++) { re[i] /= M; im[i] /= M; }
}

/**
 * FFT de una señal real. `x` puede ser más corta que N: se rellena con ceros (N potencia de 2, ≥ 2).
 * → { re, im } de largo N/2 + 1 (k = 0…N/2).
 */
export function rfft(x, N = siguientePotencia2(Math.max(2, x.length))) {
  if (!esPotencia2(N) || N < 2) throw new Error(`rfft: N = ${N} no es potencia de 2 ≥ 2`);
  if (x.length > N) throw new Error(`rfft: la señal (${x.length}) es más larga que N = ${N}`);
  const M = N >> 1;
  const zr = new Float64Array(M), zi = new Float64Array(M);
  const L = x.length;
  for (let m = 0; m < M; m++) {
    const i = 2 * m;
    zr[m] = i < L ? x[i] : 0;
    zi[m] = i + 1 < L ? x[i + 1] : 0;
  }
  const tab = tablas(N);
  fftCompleja(zr, zi, M, -1, tab, 2);
  // Separación: E_k = (Z_k + conj Z_{M−k})/2 (pares), O_k = (Z_k − conj Z_{M−k})/(2i) (impares),
  // X_k = E_k + e^{−2πik/N}·O_k, con Z_M ≡ Z_0.
  const re = new Float64Array(M + 1), im = new Float64Array(M + 1);
  for (let k = 0; k <= M; k++) {
    const a = k === M ? 0 : k, b = k === 0 ? 0 : M - k;
    const zkr = zr[a], zki = zi[a], zmr = zr[b], zmi = -zi[b];   // Z_k y conj(Z_{M−k})
    const er = 0.5 * (zkr + zmr), ei = 0.5 * (zki + zmi);
    // (Z_k − conj Z_{M−k})/(2i) = (dr + i·di)/(2i) = (di − i·dr)/2
    const dr = zkr - zmr, di = zki - zmi;
    const or = 0.5 * di, oi = -0.5 * dr;
    const wr = tab.c[k], wi = -tab.s[k];                        // e^{−2πik/N}
    re[k] = er + wr * or - wi * oi;
    im[k] = ei + wr * oi + wi * or;
  }
  return { re, im };
}

/**
 * Inversa de rfft: de los N/2 + 1 coeficientes (re, im) a la señal real de N puntos (con el factor 1/N).
 * Las partes imaginarias de k = 0 y k = N/2 se ignoran (como numpy.fft.irfft): en una señal real son cero.
 */
export function irfft(re, im, N) {
  const M = N >> 1;
  if (!esPotencia2(N) || N < 2 || re.length !== M + 1 || im.length !== M + 1) {
    throw new Error(`irfft: N = ${N} no es potencia de 2 o los coeficientes no son N/2 + 1`);
  }
  const tab = tablas(N);
  const zr = new Float64Array(M), zi = new Float64Array(M);
  // E_k = (X_k + conj X_{M−k})/2, O_k = (X_k − conj X_{M−k})·e^{+2πik/N}/2, Z_k = E_k + i·O_k
  for (let k = 0; k < M; k++) {
    const xkr = re[k], xki = k === 0 ? 0 : im[k];
    const xmr = re[M - k], xmi = M - k === M || M - k === 0 ? 0 : -im[M - k];   // conj X_{M−k}
    const er = 0.5 * (xkr + xmr), ei = 0.5 * (xki + xmi);
    const dr = 0.5 * (xkr - xmr), di = 0.5 * (xki - xmi);
    const wr = tab.c[k], wi = tab.s[k];                          // e^{+2πik/N}
    const or = dr * wr - di * wi, oi = dr * wi + di * wr;
    zr[k] = er - oi;   // E + i·O
    zi[k] = ei + or;
  }
  fftCompleja(zr, zi, M, +1, tab, 2);
  const x = new Float64Array(N);
  for (let m = 0; m < M; m++) {
    x[2 * m] = zr[m] / M;
    x[2 * m + 1] = zi[m] / M;
  }
  return x;
}
