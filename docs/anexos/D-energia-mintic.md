# D. Energía y MinTIC: microrred y domótica municipal para Yondó (Antioquia)

> **Anexo de investigación.** Informe de trabajo con cada dato y su fuente. Marcas de certeza: verificado, derivado o calculado, inferencia y por verificar. Donde dice que "se agotó el cupo de búsquedas", el punto quedó abierto y está listado en la sección final de pendientes.


**Alcance.** Este documento reúne la base de evidencia y una propuesta preliminar de dimensionamiento para una microrred municipal con gestión inteligente IoT. Debe cubrir alcaldía, hospital, colegios, biblioteca, policía y bomberos, alumbrado público y acueducto/bombeo de Yondó, en el Magdalena Medio antioqueño, frente a Barrancabermeja. El componente digital se apoya en MinTIC.

**Fecha de corte de la investigación:** 20-oct-2026.

**Convenciones de confianza** (se usan en todas las tablas):

| Marca | Significado |
|---|---|
| **V** | Verificado en fuente primaria u oficial: documento leído (PDF, dataset o página institucional). |
| **V2** | Verificado en fuente secundaria (prensa, blog de instalador o resumen de buscador). Úsese con cautela. |
| **C** | Cálculo propio a partir de datos V/V2. La fórmula se indica. |
| **S** | Supuesto del autor. **No es un dato.** Debe reemplazarse por facturas, auditorías o cotizaciones. |
| **P** | Pendiente: no se encontró o no se pudo verificar. |

> Nota metodológica: se agotó el cupo de búsquedas web de la sesión antes de cerrar algunos puntos (costos locales de IoT/EMS, intensidad energética del acueducto, operador del alumbrado). Esos puntos quedan como **S** o **P**.

---

## 0. Hallazgos clave (resumen)

1. **El operador de red es EPM.** Yondó se conectó al SIN mediante la nueva **subestación Yondó**: 10 MVA, 34,5/13,2 kV. La alimentan **dos circuitos exclusivos de 34,5 kV desde la subestación Barranca (Barrancabermeja, Santander)**, con 32 km de red y $15.509 millones, y entró en operación en 2021. El municipio depende, por tanto, de un único nodo aguas arriba en Santander. Ese es el argumento técnico central para una microrred con capacidad de isla en cargas críticas.
2. **Calidad.** EPM registró en 2025 un SAIDI de 9,14 h y un SAIFI de 5,68 en toda la empresa, con un promedio nacional de 21 h y 14,2. No hay dato público específico de Yondó (P). El 22-ago-2026 hubo un corte programado de 9:00 a 16:00 en veredas rurales de Yondó.
3. **Tarifa EPM a octubre de 2026** (mercado regulado Antioquia, nivel 1, activos EPM): **oficial 991,29 COP/kWh; comercial 1.189,54; ESPD (acueducto) 1.090,41.**
4. **Recurso solar alto y estable.** Global Solar Atlas da GHI = 2.012,5 kWh/m²·año (5,51 kWh/m²·día) y PVOUT = 1.602 kWh/kWp·año. NASA POWER (2001–2025) da GHI = 5,08 kWh/m²·día. La variación mensual es baja: de 4,56 en noviembre a 5,54 en febrero (NASA).
5. **Hay un análogo regional verificado.** El **Hospital San Antonio de Padua de Simití** (Bolívar, misma subregión PDET Sur de Bolívar que Yondó) tiene **230 kWp** y genera 268.142 kWh/año, con un consumo total cubierto de 300.794 kWh/año. La inversión fue de **$3.152 millones** (FENOGE, jul-2025).
6. **Financiación.** Yondó es **PDET (Sur de Bolívar)** y figura entre los **209 municipios beneficiarios del Incentivo a la Producción (SGR)**. En la Convocatoria IP 2025 presentó solo un proyecto de **sistemas aislados rurales**, que quedó en la lista de **"no cumplen"**. La línea "Territorios energéticos" de esa convocatoria financia exactamente FNCER en instituciones educativas, acueductos, centros de salud y centros administrativos. Es una oportunidad no aprovechada.
7. **MinTIC.** La guía FUTIC de cofinanciación de Ciudades y Territorios Inteligentes cubre dispositivos IoT, SaaS/IaaS/PaaS, equipo, capacitación e ingeniería de detalle. No cubre plataformas propias. La convocatoria **Máxima Velocidad 2026** (abierta desde el 21-abr-2026) incluye el reto "territorios inteligentes". La conectividad fija de Yondó es baja: **1.062 accesos en 2023-T3, ≈4,9 por 100 habitantes (C)**, frente a 26,6 en Antioquia (2026-T2) y 19 en el país (2025-T4).
8. **Ecopetrol.** La **Granja Solar La Iguana** (26 MWp, 42,2 GWh/año) está **en Yondó** y se inauguró el 4-dic-2025. Abastece la refinería y los campos Casabe y Llanito. Según un trabajo académico basado en datos de Ecopetrol (2021), el gas asociado de Casabe no se comercializa. Ecopetrol es el mayor contribuyente de Obras por Impuestos y ya apoya comunidades energéticas en el Magdalena Medio.
9. **Propuesta preliminar (S/C).** Son **≈400 kWp FV conectados a red** en 10 fronteras, cada una de ≤100 kW, más **≈290 kWh de baterías LFP** en sedes críticas y 10 sedes rurales aisladas, con EMS/SCADA, LoRaWAN y BMS. El CAPEX total indicativo es **≈$4.570 millones (≈USD 1,44 M)**. El ahorro estimado es **≈$548 millones/año** a tarifas de octubre de 2026. El repago simple del componente FV+BESS es de **≈3,5 años**. Todas estas cifras dependen de supuestos que deben validarse con las facturas EPM de cada NIU.

---

## 1. Red eléctrica, operador, calidad, tarifas y alumbrado

### 1.1 Operador de red e infraestructura

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| Operador de red / comercializador incumbente | **EPM** (Empresas Públicas de Medellín E.S.P.) | V | https://www.epm.com.co/clientesyusuarios/noticias-y-novedades/epm-pone-en-marcha-solucion-de-energia-electrica-en-yondo--que-b/ |
| Subestación Yondó | Nueva subestación con edificio de control; **transformador 10 MVA, 34,5/13,2 kV** | V | ídem (nota EPM, 7-jul-2020) |
| Alimentación | **Dos circuitos exclusivos de 34,5 kV desde la subestación Barranca (Barrancabermeja, Santander)** hasta Yondó, que lo conectan al SIN | V | ídem |
| Beneficiarios declarados | >19.000 habitantes | V | ídem |
| Puesta en operación | Interconexión Yondó–Barrancabermeja en operación en 2021; **32 km de redes; inversión $15.509 millones; 7.000 usuarios** | V | https://www.epm.com.co/clientesyusuarios/noticias-y-novedades/en-2021-epm-entro-en-operacion-importantes-proyectos-de-infraestructura-de-servicios-publicos/ |
| Cobertura de EPM | 124 municipios de Antioquia y El Carmen de Atrato (Chocó) | V2 | https://lanotaeconomica.com.co/movidas-empresarial/epm-sigue-mejorando-la-calidad-en-la-prestacion-del-servicio-de-energia-electrica-para-la-comunidad |
| Implicación | El suministro depende de **un nodo aguas arriba en Santander** (S/E Barranca, en el área de ESSA o del STR). Es el argumento para operar en isla las cargas críticas. | C (inferencia) | — |
| Límite de penetración de GD/AGPE | En nivel de tensión 1, la suma de la potencia de GD y AGPE que entregan energía debe ser **≤50 % de la capacidad nominal del circuito, transformador o subestación** (art. 6, CREG 174/2021) | V | https://gestornormativo.creg.gov.co/gestor/entorno/docs/resolucion_creg_0174_2021.htm |

### 1.2 Calidad del servicio (SAIDI/SAIFI)

| Indicador | Valor | Conf. | Fuente |
|---|---|---|---|
| EPM 2024: SAIDI | **10,68 h/usuario-año** (−14 % vs 2023; meta regulatoria 10,89) | V2 | https://lanotaeconomica.com.co/movidas-empresarial/epm-sigue-mejorando-la-calidad-en-la-prestacion-del-servicio-de-energia-electrica-para-la-comunidad |
| EPM 2024: SAIFI | **6,56** veces (la tabla de la misma nota dice 6,55; meta 9,00) | V2 | ídem |
| EPM 2025: SAIDI / SAIFI | **9,14 h / 5,68 veces** | V2 (El Tiempo cita a XM) | https://www.eltiempo.com/economia/sectores/cuanto-tiempo-pasan-los-colombianos-sin-luz-al-ano-el-ranking-de-las-empresas-con-mas-cortes-de-energia-3561936 |
| ESSA 2025 (S/E Barranca aguas arriba): SAIDI / SAIFI | **17,19 h / 8,08 veces** | V2 | ídem |
| Promedio nacional 2024 → 2025 | SAIDI 23 → **21 h**; SAIFI 14,8 → **14,2** | V2 | ídem |
| SAIDI/SAIFI específico de Yondó o del circuito | No publicado en las fuentes halladas. Pedir a EPM los indicadores DIU/FIU por circuito (CREG 015/2018) | P | — |
| Metas de calidad de la CREG | Reducción del 8 % anual sobre los indicadores de referencia de cada OR | V2 | https://gestornormativo.creg.gov.co/gestor/entorno/docs/originales/Circular_CREG_254_2026/Anexo%202.%20Documento%20Soporte%20metas%20calidad.pdf |

### 1.3 Cortes recientes en Yondó

| Evento | Detalle | Conf. | Fuente |
|---|---|---|---|
| 22-ago-2026 (programado, EPM) | 9:00–16:00, **veredas Cuatro Bocas, El Campo Cimitarra y El Bagre** | V2 | https://newsroom.rcnradio.com/colombia/cortes-de-agua-y-luz-en-medellin-y-bello-este-22-de-agosto-de-2026-horarios-y-sectores-afectados |
| Avisos de mantenimiento de subtransmisión (EPM) | Yondó aparece en avisos de interrupciones programadas (p. ej., oct-2023) | V2 | https://epm.com.co/clientesyusuarios/interrupciones-del-servicio/energia.html |
| Cortes no programados en el casco urbano (2025-2026) | No se encontraron reportes de prensa | P | — |

