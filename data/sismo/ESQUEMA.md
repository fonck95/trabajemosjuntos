# Simulación sísmica: formato de los modelos y del motor

Este documento fija el contrato entre los modelos estructurales (`data/sismo/*_estructura.json`), la amenaza
(`data/sismo/amenaza.json`), el motor de cálculo en JavaScript (`web/js/sismo/`) y la validación con OpenSees
(`scripts/sismo/validar_opensees.py`). Quien cambie el formato actualiza este documento.

> **Versión 2 (23-oct-2026).** Aplica los cambios E1 a E16 del contrato de integración de la torre
> (`data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md`, sección 7.1). Se **agregan** campos opcionales,
> la sección de resultados y la de mensajes; ningún campo que ya existía cambia de significado. Dos **reglas** sí
> cambian y se marcan como «Cambio de regla»: la demanda/capacidad que se muestra (E16) y el anclaje del
> amortiguamiento (E8). La tabla del final dice dónde quedó cada cambio.
>
> **Versión 2.1 (24-oct-2026).** Contrato 17 (prevalece sobre el 7.2): la torre se prediseña en zona de amenaza
> intermedia con capacidad moderada de disipación (DMO) y el archivo de la estructura trae además la cimentación, el
> despiece del refuerzo de cada elemento y las cantidades (ver «Prediseño de la torre», con las correcciones al
> contrato: criterio del sistema dual, espectro del umbral de daño, muros partidos por las puertas y sismo en la
> cimentación).

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
- Rigidez axial `EA/L_f` en cada copia de una columna o muro (limitación conocida de TABS: la columna compartida suma
  su rigidez axial en los dos pórticos). Se usa la longitud flexible porque los brazos rígidos del nudo tampoco se
  acortan (así es la réplica de OpenSees del 7.9, con brazos 10³ veces más rígidos); sin brazos es `EA/L`. Las vigas
  no se deforman axialmente: sus dos extremos están en el mismo diafragma.
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
- Carga del vano (E4): giros de la viga simplemente apoyada `θ0 = c·[−1, +1]` con `c = w·L_f³/(24EI)`; la carga
  sobre los brazos rígidos pasa directo a los nudos. **Corrección física (ola 1):** el contrato (7.4) y la versión
  anterior de este esquema sumaban `w·L_f/(2·G·Av)`. Ese término es la pendiente que el cortante le da al eje
  deformado en el apoyo, no el giro de la sección, y los θ del elemento (los de `f_e`) son giros de sección: por
  trabajo virtual, el aporte del cortante es `∫V_w·v_i/(G·Av) dx`, con `v_i = 1/L_f` constante (cortante de un momento
  unitario en un extremo) y `V_w` antisimétrico, así que vale 0. Comprobación independiente: en una viga de Timoshenko
  empotrada con carga uniforme, `φ(0) = φ(L) = 0` exige `∫M dx = 0` y los momentos de empotramiento son `w·L²/12` sin
  importar `G·Av`; con el término de más no lo serían. Desde la ola 2 el cálculo de referencia
  (`referencia_min.py`) y los fixtures del Anexo A.4 (regenerados con el motor) usan la regla corregida (en el cubo
  el giro de gravedad de los nudos cambió ≈ 1 % respecto a los fixtures de la ola 0).
- Rótulas: concentradas en los extremos de vigas y columnas y **solo en la base** de los muros de concreto (E1:
  en el tramo de abajo de cada muro, el elemento cuyo nodo i no es el nodo j de otro tramo del mismo muro; los tramos
  de encima son elásticos, como pide el diseño por capacidad de muros), modelo de Giberson (resorte rotacional en serie con el elemento elástico). Rígidas hasta la fluencia **esperada**
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
- **Las anclas del archivo valen solo para el modelo con los muros de mampostería como dice el archivo** (corrección
  al contrato, revisión A6). `periodos_ancla_s` sale del modelo con cada muro `aislado` como está escrito; con
  `noEstructurales: 'confinados'` («Sin aislar») y algún muro que en el archivo está aislado, el sistema dinámico es
  otro (torre: T1 = 0,285 s en lugar de 0,456 s; T2 = 0,244 s; T3 = 0,218 s) y el motor aplica la regla automática
  sobre los modos del modelo analizado. `regla` dice cuál se usó y por qué. Con las anclas del archivo, la torre
  «sin aislar» quedaba con ξ = 3,2 %, 2,8 % y 2,6 % en sus tres modos fundamentales, y con eso la deriva salía
  +30 % y la aceleración de piso +15 a +24 % por encima de la del modelo con su propio amortiguamiento: el contraste
  de E5 (aislados frente a sin aislar) quedaba sesgado.
- `C = a0·M + a1·Σe K0,e`, donde `K0,e` es la rigidez inicial de la **parte elástica** de cada viga, columna y muro
  (flexión, cortante y axial). **Las rótulas nunca amortiguan** (evita el amortiguamiento espurio después de la
  fluencia, Charney 2008), y así OpenSees con `rayleigh(a0, 0, a1, 0)` y `zeroLength` sin Rayleigh es réplica exacta.
  La mampostería tampoco (mismo argumento: se fisura en `dcr` y su rigidez inicial dejaría de representarla).
- **a0 y a1 con ξ exacto en las dos anclas** (corrección al contrato, revisión A6). Con `φ_r` normalizado a la masa,
  `ξ_r = (a0 + a1·k_r)/(2ω_r)`, `k_r = φ_rᵀ·K_el·φ_r`. La fórmula del contrato, `a0 = 2ξ·ωi·ωj/(ωi + ωj)` y
  `a1 = 2ξ/(ωi + ωj)`, supone `k_r = ω_r²`, es decir, que toda la rigidez amortigua; con la mampostería trabajando
  (≈ 60 % de la rigidez inicial de la torre «sin aislar», (0,456/0,285)² ≈ 2,56) daba ξ1 = 4,55 % aun con las
  anclas bien puestas. Con `ρ(ω) = k/ω²` (fracción de la rigidez modal que amortigua), imponer ξ en ωi y ωj da
  `a0 + a1·ρi·ωi² = 2ξ·ωi` y `a0 + a1·ρj·ωj² = 2ξ·ωj`, es decir
  `a1 = 2ξ·(ωj − ωi)/(ρj·ωj² − ρi·ωi²)` y `a0 = 2ξ·ωi − a1·ρi·ωi²` (con `ρ = 1` es la fórmula de siempre). Si un
  ancla no cae en un modo (`0,2·T1`), `ρ` se interpola linealmente en `ln ω` entre los dos modos vecinos (fuera de
  su rango, la del modo extremo). En la torre con los muros aislados `ρ ≈ 1,004` (P-Delta) y ξ1 pasa de 5,004 % a
  5 %; «sin aislar» queda ξ = 5,00 / 4,29 / 3,92 % en los modos 1 a 3 (los modos 2 y 3 tienen más mampostería que el
  1: con dos parámetros no se puede fijar más). Lo mismo hacen `referencia_min.py` (prueba R0) y el prediseño
  (`amortiguamiento_y_anclas`), y lo prueba S5.
