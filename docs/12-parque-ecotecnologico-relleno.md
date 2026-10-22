# 12 · Del relleno Las Américas al Parque Ecotecnológico de Yondó

**Cerrar bien el relleno sanitario, llevar la basura a un relleno regional con licencia y convertir el predio en un parque: una granja solar de 1 MWp sobre las celdas que baja la factura de los hogares de estratos 1 y 2, un coworking rural con internet y energía propia, una granja que enseña a producir y compostar, y un circuito para correr y pedalear a 4 km del parque principal.**

> Estado: **prefactibilidad**, con fecha de corte del 22 de octubre de 2026. Cada cifra dice si es un **dato oficial** (copiado de la fuente), un **cálculo propio** (operación sobre datos oficiales, con el método a la vista) o una **estimación** (supuesto con rango, por confirmar). Pesos constantes de 2026 (IPC del DANE, base enero–septiembre de 2026). Los datos completos están en `data/proyectos/parque_relleno/` (diagnóstico, energía, programa, presupuesto y financiación) y el modelo 3D en `data/edificios/relleno_parque.json`.
>
> **Inspirado en los proyectos tipo del DNP.** El parque se armó con las piezas que el Departamento Nacional de Planeación ya tiene estandarizadas y con MGA lista: Centro TIC municipal (para el coworking), Parque recreodeportivo, Ciclo-infraestructura y servicios complementarios, Recuperación de cobertura vegetal y Señalización turística. Donde no hay proyecto tipo (clausura de rellenos y granjas solares conectadas a la red) se siguen el Decreto 1784 de 2017, la Resolución 938 de 2019 y la guía de la EPA y el NREL (2022). Ver la sección 5.4.

## En pocas palabras

- **El relleno opera vencido.** Yondó dispone su basura desde 1999 en el relleno Las Américas (vereda Las Américas, predio del municipio, operado por Aguas y Aseo). Según el SUI, su licencia de Corantioquia venció el **12 de noviembre de 2023** y su vida útil terminó en 2023 (dato oficial). Aun así, en noviembre de 2025 se contrató una obra de mantenimiento y adecuación y en mayo de 2026 se publicaron procesos de maquinaria, material de cobertura y arreglo de la vía (SECOP).
- **Toca clausurarlo** con cobertura final, manejo de lixiviados y gases, y un **plan de posclausura de al menos 20 años** (Resolución 938 de 2019, art. 4). La basura iría al **Parque Tecnológico Ambiental San Silvestre** (Barrancabermeja), con licencia hasta 2044, a **40 km** por vía (cálculo propio). Cuesta unos **$321 millones al año** (estimación, $221–466 M), menos que operar el relleno local (unos $576 M al año en contratos, 2019–2023) y sin los $3.900 M que costaría ampliarlo.
- **Sobre las celdas cabe una granja solar de 997 kWp** (1.812 módulos de 550 Wp) que produce unos **1,34 GWh al año** (cálculo propio, rango 1,30–1,45 GWh).
- **Esa energía alcanza para un bloque solar de 50 kWh al mes para 2.236 hogares de estratos 1 y 2** (el 27 % de los 8.193 hogares de esos estratos que atiende EPM): un ahorro de **$21.352 al mes en estrato 1 (31 % de la factura típica)** y de $26.690 en estrato 2 (22 %). Si reemplaza consumo subsidiado, la Nación deja de pagar unos **$721 millones al año** en subsidios y los hogares se ahorran unos **$608 millones** (cálculo propio).
- **La figura legal:** una **comunidad energética** de hogares de estratos 1 y 2 (Decreto 2236 de 2023) que actúa como **autogenerador colectivo** (Resolución CREG 101 072 de 2025) y se postula a **Colombia Solar** (Decreto 0972 de 2025 y Resolución 40159 de 2026), que cambia subsidios por paneles.
- **El parque** pone todo lo que tiene gente **fuera de las celdas y a 30 m o más de las celdas y lagunas que se ven** (la zona de servicios hay que revisarla con apiques antes de diseñar, ver la sección 1.2): coworking de 312 m² con 40 puestos, cafetería y duchas, taller de bicicletas, granja con invernadero, huerta, compostaje y apiario, módulo recreodeportivo, mirador y un circuito de 0,9 km conectado con el pueblo por una ruta ciclista de 3,9 km.
- **Cuánto cuesta:** unos **$16.417 millones** (rango de prefactibilidad $11.492–24.625 M): $4.194 M para estudios y clausura, $5.603 M para la granja solar y la conexión a EPM, y $6.620 M para el parque. La línea a EPM va con el precio rural de la base de la red ya corregida (sección 7).

## 1. Dónde está el relleno y cómo está hoy

### 1.1 Ubicación

No hay un lugar de Google para el relleno ni fotos con coordenadas. Se ubicó cruzando documentos, contratos y satélite (confianza **media**):

| Prueba | Qué dice | Fuente |
|---|---|---|
| Superservicios, visita de mayo de 2018 | "Relleno sanitario Las Américas ubicado a 2 kilómetros del municipio de Yondó en la vereda Las Américas, operado por el mismo prestador"; cerca de postes y alambre de púas, chimeneas de piedra, lixiviados que van a un pozo y se recirculan | Evaluación integral, págs. 68–74 |
| Contratos de 2015 y 2025 | "Torre para tanque de almacenamiento de agua potable; tramo de vía y cerramiento del predio del relleno" (2015). "Vía de acceso (Calle 16) y vías internas del acueducto y relleno" (BPIN 2025058930008) | SECOP I; MapaInversiones |
| Satélite de Google (posterior a 2024) | Dos plataformas grises de material de cobertura, una celda con pasto, cuatro piscinas rectangulares, vía interna en afirmado nueva (en diciembre de 2024 se compró material triturado para la vía del relleno) y una caseta en la entrada norte | Google z19–z20 |
| Satélite de Esri (enero de 2020) | Plataforma parda y blanca de unas 3–4 ha con las mismas piscinas llenas de agua oscura, y otra mancha parda de unas 2,7 ha al sur | Esri World Imagery |
| Lugar de Google "Escombrera" | 140 m al norte, sobre el área de préstamo de material de cobertura | Google Maps |

El sitio queda en **7,0140 N, 73,9342 O**, a **348 m** del tanque elevado del acueducto y a **588 m** de la planta de tratamiento (PTAP) (cálculo propio).

