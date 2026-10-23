# Simulación sísmica: formato de los modelos y del motor

Este documento fija el contrato entre los modelos estructurales (`data/sismo/*_estructura.json`), la amenaza
(`data/sismo/amenaza.json`), el motor de cálculo en JavaScript (`web/js/sismo/`) y la validación con OpenSees
(`scripts/sismo/validar_opensees.py`). Quien cambie el formato actualiza este documento.

> **Versión 2 (23-oct-2026).** Aplica los cambios E1 a E16 del contrato de integración de la torre
> (`data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md`, sección 7.1). Se **agregan** campos opcionales,
> la sección de resultados y la de mensajes; ningún campo que ya existía cambia de significado. Dos **reglas** sí
> cambian y se marcan como «Cambio de regla»: la demanda/capacidad que se muestra (E16) y el anclaje del
> amortiguamiento (E8). La tabla del final dice dónde quedó cada cambio.

## Unidades y ejes

- Fuerza en kN, longitud en m, tiempo en s, masa en t (= kN·s²/m), ángulos en rad, esfuerzos en MPa solo en `materiales`.
- Gravedad g = 9,80665 m/s².
- Ejes del modelo: x al este, y al norte, z arriba. El origen es el ancla de la especificación del edificio
  (`data/edificios/<id>.json`, mismo marco en metros). Así el modelo cae encima del 3D de la web.
- Todo ángulo en planta (la dirección del sismo `angulo_deg`, `rot_z` de los equipos) se mide en sentido antihorario
  desde +x (el este).
- **Ejes con nombre (E6).** Las líneas de x constante se llaman con letras (`A`, `B`, …, de occidente a oriente) y
  las de y constante con números (`1`, `2`, …, de sur a norte). En la torre: `A = −13,0`, `B = −5,8`, `C = 1,4`,
  `D = 8,6`; `1 = −19,6`, `2 = −12,4`, `3 = −7,6`, `4 = 0,8`, `5 = 8,0`, `6 = 14,0`, `7 = 22,4` (contrato, 1.2).
  La estructura los guarda en el bloque `ejes`.
- **Coordenada `s` de los nodos (E12):** `s = x` en los pórticos X y `s = y` en los pórticos Y.

## Idealización (por qué así)

Modelo pseudotridimensional clásico (el de TABS/ETABS en su origen, Wilson y Dovey, 1972):

- Cada bloque (cuerpo separado por juntas) tiene un diafragma rígido por nivel con 3 grados de libertad
  dinámicos en su centro de masa: ux, uy y rz (giro alrededor de z, antihorario visto desde arriba).
- La resistencia lateral la dan **pórticos planos** (dirección x o y), **muros de concreto** como columnas anchas
  dentro de «pórticos» de muros (E1) y **resortes laterales** (muros de mampostería). Una columna que pertenece a un
  pórtico en x y a otro en y aparece en los dos, con su rigidez en cada plano; el campo `fisico` dice cuál es la
  columna física (E6).
- El desplazamiento lateral de un pórtico en x ubicado en y = yf, en el nivel k, es  dx = ux_k − (yf − yc_k)·rz_k;
  el de un pórtico en y ubicado en x = xf es  dy = uy_k + (xf − xc_k)·rz_k  (xc, yc: centro de masa del nivel).
- Cada nodo de un pórtico tiene además su desplazamiento vertical v y su giro θ en el plano: son grados de libertad
  sin masa que se condensan (complemento de Schur) en cada iteración de Newton; su equilibrio se impone en la misma
  iteración, sin iteración anidada.
- La masa está concentrada en los diafragmas (masa traslacional y momento polar Jz).
- Rigidez axial `EA/L` en cada copia de una columna (limitación conocida de TABS: la columna compartida suma su
  rigidez axial en los dos pórticos). Las vigas no se deforman axialmente: sus dos extremos están en el mismo
  diafragma.
- **Gravedad primero (E4):** análisis estático no lineal con las cargas de gravedad de las vigas y de los nodos; el
  análisis dinámico parte de ese estado (desplazamientos, momentos y axiales).
- **P-Delta lineal por nivel con el peso y el centro de masa de cada nivel de encima (E14)** y **amortiguamiento de
  Rayleigh de la parte elástica de los elementos, sin las rótulas (E8)**: ver «Motor».

Limitaciones declaradas (las mismas que la vista debe mostrar): diafragmas rígidos, pórticos planos, rótulas
concentradas en los extremos (una rótula positiva dentro del vano de una viga no se captura), núcleos como muros
planos con aletas efectivas (sin compatibilidad vertical en las esquinas y sin variación de la resistencia con la
carga axial del sismo), sin interacción suelo-estructura, sin componente vertical, sin degradación de resistencia.

## `data/sismo/<id>_estructura.json`

