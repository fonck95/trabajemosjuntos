// Trabajador simulado del motor sísmico (equipo A, ola 0 del contrato de integración de la torre).
//
// Responde los mensajes del 7.5 (data/sismo/ESQUEMA.md, «Mensajes del trabajador») con los fixtures del Anexo A:
// `listo` con el modelo de estructura_min.json, `movimiento` con el registro de prueba, `resultado` con
// resultado_min.json y `serie_elemento` con serie_elemento_min.json (C-A1-1@X) o con la serie del elemento pedido.
// Sirve para que la vista sísmica (web/js/scenes/torre/sismo.js) se desarrolle y se pruebe sin calcular. No calcula
// nada: todos los números los calculó el motor real (web/js/sismo/) con scripts/sismo/fixtures_min.mjs, que también
// escribe el bloque GENERADO de abajo.
//
// Uso desde la vista (sirviendo la raíz del repositorio, para que exista scripts/fixtures/torre/):
//   const w = new Worker(new URL('../../../../scripts/fixtures/torre/trabajador_simulado.js', import.meta.url), { type: 'module' });
//   w.postMessage({ tipo: 'iniciar', v: 1, id, url_estructura, url_amenaza, opciones });
// Las URL de `iniciar` se aceptan y se ignoran (siempre responde con el cubo de prueba). Campos propios del simulador:
//   iniciar.url_fixtures   URL absoluta de la carpeta con los fixtures, si no están junto a este archivo.
//   *.simular              { retardo_ms: 600, error: 'datos' | 'no_converge' | 'interno' } para probar estados de la vista.
// Mismos tipos que el motor: series en Float32Array, D/C y rótulas en Uint8Array, thp en Int32Array/Int16Array;
// los búferes de `resultado`, `movimiento` y `serie_elemento` se transfieren.

