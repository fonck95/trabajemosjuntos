# 13 · Red de distribución eléctrica y de datos de la microrred: precios, supuestos y APU

**Cuánto cuesta cada kilómetro de red para unir las sedes públicas de Yondó: media tensión de 13,2 kV, baja tensión, fibra óptica y canalización subterránea, con sus capítulos (por mayores), sus ítems (por menores) y el análisis de precio de cada ítem principal. Las distancias por las calles se calculan aparte y se cruzan con estos precios en la sección 9.**

> Estado: **prefactibilidad (clase 4: −30 % / +50 %)**, con fecha de corte del 22 de octubre de 2026. Cada cifra dice si es un **dato oficial** (copiado de la fuente), un **dato de mercado** (precio publicado por un comercio, con fecha de consulta), un **cálculo propio** (operación sobre datos oficiales, con el método a la vista) o una **estimación** (supuesto con rango, por confirmar con tres cotizaciones). Todo está en pesos constantes de 2026. Los datos completos están en `data/red/precios_unitarios.json` (214 ítems), `data/red/parametros.json` (cantidades por km), `data/red/apu_red.json` (19 APU), `data/red/subestacion.json`, `data/red/distancias.json` (distancias por las calles) y `data/red/presupuesto_red.json` (presupuesto de la red propuesta, sección 9).
>
> **Inspirado en los proyectos tipo del DNP.** El DNP no tiene un proyecto tipo de redes de distribución eléctrica ni de fibra óptica (en Minas y Energía solo publica "Celdas solares uso residencial" y "Beneficio de oro"; en TIC, "Zonas digitales", "Implementación de TIC" y "Centro TIC municipal"). Por eso este capítulo toma del proyecto tipo su **forma**: presupuesto por capítulos, análisis de precios unitarios (APU) por ítem, cantidades por unidad de obra y especificaciones de referencia. Y toma las **piezas tipo** de las dos fuentes que en Colombia hacen de "proyecto tipo" para redes: las **unidades constructivas de la CREG** (Resolución 015 de 2018), que son los precios con los que se remunera cada poste, km de cable o transformador en todo el país, y las **estructuras normalizadas de EPM** (normas RA), que dicen exactamente qué lleva cada poste en Antioquia.

## En pocas palabras

- **Un km de red de media tensión aérea en el casco urbano cuesta unos 152,9 millones** (cálculo propio con insumos estimados; rango 122–199 M), ya con AIU. Lleva 25 postes de 12 m, 4 conductores y sus vientos y puestas a tierra. La suma de las unidades constructivas de la CREG para ese mismo km da 179,3 M, con ingeniería incluida.
- **En zona rural** (vía a la PTAP, a los pozos y a la PTAP veredal) el km baja a **86,7 M** porque el vano sube de 40 a 80 m (CREG: 103,7 M). Ahí hay que sumar servidumbre y poda: unos 13 M por km (estimación).
- **La baja tensión trenzada** sobre los mismos postes cuesta **36,7 M por km**, y **la fibra óptica ADSS de 24 hilos** sobre postes existentes, **12,9 M por km** (48 hilos: 27,8 M), más un arriendo de unos $900.668 al año por km si los postes son de EPM (tope regulado por la CRC). Conectar cada sede a la fibra (NAP, acometida y ONU) cuesta 2,2 M y el nodo central del CCED (OLT y switch), 41,2 M.
- **Enterrar la red multiplica el costo por siete:** un km de media tensión subterránea con canalización de 4 ductos, cámaras cada 50 m y cable XLPE cuesta **1.124 M** (CREG: 1.183 M). Solo se justifica en cruces, plazas o frente al hospital.
- **Un transformador trifásico de 75 kVA instalado en poste cuesta unos 46,8 M** y uno monofásico de 25 kVA, 25,3 M. La acometida trifásica de una sede con medidor bidireccional y comunicación, **13,7 M**.
- **Indirectos:** AIU de 27 % (estimación, rango 24–32 %), interventoría de 8 % (la mediana de 9 contratos de redes en SECOP, 6 de ellos de Yondó, es 7,7 %), ingeniería de detalle de 4 % y trámites con EPM.
- **La red propuesta** une 22 puntos (las sedes públicas, la torre del hospital y el parque del relleno) con 21 tramos y **10,066 km de red nueva**: 4,596 km urbanos y 5,47 km rurales. Cuesta **unos $2.965 millones** (cálculo propio, rango $2.075–4.447 M), unos $295 M por km de red con transformadores, acometidas, protecciones, fibra e indirectos; solo la media tensión sale a unos $117 M por km (sección 9).
- **La subestación de EPM en Yondó no se pudo ubicar** con evidencia verificable. Se descartaron tres patios eléctricos de Ecopetrol (el más grande, el de la planta de inyección de agua de Casabe, 4 km al norte). Para la red de la microrred no hace falta llegar hasta ella: la red de 13,2 kV de EPM ya pasa por todas las calles. Queda un derecho de petición a EPM (sección 8). Ojo: `docs/12` sí usa una ubicación probable, el lugar de Google "Subestación yondo epm" (7,0032 N, −73,9226 O); de ese punto dependen los 2,6 km de línea y los $990 M de conexión del parque. Hay que confirmarlo con EPM.

### Palabras que se usan

- **Media tensión (MT):** la red de 13,2 kV que va por los postes altos y llega a los transformadores. **Baja tensión (BT):** la de 120/220 V que sale del transformador hacia las sedes.
- **Vano:** distancia entre dos postes. **Estructura:** lo que se arma en la punta del poste (cruceta, aisladores y herrajes). **Retención** o **terminal:** estructura que aguanta el tiro del cable en ángulos o al final de la línea. **Viento** o **retenida:** el cable de acero que va del poste al piso para que no se incline.
- **Puesta a tierra:** varilla de cobre enterrada y unida al poste o al equipo para descargar rayos y fallas. **Cortacircuitos** y **DPS:** fusible y pararrayos que protegen el transformador.
- **ADSS:** cable de fibra óptica totalmente dieléctrico (sin metal) que se cuelga de los postes de energía. **NAP:** caja de la fibra en el poste de donde sale la acometida de cada sede. **OLT** y **ONU:** equipo central y equipo de cada sede de una red de fibra GPON.
- **APU (análisis de precios unitarios):** la hoja que dice cuánto material, equipo, transporte y mano de obra lleva una unidad de obra. **Costo directo:** la suma de todo eso. **AIU:** administración, imprevistos y utilidad del contratista, que se suman al costo directo.
- **UC (unidad constructiva):** pieza tipo con la que la CREG valora las redes de todos los operadores del país.

## 1. Cómo se usa: por mayores y por menores

Un presupuesto de red se arma en dos niveles:

- **Por mayores (capítulos):** cada capítulo es una parte de la obra con su precio por km o por unidad. Sirve para comparar alternativas de trazado rápidamente.
- **Por menores (ítems):** cada capítulo se abre en los ítems que de verdad se compran e instalan (postes, estructuras, conductor, vientos, puestas a tierra…), con sus cantidades y su APU. Es lo que se contrata.

Los capítulos que se usarán por tramo son estos:

| Capítulo (por mayor) | Unidad | Ítems (por menores) | Precio de referencia (con AIU) |
|---|---|---|---|
| 1. Preliminares y gestión | km y global | Topografía y replanteo; trámites con EPM; certificado RETIE; plan de manejo ambiental y de tránsito; servidumbre y poda (rural) | $1.800.000/km + $2.500.000/km + $6.000.000 global |
| 2. Red de MT aérea 13,2 kV | km | Postes (APU-01/01b), estructuras de suspensión, retención y terminal (APU-02/03/03b), vientos (APU-04), puestas a tierra (APU-05), conductor | Urbana $152.942.069; rural $86.747.371 |
| 3. Protección y maniobra | un | Reconectador, seccionadores, cortacircuitos, DPS, indicadores de falla | Reconectador $74.783.431 (CREG) |
| 4. Red de MT subterránea | m y km | Canalización (APU-10), cámaras (APU-10b), cable XLPE, transiciones | $1.124.367.176/km |
| 5. Transformación | un | Transformador instalado según capacidad (APU-08 y variantes) | 25 kVA $25.326.717 a 112,5 kVA $58.871.866 |
| 6. Red de BT y acometidas | km y un | Trenzado (APU-07), postes de 10 m si hacen falta (APU-01c), acometida con medidor bidireccional (APU-11) | $36.711.209/km; $13.666.966 por sede |
| 7. Red de datos | km y un | Fibra ADSS 24 o 48 hilos (APU-09), conexión de cada sede con NAP y ONU (APU-13), nodo central con OLT y switch en el CCED (APU-14) | $12.923.326/km (24 h); $2.152.090 por sede; $41.220.943 el nodo |
| 8. Indirectos | % | AIU 27 % (ya dentro de los APU), ingeniería 4 %, PMA 1,5 %, interventoría 8 % | — |

**Regla para un tramo de longitud L (km), medida por las calles:** red de MT = L × precio por km (urbano o rural); postes nuevos = redondeo hacia arriba de L × postes por km + 1; fibra = L × precio por km; canalización = L × 1.000 × precio por metro + una cámara cada 50 m; a eso se suman transformadores y acometidas por sede, los preliminares por km y, al final, ingeniería, trámites e interventoría. Las reglas completas están en `data/red/parametros.json` → `reglas_presupuesto_por_tramo`.

## 2. Proyecto tipo de referencia: de dónde sale cada pieza

| Pieza | Fuente | Qué aporta | Tipo |
|---|---|---|---|
| Forma del presupuesto | Proyectos tipo del DNP (catálogo consultado el 22-oct-2026) | Capítulos, APU, cantidades por unidad y especificaciones; no hay proyecto tipo de redes | Oficial |
| Precio techo por pieza | Res. CREG 015 de 2018, cap. 14 (unidades constructivas) | Valor instalado de cada estructura, km de conductor, transformador y equipo, con montaje, obra civil e ingeniería | Oficial, actualizado con IPP |
| Qué lleva cada poste | Normas de construcción de EPM (RA2-001, RA2-003, RA2-004, RA2-011, RA2-021, RA3-026, RA3-029…) | Lista exacta de materiales por estructura y vanos máximos (60 m urbano; 90 m rural) | Oficial |
| APU de una obra pública de Antioquia | Gobernación de Antioquia, base de APU de la Secretaría de Infraestructura Física, 2020-II, cap. 17 | Rendimientos, jornales y precios de materiales eléctricos de una entidad del departamento | Oficial, actualizado con IPC |
| Precios de hoy | Homecenter (transformadores) y Fenix Comercial (fibra y equipos de red), 22-oct-2026 | Precios publicados en Colombia en 2026 | Mercado |
| Interventoría | SECOP I y II (9 contratos de obra con su interventoría) | Porcentaje real pagado | Cálculo propio |

## 3. Fuentes y cómo se llevan a pesos de 2026

| Fuente | Año de los precios | Cómo se actualiza | Factor |
|---|---|---|---|
| CREG 015 de 2018 | Diciembre de 2017 | IPP de oferta interna del DANE (el mismo índice que usa la CREG): promedio ene–sep 2026 (186,81) ÷ dic-2017 (113,41) | 1,6472 |
| APU de la SIF de Antioquia | Abril de 2020 | IPC del repositorio (`data/fuentes/ipc_dane.csv`) | 1,50538 |
| Tope de arriendo de postes de la CRC | Pesos de 2023 | IPC | 1,181514 |
| Homecenter y Fenix | Octubre de 2026 | Ninguna (a Fenix se le suma el IVA del 19 %, porque publica "+ IVA") | 1,00 |

Dos advertencias. **Primera:** los valores de la CREG son los que se reconocen a los operadores de red, que compran a gran escala; sirven de techo de comparación, pero ya incluyen ingeniería y montaje, así que no se les suma AIU. **Segunda:** el transformador de 25 kVA que la CREG reconoce instalado en $11,0 millones cuesta $11,4 millones solo el equipo en un almacén de 2026. La brecha no la explica la inflación de los insumos: según el IPP del DANE, la clase "motores, generadores y transformadores eléctricos" (2710) subió ×1,30 entre diciembre de 2017 y 2026, menos que el IPP total (×1,65) con el que aquí se actualiza la CREG. La diferencia está en que la CREG valora compras al por mayor de los operadores de red y el almacén vende al detal. Por eso los transformadores son el ítem que más necesita cotizaciones de fabricante.

## 4. Precios unitarios de referencia

### 4.1 Valores regulatorios de la CREG (referencia, ya incluyen montaje e ingeniería)

| Código | Unidad constructiva | Unidad | Dic-2017 (oficial) | 2026 (cálculo propio) |
|---|---|---|---|---|
| N2L70 | Estructura en poste de concreto de 12 m y 510 kg, suspensión, nivel 2 (13,2 kV), instalada | un | $3.215.000 | $5.295.904 |
| N2L72 | Estructura en poste de concreto de 12 m y 750 kg, retención, nivel 2, instalada | un | $4.086.000 | $6.730.657 |
| N2L71 | Estructura en poste de concreto de 12 m y 1.050 kg, retención, nivel 2, instalada | un | $4.226.000 | $6.961.272 |
| N2L83 | km de conductor ACSR 1/0 AWG (3 fases), tendido | km | $14.814.000 | $24.402.338 |
| N2L84 | km de conductor ACSR 2/0 AWG (3 fases), tendido | km | $16.647.000 | $27.421.745 |
| N2L96 | km de conductor semiaislado 1/0 AWG (3 fases), tendido | km | $23.386.000 | $38.522.552 |
| N2L97 | km de conductor semiaislado 2/0 AWG (3 fases), tendido | km | $30.990.000 | $51.048.229 |
| N2L137 | Sistema de puesta a tierra, diseño típico, nivel 2 | un | $270.000 | $444.757 |
| N2L77 | Canalización urbana 4 ductos de 4" (nivel 2), por km (incluye cámaras y obra civil) | km | $525.751.000 | $866.042.509 |
| N2L127 | km de cable de cobre aislado XLPE o EPR 15 kV, 1/0 AWG (3 fases), instalado | km | $192.490.000 | $317.078.850 |
| N2EQ12 | Juego de cortacircuitos (3), nivel 2, instalado | juego | $1.200.000 | $1.976.698 |
| N2EQ15 | Juego de pararrayos (3), nivel 2, instalado | juego | $962.000 | $1.584.653 |
| N2EQ13 | Juego de cuchillas de operación sin carga, nivel 2, instalado | juego | $1.003.000 | $1.652.190 |
| N2EQ29 | Seccionalizador manual bajo carga 400 A, nivel 2, instalado | un | $20.319.000 | $33.470.441 |
| N2EQ35 | Reconectador, nivel 2, instalado | un | $45.399.000 | $74.783.431 |
| N2EQ11 | Indicador de falla, nivel 2, instalado | un | $1.124.000 | $1.851.507 |
| N2EQ31 | Transición aérea–subterránea, nivel 2 (terminales y DPS en poste) | un | $1.260.000 | $2.075.533 |
| N1T5 | Transformador aéreo monofásico urbano de 25 kVA, instalado (nivel 1) | un | $6.686.000 | $11.013.503 |
| N1T6 | Transformador aéreo monofásico urbano de 37,5 kVA, instalado | un | $7.133.000 | $11.749.823 |
| N1T12 | Transformador aéreo trifásico urbano de 45 kVA, instalado | un | $9.446.000 | $15.559.909 |
| N1T14 | Transformador aéreo trifásico urbano de 75 kVA, instalado | un | $11.958.000 | $19.697.797 |
| N1T15 | Transformador aéreo trifásico urbano de 112,5 kVA, instalado | un | $13.265.000 | $21.850.750 |
| N1T18 | Transformador pedestal (pad-mounted) trifásico de 75 kVA, instalado | un | $39.854.000 | $65.649.439 |
| N1P50 | Poste de concreto de 10 m urbano, suspensión, red trenzada, instalado | un | $813.000 | $1.339.213 |
| N1L56 | km de conductor por fase, aéreo urbano, trenzado de aluminio 1/0 (nivel 1), instalado | km-fase | $10.612.500 | $17.481.424 |
| N1C8 | Canalización con 4 ductos (nivel 1), instalada | m | $185.000 | $304.741 |
| N1C1 | Caja para redes subterráneas tipo sencillo, instalada | un | $1.519.000 | $2.502.170 |
| N1C2 | Caja para redes subterráneas tipo doble, instalada | un | $3.755.000 | $6.185.418 |
| N4L93 | km de cable de fibra óptica ADSS monomodo (UC de líneas de nivel 4, de 57,5 a 220 kV, como las de 115 kV), instalado | km | $30.407.000 | $50.087.883 |

Fuente: Res. CREG 015 de 2018, cap. 14, tablas 12, 14, 19, 25, 26, 29 y 31 (gestornormativo.creg.gov.co). Las UC de nivel 2 suponen 3 conductores; con neutro (4 conductores) se multiplica el conductor por 4/3, como dice la propia resolución.

