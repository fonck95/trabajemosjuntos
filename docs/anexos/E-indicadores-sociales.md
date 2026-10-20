# Yondó (Antioquia, DANE 05893): evolución de indicadores sociales y territoriales 2004-2026

> **Anexo de investigación.** Informe de trabajo con cada dato y su fuente. Marcas de certeza: verificado, derivado o calculado, inferencia y por verificar. Donde dice que "se agotó el cupo de búsquedas", el punto quedó abierto y está listado en la sección final de pendientes.


Ficha de investigación (componente E, social y territorial) para un marco comparativo por periodos de gobierno municipal: 2004-2007, 2008-2011, 2012-2015, 2016-2019, 2020-2023 y 2024-2027. Fecha de consulta: 20 de octubre de 2026.

**Cómo leer este documento**
- Las cifras provienen de descargas directas de TerriData-DNP (archivo plano municipal, actualizado el 7-ago-2026), de datos.gov.co (Socrata: MinTIC, INS, MinDefensa, INMLCF, UARIV, ANH, MEN, FNG, ICA y Gobernación de Antioquia), de archivos del DANE, de la Superservicios y de prensa regional. Los archivos crudos están en `research/raw/`.
- "No encontrado" significa que no hallé la cifra en fuentes verificables. No hay valores estimados ni inventados. Los cálculos propios (sumas, promedios por periodo, bpd) se señalan como tales.
- Formato decimal colombiano (coma decimal, punto de miles). "s.d." = sin dato.
- Limitación: se agotó el cupo de búsquedas web de la sesión. Algunos temas cualitativos, como la lista completa de alertas tempranas de la Defensoría o el estado del puente después de junio de 2026, quedaron con verificación parcial.

## 0. Resumen comparativo por periodo de gobierno

Cálculo propio con las series de `E-series.json`. Promedio = media simple de los años con dato dentro del periodo. *2024-2027 es parcial: datos hasta 2024, 2025 o 2026 según la serie (homicidios 2026 = enero-agosto; víctimas y desplazamiento 2026 = corte 30-sep-2026). La población 2027 es proyección DANE.

| Indicador | 2004-2007 | 2008-2011 | 2012-2015 | 2016-2019 | 2020-2023 | 2024-2027* |
|---|---|---|---|---|---|---|
| Población total DANE base CNPV 2018 (inicio → fin) | 14.154 → 15.116 | 15.496 → 16.508 | 16.870 → 17.813 | 18.204 → 19.531 | 20.037 → 21.255 | 21.677 → 22.789 |
| % población rural (inicio → fin) | 53,53 → 52,26 | 52,01 → 51,05 | 50,72 → 50,12 | 49,76 → 49,01 | 48,76 → 47,63 | 47,82 → 46,77 |
| Homicidios (suma, MinDefensa) | 42 | 43 | 47 | 19 | 63 | 72 |
| Tasa homicidio intencional Yondó (promedio) | 72,08 | 67,47 | 67,4 | 25,23 | 75,97 | 134,4 |
| Tasa homicidio intencional Antioquia (promedio) | 39,45 | 46,23 | 38,9 | 33,6 | 28,88 | 24,6 |
| Víctimas RUV por ocurrencia (suma personas-año) | 5.376 | 2.138 | 663 | 440 | 612 | 1.014 |
| Desplazamiento - expulsión (suma personas) | 5.119 | 2.028 | 608 | 403 | 484 | 866 |
| Eventos minas antipersonal (suma) | 8 | 15 | 11 | 4 | 0 | 2 |
| Coca ha (promedio) | 54,5 | 115,25 | 3,52 | 6,44 | 14,09 | s.d. |
| IRCA total (promedio) | 0 | 22,25 | 5,8 | 1,7 | 6,83 | 0,8 |
| IRCA rural (promedio años con dato) | s.d. | 66,9 | s.d. | s.d. | 75,58 | s.d. |
| Cobertura neta educación total (promedio) | 77,03 | 86,83 | 92,16 | 83,42 | 84,09 | 84,96 |
| Cobertura neta media (promedio) | 14,03 | 20,32 | 21,53 | 25,51 | 29,73 | 31,44 |
| Deserción intra-anual sector oficial (promedio) | s.d. | 5,9 | 5,12 | 7,22 | 4,07 | 3,07 |
| Saber 11 Matemáticas Yondó (promedio) | s.d. | 43,56 | 43,84 | 47,59 | 47,63 | s.d. |
| Saber 11 Matemáticas Colombia (promedio) | s.d. | 48,2 | 47,77 | 50,26 | 50,44 | s.d. |
| Tránsito inmediato a ed. superior (promedio) | s.d. | s.d. | 23,93 | 33,72 | 43,28 | 53,69 |
| Mortalidad infantil <1 año x1.000 NV (promedio) | 23,91 | 21,95 | 19,07 | 16,38 | 12,16 | 9,52 |
| Casos malaria SIVIGILA (suma) | 1 | 251 | 194 | 210 | 28 | s.d. |
| Afiliados SGSSS (último año) | s.d. | s.d. | 11.502 (2015) | 11.218 (2019) | 10.638 (2023) | 10.179 (2025) |
| Penetración internet fijo x100 hab. (último año) | s.d. | 1,67 (2011) | 3,77 (2015) | 5,45 (2019) | 5,06 (2023) | 3,56 (2025) |
| Producción crudo bpd (promedio) | s.d. | s.d. | 21.953,5 | 15.200 | 12.654,5 | 11.123 |
| Valor agregado municipal, miles de millones COP corrientes (promedio) | s.d. | 974,07 | 1.135,23 | 846,19 | 1.102,95 | s.d. |
| % actividades primarias en VA (promedio) | s.d. | 91,69 | 89,75 | 81,23 | 78,99 | s.d. |
| Inventario bovino (último año) | 87.185 (2007) | 93.287 (2011) | 99.047 (2015) | 120.960 (2019) | 136.146 (2023) | 126.743 (2025) |
| Bosque estable ha, IDEAM (último año con dato) | 50.001,67 (2005) | 42.946,19 (2010) | 40.644,8 (2015) | 36.397,97 (2018) | s.d. | s.d. |
| Tasa personas afectadas por desastres x100.000 (promedio) | 11.159,99 | 5.176,19 | 0 | 1.312,89 | 760,7 | s.d. |
| Cobertura energía rural ICEE (promedio) | s.d. | 84,16 | 81,65 | 88,17 | 98,67 | 95,55 |
| MDM - Medición de Desempeño Municipal (promedio) | s.d. | s.d. | s.d. | 51,62 | 59,03 | 64,03 |

**Lectura rápida**
- **Pobreza:** cayó con fuerza entre censos (NBI de 59,1% a 26,0%; miseria de 30,1% a 6,4%; IPM censal de 79,2% a 46,3%). Aun así, Yondó sigue con más del doble de la pobreza de Antioquia (NBI 10,7%; IPM 21,6%).
- **Violencia:** sigue un ciclo. Los picos ocurrieron en 2004 (106 por 100.000 hab.), 2009 y 2015 (106,7). El valle fue 2016-2019, con un mínimo de 15,4 en 2019. Desde 2020 la violencia repunta y 2025 es el año récord: 41 homicidios y una tasa de 185,8 por 100.000 hab., 7,5 veces la de Antioquia. Las víctimas y el desplazamiento siguen el mismo patrón, con un resurgimiento entre 2022 y 2026.
- **Agua:** el agua urbana es "sin riesgo" (IRCA urbano ≤5) en todos los años reportados desde 2015. El agua rural, cuando se mide, es "inviable sanitariamente" (IRCA rural de 82,6 a 97,4 entre 2021 y 2023). No hay planta de tratamiento de aguas residuales (PTAR).
- **Educación:** la cobertura neta en media subió de 13,8% (2005) a 31-36% (2023-2024), aunque sigue muy baja. Saber 11 sigue 1 a 6 puntos por debajo de Antioquia y Colombia. El tránsito inmediato a la educación superior pasó de 27% (2014) a 54% (2024).
- **Economía:** depende del petróleo (actividades primarias = 76-92% del valor agregado). La producción fiscalizada cayó de unos 22.000 bpd (2014) a unos 10.600 bpd (2025). En 2026 se anunció la entrada de Parex como socio de Ecopetrol en Casabe. La ganadería bovina y bufalina se expandió.
- **Conectividad:** la penetración de internet fijo es muy baja y retrocede: 7,64 accesos por 100 hab. en 2021 y 3,56 en 2025, frente a 26,1 en Antioquia y 19,3 en Colombia.

## 1. Población y división territorial

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| Población total, retroproyección y proyección DANE base CNPV 2018 | personas | 2004: 14.154; 2005: 14.459; 2006: 14.810; 2007: 15.116; 2008: 15.496; 2009: 15.869; 2010: 16.158; 2011: 16.508; 2012: 16.870; 2013: 17.180; 2014: 17.496; 2015: 17.813; 2016: 18.204; 2017: 18.610; 2018: 19.043; 2019: 19.531; 2020: 20.037; 2021: 20.471; 2022: 20.861; 2023: 21.255; 2024: 21.677; 2025: 22.061; 2026: 22.429; 2027: 22.789 *Nota: Retroproyecciones 2004-2017 y proyecciones 2018-2027 conciliadas con CNPV 2018 (valores a 30 de junio).* | https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion (DCD-area-proypoblacion-Mun-1995-2004.xlsx; DCD-area-proypoblacion-Mun-2005-2017_VP.xlsx; PPED-AreaMun-2018-2042_VP.xlsx) |
| Población cabecera, base CNPV 2018 | personas | 2004: 6.578; 2005: 6.767; 2006: 7.005; 2007: 7.217; 2008: 7.437; 2009: 7.655; 2010: 7.863; 2011: 8.081; 2012: 8.314; 2013: 8.483; 2014: 8.668; 2015: 8.886; 2016: 9.145; 2017: 9.350; 2018: 9.641; 2019: 9.958; 2020: 10.267; 2021: 10.567; 2022: 10.854; 2023: 11.131; 2024: 11.310; 2025: 11.587; 2026: 11.856; 2027: 12.130 | https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion |
| Población centros poblados y rural disperso, base CNPV 2018 | personas | 2004: 7.576; 2005: 7.692; 2006: 7.805; 2007: 7.899; 2008: 8.059; 2009: 8.214; 2010: 8.295; 2011: 8.427; 2012: 8.556; 2013: 8.697; 2014: 8.828; 2015: 8.927; 2016: 9.059; 2017: 9.260; 2018: 9.402; 2019: 9.573; 2020: 9.770; 2021: 9.904; 2022: 10.007; 2023: 10.124; 2024: 10.367; 2025: 10.474; 2026: 10.573; 2027: 10.659 | https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion |
| % población rural, base CNPV 2018 (cálculo propio) | % | 2004: 53,53; 2005: 53,2; 2006: 52,7; 2007: 52,26; 2008: 52,01; 2009: 51,76; 2010: 51,34; 2011: 51,05; 2012: 50,72; 2013: 50,62; 2014: 50,46; 2015: 50,12; 2016: 49,76; 2017: 49,76; 2018: 49,37; 2019: 49,01; 2020: 48,76; 2021: 48,38; 2022: 47,97; 2023: 47,63; 2024: 47,82; 2025: 47,48; 2026: 47,14; 2027: 46,77 | https://www.dane.gov.co/index.php/estadisticas-por-tema/demografia-y-poblacion/proyecciones-de-poblacion |
| Población total, serie antigua base Censo 2005 | personas | 2005: 15.097; 2006: 15.419; 2007: 15.756; 2008: 16.100; 2009: 16.442; 2010: 16.788; 2011: 17.153; 2012: 17.503; 2013: 17.867; 2014: 18.239; 2015: 18.613; 2016: 18.992; 2017: 19.365; 2018: 19.757; 2019: 20.136; 2020: 20.524 *Nota: Serie antigua base Censo 2005 conciliado (2005 = población censal conciliada). Reemplazada por la base CNPV 2018.* | https://www.dane.gov.co/files/investigaciones/poblacion/proyepobla06_20/ProyeccionMunicipios2005_2020.xls |
| Población cabecera, base Censo 2005 | personas | 2005: 7.180; 2006: 7.401; 2007: 7.622; 2008: 7.843; 2009: 8.064; 2010: 8.285; 2011: 8.506; 2012: 8.727; 2013: 8.949; 2014: 9.170; 2015: 9.391; 2016: 9.612; 2017: 9.834; 2018: 10.055; 2019: 10.277; 2020: 10.498 | https://www.dane.gov.co/files/investigaciones/poblacion/proyepobla06_20/ProyeccionMunicipios2005_2020.xls |
| Población resto, base Censo 2005 | personas | 2005: 7.917; 2006: 8.018; 2007: 8.134; 2008: 8.257; 2009: 8.378; 2010: 8.503; 2011: 8.647; 2012: 8.776; 2013: 8.918; 2014: 9.069; 2015: 9.222; 2016: 9.380; 2017: 9.531; 2018: 9.702; 2019: 9.859; 2020: 10.026 | https://www.dane.gov.co/files/investigaciones/poblacion/proyepobla06_20/ProyeccionMunicipios2005_2020.xls |
| CNPV 2018: personas efectivamente censadas | personas | 2018: 17.597 *Nota: Personas efectivamente censadas: cabecera 9.515; centros poblados 2.601; rural disperso 5.481. La población ajustada por cobertura (proyección) es 19.043.* | https://www.dane.gov.co/files/censo2018/informacion-tecnica/PERSONAS_DEMOGRAFICO_Cuadros_CNPV_2018.xlsx (hoja 1PM) |