**Distancia y desnivel.** Desde el Parque Principal (7,007366, −73,909609) hay **3,9 km por vía** (cálculo propio: 3,80 km en OpenStreetMap por la Calle 50, la Carrera 57, la vía Barrancabermeja–Yondó y el ramal destapado que bordea el relleno; el enrutador OSRM da 3,99 km). En línea recta son 2,8 km. El terreno es casi plano: el modelo de elevación SRTM da 70–80 m en el relleno y 68–80 m en el parque principal, con lomas suaves en el camino (la del tanque elevado llega a unos 85 m). **Desnivel aproximado: 0 a +10 m** (estimación). Es una ruta fácil para ciclistas y corredores.

### 1.2 Lo que se ve y se midió (cálculo propio sobre Google z20)

| Elemento | Medida |
|---|---|
| Celda occidental (plataforma gris reciente) | 1.844 m² |
| Celda oriental (frente activo, con borde de piedra) | 2.452 m² |
| Celda norte con pasto (probable celda clausurada de las etapas 1 y 2) | 3.732 m² |
| **Celdas visibles en total** | **8.026 m² (0,80 ha)** |
| Etapas del Manual de Operaciones (dato oficial) | 1.840 + 9.483 + 4.243 + 2.893 = 18.459 m² |
| Zona intervenida en enero de 2020 alrededor de las celdas (estimación) | unas 3–4 ha |
| Mancha parda al sur de las lagunas en enero de 2020, donde van los servicios del parque (estimación) | unas 2,7 ha |
| Cuatro piscinas (probables lagunas de lixiviados) | 20×18, 18×16, 13×8 y 8×8 m, giradas 35° (816 m² en total) |
| Chimenea o caja de gases visible | sobre la celda oriental |

La huella real de los residuos está entre 0,8 y 4 ha (estimación). Se define con topografía, apiques y georradar antes de diseñar la cobertura.

**Ojo con la zona de servicios.** En la imagen de Esri de enero de 2020 también estaba parda la franja al sur de las lagunas, donde este proyecto pone el coworking, la cafetería, la plazoleta y la granja. Puede ser potrero seco (enero es época seca), tierra removida o residuos regados; en Google (después de 2024) ya está empradizada. Los apiques, el georradar y la línea base de biogás tienen que cubrirla antes de diseñar las edificaciones. Si aparecen residuos, la huella llegaría a unas 6,6 ha y los servicios se corren hacia el occidente o el sur.

**Un botadero más viejo.** Noticias Caracol (23 de septiembre de 2020) informó que los dos pozos que hoy abastecen al acueducto se perforaban "dentro del polígono que otrora ocupara un relleno sanitario", el de Las Américas, que funcionó allí hace unos 25 años; Corantioquia suspendió la obra porque no tenía permiso de captación. Ese sitio antiguo no está delimitado y **hay que incluirlo en la clausura** (Resolución 1390 de 2005) y en el monitoreo del agua subterránea.

### 1.3 Estado legal y operación

| Hecho | Dato | Tipo y fuente |
|---|---|---|
| Inicio de operación | 21 de julio de 1999 | Dato oficial, SUI |
| Licencia inicial | Resolución 130ZF-3106 del 19 de junio de 2008 | Dato oficial, Superservicios 2018, pág. 71 |
| Prórroga | Resolución 130ZF-1311-6219 del 12 de noviembre de 2013, por 10 años; en 2014 Corantioquia la redujo a 3 años por el área disponible (el SUI la registra como 130FZ13115219) | Dato oficial, ídem |
| Vencimiento | Licencia vigente hasta el **12 de noviembre de 2023**; vida útil hasta el 31 de diciembre de 2023 | Dato oficial, SUI (datos.gov.co wu2p-623h y 84tn-nnhf) |
| Capacidad | 74.303 m³ (PGIRS) u 81.147 m³ (SUI) | Dato oficial |
| Toneladas | 167 t/mes en 2018; 3.316 t en 2020 y 3.761 t en 2021 | Dato oficial, Superservicios y SUI |
| Acumulado 1999–2026 | unas 78.000 t (71.000–84.000) | Estimación |
| Volumen ocupado | 78.000–130.000 m³ solo de residuos (densidad de 1,0 a 0,6 t/m³); con el material de cobertura, 94.000–156.000 m³. Supera la capacidad de diseño | Estimación |
| Problemas que encontró la Superservicios | sin báscula ni cobertura diaria; gallinazos, insectos y olores; sin permiso de vertimientos; sin monitoreo de agua ni aire; puerta abierta a terceros; "presuntamente operando sin un permiso ambiental vigente" | Dato oficial, págs. 69–74 |
| Ampliación formulada | BPIN 2025058930015, $3.701 M de 2025 ($3.901 M de 2026), devuelto a MGA | Dato oficial, MapaInversiones |
| Contratos del relleno | promedio de $576 M al año en 2019–2023 (pesos de 2026), sin contar la nómina | Cálculo propio, SECOP |

No se encontró una prórroga, una licencia nueva ni sanciones publicadas.

## 2. Cerrarlo bien

### 2.1 Lo que exige la norma

| Norma | Qué exige |
|---|---|
| Decreto 1077 de 2015 modificado por el **Decreto 1784 de 2017**, art. 2.3.2.3.3 | El municipio debe asegurar la disposición final, en su territorio o en otro, participando en soluciones regionales |
| Decreto 1784, arts. 2.3.2.3.5 y 2.3.2.3.7 | Enfoque regional; para cofinanciar con la Nación hay que analizar la regionalización |
| Decreto 1784, art. 2.3.2.3.12 | El uso futuro del sitio clausurado debe quedar definido (aquí: parque y granja solar) |
| Decreto 1784, arts. 2.3.2.3.11 y 2.3.2.3.16 | Instrumentación (piezómetros, pozos de monitoreo, estabilidad) y monitoreo de lixiviados (DBO, DQO, sólidos), agua subsuperficial, biogás (metano, H₂S, límite de explosividad), olores, vectores e incendios; captura y quema tecnificada del biogás |
| Decreto 1784, art. 2.3.2.3.17 | El prestador debe tener una **provisión** para el cierre, la clausura, la posclausura y el monitoreo |
| **Resolución 938 de 2019**, art. 4 | Cierre, clausura y posclausura: **mínimo 20 años**, asociados al uso futuro |
| Resolución 0330 de 2017 (RAS) | Sus artículos de rellenos (223 y 224) fueron **eliminados por la Resolución 0799 de 2021**; los requisitos quedaron en el Decreto 1784 y la Resolución 938 |
| Resolución 1390 de 2005 (modificada por la 1890 de 2011) | Clausura de botaderos: aplica al botadero antiguo si se confirma |
| Corantioquia | Aprueba el plan de clausura y posclausura y hace el seguimiento |