- `modos: [1, 3]` (la forma anterior) sigue aceptándose, pero `periodos_ancla_s` manda si están los dos, y los
  validadores avisan si se usa `modos`. Por qué: en el modelo pseudotridimensional los modos 1 a 3 suelen ser los
  tres fundamentales (x, y, torsión), con ω3 ≈ 1,2-1,5·ω1, y anclar en 1 y 3 sobreamortigua los modos altos (con
  ω3 = 1,3·ω1: ξ ≈ 7,5 % en 3ω1, 11 % en 5ω1 y ≈ 22 % en 10ω1; cálculo propio del contrato) y baja las aceleraciones
  de piso con las que se evalúa la dotación.
- El motor publica el ξ efectivo de los primeros `min(12, 3N)` modos: `ξ_r = φ_rᵀ(a0·M + a1·K_el)φ_r / (2ω_r)` con
  modos normalizados a la masa y `K_el` la rigidez condensada de la parte elástica de los elementos (sin P-Delta y
  **sin la mampostería**, que no lleva amortiguamiento de Rayleigh). Como dentro de cada pórtico el amortiguamiento es
  proporcional a la rigidez de la parte elástica, condensarlo es exacto: `(1 + a1·d/dt)(K_cc·u_c + K_cd·u_d) = 0`
  da `u_c = −K_cc⁻¹·K_cd·u_d`, y la matriz de amortiguamiento condensada es `a0·M + a1·K̂_el`.

### Prediseño de la torre (`sistema`, `prediseno`, `cimentacion`, `refuerzo` y `cantidades`; E13 y contrato 17)

`data/sismo/torre_hospital_estructura.json` lo genera `scripts/sismo/estructura_torre.py` (Python 3.12, solo biblioteca
estándar, determinista byte a byte; `--verificar` regenera, compara e imprime los chequeos, y sale con 1 si algo
difiere o falla; `--informe` imprime además el detalle). **Norma (contrato 17, que prevalece sobre el 7.2):** zona de
amenaza sísmica **intermedia** (Aa = Av = 0,15) y capacidad **moderada** de disipación de energía (**DMO**); la revisión
de la exigencia para el grupo IV está en `prediseno.verificacion_nsr10` (no cambia la capacidad de disipación; sí pide
I = 1,5, el umbral de daño, el desempeño superior de los no estructurales y la supervisión técnica; por confirmar con el
texto). El prediseño agrega criterios más exigentes que el mínimo DMO, todos declarados: confinamiento Ash de DES en
columnas, cortante por capacidad con `Mpr` en vigas, columnas y muros, columna fuerte-viga débil en todos los nudos, sin
irregularidad torsional extrema y cimentación revisada con el sismo de capacidad.

**Correcciones al contrato (escritas también en la respuesta de la tarea):**

- **Paso 0 (dual o combinado).** El contrato tomaba la fracción del cortante que los pórticos resisten en el modelo
  elástico (≥ 25 % → dual). La NSR-10 (A.3.2.1.4) no clasifica por esa fracción: exige que el pórtico resistente a
  momentos, esencialmente completo y capaz de llevar las cargas verticales, **se diseñe** para resistir por sí solo al
  menos el 25 % del cortante sísmico de diseño. `sistema.fraccion_cortante_porticos` guarda la fracción elástica
  (informativa: 18 % en x y 28 % en y en el entrepiso 1) y el diseño usa la envolvente del modelo completo y del modelo
  de solo pórticos con el 25 % de la FHE (con su torsión accidental): el sistema es **dual** (Tabla A.3-4, fila de muros
  de concreto DMO con pórticos DMO: R0 = 6,0 y Ω0 = 2,5, por confirmar).
- **Espectro del umbral de daño.** Con ξ = 2 % (A.12.3): meseta `3,0·Ad·Fa` hasta `TC = 0,5·Fv/Fa` y `1,5·Ad·Fv/T`
  después (la forma de la NSR-98, 3,0·Ad y 1,5·Ad·S/T, con los coeficientes de sitio de la NSR-10: 3,0 = 2,5·1,2 y
  1,5 = 1,2·1,25 son la meseta y la rama del espectro de diseño llevadas de 5 % a 2 %). Texto exacto por confirmar; si la
  meseta fuera 3,0·Ad sin Fa, esta queda del lado seguro. La curva `nsr10.umbral_dano` del mensaje `movimiento`
  (`motor.js`, con `espectroUmbralDano` de `movimiento.js`) es esta misma (unificada en la revisión A6; antes usaba
  la forma del 5 %, 2,5·Ad·Fa, entre 17 % y 20 % más baja).
- **Muros con las puertas de las escaleras.** Las puertas de las escaleras (planta de B) parten los muros en x = 3,1:
  cada muro en y es el machón de 6,5 m que queda entre la jamba y el otro extremo, con la aleta del muro en x de ese
  extremo; el machón corto del otro lado de la puerta (0,7 m) es aleta del muro en x de su esquina. El prediseño supone
  las puertas apiladas en x = 3,1 (y = 15,3 al norte, y = −6,3 al sur) en los cuatro pisos.
- **Cimentación con el sismo.** La capacidad geotécnica de los pilotes se revisa con las combinaciones de servicio de
  B.2.3 y los factores de seguridad de H.4.7-1 (3,0 estático; 1,5 con el sismo); el sismo de capacidad (`Ecap`: Ω0·E
  sin pasar de lo que pueden entregar muros y columnas, Mpr y Ve, ni de la suma de los cortantes de capacidad de las
  vigas en la carga axial de las columnas) se usa para el refuerzo y el anclaje de los pilotes y se informa en las
  reacciones, pero no para la capacidad del suelo (un núcleo que llega a la capacidad última de sus pilotes se mece y
  eso limita la demanda; ASCE/SEI 41-17 8.4 y ASCE/SEI 7-16 12.13.5 tampoco piden Ω0 para el suelo).

Campos agregados (todos opcionales para el motor, que no los usa salvo lo dicho):

