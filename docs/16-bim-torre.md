# 16 · Modelo BIM de la torre: plan de ejecución, coordinación y cantidades

**La torre de servicios de primer nivel de Yondó modelada con la metodología BIM: un modelo federado por disciplinas (arquitectura, estructura, cimentación, refuerzo, equipamiento fijo e infraestructura, y dotación), exportado a IFC4 real y georreferenciado, con cantidades y costos (5D), fases de obra (4D), el vínculo con el simulador sísmico y la detección de interferencias. Este documento es su plan de ejecución BIM y dice qué resultó de la coordinación y cuánto cambia el presupuesto.**

> Estado: **modelo de prefactibilidad: no reemplaza los diseños firmados.** Fecha de corte: 25 de octubre de 2026. Se construye sobre el anteproyecto ilustrativo de plantas (estimación) y sobre el prediseño estructural DMO sin firmar (cálculo propio). Las cifras salen del modelo generado, de su validación con IfcOpenShell, de la detección de interferencias y de la comparación con el presupuesto; un control automático las compara con esos datos.
>
> Tipos de dato: **dato oficial** (copiado de la fuente), **dato del proyecto** (programa, presupuesto y cronograma del documento 11), **cálculo propio** (operación sobre datos citados, con el método a la vista) y **estimación** (supuesto con rango, por confirmar). Pesos constantes de 2026.

## En pocas palabras

- **Qué es:** 4.583 elementos con su clase IFC4, su nivel, su geometría, su material, sus conjuntos de propiedades y cantidades, su ítem del presupuesto y su fase de obra, más 6.170 juegos de barras de refuerzo (64.849 barras, 292.289 kg) con su forma real. Se descarga en dos archivos IFC4: el principal (7,3 MB) y el del refuerzo (12,26 MB).
- **Validado:** el esquema IFC4 no tiene errores; los 31 tipos de elemento y todas las cantidades coinciden con el modelo; 30.638 identificadores globales en el archivo principal y 39.677 en el del refuerzo, sin repetidos (cálculo propio con IfcOpenShell 0.9.0).
- **Coordinación:** la primera corrida del modelo federado (24-oct-2026) encontró **280 interferencias duras** (201 del prediseño estructural, 46 del anteproyecto de plantas y 33 compartidas). Después de corregir sus causas en la estructura, en la planta y en el modelo, quedan **0 duras**; siguen 683 medias (sobre todo congestión de barras que se resuelve en el detallado) y 7 leves (cálculo propio).
- **Lo que cuesta cumplir la norma:** el prediseño que cumple la NSR-10 (columnas de 0,80-0,90 m, muros de 0,35 m y 146 pilotes de 15 m) cuesta más que el presupuesto vigente: **entre $1.310 M y $1.390 M más de costo directo** en estructura y cimentación, **$1.742 M a $1.848 M con AIU** (cálculo propio). Con las secciones del presupuesto, la deriva llegaba a 2,09 % y no cumplía el 1 %. El presupuesto no se cambió: es un **ajuste pendiente del prediseño estructural** (documento 11, presupuesto).
- **LOIN:** arquitectura ≈ 300, estructura y cimentación ≈ 350, refuerzo ≈ 400 y dotación ≈ 200-300 como objetivo; hoy cada disciplina está en prefactibilidad y dice qué información le falta para llegar.

## 1. Qué es este modelo y qué no es

**Para qué sirve.** Para ver la torre entera, con su cimentación y su refuerzo, coordinar las disciplinas antes del diseño definitivo, medir cantidades y compararlas con el presupuesto, ordenar la obra en el tiempo, ver en la estructura los resultados del simulador sísmico (documento 14) y tener desde ya un inventario de lo que se va a operar y mantener (documento 15).

**Qué no es.** No es un diseño: el modelo hereda lo que son sus insumos, un anteproyecto ilustrativo y un prediseño sin firmar. No es apto para construcción ni para figurar barras (el refuerzo es el despiece de prediseño). La Res. 485 de 2025 pide diseños firmados por profesionales con matrícula (num. 7.1.2.6 a 7.1.2.10); este modelo es un insumo para contratarlos y para revisarlos, no un sustituto.

## 2. Marco y términos

