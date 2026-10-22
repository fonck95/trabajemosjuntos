# Simulación sísmica: formato de los modelos y del motor

Este documento fija el contrato entre los modelos estructurales (`data/sismo/*_estructura.json`), la amenaza
(`data/sismo/amenaza.json`), el motor de cálculo en JavaScript (`web/js/sismo/`) y la validación con OpenSees
(`scripts/sismo/validar_opensees.py`). Quien cambie el formato actualiza este documento.

## Unidades y ejes

- Fuerza en kN, longitud en m, tiempo en s, masa en t (= kN·s²/m), ángulos en rad, esfuerzos en MPa solo en `materiales`.
- Gravedad g = 9,80665 m/s².
- Ejes del modelo: x al este, y al norte, z arriba. El origen es el ancla de la especificación del edificio
  (`data/edificios/<id>.json`, mismo marco en metros). Así el modelo cae encima del 3D de la web.

## Idealización (por qué así)

Modelo pseudotridimensional clásico (el de TABS/ETABS en su origen, Wilson y Dovey, 1972):

- Cada bloque (cuerpo separado por juntas) tiene un diafragma rígido por nivel con 3 grados de libertad
  dinámicos en su centro de masa: ux, uy y rz (giro alrededor de z, antihorario visto desde arriba).
- La resistencia lateral la dan **pórticos planos** (dirección x o y) y **resortes laterales** (muros de mampostería).
  Una columna que pertenece a un pórtico en x y a otro en y aparece en los dos, con su rigidez en cada plano.
- El desplazamiento lateral de un pórtico en x ubicado en y = yf, en el nivel k, es  dx = ux_k − (yf − yc_k)·rz_k;
  el de un pórtico en y ubicado en x = xf es  dy = uy_k + (xf − xc_k)·rz_k  (xc, yc: centro de masa del nivel).
- Cada nodo de un pórtico tiene además su desplazamiento vertical v y su giro θ en el plano: son grados de libertad
  sin masa que se condensan (equilibrio estático) en cada iteración.
- La masa está concentrada en los diafragmas (masa traslacional y momento polar Jz).
- Amortiguamiento de Rayleigh con la rigidez inicial; P-Delta lineal por nivel (−P/h).

## `data/sismo/<id>_estructura.json`

```json
{
  "id": "torre_hospital | hospital_actual",
  "nombre": "texto",
  "tipo_dato": "calculo_propio | estimacion",
  "sistema_estructural": "texto (p. ej. pórticos de concreto resistentes a momento DES, NSR-10 C.21)",
  "norma": "NSR-10, títulos A, B y C (o el código con el que se construyó)",
  "materiales": {
    "concreto_28": { "tipo": "concreto", "fc_MPa": 28, "Ec_MPa": 24870, "nu": 0.2, "peso_kN_m3": 24, "fuente": "NSR-10 C.8.5.1: Ec = 4700√f'c" },
    "acero_420":   { "tipo": "acero", "fy_MPa": 420, "fu_MPa": 630, "Es_MPa": 200000, "fuente": "NTC 2289" },
    "ladrillo":    { "tipo": "mamposteria", "fm_MPa": 4.0, "Em_MPa": 2800, "Gm_MPa": 1120, "tau0_MPa": 0.12, "peso_kN_m3": 18, "fuente": "..." }
  },
  "secciones": {
    "C55": {
      "tipo": "rectangular", "b": 0.55, "h": 0.55, "material": "concreto_28",
      "A": 0.3025, "I": 0.007626, "Av": 0.2521,
      "factor_fisuracion": 0.70,
      "refuerzo": { "longitudinal": "12 N° 7", "rho": 0.0153, "estribos": "N° 4 c/0,10 en zona confinada" },
      "P_gravedad_kN": 1450,
      "momento_curvatura": [[0, 0], [0.0062, 410], [0.06, 480]],
      "My_kNm": 410, "Mn_kNm": 455, "phiMn_kNm": 410, "Mpr_kNm": 560,
      "theta_y": 0.0045, "theta_p_cap": 0.035,
      "Vn_kN": 980, "phiVn_kN": 735,
      "endurecimiento": 0.03,
      "histeresis": "bilineal | clough",
      "calculo": "texto corto: cómo salen My, Mn, Vn y θp (fórmula y artículo)"
    }
  },
  "bloques": [
    {
      "id": "torre",
      "niveles": [
        { "id": "N1", "z": 4.5, "altura_entrepiso": 4.5, "masa_t": 0, "Jz_t_m2": 0, "cm": [0, 0],
          "peso_sismico_kN": 0, "P_sobre_entrepiso_kN": 0, "detalle_masa": { "losa": 0, "acabados": 0, "muros": 0, "viva_25pct": 0 } }
      ],
      "porticos": [
        {
          "id": "X-3", "direccion": "x", "coordenada": -7.6,
          "nodos": [ { "id": "X-3/A0", "s": -13.0, "nivel": 0 }, { "id": "X-3/A1", "s": -13.0, "nivel": 1 } ],
          "apoyos": { "X-3/A0": "empotrado" },
          "elementos": [
            { "id": "C-A3-1", "tipo": "columna", "i": "X-3/A0", "j": "X-3/A1", "seccion": "C55", "eje": "A-3", "nivel": 1 },
            { "id": "VX-3-AB-1", "tipo": "viga", "i": "X-3/A1", "j": "X-3/B1", "seccion": "V40x60", "eje": "3 entre A y B", "nivel": 1 }
          ]
        }
      ],
      "resortes": [
        {
          "id": "M-ESP-N1", "tipo": "muro_mamposteria", "direccion": "x", "coordenada": 12.3, "nivel": 1,
          "posicion": [x0, y0, x1, y1], "L": 8.4, "t": 0.15, "h": 3.0, "material": "ladrillo", "aberturas_pct": 30,
          "envolvente": { "k0_kN_m": 0, "Vcr_kN": 0, "dcr_m": 0, "Vmax_kN": 0, "dmax_m": 0, "du_m": 0, "residual": 0.2 },
          "histeresis": "tomazevic",
          "modo_falla": "tension_diagonal | deslizamiento | balanceo",
          "estados_de_dano": [ { "nombre": "leve", "deriva": 0.001 }, { "nombre": "moderado", "deriva": 0.003 },
                               { "nombre": "extenso", "deriva": 0.006 }, { "nombre": "colapso", "deriva": 0.01 } ],
          "calculo": "texto corto con las fórmulas de rigidez y resistencia"
        }
      ]
    }
  ],
  "amortiguamiento": { "tipo": "rayleigh", "xi": 0.05, "modos": [1, 3] },
  "p_delta": true,
  "limites": { "deriva": 0.01, "fuente": "NSR-10 A.6.4.1" },
  "diseno": { "Aa": 0.15, "Av": 0.15, "suelo": "D", "Fa": 1.5, "Fv": 2.2, "I": 1.5, "Ta_s": 0.6, "Sa_g": 0.84, "R": 7, "Vs_kN": 0 },
  "fuentes": [], "supuestos": [], "incertidumbres": []
}
```