| Indicador | Año | Valor | Fuente (URL) |
|---|---|---|---|
| Censo 2005: población conciliada (total / cabecera / resto) | 2005 | 15.097 / 7.180 / 7.917 | https://www.dane.gov.co/files/investigaciones/poblacion/proyepobla06_20/ProyeccionMunicipios2005_2020.xls |
| Censo 2005: cabecera sin ajuste por cobertura (citypopulation, a partir del DANE) | 2005 | 7.162 | https://citypopulation.de/en/colombia/antioquia/yondó/05893000__yondó/ |
| CNPV 2018: personas censadas (total / cabecera / centros poblados / rural disperso) | 2018 | 17.597 / 9.515 / 2.601 / 5.481 | https://www.dane.gov.co/files/censo2018/informacion-tecnica/PERSONAS_DEMOGRAFICO_Cuadros_CNPV_2018.xlsx (hoja 1PM) |
| CNPV 2018: población ajustada (total / cabecera / resto) | 2018 | 19.043 / 9.641 / 9.402 | https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/PPED-AreaMun-2018-2042_VP.xlsx |
| Variación intercensal 2005-2018 | 2018 | 26,12% | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 |
| Proyección DANE 2026 (total / cabecera / resto) | 2026 | 22.429 / 11.856 / 10.573 | PPED-AreaMun-2018-2042_VP.xlsx |
| Población SISBEN certificada (total / cabecera / centro poblado / rural disperso) | oct-2012 | 15.073 / 8.024 / 1.450 / 5.599 | https://www.antioquia.gov.co/images/pdf/anuario_2012/data/poblacion/PO341.html (Anuario Estadístico de Antioquia 2012, cuadro 3.4.1) |
| Extensión | 2024 | 1.895,20 km² (IGAC) | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 |
| Densidad | 2026 | 11,83 hab/km² | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 |
| Categoría de ruralidad DNP | — | Rural disperso | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 |
| Categoría Ley 617 | 2018-2024 | 6 (2018-2020, 2022); 5 (2021, 2023, 2024) | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 |
| Municipio PDET (subregión Sur de Bolívar): iniciativas PDET con ruta activada / sin ruta | 2023-2025 | 86 / 53 | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 |

**División territorial (nombres verificados)**
- **Cabecera:** el nombre oficial en la DIVIPOLA es "Yondó" (código 05893000). Se la conoce popularmente como Casabe.
- **Corregimiento:** uno solo, **San Miguel del Tigre**. El Anuario Estadístico de Antioquia 2014 registra **60 veredas**: 46 adscritas a la cabecera y 14 al corregimiento ([fuente](https://www.antioquia.gov.co/images/pdf/anuario2014/es-CO/capitulos/generalidades/aspectos/divisiones/cp-1-1-3-2/medio/yondo.html)).
  - Veredas del corregimiento San Miguel del Tigre: Bellavista, Campo Cimitarra, Cuatro Bocas, El Cedro, El Descanso, El Totumo, La Cabaña, La Felicidad, La Rinconada, La Rompida No.1, La Rompida No.2, Las Lomas, Puerto Nuevo No. 2 y San Miguel del Tigre.
  - Veredas de la zona de la cabecera: San Francisco Alto, Barbacoas, Bocas de Barbacoas, Bocas de San Francisco, Caño Blanco, Caño Bodegas, Caño Bonito, Caño Don Juan, Caño Huila, Caño Las Cruces, Caño Negro, Ciénaga de Sardinata Alta, Ciénaga Chiquita, El Amparo de San Martín, El Bagre, El Dique, El Paraíso, El Porvenir, El Terminal, El Vietman, Jabonal, Kilómetro Cinco, La Cascajera, La Concepción, La Cóndor, La Congoja, La Ganadera, La Orquídea, La Paz, La Raya, La Represa, La Soledad, La Unión, Laguna del Miedo, Las Américas, No Te Pases, Patio Bonito, Puerto Casabe, Remolinos Peñas Blancas, Rompederos, San Bartolo, San Juan del Ite, San Luis Beltrán, Santa Clara, Sardinata Baja y Yondó Nuevo.
- **Centros poblados DIVIPOLA (DANE):** Ciénaga de Barbacoa-La Punta (001), San Luis Beltrán (002), San Miguel del Tigre (003), Bocas de San Francisco (005), **El Bagre (008)**, Bocas de Barbacoas (009), Puerto Los Mangos (014), Puerto Matilde (015), **Puerto Tomás (017)**, Puerto Casabe (018), La Cóndor (019) y Chorro de Lágrimas (021) ([datos.gov.co xaxy-8nri](https://www.datos.gov.co/resource/xaxy-8nri.json?codigo_municipio=05893)). Quedan **verificados** El Bagre y Puerto Tomás. San Miguel del Tigre es a la vez corregimiento y centro poblado.
- No se hallaron proyecciones DANE de población por corregimiento o vereda: **No encontrado**.

## 2. Pobreza: NBI, miseria e IPM

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| NBI total | % personas | 2005: 59,05; 2018: 26,01 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2005 / CNPV 2018) |
| NBI cabecera | % personas | 2005: 44,95; 2018: 19,54 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2005 / CNPV 2018) |
| NBI centros poblados y rural disperso | % personas | 2005: 75,18; 2018: 33,67 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2005 / CNPV 2018) |
| Miseria total (2 o más NBI) | % personas | 2005: 30,08; 2018: 6,42 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2005 / CNPV 2018) |
| Miseria cabecera | % personas | 2005: 18,99; 2018: 3,54 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2005 / CNPV 2018) |
| Miseria rural | % personas | 2005: 42,76; 2018: 9,83 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2005 / CNPV 2018) |
| IPM censal total | % personas | 2005: 79,18; 2018: 46,3 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2005 / CNPV 2018) |
| IPM censal cabecera | % personas | 2005: 69,7; 2018: 40,9 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2005 / CNPV 2018) |
| IPM censal rural | % personas | 2005: 90,02; 2018: 52,7 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2005 / CNPV 2018) |
| NBI Antioquia | % personas | 2005: 22,96; 2018: 10,73 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip |
| IPM censal Antioquia | % personas | 2005: 44,29; 2018: 21,55 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip |
| Miseria Antioquia | % personas | 2005: 8,15; 2018: 2,5 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip |
| NBI Colombia | % personas | 2005: 27,78; 2018: 14,28 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip |
| IPM censal Colombia | % personas | 2005: 48,97; 2018: 25,62 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip |
| Miseria Colombia | % personas | 2005: 10,64; 2018: 3,8 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip |

Componentes del NBI 2005 → 2018 (TerriData, DANE): vivienda inadecuada 36,25 → 17,60; servicios inadecuados 22,39 → 3,88; hacinamiento crítico 17,81 → 2,09; inasistencia escolar 6,41 → 2,80; dependencia económica 21,74 → 7,56. IPM 2018 con jefatura femenina: 47,65%. Brecha del IPM frente al total nacional (municipio PDET): 15,88 puntos porcentuales. Fuente: https://terridata.dnp.gov.co/index-app.html#/perfiles/05893.

*El IPM 2005 es una medición censal retrospectiva publicada por DANE/DNP y no es estrictamente comparable con la encuesta ECV. No existe IPM municipal anual: **No encontrado** para años intercensales.*

## 3. Agua potable y saneamiento básico

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| Cobertura acueducto (censo) total | % viviendas/hogares | 2005: 47,68; 2018: 73,75 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE censos) |
| Cobertura acueducto (censo) urbana | % viviendas/hogares | 2005: 88,32; 2018: 91,55 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE censos) |
| Cobertura acueducto (censo) rural | % viviendas/hogares | 2005: 10,2; 2018: 52,09 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE censos) |
| Cobertura alcantarillado (censo) total | % viviendas/hogares | 2005: 41,97; 2018: 59,06 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE censos) |
| Cobertura alcantarillado (censo) urbana | % viviendas/hogares | 2005: 79,18; 2018: 89,45 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE censos) |
| Cobertura alcantarillado (censo) rural | % viviendas/hogares | 2005: 7,67; 2018: 22,05 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE censos) |
| Cobertura aseo (censo) total | % viviendas/hogares | 2005: 46,54; 2018: 72,42 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE censos) |
| Cobertura acueducto REC-SSPD total | % | 2008: 33,7; 2009: 34,88; 2010: 48,51; 2011: 36,36; 2012: 91,47; 2013: 15,85; 2014: 15,85; 2015: 15,85; 2016: 46,98; 2017: 46,98; 2018: 46,68; 2019: 60,19; 2020: 59,45; 2021: 0; 2022: 61,27; 2023: 61,27; 2024: 61,27 *Nota: Serie administrativa reportada por el municipio a SSPD; tiene saltos inverosímiles (p. ej. 2012=91,47; 2013-2015=15,85; 2021=0) que indican errores de reporte. Usar con cautela.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (SSPD - Reporte de Estratificación y Coberturas, REC) |
| Cobertura acueducto REC urbana | % | 2008: 0; 2009: 0; 2010: 99,02; 2011: 97,1; 2012: 100; 2013: 70,33; 2014: 70,33; 2015: 70,33; 2016: 100; 2017: 100; 2018: 100; 2019: 100; 2020: 100; 2021: 0; 2022: 100; 2023: 100; 2024: 100 *Nota: Serie administrativa reportada por el municipio a SSPD; tiene saltos inverosímiles (p. ej. 2012=91,47; 2013-2015=15,85; 2021=0) que indican errores de reporte. Usar con cautela.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (SSPD - Reporte de Estratificación y Coberturas, REC) |
| Cobertura acueducto REC rural | % | 2008: 33,7; 2009: 34,88; 2010: 24,42; 2011: 20,89; 2012: 0; 2013: 0; 2014: 0; 2015: 0; 2016: 5,61; 2017: 5,61; 2018: 5,55; 2019: 29,84; 2020: 29,21; 2021: 0; 2022: 31,71; 2023: 31,71; 2024: 31,71 *Nota: Serie administrativa reportada por el municipio a SSPD; tiene saltos inverosímiles (p. ej. 2012=91,47; 2013-2015=15,85; 2021=0) que indican errores de reporte. Usar con cautela.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (SSPD - Reporte de Estratificación y Coberturas, REC) |
| Cobertura alcantarillado REC total | % | 2008: 32,61; 2009: 33,87; 2010: 35,47; 2011: 21,86; 2012: 91,47; 2013: 15,85; 2014: 15,85; 2015: 15,85; 2016: 43,83; 2017: 43,82; 2018: 43,55; 2019: 52,95; 2020: 52,3; 2021: 0; 2022: 61,27; 2023: 61,27; 2024: 61,27 *Nota: Serie administrativa reportada por el municipio a SSPD; tiene saltos inverosímiles (p. ej. 2012=91,47; 2013-2015=15,85; 2021=0) que indican errores de reporte. Usar con cautela.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (SSPD - Reporte de Estratificación y Coberturas, REC) |
| Cobertura alcantarillado REC urbana | % | 2008: 0; 2009: 33,87; 2010: 99,02; 2011: 97,1; 2012: 100; 2013: 70,33; 2014: 70,33; 2015: 70,33; 2016: 100; 2017: 100; 2018: 100; 2019: 100; 2020: 100; 2021: 0; 2022: 100; 2023: 100; 2024: 100 *Nota: Serie administrativa reportada por el municipio a SSPD; tiene saltos inverosímiles (p. ej. 2012=91,47; 2013-2015=15,85; 2021=0) que indican errores de reporte. Usar con cautela.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (SSPD - Reporte de Estratificación y Coberturas, REC) |
| Cobertura alcantarillado REC rural | % | 2008: 32,61; 2009: 33,87; 2010: 5,17; 2011: 2,7; 2012: 0; 2013: 2,7; 2014: 0; 2015: 0; 2016: 0; 2017: 0; 2018: 0; 2019: 17,07; 2020: 16,7; 2021: 0; 2022: 31,71; 2023: 31,71; 2024: 31,71 *Nota: Serie administrativa reportada por el municipio a SSPD; tiene saltos inverosímiles (p. ej. 2012=91,47; 2013-2015=15,85; 2021=0) que indican errores de reporte. Usar con cautela.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (SSPD - Reporte de Estratificación y Coberturas, REC) |
| IRCA total Yondó (SIVICAP) | puntaje IRCA (0-100; >5 riesgo) | 2007: 0; 2008: 0; 2009: 7,5; 2010: 34,3; 2011: 47,2; 2012: 11,1; 2013: 5,2; 2014: 4,7; 2015: 2,2; 2016: 2,1; 2017: 0,9; 2018: 1,4; 2019: 2,4; 2020: 7,1; 2021: 7,4; 2022: 6,5; 2023: 6,3; 2024: 0,8 | https://www.datos.gov.co/resource/nxt2-39c3.json (INS-SIVICAP, Calidad del Agua para Consumo Humano en Colombia) |
| IRCA urbano Yondó | puntaje IRCA | 2007: 0; 2008: 0; 2009: 7,9; 2010: 20,8; 2011: 21,4; 2012: 11,1; 2013: 5,2; 2014: 5,1; 2015: 1,8; 2018: 1,4; 2019: 2,4; 2020: 2,5; 2021: 0,6; 2022: 1,5; 2023: 4; 2024: 0,8 | https://www.datos.gov.co/resource/nxt2-39c3.json (INS-SIVICAP, Calidad del Agua para Consumo Humano en Colombia) |
| IRCA rural Yondó | puntaje IRCA | 2010: 47,4; 2011: 86,4; 2020: 34,3; 2021: 82,6; 2022: 97,4; 2023: 88 *Nota: Años sin dato rural (ND) omitidos. 2021-2023 rural en nivel "inviable sanitariamente" (>80).* | https://www.datos.gov.co/resource/nxt2-39c3.json (INS-SIVICAP, Calidad del Agua para Consumo Humano en Colombia) |
| IRCA total Antioquia | puntaje IRCA | 2007: 7,8; 2008: 4,4; 2009: 5,4; 2010: 16,5; 2011: 20,9; 2012: 7,5; 2013: 9,2; 2014: 7,8; 2015: 6,8; 2016: 5,2; 2017: 3,3; 2018: 3,8; 2019: 3,7; 2020: 5,6; 2021: 6,4; 2022: 6,6; 2023: 5,4; 2024: 5,2 | https://www.datos.gov.co/resource/nxt2-39c3.json (INS-SIVICAP, Calidad del Agua para Consumo Humano en Colombia) |