| Término | Qué es en este proyecto | Referencia |
|---|---|---|
| Serie ISO 19650 (gestión de la información con BIM) | Marco de requisitos, entregas y responsabilidades que sigue este plan | ISO 19650-1 y 19650-2:2018; adopción como norma técnica colombiana (NTC-ISO 19650) por confirmar |
| Parte designante | Quien contrata y recibe la información: la E.S.E. Hospital Héctor Abad Gómez (o el Municipio de Yondó, según quién presente el proyecto) | ISO 19650-2 |
| Parte designada líder y partes designadas | El consultor de estudios y diseños (P1) y sus especialistas; luego, el contratista de obra | ISO 19650-2 |
| Requisitos de información (de la organización, del activo, del proyecto y de intercambio) | Lo que la E.S.E. necesita para operar, mantener y habilitar la torre: inventario con registro y clase de riesgo, mantenimiento, áreas, cantidades y costos | ISO 19650-1 |
| Plan de ejecución BIM | Este documento: usos, disciplinas, nivel de información, codificación, georreferenciación, coordinación y entregables | ISO 19650-2 |
| Entorno común de datos | El repositorio del atlas: cada archivo generado guarda las huellas de sus insumos y no se publica si está desactualizado (estados «en curso», «compartido» y «publicado» simplificados) | ISO 19650-1 |
| Modelo de información del proyecto y del activo | Hoy, un modelo de información del proyecto en prefactibilidad; al entregar la obra se vuelve el del activo (operación y mantenimiento) | ISO 19650-1 y 19650-3 |
| Nivel de información necesario (LOIN) | Geometría, información alfanumérica y documentación por disciplina, con el tipo de dato de cada parte (sección 5) | ISO 7817-1:2024 (antes EN 17412-1); por confirmar |
| IFC4 | Formato abierto de intercambio; IFC4 ADD2 TC1 con las plantillas de conjuntos de propiedades de IFC4 | ISO 16739-1:2018 |
| Estrategia Nacional BIM 2020-2026 | Marco de adopción de BIM en la contratación pública de Colombia | Gobierno de Colombia; texto, metas y entidad responsable por confirmar. La norma propia de la entidad que financie (MinSalud, Gobernación o SGR) sobre BIM: por confirmar |

## 3. Alcance y usos del modelo

| Uso | Qué hace el modelo | Estado |
|---|---|---|
| Coordinación de disciplinas | Detecta choques entre estructura, arquitectura, redes, dotación y refuerzo (sección 8) | Hecho: 0 interferencias duras |
| Cantidades y costos (5D) | Cada elemento lleva su ítem del presupuesto y su análisis de precio unitario; las cantidades del modelo se comparan con las del presupuesto (sección 9) | Hecho; ajuste pendiente en el presupuesto |
| Programación (4D) | Cada elemento lleva su fase de obra, repartida por piso y disciplina dentro de las etapas 7 a 11 del cronograma del documento 11 (sección 10) | Hecho (el reparto es estimación) |
| Análisis estructural | Cada columna, viga y muro se enlaza con su elemento del modelo sísmico: en el modo «Modelo BIM» se pintan la demanda/capacidad, las rótulas y la deriva del último cálculo (documento 14) | Hecho |
| Dotación y habilitación | Cada unidad del inventario (equipo, mueble, implemento a la vista, infraestructura) es un elemento con su clase de riesgo, su registro y su exigencia (documento 15) | Hecho |
| Operación y mantenimiento | Base para el inventario de mantenimiento: clase de riesgo, si requiere personal inscrito en el INVIMA, vida útil y porcentaje anual de mantenimiento por línea | Parcial: marca, modelo y serie se llenan al comprar |

## 4. Organización del modelo federado

**Disciplinas y conteos** (cálculo propio):

| Disciplina | Qué contiene | Elementos | Clases IFC4 principales |
|---|---|---:|---|
| Arquitectura | Espacios (recintos), muros, puertas, ventanas, pisos y cielos, losas no estructurales, escaleras | 2.236 | 322 espacios, 922 muros, 310 puertas, 126 ventanas, 506 recubrimientos de piso y cielo, 23 losas, 9 escaleras con 18 tramos |
| Estructura | Columnas, vigas, losas nervadas y muros estructurales | 394 | 104 columnas, 187 vigas, 83 losas, 20 tramos de muro |
| Cimentación | Arranques de columna, pilotes, dados y losas de pilotes, vigas de amarre, muros de contención, contrapiso, fosos y cisternas | 254 | 146 pilotes, 59 zapatas (dados, losas de pilotes y vigas de amarre), 28 arranques, 13 muros |
| Refuerzo | Juegos de barras con su geometría (despiece del prediseño) | 6.170 juegos (64.849 barras) | Barras de refuerzo |
| Equipamiento fijo e infraestructura | Aparatos sanitarios, tomas de gases, seguridad, energía, bombas, tanques, paneles solares, ascensores | 627 | 259 aparatos sanitarios, 64 extintores y gabinetes contra incendio, 58 señales de evacuación con luz, 55 tomas de gases en cabecera, 25 filas de paneles solares |
| Dotación | Equipos biomédicos, mobiliario y laboratorio | 1.072 | 702 dispositivos médicos, 247 muebles, 123 equipos eléctricos |