| Campo | Dónde | Qué es |
|---|---|---|
| `xyz` | nodos | Coordenadas `[x, y, z]` del nodo (para la vista y el modelo BIM; el motor las recalcula con `s`, `coordenada` y `z`) |
| `ejes.x[].auxiliar` | `ejes` | Eje auxiliar `N` (x = 3,1, cara occidental de los núcleos); no es línea de pórtico |
| `detalle_masa` | niveles | Masa por categoría **en t** (losa, vigas, columnas, muros de concreto, acabados e instalaciones, divisorios, fachada, escaleras, mampostería de núcleos, casetas, equipos de cubierta, `viva_25pct`) |
| `aletas` | secciones de muro | Partes de la sección distintas del alma: `[{u0, u1, ancho_m, de}]` en la coordenada `u` del muro (aleta efectiva o columna de borde); reemplaza la forma `{lado, ancho_efectivo_m, espesor_m}` del ejemplo |
| `Mn_pos_kNm`, `Mn_neg_kNm`, `phiMn_pos_kNm`, `Mpr_pos_kNm`, `Mn_e_pos_kNm`, `momento_curvatura_neg`, `refuerzo`, `b_ala` | secciones | Valores del otro sentido de flexión y el refuerzo resumido; `Mn_kNm`, `phiMn_kNm`, `Mpr_kNm` y `Mn_e_kNm` son los del momento negativo (el mayor) en vigas |
| `portico` | — | No se escribe en los resortes (la línea la dan `direccion` y `coordenada`) |

Bloques de la raíz:

- `sistema` (paso 0) y `diseno` (Aa, Av, Ad, Fa, Fv, I, zona, `capacidad_disipacion: "DMO"`, Ta, Cu·Ta, Sa, R, Ω0, Vs).
- `prediseno`: `metodo` y `metodo_secciones`; `historial_de_ajustes` (cada paso desde el punto de partida del
  presupuesto con su período, cocientes de torsión, deriva, umbral de daño y R: así se ve por qué se cambiaron las
  secciones); `dimensiones_adoptadas`; `eleccion_muros` (paños activos, longitudes, todos los paños de núcleo con su
  material, por qué y las notas de las aletas); `R` con φa, φp, φr y su justificación; `redundancia` (prueba de
  remoción de cada muro); `irregularidades` (1aP/1bP con el cociente por entrepiso y Ax, 3A, 1A y 2A);
  `participacion_porticos`; `periodos` (12 modos con masa participativa, T1x, T1y, Ta, Cu, Cu·Ta y la fila de la tabla);
  `cortante_basal` (FHE por dirección con Sa, k, W, Vs, Vs/R y fuerzas por nivel; modal con el factor de ajuste);
  `derivas_vector` (por entrepiso, con el vértice y la combinación 100 % + 30 %), `derivas_porticos` y
  `derivas_umbral_dano` (aislados y con la mampostería adherida, con rigidez secante a 0,2 %); `estabilidad`;
  `centro_rigidez` (por nivel, con la excentricidad); `amortiguamiento` (períodos ancla, a0, a1, ξ de 12 modos);
  `columna_fuerte_viga_debil` (cada columna y plano, los de cubierta exentos); `cortante_por_capacidad` (vigas,
  columnas y muros: Ve, φVn, Ωv); `cuantias`; `verificacion_nsr10`; `chequeos` (lista `{id, descripcion, valor, limite,
  cumple, fuente, detalle?}`: todos deben cumplir).
- `cimentacion` (17.2): `suelo_supuesto` (estimación con su fuente), `pilote` (D, L escogido por el menor total de
  metros, capacidades y factores de seguridad, `estudio_de_largo`), `reacciones` en la base por apoyo (D, L, Lr, E y
  Ecap), `grupos` (dados, dados combinados y losas de pilotes de los núcleos, con las reacciones extremas por tipo de
  combinación y el diseño de sus pilotes), y la geometría con el refuerzo para el modelo BIM: `pilotes` (posiciones,
  cotas de cabeza y punta, canasta en dos tramos y espiral), `dados` (caja en planta, cotas, parrillas),
  `vigas_amarre`, `contrapiso`, `fosos` y `cisternas`. Cotas `z` desde el piso terminado del piso 1.
- `refuerzo` (17.3): `convenciones` (barras N.º 3 a N.º 8 de NTC 2289, recubrimientos, ganchos y traslapos) y el
  despiece de **cada** elemento: `columnas` (por columna física y piso: barras por cara, traslapo, anclaje, estribos y
  ganchos suplementarios en lo, en el centro y en el nudo), `vigas` (corridas y bastones superiores con su largo desde
  la cara, inferiores y del vano, estribos en 2h y en el centro; incluye las vigas banda columna-muro que no están en el
  modelo), `muros` (por piso: cortinas, bordes y planta), `losas` (por paño: nervios con su refuerzo, riostras, malla)
  y `escaleras`; cada uno con `texto` (la etiqueta de la vista: «12 N.º 7», «E N.º 4 c/0,10 en lo = 0,60 m»), `kg` y
  `m3`.
- `cantidades`: m³ y kg por tipo con su cuantía, pilotes (número, metros, kg/m) y la comparación con los ítems de
  `presupuesto.json` (capítulos 2 y 3) con el efecto en el costo directo; el presupuesto no se edita.

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
  régimen, `avisos` advierte «intraplaca con h < 40 km» o «cortical con h > 60 km». La banda **no elimina** el
  contraste entre regímenes (≈ 3 veces en el PGA): lo **reparte** en 30 km. Por eso, sola, no basta (ver la regla
  siguiente). Con la banda y Δσ(h), el cociente de la mediana del PGA entre h + 1 y h queda dentro de 0,85-1,18 para
  Mw 5 a 7 y Repi 0 a 200 km (T19), y la tendencia con h sigue a la de las GMPE (T19b).