### 2.2 El plan de clausura

1. **Delimitar** los residuos (topografía con dron, 20–30 apiques, georradar), incluido el botadero antiguo.
2. **Reconformar** las celdas hasta pendientes de 3–5 % en la parte alta.
3. **Cobertura final** de baja permeabilidad: 0,45 m de arcilla compactada, geomembrana de polietileno de 1,0 mm, geodrén, 0,45 m de suelo, 0,15 m de capa orgánica y pasto rastrero nativo.
4. **Aguas lluvias**: canales perimetrales que no toquen los lixiviados.
5. **Lixiviados**: drenaje perimetral hacia las lagunas A y B, impermeabilizadas como lagunas de igualación, y un **humedal artificial de 400 m²** que pule el efluente; las lagunas C y D se rellenan.
6. **Gases**: 10 chimeneas pasivas con biofiltro (en los pasillos entre filas de paneles) y un quemador o biofiltro central. Con unas 78.000 t de residuos viejos, el biogás no alcanza para generar electricidad de forma rentable (el Decreto 1784 pide un análisis de beneficio-costo antes de aprovecharlo).
7. **Monitoreo**: 4 pozos de agua subterránea (que cubran también los pozos del acueducto) y 20 hitos y piezómetros.
8. **Posclausura de 20 años**: inspección y reparación de la cobertura, asentamientos dos veces al año, lixiviados y humedal cada trimestre, agua subterránea cada semestre y biogás mensual el primer año. Costo: unos **$190 M al año** (estimación, $130–260 M).

### 2.3 A dónde va la basura

| Opción | Distancia por vía | Licencia | Comentario |
|---|---|---|---|
| **Parque Tecnológico Ambiental San Silvestre** (Veolia), Barrancabermeja | **40,2 km** (OSRM, 44 min) | CAS, Resolución 1121 de 2014, **hasta el 27 de diciembre de 2044** (SUI) | Recomendada. Riesgos: el puente Guillermo Gaviria Correa tuvo socavación y cierres en marzo de 2026 (Vanguardia); organizaciones locales denuncian daños ambientales y Veolia dice que la operación está normalizada (Global Witness) |
| Registros de Rediba y Yerbabuena, Barrancabermeja | — | Misma licencia de la CAS (Resolución 1121 de 2014) que San Silvestre (SUI) | No son otra opción: son registros del mismo relleno, que Veolia le compró a Rediba en 2019 (Global Witness). Rediba tuvo una condena penal de su exgerente y la Sentencia T-227 de 2017 sigue a cargo del operador |
| Relleno La Tabaca, Puerto Berrío | unos 141 km | vencida el 2 de septiembre de 2021 (SUI) | Descartada |

**Costo de la disposición regional:** unos **$321 M al año** (estimación): 3.900 t/año (3.500–4.300) × [tarifa de disposición de $60.000/t (45.000–80.000) + 20,2 km de tramo excedente a $1.100/t·km (900–1.400)]. Las tarifas reales salen del contrato con el operador y de la metodología de la CRA. Una estación de clasificación y aprovechamiento (proyecto tipo ECA del DNP) y el compostaje bajan las toneladas.

**Hace falta un plan de contingencia** por el puente (ruta alterna y acuerdo temporal con otro sitio licenciado).

## 3. La granja solar sobre las celdas

### 3.1 Diseño

| Parámetro | Valor | Tipo |
|---|---|---|
| Módulos | **1.812** de 550 Wp | Cálculo propio sobre el trazado |
| Potencia | **996,6 kWp DC**; 8 inversores de 100 kW = **800 kW AC** (relación 1,25) | Cálculo propio |
| Bloque A (fase 1) | 1.394 módulos (766,7 kWp) sobre la cobertura de las celdas visibles (8.601 m²) | Cálculo propio |
| Bloque B (fase 2) | 418 módulos (229,9 kWp) en la zona del nororiente que en 2020 se veía intervenida (3.709 m²), solo si los apiques confirman celdas estables o suelo natural | Cálculo propio |
| Mesas | dos módulos en vertical, inclinadas 10° al sur, borde bajo a unos 1,35 m | Diseño |
| Distancia entre filas | 6,5 m (pasillo libre de 1,97 m) | Cálculo propio |
| Sombras | El 21 de diciembre, la sombra norte–sur de una mesa mide 0,63 m a las 9:00 y 0,89 m a las 8:00: no hay sombra entre filas de 8:00 a 16:00 | Cálculo propio |

**Cómo se monta sin dañar la cobertura** (guía EPA/NREL, 2022, secciones 4.2 y 5):

- **Lastres de concreto prefabricados** (unos 430 bloques de 0,4 m³): nada perfora la geomembrana ni la arcilla.
- **Asentamientos:** mesas cortas, uniones flexibles, nivelación ajustable en cada pórtico y hitos con lectura semestral. La granja se monta cuando la cobertura haya asentado (los desarrolladores evitan rellenos tapados hace menos de 2–3 años); se empieza por la celda norte, la más antigua.
- **Drenaje:** pendientes de 3–5 % en la parte alta (la guía considera ideales 2–3 % y un máximo de 5–10 %) y canales que no crucen las chimeneas.
- **Biogás:** chimeneas en los pasillos, sensores de metano en el centro de transformación y en el coworking, y cables en bandeja o ducto superficial, sin zanjas profundas.
- **Pasto** rastrero nativo bajo las mesas, cortado con guadaña u ovejas. **Nunca cultivos de comida sobre las celdas.**

### 3.2 Producción