```json
{
  "id": "torre_hospital | hospital_actual",
  "nombre": "texto",
  "tipo_dato": "calculo_propio | estimacion",
  "generado_por": "scripts/sismo/estructura_torre.py  (E13, opcional)",
  "fecha": "2026-10-23  (E13, opcional)",
  "insumos_sha1": { "data/proyectos/torre_hospital/presupuesto.json": "…  (opcional; obligatorio en los generados, contrato 10.1)" },
  "sistema_estructural": "texto (p. ej. pórticos de concreto resistentes a momento DES, NSR-10 C.21)",
  "norma": "NSR-10, títulos A, B y C (o el código con el que se construyó)",
  "ejes": { "x": [ { "id": "A", "x": -13.0 } ], "y": [ { "id": "1", "y": -19.6 } ] },
  "sistema": {
    "tipo": "dual | combinado | porticos | muros",
    "fraccion_cortante_porticos": 0.31,
    "tabla": "NSR-10 Tabla A.3-4, fila … (por confirmar)",
    "R0": 0, "Omega0": 0,
    "justificacion": "texto: cómo se calculó la fracción con el modelo elástico (paso 0 del prediseño)"
  },
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
      "theta_y": 0.0045, "theta_p_cap": 0.035, "theta_p_b": 0.05,
      "Vn_kN": 980, "phiVn_kN": 735,
      "My_e_kNm": 512, "Mn_e_kNm": 569, "Vn_e_kN": 1120, "theta_y_e": 0.0056,
      "theta_p_IO": 0.005, "theta_p_LS": 0.015, "theta_p_CP": 0.02,
      "interaccion_PM": [[-3000, 455], [0, 330], [1000, 210]],
      "endurecimiento": 0.03,
      "histeresis": "bilineal | clough",
      "calculo": "texto corto: cómo salen My, Mn, Vn, θp y las propiedades esperadas (fórmula, factores y artículo)"
    },
    "V40x60": {
      "tipo": "rectangular", "b": 0.40, "h": 0.60, "material": "concreto_28", "…": "…",
      "My_kNm": 300, "My_pos_kNm": 220, "My_neg_kNm": 300, "My_e_kNm": 375, "My_e_pos_kNm": 275, "My_e_neg_kNm": 375
    },
    "MURO-NN": {
      "tipo": "muro", "b": 0.30, "h": 5.50, "material": "concreto_28",
      "aletas": [ { "lado": "i", "ancho_efectivo_m": 1.80, "espesor_m": 0.30 }, { "lado": "j", "ancho_efectivo_m": 0.0, "espesor_m": 0.30 } ],
      "A": 2.19, "I": 5.9, "Av": 1.375, "factor_fisuracion": 0.35, "lp_m": 2.75,
      "My_kNm": 9000, "My_pos_kNm": 9000, "My_neg_kNm": 6500, "theta_y": 0.000482, "…": "…"
    }
  },
  "bloques": [
    {
      "id": "torre",
      "niveles": [
        { "id": "N1", "z": 4.5, "altura_entrepiso": 4.5, "masa_t": 0, "Jz_t_m2": 0, "cm": [0, 0],
          "contorno": [[-13.0, -19.6], [8.6, -19.6], [8.6, 22.4], [-13.0, 22.4]],
          "peso_sismico_kN": 0, "P_sobre_entrepiso_kN": 0, "detalle_masa": { "losa": 0, "acabados": 0, "muros": 0, "viva_25pct": 0 } }
      ],
      "porticos": [
        {
          "id": "X-3", "direccion": "x", "coordenada": -7.6,
          "nodos": [ { "id": "X-3/A0", "s": -13.0, "nivel": 0 }, { "id": "X-3/A1", "s": -13.0, "nivel": 1, "carga_kN": 0 } ],
          "apoyos": { "X-3/A0": "empotrado" },
          "elementos": [
            { "id": "C-A3-1@X", "fisico": "C-A3-1", "tipo": "columna", "i": "X-3/A0", "j": "X-3/A1", "seccion": "C55", "eje": "A-3", "nivel": 1, "brazo_rigido_m": [0.0, 0.30] },
            { "id": "VX-3-AB-1", "tipo": "viga", "i": "X-3/A1", "j": "X-3/B1", "seccion": "V40x60", "eje": "3 entre A y B", "nivel": 1,
              "w_gravedad_kN_m": 0, "brazo_rigido_m": [0.30, 0.30] }
          ]
        },
        {
          "id": "MY-D", "direccion": "y", "coordenada": 8.6,
          "nodos": [ { "id": "MY-D/60", "s": 18.2, "nivel": 0 }, { "id": "MY-D/61", "s": 18.2, "nivel": 1 } ],
          "apoyos": { "MY-D/60": "empotrado" },
          "elementos": [ { "id": "MY-D6-1", "tipo": "muro_concreto", "i": "MY-D/60", "j": "MY-D/61", "seccion": "MURO-NN", "eje": "D entre 6 y 7", "nivel": 1 } ]
        }
      ],
      "resortes": [
        {
          "id": "M-ESP-N1", "tipo": "muro_mamposteria", "direccion": "x", "coordenada": 12.3, "nivel": 1, "aislado": true,
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
  "amortiguamiento": { "tipo": "rayleigh", "xi": 0.05, "periodos_ancla_s": null, "rigidez": "inicial_parte_elastica" },
  "p_delta": true,
  "limites": { "deriva": 0.01, "deriva_umbral_dano": 0.004, "deriva_umbral_dano_mamposteria": 0.002,
               "tipo_deriva": "vectorial en los vértices del contorno", "fuente": "NSR-10 A.6.3.1, A.6.4.1 y Tabla A.12.5-1" },
  "diseno": { "Aa": 0.15, "Av": 0.15, "suelo": "D", "Fa": 1.5, "Fv": 2.2, "I": 1.5, "Ta_s": 0.6, "Sa_g": 0.84, "R": 7, "Vs_kN": 0 },
  "prediseno": { "…": "salida del prediseño de la torre (ver abajo)" },
  "fuentes": [], "supuestos": [], "incertidumbres": []
}
```

### Campos

**Obligatorios** (los que ya tenía el esquema): `id`, `nombre`, `tipo_dato`, `sistema_estructural`, `norma`,
`materiales`, `secciones`, `bloques`, `amortiguamiento`, `p_delta`, `limites`, `diseno`, `fuentes`, `supuestos`,
`incertidumbres`. En cada nivel: `id`, `z`, `altura_entrepiso` (= z − z del nivel de abajo), `masa_t`, `Jz_t_m2`,
`cm`, `peso_sismico_kN`. En cada sección de viga o columna: `A`, `I`, `Av`, `factor_fisuracion`, `My_kNm`, `Mn_kNm`,
`phiMn_kNm`, `Mpr_kNm`, `theta_y`, `theta_p_cap`, `Vn_kN`, `phiVn_kN`, `endurecimiento`, `histeresis`, `calculo`.

**Agregados en la versión 2** (opcionales para el formato; el motor los usa si están):