### 1.4 Tarifas EPM, octubre de 2026 (mercado regulado Antioquia), COP/kWh

Fuente: publicación oficial de tarifas de EPM, octubre de 2026 (V). PDF: https://www.epm.com.co/content/dam/epm/clientes-y-usuarios/energia/tarifas-energia/Tarifas%202026/10.PublicacionTarifasOctubre162026_ANT_OM.pdf

| Clase / nivel | Propiedad EPM | Propiedad compartida | Propiedad cliente |
|---|---|---|---|
| **Oficial y exentos de contribución, NT1** | **991,29** | 959,51 | 927,73 |
| **Industrial y comercial, NT1** | **1.189,54** | 1.151,41 | 1.113,28 |
| **ESPD (acueducto y alcantarillado, actividades operativas), NT1** | **1.090,41** | 1.055,46 | 1.020,51 |
| Oficial horaria NT1: punta / fuera de punta | 980,79 / 992,37 | — | — |
| Oficial NT2: punta / fuera de punta | 799,64 / 812,16 | — | — |
| Oficial NT3: punta / fuera de punta | 697,23 / 709,80 | — | — |
| Cargo fijo NT1 (Cf) | 9.611 $/factura | — | — |

Componentes del CU, NT1 propiedad EPM (991,29):

| G | T (STN) | D (SDL) | Cv | PR | R |
|---|---|---|---|---|---|
| 403,50 | 49,64 | 297,88 | 114,28 | 75,48 | 50,50 |

Franjas horarias EPM: punta de 9:00 a 12:00 y de 18:00 a 21:00.

| Dato complementario | Valor | Conf. | Fuente |
|---|---|---|---|
| Precio de bolsa 2026 | EPM afirma que en 2026 la bolsa tocó mínimos históricos, cerca de $100/kWh | V2 | https://www.valoraanalitik.com/epm-critica-cambios-de-petro-a-formula-de-las-tarifas-de-energia/ |
| COT (opción tarifaria) octubre de 2026 | N1 40,30; N2 18,53; N3 25,05 $/kWh | V2 (página de tarifas EPM) | https://www.epm.com.co/clientesyusuarios/energia/tarifas-energia/ |

**Valor económico de excedentes AGPE con tarifas de octubre de 2026 (C).** Aplica las reglas del art. 25 de la CREG 174, modificado por la CREG 101 072 de 2025 (ver §4.2):

| Caso | Cargo que paga el kWh permutado | Valor neto del kWh acreditado |
|---|---|---|
| AGPE ≤100 kW | Cv = 114,28 | **877 COP/kWh** |
| AGPE >100 kW | T+D+Cv+PR+R = 587,78 | **≈404 COP/kWh** |

Conclusión de diseño: conviene que cada frontera quede en **≤100 kW**, o diseñar para autoconsumo casi total.

### 1.5 Zonas rurales sin servicio y ZNI

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| Proyecto de Yondó en la Convocatoria IP 2025 (SGR) | "Construcción de sistemas aislados de energía solar fotovoltaica en zona rural dispersa del municipio de Yondó". Tipología: "soluciones individuales y microrredes en ZNI, proyectos ≥50 usuarios". Implica **≥50 viviendas rurales sin red** (inferencia). | V (listado) / C | https://www.minenergia.gov.co/documents/14988/proyectos-postulados-convocatoriaip-2025.pdf |
| Resultado | El proyecto figura en el **Anexo 3, "Listado de proyectos que no cumplen"** | V | https://www.minenergia.gov.co/documents/15326/informe-final-lista-elegibles-convocatoriaip-2025.pdf |
| ICEE Antioquia 2024 (UPME) | **100 %**. La UPME advierte "excedentes de viviendas con servicio", es decir, desajuste entre proyecciones DANE y reportes. Contrasta con la evidencia de hogares sin red en Yondó. | V | https://docs.upme.gov.co/SIMEC/Energia%20Electrica/Documents/Informes_cobertura/Boletin_ICEE_2024.pdf |
| ICEE nacional 2024 | 93,12 % (urbano 98,71 %, rural 75,92 %); ≈1.326.971 viviendas sin servicio | V | ídem |
| Cobertura rural de Antioquia (Plan Departamental) | Línea base 98,62 %; logro dic-2024 de 98,95 %; meta 99,52 % | V2 | https://www.antioquia.gov.co/Documentos_informes_de_gestion/2024/154.%20JIMMY%20COLLAZOS%20FRANCO%20-%20SERVICIOS%20P%C3%9ABLICOS%20%28E%29.pdf |
| ICEE municipal de Yondó / número de viviendas sin servicio | No extraído: el anexo municipal del boletín ICEE 2024 no está en el PDF | P | — |
| ¿Yondó es ZNI? | No. El municipio está interconectado (SIN vía Barranca). Las viviendas dispersas sin red se atienden con soluciones aisladas. | C | — |
| Centros Digitales rurales con "tipo de energía: EN VERIFICACIÓN" | Las 4 sedes del corregimiento San Miguel del Tigre (ver §5.4). Son candidatas a SSFV aislado o híbrido. | V (dataset) | https://www.datos.gov.co/resource/fybg-535s.json |

### 1.6 Alumbrado público

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| Quién opera el AP en Yondó | **No verificado.** SECOP II del Municipio de Yondó (1.292 contratos) no registra contratos de AP. Solo aparece un proceso de **alumbrado navideño** (nov-2022, $840 millones). Esto sugiere que el AP se gestiona por contrato con EPM, por SECOP I o por concesión. | P / V (dataset) | https://www.datos.gov.co/resource/jbjy-vk9h.json y https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.3588640 |
| Oferta de EPM a municipios | EPM presta servicios de AP mediante contratos interadministrativos y concesión | V2 | https://epm.com.co/clientesyusuarios/energia/corporativo/alumbrado-publico.html |
| Marco del impuesto de AP | Ley 1819 de 2016 (arts. 349-353) y **Decreto 943 de 2018**. Opción de sobretasa al predial con tope de 1 por mil del avalúo. Recaudo con destinación exclusiva al servicio. | V2 | https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=86680 |
| Responsabilidad del municipio | El municipio es responsable de la prestación y el mantenimiento. La energía la suministra el comercializador con el que acuerde (CREG 043/1995). | V2 | https://gestornormativo.creg.gov.co/Publicac.nsf/1c09d18d2d5ffb5b05256eee00709c02/e1282426139cb4570525785a007a647c/$FILE/Crg43-95.doc |
| Reglamento técnico | **RETILAP: Res. MinEnergía 40150 de 2024**, ajustada por la Res. 40318 de 2025 (transitorio de instalaciones hasta el 11-dic-2025) | V2 | https://gestornormativo.creg.gov.co/gestor/entorno/docs/resolucion_minminas_40318_2025.htm |
| Ahorros de referencia por LED | Findeter/BID: −50 % de energía y −50 a 60 % de O&M. Bogotá: −48 % de consumo. | V2 | https://www.valoraanalitik.com/findeter-y-el-bid-modernizar-n-alumbrados-p-blicos-de-colombia/ ; https://bogota.gov.co/mi-ciudad/habitat/en-2022-bogota-deja-atras-el-alumbrado-publico-con-luz-amarilla |
| Acuerdo municipal y tarifa del impuesto de AP en Yondó; inventario de luminarias | No encontrado | P | — |

---

## 2. Recurso solar y rendimiento esperado

### 2.1 Irradiación

| Fuente | Parámetro | Valor | Conf. | URL |
|---|---|---|---|---|
| **NASA POWER** (climatología 2001–2025, MERRA-2/CERES SYN1deg; punto 7,0°N, −73,91°) | GHI all-sky anual | **5,08 kWh/m²·día** (≈1.853 kWh/m²·año, C) | V | https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=ALLSKY_SFC_SW_DWN&community=RE&longitude=-73.91&latitude=7.0&format=JSON |
| NASA POWER | GHI mensual (kWh/m²·día), ene a dic | 5,36 · 5,54 · 5,08 · 4,80 · 4,92 · 5,12 · 5,29 · 5,34 · 5,23 · 4,82 · **4,56 (mín., nov)** · 4,89 | V | ídem |
| NASA POWER | Cielo despejado (clear-sky) anual | 6,84 kWh/m²·día | V | ídem |
| NASA POWER | T2M anual | 25,8 °C. La celda incluye relieve (elev. 391 m), así que subestima el calor del valle. | V | ídem |
| **Global Solar Atlas** (Solargis v2.2.68; datos hasta 2025; punto 7,005°N, −73,912°) | GHI anual | **2.012,5 kWh/m²·año = 5,51 kWh/m²·día** | V | https://api.globalsolaratlas.info/data/lta?loc=7.005,-73.912 (visor: https://globalsolaratlas.info/map?c=7.005,-73.912,11) |
| Global Solar Atlas | DNI / DIF anual | 1.444,7 / 931,9 kWh/m²·año (alta fracción difusa, 46 %) | V | ídem |
| Global Solar Atlas | Inclinación óptima / elevación / T media | 9° / 75 m / 26,3 °C | V | ídem |
| Global Solar Atlas | **PVOUT** (sistema de referencia, inclinación óptima) | **1.602 kWh/kWp·año** (4,39 kWh/kWp·día). Mensual de 124,9 (abr/jun) a 146,3 (ene). | V | ídem |
| IDEAM, Atlas de radiación solar (2015/2018) | Valor puntual Yondó/Barrancabermeja | No extraído (requiere el visor interactivo) | P | http://atlas.ideam.gov.co/visorAtlasRadiacion.html |
| Estudio local (UNAD, Barrancabermeja) | ≈5,31 kWh/(m²·día) según Solarius PV | V2 | https://hemeroteca.unad.edu.co/index.php/agricolae/article/download/2785/3045 |

### 2.2 Rendimiento específico esperado (kWh/kWp·año)

Rendimientos reportados por proyectos FENOGE (C = generación anual reportada / kWp):