Reglas que el motor asume:

- Longitud de un elemento: distancia entre sus nodos (s, z del nivel; la base está en z = 0).
- Rigidez elástica: E del material, `I · factor_fisuracion`, A y Av (Timoshenko, G = E / (2(1 + nu))).
- Rótulas: concentradas en los extremos de vigas y columnas (y en la base de los muros de concreto si los hay),
  modelo de Giberson (resorte rotacional en serie con el elemento elástico). Rígidas hasta `My_kNm`; después,
  pendiente `endurecimiento · 6EI/L` (EI fisurada). `bilineal` = endurecimiento cinemático; `clough` = recarga
  hacia el punto de máxima respuesta anterior.
- Demanda/capacidad que se muestra: flexión |M| / `phiMn_kNm`, cortante |V| / `phiVn_kN`, rotación plástica
  θp / `theta_p_cap`; en muros, deriva / deriva del estado de daño y V / Vmax.
- `P_sobre_entrepiso_kN` de cada nivel: carga de gravedad total por encima de ese entrepiso (para P-Delta).

## `data/sismo/amenaza.json`

Parámetros del método estocástico de fuente puntual (Boore, 2003) para Yondó y escenarios de referencia:
fuente de Brune (caída de esfuerzos Δσ), dispersión geométrica por tramos, Q(f) = Q0·f^η, kappa κ0,
amplificación del sitio, duración (1/f0 + b·R), velocidades β y ρ, ventana de Saragoni-Hart, distancia
epicentral por defecto, rangos de magnitud y profundidad, y una ecuación de predicción (GMPE) independiente
para comparar. Cada parámetro con su fuente. Ver `scripts/sismo/estocastico.py` (implementación de referencia).

## Motor (`web/js/sismo/`)

- `movimiento.js`: síntesis del acelerograma (dos componentes horizontales) a partir de Mw, profundidad,
  distancia epicentral, parámetros y semilla; espectro de Fourier, espectro de respuesta, PGA, PGV, Arias,
  duración 5-95 %, comparación con la GMPE.
- `modelo.js`: arma el modelo desde `*_estructura.json`, condensa y calcula modos (períodos y formas).
- `integrador.js`: Newmark (aceleración promedio) con Newton-Raphson; estado de rótulas y muros; balance de
  energía (entrada = cinética + deformación elástica + amortiguada + histerética).
- `trabajador.js`: corre el análisis en un Web Worker y devuelve resultados para animar.
- Pruebas: `node scripts/sismo/test_motor.mjs` (soluciones cerradas, energía, convergencia con dt) y
  `python3 scripts/sismo/validar_opensees.py` (mismo modelo y mismo registro en OpenSees 3.8).