**Niveles** (9, como pisos IFC): pilotes (punta a −17,35 m), cimentación (−2,45 m), bloque técnico (−1,50 m), exteriores y piso 1 (0,00), piso 2 (4,50), piso 3 (8,70), piso 4 (12,90) y cubierta (17,10). El modelo no repite lo que el recorrido 3D dibuja dos veces (el perímetro de la torre visto desde los exteriores): eso no entra en el modelo, en el IFC ni en las cantidades.

**De dónde sale cada disciplina:** arquitectura, del anteproyecto de plantas (estimación); estructura, cimentación y refuerzo, del prediseño estructural DMO (cálculo propio); equipamiento fijo, infraestructura y dotación, del inventario ubicado (documento 15). 1.699 unidades del inventario entran al modelo (las otras 3 son la lavandería, que queda en el hospital actual, y las 2 ambulancias de contexto).

## 5. Nivel de información necesario (LOIN) y LOD por disciplina

El nivel de desarrollo **objetivo** es el de un modelo coordinado para el diseño definitivo; el **estado actual** es el de prefactibilidad. En la vista, cada disciplina muestra además sus interferencias duras pendientes (hoy, ninguna).

| Disciplina | LOD objetivo | Estado actual | Geometría | Información alfanumérica | Documentación que falta |
|---|---|---|---|---|---|
| Arquitectura | 300 | Geometría del anteproyecto ilustrativo (cajas y prismas por objeto); sin planos firmados | Cajas y prismas por objeto; muros cortados en columnas y muros estructurales; vanos de puertas y ventanas (estimación) | Código, identificador global y clase IFC4 (cálculo propio); áreas a ejes y libres, alturas, materiales y acabados, ítem 5D y fase 4D (estimación); resistencia al fuego de muros y puertas (por confirmar) | Planos arquitectónicos firmados |
| Estructura | 350 | Geometría tipo 350 sobre un prediseño DMO sin firmar; no apta para construcción | Secciones del prediseño: columnas de piso a piso, vigas entre caras, losas nervadas con nervios y riostra, muros (cálculo propio) | Materiales, secciones, recubrimientos y vínculo con el modelo sísmico (cálculo propio); memoria de cálculo revisada (por confirmar) | Diseño estructural y planos firmados |
| Cimentación | 350 | Geometría tipo 350 sobre un prediseño con capacidad de pilotes estimada; falta el estudio geotécnico | Pilotes, dados, vigas de amarre, muros de contención, contrapiso, fosos y cisternas con sus cotas (cálculo propio) | Cargas de servicio y reacciones por pilote (cálculo propio); capacidad de los pilotes (estimación); parámetros del suelo y nivel freático (por confirmar) | Estudio geotécnico y planos de cimentación firmados |
| Refuerzo | 400 | Geometría de barras tipo 400 sobre un prediseño sin firmar; no apta para fabricación | Cada barra con su eje, dobleces y ganchos; un juego por grupo de barras iguales (cálculo propio) | Designación (N.º 3 a N.º 8), longitud, número y peso; zonas confinadas, traslapos y anclajes (cálculo propio); cartilla de despiece revisada (por confirmar) | Planos de refuerzo y cartilla firmados |
| Equipamiento fijo e infraestructura | 200 | Cajas con la medida del catálogo, sin fabricante elegido | Una caja por equipo con la medida del catálogo (estimación) | Clase IFC4, ubicación y recinto, ítem 5D (estimación); marca, modelo, potencia y fichas técnicas (por confirmar) | Diseños de redes firmados |
| Dotación | 200-300 | Cajas con la medida del catálogo, sin marca ni modelo (se completan al comprar) | Una caja por unidad; en la vista, el modelo 3D del catálogo (estimación) | Clase de riesgo y registro INVIMA (dato del inventario); precio de referencia (estimación o referencia de mercado ajustada); marca, modelo, serie y hoja de vida (al comprar) | Fichas técnicas y registros sanitarios |

## 6. Codificación de los elementos