| Proyecto (clima) | kWp | kWh/año | kWh/kWp·año | Fuente |
|---|---|---|---|---|
| Hospital Simití, Bolívar (cálido, Magdalena Medio) | 230 | 268.142 | **1.166** | https://fenoge.gov.co/documentos-noticias/2025/Comunicado_entrega_de_hospital_publico_autosostenible_en_Simiti_Bolivar.pdf |
| 10 IE en Villavicencio (cálido) | ≈112 | ≈135.000 | **1.205** | https://fenoge.gov.co/proyectos/energia-solar-en-colegios-publicos-en-villavicencio/ |
| Hospital Silvania, Cundinamarca | 55,2 | 67.999 | 1.232 | https://fenoge.gov.co/documentos-noticias/2025/Boletin_Silvania_2207.pdf |
| Hospital Cunday, Tolima (cálido) | 43,10 | 65.943 | 1.530 | https://fenoge.gov.co/documentos-noticias/2025/BoletinCunday14062025.pdf |

**Valor de diseño adoptado (S/C):** **1.346 kWh/kWp·año (≈112 kWh/kWp·mes)**, igual a PVOUT GSA × 0,84. El factor 0,84 representa pérdidas adicionales de techo plano o de baja inclinación, temperatura de celda elevada, suciedad (polvo y humedad del valle) y disponibilidad. Queda dentro del rango observado (1.166–1.530) y es prudente para un P50. Debe simularse con PVsyst o SAM por sitio.

---

## 3. Costos de referencia (2024-2026)

TRM de referencia: **$3.170,46/USD** (16-oct-2026; V2): https://www.portafolio.co/economia/finanzas/precio-del-dolar-hoy-en-colombia-asi-cotiza-la-divisa-este-16-de-octubre-tras-perder-casi-504569

### 3.1 FV, baterías, inversores, gestión y IoT

| Ítem | Valor | Conf. | Fuente |
|---|---|---|---|
| FV instalado en Colombia, 2026 (todos los tamaños) | **$2,0–3,5 M COP/kWp** típico; hasta $5,2 M/kWp en sistemas pequeños con equipos de gama alta. Industrial de 30–100 kWp desde $90 M. | V2 (instalador, 17-ago-2026) | https://integracionsolar.co/cuanto-cuesta-instalar-paneles-solares-en-colombia-en-2026/ |
| FV comercial a mayor escala | **$2,8–4,0 M COP/kWp**, con equipos, montaje y legalización | V2 (resumen de buscador de blogs 2026) | https://www.voltiva.com.co/blog/cuanto-cuesta-instalar-paneles-solares-colombia ; https://erco.energy/co/articles/costos-instalacion-solar-empresas-colombia |
| Desglose típico | Paneles ≈40 % (1,2–1,8 M/kWp); inversores ≈20 % | V2 | https://erco.energy/co/articles/costos-instalacion-solar-empresas-colombia (no se pudo abrir, error 502; dato tomado del snippet) |
| Proyectos públicos "todo incluido" de FENOGE (FV + eficiencia energética + capacitación + AOM inicial) | Simití $13,7 M/kWp; Silvania $11,0 M/kWp; Cunday $16,6 M/kWp; Villavicencio $23,7 M/kWp. **No son comparables con el costo FV puro** porque incluyen recambio de aires acondicionados, LED y refrigeración. | C sobre V | fuentes §2.2 |
| AMP CCE "Sistemas FV de generación y almacenamiento" (CCE-074-AMP-2022), **precios techo** por sistema llave en mano con almacenamiento | 0,5–10 kWp: **$89,5–108 M** (oferente más bajo según región). 41–50 kWp: $411–477 M. 51–60 kWp: **$500–547 M**. Equivale a ≈$8–10 M/kWp con baterías en la banda alta. | V (catálogo v3, 22-ago-2025) | https://www.colombiacompra.gov.co/wp-content/uploads/2022/10/003.-Catalogo-Sistemas-Fotovoltaicos-Generacion-y-almacenamiento_22082025.xlsx |
| Baterías: precio de paquete estacionario (mundo, 2025) | **USD 70/kWh** (−45 % vs 2024). LFP de todos los segmentos: USD 81/kWh. | V2 (BNEF) | https://about.bnef.com/insights/clean-energy/lithium-ion-battery-pack-prices/ |
| BESS llave en mano (mundo, 2025) | **USD 117/kWh** promedio global (4 h: USD 110); China USD 73; Europa **USD 177**; EE. UU. **USD 219** | V2 (BNEF vía Energy-Storage.news) | https://www.energy-storage.news/behind-the-numbers-bnef-finds-40-year-on-year-drop-in-bess-costs/ |
| Conversión a COP (C) | USD 117 ≈ $0,37 M/kWh; 177 ≈ $0,56 M; 219 ≈ $0,69 M | C | — |
| Riesgo de precio 2026 | El carbonato de litio casi se duplicó entre dic-2025 y ene-2026, lo que presiona al alza el cátodo LFP | V2 | https://www.procurementresource.com/es/resource-center/lithium-iron-phosphate-lfp-cathode-price-trends |
| **BESS C&I pequeño instalado en Yondó** (10–200 kWh, con PCS/inversor híbrido, gabinete, protección y obra) | **$1,0–2,2 M COP/kWh; central $1,4 M/kWh** | **S** (escala pequeña, logística, importación y margen; requiere ≥3 cotizaciones) | — |
| Inversor híbrido / PCS | Incluido en la cifra BESS anterior | S | — |
| EMS/SCADA de microrred (software, servidor o nube, integración, ciberseguridad) | **$300–600 M COP** para el municipio (central $450 M) | **S** | — |
| Medidores inteligentes / analizadores de red (clase 0,5S, Modbus/DLMS) | **$2–5 M COP por punto** instalado | **S** | — |
| AMI, referencia nacional CREG | 7,4 billones para el 75 % de 15,7 M de usuarios, ≈$0,47 M/usuario residencial (C) | V2 | https://www.eltiempo.com/economia/sectores/por-que-el-plan-de-medicion-inteligente-de-energia-tiene-dificultades-602699 |
| Gateway LoRaWAN (AU915) / sensores IoT | **$3–8 M COP por gateway; $0,2–1,5 M COP por sensor** | **S** (no se pudo verificar: cupo de búsqueda agotado) | — |
| LED de AP con nodo de telegestión | **≈$2,5 M COP por punto** instalado | **S** | — |

### 3.2 Proyectos solares reales en edificios públicos de Colombia

| Proyecto | Capacidad | Inversión | Generación / ahorro | Fecha | Fuente |
|---|---|---|---|---|---|
| **Hospital San Antonio de Padua, Simití (Bolívar)**, PDET Sur de Bolívar como Yondó | **230 kWp** + eficiencia energética | **$3.152 M** | 268.142 kWh/año FV + 32.652 EE = 300.794 kWh/año (100 % del consumo); **>$284 M/año**; 187,3 t CO₂/año | 17-jul-2025 | https://fenoge.gov.co/documentos-noticias/2025/Comunicado_entrega_de_hospital_publico_autosostenible_en_Simiti_Bolivar.pdf |
| Hospital San Carlos, Aipe (Huila) | n.d. | $2.146 M | 232.509 kWh/año FV + 37.536 EE = 270.045 kWh/año; ≈$200 M/año; −26,8 % en los primeros 8 días | 16-jun-2025 | https://fenoge.gov.co/documentos-noticias/2025/Boletin_hospital_autosostenible_en_AIPE.pdf |
| Hospital Federico Arbeláez, Cunday (Tolima) | 43,10 kWp | $713,5 M (incluye 16 luminarias, 5 equipos de refrigeración y 17 aires acondicionados) | 65.943 kWh/año; ahorro total 80.343 kWh/año; −90 % de factura; ≈$67 M/año | 14-jun-2025 | https://fenoge.gov.co/documentos-noticias/2025/BoletinCunday14062025.pdf |
| Hospital Ismael Silva, Silvania | 55,2 kWp | >$608 M | 67.999 kWh/año; −60 % de consumo; ≈$48 M/año | jul-2025 | https://fenoge.gov.co/documentos-noticias/2025/Boletin_Silvania_2207.pdf |
| IE Santa Inés / Subía / Aguabonita (Silvania) | 17,25 / 6,9 / 6,8 kWp | $249 M / $203 M / $146 M | −90 % de consumo; ≈$21 M/año (Santa Inés) | jul-2025 | ídem |
| 10 IE públicas, Villavicencio (convenio con la alcaldía) | ≈112 kWp | $2.657,7 M | ≈135 MWh/año; ≈$125 M/año; hasta −80 % de factura | — | https://fenoge.gov.co/proyectos/energia-solar-en-colegios-publicos-en-villavicencio/ |
| 29 IE, Pereira | ≈665 kWp | $10.435,9 M | — | — | https://fenoge.gov.co/proyectos/energia-solar-para-colegios-publicos-en-pereira/ |
| Programa ConEnergía (FENOGE): ZOMAC, PDET y municipios de 5.ª-6.ª categoría | 108 edificaciones; **3.273,27 kWp** (651 educación + 2.622 salud; 26 hospitales) | n.d. | Proyección: 4.744.794 kWh/año FV + 1.545.392 kWh/año EE | 2026 (página) | https://fenoge.gov.co/proyectos/conenergia/ |
| Hospital San Vicente Ferrer, Andalucía (Valle) | 91,43 kWp (159 paneles) | n.d. | Ahorro proyectado de hasta 90 % | jun-2026 | https://minenergia.gov.co/es/sala-de-prensa/noticias-index/energia-solar-llega-a-nueve-centros-de-salud-del-valle-del-cauca-gobierno-proyecta-ahorros-de-hasta-90-en-costos-electricos/ |

---

## 4. Marco normativo y financiación

### 4.1 Leyes de FNCER y eficiencia energética