| | Valor | Tipo y fuente |
|---|---|---|
| Rendimiento de diseño | 1.346 kWh/kWp al año (3,69 por día), rango 1.300–1.450 | Dato oficial del proyecto: `data/microrred.json` (Global Solar Atlas × 0,84) |
| Comprobación con NASA POWER | 5,08 kWh/m² al día en el sitio (mínimo 4,56 en noviembre); con un rendimiento global de 0,78 da 1.446 kWh/kWp, así que el valor de diseño es prudente | Cálculo propio sobre NASA POWER (PVGIS estaba en mantenimiento) |
| **Producción anual** | **1.341.424 kWh** (1,30–1,45 GWh); unos 111.800 kWh al mes y 100.300 en noviembre | Cálculo propio |
| Promedio de 25 años | 1.260.938 kWh al año (degradación de 0,5 % anual) | Cálculo propio |
| Emisiones evitadas | 169 t de CO₂ al año | Cálculo propio con el factor del proyecto (0,126 kg/kWh, supuesto) |

**Energía propia del parque:** 80 módulos más (44 kWp: 40 en la cubierta del coworking y 40 en la marquesina del parqueadero) producen unos 59.200 kWh al año, más que la demanda estimada del parque (unos 39.600 kWh al año). Es una autogeneración aparte, de menos de 100 kW, con su propio medidor; la batería de 100 kWh respalda el internet y el coworking en los cortes. **El parque es autosostenible en energía en el balance anual** (estimación).

### 3.3 Conexión a la red de EPM

- **Subestación Yondó de EPM** (10 MVA, 34,5/13,2 kV, en operación desde 2021), en 7,0032 N, 73,9226 O (lugar de Google "Subestación yondo epm", con un patio pequeño de equipos y un edificio en el satélite; hay que confirmarla con EPM): **1,75 km en línea recta** y 4,6 km por vías públicas (cálculo propio).
- **Línea nueva de 13,2 kV de unos 2,6 km** (estimación, 2,3–2,9 km; unos $271 M con el precio rural de la base de la red, sección 7) o, si EPM confirma capacidad, una derivación de 0,6–0,8 km desde la red que alimenta la PTAP y el tanque elevado (a 350–590 m). OpenStreetMap no tiene las líneas eléctricas: el trazado lo define EPM.
- 1 MW es el 10 % de la capacidad de la subestación; la CREG 174 de 2021 limita la generación distribuida al 50 % del circuito o transformador. De 100 kW a 1 MW aplica el **estudio de conexión simplificado**.

## 4. El subsidio a los estratos 1 y 2

### 4.1 Cuántos hogares y cuánto cuesta hoy

| Dato | Valor | Tipo y fuente |
|---|---|---|
| Usuarios residenciales de EPM en Yondó (agosto de 2026) | **estrato 1: 6.327; estrato 2: 1.866**; estrato 3: 223; total residencial: 8.445. Además, 46 de estrato 1 con ESSA | Dato oficial, SUI, reporte "Consolidado Energía por Empresa, Departamento y Municipio" |
| Consumo promedio por usuario | estrato 1: 161 kWh/mes; estrato 2: 200 kWh/mes | Cálculo propio, seis meses del SUI (dic-2025 a ago-2026) |
| Consumo de subsistencia | 173 kWh/mes (municipios por debajo de 1.000 m) | Dato oficial, UPME, Resolución 355 de 2004 |
| Tarifa de EPM, octubre de 2026 | costo unitario 991,29 $/kWh; estrato 1: 427,04 (subsidio de 56,9 %); estrato 2: 533,81 (46,1 %) | Dato oficial, publicación de tarifas de EPM |
| Factura típica | estrato 1: **$68.722 al mes**; estrato 2: $119.252 | Cálculo propio |
| **Costo anual de los subsidios de estratos 1 y 2 en Yondó** | **$7.055 M** (rango $4.538–7.363 M) | Cálculo propio: usuarios × kWh subsidiados × (costo unitario − tarifa subsidiada); la cota baja es la diferencia entre el valor del consumo y lo facturado en el SUI |

**Marco legal.** La Ley 142 de 1994 (art. 99) creó los subsidios para el consumo de subsistencia. La Ley 1117 de 2006 (con el texto de la Ley 1428 de 2010) los topa en energía en **60 % para estrato 1 y 50 % para estrato 2** y limita el alza de la tarifa subsidiada al IPC. La **Ley 2294 de 2023, art. 272**, los prorroga hasta el **30 de junio de 2027** (Resolución CREG 105 006 de 2023).

### 4.2 Cuántos hogares cubre la granja

| Escenario | Hogares | Comentario |
|---|---|---|
| A. Todo el consumo de subsistencia (173 kWh/mes) | **646** | Cálculo propio |
| B. El consumo subsidiado real promedio (130 kWh/mes) | **860** | Cálculo propio |
| **C. Un bloque solar de 50 kWh/mes por hogar (recomendado)** | **2.236 (27 % de los hogares de estratos 1 y 2)** | Ahorro de **$21.352 al mes en estrato 1 (31 % de la factura)** y $26.690 en estrato 2 (22 %): dentro del 20–40 % que estima MinEnergía para Colombia Solar |

La granja produce el 10,2 % de la energía subsidiada de estratos 1 y 2 en Yondó.

La factura típica no incluye el cargo fijo de comercialización de hasta $9.611 por factura que trae la publicación de EPM. Con él, el ahorro del bloque de 50 kWh baja a cerca del 27 % de la factura en estrato 1 y del 21 % en estrato 2 (sigue dentro del rango de MinEnergía).

### 4.3 Cuánto se ahorra

| Si la energía... | Valor anual | Tipo |
|---|---|---|
| reemplaza consumo subsidiado: subsidios que la **Nación** deja de pagar | **$721 M** (537,8 $/kWh en promedio) | Cálculo propio |
| reemplaza consumo subsidiado: ahorro de los **hogares** | **$608 M** | Cálculo propio |
| se valora al costo unitario completo | $1.330 M | Cálculo propio |
| solo evita el componente de generación (si hay que pagar a EPM el uso de la red) | $541 M (403,50 $/kWh) | Cálculo propio |

El ahorro real queda entre $541 M y $1.330 M al año, según cómo reconozca la regulación la energía colectiva y quién pague el uso de la red.

**Costo de producir la energía:** con crédito al 6 % real a 25 años, 402 $/kWh (casi lo mismo que el componente de generación, 403,50 $/kWh); sin costo financiero (recursos no reembolsables), 228 $/kWh (cálculo propio). En los dos casos es menos de lo que cuesta el subsidio de un kWh de estrato 1 (564 $/kWh).

### 4.4 Con qué figura