/* >>> generado por scripts/sismo/fixtures_min.mjs (no editar a mano) */
const GENERADO = {
  "listo": {
    "tipo": "listo",
    "id": "prueba",
    "resumen": {
      "niveles": 2,
      "porticos": 4,
      "nodos": 24,
      "elementos": 24,
      "gdl_dinamicos": 6,
      "gdl_condensados": 32,
      "masa_total_t": 40,
      "peso_kN": 392.26,
      "cm": [2.5, 2.5],
      "centro_rigidez": [
        [2.5, 0.3689106],
        [2.5, 1.415239]
      ],
      "excentricidad": [
        [0, -2.131089],
        [0, -1.084761]
      ],
      "sistema": "pórticos de concreto (prueba)",
      "sistema_detalle": null,
      "muros_mamposteria": 1,
      "p_delta": true,
      "histeresis": "la de cada sección",
      "no_estructurales": "aislados"
    },
    "elementos": [
      { "id": "C-A1-1@X", "tipo": "columna", "portico": "X-1", "nivel": 1, "fisico": "C-A1-1", "i": "X-1/A0", "j": "X-1/A1", "xyz_i": [0, 0, 0], "xyz_j": [0, 0, 3], "seccion": "C40" },
      { "id": "C-B1-1@X", "tipo": "columna", "portico": "X-1", "nivel": 1, "fisico": "C-B1-1", "i": "X-1/B0", "j": "X-1/B1", "xyz_i": [5, 0, 0], "xyz_j": [5, 0, 3], "seccion": "C40" },
      { "id": "C-A1-2@X", "tipo": "columna", "portico": "X-1", "nivel": 2, "fisico": "C-A1-2", "i": "X-1/A1", "j": "X-1/A2", "xyz_i": [0, 0, 3], "xyz_j": [0, 0, 6], "seccion": "C40" },
      { "id": "C-B1-2@X", "tipo": "columna", "portico": "X-1", "nivel": 2, "fisico": "C-B1-2", "i": "X-1/B1", "j": "X-1/B2", "xyz_i": [5, 0, 3], "xyz_j": [5, 0, 6], "seccion": "C40" },
      { "id": "VX-1-AB-1", "tipo": "viga", "portico": "X-1", "nivel": 1, "fisico": "VX-1-AB-1", "i": "X-1/A1", "j": "X-1/B1", "xyz_i": [0, 0, 3], "xyz_j": [5, 0, 3], "seccion": "V30x50" },
      { "id": "VX-1-AB-2", "tipo": "viga", "portico": "X-1", "nivel": 2, "fisico": "VX-1-AB-2", "i": "X-1/A2", "j": "X-1/B2", "xyz_i": [0, 0, 6], "xyz_j": [5, 0, 6], "seccion": "V30x50" },
      { "id": "C-A2-1@X", "tipo": "columna", "portico": "X-2", "nivel": 1, "fisico": "C-A2-1", "i": "X-2/A0", "j": "X-2/A1", "xyz_i": [0, 5, 0], "xyz_j": [0, 5, 3], "seccion": "C40" },
      { "id": "C-B2-1@X", "tipo": "columna", "portico": "X-2", "nivel": 1, "fisico": "C-B2-1", "i": "X-2/B0", "j": "X-2/B1", "xyz_i": [5, 5, 0], "xyz_j": [5, 5, 3], "seccion": "C40" },
      { "id": "C-A2-2@X", "tipo": "columna", "portico": "X-2", "nivel": 2, "fisico": "C-A2-2", "i": "X-2/A1", "j": "X-2/A2", "xyz_i": [0, 5, 3], "xyz_j": [0, 5, 6], "seccion": "C40" },
      { "id": "C-B2-2@X", "tipo": "columna", "portico": "X-2", "nivel": 2, "fisico": "C-B2-2", "i": "X-2/B1", "j": "X-2/B2", "xyz_i": [5, 5, 3], "xyz_j": [5, 5, 6], "seccion": "C40" },
      { "id": "VX-2-AB-1", "tipo": "viga", "portico": "X-2", "nivel": 1, "fisico": "VX-2-AB-1", "i": "X-2/A1", "j": "X-2/B1", "xyz_i": [0, 5, 3], "xyz_j": [5, 5, 3], "seccion": "V30x50" },
      { "id": "VX-2-AB-2", "tipo": "viga", "portico": "X-2", "nivel": 2, "fisico": "VX-2-AB-2", "i": "X-2/A2", "j": "X-2/B2", "xyz_i": [0, 5, 6], "xyz_j": [5, 5, 6], "seccion": "V30x50" },
      { "id": "C-A1-1@Y", "tipo": "columna", "portico": "Y-A", "nivel": 1, "fisico": "C-A1-1", "i": "Y-A/10", "j": "Y-A/11", "xyz_i": [0, 0, 0], "xyz_j": [0, 0, 3], "seccion": "C40" },
      { "id": "C-A2-1@Y", "tipo": "columna", "portico": "Y-A", "nivel": 1, "fisico": "C-A2-1", "i": "Y-A/20", "j": "Y-A/21", "xyz_i": [0, 5, 0], "xyz_j": [0, 5, 3], "seccion": "C40" },
      { "id": "C-A1-2@Y", "tipo": "columna", "portico": "Y-A", "nivel": 2, "fisico": "C-A1-2", "i": "Y-A/11", "j": "Y-A/12", "xyz_i": [0, 0, 3], "xyz_j": [0, 0, 6], "seccion": "C40" },
      { "id": "C-A2-2@Y", "tipo": "columna", "portico": "Y-A", "nivel": 2, "fisico": "C-A2-2", "i": "Y-A/21", "j": "Y-A/22", "xyz_i": [0, 5, 3], "xyz_j": [0, 5, 6], "seccion": "C40" },
      { "id": "VY-A-12-1", "tipo": "viga", "portico": "Y-A", "nivel": 1, "fisico": "VY-A-12-1", "i": "Y-A/11", "j": "Y-A/21", "xyz_i": [0, 0, 3], "xyz_j": [0, 5, 3], "seccion": "V30x50" },
      { "id": "VY-A-12-2", "tipo": "viga", "portico": "Y-A", "nivel": 2, "fisico": "VY-A-12-2", "i": "Y-A/12", "j": "Y-A/22", "xyz_i": [0, 0, 6], "xyz_j": [0, 5, 6], "seccion": "V30x50" },
      { "id": "C-B1-1@Y", "tipo": "columna", "portico": "Y-B", "nivel": 1, "fisico": "C-B1-1", "i": "Y-B/10", "j": "Y-B/11", "xyz_i": [5, 0, 0], "xyz_j": [5, 0, 3], "seccion": "C40" },
      { "id": "C-B2-1@Y", "tipo": "columna", "portico": "Y-B", "nivel": 1, "fisico": "C-B2-1", "i": "Y-B/20", "j": "Y-B/21", "xyz_i": [5, 5, 0], "xyz_j": [5, 5, 3], "seccion": "C40" },
      { "id": "C-B1-2@Y", "tipo": "columna", "portico": "Y-B", "nivel": 2, "fisico": "C-B1-2", "i": "Y-B/11", "j": "Y-B/12", "xyz_i": [5, 0, 3], "xyz_j": [5, 0, 6], "seccion": "C40" },
      { "id": "C-B2-2@Y", "tipo": "columna", "portico": "Y-B", "nivel": 2, "fisico": "C-B2-2", "i": "Y-B/21", "j": "Y-B/22", "xyz_i": [5, 5, 3], "xyz_j": [5, 5, 6], "seccion": "C40" },
      { "id": "VY-B-12-1", "tipo": "viga", "portico": "Y-B", "nivel": 1, "fisico": "VY-B-12-1", "i": "Y-B/11", "j": "Y-B/21", "xyz_i": [5, 0, 3], "xyz_j": [5, 5, 3], "seccion": "V30x50" },
      { "id": "VY-B-12-2", "tipo": "viga", "portico": "Y-B", "nivel": 2, "fisico": "VY-B-12-2", "i": "Y-B/12", "j": "Y-B/22", "xyz_i": [5, 0, 6], "xyz_j": [5, 5, 6], "seccion": "V30x50" }
    ],
    "nodos": [
      { "id": "X-1/A0", "portico": "X-1", "xyz": [0, 0, 0] },
      { "id": "X-1/B0", "portico": "X-1", "xyz": [5, 0, 0] },
      { "id": "X-1/A1", "portico": "X-1", "xyz": [0, 0, 3] },
      { "id": "X-1/B1", "portico": "X-1", "xyz": [5, 0, 3] },
      { "id": "X-1/A2", "portico": "X-1", "xyz": [0, 0, 6] },
      { "id": "X-1/B2", "portico": "X-1", "xyz": [5, 0, 6] },
      { "id": "X-2/A0", "portico": "X-2", "xyz": [0, 5, 0] },
      { "id": "X-2/B0", "portico": "X-2", "xyz": [5, 5, 0] },
      { "id": "X-2/A1", "portico": "X-2", "xyz": [0, 5, 3] },
      { "id": "X-2/B1", "portico": "X-2", "xyz": [5, 5, 3] },
      { "id": "X-2/A2", "portico": "X-2", "xyz": [0, 5, 6] },
      { "id": "X-2/B2", "portico": "X-2", "xyz": [5, 5, 6] },
      { "id": "Y-A/10", "portico": "Y-A", "xyz": [0, 0, 0] },
      { "id": "Y-A/20", "portico": "Y-A", "xyz": [0, 5, 0] },
      { "id": "Y-A/11", "portico": "Y-A", "xyz": [0, 0, 3] },
      { "id": "Y-A/21", "portico": "Y-A", "xyz": [0, 5, 3] },
      { "id": "Y-A/12", "portico": "Y-A", "xyz": [0, 0, 6] },
      { "id": "Y-A/22", "portico": "Y-A", "xyz": [0, 5, 6] },
      { "id": "Y-B/10", "portico": "Y-B", "xyz": [5, 0, 0] },
      { "id": "Y-B/20", "portico": "Y-B", "xyz": [5, 5, 0] },
      { "id": "Y-B/11", "portico": "Y-B", "xyz": [5, 0, 3] },
      { "id": "Y-B/21", "portico": "Y-B", "xyz": [5, 5, 3] },
      { "id": "Y-B/12", "portico": "Y-B", "xyz": [5, 0, 6] },
      { "id": "Y-B/22", "portico": "Y-B", "xyz": [5, 5, 6] }
    ],
    "modos": {
      "periodos_s": [0.2854418, 0.2310557, 0.1303484, 0.08132378, 0.06233579, 0.03067519],
      "masa_participativa": { "x": [0, 0.6728899, 0.0332628, 0, 0.1849372, 0.10891], "y": [0.8775487, 0, 0, 0.1224513, 0, 0], "rz": [0, 0.1476333, 0.5951177, 0, 0.0002800539, 0.256969] },
      "formas": [
        [0, 0.09278839, 0, 0, 0.2034461, 0],
        [0.06479686, 0, -0.02164733, 0.1946044, 0, -0.03787864],
        [-0.04386276, 0, 0.0287518, 0.1015367, 0, 0.09076136],
        [0, 0.2034461, 0, 0, -0.09278839, 0],
        [0.1782748, 0, -0.04308867, -0.04228319, 0, 0.04568126],
        [0.1099796, 0, 0.09406686, -0.005619648, 0, -0.01553341]
      ],
      "T1x": 0.2310557,
      "T1y": 0.2854418
    },
    "amortiguamiento": {
      "a0": 1.543556,
      "a1": 0.001351924,
      "periodos_ancla_s": [0.2854418, 0.03067519],
      "xi_modos": [0.05, 0.046146747, 0.046055112, 0.062312473, 0.06802728, 0.05],
      "regla": "E8: Ti = T1; Tj = mín(T del modo 6, con ≥ 90 % de masa en x y en y; 0,2·T1)"
    },
    "escala_nsr10": { "T1x": 0.23105565989618188, "T1y": 0.28544181676459923, "modelo": "el analizado" },
    "gravedad": { "iteraciones": 10 },
    "avisos": []
  },
  "movimiento": {
    "tipo": "movimiento",
    "id": "prueba",
    "registro": {
      "dt": 0.005,
      "n": 9,
      "ax": [0, 25, 25, 25, 25, 25, 25, 25, 25],
      "ay": [0, -12.5, -12.5, -12.5, -12.5, -12.5, -12.5, -12.5, -12.5],
      "meta": {
        "M0_dina_cm": 2.238721e+25,
        "M0_N_m": 2238721000000000000,
        "energia_J_aprox": 111936100000000,
        "f0_Hz": 0.7271713,
        "delta_sigma_bar": 800,
        "beta_s_km_s": 4.5,
        "rho_s_g_cm3": 3.35,
        "Q0": 251,
        "eta": 0.58,
        "kappa0_s": 0.035,
        "Rhip_km": 175.9659,
        "Ref_km": 175.9659,
        "Tgm_s": 10.17349,
        "t_eta_s": 20.34697,
        "regimen": "intraplaca_profunda",
        "w_transicion": 1,
        "regimen_pedido": "auto",
        "pga_roca_g": 0.01259573,
        "pga_roca_x_g": 0.01583513,
        "pga_roca_y_g": 0.01001902,
        "escala_pgar": 1,
        "vs30_m_s": 270,
        "semillas": [2028, 2029],
        "terminos": [
          {
            "regimen": "intraplaca_profunda",
            "peso": 1,
            "f0_Hz": 0.727171283525305,
            "delta_sigma_bar": 800,
            "beta_s_km_s": 4.5,
            "rho_s_g_cm3": 3.35,
            "Q0": 251,
            "eta": 0.58,
            "beta_Q_km_s": 3.5,
            "kappa0_s": 0.035,
            "Ref_km": 175.96590578859303,
            "Z": 0.005682919060476458,
            "Tcamino_s": 8.798295289429651,
            "Tgm_s": 10.173487108270502,
            "Fimp": 1.2402682395846671
          }
        ],
        "t_inicio_ventana_s": 1.095,
        "n_fft": 16384,
        "duracion_s": 22.535,
        "fraccion_energia_fuera": 1.578719e-7,
        "nota_mezcla": undefined
      },
      "intensidades": {
        "x": { "pga_g": 2.54929, "pgv_cm_s": 93.75, "pgd_cm": 1.76563, "arias_m_s": 3.75414, "d595_s": 0.034375, "t5_s": 0.00375, "t95_s": 0.038125 },
        "y": { "pga_g": 1.27465, "pgv_cm_s": 46.875, "pgd_cm": 0.882813, "arias_m_s": 0.938535, "d595_s": 0.034375, "t5_s": 0.00375, "t95_s": 0.038125 }
      },
      "avisos": ["Trabajador simulado: el registro es el pulso de prueba del fixture (escala ×25), no la síntesis de estos parámetros.", "Espectro de umbral de daño de A.12.3 con ξ = 2 % (el del prediseño; forma por confirmar)."]
    },
    "espectro": {
      "T": [0.02, 0.021962058, 0.024116602, 0.02648251, 0.029080521, 0.03193341, 0.03506617, 0.038506262, 0.042283837, 0.046432007, 0.050987124, 0.05598911, 0.061481804, 0.06751335, 0.07413661, 0.081409626, 0.08939615, 0.098166175, 0.107796565, 0.118371725, 0.12998433, 0.14273618, 0.15673901, 0.17211558, 0.18900062, 0.20754214, 0.22790262, 0.25026053, 0.27481183, 0.30177167, 0.33137637, 0.36388534, 0.39958358, 0.43878388, 0.48182988, 0.5290988, 0.581005, 0.63800323, 0.70059323, 0.76932347, 0.84479636, 0.92767334, 1.0186808, 1.1186165, 1.228356, 1.3488613, 1.4811885, 1.6264975, 1.7860616, 1.9612795, 2.1536868, 2.3649697, 2.5969803, 2.8517516, 3.131517, 3.4387279, 3.776077, 4.146521, 4.553307, 5],
      "Sa_x": [3.9700747, 4.373954, 4.5659266, 4.566539, 4.413874, 4.552132, 4.6552753, 4.576621, 4.637518, 4.6749578, 4.631448, 4.6951404, 4.671334, 4.691922, 4.710217, 4.6451883, 4.63723, 4.478977, 4.3212323, 4.0992656, 3.8776143, 3.6151376, 3.3878922, 3.1463182, 2.908294, 2.681753, 2.4692051, 2.2705305, 2.084582, 1.9100264, 1.7471064, 1.5987736, 1.4610875, 1.3342819, 1.2180754, 1.1114339, 1.0136863, 0.92430615, 0.84268457, 0.7682594, 0.7000875, 0.6379612, 0.58134556, 0.52962977, 0.4825035, 0.43952897, 0.40035608, 0.3646641, 0.33214968, 0.30251208, 0.27552512, 0.25093475, 0.22853324, 0.20813166, 0.18954824, 0.17262278, 0.15720592, 0.14316615, 0.1303801, 0.118734784],
      "Sa_y": [1.9850373, 2.186977, 2.2829633, 2.2832694, 2.206937, 2.276066, 2.3276377, 2.2883105, 2.318759, 2.3374789, 2.315724, 2.3475702, 2.335667, 2.345961, 2.3551085, 2.3225942, 2.318615, 2.2394886, 2.1606162, 2.0496328, 1.9388071, 1.8075688, 1.6939461, 1.5731591, 1.454147, 1.3408765, 1.2346026, 1.1352652, 1.042291, 0.9550132, 0.8735532, 0.7993868, 0.73054373, 0.66714096, 0.6090377, 0.55571693, 0.50684315, 0.46215308, 0.42134228, 0.3841297, 0.35004374, 0.3189806, 0.29067278, 0.26481488, 0.24125175, 0.21976449, 0.20017804, 0.18233205, 0.16607484, 0.15125604, 0.13776256, 0.12546737, 0.11426662, 0.10406583, 0.09477412, 0.08631139, 0.07860296, 0.07158308, 0.06519005, 0.059367392]
    },
    "fourier": { "f": [12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100], "A_x": [0.6407289, 0, 0.22499405, 0, 0.15033622, 0, 0.1274489, 0], "A_y": [0.32036445, 0, 0.112497024, 0, 0.07516811, 0, 0.06372445, 0] },
    "gmpe": [
      { "nombre": "BC Hydro 2016 (intraplaca)", "modelo": "bchydro2016_intraslab", "regimen": "intraplaca_profunda", "peso": 0.5, "T": [0, 0.2, 0.5, 1], "mediana_g": [0.038078, 0.086072, 0.051208, 0.022228], "sigma_ln": [0.74, 0.74, 0.74, 0.74] },
      {
        "nombre": "Zhao et al. 2006 (intraplaca)",
        "modelo": "zhao2006_intraslab",
        "regimen": "intraplaca_profunda",
        "peso": 0.5,
        "T": [0, 0.2, 0.5, 1],
        "mediana_g": [0.028873, 0.070474, 0.048352, 0.016864],
        "sigma_ln": [0.684, 0.7641, 0.7074, 0.7166]
      }
    ],
    "nsr10": {
      "T": [0.02, 0.021962058, 0.024116602, 0.02648251, 0.029080521, 0.03193341, 0.03506617, 0.038506262, 0.042283837, 0.046432007, 0.050987124, 0.05598911, 0.061481804, 0.06751335, 0.07413661, 0.081409626, 0.08939615, 0.098166175, 0.107796565, 0.118371725, 0.12998433, 0.14273618, 0.15673901, 0.17211558, 0.18900062, 0.20754214, 0.22790262, 0.25026053, 0.27481183, 0.30177167, 0.33137637, 0.36388534, 0.39958358, 0.43878388, 0.48182988, 0.5290988, 0.581005, 0.63800323, 0.70059323, 0.76932347, 0.84479636, 0.92767334, 1.0186808, 1.1186165, 1.228356, 1.3488613, 1.4811885, 1.6264975, 1.7860616, 1.9612795, 2.1536868, 2.3649697, 2.5969803, 2.8517516, 3.131517, 3.4387279, 3.776077, 4.146521, 4.553307, 5],
      "con_I": [0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.84375, 0.77210695, 0.70312804, 0.6403116, 0.58310705, 0.53101313, 0.48357317, 0.44037145, 0.4010293, 0.36520192, 0.33257532, 0.3028635, 0.27580613, 0.251166, 0.22872719, 0.20829304, 0.18968444, 0.1727383, 0.1573061, 0.14325261, 0.13045463, 0.1188],
      "sin_I": [0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.5625, 0.51473796, 0.46875203, 0.4268744, 0.38873804, 0.35400876, 0.32238212, 0.29358098, 0.26735288, 0.24346794, 0.22171687, 0.201909, 0.18387075, 0.167444, 0.15248479, 0.13886203, 0.12645629, 0.11515887, 0.104870744, 0.09550174, 0.086969756, 0.0792],
      "umbral_dano": [0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.17157932, 0.15625067, 0.14229146, 0.12957935, 0.118002914, 0.10746071, 0.09786032, 0.089117624, 0.081155986, 0.073905624, 0.067303, 0.06129025, 0.055814665, 0.050828263, 0.04628734, 0.042152096, 0.03838629, 0.034956913, 0.031833913, 0.028989917, 0.0264],
      "xi": 0.05,
      "xi_umbral_dano": 0.02
    }
  },
  "series": {
    "C-A1-1@X": {
      "Mi": [-1.9418145, -52.84981, -150.61464],
      "Mj": [-3.9899268, -37.03936, -96.116936],
      "V": [-1.9772471, -29.963057, -82.24386],
      "N": [-30, -45.468384, -96.2176],
      "thp_i": [0, 0, -0.00027582917],
      "thp_j": [0, 0, 0],
      "dc": [0.024181375, 0.3203019, 0.912816]
    },
    "C-B1-1@X": {
      "Mi": [1.9418145, -48.966183, -150.48734],
      "Mj": [3.9899268, -29.059505, -89.19787],
      "V": [1.9772471, -26.008562, -79.895065],
      "N": [-30, -14.531615, 36.217598],
      "thp_i": [0, 0, -0.0002186992],
      "thp_j": [0, 0, 0],
      "dc": [0.024181375, 0.29676473, 0.9120444]
    },
    "C-A1-2@X": {
      "Mi": [-8.491743, -5.129172, -28.061262],
      "Mj": [-11.191884, -20.175983, -64.96426],
      "V": [-6.561209, -8.435052, -31.008507],
      "N": [-15, -18.59364, -36.489677],
      "thp_i": [0, 0, 0],
      "thp_j": [0, 0, 0],
      "dc": [0.0678296, 0.12227869, 0.39372277]
    },
    "C-B1-2@X": { "Mi": [8.491743, 11.854315, -10.263539], "Mj": [11.191884, 2.207783, -42.484127], "V": [6.561209, 4.687366, -17.582556], "N": [-15, -11.40636, 6.489677], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.0678296, 0.07184433, 0.25747955] },
    "VX-1-AB-1": { "Mi": [9.60167, 36.91358, 112.352615], "Mj": [-9.60167, 17.710241, 93.39583], "V": [-13.8, 25.674744, 58.527924], "N": [0, 0, 0], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.050535105, 0.19428201, 0.5913296] },
    "VX-1-AB-2": { "Mi": [8.311884, 16.577257, 57.786324], "Mj": [-8.311884, -0.046510972, 41.066193], "V": [-13.8, 17.39364, 35.289677], "N": [0, 0, 0], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.046, 0.08724872, 0.30413854] },
    "C-A2-1@X": {
      "Mi": [-1.9418145, -78.68059, -153.07086],
      "Mj": [-3.9899268, -60.60028, -119.99984],
      "V": [-1.9772471, -46.426956, -91.02357],
      "N": [-30, -42.644196, -99.54274],
      "thp_i": [0, 0, -0.0013781063],
      "thp_j": [0, 0, 0],
      "dc": [0.024181375, 0.47685203, 0.9277022]
    },
    "C-B2-1@X": {
      "Mi": [1.9418145, -74.79695, -152.85712],
      "Mj": [3.9899268, -52.62043, -113.056366],
      "V": [1.9772471, -42.47246, -88.637825],
      "N": [-30, -17.355806, 39.542736],
      "thp_i": [0, 0, -0.0012821887],
      "thp_j": [0, 0, 0],
      "dc": [0.024181375, 0.45331487, 0.9264068]
    },
    "C-A2-2@X": {
      "Mi": [-8.491743, 14.598664, -15.804978],
      "Mj": [-11.191884, -9.28242, -61.652214],
      "V": [-6.561209, 1.7720814, -25.819063],
      "N": [-15, -14.236215, -35.165302],
      "thp_i": [0, 0, 0],
      "thp_j": [0, 0, 0],
      "dc": [0.0678296, 0.088476755, 0.37364978]
    },
    "C-B2-2@X": { "Mi": [8.491743, 31.582151, 1.9740106], "Mj": [11.191884, 13.101347, -39.1743], "V": [6.561209, 14.8945, -12.400097], "N": [-15, -15.763785, 5.1653028], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.0678296, 0.19140698, 0.23742001] },
    "VX-2-AB-1": { "Mi": [9.60167, 40.44002, 123.04933], "Mj": [-9.60167, 21.236681, 104.08687], "V": [-13.8, 27.20798, 63.177433], "N": [0, 0, 0], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.050535105, 0.21284223, 0.64762807] },
    "VX-2-AB-2": { "Mi": [8.311884, 6.5551777, 54.73915], "Mj": [-8.311884, -10.06859, 38.02124], "V": [-13.8, -14.563786, 33.9653], "N": [0, 0, 0], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.046, 0.05299258, 0.2881008] },
    "C-A1-1@Y": {
      "Mi": [-1.9418145, 22.94612, 88.035835],
      "Mj": [-3.9899268, 12.16527, 52.463856],
      "V": [-1.9772471, 11.703796, 46.83323],
      "N": [-30, -22.434614, 0.4192236],
      "thp_i": [0, 0, 0],
      "thp_j": [0, 0, 0],
      "dc": [0.024181375, 0.13906738, 0.5335505]
    },
    "C-A2-1@Y": {
      "Mi": [1.9418145, 26.829748, 91.919464],
      "Mj": [3.9899268, 20.145123, 60.443707],
      "V": [1.9772471, 15.65829, 50.787724],
      "N": [-30, -37.565384, -60.419224],
      "thp_i": [0, 0, 0],
      "thp_j": [0, 0, 0],
      "dc": [0.024181375, 0.16260453, 0.55708766]
    },
    "C-A1-2@Y": {
      "Mi": [-8.491743, -10.130251, -9.234997],
      "Mj": [-11.191884, -6.7951107, 9.145648],
      "V": [-6.561209, -5.641787, -0.029782966],
      "N": [-15, -13.241291, -6.8649874],
      "thp_i": [0, 0, 0],
      "thp_j": [0, 0, 0],
      "dc": [0.0678296, 0.06139546, 0.055969674]
    },
    "C-A2-2@Y": { "Mi": [8.491743, 6.853236, 7.7484903], "Mj": [11.191884, 15.588656, 31.529415], "V": [6.561209, 7.480631, 13.092635], "N": [-15, -16.758709, -23.135012], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.0678296, 0.09447671, 0.19108737] },
    "VY-A-12-1": { "Mi": [9.60167, -3.7536838, -41.652016], "Mj": [-9.60167, -22.957024, -60.855354], "V": [-13.8, -19.606676, -36.08421], "N": [0, 0, 0], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.050535105, 0.120826446, 0.32029134] },
    "VY-A-12-2": { "Mi": [8.311884, 4.2668524, -10.398645], "Mj": [-8.311884, -12.3569145, -27.022413], "V": [13.8, -15.558709, -21.935013], "N": [0, 0, 0], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.046, 0.06503639, 0.14222322] },
    "C-B1-1@Y": { "Mi": [-1.9418145, 48.77689, 141.0256], "Mj": [-3.9899268, 35.726192, 93.41119], "V": [-1.9772471, 28.167694, 78.1456], "N": [-30, -25.258806, 6.232597], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.024181375, 0.29561752, 0.8547006] },
    "C-B2-1@Y": { "Mi": [1.9418145, 52.66052, 144.90923], "Mj": [3.9899268, 43.706047, 101.391045], "V": [1.9772471, 32.12219, 82.10009], "N": [-30, -34.741196, -66.2326], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.024181375, 0.31915468, 0.8782378] },
    "C-B1-2@Y": {
      "Mi": [-8.491743, -29.858088, -30.106123],
      "Mj": [-11.191884, -17.688675, 3.6028748],
      "V": [-6.561209, -15.848921, -8.834416],
      "N": [-15, -17.598717, -9.082097],
      "thp_i": [0, 0, 0],
      "thp_j": [0, 0, 0],
      "dc": [0.0678296, 0.1809581, 0.18246135]
    },
    "C-B2-2@Y": { "Mi": [8.491743, -12.8746, -13.122637], "Mj": [11.191884, 4.695093, 25.986643], "V": [6.561209, -2.7265024, 4.2880015], "N": [-15, -12.401283, -20.917904], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.0678296, 0.07802788, 0.1574948] },
    "VY-B-12-1": { "Mi": [9.60167, -7.280123, -60.122124], "Mj": [-9.60167, -26.483463, -79.32546], "V": [-13.8, -21.13991, -44.114693], "N": [0, 0, 0], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.050535105, 0.13938665, 0.41750243] },
    "VY-B-12-2": { "Mi": [8.311884, 14.288931, -5.299294], "Mj": [-8.311884, -2.3348362, -21.923061], "V": [-13.8, 16.398716, -19.717903], "N": [0, 0, 0], "thp_i": [0, 0, 0], "thp_j": [0, 0, 0], "dc": [0.046, 0.0752049, 0.115384534] }
  }
};
/* <<< generado */

