// Álgebra lineal del motor sísmico (data/sismo/ESQUEMA.md, «Motor»; contrato de la torre, 7.4).
//
// Módulo puro: sin DOM ni dependencias. Matrices densas en Float64Array por filas (A[i·n + j]) y matrices en banda
// simétricas guardadas por filas: la fila i guarda las columnas j ∈ [i − w, i] en B[i·(w + 1) + (j − i + w)].
// Todo es determinista (mismo orden de operaciones en cualquier máquina con IEEE 754).

/** Factorización LU con pivoteo parcial, en el lugar. Devuelve la permutación (Int32Array) o null si es singular. */
export function factorLU(A, n, piv = new Int32Array(n)) {
  for (let i = 0; i < n; i++) piv[i] = i;
  for (let k = 0; k < n; k++) {
    let p = k, m = Math.abs(A[k * n + k]);
    for (let i = k + 1; i < n; i++) { const v = Math.abs(A[i * n + k]); if (v > m) { m = v; p = i; } }
    if (!(m > 0)) return null;
    if (p !== k) {
      for (let j = 0; j < n; j++) { const t = A[k * n + j]; A[k * n + j] = A[p * n + j]; A[p * n + j] = t; }
      const t = piv[k]; piv[k] = piv[p]; piv[p] = t;
    }
    const akk = A[k * n + k];
    for (let i = k + 1; i < n; i++) {
      const f = (A[i * n + k] /= akk);
      if (f !== 0) for (let j = k + 1; j < n; j++) A[i * n + j] -= f * A[k * n + j];
    }
  }
  return piv;
}

/** Resuelve A·x = b con la LU de factorLU; x puede ser b (en el lugar). `tmp` de largo n. */
export function resolverLU(LU, n, piv, b, x = b, tmp = new Float64Array(n)) {
  for (let i = 0; i < n; i++) tmp[i] = b[piv[i]];
  for (let i = 0; i < n; i++) {
    let s = tmp[i];
    for (let j = 0; j < i; j++) s -= LU[i * n + j] * tmp[j];
    tmp[i] = s;
  }
  for (let i = n - 1; i >= 0; i--) {
    let s = tmp[i];
    for (let j = i + 1; j < n; j++) s -= LU[i * n + j] * tmp[j];
    tmp[i] = s / LU[i * n + i];
  }
  for (let i = 0; i < n; i++) x[i] = tmp[i];
  return x;
}

/** Inversa de una matriz densa pequeña (copia). Lanza si es singular. */
export function inversa(A, n) {
  const LU = Float64Array.from(A);
  const piv = factorLU(LU, n);
  if (!piv) throw new Error('matriz singular');
  const inv = new Float64Array(n * n), e = new Float64Array(n), tmp = new Float64Array(n);
  for (let j = 0; j < n; j++) {
    e.fill(0); e[j] = 1;
    resolverLU(LU, n, piv, e, e, tmp);
    for (let i = 0; i < n; i++) inv[i * n + j] = e[i];
  }
  return inv;
}

/**
 * Cholesky en banda, en el lugar (A = L·Lᵀ; queda L en la misma banda). Costo n·w². Devuelve false si A no es
 * definida positiva (pivote ≤ 0).
 */
export function choleskyBanda(B, n, w) {
  const s = w + 1;
  for (let i = 0; i < n; i++) {
    const j0 = i - w > 0 ? i - w : 0;
    for (let j = j0; j <= i; j++) {
      // suma de L[i,k]·L[j,k] para k ∈ [max(i−w, j−w, 0), j)
      let sum = B[i * s + (j - i + w)];
      const k0 = j - w > j0 ? j - w : j0;
      const bi = i * s - i + w, bj = j * s - j + w;
      for (let k = k0; k < j; k++) sum -= B[bi + k] * B[bj + k];
      if (j === i) {
        if (!(sum > 0)) return false;
        B[i * s + w] = Math.sqrt(sum);
      } else {
        B[i * s + (j - i + w)] = sum / B[j * s + w];
      }
    }
  }
  return true;
}