- **Caída de esfuerzos intraplaca según la profundidad (regla del motor, revisión A6; desviación de E15, sin cambiar
  números de este archivo).** `Δσ_i(h) = Δσ_ref·exp((3/2)·θ̄·(min(h, h_c) − h_c))`, con `Δσ_ref = 800 bar`
  (`intraplaca_profunda.delta_sigma_bar`, calibrado solo con focos de 100 a 150 km), `θ̄ = 0,0135/km` y
  `h_c = 120 km`. Deducción: `θ̄` es la media de las pendientes de profundidad del PGA de las dos GMPE con que se
  calibró `Δσ_ref` (BC Hydro 2016, `fdepth = θ11·(min(Zh, 120) − 60)`, `θ11 = 0,013`; Zhao et al. 2006,
  `e·(min(h, 125) − 15)`, `e = 0,0141`), y `h_c` es el tope de BC Hydro (Zhao usa 125 km). En alta frecuencia
  (`f ≫ f0`) la amplitud de Fourier de Brune es `∝ M0·f0² ∝ M0^(1/3)·Δσ^(2/3)`; para que `d ln A/dh = θ̄` hace falta
  `d ln Δσ/dh = (3/2)·θ̄`. Por qué: con Δσ fijo desde 40 km, a igual distancia epicentral el PGA mediano subía 2,1 a
  2,4 veces entre h = 40 y 70 km, tenía su máximo en 70 km y bajaba después, al revés de las GMPE (que suben despacio
  hasta 120 km); a 70 km la simulación quedaba 1,5 a 2,7 veces sobre sus propias GMPE (Mw 6,2, Repi 92 km:
  ln(sim/GMPE) = +0,49 en el PGA, +0,77 en Sa(0,5) y +0,98 en Sa(1,0)). Con Δσ(h), en Repi 92 y 200 km el residuo
  del PGA queda entre −0,24 y −0,05 para h de 50 a 150 km (T19b, tolerancia ±0,35). Para h ≥ 120 km (el nido,
  150 km) Δσ = 800 bar: `nido_2015` y T15 no cambian. `meta.delta_sigma_bar` (y el de cada término) es el Δσ ya
  ajustado. La aplican igual `movimiento.js` y `estocastico.py` (T15b).

### Movimiento del suelo (`movimiento.js`; decisiones de implementación)

Los 12 pasos de `notas_para_implementar` se siguen tal cual, con estas precisiones (todas escritas también en el
encabezado de `web/js/sismo/movimiento.js`; `scripts/sismo/estocastico.py` hace lo mismo en Python):

- **Precursor del filtro de fase cero.** `A(f)` es real y positivo: su respuesta al impulso es simétrica y deja
  energía antes de la ventana (la parte de baja frecuencia decae como `e^(−2π·f0·|t|)`, porque
  `f²/(1 + (f/f0)²) ↔ f0²·[δ(t) − π·f0·e^(−2π·f0·|t|)]`; deducción propia). Por eso la ventana empieza en
  `t_pre = max(5/(2π·f0), 1 s)` y el registro termina `t_pre` después de ella; `N` (potencia de 2) cubre además los
  40 s de ceros del paso 5. La energía que queda fuera va en `meta.fraccion_energia_fuera` (≈ 10⁻⁷). `sim.py` empieza
  la ventana en t = 0 y deja que el precursor dé la vuelta al búfer circular: la estadística es la misma (T15).
- **No linealidad del suelo con las dos componentes.** El PGA en roca que entra en `Fnl` de BSSA14 es la media
  geométrica de los PGA en roca de las dos componentes (el paso 8 lo toma por componente): el suelo es uno solo y
  BSSA14 define `PGAr` sobre la media de las dos horizontales. `meta.pga_roca_g` es esa media; `escala_pgar` la
  multiplica solo en la pasada de suelo (escala «nsr10»), sin escalar el registro.
- **`espectroObjetivo`** aplica la misma regla: `pgar_g` (sin escalar) × `p.escala_pgar`. Si no se da `pgar_g`, usa el
  PGA esperado en roca por vibración aleatoria (Boore, 2003, con el factor de pico de Cartwright y Longuet-Higgins,
  1956). Para dibujar el objetivo de un registro ya sintetizado, el motor pasa `pgar_g = meta.pga_roca_g`: así es el
  filtro que de verdad se aplicó (T15c lo usa así).
- **PGV y PGD** se integran en el tiempo (trapecios, desde reposo), no por FFT (paso 10): sirve igual para el registro
  filtrado de la calidad baja y no hay desplazamiento residual que corregir, porque `A(f) ∝ f²` cerca de f = 0.
  `Sa(T = 0) = PGA`. El espectro de Nigam y Jennings sigue un período amortiguado de vibración libre después del
  registro (el máximo de la vibración libre está en su primer medio ciclo).
- **Banda de transición (E15).** Cada término lleva sus propios parámetros (`meta.terminos`); `meta` muestra, solo para
  leer, medias geométricas ponderadas de f0, Δσ, βs, ρs, Q0 y Ref y medias lineales de κ0, η y Tgm.
- **GMPE.** `amenaza.json` trae coeficientes solo para PGA, 0,2, 0,5 y 1,0 s. `gmpe()` devuelve el PGA para
  T ≤ 0,01 s, interpola ln Sa y σ linealmente en ln T entre 0,2 y 1,0 s (`gmpe.otras_periodos`) y devuelve **NaN**
  en 0,01 < T < 0,2 s y en T > 1,0 s: la meseta y la rama larga no se pueden reconstruir sin inventarlas. Quien
  dibuje la GMPE salta los NaN: queda el PGA (T = 0) y la curva de 0,2 a 1,0 s, con su banda ±1σ. Distancias de fuente
  puntual: BC Hydro con la hipocentral, Zhao con la hipocentral como distancia a la ruptura, BSSA14 con Rjb ≈ Repi
  **solo para focos someros**; fFABA = 0, mecanismo no especificado y Zhao cortical sin el término de falla inversa,
  como en la investigación. `gmpeEscenario` pesa las dos de cada régimen con (1 − w)/2 y w/2, salvo BSSA14.
- **BSSA14 y la profundidad (regla del motor, revisión A6; desviación de `amenaza.json → gmpe.bssa14.
  distancia_para_fuente_puntual`, que solo vale para focos someros).** BSSA14 no tiene término de profundidad
  (`FE(M) + FP(√(Rjb² + h_coef²)) + FS`, con una seudoprofundidad fija de 4,5 km en el PGA) y se ajustó con sismos
  corticales someros de NGA-West2. Con `Rjb = Repi` daba lo mismo para un foco a 10 km que a 40 o a 65 km
  (Mw 6,2, Repi 0: 0,481 g en todos) y, con Repi corto y h ≥ 20 km, arrastraba hacia arriba la media ponderada: la
  simulación parecía quedarse hasta 3 veces corta (ln = −1,12 en h = 40 km) cuando el problema era la referencia. Ahora
  BSSA14 conserva `fraccionBSSA14(h) = clamp((25 − h)/10, 0, 1)` de su peso (todo hasta 15 km, nada desde 25 km;
  rango de focos de NGA-West2 por confirmar) y el resto pasa a Zhao 2006 cortical, que sí tiene término de
  profundidad. `avisos` dice «BSSA14 fuera de su rango de profundidad» cuando pierde peso. Los coeficientes y las
  formas de las cuatro GMPE no cambian (la revisión los comparó con pygmm 0.8.0 y con `zhao_2006.py` de OpenQuake).