| Campo | Dónde | Qué es | Cambio |
|---|---|---|---|
| `tipo: "muro_concreto"` | elementos | Muro de concreto como columna ancha de Timoshenko (`A`, `I·factor_fisuracion`, `Av`), con rótula **solo en la base**. Va en «pórticos» de muros con id `MX-{línea}` (muros en x, a lo largo de una línea de y constante) o `MY-{línea}`; el elemento se llama `M{X\|Y}-{línea}{eje}-{nivel}` (`MY-D6-1`: muro en la línea D junto al eje 6, nivel 1; el campo `eje` dice el tramo) | E1 |
| `aletas`, `lp_m` | secciones de muro | Ancho efectivo de los paños perpendiculares que llegan a cada borde (NSR-10 C.21.9.5.2, numeral por confirmar), incluido en `A`, `I` y en el momento-curvatura de la base. `lp_m` = longitud de rótula; si falta, `lp = min(0,5·lw; altura del piso)` con `lw = h` de la sección (ASCE/SEI 41-17, por confirmar) | E1 |
| `brazo_rigido_m: [di, dj]` | vigas, columnas y muros | Zona rígida del nudo en cada extremo; longitud flexible `L_f = L − di − dj` | E2 |
| `My_pos_kNm`, `My_neg_kNm` | secciones de viga y de muro | Fluencia asimétrica; si faltan, se usa `My_kNm` en los dos sentidos | E3 |
| `w_gravedad_kN_m` | vigas | Carga de gravedad repartida en toda la viga (kN/m, hacia abajo) | E4 |
| `carga_kN` | nodos | Carga vertical puntual hacia abajo en el nodo (kN) | E4 |
| `aislado: true \| false` | resortes de mampostería | `true`: el muro está separado de la estructura (grupo IV, NSR-10 A.9, numeral por confirmar): no aporta rigidez, pero su daño se evalúa con la deriva del entrepiso. `false`: el muro trabaja con la envolvente de Tomaževič («qué pasa si no se aíslan»). Si falta vale `false`, que es lo que el resorte significaba en la versión 1; la torre lo escribe siempre | E5 |
| `fisico` | columnas (y muros) | Id de la columna física cuando aparece en dos pórticos: `C-A3-1@X` y `C-A3-1@Y` tienen `fisico: "C-A3-1"`. En vigas y muros, si falta, es el propio id | E6 |
| `contorno` | niveles | Polígono del diafragma (vértices en orden, en m). Sirve para dibujar la losa, calcular `Jz` y medir la deriva en los vértices (E9); el piso 4 de la torre retrocede | E7 |
| `periodos_ancla_s`, `rigidez` | `amortiguamiento` | Ver «Amortiguamiento» (Cambio de regla) | E8 |
| `deriva_umbral_dano`, `deriva_umbral_dano_mamposteria`, `tipo_deriva` | `limites` | 0,004 y 0,002 (NSR-10 Tabla A.12.5-1: 0,40 %, y 0,20 % en mampostería que no cumpla A.12.5.3.1; dato oficial). La deriva se compara como **vector** en los vértices del contorno (NSR-10 A.6.3.1, ec. A.6.3-1; numeral por confirmar) | E9 |
| `interaccion_PM` | secciones de columna y muro | Pares `[P_kN, My_kNm]` (compresión negativa) — **fase 2**: el motor puede ignorarlos y la validación corre sin ellos | E10 |
| `ejes`, `sistema`, `prediseno`, `generado_por`, `fecha` | raíz | Trazabilidad (ver «Prediseño de la torre») | E13 |
| `My_e_kNm` (y `My_e_pos_kNm`, `My_e_neg_kNm`), `Mn_e_kNm`, `Vn_e_kN`, `theta_y_e` | secciones | Propiedades **esperadas** que usa la simulación: factores de material esperado de ASCE/SEI 41-17 para f'c y fy (declarados en `calculo`; por confirmar) y φ = 1. Si faltan, el motor usa `My_kNm`, `Mn_kNm`, `Vn_kN` y `theta_y` (y el validador avisa) | E16 |
| `theta_p_IO`, `theta_p_LS`, `theta_p_CP`, `theta_p_b` | secciones | Límites de rotación plástica de ocupación inmediata, seguridad de la vida y prevención del colapso, y el parámetro «b» de modelado (ASCE/SEI 41-17, tablas de vigas, columnas y muros de concreto; por confirmar). `theta_p_cap` («a») conserva su significado: inicio de la pérdida de resistencia. Si faltan los límites, `dc_rotacion` usa `theta_p_cap` y no se marcan los bits de IO, LS y CP | E16 |

`P_sobre_entrepiso_kN` se conserva como **dato informativo** (carga total por encima del entrepiso); el motor ya no
lo usa para P-Delta (E14).

### Convención de ids (E6)

- Pórticos: `X-{n}` (pórtico a lo largo de x en la línea n) y `Y-{L}` (a lo largo de y en la línea L); de muros:
  `MX-{n}` y `MY-{L}`.
- Nodos: `{pórtico}/{eje}{nivel}`: `X-3/A0` (pórtico X-3, eje A, base); en los pórticos Y el eje es un número:
  `Y-A/10`, `Y-A/21`.
- Columnas: `C-{eje x}{eje y}-{nivel}@{X|Y}`: `C-A3-1@X` (columna A-3 del nivel 1 en su pórtico X) y `C-A3-1@Y`.
- Vigas: `VX-{línea}-{eje}{eje}-{nivel}` y `VY-{línea}-{eje}{eje}-{nivel}`: `VX-3-AB-1`, `VY-A-34-1`.
- Muros de concreto: `MY-D6-1`; muros de mampostería: `M-{lo que los ubique}` (`M-X1-1`, `M-ESP-N1`).
- Los ids son únicos en todo el archivo (también entre pórticos).
- Orden: los índices de elementos, nodos y pórticos de `Resultados` siguen el orden del archivo (bloques →
  pórticos → nodos y elementos).

### Signos y convenciones del elemento

- En el plano de cada pórtico, `s` va a la derecha y `z` arriba; los giros y los **momentos de extremo** son
  positivos en sentido antihorario en ese plano. El nodo `i` de una viga queda a menor `s` que el `j`; el `i` de una
  columna o un muro, abajo.
- **Vigas:** el momento de flexión (positivo con tracción abajo) es `−M_i` en el extremo i y `+M_j` en el j.
  `My_pos` es la fluencia con tracción abajo (refuerzo inferior) y `My_neg` con tracción arriba (sobre los apoyos):
  la rótula del extremo i es rígida mientras `−My_pos ≤ M_i − β_i ≤ My_neg`, y la del j mientras
  `−My_neg ≤ M_j − β_j ≤ My_pos` (β: retroceso del endurecimiento cinemático).
- **Muros:** `My_pos` corresponde a momento de extremo positivo en la base, es decir, al borde de mayor `s` (y su
  aleta) en compresión; `My_neg`, al borde de menor `s` en compresión.
- Axial `N` positivo en tracción. Cortante del elemento `V = (M_i + M_j)/L_f ∓ w·L_f/2` (extremo i con −, j con +);
  en columnas `V = (M_i + M_j)/L_f` es la fuerza que el entrepiso resiste (positiva con deriva positiva).

### Reglas que el motor asume

- Longitud de un elemento: distancia entre sus nodos (s, z del nivel; la base está en z = 0); longitud flexible
  `L_f = L − di − dj` (E2). Las fuerzas pasan al nudo a través de los brazos rígidos (`M_nudo = M + V·d`).
- Rigidez elástica: E del material, `I · factor_fisuracion`, A y Av (Timoshenko, G = E / (2(1 + nu))).
  Flexibilidad de la parte elástica: `f_e = (L_f/(6EI))·[[2, −1], [−1, 2]] + (1/(G·Av·L_f))·[[1, 1], [1, 1]]`.
- Carga del vano (E4): giros de viga simplemente apoyada `θ0 = c·[−1, +1]`, `c = w·L_f³/(24EI) + w·L_f/(2·G·Av)`;
  la carga sobre los brazos rígidos pasa directo a los nudos.
- Rótulas: concentradas en los extremos de vigas y columnas y **solo en la base** de los muros de concreto (E1),
  modelo de Giberson (resorte rotacional en serie con el elemento elástico). Rígidas hasta la fluencia **esperada**
  `My_e` (E16; asimétrica en vigas y muros, E3); después, pendiente `H = endurecimiento · k_e` con
  `k_e = 6EI_fis/L_f` en vigas y columnas y `k_e = EI_fis/lp` en muros (E1); si `endurecimiento` es 0 se usa 10⁻⁴.
  `bilineal` = endurecimiento cinemático (`β = H·θp`); `clough` = recarga hacia el punto de máxima respuesta anterior
  (regla completa en el contrato, 7.4).
- `theta_y` (nominal) vale `My·L_f/(6·EI_fis)` en vigas y columnas (doble curvatura) y `My·lp/EI_fis` en muros;
  `theta_y_e` es lo mismo con `My_e`. `scripts/sismo/validar_resultado.mjs` lo comprueba con ± 1 %.