- **Identificadores estables del proyecto**, iguales en las plantas, la estructura, el inventario, el simulador y el modelo: recintos por piso y fila del programa (por ejemplo, P2-A066-01 es el primer consultorio de medicina general del piso 2), columnas por eje y piso (C-A1-1 es la columna A-1 del piso 1), vigas por dirección, eje, tramo y nivel (VX-1-AB-1), muros por núcleo (MX-3, MY-N6), dados y losas de pilotes (D-A1, LP-escalera_sur), pilotes por dado y unidades del inventario por servicio y línea.
- **Identificador global IFC** de 22 caracteres, determinista: sale del identificador estable, así que regenerar el modelo no cambia los identificadores de lo que no cambió. 30.638 en el archivo principal y 39.677 en el del refuerzo, todos únicos y con formato válido; los dos archivos comparten solo los 47 del proyecto, el sitio, el edificio, los niveles, las fases y el programa.
- **Conjuntos de propiedades:** los de IFC4 (por ejemplo, propiedades comunes de columnas, de concreto y del paso de estribos) y tres propios del atlas: uno con el tipo de dato, la fuente, la norma y el numeral de cada elemento; uno con el refuerzo y uno con las cantidades. La validación revisó 3.566 conjuntos y 16.679 propiedades contra las plantillas de IFC4: 0 problemas.

## 7. Georreferenciación

| Qué | Valor | Tipo de dato |
|---|---|---|
| Sistema de referencia | MAGNA-SIRGAS 2018 / Origen-Nacional (EPSG:9377), Transversa de Mercator con φ0 = 4° N, λ0 = 73° W, k0 = 0,9992, falso este 5.000.000 m y falso norte 2.000.000 m | Dato oficial (definición del sistema) |
| Ancla del proyecto (±0,00 en x = 0, y = 0) | lat 7,005271; lon −73,914597 | Dato del proyecto |
| Este y norte del ancla | 4.899.019,19 m y 2.332.169,534 m | Cálculo propio (fórmulas de Krüger); coincide con PROJ a 0,25 mm |
| Convergencia de meridianos y factor de escala del punto | 0,111558° y 0,9993262 | Cálculo propio |
| Altura del ±0,00 | 75 m sobre el nivel del mar | Estimación (rango de 75-100 m): la fija el levantamiento topográfico |

El eje x del proyecto es el este verdadero; en la cuadrícula del Origen Nacional gira la convergencia. Los dos archivos IFC llevan la misma conversión de mapa.

## 8. Coordinación: detección de interferencias y su resultado

**Qué se revisa** (cálculo propio): 1.699 unidades del inventario y 310 puertas contra columnas y muros estructurales; 2.449 sólidos de concreto entre sí; 922 muros de mampostería contra la estructura; los ductos de los 4 pisos contra vigas y cimentación; 18 tramos de escalera con su altura libre (≥ 2,05 m sobre la nariz de los peldaños); 146 pilotes dentro de sus dados; 64.849 barras en 582.942 parejas (cruces), 48.098 puntos de separación libre entre barras (contra el mínimo de NSR-10 C.7.6 y el tamaño máximo del agregado, 19 mm) y el recubrimiento de cada juego. Tolerancias: 10 mm entre sólidos y 1,5 mm entre barras.

**Severidad:** **dura**, choque físico o incumplimiento de norma: hay que corregirlo antes del diseño definitivo; **media**, congestión o falta de holgura: se resuelve en el detallado o en obra con una instrucción; **leve**, contacto o diferencia dentro de las tolerancias de construcción. Se aceptan sin contar el empotramiento de 0,10 m de la cabeza de los pilotes en los dados, las barras longitudinales en el doblez de su estribo (≤ 6,5 mm) y los traslapos de contacto (C.12.14.2.1).

**Resultado por responsable**, antes (primera corrida del modelo federado, 24-oct-2026) y después de la coordinación (25-oct-2026):

| Responsable | Duras antes | Duras después | Medias antes | Medias después | Leves antes | Leves después |
|---|---:|---:|---:|---:|---:|---:|
| Prediseño estructural (A) | 201 | 0 | 123 | 75 | 0 | 0 |
| Prediseño estructural y anteproyecto de plantas (A y B) | 33 | 0 | 6 | 1 | 0 | 0 |
| Prediseño estructural y modelo BIM (A y F) | 0 | 0 | 495 | 607 | 0 | 0 |
| Anteproyecto de plantas (B) | 46 | 0 | 21 | 0 | 0 | 0 |
| Modelo BIM (F) | 0 | 0 | 0 | 0 | 7 | 7 |
| **Total** | **280** | **0** | **645** | **683** | **7** | **7** |

En total, 932 interferencias antes y 690 después (cálculo propio).