1. **Comunidad energética** de hogares de estratos 1 y 2 de Yondó (Ley 2294 de 2023, art. 235; **Decreto 2236 de 2023**), inscrita en el Registro Único de Comunidades Energéticas (Resolución MinEnergía 40136 de 2024).
2. La comunidad actúa como **autogenerador colectivo** de hasta 1 MW: la granja es el punto de inyección y cada hogar recibe un porcentaje fijo de la energía (Resolución **CREG 101 072 de 2025**, arts. 6, 19 y 21). Todos deben estar en el mismo mercado y sistema de distribución de EPM y la potencia total debe ser menor de 5 MW (Resolución UPME 501 de 2024).
3. Se postula a **Colombia Solar** (Decreto 0972 de 2025 y Resolución MinEnergía 40159 de 2026) como **solución colectiva**: el programa sustituye subsidios por autogeneración, con contratos de hasta 25 años y prioridad por pobreza multidimensional, pobreza energética y radiación.
4. El municipio aporta el predio (comodato o derecho de superficie por 25 años).

**Por qué no basta una autogeneración común:** un autogenerador de más de 100 kW recibe el crédito de energía descontando los cargos de red (T + D + Cv + PR + R = 587,78 $/kWh). Para un hogar de estrato 1, que paga 427,04 $/kWh, ese crédito no sirve si no se combina con la sustitución de subsidios de Colombia Solar.

**Alternativas:** generación distribuida que vende la energía y alimenta un fondo energético social (requiere revisión jurídica: los subsidios municipales a la tarifa ya están cerca del tope legal), o un privado con contrato de compra de energía que paga un canon por el predio y destina una parte a los hogares.

## 5. El parque

### 5.1 La regla de oro

**Todo lo que tiene gente queda fuera de las celdas y a 30 m o más de los residuos y de las lagunas** (por el biogás y los asentamientos). Sobre las celdas solo van la granja solar, el pasto y las chimeneas. Las edificaciones llevan losa sobre membrana antigás, ventilación bajo el piso y sensor de metano. Las distancias de la tabla se midieron a las celdas, lagunas y humedal dibujados, no a la huella real de los residuos, que todavía no se conoce: por eso la zona de servicios entra en los apiques y en la línea base de biogás (sección 1.2). Los dos árboles que hoy crecen sobre la zona de la cobertura se retiran en la clausura, porque las raíces la dañan.

### 5.2 Programa

| Componente | Qué tiene | Distancia a residuos (cálculo propio) |
|---|---|---|
| **Coworking rural bioclimático y aula ambiental** (312 m²) | 40 puestos, sala de reuniones de 10, 4 cabinas, aula de 20, internet dedicado con respaldo satelital, 22 kWp en la cubierta y tanque de agua lluvia de 30 m³. Eje oriente–occidente, aleros de 1,5 m, corredor sur de 2,6 m, ventilación cruzada, ventiladores de techo y aire solo en la sala | 36,5 m |
| Cafetería, baños y duchas para ciclistas (96 m²) | 30 puestos en el corredor y la plazoleta | 47,6 m |
| Taller de bicicletas y biciparqueadero | 40 cupos, herramientas, aire, hidratación y 6 tomas para bicicletas eléctricas | 52,6 m |
| Parqueadero con marquesina solar | 16 carros, motos y un bus; 2 cargadores de 22 kW | 60,3 m |
| Plazoleta y 3 kioscos de trabajo al aire libre | mesas y tomas solares | 57–79 m |
| Módulo recreodeportivo (528 m²) | ejercitadores para adultos y adolescentes, juegos infantiles, mesas de ajedrez y escenario a nivel | 89 m |
| **Granja autosostenible** | invernadero y vivero de nativas (216 m²), huerta en 4 camas (784 m²), compostaje de poda y de la cafetería (no basura del pueblo), apiario de 10 colmenas a más de 25 m de los senderos | 98–109 m |
| Humedal de lixiviados con sendero de observación | aula ambiental al aire libre, con baranda | — |
| Mirador | terraza a 3 m con vista a la granja solar y al valle del Magdalena | 42 m |
| **Circuito de trote y ciclismo** | **0,90 km** por vuelta (más 0,19 km de enlace por la plazoleta), 3 m de ancho | perimetral |
| **Ruta pueblo–parque** | 3,9 km desde el parque principal; ida, una vuelta y regreso: unos 8,7 km. Con la Laguna del Miedo (3,1 km más por vía) sale un recorrido de unos 15 km | — |
| Portería, cerramiento y seguridad | portería en el acceso occidental, 1.100 m de malla y cerca viva, malla de 2 m con concertina en la granja solar, cámaras y alumbrado solar con sensor | — |
| Centro de transformación y control | 8 inversores de 100 kW, transformador de 1.000 kVA, batería de 100 kWh | 30 m |
| Señalización | 14 señales, 4 de ellas en la ruta al pueblo | — |

**Un coworking rural "no tan lejos del pueblo".** A 3,9 km del parque principal por una vía casi plana, el parque sirve a ciclistas y corredores que buscan un circuito seguro, a trabajadores remotos y nómadas digitales que necesitan internet estable y energía que no se va, y a colegios que quieren un aula ambiental con un relleno clausurado, un humedal y una granja solar de verdad.

### 5.3 Operación

- El municipio (o una asociación público-comunitaria) administra el parque; la cafetería y el taller se dan en concesión; la comunidad energética contrata un operador técnico para la granja solar; **Aguas y Aseo responde por la posclausura** con la provisión de clausura.
- Personal: administrador, 2 operarios, vigilancia 24 horas y servicios contratados de operación solar y monitoreo ambiental.
- Costos anuales (estimación): parque $520 M ($400–650 M), posclausura $190 M, mantenimiento solar $58,5 M. Ingresos posibles: coworking $60–150 M, concesiones $24–60 M, eventos y visitas $10–40 M.
- Usuarios esperados (estimación por confirmar con un piloto): 15–35 puestos de coworking al día, 150–400 visitantes por fin de semana y 200–600 ciclistas y corredores por semana.

### 5.4 Inspirado en los proyectos tipo del DNP