| Norma | Contenido relevante | Conf. | Fuente |
|---|---|---|---|
| **Ley 1715 de 2014** (modificada por la Ley 2099) | Incentivos: **deducción del 50 % en renta** de la inversión (hasta 15 años, ≤50 % de la renta líquida); **exclusión de IVA**; **exención arancelaria** (equipos no producidos en el país); **depreciación acelerada** | V2 | https://cijuf.org.co/sites/cijuf.org.co/files/documentos_interes/BOLETIN%20TRIBUTARIO%20120_1.pdf |
| **Ley 2099 de 2021** | Extiende los incentivos a la gestión eficiente de energía (GEE), incluida la medición inteligente. Depreciación acelerada del 20 % → **33,33 % anual**. Vigencia de **30 años** desde jul-2021. El certificado UPME basta (sin aval ANLA). | V2 | https://actualicese.com/archivo/ley-2099-de-julio-10-de-2021-modifico-beneficios-tributarios-por-generacion-de-energia-electrica/ ; https://www.bu.com.co/es/insights/noticias/dictan-disposiciones-para-la-transicion-energetica |
| Decreto 895 de 2022 | Reglamenta los arts. 11-14 de la Ley 1715 modificados | V2 | https://sidn.ramajudicial.gov.co/SIDN/NORMATIVA/TEXTOS_COMPLETOS/5_DECRETOS/DECRETOS%202022/DECRETO%20895%20DE%202022%20(MODIFICA%20EL%20DECRETO%201625%20DE%202016,%20%C3%9ANICO%20REGLAMENTARIO%20EN%20MATERIA%20TRIBUTARIA).PDF |
| **Implicación para el municipio** | La alcaldía no declara renta, así que **no aprovecha la deducción del 50 %**. Sí aprovecha **exclusión de IVA y arancel** con certificado UPME. Un tercero contribuyente (ESCO, APP u Ecopetrol vía OxI) puede capturar la deducción. | C (análisis) | — |
| Ley 2099, medidores inteligentes | La Corte Constitucional declaró inexequible el traslado del costo del medidor a los usuarios | V2 | https://www.valoraanalitik.com/medidores-inteligentes-de-energia-asi-se-implementaran-en-colombia/ |

### 4.2 CREG 174 de 2021 (AGPE / GD), texto vigente con la modificación de la CREG 101 072 de 2025

Fuente (V): https://gestornormativo.creg.gov.co/gestor/entorno/docs/resolucion_creg_0174_2021.htm

| Aspecto | Regla | Conf. |
|---|---|---|
| Definición de AGPE | Capacidad instalada **≤1 MW** (límite de la Res. UPME 281/2015). Por encima es AGGE. | V |
| Conexión | AGPE con excedentes **≤100 kW**: procedimiento sin estudio de conexión. **>100 kW y ≤1 MW: estudio de conexión simplificado** (art. 12). | V |
| Respaldo | Autogeneradores **≥100 kW**: contrato de capacidad de respaldo con el OR (CREG 015/2018, cap. 10) | V2 (cartilla Electrohuila) https://www.electrohuila.com.co/wp-content/uploads/2025/06/Cartilla-para-el-procedimiento-de-conexion-resolucion-CREG-174-de-2021.pdf |
| Excedentes AGPE con FNCER **≤100 kW** | Excedentes hasta la importación: **crédito 1:1**. El comercializador cobra solo **Cv** (comercialización). Excedentes sobre la importación: se liquidan al **MCm**. | V |
| Excedentes AGPE con FNCER **>100 kW y ≤1 MW** | Crédito 1:1, pero cobrando **T + D + Cv + PR + R** por kWh permutado. Excedentes sobre la importación al **MCm**. | V |
| Transición | Los AGPE existentes con contratos a precio de bolsa pueden mantenerlo hasta el paso a MCm (Anexo 3 de la CREG 101 072) | V |
| Límite por circuito (NT1) | ΣGD+AGPE con entrega ≤50 % de la capacidad del circuito, transformador o subestación | V |
| Excedentes sin comercializador | No se remuneran (art. 26, par. 3) | V |
| Definición de "capacidad instalada" del inversor (CA vs kWp DC) | Verificar en el art. 3 antes de fijar el tamaño de cada frontera ≤100 kW | P |
| Comunidades energéticas en la CREG | Res. **CREG 101 072 de 2025** armoniza su integración (incluye AGPE) | V2 |

### 4.3 Comunidades energéticas (CE)

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| **Decreto 2236 de 2023** | Reglamenta el art. 235 de la Ley 2294 de 2023 (PND). Beneficiarios de recursos públicos: personas naturales, gobierno propio indígena, comunidades campesinas, negras, afro, raizales y palenqueras constituidas como CE, según la focalización de MinEnergía. | V2 | https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=227230 |
| Focalización | **Res. MinEnergía 40509 de 2024** (deroga la 40137 de 2024) | V2 | https://normograma.mintic.gov.co/mintic/compilacion/docs/resolucion_minminas_40509_2024.htm |
| Registro | Res. 40136 de 2024 (registro único de CE) | V2 | https://www.minenergia.gov.co/documents/11540/Resolucion_Registro_unico_de_comunidades_energeticas_.pdf |
| Ejecución 2025-2026 | **2.321 CE**, >31.000 usuarios, 37,39 MWp (la fuente escribe "MWh"). Vigencias futuras (CONFIS). Prioridad en La Guajira, Chocó y Catatumbo. | V2 (MinEnergía, 12-dic-2025) | https://www.minenergia.gov.co/es/sala-de-prensa/noticias-index/gobierno-asegura-recursos-y-acelera-ejecucion-de-2321-comunidades-energeticas-en-el-pais/ |
| Proyectos de CE presentados por operadores | 686 proyectos de 25 operadores o generadores públicos o mixtos; **$935 mil millones** priorizados; $27 mil millones para estructurar 183 proyectos con universidades públicas | V2 (resumen de buscador) | https://minenergia.gov.co/es/sala-de-prensa/noticias-index/gobierno-garantiza-vigencias-futuras-para-asegurar-la-continuidad-de-las-comunidades-energeticas-en-colombia/ |
| **Convocatoria CE Innovadoras** (MinEnergía, **Ecopetrol** y MinCiencias) | >$11 mil millones para 4 propuestas; abierta del 3-sep-2025 al 14-nov-2025; resultados en mar-2026 | V2 | https://www.minenergia.gov.co/es/sala-de-prensa/noticias-index/se-abrio-primera-convocatoria-para-desarrollar-comunidades-energeticas-innovadoras/ |
| Uso para Yondó | Instrumento adecuado para el **componente rural y residencial** (veredas sin red, pescadores, acueductos veredales). Las sedes públicas encajan mejor en FENOGE, SGR u OxI. | C | — |

### 4.4 FENOGE / Fondo de Energías No Convencionales y Gestión Eficiente de la Energía

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| Acceso de entidades territoriales | Los "Criterios de presentación de solicitudes" (parte del Manual Operativo) prevén solicitudes de **recursos reembolsables y no reembolsables**. Para entidades territoriales exigen certificado de planeación (proyecto en el plan de inversiones), Marco Fiscal de Mediano Plazo, indicadores Ley 358/617/819 y ejecución presupuestal. | V | https://fenoge.gov.co/documentos-pdf/Criterios-de-Presentacion-de-Solicitudes.pdf |
| Trámite | Concepto de entidades viabilizadoras, luego priorización FENOGE y decisión del Comité Directivo. Fechas de corte trimestrales según el proyecto de modificación de 2023. | V2 | https://ambitojuridico.com/sites/default/files/2023-10/PROYECTONORMA-Minenergia-2023%28%20Modificarian-manual-operativo-de-Fenoge%29.pdf |
| **ConEnergía** | Focaliza ZOMAC, **PDET** y municipios de 5.ª-6.ª categoría. **Yondó es PDET.** | V | https://fenoge.gov.co/proyectos/conenergia/ |
| Colombia Solar, IA-006-2026 (SSFV urbanos en el SIN) | Publicada el 17-jun-2026 y **CANCELADA**. Es contratación de implementador, no postulación de alcaldías. | V2 | https://fenoge.gov.co/ia-006-2026-fenoge-implementacion-colombia-solar/ |
| PEECES (BID 5738/OC-CO) | SSFV para el sector oficial del **Caribe**; licitación cerrada el 27-may-2026. Yondó (Antioquia) probablemente no es elegible (C). | V2 | https://fenoge.gov.co/licitacion-publica-internacional-ssfv-no-peeces-co-l1271/ |

### 4.5 SGR / regalías (lo más directo para Yondó)

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| Yondó es beneficiario del Incentivo a la Producción (IP) | Figura en el **listado de 209 municipios** (n.º 21 de Antioquia, código 5893) | V | https://www.minenergia.gov.co/documents/13987/Listado209-Municipios-ConvocatoriaIP-2025.pdf |
| Primera distribución IP 2025-2026 (directa) | **$774.931 millones** a los 209 municipios (Res. MinEnergía 40326 de 23-jul-2025) para proyectos minero-energéticos con acompañamiento gratuito del Grupo de Regalías | V2 | https://www.minenergia.gov.co/es/sala-de-prensa/noticias-index/ministerio-de-minas-y-energia-asigna-775-mil-millones-a-209-municipios-para-proyectos-de-transicion-energetica/ |
| Monto asignado a Yondó en la Res. 40326 | No verificado (el PDF devolvió 403) | P | https://normativame.minenergia.gov.co/normatividad/7323/norma/ |
| **Convocatoria IP 2025** (competitiva, ≈$921 mil millones) | Hasta **2 proyectos por municipio, ≤$8.000 M en total**. Línea de energía eléctrica: FNCER (granjas, SSFV individuales, microrredes ZNI), **AP con FNCER**, CE, electromovilidad, PCH. Tipología **"Territorios energéticos: energización con FNCER de instituciones educativas, acueductos, escenarios deportivos, centros de salud, hospitales, centros administrativos, casas de la cultura e instituciones públicas"**. Postulación del 12-ago al 5-nov-2025. | V | https://www.minenergia.gov.co/es/misional/sistema-general-de-regalias/convocatoria-ip-2025/ ; https://www.minenergia.gov.co/documents/13988/Lineamientos-ConvocatoriaIP-2025.pdf |
| Resultado IP 2025 | 288 postulados, 108 cumplen, 103 no cumplen, 77 desestimados. **Yondó: su único proyecto (aislados rurales) quedó en "no cumplen".** Vecinos como Vegachí y Frontino presentaron "Territorios energéticos". | V | https://www.minenergia.gov.co/documents/15326/informe-final-lista-elegibles-convocatoriaip-2025.pdf |
| Ciclo posterior | Los elegibles pasan por SUIFP-SGR y priorización y aprobación en el **OCAD Paz** | V | ídem |
| Asignaciones directas del SGR de Yondó 2025-2026 | Ver el Anexo 1 de la Ley 2441 de 2024 (no extraído). MinHacienda advierte recaudo bajo y bloqueo del 20 % de ingresos corrientes en el bienio. | P / V2 | https://www.minhacienda.gov.co/documents/d/portal/julio-2026-info-comportamiendo-del-recaudo |
| Proyecto tipo del DNP para FV en edificaciones públicas | No se encontró ficha vigente con costos | P | — |