**Resultado por tipo** (duras antes → después): refuerzo fuera del concreto, 140 → 0; coherencia de la cimentación, 33 → 0; mampostería contra estructura, 30 → 0; escalera contra estructura, 25 → 0; ducto contra estructura, 13 → 0; puerta contra estructura, 9 → 0; foso contra cimentación, 7 → 0; pilote fuera del dado, 7 → 0; unidad del inventario contra estructura, 6 → 0; viga de amarre contra dado o losa de pilotes, 6 → 0; coherencia de la estructura y del despiece, 4 → 0.

**Qué se corrigió y dónde** (en la causa, no en el síntoma):

- **Prediseño estructural:** barras que se salían del concreto en nudos y bordes de muro (estribos y ganchos recalculados, bordes con acopladores); dados de 3 pilotes centrados en su grupo con los pilotes a 0,45 m o más de las caras; vigas de amarre enteras dentro de sus dos apoyos y con su cara superior a la del apoyo más bajo; foso de ascensores apoyado en el suelo, fuera de la huella de dados y losas de pilotes; esquinas de los muros asignadas a un solo muro; vigas banda del ancho del muro; traslapos de columnas en la mitad central del piso de arriba; aberturas de losa con vigas de borde para el ducto y la escalera principal; muros de contención en el borde del pasaje del bloque técnico.
- **Anteproyecto de plantas:** la escalera principal abierta pasó a un solo vano (antes una viga cruzaba un tramo con 0,41 m libres); los ductos quedaron al oriente de su viga de borde; las puertas y las unidades del inventario se corrieron de columnas y muros estructurales; los muros del bloque técnico se ajustaron a la cimentación.
- **Modelo BIM:** traslapos de columnas en el piso de arriba, estribos agregados en los nudos donde los del prediseño no cabían entre las barras de las vigas (14 estribos en 7 columnas, 76 kg), y los muros de contención y el contrapiso con su planta real.

**Lo que queda** (no bloquea el prediseño): 607 cruces de barras de hasta unos 12 mm (se corren en el detallado o en obra hasta un diámetro; NSR-10 C.7.5 y C.7.6), 73 puntos con separación libre bajo el mínimo (congestión en nudos y bordes de muro), 2 de coherencia de la cimentación, 1 ducto junto a la cimentación y 7 contactos leves entre sólidos de concreto. Las medias «A y F» subieron de 495 a 607 sobre todo porque la coordinación agregó barras (cortinas continuas, estribos en nudos y bordes confinados en los arranques): hay más barras en los mismos nudos.

## 9. Cantidades contra el presupuesto (5D)

### 9.1 Estructura y cimentación: el ajuste pendiente del prediseño estructural

**Por qué cambia.** El presupuesto vigente supuso columnas de 0,60 × 0,60 m, vigas de 0,40 × 0,60 m, ≈ 45 m de muro de 0,30 m y ≈ 100 pilotes de 12 m. Con esas secciones, el modelo sísmico del prediseño daba una deriva vectorial de diseño de **2,09 %** (y 2,17 % al equilibrar la torsión), el doble del 1 % que permite la NSR-10 (Tabla A.6.4-1), y un cociente torsional de 1,561, en el rango de la torsión extrema (más de 1,4), que el prediseño se impuso evitar por ser un edificio indispensable. Para cumplir, el prediseño llevó las columnas a 0,80 m (0,90 m en la fachada occidental), las vigas a 0,40 × 0,80 m (0,50 × 0,90 m en ese eje), los muros a 0,35 m en 5 paños y la losa nervada a 0,45 m: la deriva bajó a **0,939 %** (documento 14). Las cargas mayores y el sismo de capacidad pidieron pilotes de 15 m (con 12 m no alcanzaba la capacidad estimada) y más pilotes: **146**, con losas de pilotes bajo los dos núcleos de escaleras.

**Cuánto cambia** (cálculo propio con los valores unitarios del presupuesto; costo directo, sin AIU):