- **Partición** `V = 1/√2` exacta (`amenaza.json` guarda 0,7071: diferencia relativa de 7·10⁻⁶).
- **Calidad baja.** FIR de fase cero con ventana de Kaiser (81 coeficientes): rizado ≤ 10⁻³ hasta 20 Hz y ≥ 60 dB desde
  30 Hz (medidos sobre la respuesta exacta en MOV4; con las fórmulas de Kaiser para 60 dB el rizado salía 1,1·10⁻³,
  por eso se diseña con 65 dB); después, una de cada dos muestras. `motor.js` filtra las dos componentes y llama al
  integrador con el registro de Δt = 0,01 s.
- **Magnitud.** El control es Mw («la escala que reemplazó a la de Richter»). ML (Richter, 1935) se satura por encima
  de ≈ 6,5 a 7 y no hay una conversión ML → Mw confirmada para la red colombiana: el simulador no convierte. Se usa
  `M0 = 10^(1,5·Mw + 16,05)` dina·cm (Hanks y Kanamori, 1979), con la que se calibró `amenaza.json` (la norma IASPEI
  de 2013 da 16,1: 0,03 unidades de Mw de diferencia).

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
  **T1x y T1y son los del modelo de diseño** (muros de mampostería como en el archivo), también con
  `noEstructurales: 'confinados'` (revisión A6): el registro escalado depende solo del sismo, y «Aislados» y
  «Sin aislar» se comparan con el mismo movimiento del suelo (con los períodos de «Sin aislar», 0,285/0,244 s, el
  factor subía 12-14 % y el contraste de E5 mezclaba el efecto de los muros con otro registro). `listo.escala_nsr10`
  dice qué períodos usa (`{ T1x, T1y, modelo }`).
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
  `frontera` con los dos indicadores (Shenton, 1996). El régimen informado es el del instante de aceleración máxima;
  en un bloque no cuadrado el régimen depende de la dirección de `a`, así que si en el registro pasó otra cosa se
  informa lo que pasó: `desliza` si deslizó sin empezar a balancearse, `balancea` si se balanceó sin deslizar y
  `frontera` si ocurrieron las dos.

### Integrador y motor: decisiones de implementación (ola 1)

- **Predictor de cada paso.** Con la tangente comprometida (la del último paso, si el Δt es el mismo), el
  incremento lineal de Newmark escrito con las fuerzas comprometidas:
  `K_ef·Δu = P_n+1 − M·ü(u_n) − a0·M·u̇(u_n) − (F_n − 2·D_n) − K_PΔ·u_n − F_m,n`, con `ü(u_n) = −(4/Δt)·u̇_n − ü_n`,
  `u̇(u_n) = −u̇_n` y `D_n` la fuerza de amortiguamiento de los elementos (en `u_n`, con la historia del paso nuevo,
  el momento de la parte elástica es `M_n − 2·D_n`). Es la forma incremental clásica
  `K̂·Δu = ΔP + (4M/Δt + 2C)·u̇_n + 2M·ü_n`: un paso elástico converge en la primera evaluación (1,1 iteraciones por
  paso en la torre sintética con 33 elementos que fluyen). Los v y θ siguen la condensación de la última tangente,
  `Δu_c = −X·T·Δu_d` con `X = K_cc⁻¹·K_cd`; un pórtico cuyo residuo condensado queda por debajo de 10⁻³ de la
  tolerancia omite su solución en banda en esa iteración.
- **Convergencia.** Se exigen a la vez `‖R‖∞` (diafragma sin condensar y gdl condensados) y la corrección que da ese
  residuo, `‖Δu‖∞ ≤ 10⁻⁹`; al converger esa corrección (≤ 10⁻⁹ m) no se aplica. Si el retorno de un elemento no
  encuentra conjunto activo o un pórtico queda inestable con la tangente de prueba, el paso se trata como no
  convergido y se parte.
- **Registro.** `dt_s` debe dividir al Δt del registro (la excitación entre muestras es lineal, como en Newmark y en
  Nigam-Jennings); después del registro el suelo queda quieto (vibración libre) hasta `duracion_s` (por defecto, la
  duración del registro). `motor.js` hace la síntesis a 0,005 s, la escala `nsr10` (11 períodos igualmente
  espaciados entre 0,8·T1 y 1,2·T1 para T1x y otros 11 para T1y) y, en calidad baja, `filtrarYDiezmar`.
- **Energía.** `calidad_numerica.error_energia_max` y `error_deformacion_max` son el mayor desbalance absoluto de cada
  igualdad en cualquier Δt, dividido por el máximo de `|E_entrada|` en toda la corrida.
- **Equipos.** `CUB` = el nivel más alto cuyo contorno contiene la posición del equipo (cubierta del piso 4 o terraza
  del piso 3 sur); `cielo` = la losa de arriba de su piso; `dentro` se trata como anclado a su contenedor (se informa
  la fuerza que el contenedor le da). El deslizamiento usa la aceleración media de cada paso (la misma cinemática de
  Newmark de aceleración promedio); si el bloque se detiene dentro del paso se calcula el instante y, si `|a| > μg`,
  vuelve a arrancar en lo que queda del paso; un bloque que ya desliza sigue deslizando aunque el régimen
  instantáneo sea de balanceo. Es exacto en 1D con aceleración constante por tramos (T21).
- **Espectro de umbral de daño** del mensaje `movimiento`: `espectroUmbralDano(T, { Ad, Fa, Fv })` de `movimiento.js`,
  el mismo del prediseño (A.12.3, ξ = 2 %, sin I: `3,0·Ad·Fa` hasta `TC = 0,5·Fv/Fa` y `1,5·Ad·Fv/T` después; forma
  por confirmar). El mensaje dice el amortiguamiento de cada curva: `nsr10.xi = 0,05` (diseño, con y sin I) y
  `nsr10.xi_umbral_dano = 0,02`; la de umbral de daño no se compara a la par con el espectro del registro (5 %).
