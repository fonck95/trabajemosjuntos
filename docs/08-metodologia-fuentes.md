# 08 · Metodología, fuentes y limitaciones

## 1. Principios

1. **Toda cifra tiene fuente.** Cuando un dato no se encontró, se dice "sin dato verificable" y no se rellena.
2. **Tres niveles de certeza**, marcados en los documentos y en `data/`:
   - **Verificado**: tomado directamente de una fuente oficial (SECOP, DNP, DANE, MinSalud, ICFES, INS, MinTIC), con enlace.
   - **Estimado**: calculado a partir de datos oficiales con un método explícito (por ejemplo, la clasificación de contratos o la coincidencia estudio → obra).
   - **Supuesto**: valor de diseño o de mercado usado para prefactibilidad (consumos por tipología, precios unitarios). Se reemplaza con medición o cotización antes de contratar.
3. **Indicios, no acusaciones.** Los patrones de contratación señalan dónde revisar. No se nombra a personas naturales contratistas. Cuando se mencionan hallazgos de órganos de control, se indica si son hallazgos, investigaciones, sanciones o fallos.
4. **Reproducible.** Los scripts de `scripts/` descargan los datos y regeneran todas las tablas.

## 2. Fuentes principales

| Fuente | Qué se usó | Acceso |
|---|---|---|
| SECOP I y II (Colombia Compra Eficiente) | 14.301 registros de contratos de la alcaldía, la E.S.E., Aguas y Aseo y otras entidades de Yondó, 2007–2026 | datos.gov.co, conjunto `rpmr-utcd` (SECOP Integrado) y `jbjy-vk9h` (SECOP II) |
| DNP – TerriData, Medición de Desempeño Municipal, Índice de Desempeño Fiscal | Desempeño fiscal e integral por año | terridata.dnp.gov.co |
| DNP – SGR / MapaRegalías / SICODIS | Asignaciones y proyectos de regalías | datos.gov.co, maparegalias.sgr.gov.co, sicodis.dnp.gov.co |
| CHIP / CUIPO (Contaduría y Contraloría) | Ejecución presupuestal municipal | datos.gov.co |
| DANE | Censos 2005 y 2018, proyecciones de población, NBI, IPM | dane.gov.co |
| ICFES | Resultados Saber 11 por municipio | datos.gov.co |
| INS – SIVICAP | Índice de riesgo de la calidad del agua (IRCA) | datos.gov.co |
| MinSalud – REPS, SIHO, categorización de riesgo de las E.S.E. | Perfil y finanzas del hospital | minsalud.gov.co |
| MinTIC – ColombiaTIC | Penetración de internet, Centros Digitales | colombiatic.mintic.gov.co |
| NASA POWER / Global Solar Atlas / IDEAM | Recurso solar | power.larc.nasa.gov |
| Prensa regional y nacional, informes de órganos de control | Hechos de cada periodo, alertas | Citados en cada documento |

Las referencias completas de cada dato están en `data/fuentes/` y al pie de cada documento.

## 3. Método de clasificación de contratos (SECOP)

`scripts/secop_analisis.py` asigna cada contrato a una de siete categorías con estas reglas, en orden:

1. **Interventoría**: tipo "Interventoría" o el objeto empieza por "Interventoría".
2. **Obra**: tipo "Obra" (excluye "mano de obra").
3. **Estudios / consultoría**: tipo "Consultoría" o un objeto con estudios, diseños, formulación de planes, MGA, factibilidad, EOT, plan parcial o levantamiento topográfico, que no sea una OPS de apoyo.
4. **OPS / apoyo a la gestión**: prestación de servicios a persona natural o por contratación directa con objeto de prestación, apoyo, asesoría o acompañamiento.
5. **Convenios / interadministrativos**: objeto con convenio, interadministrativo, aunar esfuerzos o administración delegada; contratos del Decreto 092 de 2017; o contratista que es una entidad pública (empresa de servicios públicos, Aguas y Aseo, E.S.E., EDU).
6. **Obra (por objeto)**: el objeto empieza por construcción, obra, pavimentación, rehabilitación o mejoramiento de vías.
7. **Suministro / compraventa** y **Otros servicios** para el resto.

**Coincidencia estudio → obra.** Para cada estudio se buscan obras de la alcaldía firmadas el mismo año o después, y se calcula la similitud de Jaccard entre las palabras significativas de ambos objetos (sin palabras vacías ni genéricas como "construcción" o "municipio"). Una similitud ≥ 0,30 cuenta como obra relacionada probable. El método produce falsos negativos (obras ejecutadas por otra entidad) y algunos falsos positivos; por eso se presenta como agenda de verificación.

## 4. Normalización del marco comparativo (0–100)

Cada indicador del marco comparativo (`docs/02`, vista "Seis gobiernos") se lleva a una escala donde 100 es el mejor valor posible o la meta nacional, y se promedia dentro de cada periodo de gobierno con los años disponibles. Los detalles por indicador están en `data/periodos.json` (campo `metodo`). Una celda sin datos se muestra hueca y no cuenta como cero.

## 5. Limitaciones conocidas

- **SECOP antes de 2008 es casi vacío** para Yondó (41 contratos en 2007). El periodo 2004–2007 se reconstruye con indicadores del DNP, DANE y prensa, no con contratación.
- **La E.S.E. publica poco en SECOP** (ningún contrato en 2008–2011 ni en 2016–2019). Su análisis depende de SIHO y de los informes de la Contraloría.
- **Valores corrientes.** Los montos de contratación no están deflactados; comparar periodos en pesos constantes reduce el peso relativo de los primeros años.
- **Clasificación automática.** Las categorías dependen de cómo cada entidad redactó el objeto y eligió el tipo de contrato. Los errores de registro de SECOP se heredan.
- **Proyectos en prefactibilidad.** Consumos, precios y montos de financiación son estimaciones con rango; cambian con medición, cotizaciones y convocatorias.