### 4.6 Obras por Impuestos (OxI), con Ecopetrol como contribuyente

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| Condición territorial de Yondó | **PDET, subregión Sur de Bolívar** (Arenal, Cantagallo, Morales, San Pablo, Santa Rosa del Sur, Simití **y Yondó**). Los municipios PDET son a su vez ZOMAC. | V2 | https://www.unidadvictimas.gov.co/wp-content/uploads/2021/04/subregionsurdebolivar.pdf |
| Sectores elegibles en OxI | Agua potable, alcantarillado, **energía**, salud pública, educación pública e infraestructura vial. MinEnergía es la entidad competente para los proyectos de energía (Res. 40360 de 2024). | V2 | https://gestornormativo.creg.gov.co/gestor/entorno/docs/resolucion_minminas_40360_2024.htm |
| Cupo 2025 | La ART viabilizó **137 proyectos por ≈$1,6 billones** (el mayor en 8 años) | V2 | https://actualicese.com/obras-por-impuestos-gobierno-nacional-aprueba-137-proyectos-por-cerca-de-16-billones/ |
| Ecopetrol en OxI | **91 proyectos asignados** (46 terminados; $758.000 M), con proyectos de energía alternativa. Incluyó **36 sistemas de energía renovable para instituciones educativas** y 317 celdas solares rurales (13 departamentos, incluida Antioquia). | V2 | https://www.larepublica.co/especiales/asi-avanzan-las-obras-por-impuestos/los-proyectos-que-operan-en-el-sector-de-energia-3788747 ; https://www.eltiempo.com/economia/empresas/ecopetrol-destinara-167-000-millones-de-impuestos-para-obras-en-13-departamentos-773482 |
| Proyecto OxI vigente en Yondó | No encontrado | P | — |

### 4.7 Findeter y Bancóldex

| Línea | Condiciones | Conf. | Fuente |
|---|---|---|---|
| Findeter, **"Compromiso Eficiencia Energética y Conectividad Virtual"** (redescuento) | Beneficiarios públicos, privados y descentralizados. Financia EE, generación, distribución y **almacenamiento**, en los sectores Energía y TIC. Plazo de 10 años y 2 de gracia. Tasas publicadas: IBR +2,00 % M.V. / +1,85 % T.V. / +1,75 % S.V. (verificar el signo: un resumen de buscador lo leyó como "IBR −"). Margen del intermediario hasta 400 pb. Requiere viabilidad técnica del ministerio sectorial. | V | https://www.findeter.gov.co/productos-y-servicios/lineas-de-credito-redescuento/compromiso-eficiencia-energetica-y-conectividad-virtual |
| Findeter + MinEnergía, **"Municipios Territorios Energéticos"** (crédito directo) | **IBR + 0,7 % M.V.**, 10 años y 2 de gracia. Requiere registro del municipio como "municipio energético" (427 postulados en la 1.ª ventana). Soluciones: granjas agrovoltaicas de 1 MW, "canchas energéticas" de 130 kW e híbridos. | V (comunicado, 2-ago-2024) | https://www.findeter.gov.co/noticias/comunicados/ministerio-de-minas-y-energia-y-findeter-en-alianza-con-asocapitales-asointermedias-y-fedemunicipios-lanzan-linea-de-financiamiento-para-parques-de-generacion-de-energia |
| Programa reportado de $1,6 billones con subsidio a la tasa | — | V2 | https://www.valoraanalitik.com/gobierno-impulsara-municipios-energeticos/ |
| Decreto 1223 de 14-nov-2025 | Da continuidad a la línea de tasa compensada y al crédito directo a entidades territoriales para proyectos energéticos viabilizados | V2 | https://www.findeter.gov.co/sites/default/files/2026-01/DECRETO%201223%20DEL%2014%20DE%20NOVIEMBRE%20DE%202025.pdf |
| Findeter/BID, "Eficiencia Energética en Alumbrado Público" | LED para municipios (−50 % de energía) | V2 | https://www.valoraanalitik.com/findeter-y-el-bid-modernizar-n-alumbrados-p-blicos-de-colombia/ |
| Bancóldex | No investigado (la línea pública relevante es Findeter) | P | — |

### 4.8 IPSE, FAER y otros fondos

| Fondo | Nota | Conf. | Fuente |
|---|---|---|---|
| IPSE | Mandato en **ZNI**. Yondó está en el SIN, así que la relevancia es limitada. El informe de gestión 2025 lista a Antioquia entre los departamentos con usuarios energizados con SSFV e híbridos. | V2 | https://www.minenergia.gov.co/documents/14805/informeGestion-IPSE-2025.pdf |
| **FAER** (zonas rurales **interconectadas**) | Aplica a la electrificación rural de Yondó en el SIN. La UPME exige proyectos "funcionales". | V2 | https://www1.upme.gov.co:443/fondos-apoyo-financiero/Documents/Guia_presentacion_proyectos/Guia_FAER.pdf |

### 4.9 Compras públicas (Colombia Compra Eficiente)

| Instrumento | Estado | Conf. | Fuente |
|---|---|---|---|
| AMP "Sistemas FV y sus elementos" (CCE-200-AMP-2021) | **Finalizó el 20-mar-2024**, sin prórroga | V2 | https://operaciones.colombiacompra.gov.co/sites/cce_public/files/cce_tienda_virtual/comunicado_finalizacion_amp.pdf |
| AMP "Sistemas FV de generación y almacenamiento" (CCE-074-AMP-2022), de 0,5 a 60 kWp | **Cerrado.** Las órdenes se pudieron colocar hasta el 23-oct-2025 y pueden ejecutarse hasta el 23-oct-2027. Hay comunicación de no prórroga. | V | https://www.colombiacompra.gov.co/archivos/portfolio-item/acuerdo-marco-de-sistemas-fotovoltaicos-de-generacion-y-almacenamiento |
| AMP **Nube Pública V** (CCE-SNG-AMP-011-2026) | **Vigente** del 5-mar-2026 al 5-mar-2028. Útil para hospedar EMS/SCADA y la plataforma IoT. | V2 | https://www.colombiacompra.gov.co/wp-content/uploads/2026/02/Acta-de-inicio-de-operacion-Acuerdo-Marco-de-Precios-Nube-Publica-V.pdf |
| Implicación | Hoy **no hay AMP vigente para FV**: se requiere licitación o selección abreviada propia, o ejecución vía FENOGE, Findeter u OxI | C | — |

---

## 5. MinTIC y componente digital, IoT y domótica

### 5.1 Programas e instrumentos

| Programa / norma | Qué puede financiar o exigir | Conf. | Fuente |
|---|---|---|---|
| **FUTIC, guía de cofinanciación de Ciudades y Territorios Inteligentes** (v1.0, 17-feb-2022) | Cofinancia **(i)** soluciones integrales con licencias y **SaaS/IaaS/PaaS**, **(ii) dispositivos IoT** de captura y procesamiento de datos, **(iii)** nube, **(iv)** equipo de trabajo, **(v)** capacitación y **(vi) fase 1 de ingeniería de detalle**. **No cofinancia el desarrollo o la compra de plataformas CTI.** Exige integración con la "Plataforma CTi País", compartir datos, sostenibilidad durante el Plan de Desarrollo y cumplir la Política de Gobierno Digital. Cofinanciación diferencial: a menor presupuesto, mayor cofinanciación. Dominio aplicable: **"Servicios Públicos Inteligentes"**. Solo opera "en caso de que dichos mecanismos se llegasen a generar". | V | https://gobiernodigital.mintic.gov.co/692/articles-392044_recurso_3.pdf |
| Modelo de madurez de CTI | Seis dimensiones; aplicado a 60-61 entidades desde 2020 | V2 | https://mintic.gov.co/portal/inicio/Sala-de-prensa/MinTIC-en-los-medios/151489:MinTIC-impulsa-a-60-ciudades-de-Colombia-para-que-se-conviertan-en-territorios-inteligentes |
| Res. MinTIC 1117 de 2022 | Lineamientos de transformación digital para estrategias de CTI | V2 | https://gobiernodigital.mintic.gov.co/portal/Iniciativas/Ciudades-y-Territorios-Inteligentes/ |
| **Máxima Velocidad 2026** | Inscripciones desde el 21-abr-2026. Acompañamiento técnico y retos para ≈250 entidades territoriales: **arquitectura empresarial, seguridad de la información, datos abiertos, territorios inteligentes, IPv6**. Términos en maximavelocidad.gov.co. | V | https://www.mintic.gov.co/portal/inicio/Sala-de-prensa/Noticias/437132:Abiertas-las-inscripciones-para-Maxima-Velocidad-2026-el-pais-acelera-hacia-un-nuevo-estandar-de-transformacion-digital-territorial |
| "IA para el Estado" (MinTIC y U. de Cartagena) | Llevar IA a 200 entidades territoriales (2026) | V2 | https://724noticias.com.co/2026/06/04/slug-mintic-universidad-cartagena-ia-para-el-estado-200-entidades-territoriales/ |
| Política de Gobierno Digital, **Decreto 767 de 2022** | Componentes y habilitadores (arquitectura, seguridad y privacidad, servicios ciudadanos digitales). Es obligatoria como política de gestión (MIPG). | V2 | https://gobiernodigital.mintic.gov.co/692/articles-272977_Decreto_767_2022.pdf |
| Servicios Ciudadanos Digitales, Decreto 620 de 2020 | Habilitador (interoperabilidad, autenticación, carpeta ciudadana) | V2 | ídem |
| AMP de FV como "habilitador de CTI" (2021) | MinTIC promovió con CCE el AMP de FV para alcaldías como habilitador de la política de CTI | V | https://mintic.gov.co/portal/inicio/Sala-de-prensa/178805:MinTIC-continua-promoviendo-el-desarrollo-de-Ciudades-y-Territorios-Inteligentes-con-el-Acuerdo-Marco-de-Precios-para-adquirir-sistemas-fotovoltaicos |
| Convocatorias específicas de IoT de MinTIC 2025-2026 | No se hallaron. Las conocidas (Centro de Excelencia IoT con Colciencias) son de 2014-2015. | P | https://mintic.gov.co/portal/historico/w3-article-7316.html |
| "Colombia Inteligente 2026" | Es de **MinCiencias**, no de MinTIC, y ya cerró | V2 | https://minciencias.gov.co/convocatorias/convocatoria-colombia-inteligente-2026 |