// Tipos de cada arreglo de Resultados (7.6). Lo que no está aquí viaja como objeto o número.
const TIPOS = {
  t: Float32Array, ag: Float32Array, u: Float32Array, a_abs: Float32Array, giros: Float32Array, v_nodos: Float32Array,
  dc: Uint8Array, dc_flexion: Uint8Array, dc_cortante: Uint8Array, dc_rotacion: Uint8Array, rotulas: Uint8Array,
  derivas: Float32Array, derivas_vector: Float32Array, derivas_porticos_env: Float32Array, cortante_basal: Float32Array,
  energia: Float32Array,
};

let base = new URL('./', import.meta.url);
let iniciado = false;
const cache = new Map();

async function leer(nombre) {
  if (!cache.has(nombre)) {
    const r = await fetch(new URL(nombre, base));
    if (!r.ok) throw Object.assign(new Error(`no se pudo leer ${nombre} (${r.status})`), { codigo: 'datos' });
    cache.set(nombre, await r.json());
  }
  return cache.get(nombre);
}

// Copia profunda con los arreglos convertidos a su tipo; junta los búferes para transferirlos.
function aTipados(res, buffers) {
  const out = { ...res };
  for (const [k, T] of Object.entries(TIPOS)) {
    if (Array.isArray(res[k])) { out[k] = T.from(res[k]); buffers.push(out[k].buffer); }
  }
  out.thp = { elementos: Int32Array.from(res.thp.elementos), valores: Int16Array.from(res.thp.valores) };
  buffers.push(out.thp.elementos.buffer, out.thp.valores.buffer);
  out.envolventes = {};
  for (const [k, v] of Object.entries(res.envolventes)) { out.envolventes[k] = Float32Array.from(v); buffers.push(out.envolventes[k].buffer); }
  out.amortiguamiento = { ...res.amortiguamiento, xi_modos: Float32Array.from(res.amortiguamiento.xi_modos) };
  buffers.push(out.amortiguamiento.xi_modos.buffer);
  out.muros_mamposteria = res.muros_mamposteria.map((m) => ({ ...m }));
  out.equipos = res.equipos.map((e) => ({ ...e }));
  out.calidad_numerica = { ...res.calidad_numerica };
  return out;
}