/** Resuelve (L·Lᵀ)·x = b con la L de choleskyBanda; en el lugar sobre x (x = b de entrada). */
export function resolverBanda(B, n, w, x) {
  const s = w + 1;
  for (let i = 0; i < n; i++) {           // L·y = b
    let sum = x[i];
    const k0 = i - w > 0 ? i - w : 0;
    const bi = i * s - i + w;
    for (let k = k0; k < i; k++) sum -= B[bi + k] * x[k];
    x[i] = sum / B[i * s + w];
  }
  for (let i = n - 1; i >= 0; i--) {      // Lᵀ·x = y
    let sum = x[i];
    const k1 = i + w < n - 1 ? i + w : n - 1;
    for (let k = i + 1; k <= k1; k++) sum -= B[k * s + (i - k + w)] * x[k];
    x[i] = sum / B[i * s + w];
  }
  return x;
}

/**
 * Valores y vectores propios de una matriz simétrica (método de Jacobi cíclico; Golub y Van Loan, 2013, §8.5).
 * Devuelve { valores: Float64Array(n), vectores: Float64Array(n·n) } con los vectores en columnas (V[i·n + r]),
 * sin ordenar. Para las matrices de 3N × 3N del diafragma (N niveles) es exacto a la precisión de la máquina.
 */
export function jacobiSimetrico(Aent, n, { tolerancia = 1e-15, maxBarridos = 100 } = {}) {
  const A = Float64Array.from(Aent);
  const V = new Float64Array(n * n);
  for (let i = 0; i < n; i++) V[i * n + i] = 1;
  let escala = 0;
  for (let i = 0; i < n * n; i++) escala = Math.max(escala, Math.abs(A[i]));
  for (let barrido = 0; barrido < maxBarridos; barrido++) {
    let fuera = 0;
    for (let p = 0; p < n; p++) for (let q = p + 1; q < n; q++) fuera = Math.max(fuera, Math.abs(A[p * n + q]));
    if (fuera <= tolerancia * escala) break;
    for (let p = 0; p < n; p++) {
      for (let q = p + 1; q < n; q++) {
        const apq = A[p * n + q];
        if (apq === 0) continue;
        const app = A[p * n + p], aqq = A[q * n + q];
        // rotación que anula A[p,q]: t = tan φ con la raíz menor (estabilidad)
        const tau = (aqq - app) / (2 * apq);
        const t = Math.sign(tau || 1) / (Math.abs(tau) + Math.sqrt(1 + tau * tau));
        const c = 1 / Math.sqrt(1 + t * t), s = t * c;
        for (let k = 0; k < n; k++) {
          const akp = A[k * n + p], akq = A[k * n + q];
          A[k * n + p] = c * akp - s * akq;
          A[k * n + q] = s * akp + c * akq;
        }
        for (let k = 0; k < n; k++) {
          const apk = A[p * n + k], aqk = A[q * n + k];
          A[p * n + k] = c * apk - s * aqk;
          A[q * n + k] = s * apk + c * aqk;
        }
        A[p * n + q] = A[q * n + p] = 0;
        for (let k = 0; k < n; k++) {
          const vkp = V[k * n + p], vkq = V[k * n + q];
          V[k * n + p] = c * vkp - s * vkq;
          V[k * n + q] = s * vkp + c * vkq;
        }
      }
    }
  }
  const valores = new Float64Array(n);
  for (let i = 0; i < n; i++) valores[i] = A[i * n + i];
  return { valores, vectores: V };
}

/** max |x_i| */
export function normaInf(x, n = x.length) {
  let m = 0;
  for (let i = 0; i < n; i++) { const a = Math.abs(x[i]); if (a > m) m = a; }
  return m;
}