### 4.2 APU oficiales de la Gobernación de Antioquia (2020, sin AIU)

| Ítem SIF | Descripción | Unidad | 2020 (oficial) | 2026 (cálculo propio) |
|---|---|---|---|---|
| 17.13 | Suministro, transporte e instalación (STI) de poste de concreto reforzado de 12 m (1.052 kg), sin vestida | un | $1.097.170 | $1.651.658 |
| 17.14 | STI de vestida de poste según normas EPM (2 crucetas de 1,5 m, 6 aisladores de suspensión, herrajes de retención) | un | $1.169.465 | $1.760.489 |
| 17.18 | STI de viento (retenida) convencional | un | $260.480 | $392.121 |
| 17.12 | STI de línea trifásica en cable compacto 1/0 (3 × ACSR protegido 1/0 + mensajero y separadores), por metro | m | $54.598 | $82.191 |
| 17.1 | STI de transformador monofásico 5 kVA 7.620-480/240 V con puesta a tierra (malla 15 m, 3 varillas) según RA3-026 | un | $5.745.532 | $8.649.209 |
| 17.6 | STI de poste de concreto reforzado de 10 m | un | $884.422 | $1.331.391 |
| 17.17 | Retiro e instalación de transformador (mano de obra y grúa) | un | $763.750 | $1.149.734 |
| 17.21 | Traslado de poste de concreto, desnudo, hasta 5 km | un | $311.019 | $468.202 |

La misma base trae los jornales de 2020: oficial eléctrico $118.167 y ayudante $76.809 por día con 75 % de prestaciones ($177.886 y $115.627 en pesos de 2026), que sirven para contrastar los jornales de la sección 4.5.

### 4.3 Precios de mercado consultados el 22 de octubre de 2026

| Código | Producto | Unidad | Precio (con IVA) | Fuente |
|---|---|---|---|---|
| TR-25-1F | Transformador monofásico tipo poste en aceite, 25 kVA, 13.200 V (Ecuatran), solo equipo | un | $11.390.900 | Homecenter |
| TR-37-1F | Transformador monofásico tipo poste en aceite, 37,5 kVA, 13.200 V (Ecuatran), solo equipo | un | $12.592.900 | Homecenter |
| FO-ADSS24-4K | Cable de fibra óptica ADSS G.652D monomodo 24 hilos, span 100 m, en carrete de 4 km | m | $6.209 | Fenix Comercial |
| FO-ADSS24-1K | Cable de fibra óptica ADSS G.652D monomodo 24 hilos, span 100 m, por kilómetro suelto | m | $9.274 | Fenix Comercial |
| FO-ADSS48-1K | Cable de fibra óptica ADSS G.652D monomodo 48 hilos, span 100 m, por kilómetro | m | $16.677 | Fenix Comercial |
| FO-HSUS | Herraje de suspensión tipo J para ADSS Φ 10–15 mm | un | $24.640 | Fenix Comercial |
| FO-REMATE | Remate preformado (retención) para ADSS span 100 m, Φ 10–11 mm | un | $16.755 | Fenix Comercial |
| FO-RAQ | Par de raquetas de reserva para cable ADSS, 12" | par | $93.961 | Fenix Comercial |
| FO-CEMP | Caja de empalme exterior IP65, aérea, hasta 144 empalmes | un | $425.782 | Fenix Comercial |
| FO-NAP16 | Caja de distribución (NAP) exterior para 24 empalmes con 16 acopladores SC/APC | un | $261.679 | Fenix Comercial |
| FO-FLEJE | Fleje de acero inoxidable 304 de 3/4", 0,70 mm (rollo de 30,5 m) | m | $4.718 | Fenix Comercial |
| FO-SPL8 | Splitter PLC 1×8 con conectores SC/APC | un | $140.284 | Fenix Comercial |
| FO-ODF48 | Distribuidor de fibra (ODF) 19" para 48 adaptadores LC dúplex, vacío | un | $323.772 | Fenix Comercial |
| NET-OLT16 | OLT GPON de 16 puertos con 8 uplinks (4 GE + 4 SFP) | un | $18.904.079 | Fenix Comercial |
| NET-OLT8 | OLT GPON de 8 puertos | un | $8.530.580 | Fenix Comercial |
| NET-ONU | ONU (ONT) GPON con 4 puertos Gigabit y WiFi 2,4 GHz | un | $399.416 | Fenix Comercial |
| NET-SWL3 | Switch industrial administrable capa 3, 16 puertos GE + 4 SFP+ 10G | un | $8.484.093 | Fenix Comercial |
| NET-SWL2 | Switch industrial administrable capa 2, 4 puertos PoE + 2 SFP | un | $3.027.780 | Fenix Comercial |
| NET-SFP | Transceptor SFP 1G LX BiDi monomodo, 20 km | un | $266.199 | Fenix Comercial |

Los transformadores trifásicos no tienen precio publicado; se estimaron con una regla de escala sobre el de 37,5 kVA (ver 4.4). El carrete de 4 km de fibra de 48 hilos aparece en el mismo catálogo a $15.810.273 + IVA, más barato que el de 24 hilos: es un valor atípico y no se usa.

### 4.4 Insumos estimados (con su ancla)