| Ítem | Qué | Unidad | Presupuesto | Prediseño | Modelo BIM | Efecto del prediseño | Efecto del modelo BIM |
|---|---|---|---:|---:|---:|---:|---:|
| 2.04 | Pilote preexcavado de 0,60 m | ml | 1.200 | 2.190 | 2.190 | $526.716.630 | $526.716.630 |
| 2.05 | Descabezado de pilotes | un | 100 | 146 | 146 | $3.910.000 | $3.910.000 |
| 2.07 | Concreto en dados y losas de pilotes | m³ | 149 | 478,2 | 478,2 | $390.870.995 | $390.870.817 |
| 2.08 | Concreto en vigas de cimentación | m³ | 112 | 30,0 | 30,0 | −$98.991.438 | −$98.991.670 |
| 2.09 | Concreto en cisternas, fosos y muros de contención | m³ | 85 | 83,4 | 82,2 | −$2.068.483 | −$3.754.745 |
| 2.12 | Losa de contrapiso | m² | 1.050,8 | 741,7 | 865,9 | −$48.584.277 | −$29.056.673 |
| 2.13 | Acero de refuerzo de cimentación | kg | 57.020 | 144.143 | 147.292 | $703.956.092 | $729.395.659 |
| 3.01 | Concreto en columnas | m³ | 160 | 303,8 | 319,7 | $186.727.366 | $207.338.524 |
| 3.02 | Concreto en muros estructurales | m³ | 200 | 173,6 | 181,0 | −$34.314.718 | −$24.693.097 |
| 3.03 | Concreto en vigas y losa nervada | m³ | 834 | 624,9 | 642,1 | −$257.947.326 | −$236.705.265 |
| 3.04 | Concreto en escaleras | m³ | 45 | 80,2 | 82,0 | $45.647.058 | $47.999.976 |
| 3.05 | Acero de refuerzo de la superestructura | kg | 160.200 | 147.142 | 144.997 | −$105.506.884 | −$122.838.139 |
| | **Cimentación (capítulo 2)** | | | | | **$1.475.809.519** | **$1.519.090.018** |
| | **Superestructura (capítulo 3)** | | | | | **−$165.394.504** | **−$128.898.001** |
| | **Total de costo directo** | | | | | **$1.310.415.015** | **$1.390.192.017** |

**Lectura.** Casi todo el aumento está en la **cimentación**: más metros de pilote (+$527 M), dados y losas de pilotes más grandes (+$391 M) y el doble y medio de acero (+$704 M a $729 M). La superestructura cuesta **menos** que lo presupuestado: las columnas y escaleras suben, pero la losa nervada de 0,45 m gasta menos concreto que los 0,24 m³ por m² del presupuesto y el acero de la superestructura baja entre 8 % y 9,5 %. Las dos columnas de efecto difieren porque el modelo mide la geometría (columnas de piso a piso, vigas entre caras de columnas, losas con nervios y riostras, barras dibujadas con sus traslapos y estribos de nudo) y el prediseño mide con espesores equivalentes sobre el área a ejes; la suma de vigas y losas casi no cambia.

**Efecto en el presupuesto** (cálculo propio; documento 11):

- Costo directo: **+$1.310 M a +$1.390 M** (6,6 % a 7,0 % del costo directo de la obra, $19.727 M); los capítulos 2 y 3 pasan de $4.813 M a $6.123 M o $6.203 M (+27,2 % a +28,9 %).
- Con AIU (factor 1,3295 del presupuesto: 24 % de administración, 3 % de imprevistos y 5 % de utilidad con su IVA): **+$1.742 M a +$1.848 M**; el valor de la obra pasaría de $26.228 M a $27.970 M o $28.076 M ($7,73 M a $7,75 M por m² construido, sobre 3.620,6 m²).
- Si además se recalculan los rubros que el presupuesto calcula como porcentaje del valor de obra (interventoría 7 %, contingencia 5 % y diseños y licencia ≈ 6,0 %), el total de la torre subiría ≈ $2.055 M a $2.180 M (5,5 % a 5,9 %), de $37.137 M a ≈ $39.193 M o $39.318 M (estimación).
- **El presupuesto no se edita en esta versión:** el ajuste queda pendiente con estas cifras, para que lo haga el equipo del presupuesto con el diseño estructural y el estudio geotécnico (que puede bajar o subir el número y el largo de los pilotes).

### 9.2 Lo demás del modelo frente al presupuesto

En las demás partidas medibles el modelo da, en neto, **−$296,9 M** de costo directo frente al presupuesto: más muro de bloque (+$273,1 M en el ítem 4.01) y de cerramiento, y menos fachada de ladrillo, piso vinílico, cielo raso, impermeabilización y puertas (cálculo propio). Son mediciones del **anteproyecto ilustrativo**: no se adoptan como ajuste hasta tener el diseño arquitectónico. Los ítems globales (redes, equipos, solar) se enlazan sin cantidad propia y no cambian.

En la dotación, la suma de las unidades del modelo supera el indirecto del presupuesto en $257,9 M; la diferencia es exactamente el valor de los equipos que van dentro de los kits y carros (urgencias, consulta externa, partos y hospitalización), cuyo precio ya está incluido en el del kit: es un **doble conteo del modelo** que queda por corregir en su cálculo de cantidades, no un costo nuevo (documento 15, implementos internos).

## 10. Programación de la obra (4D)

Las etapas 7 a 11 del cronograma del documento 11 se reparten en 29 tareas por piso y disciplina (estimación del modelo; cada tarea cae dentro de su etapa, lo comprueba la validación):