### 5.2 Capacidad institucional TIC de Yondó (SECOP II, datos abiertos)

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| Dependencia | **"Secretaría de Planeación, TIC y Desarrollo Territorial"** | V | https://www.datos.gov.co/resource/jbjy-vk9h.json (contratos del Municipio de Yondó) |
| PETI | Contratos 2025-2026 para la **implementación y seguimiento del Plan Estratégico de TI (PETI)** y de la política de Gobierno Digital (p. ej., 9-oct-2026, 26-ene-2026, 12-feb-2025, 29-oct-2024) | V | ídem |
| Empresa de servicios públicos | **Aguas y Aseo de Yondó S.A. E.S.P.** (238 contratos): PTAP municipal y veredal, generación de hipoclorito in situ, EBAR con 4 electrobombas, electrobomba sumergible de 20 HP en acueducto veredal | V | ídem |

### 5.3 Conectividad en Yondó

| Indicador | Valor | Conf. | Fuente |
|---|---|---|---|
| Accesos fijos a internet, Yondó (código DANE 05893), **2023-T3** (último dato en el dataset) | **1.062**, en descenso desde 1.545 en 2021-T4. Por tecnología: xDSL 661, inalámbrica 238, satelital 128, **FTTH 34**. Por proveedor: Edatel 670, DirecTV 238, Hughes 127. Por segmento: estrato 2 510, estrato 1 395, corporativo 74. | V | https://www.datos.gov.co/resource/n48w-gutb.json?cod_municipio=05893 |
| Población de Yondó (proyección DANE) | 21.677 (2024); 22.061 (2025) | V2 (reproduce DANE) | https://telencuestas.com/censos-de-poblacion/colombia/2025/antioquia/yondo |
| **Penetración de internet fijo en Yondó** | **≈4,9 accesos por 100 habitantes** (1.062 / 21.677; los años de numerador y denominador no coinciden) | C | — |
| Antioquia, 2026-T2 | 26,6 por 100 habitantes (1.863.160 accesos) | V | https://www.datos.gov.co/resource/wym4-7diu.json |
| Nacional, 2025-T4 | 19 por 100 habitantes | V | https://colombiatic.mintic.gov.co/679/articles-437023_archivo_pdf.pdf |

### 5.4 Centros Digitales y Zonas WiFi en Yondó

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| Centros Digitales rurales (corte 31-oct-2023) | **4**, todos en el **corregimiento San Miguel del Tigre**: IER San Miguel del Tigre, IER San Luis Beltrán, CER La Primavera y CER La Raya. Estado "OPERACIÓN"; bajada 15–18 Mbps; tipo de energía "EN VERIFICACIÓN"; inversión registrada $142,7 M por sitio. | V | https://www.datos.gov.co/resource/fybg-535s.json |
| Zonas Digitales urbanas (corte oct-2023) | Yondó **no aparece** | V | https://www.datos.gov.co/resource/wg2u-d8ji.json |
| Conectividad de Alta Velocidad (torres), "Acceso universal" | Yondó no aparece | V | https://www.datos.gov.co/resource/xcpu-5b5n.json ; https://www.datos.gov.co/resource/rejx-ewy7.json |
| Programa Centros Digitales | Conectividad prevista hasta 2032; dos puntos (interno y externo) por sede | V2 | https://mintic.gov.co/portal/inicio/Sala-de-prensa/Noticias/161294:En-el-2020-revolucionamos-la-conectividad-para-que-llegara-a-todas-las-regiones-de-Colombia-ministra-Karen-Abudinen |
| Datos 2024-2026 de Centros Digitales en Yondó | No hay dataset actualizado | P | — |

### 5.5 Espectro para IoT (LoRaWAN)

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| Banda de uso libre | **915–928 MHz** (Res. ANE 711 de 2016 recortó 902–928 a 915–928). Modulación digital ≤1 W. | V2 | https://careers.kiwa.com/globalassets/uk/pcs/regulatory-updates-2017/regulatory_alert_colombia_24-may-17.pdf |
| Plan de canales LoRaWAN usado en Colombia | **AU915-928** (práctica comunitaria; no es norma) | V2 | https://www.thethingsnetwork.org/forum/t/frequency-plan-colombia/55850 |
| Res. ANE 000028 de 26-ene-2026 | Modifica la Res. 105/2020 sobre la banda de 900 MHz. Verificar cómo afecta al uso libre. | V2 | https://ane.gov.co/Sliders/archivos/Normatividad/2.%20DE%20LA%20ANE/Resoluciones%20ANE/Planeaci%C3%B3n%20de%20Espectro/RESOLUCION000028DEL26012026.pdf |

---

## 6. Ecopetrol y energía en el Magdalena Medio

| Dato | Valor | Conf. | Fuente |
|---|---|---|---|
| **Granja Solar La Iguana**, en el **municipio de Yondó** | **26 MWp**, 42.840 paneles, 26 ha, **42,2 GWh/año**, ≈26.000 t CO₂/año. Inaugurada el **4-dic-2025** y en operación. Abastece la **refinería de Barrancabermeja y los campos Casabe y Llanito**. | V | https://www.ecopetrol.com.co/wps/portal/Home/es/noticias/detalle/ecopetrol-inauguro-granja-solar-la-iguana-un-nuevo-hito-de-autogeneracion-con-energia-renovable |
| Efecto | Sustituye ≈6 % de la energía que esos activos compran al SIN y libera ≈1,09 GBTU/día de gas | V2 | https://www.marketscreener.com/news/colombia-s-ecopetrol-inaugurates-26mw-solar-farm-to-power-barrancabermeja-refinery-ce7d51dcd88cf527 |
| Beneficios locales | 286 empleos (221 locales); SENA para 120 mujeres; **rehabilitación de la cubierta de la IE La Patria ($800 M)**; apoyo Saber 11 a 160 estudiantes | V | página de Ecopetrol citada arriba |
| Ecoparques Del Río (Casabe, Yondó) y Magdalena (Cantagallo) | 6 MW en conjunto para operaciones de Ecopetrol y Hocol, con contrato de 15 años. Plan de 2021; **estado actual no verificado**. | V2 (2021) / P | https://www.valoraanalitik.com/ecopetrol-busca-transformacion-energetica-de-colombia-con-nuevos-parques-solares/ |
| Demanda eléctrica del activo Casabe | **11 MW** (Casabe 8,3, Casabe Sur 1,5, Peñas Blancas 1,2). **Solo el 33 % se autogenera con gas** de las operaciones (Ecopetrol, 2021, citado). | V2 (trabajo académico UNAB) | https://repository.unab.edu.co/bitstreams/56fd3131-52d4-459d-ba17-1d0dbd7ade76/download |
| Gas asociado de Casabe | "El gas subproducto de la extracción **no se incorpora a ningún mercado**": se quema o ventea. Propone reactivar los pozos PTM01/PTM02 (≈1.400 MMSCF) para autogeneración: ≈48.000 kWh/día promedio y ahorro probable de $14,3 mil millones en 10 años. | V2 | ídem |
| Campos Casabe, Casabe Sur, Peñas Blancas y Llanito | ≈14.900 bpd en conjunto. Acuerdo con **Parex (US$250 M, 50 % de la producción)** para recobro mejorado; Ecopetrol mantiene la operación. Firmado en may-2026, sujeto a condiciones. | V2 | https://www.eltiempo.com/economia/sectores/ecopetrol-cede-el-50-de-su-produccion-en-otros-cuatro-campos-petroleros-por-us-250-millones-de-parex-resources-3553025 ; https://www.prensa-latina.cu/2026/05/05/firman-acuerdo-para-desarrollo-de-campos-petroleros-en-colombia/ |
| Comunidades energéticas de Ecopetrol | **7 CE, ≈$2.500 M**, en el Magdalena Medio (Puerto Parra; San Rafael de Chucurí y El Arenal en Barrancabermeja) y Cali. Proyecto Vida Silvestre con WCS y Fondo Acción (30-ene-2025). | V | https://www.ecopetrol.com.co/wps/portal/Home/es/noticias/detalle/ecopetrol-consolida-siete-nuevas-comunidades-energeticas |
| Inversión educativa de Ecopetrol en el Magdalena Medio | $32.925 M en 2024-2025, incluido Yondó | V2 | https://elfrente.com.co/ecopetrol-apuesta-por-el-bienestar-del-magdalena-medio-con-inversion-historica-entre-2024-y-2025/ |
| Conflictividad | Bloqueos de comunidades de Yondó a Casabe (2023) con suspensión de contratos. Es un riesgo social y una razón para un proyecto de "beneficio compartido". | V2 | https://www.vanguardia.com/santander/barrancabermeja/2023/04/13/suspenderan-contratos-en-yondo-debido-a-los-bloqueos/ |

**Opciones de convenio con Ecopetrol** (C/S: hipótesis a explorar; ninguna está confirmada):