- **Cambio de regla (E16) — demanda/capacidad que se muestra:** flexión `|M| / Mn_e_kNm`, cortante `|V| / Vn_e_kN`,
  rotación plástica `θp / theta_p_IO` (grupo IV: ocupación inmediata), con marcas de LS y CP; `dc` es el máximo de
  los tres. En muros de mampostería, deriva / deriva del estado de daño. Antes la regla era `|M|/phiMn_kNm`,
  `|V|/phiVn_kN` y `θp/theta_p_cap`: mezclaba criterios de diseño con la respuesta, y `theta_p_cap` («a») marca el
  inicio de la pérdida de resistencia, no un límite de desempeño. `phiMn_kNm`, `phiVn_kN` y `My_kNm` conservan su
  significado y se usan en el prediseño.
- `P_sobre_entrepiso_kN`: informativo (E14). P-Delta: ver «Motor».

### Amortiguamiento (Cambio de regla, E8)

`amortiguamiento: { "tipo": "rayleigh", "xi": 0.05, "periodos_ancla_s": [Ti, Tj] | null, "rigidez": "inicial_parte_elastica" }`

- Con `periodos_ancla_s: null`, el motor usa `Ti = T1` (el período más largo) y `Tj` = el menor entre (a) el período
  del modo con el que la masa participativa acumulada llega a ≥ 90 % en x **y** en y y (b) `0,2·T1`; todo con la
  rigidez inicial (elástica condensada más `K_PΔ`).
- `a0 = 2ξ·ωi·ωj/(ωi + ωj)`, `a1 = 2ξ/(ωi + ωj)`; `C = a0·M + a1·Σe K0,e`, donde `K0,e` es la rigidez inicial de la
  **parte elástica** de cada viga, columna y muro (flexión, cortante y axial). **Las rótulas nunca amortiguan**
  (evita el amortiguamiento espurio después de la fluencia, Charney 2008), y así OpenSees con
  `rayleigh(a0, 0, a1, 0)` y `zeroLength` sin Rayleigh es réplica exacta.
- `modos: [1, 3]` (la forma anterior) sigue aceptándose, pero `periodos_ancla_s` manda si están los dos, y los
  validadores avisan si se usa `modos`. Por qué: en el modelo pseudotridimensional los modos 1 a 3 suelen ser los
  tres fundamentales (x, y, torsión), con ω3 ≈ 1,2-1,5·ω1, y anclar en 1 y 3 sobreamortigua los modos altos (con
  ω3 = 1,3·ω1: ξ ≈ 7,5 % en 3ω1, 11 % en 5ω1 y ≈ 22 % en 10ω1; cálculo propio del contrato) y baja las aceleraciones
  de piso con las que se evalúa la dotación.
- El motor publica el ξ efectivo de los primeros `min(12, 3N)` modos: `ξ_r = φ_rᵀ(a0·M + a1·K_el)φ_r / (2ω_r)` con
  modos normalizados a la masa y `K_el` la rigidez elástica condensada sin P-Delta.

### Prediseño de la torre (`sistema` y `prediseno`, E13)

`data/sismo/torre_hospital_estructura.json` lo genera `scripts/sismo/estructura_torre.py` (Python, solo biblioteca
estándar, determinista byte a byte; `--verificar` regenera y compara). Pasos y salidas (contrato, 7.2):

- `sistema` (paso 0): fracción del cortante que resisten los pórticos solos con el modelo elástico; si es ≥ 25 %, el
  sistema es **dual** (Tabla A.3-4), si no, **combinado** (Tabla A.3-2); fila de la tabla, `R0`, `Omega0` y
  justificación (numerales por confirmar).
- `prediseno` (paso 7): `R = φa·φp·φr·R0` con cada factor justificado; período del modelo, `Ta` y `Cu·Ta` de la fila
  del sistema adoptado; cortante basal de diseño (FHE y modal, con el factor de ajuste a ≥ 80 % o ≥ 90 % de la FHE);
  `derivas_vector` por entrepiso con el punto donde ocurren y por pórtico; `derivas_umbral_dano` (Ad = 0,04; ≤ 0,4 %
  con muros aislados y ≤ 0,2 % sin aislar); irregularidades 1aP/1bP y 3A con sus cocientes; relaciones columna-viga
  (≥ 1,2); cortante por capacidad; cuantías; excentricidades y centro de rigidez por nivel; `periodos_ancla_s` del
  amortiguamiento con el ξ efectivo de los 12 primeros modos; supuestos e incertidumbres (sin estudio de suelos:
  base empotrada sobre los dados de pilotes).

## `data/sismo/amenaza.json`

Parámetros del método estocástico de fuente puntual (Boore, 2003) para Yondó y escenarios de referencia:
fuente de Brune (caída de esfuerzos Δσ), dispersión geométrica por tramos, Q(f) = Q0·f^η, kappa κ0,
amplificación del sitio, duración (1/f0 + b·R), velocidades β y ρ, ventana de Saragoni-Hart, distancia
epicentral por defecto, rangos de magnitud y profundidad, y ecuaciones de predicción (GMPE) independientes
para comparar. Cada parámetro con su fuente.

- Es copia de `data/sismo/fuentes_investigacion/amenaza.json` **sin cambiar números** (comprobación:
  `node scripts/sismo/test_motor.mjs --solo F2`). Agrega solo lo del contrato (7.3): `implementacion_de_referencia`
  (`scripts/sismo/estocastico.py`, puerto de `fuentes_investigacion/sim.py` y `gmpe.py`), una nota en
  `seleccion_de_regimen` que remite a la transición E15, y en `escenarios_lejanos_sentidos` el sismo de 7,4 del
  10-ago-2026 con la inconsistencia del epicentro (OPS: San José del Palmar; anexo C: Pereira) y sus dos distancias
  (≈ 342 y 313 km, fuera del rango de 0-300 km del control; cálculo propio de la investigación).
- Todo lo sismotectónico sigue **por confirmar** (centro del nido, distancias a fallas, magnitudes máximas).
- **Transición de profundidad (E15; regla del motor, no un número de este archivo).** Con `regimen: 'auto'`, entre
  40 y 70 km hay una banda con peso `w(h) = clamp((h − 40)/30, 0, 1)`:
  `ln A(f) = (1 − w)·ln A_cortical(f) + w·ln A_intraplaca(f)`, cada término con sus propios parámetros de este
  archivo (Δσ, βs, ρs, Q, κ0, dispersión, duración, `Fimp`), y `Tgm = (1 − w)·Tgm,cortical + w·Tgm,intraplaca`. Fuera
  de la banda, un solo régimen. El umbral brusco de `seleccion_de_regimen.regla` (50 km) ya no se usa: con él, mover
  la profundidad 1 km cambiaba el PGA hasta 3 a 4 veces (Mw 6,2 a 92 km: 0,0247 g con h = 49,9 km y 0,0795 g con
  h = 50 km; prueba de la revisión con `sim.py`), un artefacto del umbral y no física. Si la persona fuerza el
  régimen, `avisos` advierte «intraplaca con h < 40 km» o «cortical con h > 60 km».

## Motor (`web/js/sismo/`)