function f32(lista, buffers) { const a = Float32Array.from(lista); buffers.push(a.buffer); return a; }

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

function errorSimulado(msg) {
  const e = msg.simular && msg.simular.error;
  if (!e) return null;
  const textos = { datos: 'error de datos simulado', no_converge: 'el paso no convergió (simulado)', interno: 'error interno simulado' };
  return { tipo: 'error', id: msg.id, codigo: e, mensaje: textos[e] || String(e), detalle: { simulado: true } };
}

async function iniciar(msg) {
  if (msg.v !== 1) throw Object.assign(new Error(`versión de mensajes no soportada: ${msg.v}`), { codigo: 'datos' });
  if (msg.url_fixtures) base = new URL(msg.url_fixtures.endsWith('/') ? msg.url_fixtures : msg.url_fixtures + '/');
  await leer('estructura_min.json');   // el modelo existe y se puede leer
  iniciado = true;
  const listo = structuredClone(GENERADO.listo);
  listo.id = msg.id;
  self.postMessage(listo);
}

function movimiento(msg) {
  const m = GENERADO.movimiento;
  const buffers = [];
  const r = m.registro;
  const out = {
    tipo: 'movimiento', id: msg.id,
    registro: { dt: r.dt, n: r.n, ax: f32(r.ax, buffers), ay: f32(r.ay, buffers), meta: { ...r.meta },
                intensidades: structuredClone(r.intensidades), avisos: [...r.avisos] },
    espectro: { T: f32(m.espectro.T, buffers), Sa_x: f32(m.espectro.Sa_x, buffers), Sa_y: f32(m.espectro.Sa_y, buffers) },
    fourier: { f: f32(m.fourier.f, buffers), A_x: f32(m.fourier.A_x, buffers), A_y: f32(m.fourier.A_y, buffers) },
    gmpe: m.gmpe.map((g) => ({ nombre: g.nombre, peso: g.peso, T: f32(g.T, buffers), mediana_g: f32(g.mediana_g, buffers), sigma_ln: f32(g.sigma_ln, buffers) })),
    nsr10: { T: f32(m.nsr10.T, buffers), con_I: f32(m.nsr10.con_I, buffers), sin_I: f32(m.nsr10.sin_I, buffers), umbral_dano: f32(m.nsr10.umbral_dano, buffers),
             xi: m.nsr10.xi ?? 0.05, xi_umbral_dano: m.nsr10.xi_umbral_dano ?? 0.02 },
  };
  self.postMessage(out, buffers);
}