1. **Obras por Impuestos.** Proyecto de energía en sedes públicas de Yondó (PDET/ZOMAC) inscrito en el banco de la ART.
2. **Inversión social o PBC del contrato.** Cofinanciar el componente de colegios y la biblioteca como "Territorio energético".
3. **CE apoyadas por Ecopetrol.** Pescadores y veredas ribereñas de Yondó, replicando Pescomagda o Brisas del Río Magdalena.
4. **Cooperación técnica.** O&M de FV a escala (La Iguana) y formación SENA de técnicos locales en O&M.
5. **Gas asociado y respaldo.** Cualquier suministro de gas o energía de Ecopetrol al municipio exigiría figura regulatoria (comercialización, contrato y permisos ANH/CREG). Es de largo plazo y no se recomienda como base del diseño.

---

## 7. Estándares técnicos de referencia

| Norma | Uso en el proyecto | Conf. | Fuente |
|---|---|---|---|
| **RETIE**: Res. MinEnergía **40117 de 2024** (DO 52.716, 3-abr-2024). Transitorio de productos y personas extendido por la Res. 40304 de 2025. | Reglamento obligatorio: certificación de producto, dictamen de inspección y declaración de cumplimiento de la instalación FV y BESS | V2 | https://normograma.dian.gov.co/dian/compilacion/docs/resolucion_minminas_40117_2024.htm ; https://gestornormativo.creg.gov.co/gestor/entorno/docs/resolucion_minminas_40304_2025.htm ; https://minenergia.gov.co/es/misional/energia-electrica-2/reglamentos-tecnicos/reglamento-t%C3%A9cnico-de-instalaciones-el%C3%A9ctricas-retie/ |
| **NTC 2050** | Sección 690 (FV), 705 (interconexión), 480 (baterías). La 2.ª actualización (basada en NEC 2017) agrega artículos de almacenamiento y microrredes (706/710/712). **No se verificó si el RETIE 2024 ya remite a la 2.ª actualización.** | V2 / P | https://feriaexposolar.com/wp-content/uploads/2024/10/OSAIC.pdf |
| **RETILAP**: Res. 40150 de 2024 (y 40318 de 2025) | Luminarias LED de AP, telegestión y dictamen | V2 | §1.6 |
| **IEC 61850** (y 61850-7-420 para DER) | Comunicación de subestación y protección e interfaz de DER y BESS con el EMS en la S/E Yondó, si EPM lo exige | V | https://webstore.iec.ch/en/publication/6028 |
| **IEEE 1547-2018** | Interconexión de DER: ride-through, funciones de inversor inteligente y anti-isla | V | https://standards.ieee.org/ieee/1547/5915/ |
| **IEEE 2030.7 / 2030.8** | Especificación y pruebas del controlador de microrred (modos isla y conectado, transición) | V | https://standards.ieee.org/ieee/2030.7/5941/ |
| **Modbus TCP/RTU** | Inversores, medidores y BMS de baterías | V2 | https://www.modbus.org/specs.php |
| **BACnet** (ASHRAE 135 / ISO 16484-5) | Domótica, HVAC e iluminación en la alcaldía y el hospital | V | https://bacnet.org/ |
| **MQTT v5.0** (OASIS; ISO/IEC 20922 para v3.1.1) | Bus de datos IoT hacia la plataforma y la Plataforma CTi País | V | https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html |
| **LoRaWAN AU915** | Sensores de baja tasa (tanques, presión, calidad de agua, luminarias, temperatura de neveras de vacunas) | V2 | §5.5 |
| **ISO 50001:2018** | Sistema de gestión de la energía municipal (línea base, EnPI, M&V) | V2 (el sitio ISO bloquea la verificación automática) | https://www.iso.org/standard/69426.html |
| Res. MinVivienda 0549 de 2015 | Ahorros exigidos en edificaciones nuevas. En **cálido húmedo, año 2 en adelante: hospitales 30 %, oficinas 30 %, educativos 35 %** respecto a la línea base. | V | https://normas.cra.gov.co/gestor/docs/resolucion_minviviendact_0549_2015.htm |
| Ciberseguridad OT (IEC 62443) e ISO/IEC 27001 (MSPI de Gobierno Digital) | Segmentación de red OT/IT del EMS | S (recomendación) | — |

---

## 8. Propuesta preliminar de dimensionamiento

> **Todo lo de esta sección es preliminar.** Los consumos son **supuestos (S)** o análogos (V2) hasta obtener **12 meses de facturas EPM por NIU** de cada sede, una auditoría energética nivel ASHRAE 1/2 y levantamiento de cubiertas.

### 8.1 Supuestos de consumo (clima cálido húmedo; Yondó a 75 m s. n. m. y 26,3 °C de media anual según GSA)

**Referencias de intensidad.** Línea base de la Guía de Construcción Sostenible de MinVivienda (2015) para cálido húmedo (Barranquilla), reproducida en una fuente secundaria:

| Tipo de edificación | kWh/m²·año |
|---|---|
| Hospital | **344,1** |
| Oficinas | **221,3** |
| Educativos | **29,8** |

Fuente (V2): https://www.colmayor.edu.co/wp-content/uploads/2023/07/MI2-XXI_SEFAI_Muestras-investigativas-Impacto-Social-CC.pdf

Análogos FENOGE verificados: hospital de **Simití ≈25.066 kWh/mes** (300.794/12) y **Aipe ≈22.504 kWh/mes** (C sobre V).

| Dependencia | kWh/mes adoptado | Base del supuesto | Conf. |
|---|---|---|---|
| Alcaldía / palacio municipal | **8.000** (rango 6.000–12.000) | ≈30–40 equipos split de 12 kBTU a 8 h/día, más iluminación y TI. Por benchmark, 221 kWh/m²·año × ≈450 m² acondicionados ≈ 8.300. | S |
| ESE Hospital (nivel 1-2) | **24.000** (20.000–26.000) | Análogos de Simití y Aipe, municipios de tamaño similar | V2 (análogo) / S |
| IE urbanas, 3 sedes principales | **3 × 4.000 = 12.000** | 29,8 kWh/m²·año × ≈1.600 m² ≈ 4.000 por sede, con aulas sin aire acondicionado y salas de sistemas y administración acondicionadas | S |
| Biblioteca / casa de la cultura (punto digital) | **2.000** | Aire acondicionado parcial y equipos de cómputo | S |
| Estación de policía (24/7) | **3.000** | Carga plana: comunicaciones, aire acondicionado de alojamiento e iluminación | S |
| Bomberos / gestión del riesgo (24/7) | **1.500** | Radio, carga de equipos y alojamiento | S |
| Acueducto: captación y bombeo de agua cruda | **15.000** | ≈1.800 m³/día (≈12.000 hab. urbanos × 150 L/hab·día) × ≈0,4–0,8 kWh/m³ → 22.000–43.000 kWh/mes para todo el sistema. Se adopta 30.000, repartido en dos fronteras. | **S** (sin fuente local de intensidad) |
| PTAP (incluye hipoclorito electrolítico) + EBAR | **15.000** | ídem | S |
| **Subtotal sin AP** | **80.500 kWh/mes (≈966 MWh/año)** | — | S |
| Alumbrado público (no se cubre con FV diurna) | 1.200 luminarias (S): LED de 60 W × 12 h ≈ **25.900 kWh/mes**, o ≈19.400 con telegestión (−25 %). Si hoy son de sodio de 150 W: ≈74.500 kWh/mes. | S | — |

**Factura actual estimada (C):** 80.500 kWh/mes con 991,29 COP/kWh (y 1.090,41 para el acueducto) da **≈$82,8 M/mes ≈ $993 M/año** sin AP.

### 8.2 Arquitectura propuesta: "microrred municipal virtual" con islas críticas

- **Nivel 1. FV distribuida detrás del medidor**, una frontera AGPE por sede, cada una **≤100 kW**. Así se conecta sin estudio y el excedente se acredita a ≈877 COP/kWh.
- **Nivel 2. Islas resilientes** (BESS LFP, inversor híbrido grid-forming y transferencia automática) en **hospital, alcaldía (centro de datos y atención), policía, bomberos y biblioteca** (refugio y punto de conectividad). Se **conservan las plantas diésel existentes** como último respaldo, integradas al EMS. El EMS minimiza las horas de diésel.
- **Nivel 3. Flexibilidad de demanda.** Bombeo de agua cruda y EBAR desplazados a horas solares usando los tanques como "batería hidráulica", con variadores de velocidad y telemetría de niveles por LoRaWAN. Telegestión del AP con atenuación nocturna.
- **Nivel 4. EMS/SCADA municipal** en nube (AMP Nube Pública V) o local. Medición por sede (Modbus/DLMS), BMS/BACnet en edificios, bus MQTT y tablero abierto de datos. Debe integrarse con la Plataforma CTi País (requisito FUTIC) y con un SGEn ISO 50001.
- **Nivel 5 (rural).** SSFV aislados o híbridos en sedes rurales y Centros Digitales (San Miguel del Tigre), articulados con un nuevo proyecto IP o CE para viviendas dispersas.
- **"Microrred física" (fase 2, a estudiar con EPM):** interconectar hospital, alcaldía y policía en un mismo alimentador de 13,2 kV con un punto de acople común y operación en isla. Requiere acuerdo con el OR, que es dueño de la red, y un análisis regulatorio. No se recomienda en la fase 1.

### 8.3 Dimensionamiento y resultados (simulación horaria simplificada, C con supuestos S)

Método:
- Perfil solar horario senoidal escalado al **PVOUT mensual de GSA × 0,84**.
- Perfiles de carga por tipología: hospital 24 h con pico diurno; oficina de 7:00 a 17:00 L-V; colegio en calendario escolar (feb-jun y jul-nov); policía y bomberos planos; acueducto con bombeo desplazado al día.
- BESS con 95 % de eficiencia por tramo.
- Liquidación CREG 174 (crédito ≤100 kW al valor neto tarifa − Cv). Excedente sobre la importación a MCm = **250 COP/kWh (S, no verificado)**.
- Script: archivo de trabajo.