Escala IRCA (Res. 2115/2007): 0-5 sin riesgo; 5,1-14 bajo; 14,1-35 medio; 35,1-80 alto; 80,1-100 inviable sanitariamente. Yondó fue "riesgo alto" en 2011 (47,2), con el rural "inviable" (86,4) durante La Niña 2010-2011. El IRCA urbano es "sin riesgo" (≤5) en todos los años reportados desde 2015, con un máximo de 4,0 en 2023. El rural fue "inviable sanitariamente" en 2021 (82,6), 2022 (97,4) y 2023 (88,0). En 2024 solo se reportó el área urbana (0,8).

**Prestador e infraestructura** (Superservicios, *Evaluación integral Aguas & Aseo de Yondó S.A. E.S.P., años 2018, 2019 y primer semestre de 2020*, [PDF](https://www.superservicios.gov.co/sites/default/files/inline-files/evaluacion_integral_aguas_aseo_yondo_s.a._e.s.p.pdf); copia en `raw/sspd/`):

| Aspecto | Dato | Año |
|---|---|---|
| Empresa prestadora | **Aguas & Aseo de Yondó S.A. E.S.P.** (empresa mixta; opera desde el 21-jul-1999; acueducto, alcantarillado y aseo) | 2020 |
| Fuente de captación urbana | **Laguna del Miedo**: bocatoma de fondo, ~30 L/s, aducción de 3 km en PVC de 12" y 10" | 2020 |
| PTAP municipal | Convencional, **40 L/s**, construida en **2003**, vereda Las Américas (vía a Barrancabermeja): aireación, floculación, sedimentación de alta tasa, 4 filtros rápidos, cloro gaseoso | 2020 |
| PTAP veredal | Compacta en fibra de vidrio, **15 L/s**, construida en **2014**, abastecida por pozo | 2020 |
| Obras en curso (mayo 2020) | "Optimización del sistema de acueducto": 2 pozos subterráneos, tanque de compensación y tanque elevado | 2020 |
| Continuidad | Servicio por horarios sectorizados de ~7-8 h/día, por debajo de lo pactado en el contrato de condiciones uniformes | 2019-2020 |
| Pérdidas (IANC) | Por encima del 30% máximo admisible (Res. CRA 151/2001) | 2019-2020 |
| Cobertura reportada por el prestador | Acueducto 98% urbano / 15% rural; alcantarillado 98% urbano / 0% rural (no presta alcantarillado rural) | 2020 |
| Suscriptores acueducto | 3.672 (dic-2019); 3.702 (abr-2020). Residenciales 96%: estrato 1 = 70,9%; estrato 2 = 20,9%; estrato 3 = 4,3% | 2019-2020 |
| Tratamiento de aguas residuales | **No hay PTAR**. Los vertimientos van sin tratamiento a cuerpos de agua desde 4 estaciones de bombeo: Progreso 13,52 L/s; Paraíso 16,51; Prado 10,62; Victoria 14,69 | 2019 |
| IRCA de vigilancia 2019 (mensual) | Ene 0; Feb 2,58; Mar 0; Abr 8,85; May 0; Jun 1,78; Jul-Sep 0; Oct 8,84; Nov 0; Dic 3,87 (35 muestras; incumplimientos de coliformes totales (3) y color (1)) | 2019 |

- **Monitoreo comunitario:** CREDHOS y el Comité Municipal de DD.HH. hicieron mediciones fisicoquímicas en las PTAP y en los humedales Laguna del Miedo y La Represa en febrero de 2024. Buscaban el impacto de la palma, la minería y el petróleo sobre las fuentes de agua ([PBI Canadá, 3-feb-2024](https://pbicanada.org/2024/02/03/pbi-colombia-accompanies-credhos-as-it-tests-water-in-yondo-calls-for-the-human-right-to-potable-water-to-be-respected/)). En 2019 se denunciaron descargas de aguas residuales en el barrio El Paraíso.
- **Proyectos de agua inconclusos:** **No encontrado.** No hallé evidencia verificable (Contraloría, prensa) de una obra de acueducto inconclusa específica en Yondó o San Miguel del Tigre. Tampoco encontré información posterior a 2020 sobre el estado de la optimización del acueducto ni sobre una PTAR.

## 4. Educación

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| Cobertura bruta total (transición a media) | % | 2005: 81,19; 2006: 86,95; 2007: 87,93; 2008: 87,84; 2009: 95,91; 2010: 98,14; 2011: 103,7; 2012: 109,11; 2013: 105,78; 2014: 100,23; 2015: 98,06; 2016: 99,59; 2017: 91,63; 2018: 87,73; 2019: 92,02; 2020: 90,84; 2021: 87,16; 2022: 92,96; 2023: 93,6; 2024: 90,12 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MEN-SIMAT/SINEB) |
| Cobertura neta total | % | 2005: 76,13; 2006: 77,51; 2007: 77,45; 2008: 80,9; 2009: 86,27; 2010: 88,82; 2011: 91,34; 2012: 93,36; 2013: 94,22; 2014: 90,45; 2015: 90,61; 2016: 87,37; 2017: 84,2; 2018: 80,51; 2019: 81,61; 2020: 83,69; 2021: 79,86; 2022: 85,55; 2023: 87,26; 2024: 84,96 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| Cobertura neta transición | % | 2005: 58,21; 2006: 62,18; 2007: 67,72; 2008: 74,42; 2009: 67,06; 2010: 83,58; 2011: 56,81; 2012: 80,9; 2013: 69,05; 2014: 71,75; 2015: 64,65; 2016: 46,1; 2017: 47,27; 2018: 39,33; 2019: 46,32; 2020: 49,13; 2021: 49,47; 2022: 58,21; 2023: 61,91; 2024: 64,32 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MEN-SIMAT/SINEB) |
| Cobertura neta primaria | % | 2005: 84,55; 2006: 85,71; 2007: 87,6; 2008: 90,03; 2009: 93,58; 2010: 100,97; 2011: 103,86; 2012: 103,83; 2013: 104,7; 2014: 99,26; 2015: 93,04; 2016: 89,66; 2017: 86,63; 2018: 84,72; 2019: 82,82; 2020: 83,33; 2021: 78,09; 2022: 81,79; 2023: 83,19; 2024: 81,83 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MEN-SIMAT/SINEB) |
| Cobertura neta secundaria | % | 2005: 35,06; 2006: 37,15; 2007: 42,12; 2008: 45,33; 2009: 53,52; 2010: 52,4; 2011: 53,2; 2012: 55,39; 2013: 54,25; 2014: 59,13; 2015: 58,94; 2016: 58,35; 2017: 59,12; 2018: 61,26; 2019: 59,62; 2020: 62,79; 2021: 61,59; 2022: 70,6; 2023: 73,56; 2024: 71,52 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MEN-SIMAT/SINEB) |
| Cobertura neta media | % | 2005: 13,75; 2006: 14,12; 2007: 14,23; 2008: 15,78; 2009: 19,03; 2010: 22,28; 2011: 24,18; 2012: 19,62; 2013: 25,14; 2014: 19,97; 2015: 21,4; 2016: 27,25; 2017: 24,78; 2018: 25,3; 2019: 24,71; 2020: 26,43; 2021: 26,89; 2022: 29,09; 2023: 36,49; 2024: 31,44 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MEN-SIMAT/SINEB) |
| Cobertura bruta media | % | 2005: 31,26; 2006: 33,67; 2007: 33,38; 2008: 32,54; 2009: 39,86; 2010: 47,87; 2011: 57,14; 2012: 50,75; 2013: 51,51; 2014: 45,45; 2015: 40,56; 2016: 47,31; 2017: 43,13; 2018: 42,71; 2019: 44,56; 2020: 48,35; 2021: 53,78; 2022: 54,55; 2023: 62,75; 2024: 56,75 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MEN-SIMAT/SINEB) |
| Cobertura neta total Antioquia | % | 2005: 88,63; 2006: 90,89; 2007: 90,92; 2008: 91,06; 2009: 93,18; 2010: 92,17; 2011: 93,85; 2012: 92,65; 2013: 91,93; 2014: 90,85; 2015: 96,37; 2016: 95,85; 2017: 94,82; 2018: 94,11; 2019: 93,83; 2020: 94,27; 2021: 93,48; 2022: 93,32; 2023: 91,89; 2024: 89,85 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip |
| Cobertura neta total Colombia | % | 2005: 88,11; 2006: 89,42; 2007: 89,38; 2008: 89,2; 2009: 89,36; 2010: 89,79; 2011: 90,54; 2012: 88,31; 2013: 87,55; 2014: 86,22; 2015: 92,36; 2016: 92,43; 2017: 92,38; 2018: 92,27; 2019: 92,35; 2020: 92,47; 2021: 92,32; 2022: 91,52; 2023: 90,27; 2024: 88,21 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip |
| Deserción intra-anual total | % | 2015: 6,98; 2016: 9,01; 2017: 8,21; 2018: 5,28; 2019: 4,8; 2020: 4,94; 2021: 4,48; 2022: 2,98; 2023: 4,21; 2024: 2,9 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| Deserción intra-anual sector oficial | % | 2011: 5,9; 2012: 8,15; 2013: 3,35; 2014: 1,6; 2015: 7,37; 2016: 9,51; 2017: 8,64; 2018: 5,61; 2019: 5,12; 2020: 4; 2021: 4,69; 2022: 3,11; 2023: 4,48; 2024: 3,07 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MEN-SIMAT/SINEB) |
| Deserción intra-anual Antioquia | % | 2015: 3,69; 2016: 4,19; 2017: 3,88; 2018: 3,68; 2019: 3,85; 2020: 2,41; 2021: 4,73; 2022: 4,49; 2023: 4,72; 2024: 3,5 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip |
| Deserción intra-anual Colombia | % | 2015: 3,37; 2016: 3,47; 2017: 2,91; 2018: 2,84; 2019: 2,99; 2020: 2,55; 2021: 3,62; 2022: 4,11; 2023: 3,75; 2024: 3,44 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip |
| Repitencia sector oficial | % | 2011: 1,97; 2012: 2,12; 2013: 5,66; 2014: 6,74; 2015: 12,13; 2016: 5,01; 2017: 9,4; 2018: 3,57; 2019: 2,83; 2020: 9,33; 2021: 8,9; 2022: 6,76; 2023: 11,55; 2024: 11,32 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MEN-SIMAT/SINEB) |
| Saber 11 Matemáticas Yondó | puntos (0-100) | 2010: 46,43; 2011: 40,7; 2012: 42,52; 2013: 40,9; 2014: 47,63; 2015: 44,33; 2016: 46,69; 2017: 49,28; 2018: 46,86; 2019: 47,51; 2020: 48,77; 2021: 45,86; 2022: 48,26 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (ICFES) |
| Saber 11 Matemáticas Antioquia | puntos (0-100) | 2010: 49,03; 2011: 45,12; 2012: 45,39; 2013: 44,41; 2014: 49,26; 2015: 49,54; 2016: 48,12; 2017: 49,38; 2018: 48,85; 2019: 49,31; 2020: 49,82; 2021: 48,67; 2022: 49,27 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip (ICFES) |
| Saber 11 Matemáticas Colombia | puntos (0-100) | 2010: 50,04; 2011: 46,35; 2012: 45,68; 2013: 45,24; 2014: 49,8; 2015: 50,36; 2016: 49,62; 2017: 50,35; 2018: 50,42; 2019: 50,64; 2020: 51,05; 2021: 49,43; 2022: 50,83 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip (ICFES) |
| Saber 11 Lectura crítica Yondó | puntos (0-100) | 2010: 46,89; 2011: 41,3; 2012: 43,4; 2013: 42,98; 2014: 47,42; 2015: 45,8; 2016: 48,79; 2017: 52,35; 2018: 49,9; 2019: 48,03; 2020: 48,94; 2021: 49,46; 2022: 49,72 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (ICFES) |
| Saber 11 Lectura crítica Antioquia | puntos (0-100) | 2010: 50,15; 2011: 46,48; 2012: 46,32; 2013: 47,39; 2014: 50,37; 2015: 49,85; 2016: 50,83; 2017: 53,29; 2018: 52,7; 2019: 52,21; 2020: 52,03; 2021: 52,28; 2022: 52,44 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip (ICFES) |
| Saber 11 Lectura crítica Colombia | puntos (0-100) | 2010: 50,09; 2011: 46,43; 2012: 46,29; 2013: 47,29; 2014: 49,95; 2015: 49,92; 2016: 51,5; 2017: 53,4; 2018: 52,79; 2019: 52,19; 2020: 52,18; 2021: 52,05; 2022: 53,02 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip (ICFES) |
| Saber 11 puntaje global promedio Yondó (cálculo propio, microdatos ICFES) | puntos (0-500) | 2014: 235,46; 2015: 226,07; 2016: 241,59; 2017: 250,47; 2019: 224,02; 2022: 231,84 *Nota: Promedio simple de estudiantes por periodo (calendario A). Periodo 20194 del dataset agrupa la aplicación 2018-2019; se asigna a 2019. N estudiantes: 2014=152, 2015=122, 2016=124, 2017=105, 2019=286, 2022=282.* | https://www.datos.gov.co/resource/kgxf-xxbe.json (ICFES Resultados únicos Saber 11, filtro cole_cod_mcpio_ubicacion=05893; cálculo propio) |
| Establecimientos educativos | número | 2015: 7; 2016: 7; 2017: 7; 2018: 7; 2019: 7; 2020: 7; 2021: 7; 2022: 7; 2023: 7; 2024: 7; 2025: 7 *Nota: 5 oficiales (I.E. Luis Eduardo Díaz, I.E.R. San Miguel del Tigre, I.E.R./C.E.R. La Raya, C.E.R. La Primavera, C.E.R. Caño Blanco) y 2 privados. 2023 reconstruido manualmente: el registro 2023 del dataset asigna por error a Yondó todos los establecimientos de Antioquia.* | https://www.datos.gov.co/resource/cfw5-qzt5.json (MEN Establecimientos educativos preescolar, básica y media) |
| Sedes educativas | número | 2015: 49; 2016: 49; 2017: 48; 2018: 49; 2019: 49; 2020: 49; 2021: 49; 2022: 48; 2023: 46; 2024: 46; 2025: 46 | https://www.datos.gov.co/resource/cfw5-qzt5.json (MEN Establecimientos educativos preescolar, básica y media) |
| Matrícula reportada por los establecimientos | estudiantes | 2015: 4.544; 2016: 4.622; 2017: 4.266; 2018: 4.138; 2019: 4.433; 2020: 4.327; 2021: 4.148; 2022: 4.475; 2023: 4.509; 2024: 4.342; 2025: 4.395 | https://www.datos.gov.co/resource/cfw5-qzt5.json (MEN Establecimientos educativos preescolar, básica y media) |
| Tránsito inmediato a educación superior Yondó | % | 2014: 27,27; 2015: 20,59; 2016: 29; 2017: 28,44; 2018: 27,43; 2019: 50; 2020: 36,64; 2021: 48,1; 2022: 40,58; 2023: 47,79; 2024: 53,69 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| Tránsito inmediato Antioquia | % | 2014: 34,22; 2015: 34,55; 2016: 34,91; 2017: 40,9; 2018: 39,4; 2019: 42,71; 2020: 41,37; 2021: 38,31; 2022: 38,66; 2023: 41,34; 2024: 44,23 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip |
| Tránsito inmediato Colombia | % | 2015: 37,45; 2016: 37,97; 2017: 42,38; 2018: 38,69; 2019: 39,71; 2020: 40,04; 2021: 39,71; 2022: 41,08; 2023: 43,06; 2024: 45,94 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip |
| Cobertura educación superior (matrícula en el municipio) | % | 2018: 0; 2019: 0; 2020: 0; 2021: 0; 2022: 0; 2023: 0; 2024: 0 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MEN-SIMAT/SINEB) |