| Proyecto tipo del DNP | Qué se tomó |
|---|---|
| [Construcción y dotación de centro TIC municipal](https://proyectostipo.dnp.gov.co/index.php?option=com_k2&view=item&layout=item&id=145&Itemid=197) (v2.0, 2018) | Programa de 250 m² con acceso, internet, capacitación y baños; 24 equipos; costos de construcción ($430 M), dotación ($210 M), mantenimiento ($15 M/año) y operación ($9 M/mes) en pesos de 2018. El coworking lo escala a 312 m² y a $3,16 M/m² de 2026 |
| [Construcción y dotación parque recreodeportivo](https://proyectostipo.dnp.gov.co/index.php?option=com_k2&view=item&layout=item&id=132&Itemid=201) (v2.0, 2017) | Módulos de ejercitadores, juegos infantiles, mesas de ajedrez y escenario; $700 M por 2.040 m² (precios de 2016), unos $590.000/m² de 2026 |
| [Ciclo-infraestructura y servicios complementarios](https://proyectostipo.dnp.gov.co/index.php?option=com_k2&view=item&layout=item&id=144&Itemid=205) (v2.0, 2022) | Sección bidireccional de 2,6 m con bordillos; $2.110 M por 8 km de ciclo-infraestructura sobre vía (precios de 2022), unos $348 M/km de 2026; mantenimiento de $5,8 M/km al año |
| [Recuperación de cobertura vegetal en áreas disturbadas](https://proyectostipo.dnp.gov.co/index.php?option=com_k2&view=item&layout=item&id=263&Itemid=365) (v1.0, 2022) | Método de restauración con especies nativas para la cobertura, la cerca viva y el borde del caño |
| [Señalización turística urbana](https://proyectostipo.dnp.gov.co/index.php?option=com_k2&view=item&layout=item&id=269&Itemid=380) (2022) | Tipologías y costo por señal ($130,7 M por 18 señales) |
| [Estación de clasificación y aprovechamiento – ECA](https://proyectostipo.dnp.gov.co/index.php?option=com_k2&view=item&layout=item&id=259&Itemid=360) (v1.0, 2021) y Zonas Digitales | Proyectos complementarios: menos toneladas para el relleno regional y wifi público en el parque |

Los proyectos tipo ahorran hasta el 70 % de la preinversión y ya traen MGA. **No hay** proyecto tipo para granjas solares conectadas a la red ni para clausura de rellenos.

## 6. El modelo 3D

`data/edificios/relleno_parque.json` describe lo que hay hoy (celdas, lagunas, vías, cerca y caseta de la entrada norte) y lo que propone el proyecto (cobertura final, humedal, 21 filas de paneles, chimeneas, centro de transformación, coworking, cafetería, taller, portería, mirador, granja, módulo recreodeportivo, circuito y árboles nuevos). El generador lo convierte en un modelo con el conmutador **Hoy / Con el proyecto**:

```bash
cd scripts/modelos
node render_vista.mjs relleno_parque --orbita 200,38,330 --mira 20,0,-20 --fov 60 --out ../../data/geo/img/relleno_parque_orbita_todo.png --capa todo
node render_vista.mjs relleno_parque --orbita 200,38,330 --mira 20,0,-20 --fov 60 --out ../../data/geo/img/relleno_parque_orbita_hoy.png --capa existente
```

El trazado se comprobó sobre el satélite (`scripts/geo/gtrace.py`); las imágenes de Google y Esri son solo referencia y no se publican.

## 7. Presupuesto

Prefactibilidad (clase 4: −30 % / +50 %). Precios unitarios con AIU, de referencia para Antioquia en 2026. Detalle por ítem en `data/proyectos/parque_relleno/presupuesto.json`.

| Capítulo | Millones de 2026 |
|---|---:|
| 1. Estudios, diseños, plan de clausura y posclausura y trámites | 975,0 |
| 2. Clausura técnica de las celdas (reconformación, cobertura, canales, lixiviados, gases, monitoreo, humedal) | 2.549,5 |
| 3. Granja solar de 996,6 kWp (sistema a $2,7 M/kWp, lastres, transformador, caseta, malla, cámaras, batería) | 3.903,0 |
| 4. Conexión a EPM (línea de 2,6 km, reconectador, medición, salida en la subestación si se exige). La línea va a $104 M/km, el precio rural de la base de la red: ver la nota | 805,5 |
| 5. Parque: coworking, dotación, conectividad, solar propia, cargadores, agua lluvia, cafetería, taller, portería, mirador, kioscos | 2.589,6 |
| 6. Granja autosostenible | 269,4 |
| 7. Circuito, senderos, parqueadero, módulo recreodeportivo, señalización, alumbrado solar, cerramiento y ciclo-infraestructura al pueblo (3,8 km) | 2.703,8 |
| **Costo directo** | **13.795,8** |
| Interventoría (7 %) | 965,7 |
| Gestión social y ambiental (2 %) | 275,9 |
| Imprevistos (10 %) | 1.379,6 |
| **Total** | **16.416,9** (rango 11.492–24.625) |

| Fase | Millones de 2026 |
|---|---:|
| 0–1. Estudios y clausura | 4.194,2 |
| 2. Granja solar y conexión | 5.603,2 |
| 3. Parque | 6.619,6 |

**Precio de la línea a EPM, corregido.** `presupuesto.json` costeaba la línea de 2,6 km a $175 M/km: el km urbano de una versión anterior de la base de precios de la red (156,4 M/km) más gestión por km, redondeado. La base ya corregida (`data/red/precios_unitarios.json`) da **$152,9 M/km en zona urbana (APU-06U) y $86,7 M/km en zona rural (APU-06R)**. La línea va casi toda por zona rural: la subestación queda a unos 1,3 km del centro y la red cuenta como urbanos solo los km a menos de 1,1 km. Por eso le corresponde el precio rural más servidumbre ($10 M/km), poda ($3 M/km), topografía ($1,8 M/km) y RETIE ($2,5 M/km): **unos $104 M/km** (cálculo propio). La APU rural usa conductor ACSR 1/0 y no 2/0; para los 800 kW de la granja basta, porque son unos 35 A a 13,2 kV. Como control, la red de `docs/13` cobra su tramo rural al parque a unos $115 M/km, con fibra.

| Millones de 2026 | Antes ($175 M/km) | Ahora, con el precio rural ($104 M/km) |
|---|---:|---:|
| Línea de 2,6 km | 455,0 | 270,5 (239,3–301,7 para 2,3–2,9 km) |
| Capítulo 4 | 990,0 | 805,5 |
| Costo directo | 13.980,2 | 13.795,8 |
| Total con interventoría, gestión e imprevistos (19 %) | 16.636,5 | 16.416,9 |
| Fase 2: granja solar y conexión | 5.822,7 | 5.603,2 |

La diferencia es de $219,5 M (1,3 % del total). `presupuesto.json`, `financiacion.json`, este documento, `docs/00` y `docs/07` ya usan el precio rural. Si EPM confirma capacidad en la red que alimenta la PTAP, o si se construye la red de distribución de `docs/13` (que ya incluye el tramo tanque elevado → parque, 0,614 km y $81 M), la línea de 2,6 km no hace falta. No se deben pagar las dos.

**Ojo con la huella de los residuos.** La cobertura del capítulo 2 está calculada para unos 10.000–12.000 m². Si los apiques confirman la huella del Manual de Operaciones (1,85 ha), la clausura técnica pasa de $2.550 M a unos $3.860 M; si llega a unas 4 ha, a unos $7.180 M (cálculo propio). Eso supera el margen de prefactibilidad, por eso la delimitación de residuos va primero.

**Para comparar:** ampliar el relleno (BPIN 2025058930015) costaba unos $3.901 M de 2026 y seguir operándolo, unos $576 M al año. La clausura cuesta del mismo orden que la ampliación, pero resuelve el problema para siempre y libera el predio.

## 8. Cómo se paga

| Fase | Fuentes | Mezcla sugerida (millones) |
|---|---|---|
| 0–1. Clausura ($4.194 M) | Provisión de clausura y tarifa de aseo (Decreto 1784, art. 2.3.2.3.17); SGP de agua potable y saneamiento y Plan Departamental de Agua; regalías (reformular el BPIN de la ampliación como clausura con uso futuro) | tarifa 600; SGP y PDA 1.200; SGR 2.394 |
| 2. Granja solar ($5.603 M) | Colombia Solar o FENOGE (ConEnergía para municipios PDET); SGR, Incentivo a la Producción (hasta $8.000 M y dos proyectos por municipio; en 2025 el único proyecto de Yondó no cumplió); Findeter "Municipios Territorios Energéticos" (IBR + 0,7 %, granjas de 1 MW); obras por impuestos (Yondó es ZOMAC y PDET); o un privado con contrato de compra de energía | Colombia Solar o FENOGE 2.911; SGR 1.747; Findeter o privado 945 |
| 3. Parque ($6.620 M) | Regalías (y el BPIN 2025058930008 de la vía de acceso como ruta ciclista); MinTIC (Zonas Digitales); Ministerio del Deporte e INDER (proyectos tipo de parque y ciclo-infraestructura); Ecopetrol (inversión social, comunidades energéticas); cooperación internacional; recursos propios | SGR 3.310; deporte, TIC y cultura 1.324; Ecopetrol y cooperación 993; propios 993 |

**Compuertas:** no se licita la granja solar sin delimitar los residuos y sin el concepto de Corantioquia sobre el uso futuro; no se construye nada con gente sin la línea base de biogás; no se cierra el relleno sin el contrato de disposición regional y un plan de contingencia por el puente; cada fuente se radica con su MGA.

## 9. Hoja de ruta

| Fase | Años | Qué |
|---|---|---|
| 0 | 2027 | Topografía, apiques, georradar y línea base ambiental; contrato con el relleno regional; plan de clausura ante Corantioquia; MGA y postulaciones |
| 1 | 2027–2028 | Traslado de la basura a San Silvestre; clausura técnica |
| 2 | 2029–2030 | Granja solar, bloque A (unos 0,77 MWp), y conexión a EPM; constitución de la comunidad energética; bloque B si los apiques lo permiten |
| 3 | 2028–2030 | Coworking, cafetería, taller, granja, circuito, mirador y ruta ciclista (pueden empezar en paralelo con la clausura porque están fuera de las celdas, cuando los apiques y la línea base de biogás descarten residuos bajo la zona de servicios) |
| Posclausura | 2028–2048 | Monitoreo y mantenimiento por 20 años como mínimo |

## 10. Lo que todavía no sabemos

- La ubicación del relleno se dedujo de documentos y del satélite (confianza media): no hay foto georreferenciada.
- La huella real de los residuos (0,8–4 ha, o hasta 6,6 ha si la mancha parda del sur de 2020 tiene residuos) define cuántos kWp quedan sobre las celdas y dónde pueden ir los servicios; el bloque B depende de los apiques.
- Las cuatro piscinas se interpretan como lagunas de lixiviados; podrían ser de aguas lluvias.
- El botadero antiguo de los años noventa no está delimitado; está cerca de los pozos del acueducto según la nota de 2020.
- El predio del municipio puede no incluir todo el potrero del sur donde van los servicios: hay que revisar el certificado de tradición y el catastro.
- Las tarifas de disposición regional, la ruta y el costo de la línea de 13,2 kV y la capacidad de la red los definen el operador del relleno y EPM. La ubicación de la subestación sale de un lugar de Google y del satélite; EPM no la ha publicado.
- Las reglas de Colombia Solar para soluciones colectivas están en reglamentación y los subsidios de la Ley 1117 están prorrogados solo hasta el 30 de junio de 2027.
- Los consumos por estrato salen de seis meses del SUI; los meses varían por los ciclos de facturación.

## Fuentes

**Relleno y servicio de aseo**
- Superservicios, evaluación integral de Aguas y Aseo de Yondó, vigencia 2017 (visita del 17 y 18 de mayo de 2018), págs. 51–52 (PGIRS) y 68–74 (disposición final): https://www.superservicios.gov.co/sites/default/files/inline-files/ei_yondo_ok1.pdf
- Superservicios, evaluación integral 2020 (vigencia 2019), sin componente técnico de aseo: https://www.superservicios.gov.co/sites/default/files/inline-files/evaluacion_integral_aguas_aseo_yondo_s.a._e.s.p.pdf
- SUI en datos.gov.co (consulta del 22-oct-2026): registro de sitios https://www.datos.gov.co/resource/84tn-nnhf.json; autorización ambiental https://www.datos.gov.co/resource/wu2p-623h.json; registro R48765 https://www.datos.gov.co/resource/6nqe-quhx.json; toneladas https://www.datos.gov.co/resource/urvy-i3ii.json; activos 2020 https://www.datos.gov.co/resource/6ga6-iyr7.json
- MinVivienda, sitios de disposición final por municipio (2020): https://www.minvivienda.gov.co/sites/default/files/2020-09/disposicion-final.pdf
- SECOP I y II (contratos del relleno 2008–2026), copia local en `data/secop/raw/`; ejemplos: https://www.contratos.gov.co/consultas/detalleProceso.do?numConstancia=14-4-3110226 y https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.10321878
- Regalías: BPIN 2025058930015 y 2025058930008 (`data/comparativa/sgr_fondos.json`, de MapaInversiones)
- Noticias Caracol, "Denuncian construcción de pozos de agua para consumo humano en antiguo relleno sanitario" (23-sep-2020): https://www.noticiascaracol.com/antioquia/denuncian-construccion-de-pozos-de-agua-para-consumo-humano-en-antiguo-relleno-sanitario
- Vanguardia, riesgo del puente Barrancabermeja–Yondó (4-jun-2026): https://www.vanguardia.com/santander/barrancabermeja/2026/06/04/por-que-sigue-en-riesgo-el-puente-que-conecta-a-barrancabermeja-con-yondo-ruta-del-cacao-explico-las-causas/
- Global Witness, "Cicatrices de por vida" (San Silvestre): https://globalwitness.org/es/campaigns/land-and-environmental-defenders/colombia-report-es/

**Normas**
- Decreto 1784 de 2017: https://normas.cra.gov.co/gestor/docs/decreto_1784_2017.htm
- Resolución MVCT 938 de 2019 (Diario Oficial 51.185): https://normas.cra.gov.co/gestor/docs/resolucion_minviviendact_0938_2019.htm
- Resolución 0330 de 2017 con las modificaciones de la 0799 de 2021: https://normas.cra.gov.co/gestor/docs/resolucion_minviviendact_0330_2017.htm
- Resolución CREG 174 de 2021: https://gestornormativo.creg.gov.co/gestor/entorno/docs/resolucion_creg_0174_2021.htm
- Resolución CREG 101 072 de 2025 (comunidades energéticas): https://gestornormativo.creg.gov.co/gestor/entorno/docs/originales/Resoluci%C3%B3n_CREG_101_072_2025/Resoluci%C3%B3n_CREG_101_072_2025.pdf
- Resolución CREG 105 006 de 2023 (prórroga de subsidios, Ley 2294 de 2023, art. 272): https://gestornormativo.creg.gov.co/gestor/entorno/docs/resolucion_creg_105-6_2023.htm
- Colombia Solar: MinEnergía (10-sep-2025) https://www.minenergia.gov.co/es/sala-de-prensa/noticias-index/con-colombia-solar-subsidios-convierten-paneles-reducen-tarifa-energia-hogares-mas-pobres/ ; reglamentación (29-ene-2026) https://www.minenergia.gov.co/es/sala-de-prensa/noticias-index/gobierno-nacional-reglamenta-colombia-solar-y-convierte-el-subsidio-electrico-en-autogeneracion-para-estratos-1-2-y-3/ ; pv magazine (19-mar-2026) https://www.pv-magazine-latam.com/2026/03/19/reglamentan-el-programa-colombia-solar-para-sustituir-subsidios-electricos-por-autogeneracion-en-hogares-vulnerables/
- Decreto 2236 de 2023 y demás normas de comunidades energéticas: ver `docs/anexos/D-energia-mintic.md`, sección 4.3

**Energía**
- SUI, reporte "Consolidado Energía por Empresa, Departamento y Municipio" (ele_com_096), Yondó, 2024–2026: http://reportes.sui.gov.co/fabricaReportes/frameSet.jsp?idreporte=ele_com_096
- EPM, tarifas de octubre de 2026 (Antioquia): https://www.epm.com.co/content/dam/epm/clientes-y-usuarios/energia/tarifas-energia/Tarifas%202026/10.PublicacionTarifasOctubre162026_ANT_OM.pdf
- Base de precios de red del proyecto (unidades constructivas de la Res. CREG 015 de 2018 y APU propios): `data/red/precios_unitarios.json`, ítems APU-06U, APU-06R, GES-SERV, GES-PODA, GES-TOPO, GES-RETIE-KM y CREG-N2EQ35; presupuesto de la red propuesta en `data/red/presupuesto_red.json`
- Google Maps, lugar "Subestación yondo epm" (7,0031989, −73,9226337), consulta del 22-oct-2026
- NASA POWER, climatología en el sitio: https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=ALLSKY_SFC_SW_DWN&community=RE&longitude=-73.934&latitude=7.014&format=JSON
- EPA y NREL, Best Practices for Siting Solar Photovoltaics on MSW Landfills (mayo de 2022), secciones 4.2.2 y 5: https://www.epa.gov/system/files/documents/2022-05/best-practices-siting-solar-photovoltaics-municipal-solid-waste-landfills_051722-pub.pdf
- Findeter–MinEnergía, línea "Municipios Territorios Energéticos": https://www.findeter.gov.co/noticias/comunicados/ministerio-de-minas-y-energia-y-findeter-en-alianza-con-asocapitales-asointermedias-y-fedemunicipios-lanzan-linea-de-financiamiento-para-parques-de-generacion-de-energia

**Proyectos tipo del DNP** (consulta del 22-oct-2026): https://proyectostipo.dnp.gov.co — Centro TIC municipal (`/images/pdf/centrotic/ptcentrotic.pdf`, págs. 16–18), Parque recreodeportivo (`/images/pdf/parque/PTparquerecreodeportivo.pdf`, págs. 18–19), Ciclo-infraestructura (`/images/pdf/cicloinfraestructura/PT_GuiaFormulacion_ciclo-infraestructura_y_servicios_complementarios.pdf`, sección 4.1), Recuperación de cobertura vegetal (`/images/pdf/Coberturavegetal/PT-RECUPERACION-13062022_1.pdf`), Señalización turística (`/images/pdf/senalizacionturistica/PT_Infraestructura_para_Senalizacion_Turistica.pdf`) y ECA (`/images/pdf/Residuos-solidos-ECA/GUIA-DE-FORMULACION-PT-ECAS-13012022-VF2.pdf`).

**Mapas y distancias:** © colaboradores de OpenStreetMap (ODbL); OSRM (https://router.project-osrm.org); elevaciones de https://api.opentopodata.org (SRTM, ASTER y Mapzen). Las imágenes de Google y Esri se usaron solo como referencia de levantamiento y no se publican.