Módulos puros: sin DOM, sin three, sin especificadores del importmap; imports relativos con extensión `.js`.
Firmas completas en el contrato (7.4).

- `movimiento.js`: síntesis del acelerograma (dos componentes horizontales, semillas `s` y `s + 1`, **siempre con
  Δt = 0,005 s**; FFT radix-2 propia, ruido mulberry32 + Box-Muller) a partir de Mw, profundidad, distancia
  epicentral, Vs30 y semilla (`regimenPorProfundidad`, `sintetizar`); `intensidades` (PGA, PGV, PGD, Arias, D5-95),
  `espectroRespuesta` (Nigam y Jennings, 1969), `espectroFourier`, `espectroObjetivo`, `gmpe`, `espectroNSR10`,
  `filtrarYDiezmar` (calidad baja) y `avisos`.
- `modelo.js`: `armarModelo`, `rigidezLateral`, `rigidezPDelta`, `modos`, `amortiguamiento`, `gravedad`,
  `resumenModelo`, `infoElementos`.
- `integrador.js`: Newmark de aceleración promedio (γ = 1/2, β = 1/4) con Newton-Raphson completo
  (`analizar`, `analizarPorTramos`), `osciladorNewmark` (pruebas cerradas) y `riesgoEquipos`.
- `motor.js`: `crearMotor()` → `{ iniciar, movimiento, analizar, serieElemento, cancelar }`; reúne toda la lógica
  que usan el trabajador y el respaldo en el hilo principal (nadie la duplica en la vista).
- `trabajador.js`: Web Worker de módulo que solo traduce mensajes a llamadas de `motor.js`.
- Puede haber además `fft.js`, `azar.js`, `algebra.js` e `histeresis.js`.

Reglas de física y numérica (resumen; el detalle está en el contrato, 7.4):

- **Elemento de Giberson con su amortiguamiento:** giros de los extremos respecto a la cuerda
  `θ = f_e·M + θ0(w) + θp`. El momento equilibra la parte elástica y su amortiguamiento:
  `M = K_e·(e + a1·ė)` con `e = θ − θ0 − θp` y, con Newmark, `ė_{n+1} = (γ/(βΔt))·(e_{n+1} − e_n) + (1 − γ/β)·ė_n +
  Δt·(1 − γ/(2β))·ë_n`; el retorno se hace con `K̃_e = (1 + a1·γ/(βΔt))·K_e` más un término de historia. Lo mismo con
  la parte axial. `K_ef = K_t + (γ/(βΔt))·C_t + M/(βΔt²)`, con `a0·M` solo en los gdl del diafragma.
- **Retorno al estado admisible (2 × 2):** con el momento de prueba se prueban los 4 conjuntos activos (ninguno, i,
  j, ambos); en cada uno se resuelve `M_k − β_k = ±My_k` en las activas y se acepta el conjunto con `Δλ_k ≥ 0` en las
  activas y dentro de la superficie en las inactivas (es único). Tangente consistente `K_t = (K̃_e⁻¹ + diag(c_k))⁻¹`
  con `c_k = 1/H_k` en las activas.
- **Convergencia:** `‖R‖∞ ≤ tolerancia·max(‖P‖∞, 1 kN)` y `‖Δu‖∞ ≤ 10⁻⁹ m` (tolerancia 10⁻⁶, `max_iter` 20); si no
  converge, el paso se parte en dos hasta `max_subdiv` = 4 veces; si aun así no converge, error `no_converge` con
  resultados parciales. Paso `dt_s = 0,005 s` y `0,01 s` en calidad baja (registro filtrado a 20 Hz y diezmado);
  intensidades y espectros siempre con el registro de 0,005 s.
- **P-Delta lineal por nivel (E14):** para cada entrepiso k (altura `h_k`) y cada nivel `j ≥ k`, el peso `W_j`
  (`peso_sismico_kN`) aporta `−(W_j/h_k)·(b_xᵀb_x + b_yᵀb_y)` más `−(W_j/h_k)·(Jz_j/m_j)` sobre `(rz_k − rz_{k−1})²`,
  donde `b_x`, `b_y` dan la deriva del entrepiso k medida en el centro de masa `CM_j` con las ecuaciones de
  compatibilidad. Es la rigidez geométrica de 4 columnas articuladas con `W_j/4` en `CM_j ± r_j`,
  `r_j = √(Jz_j/m_j)` (así se modela en OpenSees). `K_PΔ` es constante. Por qué: con el retroceso, el centro de masa
  del piso 4 queda ≈ 6 m al norte del de los niveles 1-3 (estimación); la carga total por entrepiso no dice dónde actúa.
- **Entrada:** componente 1 y 2 giradas `angulo_deg`; fuerzas `−M·ι·üg` en los gdl del centro de masa.
- **Escala «nivel de diseño NSR-10»** (`escala: 'nsr10'`): factor que iguala la media del espectro de la media
  geométrica de las dos componentes entre `0,8·T1` y `1,2·T1` (de x y de y) con la del espectro de diseño con
  I = 1,5; la pasada de suelo se repite con `PGAr × f` hasta que el factor cambie < 1 % (máximo 10 vueltas).
- **Qué se evalúa en cada Δt** (no sobre la salida): envolventes, primera fluencia, bits de `rotulas` (O lógico
  entre dos salidas), derivas vectoriales y `riesgoEquipos`. Las series de salida (cada `dt_salida_s`) son para
  dibujar.
- **Deriva vectorial (E9):** en cada vértice del `contorno` del nivel de arriba de cada entrepiso,
  `Δ = √(Δx² + Δy²)/h` con la cinemática del diafragma de los dos niveles; se guarda el máximo por entrepiso, su
  envolvente y el vértice donde ocurre.
- **Balance de energía (Uang y Bertero, 1990, formulación relativa):** `E_entrada = −∫u̇ᵀMιüg dt = E_cinética +
  E_amortiguada + E_elástica + E_histerética + trabajo_PDelta`, con `E_amortiguada = ∫u̇ᵀa0·M·u̇ dt + Σe∫(a1·K_e·ė)ᵀė dt`,
  `E_histerética = Σ∫M dθp` (más, en la mampostería, el trabajo que no es `½·F·Δ`), `E_elástica = Σe ½(eᵀK_e e −
  e_gᵀK_e e_g) − F_g,cᵀ(u_c − u_c,g)` (más `½·F·Δ` de la mampostería) y `trabajo_PDelta = ½(uᵀK_PΔu − u_gᵀK_PΔu_g)`
  (negativo; igual a `½uᵀK_PΔu` cuando la gravedad no desplaza lateralmente). Control independiente:
  `E_deformación = ∫(F_r + F_PΔ)ᵀdu_m` sobre los gdl del diafragma desde el estado de gravedad debe ser
  `E_elástica + Σe∫(a1·K_e·ė)ᵀė dt + E_histerética + trabajo_PDelta`. Error de las dos igualdades < 1 % del máximo
  de `E_entrada` (con Newmark de aceleración promedio y la regla del trapecio las dos cierran a la tolerancia de Newton).