| Indicador | Año | Valor | Fuente (URL) |
|---|---|---|---|
| Tasa de analfabetismo total / urbana / rural (15+) | 2018 | 9,71% / 7,17% / 12,66% | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 (DANE CNPV 2018) |
| Asistencia escolar 5-24 años total / urbana / rural | 2018 | 65,07% / 68,36% / 60,90% | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 |
| Alfabetismo de la población de 5 años y más total / cabecera / resto | 2005 | 80,3% / 84,9% / 75,3% | https://www.dane.gov.co/files/censo2005/perfiles/antioquia/yondo.pdf |
| Asistencia escolar 3-5 / 6-10 / 11-17 años | 2005 | 24,8% / 82,0% / 70,4% | idem |
| Población con nivel profesional / posgrado | 2005 | 1,0% / 0,1% | idem |

- **Sedes:** 49 sedes en 2015 y 46 en 2024-2025. Hay 7 establecimientos: I.E. Luis Eduardo Díaz (urbana, 3 sedes, ~2.390 alumnos), I.E.R. San Miguel del Tigre (8 sedes), C.E.R. La Primavera (14), I.E.R. La Raya (9), C.E.R. Caño Blanco (10) y los privados Colegio El Oasis y C.E. Mi Nuevo Horizonte.
- **Saber 11:** TerriData publica datos hasta 2022. Para **2023, 2024 y 2025** **No encontrado**: el conjunto abierto del ICFES en datos.gov.co (kgxf-xxbe) termina en 2022. La brecha frente a Colombia en matemáticas fue de -3,6 puntos (2010), -5,7 (2011), -2,2 (2014), -1,1 (2017) y -2,6 (2022).
- **Educación superior:** TerriData registra 0% de cobertura con matrícula en el municipio entre 2018 y 2024, es decir, no hay oferta registrada en Yondó. El tránsito inmediato se duplicó (27,3% en 2014 a 53,7% en 2024) y supera a Antioquia (44,2%) y Colombia (45,9%) en 2024. Probablemente refleja la cercanía de Barrancabermeja (inferencia, no verificada). Las sedes o programas de IES en el municipio quedan como **No encontrado**.
- Los datos MEN de "sedes conectadas a internet" por municipio están vacíos para Yondó: **No encontrado**.