- **Respaldo por tramos.** Con `opciones.ceder` (o `crearMotor({ modo: 'tramos' })`), `analizar` cede también entre
  las etapas previas (síntesis, vueltas de la escala `nsr10`, filtro), no solo entre pasos; la síntesis de un
  registro (≈ 60 ms en escritorio) sigue siendo un bloque. Cancelado: error con `codigo: 'cancelado'`.
  `analizarPorTramos` cede también después de armar el análisis (gravedad y cajas de resultados de ≈ 30 MB) y avanza
  de a un paso mientras quede presupuesto (ola 2): con tandas de 10 pasos, un paso frío (primera factorización de los
  pórticos y compilación) dejaba tramos de ≈ 25 ms en Chromium; ahora el más largo es de ≈ 13 ms. Los pasos y los
  resultados son los mismos, bit a bit (T17).
- **Historia interna.** Series `Float32Array(nt·nE)` de `Mi`, `Mj`, `V`, `N`, `thp_i`, `thp_j` y `dc` (cociente) por
  salida; con `guardar_serie_completa`, además `u_completa` (Float64, cada Δt) para `exportar_caso.mjs`.
- **Tiempos medidos (Node 22, este entorno, 4 núcleos compartidos)** con una torre sintética de 398 elementos, 294
  nodos y 464 gdl condensados (`pruebas/_torre_sintetica.mjs`, geometría del 1.2): `iniciar` 5-40 ms, `movimiento`
  20-130 ms, `analizar` de 40 s con Δt = 0,005 s (8.000 pasos, cimitarra, 33 elementos con fluencia) 0,85-1,3 s;
  resultados más historia 31,7 MB. En Chromium sin pantalla, el trabajador de módulo y el respaldo dan resultados
  idénticos bit a bit. Los tiempos con la torre real y con CPU ×4 los mide `qa_worker.mjs` (ola 2, abajo).

## Mensajes del trabajador (E11; contrato, 7.5)

`web/js/scenes/torre/sismo.js` crea el trabajador con `new Worker(new URL('../../sismo/trabajador.js',
import.meta.url), { type: 'module' })` y le pasa URL **absolutas** (dentro del trabajador la base sería
`web/js/sismo/`). Sin `SharedArrayBuffer` (GitHub Pages no envía COOP/COEP).

| Dirección | Mensaje | Respuesta |
|---|---|---|
| ← | (al evaluar el módulo) | `{ tipo: 'cargado' }` |
| → | `{ tipo: 'iniciar', v: 1, id, url_estructura, url_amenaza, opciones: { histeresis, noEstructurales } }` | `{ tipo: 'listo', id, resumen, elementos, nodos, modos, amortiguamiento }` |
| → | `{ tipo: 'movimiento', id, params }` | `{ tipo: 'movimiento', id, registro: { dt, n, ax, ay, meta, intensidades, avisos }, espectro: { T, Sa_x, Sa_y }, fourier: { f, A_x, A_y }, gmpe: [{ nombre, peso, T, mediana_g, sigma_ln }], nsr10: { T, con_I, sin_I, umbral_dano, xi, xi_umbral_dano } }` |
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
- `listo.escala_nsr10`: `{ T1x, T1y, modelo }`, los períodos con que se calcula la escala «nsr10» (los del modelo de
  diseño; con «Sin aislar» no son los de `listo.modos`). `listo.amortiguamiento.regla` dice de dónde salen las anclas.
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
| `pruebas/movimiento.mjs` | T13-T15, T15b, T15c, T16, T19 (en hilos de trabajo, ≈ 45 s con 4 núcleos), T20; MOV1-MOV5 propias (fragmentos de `notas_para_implementar`, FFT y azar, Nigam y Jennings con solución cerrada, registro y filtro, intensidades) |
| `pruebas/integrador.mjs` (además) | R0: el motor contra una segunda implementación del mismo cálculo (`scripts/sismo/referencia_min.py` → `scripts/fixtures/torre/referencia_min.json`, con las mismas reglas): series, envolventes y serie de `C-A1-1@X` a 10⁻⁶ del máximo de cada arreglo; D/C, rótulas, thp, equipos y muro idénticos; a0, a1 y ξ de los modos a 10⁻⁶ |
| `pruebas/motor.mjs` | T17; W1 el trabajador real responde los mensajes del 7.5; E1 escala `nsr10` y calidad baja; R1 tiempos del 7.7 con la torre sintética |
| `pruebas/estructura.mjs` | T18 con la estructura real (`torre_hospital_estructura.json`); S1 la estructura cumple el esquema; S2 los 12 períodos del motor son los del prediseño en Python (< 10⁻³); S3 períodos ancla y centro de rigidez iguales; S4 equilibrio de gravedad |
| `pruebas/_estructuras.mjs`, `pruebas/_torre_sintetica.mjs` | Ayudantes: estructuras pequeñas con solución cerrada y registro sintético determinista; torre sintética del tamaño de la torre (hasta que exista `torre_hospital_estructura.json`) |
| `pruebas/datos.mjs` | F1 fixtures del Anexo A, F2 `amenaza.json` idéntico en números a la investigación, F3 el validador detecta errores sembrados, F4 el trabajador simulado responde los mensajes |

Las referencias y tolerancias de T1-T22 son las del contrato (7.8, con la tabla del lazo de T7). T18 corre la
estructura real y usa `validarResultado` de `validar_resultado.mjs`. Dos lecturas precisas de la tabla del 7.8:

- **T4 (escalón, 20 ciclos, 0,5 %).** Newmark de aceleración promedio no disipa pero alarga el período; con
  Δt = T/100 el desfase acumulado a los 20 ciclos es 20·2π·(ωΔt)²/12 ≈ 0,041 rad, así que contra
  `−(ag/ω²)(1 − cos ωt)` con la ω continua el error es ≈ 2 %, inalcanzable para cualquier implementación correcta.
  La prueba compara la amplitud (`2·ag/ω²`, exacta) y la historia con la frecuencia discreta ω̄ = ω/(T̄/T) de T1
  (la solución discreta es exactamente `−(ag/ω²)(1 − cos ω̄t)`, por ser el método la regla del trapecio sobre
  `[u, u̇]`), e imprime el desfase contra la ω continua.
- **T7.** Las cifras de la tabla están redondeadas: con `k_e = 10⁴ kN·m/rad`, imponer θ = 0,019417 en vez de
  0,0194175 cambia M en 0,005 kN·m. La prueba impone el θ exacto de cada punto (deducido con las reglas del 7.4) y
  compara θ, M y θp con las cifras impresas a media unidad de su última cifra; los 200 puntos intermedios se
  comparan con el lazo lineal por tramos exacto (|ΔM|/My ≤ 10⁻⁶).