async function analizar(msg) {
  const res = await leer('resultado_min.json');
  const total = Math.max(0, (msg.simular && msg.simular.retardo_ms) ?? 600);
  const t_fin = res.t[res.t.length - 1];
  for (const fraccion of [0.25, 0.5, 0.75]) {
    await esperar(total / 4);
    self.postMessage({ tipo: 'progreso', id: msg.id, fraccion, t_s: fraccion * t_fin });
  }
  await esperar(total / 4);
  const err = errorSimulado(msg);
  if (err) { self.postMessage(err); return; }
  const buffers = [];
  const resultados = aTipados(res, buffers);
  resultados.id = msg.id;
  self.postMessage({ tipo: 'resultado', id: msg.id, resultados }, buffers);
}

async function serieElemento(msg) {
  const res = await leer('resultado_min.json');
  let s;
  const archivo = await leer('serie_elemento_min.json');
  if (msg.elemento === archivo.elemento) s = archivo;
  else if (GENERADO.series[msg.elemento]) s = { ...GENERADO.series[msg.elemento], t: res.t };
  else throw Object.assign(new Error(`elemento desconocido: ${msg.elemento}`), { codigo: 'datos' });
  const buffers = [];
  const out = { tipo: 'serie_elemento', id: msg.id, elemento: msg.elemento };
  for (const k of ['t', 'Mi', 'Mj', 'V', 'N', 'thp_i', 'thp_j', 'dc']) out[k] = f32(s[k], buffers);
  self.postMessage(out, buffers);
}

self.onmessage = async (ev) => {
  const msg = ev.data || {};
  try {
    // `analizar` simula el error al final, después de los mensajes de progreso; los demás, de inmediato
    const err = msg.tipo !== 'analizar' && errorSimulado(msg);
    if (err) { self.postMessage(err); return; }
    if (msg.tipo === 'iniciar') { await iniciar(msg); return; }
    if (!iniciado && ['movimiento', 'analizar', 'serie_elemento'].includes(msg.tipo)) {
      throw Object.assign(new Error('falta el mensaje iniciar'), { codigo: 'datos' });
    }
    if (msg.tipo === 'movimiento') movimiento(msg);
    else if (msg.tipo === 'analizar') await analizar(msg);
    else if (msg.tipo === 'serie_elemento') await serieElemento(msg);
    else throw Object.assign(new Error(`mensaje desconocido: ${msg.tipo}`), { codigo: 'datos' });
  } catch (e) {
    self.postMessage({ tipo: 'error', id: msg.id, codigo: e.codigo || 'interno', mensaje: e.message, detalle: { simulado: true } });
  }
};

self.postMessage({ tipo: 'cargado' });