## 5. Salud

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| Afiliados SGSSS | personas | 2012: 11.403; 2013: 11.673; 2014: 11.487; 2015: 11.502; 2016: 10.707; 2017: 10.897; 2018: 11.625; 2019: 11.218; 2020: 11.586; 2021: 11.521; 2022: 11.323; 2023: 10.638; 2024: 10.413; 2025: 10.179 *Nota: Afiliados con municipio de afiliación Yondó (BDUA). Equivalen a ~46-61% de la población proyectada; parte de la población se afilia/atiende en Barrancabermeja. No interpretar como no asegurados.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Afiliados régimen contributivo | personas | 2012: 747; 2013: 1.048; 2014: 949; 2015: 1.003; 2016: 822; 2017: 668; 2018: 811; 2019: 1.016; 2020: 1.242; 2021: 1.490; 2022: 1.414; 2023: 1.229; 2024: 1.344; 2025: 1.314 *Nota: Afiliados con municipio de afiliación Yondó (BDUA). Equivalen a ~46-61% de la población proyectada; parte de la población se afilia/atiende en Barrancabermeja. No interpretar como no asegurados.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Afiliados régimen subsidiado | personas | 2012: 10.656; 2013: 10.625; 2014: 10.538; 2015: 10.499; 2016: 9.885; 2017: 10.229; 2018: 10.599; 2019: 9.997; 2020: 10.083; 2021: 9.762; 2022: 9.636; 2023: 9.092; 2024: 8.738; 2025: 8.503 *Nota: Afiliados con municipio de afiliación Yondó (BDUA). Equivalen a ~46-61% de la población proyectada; parte de la población se afilia/atiende en Barrancabermeja. No interpretar como no asegurados.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Afiliados regímenes especiales | personas | 2012: 78; 2013: 78; 2014: 162; 2015: 200; 2016: 209; 2017: 221; 2018: 215; 2019: 205; 2020: 261; 2021: 269; 2022: 273; 2023: 317; 2024: 331; 2025: 362 *Nota: Afiliados con municipio de afiliación Yondó (BDUA). Equivalen a ~46-61% de la población proyectada; parte de la población se afilia/atiende en Barrancabermeja. No interpretar como no asegurados.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Cobertura régimen subsidiado | % | 2010: 90,2; 2011: 100; 2012: 100; 2013: 100; 2014: 95,2; 2015: 95,4; 2016: 97,3; 2017: 97,81; 2018: 53,65; 2019: 49,65; 2020: 49,75; 2021: 47,43; 2022: 46,1; 2023: 42,92; 2024: 42,01; 2025: 40,62 *Nota: Salto 2017->2018 (97,8 -> 53,7) por cambio de denominador (población proyectada CNPV 2018), no por pérdida real de afiliados.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Mortalidad infantil <1 año Yondó | por 1.000 nacidos vivos | 2005: 24,45; 2006: 23,91; 2007: 23,36; 2008: 22,82; 2009: 22,28; 2010: 21,73; 2011: 20,99; 2012: 20,92; 2013: 18,83; 2014: 17,4; 2015: 19,15; 2016: 19,82; 2017: 7,27; 2018: 24,39; 2019: 14,02; 2020: 15,07; 2021: 10,87; 2022: 8,23; 2023: 14,49; 2024: 9,52 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Mortalidad infantil <1 año Antioquia | por 1.000 nacidos vivos | 2005: 16,75; 2006: 16,53; 2007: 16,32; 2008: 16,1; 2009: 15,88; 2010: 15,66; 2011: 15,05; 2012: 14,7; 2013: 14,57; 2014: 14,52; 2015: 14,37; 2016: 14,09; 2017: 9,11; 2018: 8,48; 2019: 8,75; 2020: 12,61; 2021: 9,44; 2022: 8,94; 2023: 7,81; 2024: 8,42 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip |
| Mortalidad infantil <1 año Colombia | por 1.000 nacidos vivos | 2005: 20,4; 2006: 19,99; 2007: 19,58; 2008: 19,17; 2009: 18,76; 2010: 18,36; 2011: 17,78; 2012: 17,47; 2013: 17,25; 2014: 17,23; 2015: 17,1; 2016: 16,8; 2017: 10,73; 2018: 11,29; 2019: 11,35; 2020: 17,62; 2021: 10,94; 2022: 11,66; 2023: 10,88; 2024: 10,37 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip |
| Mortalidad en menores de 5 años | por 1.000 nacidos vivos | 2005: 29,2; 2006: 42,9; 2007: 32,14; 2008: 8; 2009: 14,88; 2010: 33,09; 2011: 6,1; 2012: 35,71; 2013: 14,13; 2014: 9,23; 2015: 3,51; 2016: 9,52; 2017: 7,27; 2018: 28,46; 2019: 18,69; 2020: 0; 2021: 18,12; 2022: 12,35; 2023: 18,12; 2024: 14,29 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Mortalidad neonatal | por 1.000 nacidos vivos | 2005: 18,25; 2006: 13,2; 2007: 21,43; 2008: 4; 2009: 8,93; 2010: 18,38; 2011: 0; 2012: 21,43; 2013: 10,6; 2014: 3,08; 2015: 3,51; 2016: 0; 2017: 0; 2018: 16,26; 2019: 9,35; 2020: 0; 2021: 10,87; 2022: 8,23; 2023: 14,49; 2024: 9,52 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Razón de mortalidad materna a 42 días | por 100.000 nacidos vivos | 2011: 304,88; 2015: 350,88; 2016: 317,46; 2018: 406,5; 2019: 0; 2020: 0; 2021: 0 *Nota: Con ~250-330 nacimientos/año, 1 muerte materna = 300-400 por 100.000 NV. Años vacíos en TerriData = sin dato o sin casos.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Muertes maternas notificadas (SIVIGILA, ocurrencia) | casos notificados | 2011: 1; 2014: 1; 2016: 1; 2018: 1; 2020: 1 | https://www.datos.gov.co/resource/4hyg-wa9d.json (INS - Datos de Vigilancia en Salud Pública, municipio de ocurrencia 05893) |
| Muertes por desnutrición en menores de 5 años | defunciones | 2005: 0; 2006: 0; 2007: 0; 2008: 0; 2009: 0; 2010: 0; 2011: 0; 2012: 0; 2013: 0; 2014: 0; 2015: 0; 2016: 0; 2017: 0; 2018: 0; 2019: 0; 2020: 0; 2021: 1; 2022: 0; 2023: 0; 2024: 0; 2025: 0 | https://www.datos.gov.co/resource/xvyx-dzp4.json (Gobernación de Antioquia - Mortalidad por desnutrición en menores de 5 años) |
| Casos de desnutrición aguda en menores de 5 años (SIVIGILA) | casos notificados | 2017: 3; 2018: 3; 2019: 6; 2020: 2; 2021: 5; 2022: 14 | https://www.datos.gov.co/resource/4hyg-wa9d.json (INS - Datos de Vigilancia en Salud Pública, municipio de ocurrencia 05893) |
| % nacidos vivos con bajo peso | % | 2005: 5,68; 2006: 7,93; 2007: 5,42; 2008: 6,53; 2009: 5,71; 2010: 7,72; 2011: 8,56; 2012: 6,43; 2013: 5,3; 2014: 4,63; 2015: 4,93; 2016: 8,57; 2017: 8,36; 2018: 3,15; 2019: 4,67; 2020: 7,22; 2021: 8,7; 2022: 9,47; 2023: 10,87; 2024: 9,52 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Incidencia de dengue | casos por 100.000 hab. en riesgo | 2017: 71,18; 2018: 59,67; 2019: 360,03; 2020: 54,7; 2021: 29,37; 2022: 101,25; 2023: 280,09; 2024: 192,99 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Casos de dengue (SIVIGILA) | casos notificados | 2007: 6; 2008: 36; 2009: 18; 2010: 79; 2011: 26; 2012: 44; 2013: 88; 2014: 42; 2015: 19; 2016: 18; 2017: 7; 2018: 6; 2019: 37; 2020: 11; 2021: 6; 2022: 25 *Nota: Dengue + dengue grave.* | https://www.datos.gov.co/resource/4hyg-wa9d.json (INS - Datos de Vigilancia en Salud Pública, municipio de ocurrencia 05893) |
| Casos de malaria (SIVIGILA) | casos notificados | 2007: 1; 2008: 183; 2009: 21; 2010: 27; 2011: 20; 2012: 83; 2013: 32; 2014: 61; 2015: 18; 2016: 43; 2017: 78; 2018: 49; 2019: 40; 2021: 9; 2022: 19 *Nota: Suma de vivax, falciparum, mixta, malariae y complicada. 2020 sin registros en el dataset. Dataset termina en 2022.* | https://www.datos.gov.co/resource/4hyg-wa9d.json (INS - Datos de Vigilancia en Salud Pública, municipio de ocurrencia 05893) |
| Incidencia de tuberculosis | por 100.000 hab. | 2017: 5,16; 2018: 20,25; 2019: 20,38; 2020: 0; 2021: 9,79; 2022: 19,6; 2023: 19,44; 2024: 28,95 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Cobertura de vacunación pentavalente <1 año | % | 2005: 87,39; 2006: 84,57; 2007: 85,92; 2008: 86,99; 2009: 109,4; 2010: 81,51; 2011: 85,52; 2012: 78,6; 2013: 90,8; 2014: 85; 2015: 81,3; 2016: 96,84; 2017: 102,95; 2018: 96,1; 2019: 97,29; 2020: 52,43; 2021: 52,54; 2022: 40,56; 2023: 52,42; 2024: 52,45; 2025: 46,51 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Fecundidad 15-19 años | nacidos vivos por 1.000 mujeres 15-19 | 2016: 86,46; 2017: 71,43; 2018: 75,45; 2019: 80,6; 2020: 91,36; 2021: 78,85; 2022: 59,82; 2023: 85,3; 2024: 47,57 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |
| Tasa de mortalidad general | por 1.000 hab. | 2005: 4,37; 2006: 4,41; 2007: 3,94; 2008: 3,91; 2009: 4,26; 2010: 5,06; 2011: 3,56; 2012: 4,46; 2013: 4,31; 2014: 3,4; 2015: 4,19; 2016: 3,11; 2017: 2,74; 2018: 3,85; 2019: 2,96; 2020: 3,88; 2021: 5,68; 2022: 4,8; 2023: 3,74; 2024: 4,58 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinSalud/INS/DANE EEVV) |

- La mortalidad infantil 2005-2016 de TerriData parece una serie modelada o suavizada (descenso lineal de 24,45 a 17,40), con un cambio de fuente desde 2017. Hay que tratar con cautela la comparación antes y después de 2017.
- **Malaria:** el pico fue en 2008 (183 casos, 141 de ellos por *P. vivax*). Hubo rebrotes en 2012 (83), 2017 (78) y 2014 (61), y 19 casos en 2022.
- **Dengue:** picos en 2013 (88 casos) y 2010 (79). La incidencia fue de 360 por 100.000 hab. en riesgo en 2019 y de 280 en 2023.
- **Desnutrición:** 1 muerte de menor de 5 años en 2021 y 0 en el resto de 2005-2025. Los casos de desnutrición aguda subieron a 14 en 2022.
- **Mortalidad materna:** 1 caso en 2011, 2014 (SIVIGILA) o 2015 (TerriData), 2016, 2018 y 2020 (SIVIGILA). La razón resulta muy volátil por el bajo número de nacimientos.
- La cobertura de vacunación pentavalente bajó de ~96-103% (2016-2019) a ~41-52% (2020-2025). Puede reflejar un problema real o el cambio de denominador poblacional; no lo verifiqué.
- La red hospitalaria (nombre y nivel de la E.S.E. local) no quedó verificada en esta sesión: **No encontrado**.

## 6. Conectividad

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| Penetración internet fijo Yondó | accesos fijos por 100 hab. (4T) | 2010: 1,64; 2011: 1,67; 2012: 2,25; 2013: 2,45; 2014: 2,75; 2015: 3,77; 2016: 3,65; 2017: 4,45; 2018: 4,9; 2019: 5,45; 2020: 5,86; 2021: 7,64; 2022: 7,25; 2023: 5,06; 2024: 3,41; 2025: 3,56 *Nota: Valor anual = cuarto trimestre (en 2025 el último trimestre publicado en TerriData).* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinTIC - Boletín trimestral TIC) |
| Penetración internet fijo Antioquia | accesos fijos por 100 hab. (4T) | 2010: 8,44; 2011: 10,91; 2012: 12,98; 2013: 13,39; 2014: 13,99; 2015: 14,65; 2016: 15,81; 2017: 16,61; 2018: 18,17; 2019: 18,82; 2020: 20,51; 2021: 22,49; 2022: 24,23; 2023: 23,07; 2024: 23,95; 2025: 26,1 *Nota: Valor anual = cuarto trimestre (en 2025 el último trimestre publicado en TerriData).* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip (MinTIC - Boletín trimestral TIC) |
| Penetración internet fijo Colombia | accesos fijos por 100 hab. (4T) | 2010: 5,83; 2011: 7,23; 2012: 8,67; 2013: 9,55; 2014: 10,6; 2015: 11,39; 2016: 12,18; 2017: 12,69; 2018: 13,94; 2019: 14,12; 2020: 15,57; 2021: 16,56; 2022: 17,08; 2023: 17,1; 2024: 17,51; 2025: 19,33 *Nota: Valor anual = cuarto trimestre (en 2025 el último trimestre publicado en TerriData).* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip (MinTIC - Boletín trimestral TIC) |
| Accesos fijos a internet Yondó | accesos (último trimestre disponible del año) | 2017: 862; 2018: 933; 2019: 1.069; 2020: 1.168; 2021: 1.545; 2022: 1.479; 2023: 1.062 *Nota: 2017 desde 2T; 2023 hasta 3T (fin del dataset). 2023-3T: 1.062 accesos (661 xDSL Edatel, 238 inalámbrico DirecTV, 127 satelital Hughes, 34 FTTH).* | https://www.datos.gov.co/resource/n48w-gutb.json (MinTIC Internet Fijo Accesos por tecnología y segmento; suma propia) |
| Hogares con internet (CNPV 2018) | % hogares | 2018: 10,57 *Nota: Urbana 17,75%; rural 1,81%.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE CNPV 2018) |