## Validación con OpenSees: `python3 scripts/sismo/validar_opensees.py` (contrato, 7.9)

Requisitos en `scripts/sismo/requisitos_validacion.txt` (`openseespy==3.8.0`, `numpy`); no corre en CI: el resultado
se versiona en `data/sismo/validacion_opensees.json` (con los criterios del 7.9, cada uno con su valor, su tolerancia
y si cumple). `node scripts/sismo/exportar_caso.mjs <escenario|ninguno> <salida.json> [--estructura R] [--escala X|nsr10]
[--angulo G] [--calidad baja] [--duracion S] [--sin-pdelta]` escribe el registro tal como lo integra el motor (cada Δt,
girado, escalado y, en calidad baja, filtrado y diezmado), `a0` y `a1`, el modelo de referencia con las propiedades
que el motor usa de verdad (E, G, A, `I·factor_fisuracion`, Av, `L_f`, brazos, `k_e`, `H`, momentos de fluencia de cada
extremo, rótula sí o no, cargas de gravedad), la rigidez lateral condensada, `K_PΔ`, los modos y los resultados del
motor sobre el mismo caso (con `u_completa` de cada Δt); así la réplica no reimplementa la síntesis ni las reglas de
las secciones.

Réplica de la idealización (modelo 3D, `ndm 3, ndf 6`): nodos propios por pórtico como esclavos de `rigidDiaphragm 3`
(maestro en el centro de masa con `mass(m, m, 0, 0, 0, Jz)`), sin restringir en ellos `ux`, `uy` ni `rz` (solo el giro
fuera del plano); `ElasticTimoshenkoBeam` con `I·factor_fisuracion` e `Iy = J = 10⁻⁶·I`; brazos rígidos como
`elasticBeamColumn` 10³ veces más rígidos (no `rigidLink`); rótulas `zeroLength` sin Rayleigh con `k0 = 10³·k_e` y
pendiente después de la fluencia `α·k_e`; `rayleigh(a0, 0, a1, 0)` (las columnas de gravedad, en una región sin
Rayleigh); P-Delta con 4 pilas de columnas articuladas de gravedad por nivel (`geomTransf PDelta`, `EI = 10⁻⁶ kN·m²`);
gravedad con `loadConst -time 0.0`; `Newmark 0.5 0.25`; `Transformation`. Decisiones de la réplica (medidas en este
entorno; el detalle está al principio del programa):

- **Rótulas asimétricas** (vigas y muros, E3): `Parallel(ElasticPP(k0 − H, My_pos/k0, −My_neg/k0), Elastic(H))`, que
  es el mismo endurecimiento cinemático bilineal (resorte elastoplástico perfecto en paralelo con uno elástico) con
  fluencia distinta en cada sentido; las simétricas, `Steel01(My, k0, b = α/10³)`. El caso de control 2 prueba las dos.
- **Los otros 5 gdl de la rótula:** `equalDOF` cuando la cara no es esclava del diafragma. Con el manejador
  `Transformation`, un `equalDOF` cuyo nodo retenido es esclavo de `rigidDiaphragm` da desplazamientos errados
  (restricciones encadenadas: 112 % en un pórtico de prueba); por eso, si la cara es esclava (nudo sin brazo), el nodo
  interno es esclavo del mismo diafragma (mismo punto) y `uz` se une con un resorte de 10¹² kN/m. Si la cara es el
  apoyo, el nodo interno queda fijo salvo el giro de la rótula: con `equalDOF` hacia el apoyo, OpenSees no suma las
  fuerzas del elemento a la reacción del apoyo y el cortante basal salía 0.
- **Cortante basal** de OpenSees: suma de las reacciones de los apoyos de los pórticos con `reactions -dynamic` (las
  fuerzas resistentes con el amortiguamiento de Rayleigh; `-rayleigh` da solo el amortiguamiento).
- **Energía amortiguada** de OpenSees: `a0·∫u̇ᵀMu̇` en los maestros más `a1·∫ėᵀK_e ė` en la parte elástica de cada
  elemento, con las velocidades que da OpenSees y la misma regla del trapecio del motor (`Δu = Δt/2·(u̇_n + u̇_{n+1})`
  es exacta en Newmark de aceleración promedio). Los brazos también amortiguan en OpenSees, pero en serie y 10³ veces
  más rígidos su aporte es ≈ 10⁻³.
- **Períodos** de OpenSees: de la flexibilidad lateral condensada (3N cargas unitarias en los maestros, después de la
  gravedad, con P-Delta) y, como control, de `eigen -genBandArpack` (coinciden a 10⁻⁹).
- **Sistema de ecuaciones:** `ProfileSPD` (38 ms por paso en la torre, frente a 67 ms de `UmfPack`, con los mismos
  resultados). `SparseSYM` es más rápido, pero en OpenSees 3.8 dio el caso de control 1 errado (97 %) y un valor propio
  negativo en la torre: no se usa.
- **Algoritmo:** Newton; si no converge (en la inversión de una rótula de `k0 = 10³·k_e`, el primer tanteo con la
  tangente después de la fluencia salta al otro lado de la superficie y Newton oscila), Newton-Krylov con la tangente
  inicial, Krylov con la del paso y Newton con búsqueda lineal; si nada converge, el paso se parte en 10 (hasta 3
  veces). Después de un intento fallido OpenSees 3.8 deja el análisis contaminado (el siguiente algoritmo tampoco
  converge, aunque desde un análisis limpio converja en 3 iteraciones): cada intento nuevo arma el análisis otra vez
  (`wipeAnalysis`), que parte del estado comprometido. Todos llevan a la misma solución.

Casos de control (7.9): (1) un piso y tres pórticos (dos X con columnas distintas y uno Y, Timoshenko, CM corrido)
contra la condensación pseudotridimensional exacta armada aparte en el programa (Przemieniecki, condensación estática y
compatibilidad del diafragma; P-Delta con las 4 columnas articuladas): desplazamientos < 10⁻⁵ sin y con P-Delta. El
residuo (≈ 9·10⁻⁶) es la rigidez fuera del plano `Iy = J = 10⁻⁶·I` que pide el 7.9: con `10⁻⁹·I` baja a 9·10⁻⁹. Con las
rótulas `zeroLength` de `k0 = 10³·k_e` (informativo) la diferencia es ≈ 9·10⁻⁴. (2) Ciclo cuasiestático de una rótula
en serie con su parte elástica contra la tabla de T7 (< 0,5 %), con las dos formas de la réplica, y una rótula
asimétrica (100 y 60 kN·m) contra la del motor (`rotulaEnSerie`). El caso no lineal de la torre es `local_hip` con la
escala «nivel de diseño NSR-10» (×2,46, declarada). Fluencia en OpenSees: θp = deformación − parte elástica del
resorte (σ/k0 en `Steel01`; σ_pp/(k0 − H) en el paralelo) mayor que 10⁻⁹ rad.