| Sede | kWh/mes | FV (kWp) | BESS útil (kWh / kW) | Gen. kWh/mes | Cobertura | Autoconsumo | Ahorro estimado (M COP/mes) |
|---|---|---|---|---|---|---|---|
| Alcaldía | 8.000 | 40 | 50 / 25 | 4.500 | 56 % | 89 % | 4,36 |
| ESE Hospital | 24.000 | **100** | **160 / 50** | 11.250 | 47 % | 100 % | 11,10 |
| IE urbana × 3 | 3 × 4.000 | 3 × 25 | — | 3 × 2.812 | 70 % | 70 % (vacaciones y fines de semana exportan) | 3 × 2,69 |
| Biblioteca / casa de la cultura | 2.000 | 12 | 12 / 6 | 1.350 | 68 % | 88 % | 1,31 |
| Policía | 3.000 | 15 | 25 / 10 | 1.687 | 56 % | 100 % | 1,63 |
| Bomberos | 1.500 | 8 | 16 / 8 | 900 | 60 % | 100 % | 0,87 |
| Acueducto: bombeo agua cruda | 15.000 | 75 | — (tanques) | 8.437 | 56 % | 97 % | 9,17 |
| PTAP + EBAR | 15.000 | 75 | — (tanques) | 8.437 | 56 % | 97 % | 9,17 |
| **Total conectado** | **80.500** | **≈400 kWp** | **≈263 kWh útiles (≈290 kWh nominales)** | **≈45.000 (≈540 MWh/año)** | **≈56 %** | ≈92 % | **≈45,7 M/mes ≈ $548 M/año (≈55 % de la factura)** |
| Sedes rurales aisladas (10) | — | 10 × 3 kWp | 10 × 10 kWh | — | — | — | (beneficio social; no factura) |

Lectura:
- El hospital se limita a 100 kWp para quedar en ≤100 kW, autoconsumir el 100 % y evitar el estudio de conexión y el contrato de respaldo. Simití instaló 230 kWp para un consumo similar, pero sobre una base neta anual que, con las reglas de >100 kW, valoraría la exportación a ≈404 COP/kWh.
- Una fase 2 podría llevar el hospital a ≈150 kWp con más BESS, si el EMS demuestra perfiles diurnos más altos.

### 8.4 CAPEX indicativo (S salvo indicación)

| Componente | Cálculo | M COP |
|---|---|---|
| FV conectada a red | 400 kWp × $3,5 M/kWp (S; rango de mercado V2 2,0–4,0) | 1.400 |
| BESS LFP + PCS/inversor híbrido + transferencia | ≈290 kWh nominales × $1,4 M/kWh (S) | 406 |
| Sedes rurales aisladas (3 kWp + 10 kWh) | 10 × $60 M (S). El techo del AMP CCE para 0,5–10 kWp con almacenamiento fue de $89,5–108 M (V). | 600 |
| Medición inteligente / analizadores | 30 puntos × $4 M | 120 |
| Red LoRaWAN | 3 gateways × $8 M | 24 |
| Sensores IoT (niveles, presión, cloro, temperatura de neveras, ocupación, luminarias piloto) | 150 × $0,8 M | 120 |
| EMS/SCADA de microrred + integración + ciberseguridad OT | global | 450 |
| BMS/domótica en alcaldía y hospital (HVAC, iluminación, BACnet) | 2 × $150 M | 300 |
| Conectividad entre sedes (fibra o radioenlaces, 4G de respaldo) | global | 150 |
| Eficiencia energética (aires inverter, LED interior, variadores en bombas) | global | 400 |
| **Subtotal** | | **3.970** |
| Estudios, diseños, RETIE e interventoría (10 %) | | 397 |
| Imprevistos (5 %) | | 199 |
| **Total indicativo** | | **≈4.566 (≈USD 1,44 M a $3.170)** |
| *Opcional: AP LED con telegestión* | 1.200 × $2,5 M (S) | *3.000* |

**Sensibilidad del repago simple del componente FV+BESS** (ahorro de $548 M/año; O&M del 1,5 %/año del CAPEX; C):

| FV \ BESS | $1,0 M/kWh | $1,4 M/kWh | $2,2 M/kWh |
|---|---|---|---|
| $2,5 M/kWp | 2,4 años | 2,7 | 3,1 |
| **$3,5 M/kWp** | 3,2 | **3,5** | 3,9 |
| $5,0 M/kWp | 4,5 | 4,7 | 5,2 |

Proyecto completo (incluye digital, rural y EE, sin AP): **≈8,8 años** de repago simple. El componente digital y rural se justifica por resiliencia, servicio y cofinanciación, no por la factura. El cálculo no incluye inflación tarifaria, degradación (≈0,5 %/año), reposición de baterías (≈año 10–12) ni los ahorros de EE.

### 8.5 Indicadores de resiliencia sugeridos (S)

| Carga crítica | Potencia (S) | Autonomía con BESS (sin sol) | Respaldo |
|---|---|---|---|
| Hospital: urgencias, neveras de vacunas, oxígeno, iluminación y TI | 40 kW | 160 kWh útiles → **≈4 h** | Planta diésel existente (verificar exigencias de habilitación) |
| Alcaldía: servidores, telecom y atención ciudadana | 10 kW | 50 kWh → ≈5 h | — |
| Policía y bomberos: radio y comunicaciones | 3–5 kW | 16–25 kWh → ≈5 h | Pequeña planta (S) |

La duración de los cortes de EPM (SAIDI ≈9 h/año) sugiere que **4–5 h de autonomía más FV diurna** cubren la mayoría de los eventos. Debe validarse con los DIU/FIU del circuito.

### 8.6 Ruta de financiación sugerida (C)

| Componente | Fuente principal | Alternativa |
|---|---|---|
| FV + EE en IE, hospital, alcaldía, biblioteca y acueducto | **SGR, Incentivo a la Producción**, tipología "Territorios energéticos" (≤$8.000 M y 2 proyectos), vía OCAD Paz | FENOGE (ConEnergía o solicitud propia, no reembolsable); **OxI con Ecopetrol** |
| BESS de resiliencia (hospital, policía, bomberos) | FENOGE, Findeter (la línea admite almacenamiento) | Gobernación (gestión del riesgo) |
| EMS/IoT/domótica/datos | **MinTIC FUTIC** (dispositivos IoT, SaaS, equipo, capacitación, ingeniería de detalle) + Máxima Velocidad 2026 (reto territorios inteligentes) | Findeter "EE y Conectividad Virtual" (sector TIC) |
| Rural disperso | Reformular el proyecto IP rechazado, más **comunidades energéticas** y FAER | CE innovadoras (Ecopetrol) |
| AP LED con telegestión | IP 2025: línea "AP con FNCER"; Findeter/BID AP | APP o concesión con pago desde el impuesto de AP |
| Compras | No hay AMP de FV vigente: licitación propia (pliegos tipo) o ejecución vía FENOGE. **Nube Pública V** vigente para el hosting. | — |

### 8.7 Fases (S)

| Fase | Plazo | Contenido |
|---|---|---|
| 0 | 0–4 meses | Recolección de facturas por NIU, auditoría energética, levantamiento de cubiertas y estructura, consulta a EPM (capacidad de circuitos y DIU/FIU), formulación en MGA y postulación |
| 1 | 6–15 meses | FV en hospital, acueducto, IE y alcaldía; medición e IoT piloto; EMS básico |
| 2 | 12–24 meses | BESS de resiliencia, BMS, telegestión de AP (piloto de 200 luminarias), integración con la Plataforma CTi País e ISO 50001 |
| 3 | 24–36 meses | Rural (CE y SSFV), análisis de microrred física con EPM y escalamiento de AP |

---

## 9. Riesgos, vacíos y pendientes de verificación

| # | Pendiente | Cómo cerrarlo |
|---|---|---|
| 1 | Consumos reales por sede | Facturas EPM (12 meses) por NIU; inventario de cargas |
| 2 | Operador, contrato e inventario de AP; tarifa del impuesto de AP | Secretaría de Hacienda e Infraestructura de Yondó; SECOP I; EPM |
| 3 | SAIDI/SAIFI y DIU/FIU de los circuitos de Yondó | Solicitud a EPM o Superservicios (SUI) |
| 4 | Capacidad disponible por circuito y transformador (límite del 50 %) | Sistema de información de disponibilidad de red de EPM (CREG 174, art. 7) |
| 5 | Definición de "capacidad instalada" (CA del inversor vs kWp) para el umbral de 100 kW | Texto del art. 3 de la CREG 174 o concepto de la CREG |
| 6 | Valor del MCm vigente para excedentes sobre la importación | Publicaciones de XM y la CREG |
| 7 | Monto IP asignado a Yondó (Res. 40326/2025) y asignaciones directas del SGR | Res. 40326 y Anexo 1 de la Ley 2441 de 2024; Secretaría de Planeación |
| 8 | Costos locales de BESS, EMS, IoT y LoRaWAN | ≥3 cotizaciones; precios de SECOP de proyectos similares |
| 9 | Intensidad energética (kWh/m³) del acueducto de Yondó | Facturas de Aguas y Aseo de Yondó; macromedición |
| 10 | Categoría municipal 2026 y elegibilidad en ConEnergía | Decreto de categorización de Yondó; CGN |
| 11 | Estado de los Ecoparques Del Río y Magdalena; proyectos OxI de Ecopetrol en Yondó | Ecopetrol (Gerencia de Entorno); portal de OxI de la ART |
| 12 | Si el RETIE 2024 remite a la NTC 2050 2.ª actualización | Texto de la Res. 40117/2024, Anexo General |
| 13 | Radiación IDEAM puntual | Visor del Atlas IDEAM |
| 14 | Centros Digitales y conectividad posteriores a 2023 | MinTIC (colombiatic) o Gobernación |

---

## 10. Archivos y datos de soporte

- Respuesta de NASA POWER: archivo de trabajo; respuesta de GSA: archivo de trabajo.
- Tarifas EPM octubre de 2026 (PDF): archivo de trabajo.
- Listados de la Convocatoria IP 2025: archivo de trabajo.
- Boletines FENOGE: archivo de trabajo.
- Catálogo del AMP CCE: archivo de trabajo.
- Guía FUTIC y boletín TIC 2025-T4: archivo de trabajo.
- Scripts de cálculo: archivo de trabajo, archivo de trabajo.

(Las rutas son relativas a `el entorno de trabajo`.)