- **Centros Digitales MinTIC** (corte 31-oct-2023): 4 en operación, todos en sedes educativas rurales de la zona del corregimiento San Miguel del Tigre: I.E.R. San Luis Beltrán, C.E.R. La Primavera, I.E.R. San Miguel del Tigre y C.E.R. La Raya. Inversión registrada: $142.684.114 COP cada uno ([datos.gov.co fybg-535s](https://www.datos.gov.co/resource/fybg-535s.json)).
- El conjunto de penetración por municipio que se buscaba no existe hoy en datos.gov.co como dataset independiente. La serie viene del boletín MinTIC compilado por TerriData. Para verificarla, sumé los accesos del dataset n48w-gutb: 933 accesos en el 4T de 2018 sobre 19.043 hab. = 4,90 por 100 hab., igual al valor de TerriData.
- La caída de 2023-2025 coincide con la pérdida de accesos xDSL e inalámbricos. En 2023-3T, Edatel xDSL tenía 661 accesos, el 62% del total.
- Telefonía e internet móvil por municipio: **No encontrado**.

## 7. Vías y movilidad

| Tema | Dato | Fecha | Fuente (URL) |
|---|---|---|---|
| Puente Barrancabermeja-Yondó (**Puente Guillermo Gaviria Correa**) sobre el río Magdalena | Viga cajón de concreto preesforzado, luces de 100+200+100 m, longitud total 917 m, terminado en 2006. Ganó el XV Premio Obras Cemex (2006). Antes del puente, a Yondó se llegaba cruzando el río en chalupa o ferry | 2006 | https://en.wikipedia.org/wiki/List_of_bridges_in_Colombia ; https://revistas.uis.edu.co/index.php/revistasantander/article/download/2192/2553/6320 ; https://www.las2orillas.co/?p=523331 |
| Corredor 4G Bucaramanga-Barrancabermeja-Yondó (Concesionaria Ruta del Cacao) | 152 km, de ellos 95 km de doble calzada Bucaramanga-Barrancabermeja. Avance del 99% e inversión de $2,6 billones. La UF8 sigue pendiente por un derrumbe el 1-oct-2023 (PR 42) | may-2025 | https://www.vanguardia.com/santander/barrancabermeja/2025/05/06/gremios-de-santander-exigen-al-gobierno-culminar-tramo-vial-bucaramanga-barrancabermeja-yondo/ |
| Estado del puente en 2026 | 16-mar-2026: cierre total por socavación en el acceso del lado de Yondó. 20-mar: reapertura parcial a un carril para vehículos livianos. 6-may: nueva falla y paso restringido a un carril. 3-5 de junio: Ruta del Cacao atribuye la falla a la socavación lateral del Magdalena y a diseños e intervenciones de terceros, y ejecuta obras temporales (roca, rellenos, base modular) mientras estudia una solución definitiva. Por el corredor pasan entre 5.000 y 8.000 vehículos al día | mar-jun 2026 | https://www.elcolombiano.com/antioquia/rehabilitan-paso-puente-entre-yondo-y-barrancabermeja-BP34804522 ; https://www.vanguardia.com/santander/barrancabermeja/2026/06/04/por-que-sigue-en-riesgo-el-puente-que-conecta-a-barrancabermeja-con-yondo-ruta-del-cacao-explico-las-causas/ ; https://www.bluradio.com/regiones/santanderes/erosion-del-rio-magdalena-pone-en-riesgo-puente-entre-santander-y-antioquia-rg10 |
| Estado del puente después de junio de 2026 | **No encontrado** (no verificado por el límite de búsquedas) | — | — |
| Vía Puerto Berrío-Yondó (94 km), programa departamental de pavimentación de vías a cabeceras | "No se avanzó... el recurso no alcanzó" (secretario de Infraestructura). La meta es dejar los tramos pendientes en ejecución antes de 2028 | 4-may-2025 | https://www.elcolombiano.com/antioquia/inversion-en-obras-para-las-vias-en-las-cabeceras-de-antioquia-BG27307363 |
| Licitación departamental de pavimentación con estabilización (29 tramos, 634,43 km) | Magdalena Medio, 55 km: **La Ye-Yondó, 30 km**; Remedios-La Ye de la Virgen-Puerto Berrío, 25 km. El documento dice "Se adjudica en enero de 2026"; no hallé el avance de obra | 2025-2026 | https://www.antioquia.gov.co/images/PDF2/Infraestructura/2025/estabilizacion.pdf (copia en raw/gob_antioquia/) |
| Vías terciarias | Placa huella de 8,2 km en las veredas Kilómetro Cinco y Caño Bonito: $5.426 millones de la Gobernación y $5.647 millones del municipio, más de 4.000 beneficiarios (nota de la Gobernación, ~2021; la página ya no está disponible y el dato viene del extracto del buscador) | ~2021 | https://antioquia.gov.co/secretaria-infraestructura-oculto/gobernacion-de-antioquia-y-yondo-hicieron-entrega-de-nueva-placa-huella-de-82-kilometros-para-beneficio-de-sus-comunidades-rurales |
| Siniestros viales: fallecidos | 2015: 2; 2016: 4; 2017: 6; 2018: 2; 2019: 8; 2020: 2; 2021: 10; 2022: 8 | 2015-2022 | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 |
| Inventario de km de red terciaria y % pavimentado del municipio | **No encontrado** | — | — |

## 8. Seguridad y conflicto armado

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| Homicidios (casos, MinDefensa/SIEDCO) | homicidios (casos) | 2003: 4; 2004: 15; 2005: 9; 2006: 7; 2007: 11; 2008: 12; 2009: 14; 2010: 10; 2011: 7; 2012: 8; 2013: 12; 2014: 8; 2015: 19; 2016: 3; 2017: 6; 2018: 7; 2019: 3; 2020: 11; 2021: 15; 2022: 18; 2023: 19; 2024: 18; 2025: 41; 2026: 13 *Nota: 2026 parcial (enero-agosto). 2025: 41 (12 en julio).* | https://www.datos.gov.co/resource/m8fd-ahd9.json (MinDefensa/Policía SIEDCO, HOMICIDIO; suma de cantidad, cod_muni 05893) |
| Presuntos homicidios (Medicina Legal) | presuntos homicidios | 2015: 20; 2016: 4; 2017: 6; 2018: 9; 2019: 4; 2020: 10; 2021: 14; 2022: 23; 2023: 24; 2024: 18 | https://www.datos.gov.co/resource/vtub-3de2.json (INMLCF, cifras definitivas 2015-2024) |
| Tasa de homicidio intencional Yondó | por 100.000 hab. | 2003: 29; 2004: 106; 2005: 62,2; 2006: 47,3; 2007: 72,8; 2008: 77,4; 2009: 88,2; 2010: 61,9; 2011: 42,4; 2012: 47,4; 2013: 69,8; 2014: 45,7; 2015: 106,7; 2016: 16,5; 2017: 32,2; 2018: 36,8; 2019: 15,4; 2020: 54,9; 2021: 73,3; 2022: 86,3; 2023: 89,4; 2024: 83; 2025: 185,8 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DNP con MinDefensa y DANE) |
| Tasa de homicidio Antioquia | por 100.000 hab. | 2003: 78,7; 2004: 45,3; 2005: 40,2; 2006: 37,5; 2007: 34,8; 2008: 39,1; 2009: 48,8; 2010: 47,2; 2011: 49,8; 2012: 51,4; 2013: 40,9; 2014: 32,5; 2015: 30,8; 2016: 30; 2017: 30,5; 2018: 38,1; 2019: 35,8; 2020: 30,5; 2021: 31,4; 2022: 28; 2023: 25,6; 2024: 24,5; 2025: 24,7 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05000.txt.zip (DNP con MinDefensa y DANE) |
| Tasa de homicidio Colombia | por 100.000 hab. | 2003: 55,6; 2004: 46; 2005: 40,5; 2006: 37,6; 2007: 35,8; 2008: 34,2; 2009: 35,2; 2010: 33,7; 2011: 35,2; 2012: 35,2; 2013: 32,6; 2014: 28; 2015: 26,6; 2016: 25,7; 2017: 25,2; 2018: 26,1; 2019: 25,5; 2020: 23,8; 2021: 26,8; 2022: 26,2; 2023: 26; 2024: 25,7; 2025: 25,9 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData01001.txt.zip (DNP con MinDefensa y DANE) |
| Tasa de homicidio rural Yondó | por 100.000 hab. | 2003: 40,3; 2004: 171,6; 2005: 104; 2006: 51,2; 2007: 139,3; 2008: 86,9; 2009: 109,6; 2010: 108,5; 2011: 71,2; 2012: 93,5; 2013: 115; 2014: 79,3; 2015: 134,4; 2016: 22,1; 2017: 32,4; 2018: 53,2; 2019: 20,9; 2020: 51,2; 2021: 121,2; 2022: 129,9; 2023: 98,8; 2024: 96,5; 2025: 276,9 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| Tasa de homicidio urbano Yondó | por 100.000 hab. | 2003: 15,7; 2004: 30,4; 2005: 14,8; 2006: 42,8; 2008: 67,2; 2009: 65,3; 2010: 12,7; 2011: 12,4; 2013: 23,6; 2014: 11,5; 2015: 78,8; 2016: 10,9; 2017: 32,1; 2018: 20,7; 2019: 10; 2020: 58,4; 2021: 28,4; 2022: 46,1; 2023: 80,9; 2024: 70,7; 2025: 103,6 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| Víctimas RUV por año de ocurrencia | personas victimizadas en el año (ocurrencia en Yondó) | 1996: 434; 1997: 492; 1998: 1.513; 1999: 316; 2000: 3.817; 2001: 2.128; 2002: 1.335; 2003: 423; 2004: 798; 2005: 1.338; 2006: 1.501; 2007: 1.739; 2008: 1.429; 2009: 341; 2010: 239; 2011: 129; 2012: 163; 2013: 182; 2014: 159; 2015: 159; 2016: 146; 2017: 68; 2018: 98; 2019: 128; 2020: 44; 2021: 80; 2022: 227; 2023: 261; 2024: 208; 2025: 532; 2026: 274 *Nota: Una persona puede contarse en más de un año. 2026 parcial. Total 1985-2026 (suma anual): 22.002.* | https://www.datos.gov.co/resource/m64i-rnss.json (UARIV - Víctimas por años municipal, corte 30/09/2026) |
| Desplazamiento forzado: personas expulsadas | personas expulsadas | 1996: 405; 1997: 431; 1998: 1.502; 1999: 295; 2000: 3.670; 2001: 2.036; 2002: 1.225; 2003: 350; 2004: 689; 2005: 1.269; 2006: 1.459; 2007: 1.702; 2008: 1.388; 2009: 299; 2010: 219; 2011: 122; 2012: 153; 2013: 162; 2014: 144; 2015: 149; 2016: 139; 2017: 59; 2018: 95; 2019: 110; 2020: 38; 2021: 52; 2022: 163; 2023: 231; 2024: 158; 2025: 446; 2026: 262 *Nota: Total histórico expulsión: 20.314 personas. 2026 parcial.* | https://www.datos.gov.co/resource/krnc-8azs.json (UARIV - Desplazamiento anualizado ocurrencia y llegada, corte 30/09/2026) |
| Hechos victimizantes por ocurrencia (TerriData) | hechos victimizantes | 2018: 304; 2019: 379; 2020: 155; 2021: 227; 2022: 638; 2023: 784; 2024: 533; 2025: 1.250 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (UARIV-RNI) |
| Eventos de minas antipersonal | eventos | 2002: 5; 2003: 2; 2004: 1; 2005: 2; 2006: 3; 2007: 2; 2008: 1; 2009: 2; 2010: 3; 2011: 9; 2012: 3; 2013: 3; 2014: 1; 2015: 4; 2016: 4; 2017: 0; 2018: 0; 2019: 0; 2020: 0; 2021: 0; 2022: 0; 2023: 0; 2024: 2; 2025: 0 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DAICMA) |
| Hectáreas de coca | ha | 2002: 59; 2003: 85; 2004: 86; 2005: 88; 2006: 13; 2007: 31; 2008: 239; 2009: 153; 2010: 0; 2011: 69; 2012: 8; 2013: 0; 2014: 3; 2015: 3,08; 2016: 0; 2017: 4,58; 2018: 6,5; 2019: 14,67; 2020: 8,72; 2021: 10,68; 2022: 17,86; 2023: 19,09 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (MinJusticia/SIMCI) |
| Índice de Incidencia del Conflicto Armado (IICA) | índice | 2017: 0,03; 2018: 0,17; 2019: 0,02; 2020: 0,05; 2021: 0,02; 2022: 0,1; 2023: 0,13 *Nota: Categoría: 2017 Medio Bajo; 2018 Alto; 2019-2021 Medio Bajo; 2022 Medio; 2023 Alto.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DNP) |
| Personas en proceso de reincorporación | personas | 2018: 25; 2019: 32; 2020: 31; 2021: 37; 2022: 34; 2023: 35; 2024: 25; 2025: 18 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (ARN) |
| Tasa de extorsión | por 100.000 hab. | 2003: 7,2; 2007: 6,6; 2008: 6,5; 2009: 6,3; 2011: 24,2; 2012: 5,9; 2015: 22,5; 2016: 11; 2017: 16,1; 2018: 10,5; 2019: 20,5; 2020: 5; 2021: 24,4; 2022: 24; 2023: 23,5; 2024: 27,7; 2025: 18,1 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| Tasa de violencia intrafamiliar | por 100.000 hab. | 2005: 13,8; 2006: 6,8; 2012: 5,9; 2013: 5,8; 2014: 68,6; 2015: 123,5; 2016: 285,7; 2017: 150,5; 2018: 110,3; 2019: 133,1; 2020: 174,7; 2021: 68,4; 2022: 210,9; 2023: 268,2; 2024: 207,6; 2025: 154,1 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |

Tasa de secuestro (por 100.000 hab.): 2003: 7,2; 2006: 27,0; 2018: 5,3 ([TerriData](https://terridata.dnp.gov.co/index-app.html#/perfiles/05893)).

**Grupos armados y hechos recientes**
- **Alerta Temprana 027-2022 de la Defensoría** (octubre de 2022): cubre Yondó, Barrancabermeja, Puerto Wilches y Simacota por el riesgo que generan los grupos armados ilegales. Ese mismo año la Defensoría rechazó un "plan pistola" del Clan del Golfo que declaraba "objetivos militares" a los alcaldes de Barrancabermeja y Yondó. El dato viene del extracto del buscador; no leí el documento de la AT. Otras alertas 2018-2026: **No verificado**.
- **1-oct-2024, vereda La Rompida:** masacre de 4 personas. El gobernador Andrés Julián Rendón la atribuyó a las disidencias FARC (frente 24) y señaló enfrentamientos entre disidencias, ELN y Clan del Golfo en la zona ([Blu Radio](https://www.bluradio.com/regiones/antioquia/disidencias-de-las-farc-son-los-responsables-de-masacre-en-yondo-gobernador-de-antioquia-rg10)).
- **Julio de 2025:** triple homicidio en la vía Yondó-Puerto Berrío ([Vanguardia, 18-jul-2025](https://www.vanguardia.com/judicial/2025/07/18/tres-personas-fueron-asesinadas-a-tiros-estos-serian-los-moviles-de-la-masacre-en-yondo/)). Julio fue el mes con más homicidios de 2025 (12).
- **24-nov-2025, barrio Gaitán:** masacre de 3 personas. El Decreto 112 de 2025 impuso toque de queda y ley seca. A esa fecha había 31 homicidios en el año, 15 más que en el mismo periodo de 2024 (~+93%). Se reportaron enfrentamientos con drones explosivos en la vereda Puerto Matilde ([Vanguardia, 25-nov-2025](https://www.vanguardia.com/entretenimiento/2025/11/25/masacre-en-yondo-decretan-toque-de-queda-y-ley-seca-tras-el-asesinato-de-tres-personas/)).
- **Febrero de 2026:** combates entre el ELN y el Clan del Golfo ("Ejército Gaitanista de Colombia") en Tamar Bajo (Remedios, en el límite con Yondó) dejaron al menos 55 desplazados en el casco urbano. Se recuperaron 5 cuerpos. El alcalde Yerson Ariza declaró que "nuestra capacidad institucional está totalmente agotada" ([Vanguardia, 24-feb-2026](https://www.vanguardia.com/santander/barrancabermeja/2026/02/24/combates-entre-el-eln-y-el-clan-del-golfo-dejan-55-desplazados-en-yondo/)).
- **Actores con presencia reportada (2024-2026):** Clan del Golfo / EGC, ELN y disidencias FARC (frente 24), según la Gobernación y la prensa citada.
- **Minas:** se registraron eventos casi todos los años entre 2002 y 2016, con un pico de 9 en 2011. Hubo 0 entre 2017 y 2023 y reaparecieron 2 eventos en 2024.

## 9. Economía

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| Valor agregado municipal (base 2015) | miles de millones COP corrientes | 2011: 974,07; 2012: 1.201,15; 2013: 1.031,2; 2014: 1.362,15; 2015: 946,4; 2016: 669,45; 2017: 817,28; 2018: 962,28; 2019: 935,77; 2020: 687,43; 2021: 1.052,86; 2022: 1.434,95; 2023: 1.236,55 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DANE Valor agregado municipal, base 2015) |
| Valor agregado per cápita | COP corrientes | 2011: 59.005.683,1; 2012: 71.200.615,2; 2013: 60.023.555,58; 2014: 77.855.125,69; 2015: 53.129.921,56; 2016: 36.775.066,25; 2017: 43.916.192,67; 2018: 50.540.133,47; 2019: 47.685.099,81; 2020: 34.437.436,27; 2021: 51.373.464,79 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DNP con DANE) |
| % actividades primarias en el VA | % | 2011: 91,69; 2012: 91,98; 2013: 88,96; 2014: 91,02; 2015: 87,06; 2016: 79,64; 2017: 81,91; 2018: 82,45; 2019: 80,93; 2020: 76,3; 2021: 76,88; 2022: 83,65; 2023: 79,13 *Nota: Actividades primarias = agro + minas y canteras (petróleo). En base 2005 (2011-2015) "explotación de minas y canteras" pesaba 80,9-90,0% del VA.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| Participación del VA municipal en el de Antioquia | % | 2011: 1,26; 2012: 1,43; 2013: 1,14; 2014: 1,4; 2015: 0,9; 2016: 0,58; 2017: 0,68; 2018: 0,75; 2019: 0,67; 2020: 0,51; 2021: 0,65; 2022: 0,75; 2023: 0,59 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| % explotación de minas y canteras en el VA (base 2005) | % | 2011: 89,98; 2012: 88,58; 2013: 89,31; 2014: 86,84; 2015: 80,91 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| Producción fiscalizada de crudo (Casabe, Casabe Sur, Peñas Blancas) | barriles por día (promedio anual) | 2014: 22.027; 2015: 21.880; 2016: 17.866; 2017: 15.893; 2018: 13.861; 2019: 13.180; 2020: 13.150; 2021: 12.335; 2022: 12.666; 2023: 12.467; 2024: 11.647; 2025: 10.599 *Nota: Suma de barriles mensuales / 365. 2026 (ene-mar) ~10.100 bpd.* | https://www.datos.gov.co/resource/fdvb-hsrf.json (ANH Producción fiscalizada de crudo; campos Casabe, Casabe Sur, Peñas Blancas - Ecopetrol) |
| Inventario bovino | cabezas | 2000: 74.100; 2001: 61.000; 2002: 74.100; 2003: 97.352; 2004: 80.243; 2005: 80.243; 2007: 87.185; 2008: 87.185; 2009: 100.055; 2010: 105.535; 2011: 93.287; 2012: 86.693; 2013: 90.132; 2014: 97.397; 2015: 99.047; 2016: 97.659; 2017: 97.419; 2018: 119.496; 2019: 120.960; 2020: 124.889; 2021: 129.414; 2022: 133.792; 2023: 136.146; 2024: 137.168; 2025: 126.743 | https://www.datos.gov.co/resource/fy9z-8zxt.json (Gobernación de Antioquia - Inventario anual de bovinos) |
| Inventario bufalino | cabezas (ciclo II de vacunación; 2026 ciclo I) | 2019: 10.634; 2020: 11.970; 2021: 11.217; 2022: 12.971; 2023: 15.625; 2024: 15.187; 2025: 13.608; 2026: 14.716 | https://www.datos.gov.co/resource/cea5-4ctf.json (FNG/ICA Inventario bovino y bufalino ciclo de vacunación) |
| Producción del primer cultivo | toneladas | 2007: 4.608; 2008: 3.029; 2009: 3.826; 2010: 2.142,2; 2011: 1.238,4; 2012: 1.629; 2013: 4.032; 2014: 7.400; 2015: 6.400; 2016: 6.992; 2017: 45.900; 2018: 44.500; 2019: 39.000; 2020: 7.560; 2021: 16.539; 2022: 17.250; 2023: 9.500; 2024: 11.700; 2025: 15.146 *Nota: Maíz 2007-2009 y 2011-2012; arroz 2010; yuca desde 2013. Palma de aceite y arroz alternan en 2º-3º lugar.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (UPRA-EVA) |
| Trabajadores cotizantes (empleo formal) | trabajadores | 2009: 209,5; 2010: 440,58; 2011: 537,92; 2012: 580,42; 2013: 695,25; 2014: 935,58; 2015: 872; 2016: 867,75 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (FILCO-MinTrabajo) |
| % ocupados formales sobre la población | % | 2010: 4,62; 2011: 5,49; 2012: 5,75; 2013: 6,7; 2014: 8,81; 2015: 7,98; 2016: 7,65 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (FILCO-MinTrabajo) |

- **Peso del petróleo:** en base 2005, la explotación de minas y canteras fue el 80,9-90,0% del valor agregado municipal entre 2011 y 2015. En base 2015, las actividades primarias (agro más minería) representan entre 76,3% (2020) y 92,0% (2012). El VA per cápita de 2021 equivalía al 291% del promedio nacional, lo que contrasta con un IPM de 46%: es una renta de enclave poco redistribuida (lectura analítica).
- **Producción de crudo** (cálculo propio, ANH): ~22.000 bpd en 2014 y ~10.600 bpd en 2025 (-52%). Yondó nació con el auge petrolero de inicios de los años cuarenta (campo Casabe), según [Mongabay](https://es.mongabay.com/2023/06/david-contra-goliat-familia-enfrenta-a-ecopetrol-por-derrame-de-petroleo-en-sus-tierras/).
- **2026, Ecopetrol-Parex:** acuerdo de colaboración por US$250 millones en los campos Casabe y Llanito. Parex recibiría el 50% de la producción (unos 14.900 bpd en conjunto) a cambio de inversión en recobro mejorado, inyección de agua y perforación de relleno. La aprobación de la SIC estaba pendiente ([Valora Analitik](https://www.valoraanalitik.com/ecopetrol-firma-nuevo-acuerdo-con-parex-para-invertir-us250-millones-en-el-magdalena-medio/); [Offshore Technology, may-2026](https://www.offshore-technology.com/news/parex-stake-ecopetrols-magdalena-basin-assets/?.tsrc=rss)).
- **Conflicto comunidad-Ecopetrol:**
  - Abril de 2023: bloqueo de una semana a Casabe por la contratación de mano de obra local. Se suspendieron contratos con 46 empresas (~1.300 trabajadores afectados) y se firmaron acuerdos sobre empleo, transporte, protección del agua y manatíes ([Blu Radio, 18-abr-2023](https://www.bluradio.com/blu360/santanderes/levantan-protesta-en-campo-casabe-de-ecopetrol-que-llevo-a-suspension-de-contratos-con-empresas-rg10)).
  - Junio de 2026: 10 días de bloqueo por la suspensión de la campaña de perforación (se socializaron 74 pozos, luego 53, y solo se perforaron 24). Más de 1.200 trabajadores quedaron en riesgo ([Blu Radio, 26-jun-2026](https://www.bluradio.com/regiones/santanderes/comunidades-protestan-contra-campo-casabe-de-ecopetrol-por-falta-de-exploracion-rg10)).
- **Derrames y pasivos:**
  - Julio de 2019: contingencia por pérdida de contención en el campo Casabe, con vertimiento denunciado al río Magdalena. La ANLA hizo una visita de verificación ([ANLA](https://www.anla.gov.co/01_anla/index.php/noticias/386-la-anla-realiza-verificacion-a-presunto-derrame-de-crudo-en-yondo-antioquia)).
  - Finca Los Naranjitos: derrame por rotura de oleoducto reportado en 2012 (1.516 m², capa de 0,6 cm). El Concepto Técnico ANLA 05556 de 2022 estimó ~2,5 ha y 24.700 m³ de suelo afectado; Ecopetrol lo catalogó como "impacto ambiental acumulativo o no resuelto" ([Mongabay, jun-2023](https://es.mongabay.com/2023/06/david-contra-goliat-familia-enfrenta-a-ecopetrol-por-derrame-de-petroleo-en-sus-tierras/)).
  - 2020: ~200 barriles derramados por fallas de Ecopetrol entre Puerto Wilches, Yondó, Barrancabermeja y El Carmen de Chucurí (CRY-GEAM, citado por PBI).
- **Ganadería y búfalos:** el hato bovino pasó de 74.100 cabezas (2000) a 137.168 (2024), con 126.743 en 2025. Los pastos crecieron de 100.000 ha (2000) a ~150.000 ha (2024); el dato de 2025 (300.000 ha) parece un error. El hato bufalino pasó de 10.634 (2019) a 15.716 (2024-I) y 14.716 (2026-I). Yondó está entre los municipios con más búfalos del país ([CONtexto Ganadero](https://www.contextoganadero.com/ganaderia-sostenible/hato-bufalino-llega-a-668-184-cabezas-y-crece-8-52-desde-2019-asi-se-consolida-el-negocio)).
- **Cultivos (UPRA-EVA):** la yuca es el primer cultivo desde 2013 (pico de 45.900 t en 2017). Le siguen palma de aceite, arroz y maíz; el cacao es el quinto desde 2019.
- **Unidades de producción agropecuaria (CNA 2014):** las UPA de más de 100 ha suman 146.324 de 169.510 ha censadas (86%), es decir, una alta concentración de la tierra ([TerriData](https://terridata.dnp.gov.co/index-app.html#/perfiles/05893)).
- **Empleo:** solo hay series de empleo formal FILCO entre 2009 y 2016. Para 2017-2026 **No encontrado**, y tampoco hay tasa de desempleo municipal (no existe GEIH municipal).
- **Pesca:** **No encontrado** en series cuantitativas (volúmenes o número de pescadores por año). Solo hay contexto cualitativo: familias pescadoras de la ciénaga de Barbacoas y acuerdos de conservación con pescadores entre 2014 y 2021 (Mongabay, 2023).
- **Regalías por año:** **No encontrado** en esta sesión. Puede consultarse el dataset ANH j7js-yk74 (liquidación por campo) y el SGR.

## 10. Ambiente y gestión del riesgo

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| Área deforestada (IDEAM) | ha | 2000: 16.485,95; 2005: 5.420,58; 2010: 13.985,51; 2012: 2.044,08; 2013: 186,84; 2014: 871,61; 2015: 965,28; 2016: 1.076,91; 2017: 981,12; 2018: 751,88 *Nota: 2000, 2005, 2010 corresponden a periodos multianuales IDEAM (1990-2000, 2000-2005, 2005-2010); 2012 = 2010-2012.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (IDEAM) |
| Área de bosque estable | ha | 2000: 55.433,48; 2005: 50.001,67; 2010: 42.946,19; 2012: 43.418,47; 2013: 42.498,23; 2014: 41.543,07; 2015: 40.644,8; 2016: 39.390,87; 2017: 37.641,29; 2018: 36.397,97 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (IDEAM) |
| Área de humedales | ha | 2016: 61.543,88; 2020: 88.267,7 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (IAvH) |
| Área en el SINAP | ha | 2017: 32.072,19; 2022: 37.758,95; 2026: 37.756,85 *Nota: Corresponde esencialmente al DRMI Ciénaga de Barbacoas (Corantioquia, 2017).* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (PNN-RUNAP) |
| Tasa de personas afectadas por desastres | por 100.000 hab. | 2005: 15.561,24; 2006: 6.076,98; 2007: 11.841,76; 2008: 10.418,82; 2009: 0; 2010: 10.285,93; 2011: 0; 2012: 0; 2013: 0; 2014: 0; 2015: 0; 2016: 2.664,25; 2017: 2.587,32; 2018: 0; 2019: 0; 2020: 0; 2021: 0; 2022: 2.282,11 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (UNGRD) |
| Eventos de inundación (UNGRD) | eventos | 2017: 8; 2018: 0; 2019: 0; 2020: 1; 2021: 0 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (UNGRD) |

- **Ciénaga de San Silvestre: no está en Yondó.** Pertenece a Barrancabermeja (Santander) y abastece de agua a unas 300.000 personas de esa ciudad. En julio de 2026 la Alcaldía de Barrancabermeja anunció acciones contra Ecopetrol por la muerte de más de 1.000 peces, atribuida a un derrame en la red de Cenit ([Asuntos Legales](https://www.asuntoslegales.com.co/actualidad/barrancabermeja-anuncia-acciones-contra-ecopetrol-por-presunta-contaminacion-4443950)).
- **Ciénagas de Yondó:**
  - Complejo de **Barbacoas**: el **DRMI Ciénaga de Barbacoas** fue declarado por Corantioquia mediante el Acuerdo 180-ACU1705-493 del 5-may-2017, con ~32.072-32.075 ha y ~3.000 ha de espejo de agua.
  - Otras ciénagas: **Chiqueros**, Totumos y Santa Clara. El corredor Puerto Nare-Puerto Berrío-Yondó (367 km²) tiene 362 ciénagas, de las cuales 263 están en Yondó ([Ramsar/Corantioquia](https://www.ramsar.org/sites/default/files/documents/library/wwd2007_rpts_colombia_corantioquia.pdf); [Mongabay, mar-2023](https://es.mongabay.com/2023/03/conservacion-bosque-humedo-magdalena-medio-colombia/)).
  - **Laguna del Miedo** (fuente del acueducto) y **La Represa**.
  - Reserva Biológica **El Silencio** (Fundación Biodiversa, desde 2012).
  - Los humedales cubren el 32,5% del territorio (2016) o el 46,6% (2020), según el IAvH vía TerriData.
- **Deforestación:** el bosque estable cayó de 55.433 ha (2000) a 36.398 ha (2018), un 34% menos. Las mayores pérdidas fueron entre 1990-2000 (16.486 ha) y 2005-2010 (13.986 ha). Desde 2013 la pérdida se mantiene entre 187 y 1.077 ha al año. Para 2019-2025 **No encontrado** en TerriData; puede consultarse el SMByC-IDEAM.
- **Inundaciones y La Niña 2010-2011:**
  - La tasa de afectados de 2010 fue de 10.286 por 100.000 hab. (~1.660 personas con la población de 2010, cálculo propio). En 2011 figura 0, lo que probablemente indica que no se reportó.
  - Yondó aparece entre los municipios afectados por el Magdalena en los reportes de la ola invernal (La FM; fecha exacta no verificada).
  - Otras tasas altas de afectados: 2005 (15.561 por 100.000) y 2007-2008 (11.842 y 10.419).
  - En 2017 la UNGRD registró 8 eventos de inundación. En 2022 hubo 2 declaratorias de calamidad pública y una tasa de 2.282 afectados por 100.000 hab.
  - Área amenazada por fenómenos hidrometeorológicos: 29,83% (2016) y 21,55% (2019).
  - Índice de riesgo ajustado por capacidades: 42,59 (2018) y 36,24 (2022). Índice de vulnerabilidad y riesgo por cambio climático (IDEAM 2017): 19,28 (amenaza 63,21; capacidad adaptativa 92,59).
  - Fuente de todo lo anterior: [TerriData](https://terridata.dnp.gov.co/index-app.html#/perfiles/05893).
- Cifras municipales de damnificados de La Niña 2010-2011 por boletín oficial: **No encontrado**.

## 11. Vivienda

| Indicador | 2005 (metodología anterior, CG2005) | 2018 (nueva metodología DANE, CNPV 2018) | Fuente (URL) |
|---|---|---|---|
| Déficit cuantitativo, % hogares, total | 8,21 | **37,82** (2.066 de 5.463 hogares) | https://terridata.dnp.gov.co/index-app.html#/perfiles/05893 ; https://www.dane.gov.co/files/investigaciones/deficit-habitacional/deficit-hab-2020-anexo-nueva-metodologia.xlsx |
| Déficit cualitativo, % hogares, total | 57,80 | **24,11** (1.317 hogares) | idem |
| Déficit habitacional total | s.d. | 61,93 (3.383 hogares) | DANE anexo 2018 |
| Déficit cuantitativo cabecera / rural (CP y disperso) | s.d. | 31,32 / 45,72 | DANE anexo 2018 (hoja Clases Municipios) |
| Déficit cualitativo cabecera / rural | s.d. | 14,84 / 35,38 | idem |
| Antioquia: cuantitativo / cualitativo | 6,60 / 19,88 (TerriData) | 6,59 / 22,08 (verificado en el anexo DANE, hoja Total Departamentos) | https://terridata.dnp.gov.co/index-app.html#/perfiles/05000 ; anexo DANE 2018 |
| Colombia: cuantitativo / cualitativo | 12,37 / 23,84 | 9,81 / 26,78 | TerriData Colombia |

- **Ruptura metodológica:** la metodología de 2018 clasifica en déficit **cuantitativo** a las viviendas con materiales de pared precarios, como madera burda o tabla. En Yondó, 1.997 hogares tienen carencia por material de paredes, lo que explica el salto aparente de 8% a 38%. Las cifras de 2005 y 2018 **no son comparables**.
- Otras carencias de 2018 (número de hogares): hacinamiento mitigable 1.170; alcantarillado 1.066; material de pisos 1.032; recolección de basuras 836; agua para cocinar 620; cocina 273; energía 185.
- Déficit municipal anual posterior a 2018: **No encontrado**. El DANE solo publica series anuales departamentales a partir de la GEIH.

## 12. Energía eléctrica y gas

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| Cobertura de energía rural (ICEE UPME) | % | 2011: 84,16; 2012: 69,04; 2013: 74,3; 2014: 86,49; 2015: 96,78; 2016: 83,91; 2018: 80,59; 2019: 100; 2020: 100; 2021: 100; 2022: 100; 2023: 94,68; 2024: 95,55 *Nota: Serie volátil por cambios de denominador (viviendas proyectadas). 2017 sin dato.* | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (UPME - Índice de Cobertura de Energía Eléctrica) |
| Cobertura de energía total (UPME/IPSE) | % | 2019: 100; 2020: 100; 2021: 100; 2022: 100; 2023: 97,58; 2024: 98,06 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (UPME/IPSE) |
| Cobertura de energía urbana (UPME/IPSE) | % | 2019: 100; 2020: 100; 2021: 100; 2022: 100; 2023: 99,86; 2024: 100 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (UPME/IPSE) |
| Cobertura de energía por censo (% viviendas) | % viviendas | 2005: 62,7; 2018: 96,53 *Nota: 2005: % viviendas con conexión (Boletín Censo General 2005). 2018: CNPV (urbana 98,93; rural 93,60).* | https://www.dane.gov.co/files/censo2005/perfiles/antioquia/yondo.pdf ; https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |
| Cobertura de gas natural por censo (% viviendas) | % viviendas | 2005: 51,5; 2018: 43,48 *Nota: 2018: urbana 65,03; rural 17,33.* | https://www.dane.gov.co/files/censo2005/perfiles/antioquia/yondo.pdf ; https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip |

- En 2005 solo el 62,7% de las viviendas tenía conexión eléctrica. En 2018 eran el 96,5% (urbano 98,9%; rural 93,6%). El ICEE de UPME da 100% total en 2019-2022 y 98,06% en 2024, con rural en 95,55%.
- El gas natural bajó de 51,5% de viviendas (2005) a 43,5% (2018). Esta caída puede deberse a una diferencia de denominadores o a la expansión de viviendas rurales sin red; no lo verifiqué. Usuarios de gas por año (SUI): **No encontrado**.
- Operador de red (EPM u otro): **No verificado**.

## Anexo A. Desempeño institucional (MDM-DNP)

| Indicador | Unidad | Serie (año: valor) | Fuente (URL) |
|---|---|---|---|
| MDM, puntaje total | puntos | 2016: 54,71; 2017: 45,5; 2018: 45,58; 2019: 60,7; 2020: 54,17; 2021: 62,52; 2022: 61,17; 2023: 58,27; 2024: 64,03 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DNP-MDM) |
| MDM, componente de resultados | puntos | 2016: 63,11; 2017: 62,92; 2018: 62,21; 2019: 63,48; 2020: 63,43; 2021: 61,75; 2022: 63,92; 2023: 65,7; 2024: 70,56 | https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData05893.txt.zip (DNP-MDM) |

Subcomponentes de resultados MDM (TerriData):
- Educación: 42,38 (2016) → 64,57 (2024).
- Salud: 78,02 → 81,56.
- Servicios públicos: 39,99 → 53,70.
- Seguridad: 92,06 → 82,39.

## Anexo B. Consolidado de "No encontrado" o no verificado

- Población por corregimiento o vereda (proyecciones). Solo hay totales por cabecera y resto, y los censados de CNPV 2018 por centro poblado y rural disperso.
- IPM municipal intercensal (años distintos de 2005 y 2018).
- Proyectos de agua potable inconclusos específicos. Estado posterior a 2020 de la optimización del acueducto y de una PTAR.
- Saber 11 de 2023, 2024 y 2025 por municipio.
- Sedes de IES o matrícula de educación superior en el municipio (TerriData = 0%).
- Nombre y nivel de la red hospitalaria (E.S.E.) del municipio.
- Penetración de internet móvil por municipio.
- Estado del puente Guillermo Gaviria Correa después de junio de 2026. Avance de obra de La Ye-Yondó tras la licitación.
- Kilómetros totales de vías terciarias y porcentaje pavimentado.
- Lista completa de alertas tempranas de la Defensoría 2018-2026 (solo se identificó la AT 027-2022).
- Regalías por año. Desempleo municipal. Empleo formal posterior a 2016.
- Series cuantitativas de pesca (desembarcos, pescadores).
- Deforestación 2019-2025 municipal.
- Damnificados de La Niña 2010-2011 por boletín oficial municipal.
- Déficit de vivienda municipal posterior a 2018. Usuarios de gas natural por año. Operador de energía.

## Anexo C. Archivos crudos descargados (`datos crudos de trabajo (no incluidos en el repositorio; se regeneran desde las URL citadas)`)

- `terridata/TerriData05893.txt` (Yondó), `TerriData05000.txt` (Antioquia), `TerriData01001.txt` (Colombia): archivos planos completos de TerriData. `td_index.txt` es el índice de indicadores de Yondó.
- `dane/`: proyecciones municipales por área (1995-2004, 2005-2017 y 2018-2042, base CNPV 2018), `ProyeccionMunicipios2005_2020.xls` (base 2005), `deficit-hab-2020-anexo-nueva-metodologia.xlsx`, `yondo.pdf` (boletín del Censo 2005) y `cnpv2018_yondo_censada.txt`.
- Archivos de datos.gov.co:
  - `ins_irca_yondo.json` (IRCA INS).
  - `mintic_internet_fijo_yondo_raw.json` (accesos internet fijo) y `mintic_centros_digitales_yondo.json`.
  - `mindefensa_homicidios_yondo_anual.json` e `inml_homicidios_yondo.json` (homicidios).
  - `ruv_victimas_anual_yondo_corte20260930.json` y `ruv_desplazamiento_yondo_corte20260930.json` (UARIV).
  - `anh_produccion_crudo_yondo.json` (ANH).
  - `men_estadisticas_yondo.json`, `men_establecimientos_yondo.json` e `icfes_saber11_yondo.json` (educación).
  - `ins_sivigila_yondo_eventos.json` y `gobant_mort_desnutricion_menores5_yondo.json` (salud).
  - `fng_inventario_bovino_bufalino_yondo.json` y `gobant_inventario_bovinos_yondo.json` (ganadería).
  - `divipola_yondo.json` (centros poblados).
- `sspd/sspd_evaluacion_integral_aguas_aseo_yondo.pdf` y `eval.txt`: evaluación integral de la Superservicios.
- `gob_antioquia/`: anuarios 2012 y 2014 (población SISBEN, veredas) y `estabilizacion.pdf` (licitación de vías 2025-2026).

Series temporales en formato máquina: `data/fuentes/series_sociales.json` (138 series).