| Etapa | Tareas | Desde | Hasta |
|---|---|---|---|
| 7. Demolición y cimentación | Pilotes; dados, losas de pilotes, arranques, vigas de amarre y muros de contención; fosos, cisternas y contrapiso | 16-sep-2028 | 31-dic-2028 |
| 8. Estructura, mampostería, redes y cubierta | Estructura piso por piso (del piso 1 al 4), mampostería, fachada y ventanas por piso, cubierta y bloque técnico en obra gris | 16-dic-2028 | 31-ago-2029 |
| 9. Acabados y equipamiento fijo | Acabados por piso; aparatos sanitarios, gases, seguridad y equipamiento fijo por piso; bloque técnico; paneles solares y equipos de cubierta | 1-may-2029 | 31-ene-2030 |
| 10. Dotación | Compra e instalación de la dotación por piso y del bloque técnico, la cubierta y los exteriores | 1-ago-2029 | 28-feb-2030 |
| 11. Puesta en marcha | Habilitación y traslado de servicios | 1-feb-2030 | 30-abr-2030 |

En el archivo IFC, 28 de las 29 tareas tienen elementos asignados (la de puesta en marcha no construye nada) y los conteos coinciden con el modelo: 0 errores.

## 11. Entregables IFC4 y su validación

| Archivo | Tamaño | Entidades | Esquema | Contenido |
|---|---:|---:|---|---|
| Torre del hospital (arquitectura, estructura, cimentación, equipamiento y dotación) | 7,3 MB | 83.220 | IFC4, 0 errores | 4.583 elementos de 31 clases con sus cantidades, 66 partidas 5D y 29 tareas 4D |
| Refuerzo | 12,26 MB | 156.852 | IFC4, 0 errores | 64.849 barras con su geometría (292.289 kg) y 2 partidas 5D |

Se partió en dos porque un solo archivo pasaba de ≈ 15 MB. Validación con IfcOpenShell 0.9.0 en un entorno aparte (no es dependencia del sitio; cálculo propio):

- Esquema IFC4 y reglas EXPRESS: 0 errores en los dos archivos.
- Los 4.583 elementos del modelo están en el IFC, con los mismos conteos en las 31 clases.
- Concreto: 2.600,1 m³ en las cantidades y 2.598,7 m³ medidos sobre la geometría (diferencia de 1,3 m³, 0,05 %); acero: 292.289 kg en las cantidades y en el modelo, con las 64.849 barras dibujadas.
- Una muestra de 79 elementos y 43 barras tiene la misma caja envolvente que el modelo, con diferencias de 0,5 mm o menos.
- 5D: las 66 y 2 partidas del presupuesto llevan el mismo valor que el presupuesto; 4D: 29 tareas, 0 errores.
- Georreferenciación igual en los dos archivos y en el modelo.

## 12. El modo «Modelo BIM» en la vista

Árbol del modelo por disciplina, nivel y clase, con contadores, buscador, aislar, ocultar y transparencia; propiedades del elemento (conjuntos de propiedades, cantidades, 5D, 4D y norma); cortes horizontales por nivel y verticales por eje con tapa; la cimentación con el terreno semitransparente, los pilotes hasta su punta y sus cotas; el refuerzo del elemento elegido en 3D con sus etiquetas («16 N.º 8», estribos con su paso y su zona confinada) y el esquema 2D del despiece; los colores del último cálculo sísmico; la tabla 5D por disciplina y capítulo frente al presupuesto; el deslizador 4D; la lista de interferencias con «Ir a»; y la descarga de los dos IFC. Para no saturar el dibujo, el refuerzo se dibuja solo del elemento o del eje elegido (documento 9).

## 13. Alineado con el proyecto tipo

La torre mantiene la lógica estructural del proyecto tipo DNP 2018 (pórticos de concreto reforzado modulares sobre una retícula repetible), escalada a la retícula de 7,20 m, múltiplo del módulo de 1,20 m de la Res. 1633. Frente al tipo (dato oficial del tipo y cálculo propio de la torre; lo que el tipo no trae dice «por confirmar»):