- **Equilibrio en la base (para T12, con los signos explícitos):** `Σ m·a_abs = −(V_elem + V_a0) + Σ_{j≥1}
  (W_j/h_1)·δ_1(CM_j)`, con `V_elem` el `cortante_basal` (cortante de los elementos del entrepiso 1, incluido su
  amortiguamiento) y `V_a0 = Σ a0·m·u̇`. El término de P-Delta suma: la gravedad empuja hacia donde se desplaza el
  edificio.
- **Equipos no anclados (`riesgoEquipos`):** aceleración absoluta en la posición del equipo
  `a = üg + (üx − (y − yc)·r̈z, üy + (x − xc)·r̈z)` del diafragma que lo sostiene (piso 1 y `BT` = suelo; piso p =
  nivel p − 1; `CUB` = último nivel; los de `cielo`, el nivel de arriba). `anclado`, `pared`, `cielo` y `en_nucleo`
  son **anclados** (fuerza `m·|a|max` que debe resistir el anclaje, sin los factores de A.9); `apoyado`,
  `ruedas_con_freno`, `ruedas_sin_freno` y `sobre` son bloques libres; `dentro` sigue a su contenedor. Bloque rígido
  en 2D: `ψ` = dirección de `a` en los ejes locales (con `rot_z`), `b_ψ = min(bx/|cos ψ|, by/|sen ψ|)`. Si
  `μ < b_ψ/h_cg` **desliza primero** (Coulomb; empieza cuando `|a| > μg`); si `μ > b_ψ/h_cg` **se balancea primero**
  (solo se marca el inicio, `|a| > g·b_ψ/h_cg`, sin calcular si cae); si los dos cocientes difieren menos de 10 %,
  `frontera` con los dos indicadores (Shenton, 1996). El régimen informado es el del instante de aceleración máxima.

## Mensajes del trabajador (E11; contrato, 7.5)

`web/js/scenes/torre/sismo.js` crea el trabajador con `new Worker(new URL('../../sismo/trabajador.js',
import.meta.url), { type: 'module' })` y le pasa URL **absolutas** (dentro del trabajador la base sería
`web/js/sismo/`). Sin `SharedArrayBuffer` (GitHub Pages no envía COOP/COEP).

| Dirección | Mensaje | Respuesta |
|---|---|---|
| ← | (al evaluar el módulo) | `{ tipo: 'cargado' }` |
| → | `{ tipo: 'iniciar', v: 1, id, url_estructura, url_amenaza, opciones: { histeresis, noEstructurales } }` | `{ tipo: 'listo', id, resumen, elementos, nodos, modos, amortiguamiento }` |
| → | `{ tipo: 'movimiento', id, params }` | `{ tipo: 'movimiento', id, registro: { dt, n, ax, ay, meta, intensidades, avisos }, espectro: { T, Sa_x, Sa_y }, fourier: { f, A_x, A_y }, gmpe: [{ nombre, peso, T, mediana_g, sigma_ln }], nsr10: { T, con_I, sin_I, umbral_dano } }` |
| → | `{ tipo: 'analizar', id, params, opciones }` | varios `{ tipo: 'progreso', id, fraccion, t_s }` (cada ≥ 250 ms) y al final `{ tipo: 'resultado', id, resultados }`; usa el registro del último `movimiento` si sus `params` son iguales |
| → | `{ tipo: 'serie_elemento', id, elemento }` | `{ tipo: 'serie_elemento', id, elemento, t, Mi, Mj, V, N, thp_i, thp_j, dc }` (copias de la historia interna; también después de `resultado`) |
| ← | errores | `{ tipo: 'error', id, codigo: 'datos' \| 'no_converge' \| 'interno', mensaje, detalle }` |

- `listo.resumen`: `{ niveles, porticos, nodos, elementos, gdl_dinamicos, gdl_condensados, masa_total_t, peso_kN, cm,
  centro_rigidez, excentricidad, sistema }`. `centro_rigidez[k]` es el punto del nivel k donde una fuerza lateral
  aplicada solo en ese nivel no lo hace girar (flexibilidad elástica condensada, sin P-Delta);
  `excentricidad[k] = centro_rigidez[k] − cm del nivel k` (m).
- `listo.elementos` (`infoElementos`): `[{ id, tipo, portico, nivel, fisico, i, j, xyz_i, xyz_j, seccion }]`;
  `listo.nodos`: `[{ id, portico, xyz }]`, en el orden de la estructura.
- `listo.modos`: `{ periodos_s, masa_participativa: { x, y, rz }, formas, T1x, T1y }` con los primeros `min(12, 3N)`
  modos; `formas[r]` tiene `3N` valores (ux, uy, rz por nivel) normalizados con `φᵀMφ = 1` y la componente de mayor
  valor absoluto positiva; `T1x` y `T1y` son los períodos de mayor masa participativa en x y en y.
- Las series de `movimiento` y de `serie_elemento` viajan en `Float32Array` y sus búferes se transfieren. Unidades de
  `serie_elemento`: `Mi`, `Mj` en kN·m (momentos de extremo antihorarios), `V` en kN (el extremo de mayor valor
  absoluto, con la convención de arriba), `N` en kN (tracción +), `thp_i`, `thp_j` en rad, `dc` como **cociente**
  (no × 100).
- **Cancelar:** `analizar` corre síncrono dentro del trabajador; la vista cancela con `worker.terminate()` y crea
  otro con un `iniciar` nuevo. El respaldo en el hilo principal (si `new Worker` lanza, si llega `error` antes de
  `listo` o si `cargado` no llega en 3 s) usa `analizarPorTramos` de `motor.js` cediendo cada ≈ 12 ms y revisa la
  `senal` (`AbortSignal`) entre tramos; mismos resultados, bit a bit, en el mismo navegador.
- **Trabajador simulado:** `scripts/fixtures/torre/trabajador_simulado.js` responde estos mismos mensajes con los
  fixtures del Anexo A (ver «Fixtures»), para desarrollar la vista sin el motor.

## Resultados del motor (E11; contrato, 7.6)

`nt` = pasos de salida (`dt_salida_s`, 0,02 s por defecto), `N` = niveles, `nE` = elementos, `nN` = nodos de
pórtico, `nP` = pórticos (todos en el orden de la estructura). Orden de los arreglos: tiempo primero (`[i_t][…]`).
**Unidades de D/C:** los arreglos `dc*` por paso van en `Uint8Array` como cociente × 100 (255 = ≥ 2,55); la
envolvente `dc_max` va en `Float32Array` como **cociente** (0,12 = 12 %).