| Código | Insumo | Unidad | Precio 2026 | Rango | Ancla |
|---|---|---|---|---|---|
| POSTE-12-510 | Poste de concreto octogonal de 12 m y 510 kgf (RA7-035), puesto en planta, con IVA | un | $1.050.000 | $900.000–$1.300.000 | Ancla oficial: la SIF 2020 pagó $835.000 por un poste de 12 m de 1.052 kg ($1.256.992 en pesos de 2026 con IPC). El de 510 kgf lleva menos acero: se toma 16 % menos (estimación). El IPC es un techo prudente: el IPP del DANE de… |
| POSTE-12-750 | Poste de concreto octogonal de 12 m y 750 kgf, puesto en planta, con IVA | un | $1.150.000 | $1.000.000–$1.450.000 | Misma ancla (SIF 2020, poste de 12 m y 1.052 kg, actualizado con IPC): 8 % menos por menor refuerzo (estimación). En la CREG la estructura de retención con poste de 750 kg vale 3 % menos que con poste de 1.050 kg (N2L72 frente… |
| POSTE-12-1050 | Poste de concreto octogonal de 12 m y 1.050 kgf, puesto en planta, con IVA | un | $1.256.992 | $1.134.765–$1.600.000 | Cálculo sobre dato oficial: SIF 2020, poste de 12 m de 1.052 kg a $835.000 × IPC 2020→2026 (1,50538). Límite bajo del rango: con el IPP de minerales no metálicos (×1,359). La versión anterior ponía $1.750.000, 39 % por encima… |
| POSTE-10-510 | Poste de concreto de 10 m y 510 kgf, puesto en planta, con IVA | un | $1.000.000 | $800.000–$1.250.000 | Ancla: SIF 2020, poste de 10 m a $670.000 ($1.008.605 con IPC). |
| CRU-15 | Cruceta angular metálica galvanizada de 1.500 mm (RA7-013) | un | $95.000 | $75.000–$140.000 | Ancla: SIF 2020, cruceta de 1.500 mm a $55.000 ($82.796 con IPC). |
| CRU-24 | Cruceta angular metálica galvanizada de 2.400 mm (RA7-013) | un | $150.000 | $110.000–$220.000 | Proporcional a la de 1.500 mm por peso de acero. |
| AIS-PIN | Aislador tipo pin 13,2 kV (porcelana ANSI 55-5 o polimérico) | un | $38.000 | $25.000–$60.000 | Sin cotización; precio de distribuidor esperado. |
| AIS-SUS | Aislador de suspensión polimérico 13,2 kV, 165 mm (RA7-011) | un | $40.000 | $30.000–$65.000 | Ancla: SIF 2020, aislador polimérico de suspensión a $25.000 ($37.635 con IPC). |
| GRAPA-T | Grapa terminal (recta o pistola) para ACSR 1/0–2/0 | un | $30.000 | $22.000–$45.000 | Ancla: SIF 2020, $18.000 ($27.097 con IPC). |
| ACSR-10 | Conductor ACSR 1/0 AWG (Raven), con IVA | m | $4.800 | $3.800–$6.000 | Sin cotización local. Anclas: la UC CREG N2L83 actualizada equivale a $8.134 por metro de fase ya tendido; precios de exportación de 0,43–0,69 €/m (Alibaba) y 0,78 USD/pie al detal en EE. UU. |
| ACSR-20 | Conductor ACSR 2/0 AWG (Quail), con IVA | m | $6.000 | $4.700–$7.500 | Proporcional al peso (272 frente a 216 kg/km del 1/0). |
| SEMIAIS-10 | Cable protegido (semiaislado) 15 kV 1/0 para red compacta, con IVA | m | $15.800 | $12.000–$19.000 | Ancla: SIF 2020, "cable ACSR protegido 1/0" a $10.500/m ($15.806 con IPC). |
| TRENZ-3x10 | Cable trenzado de aluminio 3 × 1/0 AWG + neutro portante 1/0, con IVA | m | $22.000 | $17.000–$28.000 | Sin cotización. Ancla: la UC CREG N1L56 equivale a $52.444 por metro de red trifásica ya instalada (incluye herrajes y mano de obra). |
| XLPE-15-10 | Cable monopolar de cobre 1/0 AWG XLPE 15 kV, aislamiento 133 %, con IVA | m | $85.000 | $65.000–$110.000 | Sin cotización. Ancla: UC CREG N2L127 = $105.693 por metro de fase instalado. |
| CU-2D | Cable de cobre desnudo 2 AWG, 7 hilos | m | $17.000 | $12.000–$22.000 | Ancla: SIF 2020, $8.500/m ($12.796 con IPC); el cobre subió por encima del IPC. |
| VARILLA | Varilla de puesta a tierra copperweld de 5/8" × 2,40 m | un | $85.000 | $65.000–$110.000 | Ancla: SIF 2020, $55.000 ($82.796 con IPC). |
| CORTAC | Cortacircuitos 15 kV 100 A con portafusible (caja primaria), con IVA | un | $445.000 | $320.000–$600.000 | Ancla: SIF 2020, "caja primaria" a $295.000 ($444.087 con IPC). |
| DPS-12 | DPS (pararrayos) de óxido metálico 12 kV polimérico, con IVA | un | $250.000 | $180.000–$350.000 | Ancla: SIF 2020, DPS a $165.000 ($248.388 con IPC). |
| TR-45-3F | Transformador trifásico tipo poste en aceite, 45 kVA, 13.200/220-127 V, solo equipo | un | $18.263.241 | $14.610.593–$23.742.214 | Cálculo propio sin cotización: precio del monofásico de 37,5 kVA de Homecenter × (kVA/37,5)^0,6 (regla de escala de equipos) × 1,30 (tres núcleos y bobinas, más bujes y tanque) |
| TR-75-3F | Transformador trifásico tipo poste en aceite, 75 kVA, 13.200/220-127 V, solo equipo | un | $24.813.447 | $19.850.758–$32.257.481 | Cálculo propio sin cotización: precio del monofásico de 37,5 kVA de Homecenter × (kVA/37,5)^0,6 (regla de escala de equipos) × 1,30 (tres núcleos y bobinas, más bujes y tanque) |
| TR-1125-3F | Transformador trifásico tipo poste en aceite, 112,5 kVA, 13.200/220-127 V, solo equipo | un | $31.647.679 | $25.318.143–$41.141.982 | Cálculo propio sin cotización: precio del monofásico de 37,5 kVA de Homecenter × (kVA/37,5)^0,6 (regla de escala de equipos) × 1,30 (tres núcleos y bobinas, más bujes y tanque) |
| MED-BID | Medidor electrónico bidireccional trifásico clase 0,5S/1 semidirecto, con puerto de comunicación (homologado por EPM) | un | $1.500.000 | $900.000–$2.500.000 | Sin cotización |
| MODEM-AMI | Módem o módulo de comunicación (celular, LoRaWAN o RS-485) para el medidor | un | $450.000 | $250.000–$800.000 | Coherente con el rango de 2–5 M COP por punto de medición instalado de data/presupuesto_microrred.json. |
| CAJA-MED | Celda o caja de medida trifásica con totalizador 3 × 200 A, sellable | un | $1.900.000 | $1.300.000–$2.800.000 | — |
| DUCTO-4 | Ducto PVC 4" tipo DB o TDP para canalización eléctrica (por metro) | m | $26.000 | $20.000–$35.000 | — |
| CONCRETO-21 | Concreto de 3.000 psi (21 MPa) hecho en obra, puesto en Yondó | m3 | $650.000 | $560.000–$800.000 | Ancla: SIF 2020, subanálisis de concreto de 3.000 psi a $393.125/m³ ($591.803 con IPC). |
| TAPA-CAMARA | Tapa y marco en ferroconcreto para cámara de 1,0 × 1,0 m, tráfico peatonal/vehicular liviano | un | $750.000 | $500.000–$1.100.000 | — |

El resto de los herrajes (tirantas, espigos, tuercas de ojo, eslabones, pernos, conectores, materiales de vientos y de puesta a tierra) está en el JSON con el mismo formato.

### 4.5 Mano de obra, equipo y transporte

| Código | Recurso | Unidad | Costo 2026 | Tipo | Nota |
|---|---|---|---|---|---|
| MO-CAPATAZ | Jornal de capataz o técnico electricista líder de cuadrilla, con prestaciones | día | $234.000 | Estimación | Básico mensual supuesto $3.900.000 (2,23 salarios mínimos de 2026, $1.750.905) ÷ 30 × factor prestacional 1,80 (seguridad social con ARL de riesgo V,… |
| MO-LINIERO | Jornal de liniero (oficial electricista de redes), con prestaciones | día | $180.000 | Estimación | Básico mensual supuesto $3.000.000 (1,71 salarios mínimos de 2026, $1.750.905) ÷ 30 × factor prestacional 1,80 (seguridad social con ARL de riesgo V,… |
| MO-AYUDANTE | Jornal de ayudante de liniería, con prestaciones | día | $126.000 | Estimación | Básico mensual supuesto $2.100.000 (1,20 salarios mínimos de 2026, $1.750.905) ÷ 30 × factor prestacional 1,80 (seguridad social con ARL de riesgo V,… |
| MO-EMPALMADOR | Jornal de técnico empalmador de fibra óptica, con prestaciones | día | $198.000 | Estimación | Básico mensual supuesto $3.300.000 (1,88 salarios mínimos de 2026, $1.750.905) ÷ 30 × factor prestacional 1,80 (seguridad social con ARL de riesgo V,… |
| MO-OFICIAL | Jornal de oficial de obra civil, con prestaciones | día | $147.000 | Estimación | Básico mensual supuesto $2.450.000 (1,40 salarios mínimos de 2026, $1.750.905) ÷ 30 × factor prestacional 1,80 (seguridad social con ARL de riesgo V,… |
| MO-OBRERO | Jornal de obrero (ayudante de obra civil), con prestaciones | día | $105.054 | Estimación | Básico mensual supuesto $1.750.905 (1,00 salarios mínimos de 2026, $1.750.905) ÷ 30 × factor prestacional 1,80 (seguridad social con ARL de riesgo V,… |
| CUAD-CMT | Cuadrilla de redes aéreas: 1 capataz + 2 linieros + 3 ayudantes (costo por día) | día | $972.000 | Cálculo propio | Suma de los jornales estimados de esta lista. |
| CUAD-CFO | Cuadrilla de fibra óptica: 1 empalmador + 1 liniero + 2 ayudantes (costo por día) | día | $630.000 | Cálculo propio | Suma de los jornales estimados de esta lista. |
| CUAD-CCIV | Cuadrilla de obra civil: 1 oficial + 4 obreros (costo por día) | día | $567.217 | Cálculo propio | Suma de los jornales estimados de esta lista. |
| CUAD-CPAR | Pareja: 1 liniero + 1 ayudante (costo por día) | día | $306.000 | Cálculo propio | Suma de los jornales estimados de esta lista. |
| EQ-GRUA | Camión grúa de brazo articulado (8–12 t) con canasta, operador y combustible | día | $1.800.000 | Estimación | Tarifa de alquiler esperada en el Magdalena Medio (Barrancabermeja); confirmar con 3 cotizaciones. |
| EQ-CAMIONETA | Camioneta 4×4 de cuadrilla con conductor y combustible | día | $380.000 | Estimación | Tarifa de alquiler esperada en el Magdalena Medio (Barrancabermeja); confirmar con 3 cotizaciones. |
| EQ-TENDIDO | Equipo de tendido: poleas, malacate, ranas, tensiómetro y pértigas | día | $250.000 | Estimación | Tarifa de alquiler esperada en el Magdalena Medio (Barrancabermeja); confirmar con 3 cotizaciones. |
| EQ-FUSION | Fusionadora de fibra, OTDR, cortadora de precisión y medidor de potencia | día | $450.000 | Estimación | Tarifa de alquiler esperada en el Magdalena Medio (Barrancabermeja); confirmar con 3 cotizaciones. |
| EQ-TELUR | Telurómetro y equipo de soldadura exotérmica | día | $120.000 | Estimación | Tarifa de alquiler esperada en el Magdalena Medio (Barrancabermeja); confirmar con 3 cotizaciones. |
| EQ-COMPACT | Vibrocompactador tipo canguro | día | $150.000 | Estimación | Tarifa de alquiler esperada en el Magdalena Medio (Barrancabermeja); confirmar con 3 cotizaciones. |
| EQ-MEZCLA | Mezcladora de concreto de 1 bulto | día | $90.000 | Estimación | Tarifa de alquiler esperada en el Magdalena Medio (Barrancabermeja); confirmar con 3 cotizaciones. |
| TR-POSTE | Transporte de un poste de 12 m desde la planta (Santander o Antioquia) hasta Yondó, con cargue y descargue | un | $350.000 | Estimación | Supone 8–10 postes por viaje de tractomula y un viaje de $2,8–3,5 M desde Bucaramanga o Puerto Berrío. La SIF 2020 pagaba $20.000 por poste y kilómetro solo… |
| TR-TRAFO | Transporte de un transformador de distribución hasta Yondó | un | $600.000 | Estimación |  |
| TR-ESCOMBRO | Retiro y disposición de sobrantes de excavación | m3 | $85.000 | Estimación |  |
| TR-MAT | Transporte de materiales menores hasta Yondó | % de materiales | 3 % (2–5 %) | Estimación | — |
| EQ-HM | Herramienta menor | % de mano de obra | 5 % | Estimación | — |

Los jornales parten del salario mínimo de 2026 ($1.750.905, Decreto 1469 de 2025 y Decreto 0159 de 2026) y de lo que se paga en la zona (un técnico electricista gana en promedio $2,39 M al mes en Colombia, y los mejor pagados, hasta $4,5 M, están en Bogotá, Medellín y zonas petroleras como Barrancabermeja, según Magneto365). El factor prestacional de 1,80 suma seguridad social con ARL de riesgo V (trabajo en altura y con tensión), parafiscales, prestaciones y dotación.

### 4.6 Preliminares, trámites e indirectos

| Código | Ítem | Unidad | Valor | Rango | Tipo |
|---|---|---|---|---|---|
| GES-TOPO | Topografía, replanteo con GPS y levantamiento de postes existentes | km | $1.800.000 | $1.200.000–$3.000.000 | Estimación |
| GES-EPM | Trámites con EPM: solicitud de factibilidad, estudio de conexión, revisión de diseños, recibo de obra y energización (por proyecto) | global | $6.000.000 | $2.000.000–$15.000.000 | Estimación |
| GES-RETIE-KM | Inspección y certificado de conformidad RETIE de red de MT por organismo acreditado | km | $2.500.000 | $1.500.000–$4.000.000 | Estimación |
| GES-RETIE-TR | Inspección y certificado RETIE por subestación de poste (transformador) | un | $1.000.000 | $600.000–$1.600.000 | Estimación |
| GES-RETIE-AC | Inspección RETIE de acometida y medida por sede | un | $600.000 | $400.000–$1.000.000 | Estimación |
| GES-SERV | Servidumbre para red aérea en tramo rural (franja de 15 m), avalúo y escritura | km | $10.000.000 | $4.000.000–$20.000.000 | Estimación |
| GES-PODA | Poda, rocería y despeje de franja en tramo rural | km | $3.000.000 | $1.500.000–$6.000.000 | Estimación |
| IND-AIU | AIU de obra: administración 19 % + imprevistos 3 % + utilidad 5 % = 27 % del costo directo | % | 27,0 % | 24,0 %–32,0 % | Estimación |
| IND-IVA-U | IVA del 19 % sobre la utilidad (contratos de obra con AIU) | % | 0,95 % | — | Cálculo propio |
| IND-INTERV | Interventoría técnica, administrativa y financiera (sobre el valor de la obra) | % | 8,0 % | 6,2 %–9,8 % | Cálculo propio |
| IND-ING | Ingeniería de detalle: diseño RETIE, memorias, planos, aprobación de EPM | % | 4,0 % | 3,0 %–6,0 % | Estimación |
| IND-PMA | Plan de manejo ambiental y de tránsito, señalización y SST de obra | % | 1,5 % | 1,0 %–2,5 % | Estimación |
| OPEX-POSTE | Arriendo mensual por punto de apoyo en poste de EPM de más de 10 m (fibra óptica en postes existentes), tope regulado (gasto de operación, no inversión) | poste-mes | $3.002 | — | Cálculo propio |

**De dónde sale el 8 % de interventoría** (dato oficial de cada contrato; el porcentaje es cálculo propio):

| Contrato de obra | Obra | Interventoría | % |
|---|---|---|---|
| [Yondó, electrificación de La Paz, Rompederos, El Amparo, Cimitarra y Barbacoas (2014)](https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=14-1-120659) | $2.696.062.128 | $255.351.440 | 9,5 % |
| [Yondó, redes de Bocas de San Francisco, ITE, La Congoja, No te Pases, La Rompida 1 y 2 y La Felicidad (2014)](https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=14-1-120658) | $3.672.156.031 | $255.351.440 | 7,0 % |
| [Yondó, electrificación de Caño Negro y Caño Bonito (2013–2014)](https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=13-1-107398) | $250.000.000 | $16.500.000 | 6,6 % |
| [Yondó, redes y acometidas de la vereda Jabonal (2015)](https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=15-1-144334) | $651.225.171 | $58.966.420 | 9,1 % |
| [Yondó, redes y acometidas de Puerto Matilde (2016)](https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=16-1-158064) | $228.845.368 | $19.000.000 | 8,3 % |
| [Yondó, redes y acometidas de Bellavista (2017)](https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=17-1-173703) | $1.095.249.059 | $76.667.434 | 7,0 % |
| [Santander, redes de MT y BT en varios municipios (2022)](https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.3444334) | $14.886.142.702 | $1.141.981.784 | 7,7 % |
| [Santander, redes de MT y BT en varios municipios (2023)](https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.3685607) | $12.599.562.327 | $781.485.951 | 6,2 % |
| [Guapotá (Santander), redes de MT y BT (2026)](https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.10269210) | $2.717.803.160 | $265.657.432 | 9,8 % |

La mediana es 7,7 %; se usa 8 %. El AIU de 27 % es una estimación: en Antioquia la administración carga, además del residente y las pólizas, la contribución de obra pública del 5 % (Ley 1106 de 2006) y las estampillas, que suman 6 a 9 puntos. Sobre la utilidad se liquida IVA del 19 % (Decreto 1372 de 1992, art. 3).

## 5. Supuestos de cantidades por km

### 5.1 Red de media tensión aérea

| Supuesto | Urbano | Rural | Base |
|---|---|---|---|
| Vano de diseño | 40 m (30–50) | 80 m (70–90) | Estimación; máximos de EPM: 60 m con estructuras RA2-001/RA2-021 y 90 m con RA2-011 (poste de 12 m, 20 % de la tensión de rotura, 7,0 y 6,5 m de distancia a tierra) |
| Postes por km | 25 (+1 por tramo) | 12,5 (+1 por tramo) | 1.000 m ÷ vano |
| Postes de retención por km | 5 (uno cada 200 m) | 2 (uno cada 500 m) | Estimación: ángulos de más de 15–20°, cambios de calle y anclajes intermedios; todos se costean con la lista de la RA2-004 |
| Terminales | 2 por tramo | 2 por tramo | RA2-003 |
| Vientos (retenidas) por km | 12 | 5,5 | Listas de materiales de EPM (dato oficial): 4 por referencia RA2-004, 1 por ángulo RA2-012 y 1 por terminal RA2-003. Se suponen 2 referencias y 3 ángulos por km urbano, y 1 y 1 por km rural (estimación) |
| Puestas a tierra por km | 4 | 3 | Estimación: cada 250–330 m y en cada terminal o equipo |
| Conductores | 3 fases ACSR 2/0 + neutro ACSR 1/0 | 4 × ACSR 1/0 | Neutro inferior de las estructuras de EPM |
| Factor de conductor | 1,04 | 1,04 | 3 % de flecha y desperdicio + 1 % de puentes y colas |

### 5.2 Qué lleva cada estructura (dato oficial de EPM)

| Norma EPM | Estructura | Materiales por estructura |
|---|---|---|
| [RA2-001](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA2-001.pdf) | Suspensión con neutro inferior, cruceta de 1.500 mm al centro | 1 poste concreto 12 m octogonal; 1 cruceta angular metálica 1.500 mm; 1 tiranta 1.500 mm; 1 aislador carrete 600 V 81 mm (neutro); 2 espigo para aisladores; 1 tornillo tipo carrete; 3 perno espaciador 15,9 × 254 mm; 2 tornillo 5/8" × 1½"; 3 aislador pin (corona) 13,2 kV; 1 espigo de barra plana |
| [RA2-003](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA2-003.pdf) | Terminal con neutro inferior, doble cruceta de 1.500 mm | 1 poste concreto 12 m octogonal; 2 cruceta angular metálica 1.500 mm; 2 tiranta 1.500 mm; 6 aislador de suspensión 13,2 kV 165 mm; 4 grapa terminal tipo recta; 2 tuerca de ojo 5/8"; 2 eslabón 5/8"; 6 perno espaciador 15,9 × 254 mm; 4 tornillo 5/8" × 1½"; 1 viento poste 12 m (RA6-001) |
| [RA2-004](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA2-004.pdf) | Referencia (retención doble) con neutro inferior | 1 poste concreto 12 m octogonal; 2 cruceta angular metálica 1.500 mm; 2 tiranta 1.500 mm; 12 aislador de suspensión 13,2 kV 165 mm; 8 grapa terminal tipo recta; 4 tuerca de ojo 5/8"; 4 eslabón 5/8"; 6 perno espaciador 15,9 × 254 mm; 4 tornillo 5/8" × 1½"; 4 viento poste 12 m; 3 espigo para aisladores; 3 aislador pin 13,2 kV |
| [RA2-011](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA2-011.pdf) | Suspensión en disposición V con neutro (rural, vanos hasta 90 m) | 1 poste concreto 12 m octogonal; 1 cruceta angular metálica; 1 tiranta 1.500 mm; 3 espigo para aisladores; 3 aislador pin 13,2 kV; 1 grapa de suspensión; 1 ojal de suspensión; 1 eslabón 5/8"; 1 bayoneta sencilla 1.500 mm; 1 conector de compresión en C; 4 perno espaciador 15,9 × 254 mm; 2 tornillo 5/8" × 1½" |
| [RA2-021](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA2-021.pdf) | Suspensión con cruceta volada de 2.400 mm (calles angostas) | 1 poste concreto 12 m octogonal; 1 cruceta angular metálica 2.400 mm; 1 pie de amigo izquierdo 2.400 mm; 4 espigo para aisladores; 1 tornillo 5/8" × 1½"; 4 aislador pin 13,2 kV; 2 perno espaciador 15,9 × 254 mm |
| [RA2-006](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA2-006.pdf) | Instalación de DPS de 12 kV en línea trifásica | 3 cruceta 1.500 mm; 3 tiranta 1.500 mm; 4 tuerca de ojo; 3 DPS 12 kV; 8 aislador de suspensión; 6 grapa terminal recta; 4 eslabón; 3 espigos; 3 aislador pin; 3 estribo; 3 conector transversal universal; 3 conectores varios; 9 tornillos 5/8" × 1½"; 8 pernos espaciadores |
| [RA2-007](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA2-007.pdf) | Cortacircuitos trifásico en cruceta metálica de 2.400 mm | 1 tiranta 2.400 mm; 1 cruceta 2.400 mm; 2 tornillo 5/8" × 1½"; 3 tornillo carruaje para cajas primarias; 2 perno espaciador 15,9 × 305 mm; 6 estribo; 6 conector transversal universal; 1 conector de compresión en C 4/0 Cu; 1 puesta a tierra (RA6-010); 3 caja primaria (cortacircuitos) 13,2 kV |
| [RA2-010](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA2-010.pdf) | Desconectadores (cuchillas) monopolares de 13,2 kV | 4 cruceta 1.500 mm; 2 tiranta 1.500 mm; 4 tuerca de ojo; 12 aislador de suspensión; 8 grapa terminal recta; 4 eslabón; 2 aislador pin; 2 espigo; 3 seccionador tipo cuchilla; 7 pernos espaciadores |
| [RA3-026](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA3-026.pdf) | Montaje de transformador monofásico convencional | 1 estribo; 1 caja primaria 13,2 kV; 4 conector de compresión derivación en C Cu; 1 DPS; 1 transformador monofásico; 1 conector transversal universal; 1 percha acanalada 1 puesto; 1 soporte en L para cortacircuitos y pararrayos; 1 tornillo carruaje; 2 varilla de puesta a tierra 2.400 mm; 1 tornillo 15,9 × 50,8 mm; 2 perno espaciador 254 mm; 3 perno espaciador 305 mm |
| [RA3-029](https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA3-029.pdf) | Montaje de transformador autoprotegido (hasta 75 kVA) | 2 espigo para cruceta metálica; 1 transformador monofásico; 2 aislador pin; 1 conector transversal universal; 3 conector de compresión en C Cu; 1 caja de electrodos de puesta a tierra; 2 varilla de puesta a tierra 2.400 mm; 2 perno espaciador 300 mm; 1 estribo |

### 5.3 Baja tensión, fibra y canalización

| Supuesto | Valor | Tipo |
|---|---|---|
| BT sobre los postes de la MT | 25 pinzas de suspensión, 6 de anclaje y 10 derivaciones por km; trenzado × 1,03 | Estimación |
| BT en calle sin MT | 29 postes de 10 m por km (vano de 35 m) | Estimación |
| Fibra: cable | ADSS 48 hilos en la troncal (CCED–nodos) y 24 hilos en ramales; × 1,06 por desperdicio y reservas | Estimación |
| Fibra: herrajes | 1 herraje de suspensión por poste de paso; 2 remates por poste de retención (4 por km urbano, 2 rural); 1,2 m de fleje y 2 hebillas por herraje | Estimación |
| Fibra: reservas y cajas | 2 reservas (raquetas) por km; 0,5 cajas de empalme por km; 1 NAP y 1 ONU por sede | Estimación |
| Canalización | 4 ductos de 4" (2 para MT/BT, 1 para fibra y 1 de reserva); zanja de 0,60 × 1,00 m; cámara cada 50 m (40–60) y en cada cambio de dirección | Estimación |

### 5.4 Rendimientos de las cuadrillas

| Actividad | Rendimiento | Cuadrilla |
|---|---|---|
| Excavación de huecos para poste | 5 por día | Civil (1 oficial + 4 obreros) |
| Izado y aplomado de postes con grúa | 8 por día | Redes (1 capataz + 2 linieros + 3 ayudantes) |
| Armado de estructuras de suspensión / retención | 6 / 3 por día | Redes |
| Vientos / puestas a tierra | 2 / 4 por día | Pareja (liniero + ayudante) |
| Tendido de MT (4 conductores) | 0,6 km/día urbano; 1,0 km/día rural | Redes |
| Tendido de BT trenzada | 0,8 km/día | Redes |
| Tendido de fibra | 1,2 km/día urbano; 48 fusiones por día | Fibra (1 empalmador + 1 liniero + 2 ayudantes) |
| Canalización | 6 m/día | Civil |
| Montaje de transformador / acometida | 1,0 día / 1,5 días | Redes / pareja |

## 6. Análisis de precios unitarios (APU)

Cada APU suma materiales, equipo, transporte y mano de obra (costo directo) y luego aplica el AIU de 27 % y el IVA sobre la utilidad. Los APU por km (06U, 06R y 12) suman el costo directo de los APU unitarios y aplican el AIU una sola vez. En la columna "Tipo" se marca de dónde sale cada precio.

### APU-01 · Poste de concreto de 12 m y 510 kgf instalado (hincado, aplomado y relleno), sin vestida

Unidad: **un**. Norma: EPM RA7-035 (poste) y RA2-001; empotramiento 10 % de la longitud + 0,6 m (1,8 m). Supuestos: Hueco de 0,8 × 0,8 × 1,8 m excavado a mano; base y relleno con recebo compactado; Izado y aplomado con camión grúa: 8 postes por día; Transporte desde planta hasta Yondó: $350.000 por poste.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Poste de concreto octogonal de 12 m y 510 kgf (RA7-035), puesto en planta, con IVA | un | 1 | $1.050.000 | $1.050.000 | Estimación |
| Material seleccionado (recebo o arena) para relleno, puesto en obra | m3 | 0,350 | $95.000 | $33.250 | Estimación |
| Esmalte para numeración de postes | gal | 0,100 | $93.000 | $9.300 | Estimación |
| **Materiales** | | | | **$1.092.550** | |
| Camión grúa de brazo articulado (8–12 t) con canasta, operador y combustible | día | 0,125 | $1.800.000 | $225.000 | Estimación |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 0,125 | $380.000 | $47.500 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $234.943 | $11.747 | Estimación |
| **Equipo** | | | | **$284.247** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $42.550 | $1.276 | Estimación |
| Transporte de un poste de 12 m desde la planta (Santander o Antioquia) hasta Yondó, con cargue y descargue | un | 1,00 | $350.000 | $350.000 | Estimación |
| **Transporte** | | | | **$351.276** | |
| Cuadrilla de obra civil: 1 oficial + 4 obreros — excavación del hueco y relleno | día | rinde 5,00 un/día | $567.217 | $113.443 | Estimación |
| Cuadrilla de redes aéreas: 1 capataz + 2 linieros + 3 ayudantes — izado, aplomado y numeración | día | rinde 8,00 un/día | $972.000 | $121.500 | Estimación |
| **Mano de obra** | | | | **$234.943** | |
| **Costo directo** | | | | **$1.963.016** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $530.014 | Estimación |
| IVA 19 % sobre la utilidad | | | | $18.649 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$2.511.679** | Rango $2.009.343–$3.265.183 |

Contraste: SIF Antioquia 2020, ítem 17.13 (poste 12 m 1.052 kg, STI, sin AIU, actualizado con IPC): **$1.651.658**; CREG N1P3, poste de concreto 12 m urbano de BT instalado (actualizado con IPP): **$1.678.546**.

### APU-02 · Estructura de suspensión trifásica 13,2 kV con neutro inferior, cruceta de 1.500 mm al centro (vestida sobre poste ya instalado)

Unidad: **un**. Norma: EPM RA2-001 (lista de materiales del plano 3 de 4). Supuestos: Materiales exactos de la lista de EPM más 3 amarres preformados; Rendimiento: 6 estructuras por día de cuadrilla.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Cruceta angular metálica galvanizada de 1.500 mm (RA7-013) | un | 1 | $95.000 | $95.000 | Estimación |
| Tiranta (diagonal) de 1.500 mm | un | 1 | $40.000 | $40.000 | Estimación |
| Aislador tipo pin 13,2 kV (porcelana ANSI 55-5 o polimérico) | un | 3 | $38.000 | $114.000 | Estimación |
| Espigo para aislador en cruceta metálica (RA7-009) | un | 2 | $22.000 | $44.000 | Estimación |
| Espigo de barra plana para punta de poste (RA7-010) | un | 1 | $45.000 | $45.000 | Estimación |
| Perno espaciador de 15,9 × 254 mm (5/8" × 10") galvanizado | un | 3 | $12.500 | $37.500 | Estimación |
| Tornillo de máquina de 5/8" × 1½"–2" galvanizado | un | 2 | $5.500 | $11.000 | Estimación |
| Aislador carrete 600 V de 81 mm con tornillo tipo carrete (neutro) | un | 1 | $21.000 | $21.000 | Estimación |
| Amarre preformado para aislador pin (ACSR 1/0–2/0) | un | 3 | $18.000 | $54.000 | Estimación |
| Placa o marquilla de identificación de circuito o poste (RA6-020) | un | 1 | $15.000 | $15.000 | Estimación |
| **Materiales** | | | | **$476.500** | |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 0,167 | $380.000 | $63.333 | Estimación |
| Camión grúa de brazo articulado (8–12 t) con canasta, operador y combustible | día | 0,083 | $1.800.000 | $150.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $162.000 | $8.100 | Estimación |
| **Equipo** | | | | **$221.433** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $476.500 | $14.295 | Estimación |
| **Transporte** | | | | **$14.295** | |
| Cuadrilla de redes aéreas: 1 capataz + 2 linieros + 3 ayudantes — armado de la estructura en el poste | día | rinde 6,00 un/día | $972.000 | $162.000 | Estimación |
| **Mano de obra** | | | | **$162.000** | |
| **Costo directo** | | | | **$874.228** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $236.041 | Estimación |
| IVA 19 % sobre la utilidad | | | | $8.305 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$1.118.575** | Rango $894.860–$1.454.147 |

Contraste: CREG N2L70 (estructura completa con poste 12 m 510 kg, montaje e ingeniería), actualizado: **$5.295.904**.

### APU-03 · Estructura de retención (referencia) trifásica 13,2 kV, doble cruceta de 1.500 mm (vestida, sin vientos)

Unidad: **un**. Norma: EPM RA2-004. Supuestos: Materiales de la lista de EPM; los 4 vientos de la lista se costean aparte con APU-04 según los vientos por km; Rendimiento: 3 estructuras por día.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Cruceta angular metálica galvanizada de 1.500 mm (RA7-013) | un | 2 | $95.000 | $190.000 | Estimación |
| Tiranta (diagonal) de 1.500 mm | un | 2 | $40.000 | $80.000 | Estimación |
| Aislador de suspensión polimérico 13,2 kV, 165 mm (RA7-011) | un | 12 | $40.000 | $480.000 | Estimación |
| Grapa terminal (recta o pistola) para ACSR 1/0–2/0 | un | 8 | $30.000 | $240.000 | Estimación |
| Tuerca de ojo de 5/8" | un | 4 | $34.000 | $136.000 | Estimación |
| Eslabón en U de 5/8" | un | 4 | $8.000 | $32.000 | Estimación |
| Perno espaciador de 15,9 × 254 mm (5/8" × 10") galvanizado | un | 6 | $12.500 | $75.000 | Estimación |
| Tornillo de máquina de 5/8" × 1½"–2" galvanizado | un | 4 | $5.500 | $22.000 | Estimación |
| Espigo para aislador en cruceta metálica (RA7-009) | un | 3 | $22.000 | $66.000 | Estimación |
| Aislador tipo pin 13,2 kV (porcelana ANSI 55-5 o polimérico) | un | 3 | $38.000 | $114.000 | Estimación |
| Amarre preformado para aislador pin (ACSR 1/0–2/0) | un | 3 | $18.000 | $54.000 | Estimación |
| Conector de compresión en C o transversal universal (cobre/aluminio) | un | 6 | $15.000 | $90.000 | Estimación |
| Aislador carrete 600 V de 81 mm con tornillo tipo carrete (neutro) | un | 1 | $21.000 | $21.000 | Estimación |
| Placa o marquilla de identificación de circuito o poste (RA6-020) | un | 1 | $15.000 | $15.000 | Estimación |
| **Materiales** | | | | **$1.615.000** | |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 0,333 | $380.000 | $126.667 | Estimación |
| Camión grúa de brazo articulado (8–12 t) con canasta, operador y combustible | día | 0,167 | $1.800.000 | $300.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $324.000 | $16.200 | Estimación |
| **Equipo** | | | | **$442.867** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $1.615.000 | $48.450 | Estimación |
| **Transporte** | | | | **$48.450** | |
| Cuadrilla de redes aéreas: 1 capataz + 2 linieros + 3 ayudantes — armado de la estructura de retención | día | rinde 3,00 un/día | $972.000 | $324.000 | Estimación |
| **Mano de obra** | | | | **$324.000** | |
| **Costo directo** | | | | **$2.430.317** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $656.186 | Estimación |
| IVA 19 % sobre la utilidad | | | | $23.088 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$3.109.591** | Rango $2.487.672–$4.042.468 |

Contraste: SIF 2020, ítem 17.14 vestida de poste EPM (retención), actualizado con IPC: **$1.760.489**; CREG N2L72 (estructura completa con poste 12 m 750 kg), actualizado: **$6.730.657**.

### APU-04 · Viento (retenida) a tierra para poste de 12 m, con aislador tensor y varilla de anclaje

Unidad: **un**. Norma: EPM RA6-001 (viento poste 12 m); materiales tomados del ítem 17.18 de la SIF 2020. Supuestos: 15 m de cable de acero de 3/8"; Anclaje enterrado a 1,5–1,8 m; Rendimiento: 2 vientos por día de pareja más 0,25 días de obrero para el anclaje.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Cable de acero galvanizado de 3/8" para retenida | m | 15 | $4.800 | $72.000 | Estimación |
| Aislador tensor de porcelana (strain) para retenida | un | 1 | $16.500 | $16.500 | Estimación |
| Varilla de anclaje de 5/8" × 1,80 m con arandela | un | 1 | $58.000 | $58.000 | Estimación |
| Bloque de anclaje en concreto | un | 1 | $45.000 | $45.000 | Estimación |
| Preformado de retención para cable de retenida | un | 2 | $34.600 | $69.200 | Estimación |
| Guardacabo | un | 2 | $3.500 | $7.000 | Estimación |
| Collarín (abrazadera) galvanizado para poste | un | 1 | $55.000 | $55.000 | Estimación |
| Protector de retenida (guardaviento) en PVC amarillo | un | 1 | $25.000 | $25.000 | Estimación |
| **Materiales** | | | | **$347.700** | |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 0,250 | $380.000 | $95.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $181.361 | $9.068 | Estimación |
| **Equipo** | | | | **$104.068** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $347.700 | $10.431 | Estimación |
| **Transporte** | | | | **$10.431** | |
| Pareja: 1 liniero + 1 ayudante — armado y tensionado | día | rinde 2,00 un/día | $306.000 | $153.000 | Estimación |
| Cuadrilla de obra civil: 1 oficial + 4 obreros — excavación del anclaje (0,25 días de obrero equivalentes) | día | rinde 20,00 un/día | $567.217 | $28.361 | Estimación |
| **Mano de obra** | | | | **$181.361** | |
| **Costo directo** | | | | **$643.560** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $173.761 | Estimación |
| IVA 19 % sobre la utilidad | | | | $6.114 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$823.435** | Rango $658.748–$1.070.466 |

Contraste: SIF 2020, ítem 17.18 viento convencional (STI, sin AIU), actualizado con IPC: **$392.121**.

### APU-05 · Puesta a tierra de estructura o equipo: 1 varilla copperweld de 5/8" × 2,4 m, bajante de Cu 2 AWG, 2 soldaduras exotérmicas, caja de registro y medición

Unidad: **un**. Norma: RETIE (Res. 40117 de 2024) y EPM RA6-014/RA6-015 (diseño y medición de la resistencia de puesta a tierra). Supuestos: Bajante de 14 m (12 m de poste + 2 m de conexión); Si la medida supera el valor de diseño se agrega otra varilla (+$85.000 y +0,1 día de pareja); Rendimiento: 4 por día de pareja.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Varilla de puesta a tierra copperweld de 5/8" × 2,40 m | un | 1 | $85.000 | $85.000 | Estimación |
| Cable de cobre desnudo 2 AWG, 7 hilos | m | 14 | $17.000 | $238.000 | Estimación |
| Soldadura exotérmica (carga de 90 g y prorrateo del molde) | un | 2 | $45.000 | $90.000 | Estimación |
| Tubo de protección del bajante de tierra (PVC o IMC 1/2", 3 m) con cinta bandit | un | 1 | $35.000 | $35.000 | Estimación |
| Conector de compresión en C o transversal universal (cobre/aluminio) | un | 1 | $15.000 | $15.000 | Estimación |
| Caja de registro para electrodo de puesta a tierra con tapa | un | 1 | $85.000 | $85.000 | Estimación |
| **Materiales** | | | | **$548.000** | |
| Telurómetro y equipo de soldadura exotérmica | día | 0,250 | $120.000 | $30.000 | Estimación |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 0,125 | $380.000 | $47.500 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $76.500 | $3.825 | Estimación |
| **Equipo** | | | | **$81.325** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $548.000 | $16.440 | Estimación |
| **Transporte** | | | | **$16.440** | |
| Pareja: 1 liniero + 1 ayudante — hincado, soldadura, bajante y medición | día | rinde 4,00 un/día | $306.000 | $76.500 | Estimación |
| **Mano de obra** | | | | **$76.500** | |
| **Costo directo** | | | | **$722.265** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $195.011 | Estimación |
| IVA 19 % sobre la utilidad | | | | $6.862 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$924.138** | Rango $739.310–$1.201.379 |

Contraste: CREG N2L137, puesta a tierra típica de nivel 2 (actualizado con IPP): **$444.757**; CREG Tabla 30, puesta a tierra de nivel 1 (actualizado con IPP): **$253.742**.

Los APU-01b (poste de 750 kgf, $2.639.629), APU-01c (poste de 10 m para BT sola, $2.447.704) y APU-03b (estructura terminal RA2-003, $2.097.455) siguen el mismo esquema y están completos en el JSON.

### APU-06U · km de red de MT aérea trifásica 13,2 kV en zona urbana: ACSR 2/0 + neutro ACSR 1/0, postes de concreto de 12 m, vano de 40 m

Unidad: **km**. Norma: EPM RA2-001/RA2-003/RA2-004 y RETIE. Supuestos: 25 postes por km: 19 de suspensión (510 kgf), 5 de retención y 1 terminal prorrateado (750 kgf); 12 vientos y 4 puestas a tierra por km; Conductor: 3 fases ACSR 2/0 + neutro ACSR 1/0 × factor 1,04; Tendido de 4 conductores: 0,6 km por día de cuadrilla, con equipo de tendido y grúa canasta la mitad del tiempo; No incluye equipos de protección (reconectador, cortacircuitos de ramal, DPS), que se cuentan por unidad.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Conductor ACSR 2/0 AWG (Quail), con IVA | m | 3.120 | $6.000 | $18.720.000 | Estimación |
| Conductor ACSR 1/0 AWG (Raven), con IVA | m | 1.040 | $4.800 | $4.992.000 | Estimación |
| Empalmes de tensión y conectores de puentes | un | 8 | $15.000 | $120.000 | Estimación |
| Marcación de circuito (RA6-020: en derivaciones y cada 2 km) | un | 3 | $15.000 | $45.000 | Estimación |
| **Materiales** | | | | **$23.877.000** | |
| APU-01: Poste de concreto de 12 m y 510 kgf instalado (hincado, aplomado y relleno), sin vestida | un | 19 | $1.963.016 | $37.297.304 | Cálculo propio (costo directo del APU) |
| APU-01b: Poste de concreto de 12 m y 750 kgf instalado, sin vestida (para retenciones y terminales) | un | 6 | $2.063.016 | $12.378.096 | Cálculo propio (costo directo del APU) |
| APU-02: Estructura de suspensión trifásica 13,2 kV con neutro inferior, cruceta de 1.500 mm al centro (vestida sobre poste ya instalado) | un | 19 | $874.228 | $16.610.332 | Cálculo propio (costo directo del APU) |
| APU-03: Estructura de retención (referencia) trifásica 13,2 kV, doble cruceta de 1.500 mm (vestida, sin vientos) | un | 5 | $2.430.317 | $12.151.585 | Cálculo propio (costo directo del APU) |
| APU-03b: Estructura terminal trifásica 13,2 kV, doble cruceta de 1.500 mm (vestida, sin viento) | un | 1 | $1.639.277 | $1.639.277 | Cálculo propio (costo directo del APU) |
| APU-04: Viento (retenida) a tierra para poste de 12 m, con aislador tensor y varilla de anclaje | un | 12 | $643.560 | $7.722.720 | Cálculo propio (costo directo del APU) |
| APU-05: Puesta a tierra de estructura o equipo: 1 varilla copperweld de 5/8" × 2,4 m, bajante de Cu 2 AWG, 2 soldaduras exotérmicas, caja de registro y medición | un | 4 | $722.265 | $2.889.060 | Cálculo propio (costo directo del APU) |
| **APU unitarios que lo componen** | | | | **$90.688.374** | |
| Equipo de tendido: poleas, malacate, ranas, tensiómetro y pértigas | día | 1,667 | $250.000 | $416.667 | Estimación |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 1,667 | $380.000 | $633.333 | Estimación |
| Camión grúa de brazo articulado (8–12 t) con canasta, operador y combustible | día | 0,833 | $1.800.000 | $1.500.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $1.620.000 | $81.000 | Estimación |
| **Equipo** | | | | **$2.631.000** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $23.877.000 | $716.310 | Estimación |
| **Transporte** | | | | **$716.310** | |
| Cuadrilla de redes aéreas: 1 capataz + 2 linieros + 3 ayudantes — tendido, tensionado, amarres y puentes de 4 conductores | día | rinde 0,60 km/día | $972.000 | $1.620.000 | Estimación |
| **Mano de obra** | | | | **$1.620.000** | |
| **Costo directo** | | | | **$119.532.684** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $32.273.825 | Estimación |
| IVA 19 % sobre la utilidad | | | | $1.135.560 | Oficial (tarifa) |
| **Precio unitario total** | **km** | | | **$152.942.069** | Rango $122.353.655–$198.824.690 |

Contraste: Suma de UC de la CREG para el mismo km (19 N2L70 + 6 N2L72 + N2L84 × 4/3 por el neutro + 4 N2L137), actualizada con IPP; ya incluye ingeniería y montaje: **$179.347.467**; Solo conductor: CREG N2L84 ACSR 2/0 (3 fases) actualizado: **$27.421.745**.

### APU-06R · km de red de MT aérea trifásica 13,2 kV en zona rural (vía a la PTAP, pozos y PTAP veredal): ACSR 1/0 + neutro ACSR 1/0, vano de 80 m

Unidad: **km**. Norma: EPM RA2-011 (suspensión V-neutro, vano hasta 90 m), RA2-003, RA2-004. Supuestos: 12,5 postes por km: 10,0 de suspensión, 2 de retención y 0,5 terminal prorrateado; 5,5 vientos y 3 puestas a tierra por km; Se usa la estructura RA2-001 como costo de la suspensión rural (la RA2-011 tiene materiales equivalentes); Tendido: 1,0 km por día; No incluye servidumbre ni poda (ítems GES-SERV y GES-PODA por km).

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Conductor ACSR 1/0 AWG (Raven), con IVA | m | 4.160 | $4.800 | $19.968.000 | Estimación |
| Empalmes y conectores | un | 6 | $15.000 | $90.000 | Estimación |
| Marcación de circuito | un | 2 | $15.000 | $30.000 | Estimación |
| **Materiales** | | | | **$20.088.000** | |
| APU-01: Poste de concreto de 12 m y 510 kgf instalado (hincado, aplomado y relleno), sin vestida | un | 10 | $1.963.016 | $19.630.160 | Cálculo propio (costo directo del APU) |
| APU-01b: Poste de concreto de 12 m y 750 kgf instalado, sin vestida (para retenciones y terminales) | un | 2,5 | $2.063.016 | $5.157.540 | Cálculo propio (costo directo del APU) |
| APU-02: Estructura de suspensión trifásica 13,2 kV con neutro inferior, cruceta de 1.500 mm al centro (vestida sobre poste ya instalado) | un | 10 | $874.228 | $8.742.280 | Cálculo propio (costo directo del APU) |
| APU-03: Estructura de retención (referencia) trifásica 13,2 kV, doble cruceta de 1.500 mm (vestida, sin vientos) | un | 2 | $2.430.317 | $4.860.634 | Cálculo propio (costo directo del APU) |
| APU-03b: Estructura terminal trifásica 13,2 kV, doble cruceta de 1.500 mm (vestida, sin viento) | un | 0,5 | $1.639.277 | $819.638 | Cálculo propio (costo directo del APU) |
| APU-04: Viento (retenida) a tierra para poste de 12 m, con aislador tensor y varilla de anclaje | un | 5,5 | $643.560 | $3.539.580 | Cálculo propio (costo directo del APU) |
| APU-05: Puesta a tierra de estructura o equipo: 1 varilla copperweld de 5/8" × 2,4 m, bajante de Cu 2 AWG, 2 soldaduras exotérmicas, caja de registro y medición | un | 3 | $722.265 | $2.166.795 | Cálculo propio (costo directo del APU) |
| **APU unitarios que lo componen** | | | | **$44.916.627** | |
| Equipo de tendido: poleas, malacate, ranas, tensiómetro y pértigas | día | 1,000 | $250.000 | $250.000 | Estimación |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 1,000 | $380.000 | $380.000 | Estimación |
| Camión grúa de brazo articulado (8–12 t) con canasta, operador y combustible | día | 0,300 | $1.800.000 | $540.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $972.000 | $48.600 | Estimación |
| **Equipo** | | | | **$1.218.600** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $20.088.000 | $602.640 | Estimación |
| **Transporte** | | | | **$602.640** | |
| Cuadrilla de redes aéreas: 1 capataz + 2 linieros + 3 ayudantes — tendido, tensionado, amarres y puentes de 4 conductores | día | rinde 1,00 km/día | $972.000 | $972.000 | Estimación |
| **Mano de obra** | | | | **$972.000** | |
| **Costo directo** | | | | **$67.797.867** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $18.305.424 | Estimación |
| IVA 19 % sobre la utilidad | | | | $644.080 | Oficial (tarifa) |
| **Precio unitario total** | **km** | | | **$86.747.371** | Rango $69.397.897–$112.771.582 |

Contraste: Suma de UC de la CREG para el mismo km (N2L70, N2L72, N2L83 × 4/3, N2L137), actualizada con IPP: **$103.656.402**.

### APU-07 · km de red de BT trenzada 3 × 1/0 AWG Al + neutro portante 1/0, sobre postes de la red de MT (sin postes nuevos)

Unidad: **km**. Norma: RETIE y normas de EPM para red trenzada (pinzas de suspensión y anclaje). Supuestos: 25 pinzas de suspensión y 6 de anclaje por km, con collarín; 10 derivaciones con conectores de perforación aislados; Tendido: 0,8 km por día; Si no hay MT en la calle, sumar 29 postes de 10 m por km (APU-01c).

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Cable trenzado de aluminio 3 × 1/0 AWG + neutro portante 1/0, con IVA | m | 1.030 | $22.000 | $22.660.000 | Estimación |
| Collarín o abrazadera para pinza de suspensión/anclaje | un | 31 | $55.000 | $1.705.000 | Estimación |
| Pinza de suspensión para cable trenzado con soporte y tornillería | un | 25 | $38.000 | $950.000 | Estimación |
| Pinza de anclaje (retención) para cable trenzado | un | 6 | $48.000 | $288.000 | Estimación |
| Conector de perforación aislado para derivación en trenzado | un | 10 | $22.000 | $220.000 | Estimación |
| Placa o marquilla de identificación de circuito o poste (RA6-020) | un | 2 | $15.000 | $30.000 | Estimación |
| **Materiales** | | | | **$25.853.000** | |
| Equipo de tendido: poleas, malacate, ranas, tensiómetro y pértigas | día | 1,250 | $250.000 | $312.500 | Estimación |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 1,250 | $380.000 | $475.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $1.215.000 | $60.750 | Estimación |
| **Equipo** | | | | **$848.250** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $25.853.000 | $775.590 | Estimación |
| **Transporte** | | | | **$775.590** | |
| Cuadrilla de redes aéreas: 1 capataz + 2 linieros + 3 ayudantes — tendido del trenzado, pinzas y derivaciones | día | rinde 0,80 km/día | $972.000 | $1.215.000 | Estimación |
| **Mano de obra** | | | | **$1.215.000** | |
| **Costo directo** | | | | **$28.691.840** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $7.746.797 | Estimación |
| IVA 19 % sobre la utilidad | | | | $272.572 | Oficial (tarifa) |
| **Precio unitario total** | **km** | | | **$36.711.209** | Rango $29.368.967–$47.724.572 |

Contraste: CREG N1L56 trenzado Al 1/0 × 3 fases, instalado (actualizado con IPP): **$52.444.272**.

### APU-08 · Transformador trifásico de 75 kVA, 13.200/220-127 V, instalado en poste existente con cortacircuitos, DPS, bajante de BT y 2 puestas a tierra

Unidad: **un**. Norma: EPM RA3-026 y RA2-007 (cortacircuitos en cruceta de 2.400 mm); RETIE. Supuestos: El poste de 12 m (750 o 1.050 kgf) se cuenta aparte si es nuevo; Montaje: 1 día de cuadrilla con grúa medio día; Precio del transformador estimado (sin cotización).

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Transformador trifásico tipo poste en aceite, 75 kVA, 13.200/220-127 V, solo equipo | un | 1 | $24.813.447 | $24.813.447 | Estimación |
| Cortacircuitos 15 kV 100 A con portafusible (caja primaria), con IVA | un | 3 | $445.000 | $1.335.000 | Estimación |
| Fusible tipo K para cortacircuitos | un | 3 | $12.000 | $36.000 | Estimación |
| DPS (pararrayos) de óxido metálico 12 kV polimérico, con IVA | un | 3 | $250.000 | $750.000 | Estimación |
| Cruceta angular metálica galvanizada de 2.400 mm (RA7-013) | un | 1 | $150.000 | $150.000 | Estimación |
| Tiranta (diagonal) de 2.400 mm | un | 1 | $55.000 | $55.000 | Estimación |
| Soporte en L para cortacircuitos y pararrayos | un | 3 | $12.000 | $36.000 | Estimación |
| Estribo (derivación) para conexión de cortacircuitos | un | 6 | $15.000 | $90.000 | Estimación |
| Conector de compresión en C o transversal universal (cobre/aluminio) | un | 9 | $15.000 | $135.000 | Estimación |
| Cobre 2 AWG para puentes de MT y conexión de DPS | m | 12 | $17.000 | $204.000 | Estimación |
| Collarín doble o soporte para colgar transformador trifásico | un | 2 | $120.000 | $240.000 | Estimación |
| Perno espaciador de 15,9 × 254 mm (5/8" × 10") galvanizado | un | 4 | $12.500 | $50.000 | Estimación |
| Tornillo de máquina de 5/8" × 1½"–2" galvanizado | un | 6 | $5.500 | $33.000 | Estimación |
| Bajante de BT 4 × 3/0 Cu × 12 m (I = 197 A a 220 V; el 2/0 solo admite 175 A a 75 °C, NTC 2050 tabla 310-16) | m | 48 | $53.000 | $2.544.000 | Estimación |
| Tubo galvanizado de 3" × 6 m con capacete, unión y cinta bandit (bajante BT) | un | 1 | $480.000 | $480.000 | Estimación |
| Caja de derivación de acometidas o barraje de BT en poste | un | 1 | $350.000 | $350.000 | Estimación |
| Cubierta aislante para bujes secundarios (antifraude) | un | 4 | $20.000 | $80.000 | Estimación |
| Pruebas de puesta en servicio del transformador (relación TTR, aislamiento, aceite) y protocolo | global | 1 | $600.000 | $600.000 | Estimación |
| Placa o marquilla de identificación de circuito o poste (RA6-020) | un | 1 | $15.000 | $15.000 | Estimación |
| **Materiales** | | | | **$31.996.447** | |
| APU-05: Puesta a tierra de estructura o equipo: 1 varilla copperweld de 5/8" × 2,4 m, bajante de Cu 2 AWG, 2 soldaduras exotérmicas, caja de registro y medición | un | 2 | $722.265 | $1.444.530 | Cálculo propio (costo directo del APU) |
| **APU unitarios que lo componen** | | | | **$1.444.530** | |
| Camión grúa de brazo articulado (8–12 t) con canasta, operador y combustible | día | 0,500 | $1.800.000 | $900.000 | Estimación |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 1,000 | $380.000 | $380.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $972.000 | $48.600 | Estimación |
| **Equipo** | | | | **$1.328.600** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $7.183.000 | $215.490 | Estimación |
| Transporte de un transformador de distribución hasta Yondó | un | 1,00 | $600.000 | $600.000 | Estimación |
| **Transporte** | | | | **$815.490** | |
| Cuadrilla de redes aéreas: 1 capataz + 2 linieros + 3 ayudantes — montaje del transformador, protecciones, bajante y pruebas | día | rinde 1,00 un/día | $972.000 | $972.000 | Estimación |
| **Mano de obra** | | | | **$972.000** | |
| **Costo directo** | | | | **$36.557.067** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $9.870.408 | Estimación |
| IVA 19 % sobre la utilidad | | | | $347.292 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$46.774.767** | Rango $37.419.814–$60.807.197 |

Contraste: CREG N1T14, transformador aéreo trifásico urbano de 75 kVA instalado (actualizado con IPP): **$19.697.797**; CREG N1T18, transformador pedestal de 75 kVA instalado (opción subterránea): **$65.649.439**.

| Variante | Precio total | Rango | Nota |
|---|---|---|---|
| 25 kVA monofásico | $25.326.717 | $20.261.374–$32.924.732 | Monofásico (RA3-026): 1 cortacircuitos, 1 DPS, 1 estribo y soporte en L, percha en vez de cruceta de 2,4 m y collarines; bajante 3 × 1/0 Cu (104 A a 240 V); mismo montaje y puestas a tierra. CREG N1T5: $11.013.503. |
| 37,5 kVA monofásico | $27.244.227 | $21.795.381–$35.417.495 | Monofásico (RA3-026): 1 cortacircuitos, 1 DPS, 1 estribo y soporte en L, percha en vez de cruceta de 2,4 m y collarines; bajante 3 × 2/0 Cu (156 A a 240 V; el 1/0 solo admite 150 A); mismo montaje y puestas a tierra. CREG N1T6: $11.749.823. |
| 45 kVA trifásico | $37.191.867 | $29.753.494–$48.349.428 | Igual al APU-08 cambiando el transformador y el bajante a 4 × 1/0 Cu (118 A a 220 V); mismo montaje y puestas a tierra. CREG N1T12: $15.559.909. |
| 112,5 kVA trifásico | $58.871.866 | $47.097.493–$76.533.425 | Igual al APU-08 cambiando el transformador y el bajante a 2 × 3/0 Cu por fase (295 A a 220 V); mismo montaje y puestas a tierra. Para 112,5 kVA EPM puede pedir montaje en estructura doble (RA3-030) y poste de 1.050 kgf: sumar un poste APU-01b y una estructura APU-03. CREG N1T15: $21.850.750. |

### APU-09 · km de fibra óptica ADSS 24 hilos instalada en postes existentes (zona urbana, vano de 40 m), con herrajes, reservas, empalmes y pruebas

Unidad: **km**. Norma: Buenas prácticas de despliegue aéreo (UIT-T L.26/ IEC 60794-4-20); permiso del dueño de los postes. Supuestos: Cable × 1,06 por desperdicio y reservas; 21 herrajes de suspensión y 4 postes de retención con 2 remates cada uno; Fleje de 1,2 m y 2 hebillas por herraje; 2 pares de raquetas de reserva por km; Media caja de empalme por km con 24 fusiones; Tendido: 1,2 km por día; pruebas OTDR en ambos sentidos; Precio del carrete de 4 km; para tramos sueltos de menos de 4 km usar el precio por km (+$3.064/m).

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Cable de fibra óptica ADSS G.652D monomodo 24 hilos, span 100 m, en carrete de 4 km (precio con IVA) | m | 1.060 | $6.209 | $6.581.540 | Mercado |
| Herraje de suspensión tipo J para ADSS Φ 10–15 mm (precio con IVA) | un | 21 | $24.640 | $517.440 | Mercado |
| Remate preformado (retención) para ADSS span 100 m, Φ 10–11 mm (precio con IVA) | un | 8 | $16.755 | $134.040 | Mercado |
| Fleje de acero inoxidable 304 de 3/4", 0,70 mm (rollo de 30,5 m) (precio con IVA) | m | 34,80 | $4.718 | $164.186 | Mercado |
| Hebilla de acero inoxidable de 3/4" (paquete de 100) (precio con IVA) | un | 58 | $977 | $56.666 | Mercado |
| Par de raquetas de reserva para cable ADSS, 12" (precio con IVA) | par | 2 | $93.961 | $187.922 | Mercado |
| Caja de empalme exterior IP65, aérea, hasta 144 empalmes (precio con IVA) | un | 0,500 | $425.782 | $212.891 | Mercado |
| Pigtail monomodo SC/UPC simplex de 1 m (precio con IVA) | un | 12 | $4.189 | $50.268 | Mercado |
| Marquilla de identificación del cable en cada poste | un | 25 | $15.000 | $375.000 | Estimación |
| **Materiales** | | | | **$8.279.953** | |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 0,833 | $380.000 | $316.667 | Estimación |
| Camión grúa de brazo articulado (8–12 t) con canasta, operador y combustible | día | 0,200 | $1.800.000 | $360.000 | Estimación |
| Fusionadora de fibra, OTDR, cortadora de precisión y medidor de potencia | día | 0,250 | $450.000 | $112.500 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $745.500 | $37.275 | Estimación |
| **Equipo** | | | | **$826.442** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $8.279.953 | $248.399 | Estimación |
| **Transporte** | | | | **$248.399** | |
| Cuadrilla de fibra óptica: 1 empalmador + 1 liniero + 2 ayudantes — tendido, herrajes y marquillas | día | rinde 1,20 km/día | $630.000 | $525.000 | Estimación |
| Cuadrilla de fibra óptica: 1 empalmador + 1 liniero + 2 ayudantes — empalmes (12 fusiones por km) y pruebas OTDR (0,1 día por km) | día | rinde 2,86 km/día | $630.000 | $220.500 | Estimación |
| **Mano de obra** | | | | **$745.500** | |
| **Costo directo** | | | | **$10.100.294** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $2.727.080 | Estimación |
| IVA 19 % sobre la utilidad | | | | $95.953 | Oficial (tarifa) |
| **Precio unitario total** | **km** | | | **$12.923.326** | Rango $10.338.661–$16.800.324 |

Contraste: CREG N4L93, fibra ADSS en líneas de nivel 4 (actualizado con IPP); referencia alta, incluye trabajo en torres: **$50.087.883**.

| Variante | Precio total | Rango | Nota |
|---|---|---|---|
| ADSS 48 hilos (troncal) | $27.825.435 | $22.260.348–$36.173.065 | Cambia el cable al precio por km suelto de 48 hilos (no hay precio confiable de carrete) y duplica las fusiones (12 más por km, 0,25 días de cuadrilla). |
| Rural (vano 80 m, 12,5 postes/km) | $10.080.194 | — | Estimación: la mitad de herrajes, fleje y marquillas y tendido más rápido; el cable no cambia. |

Costo de operación: Arriendo de 25 puntos de apoyo por km en postes de EPM (tope CRC actualizado): **$900.668 al año por km**.

### APU-13 · Conexión de una sede a la red de fibra (GPON): caja de distribución (NAP) con splitter, acometida de fibra de 50 m, roseta, ONU y conexión al tablero de la sede

Unidad: **un**. Norma: Arquitectura GPON (UIT-T G.984): OLT en el CCED, splitters en las NAP y una ONU por sede. Supuestos: Una NAP con splitter 1×8 por sede (sirve también a sedes vecinas); 50 m de acometida de fibra (drop) desde el poste; Medio día de cuadrilla de fibra con fusionadora.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Caja de distribución (NAP) exterior para 24 empalmes con 16 acopladores SC/APC (precio con IVA) | un | 1 | $261.679 | $261.679 | Mercado |
| Splitter PLC 1×8 con conectores SC/APC (precio con IVA) | un | 1 | $140.284 | $140.284 | Mercado |
| Cable de acometida de fibra (drop) figura 8 de 1 hilo G.657A1 con mensajero, por metro | m | 55 | $415 | $22.825 | Estimación |
| Caja o bandeja de terminación óptica de pared con 2 adaptadores (roseta) en la sede | un | 1 | $22.998 | $22.998 | Estimación |
| ONU (ONT) GPON con 4 puertos Gigabit y WiFi 2,4 GHz (precio con IVA) | un | 1 | $399.416 | $399.416 | Mercado |
| Cordón de parcheo de fibra monomodo SC/APC–LC de 3 m | un | 2 | $15.000 | $30.000 | Estimación |
| Pigtail monomodo SC/UPC simplex de 1 m (precio con IVA) | un | 4 | $4.189 | $16.756 | Mercado |
| Placa o marquilla de identificación de circuito o poste (RA6-020) | un | 1 | $15.000 | $15.000 | Estimación |
| **Materiales** | | | | **$908.958** | |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 0,500 | $380.000 | $190.000 | Estimación |
| Fusionadora de fibra, OTDR, cortadora de precisión y medidor de potencia | día | 0,500 | $450.000 | $225.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $315.000 | $15.750 | Estimación |
| **Equipo** | | | | **$430.750** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $908.958 | $27.269 | Estimación |
| **Transporte** | | | | **$27.269** | |
| Cuadrilla de fibra óptica: 1 empalmador + 1 liniero + 2 ayudantes — NAP, acometida, fusiones, roseta, ONU y prueba de potencia | día | rinde 2,00 un/día | $630.000 | $315.000 | Estimación |
| **Mano de obra** | | | | **$315.000** | |
| **Costo directo** | | | | **$1.681.977** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $454.134 | Estimación |
| IVA 19 % sobre la utilidad | | | | $15.979 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$2.152.090** | Rango $1.721.672–$2.797.716 |

### APU-14 · Nodo central de la red de datos en el CCED (Alcaldía): OLT GPON de 16 puertos, switch industrial capa 3 con 10G, distribuidor de fibra (ODF) y transceptores

Unidad: **un**. Norma: Arquitectura GPON; el EMS/SCADA, los servidores y la UPS del CCED ya están en data/presupuesto_microrred.json. Supuestos: ODF de 48 fibras con 48 pigtails fusionados; 4 transceptores SFP para enlaces de respaldo; 2 días de cuadrilla de fibra y 1 día de fusionadora.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| OLT GPON de 16 puertos con 8 uplinks (4 GE + 4 SFP) (precio con IVA) | un | 1 | $18.904.079 | $18.904.079 | Mercado |
| Switch industrial administrable capa 3, 16 puertos GE + 4 SFP+ 10G (precio con IVA) | un | 1 | $8.484.093 | $8.484.093 | Mercado |
| Distribuidor de fibra (ODF) 19" para 48 adaptadores LC dúplex, vacío (precio con IVA) | un | 1 | $323.772 | $323.772 | Mercado |
| Pigtail monomodo SC/UPC simplex de 1 m (precio con IVA) | un | 48 | $4.189 | $201.072 | Mercado |
| Transceptor SFP 1G LX BiDi monomodo, 20 km (precio con IVA) | un | 4 | $266.199 | $1.064.796 | Mercado |
| Cordón de parcheo de fibra monomodo SC/APC–LC de 3 m | un | 10 | $15.000 | $150.000 | Estimación |
| Placa o marquilla de identificación de circuito o poste (RA6-020) | un | 4 | $15.000 | $60.000 | Estimación |
| **Materiales** | | | | **$29.187.812** | |
| Fusionadora de fibra, OTDR, cortadora de precisión y medidor de potencia | día | 1,000 | $450.000 | $450.000 | Estimación |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 1,000 | $380.000 | $380.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $1.260.000 | $63.000 | Estimación |
| **Equipo** | | | | **$893.000** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $29.187.812 | $875.634 | Estimación |
| **Transporte** | | | | **$875.634** | |
| Cuadrilla de fibra óptica: 1 empalmador + 1 liniero + 2 ayudantes — montaje en rack, fusiones del ODF, configuración y pruebas | día | rinde 0,50 un/día | $630.000 | $1.260.000 | Estimación |
| **Mano de obra** | | | | **$1.260.000** | |
| **Costo directo** | | | | **$32.216.446** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $8.698.440 | Estimación |
| IVA 19 % sobre la utilidad | | | | $306.056 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$41.220.943** | Rango $32.976.754–$53.587.225 |

### APU-10 · Metro de canalización subterránea con 4 ductos PVC de 4" bajo andén, envueltos en concreto, con reposición de andén (sin cámaras)

Unidad: **m**. Norma: RETIE y normas de EPM para canalizaciones (RS-); NTC 2050. Supuestos: Zanja de 0,60 × 1,00 m; envoltura de concreto de 0,16 m³/m; Relleno compactado de 0,35 m³/m y retiro de 0,40 m³/m de sobrantes; Rendimiento: 6 m por día de cuadrilla civil; Cámaras aparte (cada 50 m).

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Ducto PVC 4" tipo DB o TDP para canalización eléctrica (por metro) | m | 4,12 | $26.000 | $107.120 | Estimación |
| Separador de ductos de 4" (soporte para 4 vías) | un | 0,667 | $4.500 | $3.000 | Estimación |
| Concreto de 3.000 psi (21 MPa) hecho en obra, puesto en Yondó | m3 | 0,160 | $650.000 | $104.000 | Estimación |
| Material seleccionado (recebo o arena) para relleno, puesto en obra | m3 | 0,350 | $95.000 | $33.250 | Estimación |
| Cinta de señalización "peligro, energía" | m | 1 | $1.200 | $1.200 | Estimación |
| Demolición y reposición de andén en concreto de 0,10 m (materiales y mano de obra) | m2 | 0,600 | $145.000 | $87.000 | Estimación |
| **Materiales** | | | | **$335.570** | |
| Vibrocompactador tipo canguro | día | 0,167 | $150.000 | $25.000 | Estimación |
| Mezcladora de concreto de 1 bulto | día | 0,167 | $90.000 | $15.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $94.536 | $4.727 | Estimación |
| **Equipo** | | | | **$44.727** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $335.570 | $10.067 | Estimación |
| Retiro y disposición de sobrantes de excavación | m3 | 0,40 | $85.000 | $34.000 | Estimación |
| **Transporte** | | | | **$44.067** | |
| Cuadrilla de obra civil: 1 oficial + 4 obreros — demolición, excavación, ductos, concreto, relleno y reposición | día | rinde 6,00 m/día | $567.217 | $94.536 | Estimación |
| **Mano de obra** | | | | **$94.536** | |
| **Costo directo** | | | | **$518.900** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $140.103 | Estimación |
| IVA 19 % sobre la utilidad | | | | $4.930 | Oficial (tarifa) |
| **Precio unitario total** | **m** | | | **$663.933** | Rango $531.146–$863.112 |

Contraste: CREG N1C8 canalización 4 ductos de nivel 1 (actualizado con IPP): **$304.741**; CREG N2L77 canalización urbana 4 × 4" de nivel 2, por metro (incluye cámaras y vías), actualizado: **$866.043**.

### APU-10b · Cámara de inspección de 1,0 × 1,0 × 1,2 m en concreto reforzado con tapa en ferroconcreto

Unidad: **un**. Norma: Normas de EPM para cámaras de redes subterráneas; RETIE. Supuestos: Excavación de 1,6 × 1,6 × 1,4 m (3,6 m³) a mano; Paredes y base de 0,15 m: 1,0 m³ de concreto y 50 kg de acero; 2 días de cuadrilla civil por cámara.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Concreto de 3.000 psi (21 MPa) hecho en obra, puesto en Yondó | m3 | 1 | $650.000 | $650.000 | Estimación |
| Acero de refuerzo de 60.000 psi figurado | kg | 50 | $6.500 | $325.000 | Estimación |
| Tapa y marco en ferroconcreto para cámara de 1,0 × 1,0 m, tráfico peatonal/vehicular liviano | un | 1 | $750.000 | $750.000 | Estimación |
| Alquiler de formaleta metálica para cámara (por uso) | un | 1 | $150.000 | $150.000 | Estimación |
| Material seleccionado (recebo o arena) para relleno, puesto en obra | m3 | 0,500 | $95.000 | $47.500 | Estimación |
| **Materiales** | | | | **$1.922.500** | |
| Mezcladora de concreto de 1 bulto | día | 1,000 | $90.000 | $90.000 | Estimación |
| Vibrocompactador tipo canguro | día | 0,500 | $150.000 | $75.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $1.134.434 | $56.722 | Estimación |
| **Equipo** | | | | **$221.722** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $1.922.500 | $57.675 | Estimación |
| Retiro y disposición de sobrantes de excavación | m3 | 3,00 | $85.000 | $255.000 | Estimación |
| **Transporte** | | | | **$312.675** | |
| Cuadrilla de obra civil: 1 oficial + 4 obreros — excavación, formaleta, vaciado y relleno | día | rinde 0,50 un/día | $567.217 | $1.134.434 | Estimación |
| **Mano de obra** | | | | **$1.134.434** | |
| **Costo directo** | | | | **$3.591.331** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $969.660 | Estimación |
| IVA 19 % sobre la utilidad | | | | $34.118 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$4.595.108** | Rango $3.676.086–$5.973.640 |

Contraste: CREG N1C1 caja sencilla para redes subterráneas, instalada (actualizado): **$2.502.170**; CREG N1C2 caja doble, instalada (actualizado): **$6.185.418**.

### APU-12 · km de red de MT subterránea 13,2 kV: canalización de 4 ductos, cámara cada 50 m y 3 cables monopolares Cu 1/0 XLPE 15 kV, con transiciones aéreo–subterráneas en los extremos

Unidad: **km**. Norma: RETIE; normas de EPM para redes subterráneas. Supuestos: 1.000 m de canalización (APU-10) y 20 cámaras (APU-10b); 3 × 1.000 m × 1,04 de cable XLPE; Tendido del cable: 0,3 km de circuito por día de cuadrilla; 2 transiciones (terminales, DPS y cortacircuitos) por km de tramo.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Cable monopolar de cobre 1/0 AWG XLPE 15 kV, aislamiento 133 %, con IVA | m | 3.120 | $85.000 | $265.200.000 | Estimación |
| Juego de 3 terminales premoldeados o termocontráctiles 15 kV exterior | juego | 2 | $1.500.000 | $3.000.000 | Estimación |
| DPS (pararrayos) de óxido metálico 12 kV polimérico, con IVA | un | 6 | $250.000 | $1.500.000 | Estimación |
| Cortacircuitos 15 kV 100 A con portafusible (caja primaria), con IVA | un | 6 | $445.000 | $2.670.000 | Estimación |
| Conector de compresión en C o transversal universal (cobre/aluminio) | un | 12 | $15.000 | $180.000 | Estimación |
| **Materiales** | | | | **$272.550.000** | |
| APU-10: Metro de canalización subterránea con 4 ductos PVC de 4" bajo andén, envueltos en concreto, con reposición de andén (sin cámaras) | m | 1.000 | $518.900 | $518.900.000 | Cálculo propio (costo directo del APU) |
| APU-10b: Cámara de inspección de 1,0 × 1,0 × 1,2 m en concreto reforzado con tapa en ferroconcreto | un | 20 | $3.591.331 | $71.826.620 | Cálculo propio (costo directo del APU) |
| **APU unitarios que lo componen** | | | | **$590.726.620** | |
| Equipo de tendido: poleas, malacate, ranas, tensiómetro y pértigas | día | 3,333 | $250.000 | $833.333 | Estimación |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 3,333 | $380.000 | $1.266.667 | Estimación |
| Camión grúa de brazo articulado (8–12 t) con canasta, operador y combustible | día | 1,000 | $1.800.000 | $1.800.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $3.240.000 | $162.000 | Estimación |
| **Equipo** | | | | **$4.062.000** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $272.550.000 | $8.176.500 | Estimación |
| **Transporte** | | | | **$8.176.500** | |
| Cuadrilla de redes aéreas: 1 capataz + 2 linieros + 3 ayudantes — tendido del cable, terminales y pruebas | día | rinde 0,30 km/día | $972.000 | $3.240.000 | Estimación |
| **Mano de obra** | | | | **$3.240.000** | |
| **Costo directo** | | | | **$878.755.120** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $237.263.883 | Estimación |
| IVA 19 % sobre la utilidad | | | | $8.348.174 | Oficial (tarifa) |
| **Precio unitario total** | **km** | | | **$1.124.367.176** | Rango $899.493.741–$1.461.677.329 |

Contraste: CREG N2L77 (canalización urbana 4 × 4", por km) + N2L127 (cable XLPE Cu 1/0, 3 fases), actualizados con IPP: **$1.183.121.360**.

### APU-11 · Acometida trifásica de BT a una sede (25 m de Cu 3 × 2/0 + N 1/0 + T 4 en tubería) con medida semidirecta y medidor bidireccional con comunicación

Unidad: **un**. Norma: RETIE; normas de medida de EPM; CREG 038 de 2014 (código de medida) y CREG 174 de 2021 (medidor bidireccional del autogenerador). Supuestos: Para sedes de hasta unos 60 kVA (157 A a 220 V): el Cu 2/0 THHN admite 175 A a 75 °C (NTC 2050, tabla 310-16); para sedes mayores se sube a 4/0 o a dos conductores por fase. Para cargas menores, medida directa (restar los TC y la bornera); 27 m de cable por conductor (25 m + colas); 1,5 días de pareja de liniería.

| Componente | Unidad | Cantidad | Precio unitario | Subtotal | Tipo |
|---|---|---|---|---|---|
| Cable de cobre THHN/THWN-2 2/0 AWG | m | 81 | $42.000 | $3.402.000 | Estimación |
| Cable de cobre THHN/THWN-2 1/0 AWG | m | 27 | $34.000 | $918.000 | Estimación |
| Cable de cobre THHN/THWN-2 4 AWG | m | 27 | $14.000 | $378.000 | Estimación |
| Tubería PVC conduit 2" con accesorios (por metro) | m | 25 | $12.000 | $300.000 | Estimación |
| Terminales y conectores | un | 12 | $15.000 | $180.000 | Estimación |
| Medidor electrónico bidireccional trifásico clase 0,5S/1 semidirecto, con puerto de comunicación (homologado por EPM) | un | 1 | $1.500.000 | $1.500.000 | Estimación |
| Módem o módulo de comunicación (celular, LoRaWAN o RS-485) para el medidor | un | 1 | $450.000 | $450.000 | Estimación |
| Transformador de corriente 200/5 A clase 0,5S para medida semidirecta | un | 3 | $180.000 | $540.000 | Estimación |
| Bornera de prueba para medida semidirecta | un | 1 | $150.000 | $150.000 | Estimación |
| Celda o caja de medida trifásica con totalizador 3 × 200 A, sellable | un | 1 | $1.900.000 | $1.900.000 | Estimación |
| **Materiales** | | | | **$9.718.000** | |
| Camioneta 4×4 de cuadrilla con conductor y combustible | día | 0,500 | $380.000 | $190.000 | Estimación |
| Herramienta menor (5 % de la mano de obra) | % | 5 % | $459.000 | $22.950 | Estimación |
| **Equipo** | | | | **$212.950** | |
| Transporte de materiales menores hasta Yondó (3 % de los materiales, sin postes ni transformadores) | % | 3 % | $9.718.000 | $291.540 | Estimación |
| **Transporte** | | | | **$291.540** | |
| Pareja: 1 liniero + 1 ayudante — acometida, celda de medida y conexión | día | rinde 0,67 un/día | $306.000 | $459.000 | Estimación |
| **Mano de obra** | | | | **$459.000** | |
| **Costo directo** | | | | **$10.681.490** | |
| Administración 19 % + imprevistos 3 % + utilidad 5 % | | | | $2.884.002 | Estimación |
| IVA 19 % sobre la utilidad | | | | $101.474 | Oficial (tarifa) |
| **Precio unitario total** | **un** | | | **$13.666.966** | Rango $10.933.573–$17.767.056 |

Contraste: Rango de 2–5 M COP por punto de medición instalado usado en data/presupuesto_microrred.json (solo medidor y comunicación): **$4.000.000**.

## 7. Resumen: precios instalados para costear los tramos

| Código | Ítem | Unidad | Precio con AIU | Rango | Referencia CREG actualizada |
|---|---|---|---|---|---|
| APU-01 | Poste de concreto de 12 m y 510 kgf instalado (hincado, aplomado y relleno), sin vestida | un | $2.511.679 | $2.009.343–$3.265.183 | N1P3: $1.678.546 (poste de BT) |
| APU-01b | Poste de concreto de 12 m y 750 kgf instalado, sin vestida (para retenciones y terminales) | un | $2.639.629 | $2.111.703–$3.431.518 | — |
| APU-01c | Poste de concreto de 10 m y 510 kgf instalado, sin vestida (red de BT sola) | un | $2.447.704 | $1.958.163–$3.182.015 | N1P50: $1.339.213 |
| APU-02 | Estructura de suspensión trifásica 13,2 kV con neutro inferior, cruceta de 1.500 mm al centro (vestida sobre poste ya instalado) | un | $1.118.575 | $894.860–$1.454.147 | N2L70 (con poste): $5.295.904 |
| APU-03 | Estructura de retención (referencia) trifásica 13,2 kV, doble cruceta de 1.500 mm (vestida, sin vientos) | un | $3.109.591 | $2.487.672–$4.042.468 | N2L72 (con poste): $6.730.657 |
| APU-03b | Estructura terminal trifásica 13,2 kV, doble cruceta de 1.500 mm (vestida, sin viento) | un | $2.097.455 | $1.677.964–$2.726.691 | — |
| APU-04 | Viento (retenida) a tierra para poste de 12 m, con aislador tensor y varilla de anclaje | un | $823.435 | $658.748–$1.070.466 | — |
| APU-05 | Puesta a tierra de estructura o equipo: 1 varilla copperweld de 5/8" × 2,4 m, bajante de Cu 2 AWG, 2 soldaduras exotérmicas, caja de registro y medición | un | $924.138 | $739.310–$1.201.379 | N2L137: $444.757 |
| APU-06U | km de red de MT aérea trifásica 13,2 kV en zona urbana: ACSR 2/0 + neutro ACSR 1/0, postes de concreto de 12 m, vano de 40 m | km | $152.942.069 | $122.353.655–$198.824.690 | Suma de UC: $179.347.467 |
| APU-06R | km de red de MT aérea trifásica 13,2 kV en zona rural (vía a la PTAP, pozos y PTAP veredal): ACSR 1/0 + neutro ACSR 1/0, vano de 80 m | km | $86.747.371 | $69.397.897–$112.771.582 | Suma de UC: $103.656.402 |
| APU-07 | km de red de BT trenzada 3 × 1/0 AWG Al + neutro portante 1/0, sobre postes de la red de MT (sin postes nuevos) | km | $36.711.209 | $29.368.967–$47.724.572 | 3 × N1L56: $52.444.272 |
| APU-08 | Transformador trifásico de 75 kVA, 13.200/220-127 V, instalado en poste existente con cortacircuitos, DPS, bajante de BT y 2 puestas a tierra | un | $46.774.767 | $37.419.814–$60.807.197 | N1T14: $19.697.797 |
| APU-08 · 25 kVA monofásico | variante | un | $25.326.717 | $20.261.374–$32.924.732 | N1T5: $11.013.503 |
| APU-08 · 37,5 kVA monofásico | variante | un | $27.244.227 | $21.795.381–$35.417.495 | N1T6: $11.749.823 |
| APU-08 · 45 kVA trifásico | variante | un | $37.191.867 | $29.753.494–$48.349.428 | N1T12: $15.559.909 |
| APU-08 · 112,5 kVA trifásico | variante | un | $58.871.866 | $47.097.493–$76.533.425 | N1T15: $21.850.750 |
| APU-09 | km de fibra óptica ADSS 24 hilos instalada en postes existentes (zona urbana, vano de 40 m), con herrajes, reservas, empalmes y pruebas | km | $12.923.326 | $10.338.661–$16.800.324 | N4L93 (líneas de nivel 4, 57,5–220 kV): $50.087.883 |
| APU-09 · ADSS 48 hilos (troncal) | variante | km | $27.825.435 | $22.260.348–$36.173.065 | — |
| APU-09 · Rural (vano 80 m, 12,5 postes/km) | variante | km | $10.080.194 | — | — |
| APU-10 | Metro de canalización subterránea con 4 ductos PVC de 4" bajo andén, envueltos en concreto, con reposición de andén (sin cámaras) | m | $663.933 | $531.146–$863.112 | N1C8: $304.741 |
| APU-10b | Cámara de inspección de 1,0 × 1,0 × 1,2 m en concreto reforzado con tapa en ferroconcreto | un | $4.595.108 | $3.676.086–$5.973.640 | N1C2: $6.185.418 |
| APU-12 | km de red de MT subterránea 13,2 kV: canalización de 4 ductos, cámara cada 50 m y 3 cables monopolares Cu 1/0 XLPE 15 kV, con transiciones aéreo–subterráneas en los extremos | km | $1.124.367.176 | $899.493.741–$1.461.677.329 | N2L77 + N2L127: $1.183.121.360 |
| APU-11 | Acometida trifásica de BT a una sede (25 m de Cu 3 × 2/0 + N 1/0 + T 4 en tubería) con medida semidirecta y medidor bidireccional con comunicación | un | $13.666.966 | $10.933.573–$17.767.056 | — |
| APU-13 | Conexión de una sede a la red de fibra (GPON): caja de distribución (NAP) con splitter, acometida de fibra de 50 m, roseta, ONU y conexión al tablero de la sede | un | $2.152.090 | $1.721.672–$2.797.716 | — |
| APU-14 | Nodo central de la red de datos en el CCED (Alcaldía): OLT GPON de 16 puertos, switch industrial capa 3 con 10G, distribuidor de fibra (ODF) y transceptores | un | $41.220.943 | $32.976.754–$53.587.225 | — |
| CREG-N2EQ35 | Reconectador trifásico instalado (punto de acople de la microrred física) | un | $74.783.431 | — | Es el valor CREG |
| CREG-N2EQ29 | Seccionalizador bajo carga 400 A instalado | un | $33.470.441 | — | Es el valor CREG |
| CREG-N2EQ12 | Juego de cortacircuitos de ramal instalado | juego | $1.976.698 | — | Es el valor CREG |
| CREG-N2EQ15 | Juego de DPS de línea instalado | juego | $1.584.653 | — | Es el valor CREG |

**Por qué los APU dan más que la CREG en transformadores y menos en estructuras de media tensión:** la CREG reconoce por cada estructura un valor que incluye ingeniería, montaje y obra civil (un poste de 12 m vestido de suspensión: $5.295.904, frente a $3.630.254 del APU-01 más el APU-02), mientras que en transformadores la CREG valora compras al por mayor de los operadores de red y el municipio compra pocas unidades, al detal y con transporte hasta Yondó (el IPP de transformadores del DANE subió menos que el IPP total desde 2017, así que la brecha no es de inflación). En conjunto, el km urbano queda 15 % por debajo de la suma CREG, que trae la ingeniería incluida; aquí la ingeniería (4 %) se suma aparte.

## 8. La subestación de EPM y los circuitos de 13,2 kV

### 8.1 Lo que se sabe (dato oficial)

| Dato | Valor | Fuente |
|---|---|---|
| Capacidad | 1 transformador de 10 MVA, 34,5/13,2 kV, con edificio de control | [EPM, 7-jul-2020](https://www.epm.com.co/clientesyusuarios/noticias-y-novedades/epm-pone-en-marcha-solucion-de-energia-electrica-en-yondo--que-b/) |
| Alimentación | dos circuitos exclusivos de 34,5 kV desde la subestación Barranca (Barrancabermeja, Santander), que conectan a Yondó con el SIN | EPM, 7-jul-2020 |
| Redes, inversión y año | 32 km de redes de interconexión con la S/E Barranca, $15.509 millones corrientes, en operación en 2021 | [EPM, 2021](https://www.epm.com.co/clientesyusuarios/noticias-y-novedades/en-2021-epm-entro-en-operacion-importantes-proyectos-de-infraestructura-de-servicios-publicos/) |
| Contratistas | JE Jaimes Ingenieros S.A. (obras civiles y adecuaciones de la subestación); Ingeomega S.A.S. (circuitos de alimentación) | EPM, 7-jul-2020 |
| Código en EPM | 165 (Subestación Yondo, región 1 = Nordeste y Magdalena Medio); los circuitos de 13,2 kV se marcan 165-11 a 165-16 | [EPM, norma RA6-020](https://comercializadorenergia.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA6-020.pdf) |
| Subestación aguas arriba | Barranca (230/115 kV), Barrancabermeja: 7,0976 N, −73,8950 O | OpenStreetMap, way 1426109682 |

### 8.2 Dónde está: no se pudo confirmar

Se buscó en las notas de EPM, los avisos de cortes de 2022 a 2026, la UPME, OpenStreetMap (que en Yondó solo tiene la línea de 115 kV de Ecopetrol Barranca–Cóndor), las etiquetas de Google Maps y un barrido satelital de Google (z16 a z21) del casco urbano y de las dos vías a Barrancabermeja, entre 6,99 y 7,05 N. No apareció ningún patio de 34,5/13,2 kV atribuible a EPM. Lo que se encontró y se descartó:

| Candidato | Coordenadas | Por qué se descarta |
|---|---|---|
| Patio eléctrico de la PIA Casabe (planta de inyección de agua de Ecopetrol) | 7,04320 N; −73,91255 O | Es un patio de alta tensión real (dos zonas de equipos y un edificio de 65 × 24 m), junto a la vía Yondó–Barrancabermeja y 4 km al norte del casco; Google lo etiqueta "PIA CASABE" y al sur está la "PTAP CASABE" con tanques y tuberías. Ya existía en enero de 2020 (Esri) con menos equipos. Es infraestructura del campo Casabe, no la S/E de EPM. |
| Subestación Cóndor 115 kV (industrial, Ecopetrol) | 7,03700 N; −73,93090 O | Así figura en OpenStreetMap (way 1410062152), alimentada en 115 kV desde Barranca; es del campo petrolero. |
| Patio pequeño en la base de Ecopetrol al sur del casco | 7,00130 N; −73,91375 O | Patio de unos 22 × 38 m con pórtico, un transformador sobre losa y una caseta, en el borde occidental del complejo industrial que Google Maps etiqueta "Taller de Subsuelo" y "Equipo Liviano" (base del campo Casabe); en enero de 2020 (Esri) ya estaba lleno de equipos. Por tamaño no se puede descartar (una S/E compacta de 10 MVA cabe en 30 × 40 m), pero por estar dentro de la base se toma como subestación industrial. Verificar en la visita de campo (verificación del 22-oct-2026, imágenes data/geo/img/vr_red_c5_*.png). |
| Patio de camiones al norte (7,0187, −73,9145) y construcción en la Calle 15 (7,0170, −73,9160) | — | No son instalaciones eléctricas. |

Una verificación independiente (22-oct-2026) repitió la consulta a OpenStreetMap y revisó de nuevo el norte, el noreste y el occidente del casco y el patio del sur con imágenes de Google y de Esri (`data/geo/img/vr_red_*.png`): llega a la misma conclusión. El patio del sur no se puede descartar por tamaño, pero está dentro de la base industrial del campo Casabe.

**Confianza: ninguna ubicación confirmada.** Las imágenes del barrido quedaron en `data/geo/img/red_se_*.png` (fuera del repositorio, como todas las imágenes de Google y Esri).

**La ubicación que usa `docs/12`.** El documento del parque del relleno toma como ubicación probable el lugar de Google "Subestación yondo epm", en **7,0032 N, −73,9226 O**, donde el satélite muestra un patio pequeño de equipos y un edificio (`data/proyectos/parque_relleno/energia.json`, consulta del 22-oct-2026). Queda a unos 1,3 km al occidente de la alcaldía, en línea recta (cálculo propio). Ese punto no figura entre los candidatos revisados en esta sección (la búsqueda de etiquetas de Google Maps descrita arriba no lo encontró; se halló después, al preparar `docs/12`) y EPM no lo ha confirmado. De él dependen la línea de unos 2,6 km y los $805,5 M del capítulo de conexión del parque. Las dos lecturas coinciden en lo que hay que hacer: confirmar la ubicación con EPM antes de diseñar cualquier línea.

### 8.3 Los circuitos de 13,2 kV

- **Casco urbano:** No publicado. EPM no divulga el GIS de sus redes. Los avisos de cortes de 2022, 2025 y 2026 hablan de la "zona urbana y rural" o listan veredas (Rocas de San Francisco, Jabonal, Vietnam, La Rompida 1 y 2, El Totumo, Puerto Nuevo, La Felicidad, El Campo Cimitarra, El Bagre, Cuatro Bocas, Bellavista, El Cedro, El Descanso, Las Lomas, Bocas de San Juan): eso solo confirma que de la subestación salen circuitos que alimentan tanto el casco como las veredas, no su recorrido.
- **Hacia la PTAP:** La PTAP (7,00919, −73,932) y sus pozos tienen fronteras propias de EPM con tarifa ESPD (data/microrred.json), así que hay una línea de 13,2 kV o un ramal hasta el predio; su recorrido no se ve en el satélite (el bosque lo tapa) ni hay Street View en la vía a la Laguna del Miedo (Calle 15). Hipótesis de trabajo, sin verificar: el ramal sale por la Calle 15 / vía a la Laguna del Miedo, que es el único acceso del predio.
- **Codificación:** Según la RA6-020 de EPM, los circuitos de 13,2 kV de las subestaciones del Mercado Regional se marcan MNN-11 a MNN-16; para Yondó serían 165-11 a 165-16 (hasta seis salidas). No se encontró cuántos están en servicio.

### 8.4 Qué cambia para el presupuesto

El nodo "conexion" de data/microrred.json (pos [-30, -20] en la escena) es esquemático y no es la ubicación real. Para la red de la microrred no hace falta llegar a la subestación: la red de 13,2 kV de EPM pasa por todas las calles del casco y cada sede ya tiene acometida. El tramo subestación → troncal solo se costea en la fase de microrred física (un alimentador propio), cuando EPM entregue la ubicación y el punto de conexión aprobado. Si EPM confirma el punto que usa `docs/12`, ese tramo arrancaría a unos 1,3 km en línea recta de la alcaldía y se costearía con los precios de la sección 7.

Pendiente: Derecho de petición a EPM (Ley 1755 de 2015): ubicación de la S/E Yondó, diagrama unifilar, número y recorrido de los circuitos 165-1x, capacidad disponible por circuito y transformador para AGPE (CREG 174 de 2021) y planos de las redes de 13,2 kV del casco y hacia la PTAP. Consulta de capacidad disponible en el aplicativo de EPM para generación distribuida (por circuito). Visita de campo con GPS a las salidas de la vía a Barrancabermeja y a la Calle 15.

## 9. Distancias y presupuesto por tramo

**La red propuesta une 22 puntos con 21 tramos: 10,066 km de red nueva (4,596 km urbanos y 5,47 km rurales) que cuestan unos $2.965 millones** (cálculo propio; $2.964.911.962, rango $2.075.438.373–$4.447.367.943; clase 4). Solo la red de media tensión (capítulos urbano y rural, $1.177.429.869) sale a unos **$117 M por km** ($116.970.978). Con transformadores, acometidas, protecciones, fibra, preliminares e indirectos, la red completa equivale a unos **$295 M por km** ($2.964.911.962 ÷ 10,066 km, cálculo propio). Los datos están en `data/red/distancias.json` y `data/red/presupuesto_red.json`.

**Cómo se midió.** Cada distancia es el camino más corto por las calles de OpenStreetMap más la acometida en línea recta de cada sede a la calle. La red es el árbol de mínima longitud que sale de la alcaldía (CCED). Si se suman los 21 tramos por la vía dan 11,442 km; la red nueva mide menos (10,066 km) porque varios tramos comparten calle y esa calle se cuenta una sola vez. Son urbanos los km a menos de 1,1 km del centro (`scripts/geo/red_distancias.py`).

**Qué no lleva.** No hay red de baja tensión nueva ni canalización: cada sede se conecta con su acometida (APU-11) y la red va aérea. La red subterránea, unas 7 veces más cara por km, solo se justifica en cruces, plazas o frente al hospital. Tampoco lleva la solar ni las baterías, que van en cada sede, ni el enlace hasta la subestación de EPM, que se suma cuando EPM confirme la ubicación (sección 8).

### 9.1 Por mayores

| Capítulo | Cantidad | Valor (pesos de 2026) |
|---|---|---:|
| Preliminares, permisos y trámites (topografía, RETIE, servidumbre y poda rural, trámites con EPM) | 10,066 km; 5,47 km rurales | $150.793.800 |
| Red de media tensión aérea 13,2 kV, zona urbana | 4,596 km × APU-06U | $702.921.748 |
| Red de media tensión aérea 13,2 kV, zona rural | 5,47 km × APU-06R | $474.508.121 |
| Transformadores de distribución | 19, uno por sede | $566.048.392 |
| Acometidas y medición bidireccional | 19 | $259.672.354 |
| Protección y maniobra | 1 reconectador y 6 seccionalizadores | $275.606.077 |
| Fibra óptica sobre los mismos postes | 10,67 km, 21 conexiones de sede y el nodo central del CCED | $207.821.157 |
| **Obra (sin preliminares)** | | **$2.486.577.849** |
| Ingeniería de detalle (4 % de la obra) | | $99.463.114 |
| Plan de manejo ambiental, de tráfico y SST (1,5 % del costo directo) | | $29.150.971 |
| Interventoría (8 % de la obra) | | $198.926.228 |
| **Indirectos** | | **$327.540.313** |
| **Total** | | **$2.964.911.962** |

La torre del hospital, el tanque elevado y el parque del relleno no llevan transformador ni acometida en esta red: por eso hay 19 y no 22.

### 9.2 Por tramo (millones de pesos de 2026)

"Red y fibra" es la red de media tensión, la fibra y lo que se paga por km (topografía y RETIE; en zona rural, también servidumbre y poda). "Sede" es el transformador, la acometida con medidor bidireccional y la conexión de fibra. "Total del tramo" suma las dos y el 12 % de ingeniería e interventoría.

| # | Desde | Hasta | km por la vía | km de red nueva | Urbanos | Rurales | Red y fibra | Sede | Total del tramo |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Alcaldía (CCED) | Policía | 0,132 | 0,113 | 0,113 | 0,000 | 19,3 | 41,1 | 67,7 |
| 2 | Policía | Registraduría | 0,192 | 0,135 | 0,135 | 0,000 | 23,1 | 41,1 | 71,9 |
| 3 | Policía | Parque Educativo | 0,276 | 0,263 | 0,263 | 0,000 | 45,0 | 41,1 | 96,4 |
| 4 | Parque Educativo | Biblioteca | 0,069 | 0,055 | 0,055 | 0,000 | 9,4 | 41,1 | 56,6 |
| 5 | Biblioteca | Coliseo | 0,084 | 0,064 | 0,064 | 0,000 | 10,9 | 41,1 | 58,3 |
| 6 | Parque Educativo | Casa de la Cultura | 0,297 | 0,235 | 0,235 | 0,000 | 40,2 | 41,1 | 91,1 |
| 7 | Casa de la Cultura | Aguas y Aseo | 0,168 | 0,109 | 0,109 | 0,000 | 18,6 | 41,1 | 67,0 |
| 8 | Aguas y Aseo | Concejo | 0,262 | 0,246 | 0,246 | 0,000 | 42,1 | 41,1 | 93,2 |
| 9 | Concejo | Bomberos | 0,150 | 0,138 | 0,138 | 0,000 | 23,6 | 41,1 | 72,5 |
| 10 | Casa de la Cultura | I.E. sede La Patria | 0,374 | 0,348 | 0,348 | 0,000 | 59,5 | 41,1 | 112,7 |
| 11 | I.E. sede La Patria | Centro Vida (adulto mayor) | 0,352 | 0,313 | 0,313 | 0,000 | 53,5 | 41,1 | 106,0 |
| 12 | Bomberos | I.E. sede principal | 0,412 | 0,399 | 0,399 | 0,000 | 68,2 | 41,1 | 122,5 |
| 13 | Aguas y Aseo | CIC | 0,423 | 0,383 | 0,383 | 0,000 | 65,5 | 53,0 | 132,7 |
| 14 | CIC | Megacolegio | 0,348 | 0,196 | 0,196 | 0,000 | 33,5 | 53,0 | 96,9 |
| 15 | Policía | Hospital | 0,557 | 0,530 | 0,530 | 0,000 | 90,6 | 43,1 | 149,7 |
| 16 | Hospital | Torre del hospital ¹ | 0,149 | 0,111 | 0,111 | 0,000 | 19,0 | 2,2 | 23,7 |
| 17 | Hospital | PTAP | 2,707 | 2,574 | 0,958 | 1,616 | 349,2 | 74,7 | 474,7 |
| 18 | PTAP | Captación (pozos) | 0,124 | 0,111 | 0,000 | 0,111 | 12,7 | 53,0 | 73,6 |
| 19 | PTAP | Tanque elevado ² | 1,051 | 0,541 | 0,000 | 0,541 | 62,1 | 2,2 | 71,9 |
| 20 | Tanque elevado | Parque del relleno ³ | 0,639 | 0,614 | 0,000 | 0,614 | 70,4 | 2,2 | 81,3 |
| 21 | Parque del relleno | PTAP veredal | 2,676 | 2,588 | 0,000 | 2,588 | 296,9 | 53,0 | 391,9 |
| | **Suma de los 21 tramos** | | **11,442** | **10,066** | **4,596** | **5,470** | **1.413,2** | **830,0** | **2.512,4** |
| | Costos comunes (no se reparten por tramo) | | | | | | | | 452,5 |
| | **Total de la red** | | | | | | | | **2.964,9** |

¹ **Hospital → torre (0,111 km).** La torre trae su acometida en media tensión y su subestación de 300 kVA en su propio presupuesto (`docs/11`, ítems 10.01 y 10.02). Aquí solo se cobran la red y la conexión de datos.

² **PTAP → tanque elevado.** Solo telemetría: el tanque se alimenta en baja tensión desde la planta.

³ **Tanque elevado → parque del relleno (0,614 km, $81,3 M).** El centro de transformación del parque (1.000 kVA para los 800 kW de la granja) y su línea a EPM están en el presupuesto del parque (`docs/12`). Este tramo es la misma derivación corta (0,6–0,8 km) que `docs/12` propone como alternativa a la línea de 2,6 km: si se construye con esta red, la línea del parque sobra. No se deben pagar las dos.

**Costos comunes ($452,5 M).** Son las piezas que sirven a toda la red y no se reparten por tramo:

| Pieza | Millones de 2026 |
|---|---:|
| Protección y maniobra (reconectador y seccionalizadores) | 275,6 |
| Nodo central de datos en el CCED (APU-14) | 41,2 |
| Transformador de 37,5 kVA y acometida de la alcaldía, que es la raíz de la red | 40,9 |
| Trámites con EPM y certificados RETIE de transformadores y acometidas | 36,4 |
| Plan de manejo ambiental, de tráfico y SST | 29,2 |
| Ingeniería e interventoría (12 %) de las tres primeras piezas | 42,9 |
| Menos el 12 % que el reparto por tramo carga sobre topografía, RETIE, servidumbre y poda, que no llevan indirectos | −13,7 |
| **Total** | **452,5** |

## 10. Qué falta y cómo verificar

1. **Tres cotizaciones** de transformadores trifásicos de 45, 75 y 112,5 kVA, postes de 12 m, conductor ACSR 1/0 y 2/0, trenzado 3 × 1/0 y medidores bidireccionales homologados por EPM. Son los ítems con más peso que hoy son estimación.
2. **Tarifas de EPM** por revisión de diseños, recibo de obra y conexión, y su procedimiento para conectar una red de propiedad del municipio (o la cesión de activos).
3. **Derecho de petición a EPM** por la ubicación de la subestación, el unifilar y los circuitos (sección 8).
4. **AIU real** de los últimos contratos de redes eléctricas de Antioquia en SECOP II (los documentos del proceso están detrás de un captcha y no se pudieron leer de forma automática).
5. **Jornales de la zona:** confirmar con dos contratistas de Barrancabermeja el salario de linieros y ayudantes.

## Verificación independiente (22 de octubre de 2026)

Se abrieron de nuevo las fuentes y se rehicieron las cuentas. **Coinciden con la fuente:** los 45 valores de la CREG (dic-2017) y sus tablas; el IPP de oferta interna (113,41 en dic-2017 y el promedio de ene–sep 2026, 186,81); los 8 APU de la SIF de 2020 y sus anclas (poste, cruceta, varilla, DPS, caja primaria, concreto y acero); el tope de la CRC ($2.541 en pesos de 2023); los precios de Homecenter y de Fenix; el salario mínimo; las obras e interventorías de SECOP; los vanos y las listas de materiales de EPM, y los datos de la subestación (10 MVA, 32 km, $15.509 millones y código 165). Los archivos se regeneran igual con los scripts.

**Se corrigió:**

1. **Postes:** el de 12 m y 1.050 kgf pasó de $1.750.000 a $1.256.992 (APU oficial de la SIF actualizado con IPC); el de 750 kgf, de $1.450.000 a $1.150.000, y el de 510 kgf, de $1.250.000 a $1.050.000. El argumento anterior (que el concreto subió más que el IPC) lo contradice el IPP del DANE.
2. **Vientos por km:** de 6 a 12 en zona urbana y de 3 a 5,5 en zona rural, para seguir las listas de materiales de EPM (4 vientos por estructura de referencia RA2-004).
3. **Interventoría:** se agregaron dos pares de Yondó que faltaban (Bocas de San Francisco, 2014, y Caño Negro y Caño Bonito, 2013–2014). La mediana de los 9 pares es 7,7 %; se sigue usando 8 %.
4. **Transformadores:** el bajante de BT del de 75 kVA pasa de 4 × 2/0 a 4 × 3/0 (197 A, más de los 175 A que admite el 2/0); cada variante lleva su calibre; el monofásico ya no lleva cruceta de 2,4 m (RA3-026); el trifásico lleva 6 estribos (RA2-007). Se quitó el 3 % de transporte que se cobraba dos veces sobre postes y transformadores.
5. **Estructura terminal RA2-003:** 2 eslabones (la norma), no 5.
6. **Fibra:** la acometida (drop) y la roseta sí tienen precio publicado en Fenix ($415/m y $22.998 con IVA); la fibra de 48 hilos figura "sin existencia".
7. **Textos:** la explicación de la brecha CREG–mercado en transformadores (sección 3), la capacidad de la acometida del APU-11 (hasta unos 60 kVA con Cu 2/0) y la cita de Magneto365.

**Queda pendiente:** cotizar postes, transformadores trifásicos, conductores y medidores; confirmar en los documentos de SECOP las dos interventorías de 2014 con el mismo valor ($255.351.440); y ubicar la subestación con EPM o en campo.

## Fuentes

- **CREG**: Resolución CREG 015 de 2018 (metodología de remuneración de la distribución), capítulo 14: unidades constructivas (UC). Texto compilado con las modificaciones de la Res. CREG 085 de 2018 y 036 de 2019. Fecha: 2018-01-29 (valores en pesos de diciembre de 2017). <https://gestornormativo.creg.gov.co/gestor/entorno/docs/resolucion_creg_0015_2018.htm>
- **DANE**: Índice de Precios del Productor (IPP), oferta interna, total. Anexo de septiembre de 2026, hoja 2.1 (base dic-2014 = 100). Fecha: 2026-10 (sep-2026 provisional). <https://www.dane.gov.co/files/operaciones/IPP/anex-IPP-sep2026.xlsx>
- **DANE**: IPC promedio anual; factores a pesos de 2026 en data/fuentes/ipc_dane.csv del repositorio. Fecha: 2026-10. <https://www.dane.gov.co/files/operaciones/IPC/sep2026/anex-IPC-Indices-sep2026.xlsx>
- **Gobernación de Antioquia**: Secretaría de Infraestructura Física: base de datos de análisis de precios unitarios (APU) de referencia, segundo semestre de 2020, capítulo 17 (redes eléctricas), págs. 398–424. Fecha: 2020-04-01 (fecha del APU). <https://www.antioquia.gov.co/images/PDF2/Infraestructura/2020/08-agosto/apu-base-referencia-sif-2020-semestre-ii.pdf>
- **EPM**: Normas técnicas de construcción de redes de distribución (RA2-001, RA2-003, RA2-004, RA2-006, RA2-007, RA2-010, RA2-011, RA2-021, RA2-031, RA3-026, RA3-029): listas de materiales por estructura y vanos máximos. Fecha: 2013-06 a 2014-02. <https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA2-001.pdf>
- **EPM**: Norma RA6-020 Marcación para la identificación de circuitos (tabla de códigos de subestaciones del Mercado Regional). Fecha: 2009-09 (modificada 2021-05). <https://comercializadorenergia.epm.com.co/content/dam/epm/proveedores-y-contratistas/RA6-020.pdf>
- **EPM**: "EPM pone en marcha solución de energía eléctrica en Yondó, que beneficiará a 19.000 personas". Fecha: 2020-07-07. <https://www.epm.com.co/clientesyusuarios/noticias-y-novedades/epm-pone-en-marcha-solucion-de-energia-electrica-en-yondo--que-b/>
- **EPM**: "En 2021 EPM entró en operación importantes proyectos de infraestructura de servicios públicos" (32 km de redes, $15.509 millones). Fecha: 2021-12. <https://www.epm.com.co/clientesyusuarios/noticias-y-novedades/en-2021-epm-entro-en-operacion-importantes-proyectos-de-infraestructura-de-servicios-publicos/>
- **Homecenter (Sodimac Colombia)**: Homecenter Colombia, transformadores en aceite tipo poste marca Ecuatran (códigos 790149 y 790148); precio de venta al público. Fecha: 2026-10-22 (consulta). <https://www.homecenter.com.co/homecenter-co/product/790149/transformador-en-aceite-clase-e-monofasico-t-poste-25kva-13200-208-v/790149/>
- **Fenix Comercial**: Fenix Comercial (distribuidor colombiano de fibra y redes), catálogo en línea: cable ADSS, herrajes, cajas, OLT, ONU y switches; precios "+ IVA". Fecha: 2026-10-22 (consulta). <https://fenixcomercial.com.co/?s=ADSS&post_type=product>
- **Gobierno nacional (resumen de ConsultorSalud)**: Salario mínimo 2026: $1.750.905 (Decreto 1469 de 2025; tras la suspensión del Consejo de Estado se expidió el Decreto 0159 de 2026 con el mismo valor). Fecha: 2025-12-29. <https://consultorsalud.com/aumento-del-salario-minimo-en-colombia-2026/>
- **Magneto365 (portal de empleo)**: Salario promedio de un técnico electricista en Colombia ($2.387.083; los más altos, hasta $4,5 M, en Bogotá, Medellín y zonas industriales o petroleras como Barrancabermeja). Fecha: 2026-10-22 (consulta). <https://www.magneto365.com/co/preguntas-frecuentes/tecnico-electricista/cual-es-salario-de-un-tecnico-electricista-en-colombia>
- **CRC**: Concepto sobre la Res. CRC 7120 de 2023 (art. 4.10.3.1 de la Res. CRC 5050 de 2016): tope de remuneración mensual por punto de apoyo en postes del SDL. Fecha: 2026-06-16 (valores en pesos de 2023). <https://www.crcom.gov.co/sites/default/files/normatividad/2026520163.pdf>
- **Colombia Compra Eficiente**: SECOP I y II: contratos de obra e interventoría de redes eléctricas (Yondó 2014–2017; Santander 2022–2023; Guapotá 2026). Fecha: 2014–2026. <https://www.datos.gov.co/resource/jbjy-vk9h.json>
- **DNP**: Catálogo de Proyectos Tipo (consultado): no hay proyecto tipo de redes de distribución; en Minas y Energía solo "Celdas solares uso residencial" y "Beneficio de oro"; en TIC, "Zonas digitales", "Implementación de TIC" y "Centro TIC municipal". Fecha: 2026-10-22 (consulta). <https://proyectostipo.dnp.gov.co/>
- **colaboradores de OpenStreetMap**: OpenStreetMap (ODbL), elementos power=* en 12 km a la redonda (Overpass, base del 31-may-2026) y vías. Fecha: 2026-05-31. <https://www.openstreetmap.org/way/1426109682>
- **EPM**: normas de construcción RA citadas en la sección 5.2 (un PDF por norma en https://www.epm.com.co/content/dam/epm/proveedores-y-contratistas/).
- **EPM**: avisos de interrupciones con veredas de Yondó: 21-mar-2025 <https://www.epm.com.co/institucional/sala-de-prensa/noticias-y-novedades/interrupciones-energia-mantenimiento-marzo-21-2025/> y 5-dic-2025 <https://www.epm.com.co/institucional/sala-de-prensa/noticias-y-novedades/interrupciones-energia-epm-antioquia-9-12-diciembre-2025/>.