| Tema | Proyecto tipo DNP 2018 | Torre | Frente al tipo |
|---|---|---|---|
| Sistema estructural | Pórticos de concreto de un piso con viga-canal en voladizo; placa maciza de 0,12 m | Dual: 5 muros de concreto de 0,35 m en los núcleos y pórticos con columnas de 0,80 m (0,90 m en el eje A) y vigas de 0,40 × 0,80 m | Se aparta: 4 pisos y edificación indispensable |
| Capacidad de disipación | Por confirmar en el PDF del tipo | Moderada (DMO), R = 4,86, con criterios de capacidad especial en columnas | Mejora (por confirmar) |
| Cimentación | Superficial, en concreto de 3.000 psi | 146 pilotes de 0,60 m × 15 m bajo 20 dados y 2 losas de pilotes | Se aparta: suelo aluvial y 4 pisos |
| Cuantías por m² | Por confirmar en el PDF; estructura con cimentación a $1.541.451 por m² | 0,74 m³ de concreto y 86,4 kg de acero por m² construido de la torre; estructura con cimentación a $2.248.544 por m² con el prediseño (1,46 veces el tipo; 1,15 veces con el presupuesto vigente) | Se aparta (por confirmar) |
| Luces | 7,60 × 4,30 m | 7,20 m en x; de 4,80 a 8,40 m en y, múltiplos de 1,20 m | Se aparta: módulo de la Res. 1633 |
| Alturas | 1 piso de ≈ 4,36 m | Entrepisos de 4,50 m y 4,20 m; 3,00 m libres bajo cielo raso; 0,40 m entre las vigas y el cielo para redes | Mejora (por confirmar) |

El detalle está en la tarjeta «Contraste con el proyecto tipo» de la vista y en el documento 11.

## 14. Límites

- **Modelo de prefactibilidad: no reemplaza los diseños firmados.** Arquitectura sobre un anteproyecto ilustrativo; estructura, cimentación y refuerzo sobre un prediseño sin firmar; capacidad de los pilotes estimada sin estudio geotécnico.
- Equipamiento fijo y dotación como cajas con la medida del catálogo, sin fabricante.
- Las redes (gases, agua, electricidad, datos, climatización) no están modeladas como tuberías y ductos: solo sus terminales y equipos, y los ductos verticales como aberturas. La coordinación con las redes queda para el diseño técnico.
- El reparto de las etapas del cronograma por piso y disciplina es una estimación.
- La altura del ±0,00 sobre el mar es una estimación hasta el levantamiento topográfico.

## 15. Lo que falta y próximos pasos

- Ajustar el presupuesto con el prediseño estructural (+$1.310 M a +$1.390 M de costo directo) cuando el diseño estructural y el estudio geotécnico lo confirmen.
- Corregir el doble conteo de los equipos que van dentro de los kits en las cantidades 5D de la dotación ($257,9 M).
- Llevar el modelo a LOD 300-350 con los diseños firmados: modelar las redes y repetir la detección de interferencias con ellas.
- Confirmar la adopción colombiana de la serie ISO 19650, el texto de la Estrategia Nacional BIM 2020-2026 y si la entidad que financie exige BIM y con qué requisitos de información.
- Confirmar la altura del ±0,00, el tipo de suelo, la capacidad de los pilotes y el nivel freático.
- Resolver en el detallado las 683 interferencias medias (cruces y separación de barras en nudos y bordes de muro).

## 16. Fuentes

- ISO 19650-1:2018 y 19650-2:2018, *Organization and digitization of information about buildings and civil engineering works, including building information modelling (BIM)*: <https://www.iso.org/standard/68078.html>
- ISO 7817-1:2024, *Building information modelling — Level of information need* (antes EN 17412-1:2020): <https://www.iso.org/standard/82914.html> (por confirmar)
- ISO 16739-1:2018, *Industry Foundation Classes (IFC) for data sharing in the construction and facility management industries* (IFC4 ADD2 TC1): <https://technical.buildingsmart.org/standards/ifc/ifc-schema-specifications/>
- IfcOpenShell 0.9.0: <https://ifcopenshell.org>
- EPSG:9377, MAGNA-SIRGAS 2018 / Origen-Nacional (IGAC): <https://epsg.io/9377>
- Reglamento Colombiano de Construcción Sismo Resistente NSR-10 (Títulos A, C y H; numerales citados en el documento 14, varios por confirmar).
- Res. 485 de 2025, MinSalud (requisitos del concepto técnico de viabilidad): <https://www.minsalud.gov.co/Normatividad_Nuevo/Resolucion%20No%20485%20de%202025.pdf>
- Proyecto tipo DNP de infraestructura básica en salud (2018): <https://proyectostipo.dnp.gov.co/images/pdf/salud/PTsalud.pdf>
- Datos del atlas: modelo BIM federado, validación del IFC e interferencias (carpeta `data/bim/`), los dos archivos IFC4 (carpeta `web/models/`), prediseño estructural (carpeta `data/sismo/`) y presupuesto, inventario y contraste de la torre (carpeta `data/proyectos/torre_hospital/`).