| Campo | Tipo | Contenido |
|---|---|---|
| `version` | número | 1 |
| `id` | texto o número | el `id` del mensaje `analizar` |
| `params` | objeto | `{ Mw, profundidad_km, distancia_epicentral_km, vs30_m_s, semilla, regimen? }` del movimiento |
| `opciones` | objeto | `{ dt_s, dt_salida_s, duracion_s, calidad, angulo_deg, escala }` usadas (`equipos` no se repite) |
| `origen_registro` | objeto, opcional | Solo si el registro **no** es la síntesis de `params` (pruebas, fixtures, registros externos): `{ tipo, descripcion }` |
| `duracion_calculo_ms`, `factor_escala` (null si la escala es un número), `iteraciones_escala` (0 si no es `nsr10`) | números | |
| `amortiguamiento` | objeto | `{ a0, a1, periodos_ancla_s: [Ti, Tj], xi_modos: Float32Array(min(12, 3N)) }` |
| `t` | `Float32Array(nt)` | s, desde 0 |
| `ag` | `Float32Array(nt·2)` | aceleración del suelo x, y (m/s²), ya girada y escalada |
| `u` | `Float32Array(nt·N·3)` | `ux`, `uy` (m) y `rz` (rad) del centro de masa, relativos al suelo |
| `a_abs` | `Float32Array(nt·N·3)` | aceleraciones absolutas del centro de masa (m/s², rad/s²) |
| `giros` | `Float32Array(nt·nN)` | θ de cada nodo en su plano (rad), medido desde la posición sin deformar (incluye la gravedad) |
| `v_nodos` | `Float32Array(nt·nN)` | desplazamiento vertical (m), también desde la posición sin deformar |
| `dc`, `dc_flexion`, `dc_cortante`, `dc_rotacion` | `Uint8Array(nt·nE)` cada uno | cociente × 100 en el instante de salida: `max(\|M_i\|, \|M_j\|)/Mn_e`, `max(\|V_i\|, \|V_j\|)/Vn_e`, `max(\|θp_i\|, \|θp_j\|)/θp_IO`; `dc` = máximo de los tres |
| `rotulas` | `Uint8Array(nt·nE)` | bits (O lógico de todos los Δt desde la salida anterior): 1 fluencia en i, 2 fluencia en j, 4 θp_i > IO, 8 θp_j > IO, 16 θp_i > LS, 32 θp_j > LS, 64 θp (i o j) > CP, 128 V > Vn_e. «Fluencia» = la rótula tuvo flujo plástico (estaba en el conjunto activo) en ese Δt |
| `thp` | `{ elementos: Int32Array(k), valores: Int16Array(nt·k·2) }` | rotación plástica (i, j) de los k elementos que fluyen alguna vez, en 10⁻⁵ rad; `elementos` en orden creciente |
| `derivas` | `Float32Array(nt·N·2)` | deriva máxima (valor absoluto) del entrepiso sobre todos los pórticos, componentes x e y |
| `derivas_vector` | `Float32Array(nt·N)` | máximo de `√(Δx² + Δy²)/h` sobre los vértices del contorno de cada entrepiso |
| `derivas_porticos_env` | `Float32Array(nP·N)` | envolvente (valor absoluto) por pórtico y entrepiso; 0 si el pórtico no llega a ese entrepiso |
| `cortante_basal` | `Float32Array(nt·3)` | Vx, Vy (kN): fuerza que resisten los elementos del entrepiso 1 (incluido su amortiguamiento y la mampostería sin aislar; sin `a0` ni P-Delta), positiva con deriva positiva; y momento torsor (kN·m) de esas fuerzas alrededor del eje vertical que pasa por el centro de masa del nivel 1 |
| `energia` | `Float32Array(nt·6)` | entrada, cinética, elástica, amortiguada (`a0` más parte elástica), histerética y trabajo_PDelta (kJ), desde el estado de gravedad |
| `envolventes` | objeto de `Float32Array` | `u_max (N·3)`, `deriva_max (N·2)`, `t_deriva_max (N·2)`, `deriva_vector_max (N)`, `punto_deriva_vector (N·2: x, y del vértice)`, `t_deriva_vector_max (N)`, `a_abs_max (N·3)`, `dc_max (nE, cociente)`, `t_dc_max (nE)`, `gobierna (nE: 0 flexión, 1 cortante, 2 rotación)`, `Mi_max (nE)`, `Mj_max (nE)`, `V_max (nE)`, `N_min (nE)`, `N_max (nE)`, `thp_max (nE·2)`, `t_primera_fluencia (nE·2; −1 si no fluye)`; los máximos son de valor absoluto salvo `N_min` y `N_max`, y todos se toman en cada Δt |
| `muros_mamposteria` | arreglo | `{ id, aislado, deriva_max, estado: 'sin_dano'\|'leve'\|'moderado'\|'extenso'\|'colapso' }`, uno por muro de la estructura; `estado` = el último estado de daño cuya deriva se alcanzó |
| `equipos` | arreglo | `{ unidad, anclaje, regimen: 'desliza'\|'balancea'\|'frontera'\|'anclado', a_max_m_s2, desliza, deslizamiento_max_m, deslizamiento_final_m, inicia_balanceo, razon_vuelco, fuerza_anclaje_kN }`. `razon_vuelco` = aceleración que recibe el equipo / `(g·b_ψ/h_cg)`: con `desliza`, la que deja pasar la fricción, `min(\|a\|max, μg)`; si no, `\|a\|max`; null si está anclado. `fuerza_anclaje_kN` solo en los anclados |
| `calidad_numerica` | objeto | `{ pasos (Δt calculados, con las subdivisiones), iteraciones_promedio, subdivisiones, no_convergidos, error_energia_max, error_deformacion_max, indice_estabilidad_max }`; `indice_estabilidad_max` = máximo por entrepiso y dirección de `P_k·Δ_k,max/(V_k,max·h_k)` (NSR-10 A.6.2.3 con las envolventes: `P_k` peso de los niveles de encima, `Δ_k,max` deriva máxima del centro de masa, `V_k,max` cortante máximo del entrepiso) |

Tamaño típico (cálculo propio del contrato): 40 s, `nt = 2.000`, `nE ≈ 420`, `nN ≈ 300`, `N = 4`: ≈ 9,4 MB a
12,8 MB. La historia interna del trabajador (≈ 23 MB) no se transfiere.

`scripts/sismo/validar_resultado.mjs` comprueba tamaños, tipos (exactos si los arreglos son tipados; que quepan si
vienen de JSON), unidades y rangos de cualquier `Resultados`, la coherencia entre series y envolventes, el balance
de energía, los estados de los muros, los equipos y la serie de un elemento; y que la estructura cumpla el esquema
y `theta_y` ± 1 %.

## Pruebas: `node scripts/sismo/test_motor.mjs` (contrato, 7.8)

**Desviación acordada del contrato:** las pruebas no están en un solo archivo sino en módulos
`scripts/sismo/pruebas/*.mjs`, uno por módulo del motor, para que varios equipos las escriban en paralelo sin tocar
el mismo archivo. `test_motor.mjs` es el ejecutor: importa todos los módulos (salta los `_*.mjs`, que son
ayudantes), corre cada prueba, imprime su error y su tolerancia y al final el estado de T1-T22 (con T15b y T15c).
Sale con código 1 si una prueba falla, si un módulo no carga, si un id se repite o si falta alguna prueba del
contrato; con `--parcial` (o `--solo T7,F2`) las que faltan no hacen fallar; `--lista` dice qué prueba está en qué
archivo.