## QA del trabajador en Chromium: `node scripts/sismo/qa_worker.mjs --vendor <carpeta>` (contrato, 7.5, 7.7 y 13.1)

Usa `scripts/qa/comun.mjs` (D) sin modificarlo. Con el trabajador real y la estructura real, sirviendo la raíz del
repositorio en `/` y bajo `/trabajemosjuntos/` (una página de prueba que Playwright entrega en esa subruta; no es un
archivo del repositorio): `cargado`, `listo`, `movimiento` (Float32Array transferidos), `progreso` (cada ≥ 250 ms),
`resultado` tipado y `serie_elemento` después del resultado; cancelar a la mitad (`terminate` y aviso) ≤ 300 ms y un
trabajador nuevo que vuelve a calcular; el respaldo por tramos con los mismos Resultados (SHA-256 de todos los arreglos
y campos, sin `duracion_calculo_ms` ni `id`) y su tramo más largo sin ceder; los tiempos del 7.7. Con `--vendor`, además
la vista real (`index.html?qa=1#torre`, modo sismo, bajo `/trabajemosjuntos/`): usa el trabajador, el botón «Cancelar»
deja «Cálculo cancelado.» en ≤ 300 ms, vuelve a calcular, y sin `Worker` usa el respaldo con los mismos Resultados.
Si `web/data` todavía no trae `sismo_torre_estructura.json`, la prueba le sirve la estructura de `data/sismo/`.

- **Teléfono (CPU ×4 por CDP):** Chromium solo frena páginas (`Emulation.setCPUThrottlingRate` sobre un trabajador:
  «Operation is only supported for pages, not workers»). La misma cuenta de `motor.js` corre de corrido en el hilo
  principal de la página frenada ×4 (es el proxy del trabajador en un teléfono), y se informa el freno medido con el
  mismo análisis a ×1 (entre ×3,2 y ×4,5 en este entorno: si queda por debajo de 4, los tiempos se llevan a ×4).
- **Memoria del trabajador:** `Runtime.getHeapUsage` del trabajador por CDP (montón de V8 y almacenamiento de los
  ArrayBuffer, después de recoger la basura: queda la historia interna) más los Resultados transferidos.

## Escenarios de referencia: `node scripts/sismo/escenarios.mjs` → `data/sismo/escenarios.json`

Cifras para `docs/14` (contrato, 11.3 punto 8): `nido_2015`, `cimitarra` y `local_hip` con su registro físico y el
«nivel de diseño NSR-10» (escenario hipotético) aplicado a los mismos tres registros (el de referencia es `local_hip`
escalado, el mismo de la validación con OpenSees), con Δt = 0,005 s, semilla y Vs30 por defecto, P-Delta y muros
aislados. Por escenario: factor de escala, PGA, PGV y D5-95 del registro integrado, deriva vectorial máxima por piso
(con el vértice y el instante), desplazamientos y aceleraciones absolutas máximos, cortante basal máximo (de la serie de
0,02 s) y sobre el peso, elementos que fluyen (por nivel y por tipo, extremos más allá de IO, LS y CP), D/C máximo con
el elemento y lo que gobierna, energía final, estado de los muros de mampostería, equipos del inventario publicado
(misma regla de la vista: cuántos deslizan, empiezan a balancearse o quedan en la frontera, y la fuerza máxima de
anclaje) y calidad numérica. Determinista (`--verificar`).

## Fixtures (Anexo A.3 y A.4 del contrato)

En `scripts/fixtures/torre/`:

- `estructura_min.json`: cubo de prueba de 2 pisos y 1 vano por dirección (5,0 × 5,0 m; entrepisos de 3,0 m),
  4 pórticos (`X-1`, `X-2`, `Y-A`, `Y-B`) con 6 nodos y 6 elementos cada uno y un muro de mampostería sin aislar
  (`M-X1-1`, nivel 1 de `X-1`). Valores de prueba, no de diseño. `theta_y` y `theta_y_e` van con 4 cifras
  (0,001616 y 0,003946 rad): con 0,0039 la viga quedaba a −1,16 % de su fórmula, fuera de ± 1 %.
- `resultado_min.json` y `serie_elemento_min.json` (`C-A1-1@X`): `Resultados` de 3 pasos de salida (0; 0,02;
  0,04 s) calculados **con el motor** sobre `estructura_min.json` por `node scripts/sismo/fixtures_min.mjs` (ola 2;
  en la ola 0 los calculó `referencia_min.py`). El registro es un pulso de prueba ×25 (`origen_registro`), porque en
  0,04 s ningún acelerograma sintético hace fluir nada; `params` conserva el escenario por defecto para que la vista
  tenga qué mostrar. Trae rótulas que fluyen, un equipo que desliza, uno que empieza a balancearse, uno anclado y el
  muro con daño. Reales en Float32 (la representación decimal más corta), `duracion_calculo_ms` fijo en 1.
- `trabajador_simulado.js`: responde `cargado`, `listo`, `movimiento`, `resultado` y `serie_elemento` con esos
  archivos y con el bloque `GENERADO` que escribe `fixtures_min.mjs` (el `listo` del motor, el pulso con sus
  espectros, Fourier, GMPE y NSR-10 calculados con `movimiento.js`, y las series de los 24 elementos de la historia
  interna). Acepta `url_fixtures` en `iniciar` y `simular: { retardo_ms, error }` en cualquier mensaje.
- `referencia_min.json`: los mismos Resultados calculados por `scripts/sismo/referencia_min.py` (Python con numpy, el
  modelo no lineal completo escrito aparte; lo que simplifica está al principio del archivo), con las reglas corregidas
  de la ola 1. Es la segunda implementación contra la que la prueba R0 compara el motor.

```bash
node scripts/sismo/fixtures_min.mjs --verificar        # recalcula con el motor y compara byte a byte
node scripts/sismo/validar_resultado.mjs scripts/fixtures/torre/resultado_min.json
python3 scripts/sismo/referencia_min.py --verificar    # con numpy: recalcula la referencia y compara byte a byte
node scripts/sismo/test_motor.mjs --solo F1,F2,F3,F4,R0
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