Cada módulo exporta `pruebas`, una lista de `{ id, nombre, fn }`. `fn` (puede ser `async`) devuelve un caso o una
lista de casos `{ caso?, error, tolerancia, ok?, detalle? }` (si falta `ok`, pasa cuando `error ≤ tolerancia`), o
lanza una excepción para fallar. Ayudantes en `pruebas/_util.mjs` (`leerJSON`, `errorRelativo`, `errorMaximo`,
`caso`, `comprobar`).

```js
// scripts/sismo/pruebas/integrador.mjs
import { osciladorNewmark } from '../../../web/js/sismo/integrador.js';
import { caso } from './_util.mjs';
export const pruebas = [
  { id: 'T1', nombre: 'Oscilador libre sin amortiguar', fn: () => { /* … */ return caso('Δt = T/20', error, 1e-4); } },
];
```

| Archivo | Pruebas |
|---|---|
| `pruebas/integrador.mjs` | T1-T7, T12, T21 |
| `pruebas/modelo.mjs` | T8-T11, T22 |
| `pruebas/movimiento.mjs` | T13-T15, T15b, T15c, T16, T19, T20 |
| `pruebas/motor.mjs` | T17, T18 |
| `pruebas/datos.mjs` | F1 fixtures del Anexo A, F2 `amenaza.json` idéntico en números a la investigación, F3 el validador detecta errores sembrados, F4 el trabajador simulado responde los mensajes |

Las referencias y tolerancias de T1-T22 son las del contrato (7.8, con la tabla del lazo de T7). T18 corre la
estructura real y usa `validarResultado` de `validar_resultado.mjs`.

## Validación con OpenSees: `python3 scripts/sismo/validar_opensees.py` (contrato, 7.9)

Requisitos en `scripts/sismo/requisitos_validacion.txt` (`openseespy==3.8.0`, `numpy`); no corre en CI: el resultado
se versiona en `data/sismo/validacion_opensees.json`. `node scripts/sismo/exportar_caso.mjs <escenario> <salida.json>`
escribe el registro (mismo `dt`), `a0`, `a1` y el modelo de referencia. Réplica de la idealización: nodos propios
por pórtico como esclavos de `rigidDiaphragm 3` sin restringir en ellos `ux`, `uy` ni `rz` (solo el giro fuera del
plano); `ElasticTimoshenkoBeam` con `I·factor_fisuracion`; brazos rígidos como elementos 10³ veces más rígidos (no
`rigidLink`); rótulas `zeroLength` con `Steel01(My_e, k0 = 10³·k_e, b = α/10³)` sin Rayleigh; `rayleigh(a0, 0, a1, 0)`;
P-Delta con 4 pilas de columnas articuladas de gravedad por nivel; gravedad con `loadConst -time 0.0`. Casos de
control antes de la torre y criterios en el contrato (7.9).

## Fixtures (Anexo A.3 y A.4 del contrato)

En `scripts/fixtures/torre/`:

- `estructura_min.json`: cubo de prueba de 2 pisos y 1 vano por dirección (5,0 × 5,0 m; entrepisos de 3,0 m),
  4 pórticos (`X-1`, `X-2`, `Y-A`, `Y-B`) con 6 nodos y 6 elementos cada uno y un muro de mampostería sin aislar
  (`M-X1-1`, nivel 1 de `X-1`). Valores de prueba, no de diseño. `theta_y` y `theta_y_e` van con 4 cifras
  (0,001616 y 0,003946 rad): con 0,0039 la viga quedaba a −1,16 % de su fórmula, fuera de ± 1 %.
- `resultado_min.json` y `serie_elemento_min.json` (`C-A1-1@X`): `Resultados` de 3 pasos de salida (0; 0,02;
  0,04 s) calculados **sobre `estructura_min.json`** con `scripts/sismo/referencia_min.py` (Python con numpy; el
  modelo no lineal completo con Newmark y Newton-Raphson; lo que simplifica está escrito al principio del archivo).
  El registro es un pulso de prueba ×25 (`origen_registro`), porque en 0,04 s ningún acelerograma sintético hace
  fluir nada; `params` conserva el escenario por defecto para que la vista tenga qué mostrar. Trae rótulas que
  fluyen, un equipo que desliza, uno que empieza a balancearse, uno anclado y el muro con daño. En la ola 2 se
  regeneran con el motor y se vuelven a pasar por `validar_resultado.mjs`.
- `trabajador_simulado.js`: responde `cargado`, `listo`, `movimiento`, `resultado` y `serie_elemento` con esos
  archivos y con el bloque `GENERADO` que escribe `referencia_min.py` (modos, registro, espectros, series de los
  24 elementos). Acepta `url_fixtures` en `iniciar` y `simular: { retardo_ms, error }` en cualquier mensaje.

```bash
node scripts/sismo/validar_resultado.mjs scripts/fixtures/torre/resultado_min.json
python3 scripts/sismo/referencia_min.py --verificar   # con numpy: recalcula y compara byte a byte
node scripts/sismo/test_motor.mjs --solo F1,F2,F3,F4
```

## Cambios de la versión 2

| # | Cambio | Dónde quedó |
|---|---|---|
| E1 | Elemento `muro_concreto` con aletas efectivas, `lp`, `My_pos`/`My_neg` y rótula solo en la base | Campos; Reglas |
| E2 | `brazo_rigido_m` y longitud flexible `L_f` | Campos; Reglas |
| E3 | `My_pos_kNm` y `My_neg_kNm` | Campos; Signos y convenciones |
| E4 | `w_gravedad_kN_m`, `carga_kN` y gravedad primero | Campos; Idealización; Reglas |
| E5 | `resortes[].aislado` | Campos |
| E6 | Ejes con nombre, ids y `fisico` | Unidades y ejes; Convención de ids |
| E7 | `niveles[].contorno` | Campos |
| E8 | Amortiguamiento de la parte elástica con `periodos_ancla_s` (**Cambio de regla**) | Amortiguamiento |
| E9 | Límites del umbral de daño y deriva vectorial | Campos; Motor; Resultados |
| E10 | `interaccion_PM` (fase 2) | Campos |
| E11 | Resultados del motor y mensajes del trabajador | Mensajes; Resultados |
| E12 | `s = x` en pórticos X y `s = y` en pórticos Y | Unidades y ejes |
| E13 | `ejes`, `sistema`, `prediseno`, `generado_por`, `fecha` | Campos; Prediseño de la torre |
| E14 | P-Delta por nivel con el peso y el centro de masa de cada nivel; `P_sobre_entrepiso_kN` informativo | Campos; Motor |
| E15 | Transición de profundidad de 40 a 70 km | amenaza.json |
| E16 | Propiedades esperadas y límites IO, LS y CP; demanda/capacidad con `Mn_e`, `Vn_e` y `θp_IO` (**Cambio de regla**) | Campos; Reglas |
