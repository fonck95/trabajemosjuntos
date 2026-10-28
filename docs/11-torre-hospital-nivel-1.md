# 11 · Torre de servicios de primer nivel para el Hospital Héctor Abad Gómez

**Demoler las construcciones del antiguo Centro Vida, al lado del hospital, y levantar allí una torre de 4 pisos que cumpla la norma sismorresistente para hospitales y toda la norma de salud, con urgencias, partos, hospitalización, consulta, rayos X, ecografía y un laboratorio clínico de 24 horas con tamizaje. El edificio actual, al que según la E.S.E. no conviene invertirle porque no cumple la norma sismorresistente para un hospital (su estudio de vulnerabilidad de 2024 no es público), pasa a oficinas, archivo, bodega y central de distribución.**

> Estado: **prefactibilidad**, con fecha de corte del 22 de octubre de 2026, actualización del 25 de octubre de 2026 (contraste con el proyecto tipo, plantas por piso, inventario para la habilitación, prediseño estructural con cimentación, simulador sísmico y modelo BIM; detalle en los documentos 14, 15 y 16) y conciliación del 28 de octubre de 2026 con la propuesta integral 2028–2031 (saldo de asignaciones directas al 27 de octubre y fuente de los $5.500 M de la sección 8). Cada cifra dice si es un **dato oficial** (copiado de la fuente), un **cálculo propio** (operación sobre datos oficiales, con el método a la vista) o una **estimación** (supuesto con rango, por confirmar). Pesos constantes de 2026 (IPC del DANE, base enero–septiembre de 2026). Los datos completos están en `data/proyectos/torre_hospital/`: `normas.json` y `proyecto_tipo.json` (norma y proyecto tipo), `programa.json` (demanda y programa por ambiente), `dotacion.json` y `laboratorio.json` (equipos y laboratorio), `presupuesto.json`, `apu.json`, `financiacion.json` y `proyectos.json` (este documento). El modelo 3D está en `data/edificios/torre_hospital.json`.
>
> **La “485”** es la Resolución 485 de 2025 de MinSalud: los requisitos para que el Ministerio (o la Secretaría Seccional de Salud) dé el *concepto técnico de viabilidad* a un proyecto de infraestructura, equipamiento fijo y dotación. La modificaron la Res. 1211 y la Res. 1519 de 2025 (esta última reescribió todo el artículo 7, que es el que rige hoy). El diseño sigue la Res. 1633 de 2025 (marco técnico de edificaciones de salud) y la habilitación, la Res. 3100 de 2019.

## En pocas palabras

- **Por qué una torre y no reforzar.** Un hospital con urgencias es una *edificación indispensable* (grupo IV de la NSR-10): debe seguir funcionando después de un terremoto. El edificio actual funciona desde 1989 (parte en el antiguo hospital de la Shell) y su estudio de vulnerabilidad de 2024 ($182,6 M) no es público. El terremoto de magnitud 7,4 del 10 de agosto de 2026 (epicentro por confirmar: San José del Palmar, Chocó, según la OPS, o Pereira, según la prensa del anexo C; ver 1.2) dejó más de 300 muertos y colapsó parcialmente un ala del Hospital Universitario del Valle: un hospital que se cae no atiende a nadie. Llevar lo asistencial a una torre nueva y dejar el edificio viejo para funciones de apoyo baja el riesgo y evita invertir en un edificio que no cumple.
- **Sí hay proyecto tipo, pero pequeño.** MinSalud y el DNP solo tienen proyectos tipo de **puesto o centro de salud** (MinSalud 2017, 128,5 m²; DNP 2018, 320,6 m²). No existe un “hospital de primer nivel tipo”. La torre **se inspira en el proyecto tipo del DNP** (pórticos de concreto modulares, circulación central con aleros, bioclimática de clima cálido, materiales durables, dotación por ambiente) y se escala con las áreas de la Res. 1633.
- **Frente al proyecto tipo.** La torre equivale a 10,5 veces el puesto tipo del DNP (base: 3.369,6 m² de la torre y 320,6 m² del tipo) y solo 30 % de su área útil tiene un ambiente equivalente en el tipo. De los 18 ambientes con equivalente, 9 mejoran, 4 igual, 4 se apartan y 1 falta; su obra civil cuesta entre 0,8 % y 19,9 % más por m² según el área con que se mida el tipo (cálculo propio, sección 3).
- **Qué tiene.** 3.369,6 m² en 4 pisos (más bloque técnico, residuos y exteriores: 3.620,6 m²). **15 camas** (13 generales y 2 habitaciones de parto TPR), 6 camillas de observación, 15 consultorios, 3 unidades odontológicas, rayos X digital, ecografía, laboratorio de 24 horas, vacunación, farmacia, terapias y una sala de expansión de 8 camillas para emergencias. Hoy (REPS 2022) hay 9 camas, 4 camillas y 13 consultorios.
- **Dotación por servicio frente a la norma.** 1.702 unidades ubicadas una por una en la planta, cada una con su exigencia de la Res. 3100, su clase de riesgo y su registro (Decreto 4725). Para cumplir en dotación e infraestructura faltan 42 ítems: $46,9 M con precio, 12 por cotizar y $4,1 M al año de operación; con ellos, 11 de los 12 servicios que se habilitan quedan sin faltantes exigibles (cálculo propio; sección 5.3 y documento 15). La matriz no revisa talento humano, historia clínica ni interdependencia.
- **Laboratorio con tamizaje.** 55 pruebas en sitio (unas 5.365 al mes) con tiempos de respuesta definidos: urgencias en 60 minutos o menos, rutina en 4 a 6 horas y tamizaje en 24 a 72 horas, incluidos VPH y tuberculosis por PCR, TSH neonatal, HbA1c, sangre oculta, sífilis, VIH, hepatitis, Chagas, toxoplasma y malaria. Los analizadores van en comodato pagado con reactivos. Hoy el hospital paga **$440 M al año** a un laboratorio externo (SECOP, 2025).
- **Qué le pasa en un sismo.** Con el prediseño que cumple la NSR-10 (sistema dual con capacidad moderada de disipación, DMO, para amenaza intermedia), el sismo del nido de Bucaramanga la mueve 0,056 % de la altura de cada piso y el sismo local hipotético bajo Yondó, 0,416 %: queda en ocupación inmediata; lo que sufre son los equipos sueltos y la mampostería (cálculo propio, sección 1.1 y documento 14).
- **Cuánto cuesta.** **$37.137 M** (rango $27.363 M a $50.600 M), sin el ajuste pendiente del prediseño estructural: cumplir la NSR-10 con columnas de 0,80-0,90 m, muros de 0,35 m y 146 pilotes de 15 m cuesta $1.310 M a $1.390 M más de costo directo ($1.742 M a $1.848 M con AIU; sección 6.3). La obra vale $26.228 M con AIU ($19.727 M de costo directo); la dotación, el laboratorio, la TIC y el generador de oxígeno, $5.355 M; estudios, diseños y licencia, $1.832 M; interventoría, $1.836 M; gestión ambiental y social, $45 M; puesta en marcha, $250 M; contingencias, $1.592 M. **$7,24 M de obra por m²** ($5,46 M sin equipos ni solar, casi igual al contrato de obra de Monguí, Boyacá, de 2025, con $5,26 M, y al proyecto tipo del DNP, con $5,42 M). Los jornales ya incluyen la jornada de 42 horas semanales que rige desde julio de 2026.
- **Quién la paga.** Ninguna fuente sola alcanza. Mezcla que cierra la torre (escenario base): MinSalud $12.000 M, regalías $14.037 M (directas e inversión local de Yondó y Asignación para la Paz del OCAD Paz), inversión regional y Gobernación $3.800 M, Obras por Impuestos $2.500 M, crédito $1.500 M y el resto entre FENOGE, MinTIC, municipio, E.S.E. y otros. MinSalud es la fuente más incierta: su inversión propia baja de $2,6 a $1,6 billones en 2027 y el terremoto compite por esa plata. Con los montos *probables* de `docs/06` (MinSalud $3.000 M, Obras por Impuestos $1.800 M, sin crédito) faltan $11.700 M.
- **Cuántos proyectos.** **9**: 7 forman la torre y 2 la complementan (adecuar el edificio actual y una ambulancia medicalizada, $2.613 M). Se pueden presentar en 7 fichas MGA. El primero —estudios y diseños, $1.832 M— cabe hoy en las asignaciones directas de regalías 2025-2026 que el municipio todavía no ha aprobado para proyectos (≈ $7.297 M al 27 de octubre de 2026, cálculo propio con datos de MinHacienda; sección 8).
- **Cuándo.** Diseños en 2027, radicación ante MinSalud entre noviembre de 2027 y abril de 2028, obra de 18 meses desde agosto de 2028 y apertura hacia **abril de 2030**. Con la modalidad llave en mano (Res. 1211) podría abrir a finales de 2029.

## 1. Por qué la torre

| Hecho | Dato | Tipo y fuente |
|---|---|---|
| El hospital es la única IPS con urgencias del municipio | 9 camas, 4 camillas de observación, 13 consultorios, 1 sala de partos, 3 ambulancias básicas | Dato oficial, REPS (corte nov-2022), `programa.json` |
| Población a atender | 22.429 habitantes en 2026 (47 % rural) y 25.550 en 2035 | Dato oficial, DANE |
| Grupo de uso sísmico | Grupo IV (edificación indispensable), coeficiente de importancia 1,5; Yondó tiene amenaza sísmica intermedia (Aa = Av = 0,15) | Dato oficial, NSR-10 A.2.5.1.1 y Apéndice A-4 |
| Edificio actual | En uso desde 1989; estudio de vulnerabilidad sísmica contratado en 2024 por $182,6 M, sin publicar | Dato oficial, SECOP I (`docs/anexos/C-hospital-2028.md`) |
| Terremoto del 10-ago-2026 (magnitud 7,4; epicentro por confirmar, ver 1.2) | 331 muertos y 4.519 heridos (OPS, 3-sep-2026); colapso parcial de un ala del Hospital Universitario del Valle | Dato oficial (OPS) y prensa: [OPS](https://www.paho.org/es/monitoreo-amenazas-naturales/monitoreo-amenazas-naturales-4-septiembre-2026), [Infobae](https://www.infobae.com/colombia/2026/08/11/asi-amanecieron-las-ciudades-mas-afectadas-por-el-terremoto-de-74-que-sacudio-a-colombia-el-10-de-agosto/) |
| Demanda 2035 | 4 a 12 camas generales, 22.500 a 39.400 consultas médicas, 6.400 a 10.200 urgencias y 27.000 a 73.000 pruebas de laboratorio al año | Estimación con rango, `programa.json` |

**La alternativa de reforzar** el edificio actual para grupo IV obligaría a intervenir todo un edificio de un piso, de los años ochenta, con los servicios funcionando adentro, y al final seguiría siendo un edificio viejo con circulaciones y áreas por debajo de la Res. 1633. La torre libera ese edificio para funciones que no son esenciales (oficinas, archivo, almacén, cocina, lavandería, mantenimiento, base de ambulancias), donde la exigencia sísmica es menor. Aun así, el edificio actual necesita la intervención que diga el estudio de 2024 para su nuevo uso (proyecto P8).

### 1.1 ¿Qué le pasa a la torre en un sismo?

- Yondó está en **amenaza sísmica intermedia** (Aa = Av = 0,15) y la torre es **grupo IV** (I = 1,5): el concreto se diseña con **capacidad moderada de disipación de energía (DMO)** y la torre debe quedar sin daño en el sismo frecuente del umbral de daño (NSR-10 A.2.3, A.3 y A.12; numerales por confirmar).
- El prediseño que cumple es **dual**: 5 muros de concreto de 0,35 m en los núcleos de escaleras y pórticos con columnas de 0,80 m (0,90 m en la fachada occidental). Su deriva de diseño es 0,939 % (límite 1 %) y la del umbral de daño, 0,178 % (límite 0,4 %; cálculo propio).
- En el sismo del nido de Bucaramanga como el del 10-mar-2015, la torre se mueve 0,056 % y ningún elemento fluye; en el sismo local hipotético bajo Yondó (Mw 6,0 a 10 km), 0,416 %, con 40 elementos que fluyen dentro de ocupación inmediata; llevado al nivel de diseño de la NSR-10 (hipotético), 0,884 % (cálculo propio con el simulador).
- Lo vulnerable son los contenidos: en el sismo local deslizan 260 equipos sueltos y 6 muros de mampostería tienen daño moderado. Por eso se anclan los equipos y la mampostería va separada de la estructura.
- El simulador, su física, su validación con OpenSees y sus límites están en el **documento 14** (`docs/14-simulacion-sismica.md`). Es un prediseño: no reemplaza el diseño estructural firmado ni el estudio de suelos.

### 1.2 Nota sobre el epicentro del 10 de agosto de 2026

Las fuentes del atlas dan dos epicentros para el terremoto de magnitud 7,4: la OPS (informe del 3-sep-2026) lo ubica en **San José del Palmar (Chocó)** y una nota de El Tiempo citada en el anexo C dice **«epicentro en Pereira»**. El atlas no escoge uno sin fuente primaria (el catálogo del Servicio Geológico Colombiano o del USGS, por confirmar), y tampoco su profundidad ni su tipo de magnitud. Las dos distancias a Yondó (≈ 342 km y ≈ 313 km, cálculo propio) quedan fuera del rango del simulador sísmico, que no lo usa como escenario.

## 2. Qué norma cumple: la lista de chequeo de la Res. 485

La Res. 485 (con el artículo 7 que reescribió la Res. 1519 de 2025) pide estos documentos. Hoy **todos están pendientes**: este estudio es el insumo para producirlos.

| Numeral | Qué pide | Cómo lo cumple la torre | Responsable |
|---|---|---|---|
| 7.1.1.1 | Carta de presentación dirigida a MinSalud con nombre, valor total, entidades que financian, fuentes, montos, tiempo de ejecución e instancia ejecutora. | La firma quien presente el proyecto (E.S.E. Hospital Héctor Abad Gómez o Municipio de Yondó). Debe cuadrar con la matriz de fuentes del proyecto. | Gerente de la E.S.E. / alcalde |
| 7.1.1.2 | Proyecto diligenciado en la Metodología General Ajustada (MGA web). | Formular la torre en MGA con su BPIN: problema (servicios asistenciales en un edificio que no cumple la NSR-10), alternativas (reforzar vs. torre nueva), productos y costos por etapa. | Oficina de planeación municipal / E.S.E. |
| 7.1.1.3 | Concepto técnico de quien presenta: conveniencia y coherencia con el Programa Territorial de Reorganización, Rediseño y Modernización de Redes de E.S.E. (PTRRM) vigente d… | Verificar que el documento de red de Antioquia contemple a Yondó con los servicios de la torre; si no, pedir su ajuste a la Secretaría Seccional de Salud antes de radicar. | E.S.E. + Secretaría Seccional de Salud de Antioquia |
| 7.1.1.4 | Certificación de que el presupuesto incluye todas las actividades y cantidades para la ejecución completa y el cierre financiero, con precios verificados como razonables … | Presupuesto con APU propios y precios de referencia del Magdalena Medio (Barrancabermeja / Gobernación de Antioquia), con fecha. | Entidad que presenta |
| 7.1.1.5 | Certificación de que el personal técnico de la entidad revisó y avala toda la documentación. | Revisión interna (o con apoyo de la Gobernación) antes de radicar. | Entidad que presenta |
| 7.1.1.6 | Inclusión y aprobación en el Plan Bienal de Inversiones Públicas en Salud si el proyecto es de control especial de oferta (art. 4). | La obra de la torre (unos $26.228 millones de 2026, presupuesto.json) supera 5.000 SMMLV ($8.754.525.000, cálculo propio): es de control especial de oferta (art. 4.2) y debe estar en el Plan Bienal. | Secretaría Seccional de Salud de Antioquia |
| 7.1.1.7 | Documento que soporte la cofinanciación de fuentes distintas del PGN. | Certificados de disponibilidad, acuerdos o actos de las fuentes (municipio, Gobernación, SGR, Obras por Impuestos, recursos propios de la E.S.E.). | Cada cofinanciador |
| 7.1.2.1 | Certificado de tradición y libertad del predio (expedido hace menos de 3 meses) o documento equivalente de titularidad. | Establecer quién es dueño del lote del antiguo Centro Vida (¿E.S.E. o municipio?). Si es del municipio, formalizar la transferencia o el título que permita a la E.S.E. construir. | E.S.E. / Secretaría de Hacienda municipal |
| 7.1.2.2 | Certificado de planeación: cumplimiento del EOT/PBOT (uso del suelo y condiciones urbanísticas) y que el predio no está en riesgo no mitigable. | Yondó está a orillas del Magdalena: pedir explícitamente el concepto de amenaza por inundación del lote y su cota frente a las crecientes. | Secretaría de Planeación de Yondó |
| 7.1.2.3 | Certificación de disponibilidad de servicios (agua potable, alcantarillado, energía) o hoja de ruta para proveerlos. | Disponibilidad de acueducto y alcantarillado del prestador municipal y de energía de EPM para la nueva carga (incluida la planta y la solar). | Prestadores de servicios públicos |
| 7.1.2.4 | Documento de Capacidad Instalada concertado entre la E.S.E. y la Subdirección de Prestación de Servicios de MinSalud, en el marco del PTRRM. | Definir camas, camillas, consultorios, salas y equipos de la torre y concertarlo; puede partir de la 'capacidad instalada tipo' que publique MinSalud (parágrafo 1, Res. 1519). | E.S.E. + MinSalud (Subdirección de Prestación de Servicios) |
| 7.1.2.5 | Programa médico arquitectónico con áreas de cada ambiente, servicio y circulaciones. | Usar las áreas mínimas de la Res. 1633 (Anexo 1) y de la Res. 3100 (parámetros de diseño de las normas del atlas). | Arquitecto diseñador |
| 7.1.2.6 | Diseños arquitectónicos (localización, plantas, cubiertas, cortes y fachadas) a escala 1:75, 1:100 o 1:125, acotados, amoblados y firmados con matrícula, que cumplan la n… | Diseño de la torre según Res. 1633 y 3100, NSR-10 Grupo IV y accesibilidad. | Arquitecto con matrícula |
| 7.1.2.8 | Implantación de la propuesta en el levantamiento topográfico con curvas de nivel. | Levantamiento del lote (el prado queda unos 2 m por encima de la vía occidental, según Street View). | Topógrafo + arquitecto |
| 7.1.2.9 | Estudios topográficos y de suelos; diseños estructural, hidrosanitario, contra incendio, eléctrico, redes de voz y datos, y mecánicos (gases medicinales, ventilación), fi… | Estructura Grupo IV (I = 1,5; umbral de daño), rociadores NFPA 13/NTC 2301, RETIE 3.28.3.2, gases medicinales, climatización según Cuadro 4 de la Res. 1633. | Especialistas con matrícula |
| 7.1.2.10 | Presupuesto detallado de obra, fechado y firmado por quien lo elaboró y por el profesional de la entidad que lo revisó. | Presupuesto por capítulos con APU (ver tareas de presupuesto del proyecto). | Presupuestador + profesional de la entidad |
| 7.1.2.11 | Mobiliario dentro del proyecto de infraestructura (solo para servicios exclusivos de primer nivel con desarrollo integral): listado con especificaciones y precios, cuadro… | Aplica si la torre se presenta como desarrollo integral (estudios, diseños y obra) de servicios exclusivos de primer nivel. Ojo: la ecografía es mediana complejidad en la Res. 3100 (servicios de la 3100 en las normas del atlas)… | E.S.E. |
| 7.1.5 | Equipamiento fijo: listado con especificaciones, cantidad, precio, justificación (nuevos servicios o incremento de capacidad), cuadro comparativo, planos con ubicación, c… | Planta eléctrica, transferencias y UPS, ascensor camillero, bombas y tanques, aire acondicionado y ventilación, central o manifold de gases, autoclave, lavachatas, sistema contra incendio. (Las autocl… | E.S.E. + ingeniería |
| 7.1.6 a | Dotación biomédica: listado por servicio con especificaciones, cantidades, precios, cuadro comparativo, justificación con inventario existente, certificación de disponibi… | Dotación de urgencias, parto, hospitalización, consulta, odontología, laboratorio clínico (con tamizaje y analizadores), rayos X, ecografía, esterilización, vacunación y farmacia. Incluir inventario a… | E.S.E. + ingeniero biomédico |
| 7.1.6 b | Dotación TIC: documento de software y hardware con licencias, especificaciones y manuales, plan de implementación y capacitación, listado con cotizaciones (2 marcas) y ce… | Sistema de información del laboratorio (LIS), PACS/RIS para imágenes, red de datos y telemedicina. | E.S.E. + ingeniero de sistemas |
| 7.1.7 | Adecuaciones: certificado de tradición, documento de evaluación del estado de la infraestructura (formato DPSAP), presupuesto aprobado (formato DPSAP); tope de 500 SMMLV … | Solo si se financia aparte la adecuación del edificio actual para archivo, bodega y administración. Tope: 500 SMMLV = $875.452.500 en 2026 (cálculo propio). | E.S.E. |
| 7.1.9 | Estudios y diseños e interventoría como proyecto separado: título, uso de suelo, servicios, Capacidad Instalada aprobada, programa médico arquitectónico, relación de prod… | Ruta recomendable si no hay diseños: un primer proyecto solo para estudios y diseños de la torre. | E.S.E. / municipio |
| 7.1.10 | Telesalud como proyecto propio: listado con cotizaciones, plataforma con certificación de datos, certificación de disponibilidad y modelo de operación (telemedicina artic… | Si la telemedicina se financia aparte (por ejemplo con MinTIC o MinSalud). | E.S.E. |
| 7.1.12 | Llave en mano a precio global fijo sin fórmula de reajuste: título, uso de suelo, servicios, Capacidad Instalada aprobada, estudio del sector, estudio de mercado (3 cotiz… | Ruta alterna a 7.1.2 cuando aún no hay diseños completos: se radica con anteproyecto y el contratista diseña y construye. Exige anteproyecto y memorias sólidas para no quedar corto en el precio global… | E.S.E. / municipio |
| Art. 6 / Art. 5 | Ruta del concepto según la fuente. | Con plata de MinSalud o por Obras por Impuestos: concepto de MinSalud. Solo con plata territorial y por debajo de 5.000 SMMLV: concepto de la Secretaría Seccional de Salud de Antioquia. Con regalías: … | E.S.E. + Gobernación |
| Res. 1633, art. 4 | Transición del marco técnico. | La torre no tiene licencia, concepto ni obra al 11-ago-2025: se diseña con la Res. 1633 completa. | Arquitecto diseñador |

**Control especial de oferta.** La infraestructura y el equipamiento fijo suman $26.228 M, más que el umbral de 5.000 salarios mínimos ($8.755 M en 2026): el proyecto necesita **concepto de MinSalud** y estar en el plan de inversiones del departamento (Plan Bienal o, desde 2025, el **PMIDS** de Antioquia). Cálculo propio.

**Otras normas de diseño** (detalle en `normas.json`): Res. 1633 de 2025 (áreas mínimas, módulo de 1,20 m, corredores de 2,40-2,80 m, climatización por ambiente, adaptación al cambio climático), Res. 3100 de 2019 (estándares de los 13 servicios), NSR-10 títulos A, B, C, H, J y K (sismo en amenaza intermedia con concreto de capacidad moderada de disipación de energía, DMO; cargas; concreto; cimentación; fuego y evacuación: rociadores en todo el edificio), RETIE 2024 y su modificación de 2026 (planta que entra en menos de 10 segundos, UPS en áreas críticas), NTC 2050 sección 517, Índice de Seguridad Hospitalaria de la OPS (reserva de agua y combustible para 72 horas), Res. 591 de 2024 (residuos) y NTC 6047 (accesibilidad).

**Tres choques entre normas y cómo se resolvieron:** reserva de agua (24 h en la 3100, 48 h en la 1633, 72 h en el índice de la OPS: se adopta 72 h); áreas mínimas (se toma siempre la mayor, por ejemplo habitación TPR de 24 m² y no de 16); ecografía (la 3100 la trata como mediana complejidad: hay que decidirlo en el Documento de Capacidad Instalada).

### 2.1 Qué norma de habilitación rige

- **La Res. 3100 de 2019 sigue vigente** «sin solución de continuidad», con sus modificaciones (2215 de 2020, 1317 de 2021, una de 2022, 544 de 2023, 465 de 2025 y 914 de 2025, entre otras). La de 2022 es la 1138 según la investigación de urgencias o la 1410 según las normas del atlas: **por confirmar** en el normograma de Supersalud.
- **La Res. 1732 de 2026** (nuevo manual de habilitación, 5-ago-2026) **fue revocada** en su integridad por la **Res. 2080 del 8-sep-2026** antes de regir; nunca se publicó en el Diario Oficial. Se informa y no se usa como requisito: la torre debe cumplir la 3100 completa desde la visita previa.
- **La Res. 914 de 2025** (manual de reprocesamiento de dispositivos médicos) rige desde el 3-ene-2027 y deroga los numerales de esterilización de la 3100: cambia la central de esterilización antes de la apertura prevista hacia abril de 2030. Sus requisitos quedan por confirmar hasta leer el manual.
- **La Res. 1811 de 2025** (radiaciones ionizantes, desde el 6-mar-2026 según MinSalud) reemplazó a la Res. 482 de 2018: la licencia de rayos X y del periapical, la dosimetría y el control de calidad se tramitan con ella.
- El **Decreto 4725 de 2005** (con los Decretos 3275 de 2009 y 582 de 2017) fija la clase de riesgo, el registro INVIMA, la prohibición de comprar usados IIb y III y el mantenimiento por personal inscrito; la Res. 4816 de 2008, la tecnovigilancia. Detalle, servicio por servicio, en el **documento 15**. Todos los textos vienen de compilaciones vistas por buscador: cotejar con el Diario Oficial antes de radicar.

## 3. El proyecto tipo que la inspira

| Proyecto tipo | Qué es | Qué se toma | Qué no se toma |
|---|---|---|---|
| **Construcción y dotación de infraestructura básica en salud**, DNP con MinSalud, v1.0 (ene-2018, precios de 2017) — [PDF](https://proyectostipo.dnp.gov.co/images/pdf/salud/PTsalud.pdf) | Puesto o centro de un piso, 320,6 m² construidos (269,6 m² en el presupuesto), con presupuesto de $885 M de 2017 ($1.461 M de 2026; $5,4 M por m² presupuestado) | Módulo estructural repetible en pórticos de concreto; circulación central bajo aleros; fachadas largas al norte y al sur, aleros de 1/3 de la altura, ventilación cruzada y árboles al oriente y occidente; concreto a la vista, aluminio natural con vidrio laminado; torre técnica como hito; dotación por ambiente; presupuesto por actividades MGA | Sus normas de base (Res. 4445 de 1996 y 2003 de 2014, derogadas); la luz de 7,60 × 4,30 m (se cambia por 7,20 m, múltiplo del módulo de 1,20 m de la Res. 1633); la cubierta azul (pasa a blanca reflectiva) |
| **Puesto de salud tipo**, MinSalud (2017) — [PDF](https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/VS/PSA/puesto-salud-tipo.pdf) | 128,5 m² en sistema liviano de PVC, sin precios | Dotación mínima por ambiente; 39 % de circulación y muros como piso del factor; muros interiores livianos en seco | El sistema de paneles de PVC (no sirve para un edificio de grupo IV de varios pisos) |
| Proyectos tipo DNP de **ambulancias** (2018) y **cadena de frío** (2016) | Vehículos TAB/TAM y cuarto frío del PAI | Componentes y costos de referencia | Se articulan como proyectos aparte (P9 y opcional) |
| **CAPS** de MinSalud (2023-2025) | Política de centros de atención primaria; sin diseño tipo publicado | La torre como sede principal de la red de Yondó | — |

**Búsquedas sin resultado** (22-oct-2026): no hay “centro de salud tipo” ni “hospital de primer nivel tipo” en la biblioteca de MinSalud; la Gobernación de Antioquia no publica prototipos; las “capacidades instaladas tipo” que prometió la Res. 1211 no están publicadas (`proyecto_tipo.json`).

**Cómo se ve.** Volumen de concreto claro y pañete blanco con aleros y quiebrasoles; base y fachadas en ladrillo terracota que recuerdan las alas que se demuelen; celosías verticales en la fachada occidental; cubierta blanca con paneles solares; el mango grande del prado se conserva y da sombra a la plaza de entrada.

### 3.1 Contraste ambiente por ambiente

De los 40 ambientes comparados, solo **18 tienen un ambiente equivalente en el proyecto tipo** (consulta, odontología, toma de muestras, citologías, dispensación, espera, recepción y apoyo técnico); los otros 22 (urgencias, hospitalización, partos, laboratorio, imágenes, esterilización, vacunación, terapias, telemedicina, bahía y expansión) se comparan solo con el mínimo de la Res. 1633. Por eso cada ambiente lleva **dos veredictos** (cálculo propio; conteos del 24-oct-2026):

| Frente a | Mejora | Cumple igual | Se aparta | Falta | Sin veredicto |
|---|---:|---:|---:|---:|---:|
| El proyecto tipo (18 ambientes con equivalente) | 9 mejoran | 4 igual | 4 se apartan | 1 falta | 22 sin equivalente |
| El mínimo de área de la Res. 1633 (34 ambientes con mínimo) | 15 lo superan | 16 justo en el mínimo | 0 | 3 bajo el mínimo o por confirmar | 6 sin mínimo de área |

La «falta» frente al tipo es un consultorio especializado que el tipo no tiene y que, si hace procedimientos (colposcopia, termoablación), pide 14 m² y tiene 12,96 m². Bajo el mínimo o por confirmar frente a la norma quedan ese consultorio y los ambientes de procesamiento de rayos X y de control y procesamiento de ecografía (Cuadros 22 y 27 de la Res. 1633, por confirmar con equipos digitales). En el recorrido 3D, la capa «Comparar con el proyecto tipo» tiñe los 18 ambientes con equivalente y deja en gris los demás.

### 3.2 Costo por m² y dotación frente al tipo

| Cifra | Valor | Tipo de dato y base de área |
|---|---|---|
| Tamaño | 10,5 veces el puesto tipo y ≈ 56 de sus módulos | Cálculo propio: 3.369,6 m² construidos de la torre frente a 320,6 m² del tipo y módulos de 59,65 m² |
| Área con equivalente en el tipo | 30 % del área útil (601,9 de 2.018,4 m²) | Cálculo propio sobre el área útil de la torre |
| Obra civil por m² | Entre 0,8 % y 19,9 % más que el tipo ($5.462.687 por m² frente a $5.417.624 o $4.555.806) | Cálculo propio: torre sobre 3.620,6 m²; tipo sobre 269,6 m² (presupuesto) o 320,6 m² (construidos) |
| Obra completa por m² (con ascensores, planta, aire, gases, sistemas y solar) | De 1,34 a 1,59 veces el tipo ($7.243.986 por m²) | Cálculo propio, mismas bases |
| Dotación | 21,7 veces la del tipo ($4.294 M frente a $198,1 M) y 2,1 veces por m² | Cálculo propio: 3.369,6 m² de la torre y 320,6 m² del tipo |
| Estructura con cimentación por m² | 1,15 veces el tipo con el presupuesto vigente ($1.767.354) y 1,46 veces con el prediseño que cumple ($2.248.544), frente a $1.541.451 | Cálculo propio: torre con AIU sobre 3.620,6 m²; tipo sobre 269,6 m² |

**Las dos cifras del tipo son la misma obra con dos áreas:** el proyecto tipo cuesta $5,42 M por m² de 2026 sobre los 270 m² de su presupuesto (269,6 m², la cifra que usa la sección 6.2) y $4.555.806 por m² sobre sus 320,6 m² construidos (la que usa el programa); por eso el costo de la obra civil de la torre frente al tipo se publica como rango, de 0,8 % a 19,9 % más (cálculo propio de la investigación del 23-oct-2026, con el IPC como deflactor).

### 3.3 Dónde se aparta y por qué

- **Escala y alcance:** el tipo es un puesto ambulatorio de un piso; la torre es la sede principal de primer nivel del municipio, con urgencias, partos e internación.
- **Norma:** el tipo se diseñó con normas derogadas (Res. 4445 de 1996 y 2003 de 2014); la torre usa la Res. 1633 de 2025 y la 3100 de 2019, y toma siempre la exigencia mayor.
- **Estructura:** se conserva la lógica del tipo (pórticos de concreto modulares sobre una retícula repetible), pero la luz de 7,60 × 4,30 m pasa a 7,20 m (múltiplo del módulo de 1,20 m); el sistema pasa a **dual** con muros de 0,35 m en los núcleos y columnas de 0,80-0,90 m, con capacidad moderada de disipación (DMO); la cimentación superficial pasa a **146 pilotes de 15 m**; las cuantías quedan en 0,74 m³ de concreto y 86,4 kg de acero por m² construido (las del tipo, por confirmar en su PDF); y los entrepisos de 4,20-4,50 m dejan 3,00 m libres bajo el cielo raso. Detalle en el documento 16, sección 13.
- **Lote y clima:** fachadas largas al oriente y al occidente por la forma del lote (con celosías) y 5,3 m de separación con el hospital actual.
- **Inconsistencias señaladas:** quiebrasoles de 0,90 m en el modelo 3D frente a 1,40 m presupuestados, muro cortina del piso 4 sin presupuesto y un posible duplicado del kit de examen ($67,5 M).

## 4. Programa por piso

| Piso | Qué hay | m² útiles | m² construidos |
|---|---|---:|---:|
| 1 | Urgencias (adultos y pediatría, 24 horas) con bahía de ambulancias, rayos X, toma de muestras de laboratorio, vestíbulo y admisiones | 560,8 | 907,2 |
| 2 | Consulta externa (medicina, enfermería, especialistas), laboratorio clínico 24 horas, vacunación, servicio farmacéutico, ecografía y toma de citologías | 559,6 | 907,2 |
| 3 | Hospitalización (adultos, pediatría y obstetricia), atención del parto en habitaciones TPR y central de esterilización | 543,5 | 907,2 |
| 4 | Terapias (física y respiratoria), odontología con rayos X periapical, psicología, nutrición, telemedicina, zona de expansión y coordinación asistencial | 354,5 | 648,0 |
| Afuera | Bloque técnico (subestación de 300 kVA, planta, tableros y baterías, gases, bombas, depósito de cadáveres), residuos, cisternas de 40 m³ de agua potable y ≈ 30 m³ contra incendio, bahía de 2 ambulancias, galería al hospital actual | — | 143,6 + 144,7 cubiertos abiertos |

**Implantación.** Torre de 21,6 × 42,0 m sobre el antiguo Centro Vida, a 5,3 m del bloque central del hospital, unida por una galería cubierta de 3,0 m de ancho al mismo nivel (no hace falta puente porque el hospital actual es de un piso). Urgencias entra por el patio occidental con retorno de ambulancias; el público, por una plaza bajo el mango grande; los servicios (residuos, gases, combustible), por el suroccidente. Índice de ocupación de 0,49 sobre el lote de 2.460 m² (`programa.json`).

**El edificio actual** (≈ 2.300 m²) queda para administración, archivo de historias clínicas, almacén y central de distribución, cocina, lavandería, mantenimiento, base de ambulancias y sede de los equipos extramurales.

### 4.1 Plantas por piso (anteproyecto ilustrativo)

**Planta ilustrativa: el diseño real lo hace el arquitecto con matrícula** (estimación; Res. 485, num. 7.1.2.6). El atlas dibujó todos los recintos del programa sobre la retícula de ejes A-D y 1-7, con los núcleos al oriente y las secciones del prediseño estructural, para poder recorrer la torre en 3D y ubicar la dotación.

| Nivel | Recintos del programa | Circulaciones | Área a ejes | Avisos de área libre |
|---|---:|---:|---:|---:|
| Piso 1 | 82 | 6 | 907,2 m² | 20 |
| Piso 2 | 69 | 6 | 907,2 m² | 12 |
| Piso 3 | 69 | 5 | 907,2 m² | 9 |
| Piso 4 | 42 | 4 | 648,0 m² | 6 |
| Bloque técnico y cubierta | 19 | 5 | — | — |
| Exteriores | 2 | 5 | — | — |

- **Criterios:** módulo de 1,20 m; cada recinto a ejes con al menos el área del programa y el mínimo de la Res. 1633 (0 errores en 283 recintos); puertas del ancho de su categoría (camillas ≥ 1,10 m, NSR-10 K.3.14.2.3); salas de rayos X y periapical plomadas; ventana a fachada o patio en hospitalización, TPR, observación, consultorios y terapias (6 recintos sin ventana, aviso).
- **Zonificación:** urgencias, rayos X, toma de muestras y admisiones en el piso 1; consulta, laboratorio, farmacia, vacunación y ecografía en el 2; hospitalización, partos y esterilización en el 3; terapias, odontología, telemedicina y expansión en el 4. El laboratorio queda sobre la toma de muestras, unido por un montacargas de muestras.
- **Áreas a ejes y libres:** 47 recintos cumplen a ejes pero no con el área libre entre caras de muro (por ejemplo, reanimación con 18,60 m² libres frente a 20 m²): queda por confirmar si la Res. 1633 mide libre o a ejes (lista en el documento 15).
- **Evacuación:** corredores de 2,55 m a ejes (≥ 2,40 m libres, Res. 1633, num. 3.3.6 b.1); la puerta de cada recinto a ≤ 30 m de una salida protegida y cualquier punto a ≤ 45 m. En la sección de las columnas de 0,80 y 0,90 m del prediseño quedan 2,02 a 2,09 m libres (aviso del validador; con las de 0,60 m eran 2,12 a 2,19 m); los 2,80 m recomendados para camillas no caben en la huella.
- **Diferencias con el programa:** puerta principal en la fachada occidental en y = −8,9; sin puerta de servicio en la fachada sur del piso 1 (el servicio entra por el pasaje del bloque técnico); escalera principal abierta en un solo vano entre los ejes 2 y 3 para que ninguna viga cruce sus tramos. Por confirmar con quien apruebe el programa.

### 4.2 Estructura y cimentación (prediseño)

**Prediseño estructural, sin estudio de suelos ni diseño firmado** (cálculo propio; detalle en los documentos 14 y 16):

- **Norma:** Yondó en amenaza sísmica intermedia (Aa = Av = 0,15), grupo de uso IV (I = 1,5), concreto con capacidad moderada de disipación de energía (DMO, NSR-10 C.21); sistema **dual** de la Tabla A.3-4 con R0 = 6,0 y Ω0 = 2,5 (por confirmar) y R = 4,86 por las irregularidades de retroceso y de torsión.
- **Secciones:** columnas de 0,80 × 0,80 m (0,90 × 0,90 m en el eje A de la fachada occidental), vigas de 0,40 × 0,80 m (0,50 × 0,90 m en el eje A), 5 muros de concreto de 0,35 m en los núcleos de escaleras (27,42 m de alma) y losa nervada de 0,45 m, en concreto de 28 MPa con acero de 420 MPa. Con las secciones del presupuesto (columnas de 0,60 m) la deriva llegaba a 2,09 % y no cumplía el 1 %; con estas queda en 0,939 %.
- **Cimentación:** 146 pilotes preexcavados de 0,60 m × 15 m (2.190 m) bajo 20 dados de 3 a 6 pilotes y 2 losas de pilotes bajo los núcleos, 37 vigas de amarre, 5 muros de contención y contrapiso de 0,15 m; capacidad de 632 kN de servicio por pilote con un suelo aluvial supuesto (estimación: la fijan el estudio geotécnico con análisis de licuación y las pruebas de carga).
- **Refuerzo:** despiece de cada elemento con barras N.º 3 a N.º 8 (NTC 2289): 291.285 kg de acero (147.142 kg en la superestructura y 144.143 kg en la cimentación) y 2.483,1 m³ de concreto, es decir 86,4 kg de acero y 0,74 m³ de concreto por m² construido de la torre.

### 4.3 Modelo BIM

El atlas modeló la torre con la metodología BIM: un modelo federado por disciplinas (arquitectura, estructura, cimentación, refuerzo, equipamiento fijo e infraestructura, y dotación) con 4.583 elementos y 64.849 barras, exportado a dos archivos IFC4 georreferenciados (MAGNA-SIRGAS 2018 / Origen-Nacional) y validado sin errores de esquema con IfcOpenShell. Cada elemento lleva su ítem del presupuesto (5D), su fase de obra (4D, dentro del cronograma de la sección 10) y su vínculo con el simulador sísmico. La coordinación bajó las interferencias duras de 280 a 0. Es un **modelo de prefactibilidad: no reemplaza los diseños firmados**. Su plan de ejecución BIM, el nivel de información por disciplina y las cantidades frente al presupuesto están en el **documento 16** (`docs/16-bim-torre.md`).

## 5. Dotación y laboratorio

La dotación biomédica y el mobiliario clínico suman **$4.294 M** (236 líneas de los 15 servicios más 14 de equipamiento fijo (250); 37 de las 236 con precio de referencia de SECOP y el resto estimados con rango). El equipamiento fijo (planta, UPS, ascensores, gases, aire, bombas, redes y sistemas especiales) se presupuesta dentro de la obra con los mismos precios de `dotacion.json` y no se suma dos veces.

| Servicio | Valor | Equipos más costosos |
|---|---:|---|
| Urgencias de baja complejidad | $519 M | Ventilador de transporte; Bomba de infusión volumétrica |
| Consulta externa general y especializada, procedimientos menores y promoción y prevención | $368 M | Kit de examen básico; Equipo de órganos de los sentidos de pared |
| Telemedicina (prestador remisor) | $71 M | Retinógrafo portátil; Estación de telemedicina |
| Odontología general y radiología odontológica | $201 M | Unidad odontológica completa; Rayos X periapical de pared con radiovisiógrafo |
| Toma de muestras de laboratorio clínico | $45 M | Nevera de muestras 2-8 °C con registrador de temperatura; Impresora de etiquetas con código de barras y lector |
| Laboratorio clínico (bienes que compra el hospital) | $357 M | Microscopio binocular con objetivo de inmersión; Cabina de bioseguridad clase II tipo A2 |
| Imágenes diagnósticas: rayos X digital y ecografía | $675 M | Equipo de rayos X digital fijo con detector plano; Ecógrafo multipropósito con 3 transductores |
| Atención del parto de baja complejidad y adaptación neonatal | $470 M | Cama de partos multiposición para habitación TPR; Lámpara de techo LED para atención del parto |
| Hospitalización general de baja complejidad | $397 M | Bomba de infusión volumétrica; Regulador de vacío de pared con frasco |
| Central de esterilización | $365 M | Autoclave de vapor central de carga frontal; Lavadora desinfectora de instrumental |
| Vacunación con cadena de frío | $54 M | Refrigerador de vacunas precalificado OMS; Registradores de temperatura de 30 días y termómetros digitales |
| Servicio farmacéutico | $85 M | Refrigerador grado médico para medicamentos; Refrigerador grado médico para urgencias/dispensación |
| Terapias: fisioterapia y terapia respiratoria | $74 M | Equipo combinado de electroterapia; Banda caminadora terapéutica con pasamanos |
| Sala de expansión para emergencias y desastres (hospital seguro) | $44 M | Monitor de signos vitales básico; Flujómetro de oxígeno con humidificador para la sala de expansión |
| Tecnologías de la información y apoyo general | $570 M | Computador todo en uno con UPS pequeña para puestos asistenciales y administrativos; PACS/RIS para imágenes con licencias y almacenamiento |

### 5.1 Laboratorio clínico de 24 horas con tamizaje

Un bacteriólogo por turno las 24 horas, más uno de día para microbiología, tamizaje y control de calidad. Área de 124 m² en el piso 2, justo encima de la toma de muestras del piso 1 (unidas por un montacargas exclusivo de muestras). Sistema de información del laboratorio (LIS) propio de la E.S.E., con interfaz a la historia clínica.

| Prueba de tamizaje o de ruta | Urgencias | Rutina | Tamizaje | Para qué |
|---|---|---|---|---|
| Hemograma completo | ≤ 60 min desde que llega la muestra | ≤ 4 h | ≤ 24 h | Morbilidad (urgencias, hospitalización, consulta); RIAMP (ingreso y semana 28); RPMS (anemia en adolescentes) |
| Hemoclasificación ABO y Rh | ≤ 60 min desde que llega la muestra | ≤ 6 h | ≤ 24 h | RIAMP (gestante y recién nacido en sangre de cordón); urgencias |
| Gota gruesa para malaria | ≤ 60 min desde que llega la muestra | ≤ 2 h | ≤ 24 h | Vigilancia en salud pública (malaria); RIAMP: tamizaje y gota gruesa mensual a gestantes en zona endémica |
| Glucosa en suero | ≤ 60 min desde que llega la muestra | ≤ 4 h | ≤ 24 h | RPMS (riesgo cardiovascular y metabólico); ruta cardiovascular; RIAMP (glicemia y PTOG 24-28 semanas); morbili… |
| Creatinina en suero | ≤ 60 min desde que llega la muestra | ≤ 4 h | ≤ 24 h | RPMS (riesgo cardiovascular); ruta cardiovascular y renal; morbilidad |
| Perfil lipídico: colesterol total, HDL, triglicéridos y LDL calculado | no aplica | ≤ 6 h | ≤ 24 h | RPMS (riesgo cardiovascular cada 5 años); ruta cardiovascular (anual en crónicos) |
| Relación albúmina/creatinina en orina | no aplica | ≤ 24 h | ≤ 24 h | Ruta cardiovascular y renal (hipertensos y diabéticos, anual) |
| Hemoglobina glicosilada | no aplica | ≤ 48 h | ≤ 48 h | Ruta cardiovascular y metabólica (diabéticos, 3 al año); diagnóstico de diabetes |
| Hormona estimulante del tiroides | no aplica | ≤ 24 h | ≤ 48 h | Morbilidad; gestantes con síntomas; control de tratados |
| TSH neonatal en sangre de cordón | no aplica | no aplica | ≤ 48 h; un resultado alterado se avisa el mismo día a la familia y a la EPS | RIAMP (recién nacido: muestra de cordón, Res. 3280) |
| Antígeno prostático específico | no aplica | ≤ 48 h | ≤ 48 h | RPMS: tamización de oportunidad de cáncer de próstata en hombres de 50 a 75 años cada 5 años o más (con tacto … |
| Toxoplasma IgG | no aplica | ≤ 72 h | ≤ 72 h | RIAMP (primera consulta prenatal y repetición) |
| Toxoplasma IgM | no aplica | ≤ 72 h | ≤ 72 h | RIAMP (Res. 3280: IgM mensual a gestantes seronegativas) |
| Rubéola IgG | no aplica | ≤ 72 h | ≤ 72 h | RIAMP y preconcepción (mujeres no vacunadas, antes de la semana 16) |
| Anticuerpos contra Trypanosoma cruzi | no aplica | ≤ 5 días | ≤ 5 días; los reactivos se confirman en el Laboratorio Departamental con otra técnica | RIAMP (gestantes de zonas endémicas, Res. 3280); vigilancia en salud pública |
| Pruebas confirmatorias o de segunda línea por quimioluminiscencia: VIH Ag/Ac de 4.ª generación, HBsAg, anti-VHC, anticuerpos treponémicos | ≤ 6 h en gestante en trabajo de parto | ≤ 72 h | ≤ 72 h | Algoritmos diagnósticos de VIH, sífilis y hepatitis después de una prueba rápida reactiva; vigilancia en salud… |
| Prueba rápida de VIH 1 y 2 | ≤ 20 min | ≤ 20 min en la consulta | ≤ 20 min en la consulta | RIAMP (cada trimestre y en el parto); RPMS (por exposición); vigilancia en salud pública |
| Prueba treponémica rápida para sífilis | ≤ 20 min | ≤ 20 min | ≤ 20 min | RIAMP (cada trimestre y en el parto si no hubo control); RPMS |
| Prueba no treponémica | ≤ 2 h en el parto | ≤ 24 h | ≤ 24 h | RIAMP (sífilis gestacional, cada trimestre); seguimiento de tratamiento |
| Antígeno de superficie de hepatitis B | ≤ 20 min | ≤ 20 min | ≤ 20 min | RIAMP (primera consulta y parto); RPMS (por exposición) |
| Prueba rápida para hepatitis C | no aplica | ≤ 20 min | ≤ 20 min | RPMS: toda persona de 50 años o más una vez en la vida y transfundidos antes de 1996 (Res. 3280) |
| Sangre oculta en materia fecal inmunoquímica | no aplica | ≤ 48 h | ≤ 48 h | RPMS: tamización de cáncer de colon y recto en personas de 50 años o más cada 2 años (Res. 3280) |
| Hemoglobina capilar | ≤ 5 min | ≤ 5 min | ≤ 5 min | Equipos básicos de salud extramurales; gestantes en zona rural |
| Uroanálisis completo | ≤ 60 min desde que llega la muestra | ≤ 4 h | ≤ 24 h | RPMS (riesgo cardiovascular); ruta cardiovascular; morbilidad; RIAMP |
| Urocultivo con recuento y antibiograma | no aplica | 48-72 h (negativo a las 24 h) | 48-72 h | RIAMP (todas las gestantes y seguimiento); morbilidad |
| Cultivo rectal y vaginal para estreptococo del grupo B | no aplica | 48-72 h | ≤ 72 h | RIAMP (semana 35 a 37, Res. 3280) |
| Baciloscopia | no aplica | ≤ 24 h | ≤ 24 h | Programa de tuberculosis (seguimiento de tratamiento); vigilancia en salud pública |
| Mycobacterium tuberculosis y resistencia a rifampicina por PCR en tiempo real | no aplica | mismo día (unas 80 min por prueba) | ≤ 24 h | Programa de tuberculosis: prueba inicial de todo sintomático respiratorio; vigilancia en salud pública |
| ADN del virus del papiloma humano de alto riesgo con genotipificación 16 y 18/45 | no aplica | no aplica | ≤ 5 días hábiles (corridas 2 veces por semana); la Res. 3280 pide entregar resultados en máximo 15 días | RPMS: tamización obligatoria de cáncer de cuello uterino con ADN-VPH en mujeres de 30 a 65 años, esquema 1-5-5… |

*RIAMP*: Ruta Integral de Atención en Salud Materno Perinatal. *RPMS*: Ruta de Promoción y Mantenimiento de la Salud. Las dos las define la Res. 3280 de 2018 de MinSalud. Tiempos de respuesta propuestos en `laboratorio.json` (estimación de diseño del servicio).

**Volumen y costo.** Unas 5.365 pruebas al mes en sitio (rango 4.247–7.309) y 81 remitidas. Reactivos e insumos: ≈ $679 M al año; personal: ≈ $583 M al año (estimaciones de `laboratorio.json`). Hoy el hospital gasta $672 M de 2026 al año en laboratorio, sobre todo pagando a un laboratorio externo (SECOP I, 2025).

**Modelo de compra recomendado.** Analizadores en **comodato pagado con reactivos** (valor de mercado $956 M: en 7 años sale $822 M más barato que comprarlos, cálculo propio de `laboratorio.json`); la E.S.E. compra lo durable (microscopios, cabina de bioseguridad, centrífugas, neveras, autoclave); el GeneXpert se pide al programa nacional de tuberculosis. Indicadores: 90 % o más de urgencias en 60 minutos, menos de 2 % de muestras rechazadas, 100 % de valores críticos avisados en 30 minutos, 100 % de mujeres con VPH positivo contactadas en 2 semanas.

### 5.2 Inventario para la habilitación

Cada línea de la dotación, del equipamiento fijo y del laboratorio se convirtió en unidades físicas ubicadas en su recinto de la planta: **1.702 unidades** en 270 recintos (946 de dotación, 611 de infraestructura, 17 de equipamiento fijo, 12 analizadores y 114 del cierre de brechas; cálculo propio). Cada unidad dice qué exigencia de la Res. 3100 cubre (con su numeral y su nivel de verificación), su clase de riesgo y si requiere registro INVIMA (Decreto 4725), su mantenimiento y su anclaje sísmico, y se puede ver e inspeccionar en el recorrido 3D. La matriz de **cumplimiento en dotación e infraestructura** cruza las 199 exigencias normalizadas con el inventario, servicio por servicio y en dos cortes (23-oct-2026 con la 3100 y la apertura con la Res. 914): no revisa talento humano, historia clínica ni interdependencia, así que no dice si un servicio se puede habilitar. Matriz, clases de riesgo revisadas y obligaciones del prestador en el **documento 15** (`docs/15-dotacion-y-habilitacion.md`).

### 5.3 Cierre de brechas

Lo que falta para cumplir en dotación e infraestructura va aparte, **sin tocar los totales de la dotación ni el presupuesto** (cálculo propio):

| Proyecto | Habilitación | Recomendado | Por confirmar | Total con precio |
|---|---:|---:|---:|---:|
| P4 · Dotación | $8.375.000 | $22.194.906 | $12.696.000 | $43.265.906 |
| P5 · Laboratorio | $350.000 | $0 | $3.289.000 | $3.639.000 |
| P6 · Sistemas de información | $0 | $0 | $0 | $0 |

- **42 ítems**, $46.904.906 con precio (rango $36.009.906 a $61.999.906) y **12 ítems** por cotizar (sin precio y sin sumar cifras supuestas).
- **Operación anual aparte:** $4.100.000 al año de dosimetría personal (el control de calidad de rayos X después del primer año, por cotizar); no se suma a la inversión.
- **Cómo se financia:** cada ítem dice su proyecto. Mientras no se actualice el presupuesto, podría salir de la contingencia de su proyecto (P4: $175 M; P5: $26 M), **pero usar la contingencia reduce la reserva para el riesgo de cantidades y precios**. La operación anual no se paga con contingencias.
- **GeneXpert:** si no lo entrega el programa nacional de tuberculosis, es un costo no presupuestado de **$144,0 M** si se compra.
- Con el cierre, 11 de los 12 servicios que se habilitan quedan sin exigencias exigibles que falten o estén en parte; el que no, consulta externa, depende de si la E.S.E. habilita la modalidad extramural. Lista completa en el documento 15.

## 6. Presupuesto por capítulos

Presupuesto de prefactibilidad (clase 4: precisión esperada de −25 % a +35 %). Las cantidades salen del programa con rendimientos por m² escritos en cada ítem de `presupuesto.json` (por ejemplo: 0,36 m³ de concreto y 62 kg de acero por m² de placa; 0,33 ml de muro por m²; un rociador cada 9 m²).

| # | Capítulo | Costo directo | Peso | Con AIU |
|---|---|---:|---:|---:|
| 1 | Preliminares, campamento y demolición del antiguo Centro Vida | $572 M | 2,9 % | $760 M |
| 2 | Movimiento de tierras y cimentación | $1.917 M | 9,7 % | $2.549 M |
| 3 | Estructura en concreto reforzado (NSR-10, grupo IV, coeficiente de importancia 1,5) | $2.896 M | 14,7 % | $3.850 M |
| 4 | Mampostería, muros y fachadas | $1.414 M | 7,2 % | $1.880 M |
| 5 | Cubiertas e impermeabilización | $278 M | 1,4 % | $370 M |
| 6 | Pisos, acabados hospitalarios y cielos rasos | $1.905 M | 9,7 % | $2.533 M |
| 7 | Carpintería metálica y de madera, puertas y vidrios | $1.252 M | 6,3 % | $1.664 M |
| 8 | Instalaciones hidrosanitarias, agua caliente y aguas lluvias | $910 M | 4,6 % | $1.210 M |
| 9 | Red contra incendio (NSR-10 títulos J y K; NFPA 13, 14 y 20; NTC 2301) | $634 M | 3,2 % | $842 M |
| 10 | Instalaciones eléctricas, iluminación y sistema eléctrico esencial (RETIE 2024 y 2026, NTC 2050 sección 517, RETILAP) | $2.352 M | 11,9 % | $3.127 M |
| 11 | Voz, datos y comunicaciones | $361 M | 1,8 % | $480 M |
| 12 | Gases medicinales | $575 M | 2,9 % | $765 M |
| 13 | Aire acondicionado y ventilación mecánica (Res. 1633, Cuadro 4) | $1.558 M | 7,9 % | $2.072 M |
| 14 | Ascensores y montacargas | $780 M | 4,0 % | $1.037 M |
| 15 | Sistemas especiales | $520 M | 2,6 % | $692 M |
| 16 | Galería de conexión con el edificio actual y pasaje de servicio | $78 M | 0,4 % | $104 M |
| 17 | Urbanismo, bahía de ambulancias, parqueaderos, cerramiento, bloque técnico y residuos | $682 M | 3,5 % | $907 M |
| 18 | Paisajismo y arborización | $60 M | 0,3 % | $80 M |
| 19 | Solar fotovoltaica, baterías y conexión con la microrred | $982 M | 5,0 % | $1.306 M |
| | **Costo directo** | **$19.727 M** | 100 % | |
| | Administración (24 %) | $4.735 M | | |
| | Imprevistos (3 %) | $592 M | | |
| | Utilidad (5 %) e IVA sobre la utilidad (19 %) | $1.174 M | | |
| | **Valor de la obra** | | | **$26.228 M** |

**La administración de 24 % incluye** el personal de dirección (9 %), servicios y ensayos (2 %), pólizas (1 %), la **contribución de 5 % sobre los contratos de obra pública** de la Ley 1106 de 2006, permanente desde la Ley 1738 de 2014 (5 % del contrato sin IVA ≈ 6,6 % del costo directo), estampillas (2,5 %, por verificar), ICA de Yondó (0,8 %) y gastos generales (2 %). Estimación.

### 6.1 Lo que va por fuera de la obra

| Componente | Valor | Cómo se calculó |
|---|---:|---|
| Estudios y diseños | $1.450 M | Topografía, geotecnia con análisis de licuación, diseños arquitectónico (2,0 % de la obra), estructural (0,7 %), técnicos (1,6 %), presupuesto (0,3 %) e interventoría de diseños (8 %) |
| Formulación y licencia | $382 M | Documento de Capacidad Instalada, estudio de mercado y MGA ($120 M) y licencia (1 % de la obra, por verificar) |
| Interventoría de obra | $1.836 M | 7 % del valor de obra con IVA, con la supervisión técnica independiente de la Ley 1796 de 2016 |
| Gestión ambiental y social | $45 M | Permiso forestal, plan de manejo ambiental y socialización |
| Dotación | $3.251 M | `dotacion.json`: todos los servicios menos laboratorio, toma de muestras y TIC |
| Laboratorio clínico | $523 M | Equipos propios del laboratorio y la toma de muestras + puesta en marcha (2 meses de reactivos, validación, control externo) |
| Sistemas de información | $931 M | Computadores, PACS/RIS y telemedicina de `dotacion.json` + LIS, interoperabilidad y ciberseguridad |
| Equipamiento fijo fuera de la obra | $650 M | Generador de oxígeno PSA (recomendado) |
| Puesta en marcha y habilitación | $250 M | Traslado, aseo terminal, licencia de rayos X, habilitación en el REPS, capacitación e inventario de 72 h |
| Contingencias | $1.592 M | 5 % de obra, dotación y equipos (no cubre inflación) |
| **Total de la torre** | **$37.137 M** | Rango $27.363 M–$50.600 M (suma de mínimos y máximos de cada ítem) |

**Para no contar dos veces:** la planta, la UPS, los ascensores, la central de gases, el aire acondicionado, las bombas, la red de datos y los sistemas especiales están en la obra con el mismo precio de `dotacion.json`; los analizadores del laboratorio van en comodato; la lavandería va con el edificio actual; y la solar, las baterías y el BMS de la torre se cuentan aquí, así que el proyecto de la microrred (`data/presupuesto_microrred.json`) debe descontar el nodo hospital.

### 6.2 ¿Es caro o barato? Comparación por m²

Valor de obra por m² construido: **$7,24 M** (rango $5,68 M–$9,48 M), sin el ajuste pendiente del prediseño estructural (sección 6.3). Sin el equipamiento fijo ni la solar: **$5,46 M**. Costo total por m² (con dotación, diseños, interventoría y contingencias): $10,26 M. Todo sobre los 3.620,6 m² construidos del proyecto (cálculo propio).

| Proyecto | Año | Área | Costo por m² en pesos de 2026 | Qué incluye | Fuente |
|---|---|---:|---:|---|---|
| Proyecto tipo DNP-MinSalud de infraestructura básica en salud (puesto o centro de un piso) | 2017 | 270 m² | $5,42 M | Costo directo con AIU teórico y exteriores; sin dotación ni interventoría | [enlace](https://proyectostipo.dnp.gov.co/images/pdf/salud/PTsalud.pdf) |
| Nueva infraestructura de la E.S.E. Hospital Las Mercedes de Monguí (Boyacá): urgencias, hospitalización, partos y laboratorio | 2025 | 2.400 m² | $5,26 M | Contrato de obra firmado el 16-abr-2025 (20 meses) por $11.966.541.300, adjudicado en SECOP II; sin interventoría ni dotación. El área de 2.400 m² es la que publicó la prensa sectorial con datos de MinSalud. Verificación V2: antes se usaba la 'inversión superior a $13 mil millones' de la prensa. | [enlace](https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.7482028) |
| Nuevo Hospital Sagrado Corazón de Jesús de Quimbaya (Quindío): urgencias, hospitalización, partos, radiología y toma de muestras, 2 pisos | 2025 | 4.456 m² | $6,69 M | Proyecto de regalías (AIR 40 %) aprobado por el OCAD Eje Cafetero en julio de 2025, con viabilidad técnica de MinSalud (dic-2024, según la prensa sectorial). Su producto MGA es 'Hospitales de primer nivel de atención construidos y dotados' (BPIN 2024000040010); los estudios y diseños se pagaron aparte en 2020 (BPIN 2019000040001, $838,6 millones). No se publica cuánto es dotación. | [enlace](https://www.dnp.gov.co/Prensa_/Noticias/Paginas/regalias-apuestan-salud-quindio-28-mil-millones-nuevo-hospital-quimbaya.aspx) |
| Nuevo hospital de primer nivel de Pasacaballos (Cartagena), tipo C: urgencias, partos, quirófano, hospitalización y consulta | 2026 | 4.500 m² | $10,75 M | Inversión estimada con construcción y dotación, con regalías; en trámite (sin contrato a oct-2026). Solo sirve como referencia de orden de magnitud. | [enlace](https://www.eluniversal.com.co/cartagena/2026/07/30/asi-va-el-proceso-para-financiar-el-nuevo-hospital-de-pasacaballos/) |
| Hospital Santa Catalina de Sena, Sucre (Sucre), Fondo Adaptación: urgencias, consulta, laboratorio, imágenes, partos, hospitalización | 2017 | 2.032 m² | $4,80 M | Obra (la interventoría de $681,7 millones va aparte); edificio bajo | [enlace](https://www.eluniversal.com.co/regional/2017/10/13/comenzara-construccion-del-nuevo-hospital-de-sucre-con-millonaria-inversion/) |
| Hospital de Fusagasugá (Cundinamarca), Gobernación: mediana y alta complejidad | 2026 | 24.966 m² | $9,29 M | Inversión total anunciada; complejidad mayor que la torre; cifra tomada del extracto del buscador (el artículo respondió con error 403) | [enlace](https://cambiocolombia.com/contenido-especial/articulo/2026/9/cundinamarca-amplia-su-red-publica-de-salud-con-nuevos-hospitales-y-mas-dotacion-tecnologica) |
| Reposición del hospital de Guarne (Antioquia), MinSalud, CONPES 4169 | 2026 | no publicada | — (total $35.059 M) | Aporte de MinSalud con vigencias futuras hasta 2030; obra de ≈ 19 meses; área no publicada | [enlace](https://www.elcolombiano.com/antioquia/guarne-antioquia-nuevo-hospital-millones-ministerio-de-salud-EG36212125) |
| Construcción de la infraestructura física de la E.S.E. Álvaro Ramírez González, San Martín (Cesar) | 2024 | no publicada | — (total $34.119 M) | Valor adjudicado en SECOP II (15 meses); área no publicada | [enlace](https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.5438578) |
| Hospital de Majagual (Sucre): urgencias, consulta, obstetricia, cirugía ambulatoria, laboratorio | 2025 | no publicada | — (total $26.034 M) | Inversión total (Fondo Adaptación, MinSalud, Gobernación, Alcaldía y E.S.E.); 18 meses | [enlace](https://www.elheraldo.co/sucre/2025/10/30/arranca-construccion-de-un-hospital-en-la-mojana-de-sucre/) |

**Lectura.** Hay dos comparables con cifra oficial y área: el **contrato de obra de Monguí** (SECOP II, 2025: $5,26 M por m²) y el **proyecto de Quimbaya** aprobado por el OCAD con viabilidad de MinSalud (2025: $6,69 M por m², construido y dotado, con los diseños pagados aparte). La obra civil de la torre ($5,46 M) queda 4 % por encima de Monguí y 1 % por encima del proyecto tipo del DNP: es razonable para un edificio de 4 pisos con pilotes en Yondó. Con ascensores, planta, aire acondicionado, gases, sistemas especiales, solar y baterías, la obra completa sube a $7,24 M. Frente a Quimbaya, la torre sin diseños ni contingencias ($9,31 M) es 39 % más cara por m²: la diferencia se explica por los 4 pisos con 2 ascensores camilleros, los pilotes, la solar con baterías ($1.734 M), el laboratorio de 24 horas y la dotación completa; no se sabe cuánta dotación incluye Quimbaya. Pasacaballos (2026, con dotación, sin contratar) da $10,75 M por m², un poco más que el costo total de la torre ($10,26 M). Santa Catalina de Sena (2017, edificio bajo) queda por debajo. Sobre el proyecto tipo: sus $5,42 M por m² son sobre los 270 m² (269,6 m²) de su presupuesto; sobre sus 320,6 m² construidos el mismo costo da $4.555.806 por m² (la cifra que usa el programa), y frente a esa base la obra civil de la torre queda 19,9 % por encima en lugar de 0,8 % (sección 3.2). El orden de magnitud que se había estimado escalando el proyecto tipo DNP ($7,0–9,8 M por m², `proyecto_tipo.json`) contiene la obra completa. Los totales de Guarne ($35.059 M), San Martín, Cesar ($34.119 M de 2026) y Majagual ($26.034 M de 2026) muestran que un hospital de primer nivel nuevo cuesta hoy entre $25.000 y $40.000 M. Cálculo propio (verificación V2).

### 6.3 Ajuste pendiente del prediseño estructural

**Por qué cambia.** El presupuesto supuso columnas de 0,60 × 0,60 m, vigas de 0,40 × 0,60 m, ≈ 45 m de muro de 0,30 m y ≈ 100 pilotes de 12 m bajo 28 dados. Con esas secciones, el modelo sísmico del prediseño daba una deriva de diseño de **2,09 %**, el doble del 1 % de la NSR-10 (Tabla A.6.4-1). El prediseño que cumple (sección 4.2) lleva las columnas a 0,80-0,90 m, los muros a 0,35 m y la cimentación a **146 pilotes de 15 m** con losas de pilotes bajo los núcleos: la deriva baja a 0,939 % (documentos 14 y 16).

**Cuánto cambia** (cálculo propio con los valores unitarios del presupuesto y las cantidades del prediseño y del modelo BIM):

| Concepto | Con las cantidades del prediseño | Con las cantidades del modelo BIM |
|---|---:|---:|
| Cimentación (capítulo 2): más pilotes, dados y losas de pilotes y acero | $1.475.809.519 | $1.519.090.018 |
| Estructura (capítulo 3): más columnas y escaleras, menos losa nervada, muros y acero | −$165.394.504 | −$128.898.001 |
| **Costo directo** | **$1.310.415.015** (6,6 % del costo directo de la obra) | **$1.390.192.017** (7,0 %) |
| **Con AIU** (factor 1,3295) | **$1.742.196.762** | **$1.848.260.287** |
| Valor de la obra (hoy $26.228 M) | $27.970 M | $28.076 M |
| Con interventoría (7 %), contingencia (5 %) y diseños y licencia (≈ 6,0 %) proporcionales | ≈ $2.055 M más: total de la torre ≈ $39.193 M | ≈ $2.180 M más: total ≈ $39.318 M |

**Efecto.** El capítulo de estructura y cimentación pasa de $4.813 M a $6.123-6.203 M de costo directo (+27 % a +29 %); la obra de la torre (P2) sube $1.742 M a $1.848 M con AIU y la brecha de financiación de la sección 8 crece en esa cifra. **El presupuesto no se edita en esta versión:** queda como ajuste pendiente con estas cifras, para hacerlo con el diseño estructural y el estudio geotécnico (que pueden mover el número y el largo de los pilotes en los dos sentidos). La diferencia entre las dos columnas es de medición (el modelo mide la geometría de cada elemento y las barras dibujadas; el prediseño, espesores equivalentes sobre el área a ejes); detalle por ítem en el documento 16, sección 9.

## 7. Análisis de precios unitarios (APU) destacados

`apu.json` trae 19 APU completos. Precios oficiales de Antioquia: la **Base de APU de la Secretaría de Infraestructura Física de la Gobernación (2020-II)**, la más reciente descargable en su sitio, con la mano de obra actualizada por el **salario mínimo** (×1,9946: pasó de $877.803 a $1.750.905) y por la **jornada de 42 horas semanales** que rige desde el 15 de julio de 2026 (Ley 2101 de 2021; la base de 2020 suponía 48 horas: ×1,1429, factor total ×2,2796), y equipos y materiales por **IPC** (×1,5054); y las **compras de 2025-2026 de la Gobernación de Antioquia en la Tienda Virtual del Estado** (cemento a $32.896 el bulto, pintura epóxica antibacterial a $196.577 el galón, cable libre de halógenos a $2.687 el metro, entre otros). Jornal con prestaciones: ayudante $134.688, oficial $269.373, oficial especializado $326.836 (cálculo propio).

| APU | Ítem | Unidad | Materiales | Equipo | Mano de obra | Transporte y otros | Costo directo | Con AIU |
|---|---|---|---:|---:|---:|---:|---:|---:|
| APU-01 | Demolición de edificación de un piso (mampostería, estructura de concreto, pisos y cimientos) | m2 | $0 | $22.995 | $35.917 | $30.773 | **$89.685** | $119.236 |
| APU-02 | Retiro de cubierta de teja de fibrocemento con posible asbesto, embalaje y disposición como residuo peligroso | m2 | $11.958 | $12.000 | $24.336 | $32.717 | **$81.011** | $107.705 |
| APU-03 | Excavación mecánica en material común para cimentación y cisternas (hasta 3 m), con cargue y retiro | m3 | $0 | $15.048 | $17.958 | $38.568 | **$71.574** | $95.158 |
| APU-04 | Concreto de 28 MPa para columnas y muros estructurales (pórticos y núcleos, NSR-10 grupo IV) | m3 | $750.366 | $174.194 | $344.141 | $29.378 | **$1.298.079** | $1.725.796 |
| APU-05 | Concreto de 28 MPa para vigas y losa nervada de entrepiso y cubierta | m3 | $741.302 | $185.082 | $280.918 | $26.217 | **$1.233.519** | $1.639.964 |
| APU-06 | Acero de refuerzo fy = 420 MPa (grado 60) figurado y amarrado | kg | $5.012 | $45 | $2.615 | $408 | **$8.080** | $10.742 |
| APU-07 | Pilote preexcavado de 0,60 m de diámetro en concreto de 28 MPa | ml | $223.440 | $250.635 | $44.715 | $13.247 | **$532.037** | $707.343 |
| APU-08 | Muro en bloque de arcilla No. 5 (e = 15 cm) con refuerzo y anclaje a la estructura | m2 | $74.485 | $2.500 | $44.896 | $14.245 | **$136.126** | $180.979 |
| APU-09 | Muro liviano en placa de yeso resistente a humedad, doble cara, con aislamiento acústico | m2 | $93.717 | $1.500 | $33.672 | $7.934 | **$136.823** | $181.907 |
| APU-10 | Pintura epóxica antibacterial (2 manos) sobre estuco y sellador, en muros de áreas asistenciales | m2 | $29.138 | $800 | $20.203 | $1.260 | **$51.401** | $68.337 |
| APU-11 | Piso vinílico heterogéneo hospitalario de 2 mm con mediacaña sanitaria y autonivelante | m2 | $177.360 | $3.000 | $31.080 | $3.679 | **$215.119** | $286.002 |
| APU-12 | Cielo raso registrable en fibra mineral de alta higiene 61 × 61 cm con perfilería suspendida y arriostramiento sísmico | m2 | $79.570 | $1.000 | $18.366 | $2.418 | **$101.354** | $134.751 |
| APU-13 | Ventanería en aluminio anodizado natural con vidrio laminado de seguridad 4+4 mm | m2 | $360.550 | $0 | $76.921 | $10.096 | **$447.567** | $595.040 |
| APU-14 | Impermeabilización de cubierta plana con aislamiento térmico y acabado blanco reflectivo | m2 | $131.035 | $2.000 | $36.365 | $3.818 | **$173.218** | $230.294 |
| APU-15 | Red de gases medicinales en tubería de cobre tipo K desengrasada (oxígeno, aire medicinal y vacío) | ml | $83.753 | $8.358 | $30.768 | $1.838 | **$124.717** | $165.812 |
| APU-16 | Ducto de aire acondicionado y extracción en lámina galvanizada con aislamiento térmico | kg | $13.260 | $600 | $7.692 | $660 | **$22.212** | $29.531 |
| APU-17 | Salida para tomacorriente normal doble con polo a tierra 20 A en tubería EMT y cable libre de halógenos | un | $146.001 | $1.000 | $76.921 | $4.596 | **$228.518** | $303.815 |
| APU-18 | Salida para tomacorriente grado hospitalario del sistema eléctrico esencial (regulada, con tierra aislada) | un | $210.751 | $1.000 | $92.305 | $5.490 | **$309.546** | $411.541 |
| APU-19 | Punto hidráulico de agua fría en PVC presión de 1/2" con válvula de paso | un | $51.874 | $0 | $76.921 | $4.346 | **$133.141** | $177.011 |

**APU-04 · Concreto de 28 MPa para columnas y muros estructurales (pórticos y núcleos, NSR-10 grupo IV) (m3)**

| Componente | Cantidad | Precio | Valor | Fuente |
|---|---:|---:|---:|---|
| Concreto premezclado de 28 MPa (4.000 psi) puesto en Yondó | 1,000 m3 (+5 %) | $700.000 | $735.000 | estimacion |
| Curador de concreto tipo antisol blanco | 1,120 kg (+0 %) | $9.702 | $10.866 | calculo_propio sobre dato oficial |
| Desmoldante para formaleta | 0,500 l (+0 %) | $9.000 | $4.500 | estimacion |
| Vibrador de concreto | rend. 5,92 | $80.658/día | $13.625 | calculo_propio sobre dato oficial |
| Formaleta metálica para columnas y muros | rend. 0,71 | $96.796/día | $135.569 | calculo_propio sobre dato oficial |
| Bomba de concreto o elevación con winche y balde | 1,000 | $25.000/m3 | $25.000 | estimacion |
| Cuadrilla de concretos (equivale a 1 oficial + 1 ayudante entendido + 4 ayudantes rasos ($431.310/día en la base SIF 2020)) | rend. 2,86 m3/día | $983.212/día | $344.141 | cálculo propio |
| Herramienta menor (5 % de la mano de obra) | | | $17.207 | método SIF |
| Acarreo interno (1,05 m³) | | | $12.171 | cálculo propio |
| Incluido en el precio del material puesto en Yondó (el concreto premezclado ya trae ≈ $40.000/m³ de transporte desde la planta de Barrancabermeja) | | | $0 | estimación |
| **Costo directo** | | | **$1.298.079** | |
| AIU (24 % + 3 % + 5 % + IVA del 19 % sobre la utilidad) | | | $427.717 | |
| **Precio unitario** | | | **$1.725.796** | |

*Comparación:* SIF 2020-II ítem 6.2.30, concreto de 28 MPa en vigas y columnas: $735.062/m³; × IPC = $1.106.548. El APU es más alto porque la mano de obra se actualiza con el salario mínimo (que subió casi el doble desde 2020) y con la jornada de 42 horas, no con el IPC. Con la misma regla de este presupuesto (mano de obra × 2,2796 y el resto × IPC) el ítem SIF da $1.223.428/m³; el APU queda por encima por el concreto puesto en Yondó y la bomba.

**APU-06 · Acero de refuerzo fy = 420 MPa (grado 60) figurado y amarrado (kg)**

| Componente | Cantidad | Precio | Valor | Fuente |
|---|---:|---:|---:|---|
| Acero corrugado G-60 (fy = 420 MPa) figurado | 1,000 kg (+5 %) | $4.600 | $4.830 | estimacion |
| Alambre negro recocido calibre 18 | 0,030 kg (+0 %) | $6.050 | $182 | calculo_propio sobre dato oficial |
| Cizalla y dobladora | 3,000 | $15/kg | $45 | calculo_propio sobre dato oficial |
| Cuadrilla de refuerzo (equivale a 1 oficial + 1 ayudante entendido ($118.167 + $76.809 en la base SIF 2020)) | rend. 170,00 kg/día | $444.466/día | $2.615 | cálculo propio |
| Herramienta menor (5 % de la mano de obra) | | | $131 | método SIF |
| Transporte interno | | | $151 | cálculo propio |
| Flete del acero desde Barrancabermeja o Bucaramanga | | | $126 | estimación |
| **Costo directo** | | | **$8.080** | |
| AIU (24 % + 3 % + 5 % + IVA del 19 % sobre la utilidad) | | | $2.662 | |
| **Precio unitario** | | | **$10.742** | |

*Comparación:* SIF 2020-II ítem 10.1: $4.478/kg; × IPC = $6.741/kg. Del mismo orden; la diferencia es la mano de obra actualizada con el salario mínimo y la jornada de 42 horas (el ítem SIF con esa regla da $7.629/kg).

**APU-11 · Piso vinílico heterogéneo hospitalario de 2 mm con mediacaña sanitaria y autonivelante (m2)**

| Componente | Cantidad | Precio | Valor | Fuente |
|---|---:|---:|---:|---|
| Piso vinílico heterogéneo hospitalario en rollo de 2 mm (tráfico intenso, antibacterial) | 1,000 m2 (+10 %) | $125.000 | $137.500 | estimacion |
| Mortero autonivelante cementicio | 5,000 kg (+0 %) | $4.800 | $24.000 | estimacion |
| Imprimante para autonivelante | 0,150 l (+0 %) | $20.000 | $3.000 | estimacion |
| Adhesivo acrílico para pisos vinílicos | 0,350 kg (+0 %) | $22.000 | $7.700 | estimacion |
| Cordón de soldadura para vinilo | 1,200 ml (+0 %) | $1.800 | $2.160 | estimacion |
| Perfil soporte de mediacaña | 0,500 ml (+0 %) | $6.000 | $3.000 | estimacion |
| Lijadora de piso, mezcladora y soldadora de vinilo | rend. 30,00 | $90.000/día | $3.000 | estimacion |
| Instalador especializado de vinilo (1 oficial especializado + 1 ayudante) | rend. 22,00 m2/día | $461.524/día | $20.978 | cálculo propio |
| Preparación de base y autonivelante (1 oficial + 1 ayudante) | rend. 40,00 m2/día | $404.061/día | $10.102 | cálculo propio |
| Herramienta menor (5 % de la mano de obra) | | | $1.554 | método SIF |
| Flete de vinilo y autonivelante desde Medellín o Bogotá | | | $2.125 | estimación |
| **Costo directo** | | | **$215.119** | |
| AIU (24 % + 3 % + 5 % + IVA del 19 % sobre la utilidad) | | | $70.883 | |
| **Precio unitario** | | | **$286.002** | |

**APU-02 · Retiro de cubierta de teja de fibrocemento con posible asbesto, embalaje y disposición como residuo peligroso (m2)**

| Componente | Cantidad | Precio | Valor | Fuente |
|---|---:|---:|---:|---|
| Plástico de polietileno de 200 micras | 2,200 m2 (+5 %) | $1.800 | $4.158 | estimacion |
| Overol desechable tipo 5/6 para trabajo con asbesto | 0,100 un (+0 %) | $25.000 | $2.500 | estimacion |
| Par de filtros P100 para respirador de media cara | 0,100 par (+0 %) | $45.000 | $4.500 | estimacion |
| Agua con surfactante, cinta y rótulos de residuo peligroso | 1,000 m2 (+0 %) | $800 | $800 | estimacion |
| Aspiradora industrial con filtro HEPA | 0,025 | $120.000/día | $3.000 | estimacion |
| Andamio o plataforma de trabajo en altura | 0,030 | $50.000/día | $1.500 | estimacion |
| Monitoreo de fibras en aire (muestreo personal y ambiental, laboratorio acreditado) | 0,001 | $6.000.000/global/800 m² | $7.500 | estimacion |
| Cuadrilla capacitada en asbesto y alturas (1 oficial + 3 ayudantes) | rend. 40,00 m2/día | $673.437/día | $16.836 | cálculo propio |
| Profesional de seguridad y salud en el trabajo (1 profesional) | rend. 40,00 m2/día | $300.000/día | $7.500 | cálculo propio |
| Herramienta menor (5 % de la mano de obra) | | | $1.217 | método SIF |
| Transporte especializado y disposición en celda de seguridad (≈ 15 kg de teja por m²) | | | $31.500 | estimación |
| **Costo directo** | | | **$81.011** | |
| AIU (24 % + 3 % + 5 % + IVA del 19 % sobre la utilidad) | | | $26.694 | |
| **Precio unitario** | | | **$107.705** | |

*Comparación:* Rango de mercado del retiro de asbesto en Colombia: $60.000-$120.000/m² (estimación). Si el laboratorio confirma que la teja no tiene asbesto, el retiro baja a ≈ $25.000/m² como RCD común.

## 8. Fuentes de financiación

La columna *escenario base* es la mezcla que cierra el valor de la torre: las asignaciones directas del SGR son el saldo que falta después de las demás fuentes. No es el escenario más probable (ver abajo).

| Fuente | Rango posible | Escenario base | Probabilidad | Requisito principal | Cuándo |
|---|---:|---:|---|---|---|
| SGR – Asignaciones Directas (incluidas las anticipadas) del Municipio de Yondó como productor de hidrocarburos | $2.000 M–$12.000 M | $7.337 M | alta (depende solo de la decisión del municipio) | Proyecto en MGA y en el SUIFP-SGR con los requisitos sectoriales de salud (Acuerdo Único de la Comisión Rectora; normas.json advierte que hay que confirmar si se exige concepto de … | Ya: el saldo 2025-2026 sin aprobar alcanza para P1 (radicar nov-2026 a feb-2027). Bienio 2027-2028: el presupuesto se ap… |
| SGR – Asignación para la Paz por convocatoria del OCAD Paz (municipio PDET) | $0 M–$12.000 M | $5.500 M | media (por el antecedente de 2025-2026, pero sin cupo reservado para Yondó) | Iniciativa del PATR del PDET Sur de Bolívar (pilar de salud rural; verificar que exista o incluirla), proyecto en MGA, postulación a una convocatoria del OCAD Paz y su aprobación. | Convocatorias y sesiones del OCAD Paz en 2027-2028. |
| SGR – Asignación para la Inversión Local (municipios con más necesidades básicas insatisfechas) | $500 M–$2.500 M | $1.200 M | media-alta | Proyecto en MGA con enfoque en población pobre; aprobación del municipio. | 2027-2029. |
| SGR – Asignación para la Inversión Regional (cuota de la Gobernación de Antioquia y bolsa regional) | $0 M–$4.000 M | $1.500 M | media-baja | Proyecto presentado o avalado por la Gobernación de Antioquia; priorización departamental. | 2027-2028, con el plan de desarrollo departamental 2028-2031. |
| SGR – Asignación para Ciencia, Tecnología e Innovación | $0 M–$600 M | $0 M | baja | Convocatoria de MinCiencias con un aliado académico (por ejemplo, telemedicina o tamizaje molecular en un municipio aislado). No financia la obra. | Según convocatorias. |
| Presupuesto General de la Nación – MinSalud (cofinanciación con concepto técnico de viabilidad, Res. 485 de 2025) | $0 M–$20.000 M | $12.000 M | media-baja en 2027-2028; media desde 2028 si entra al PMIDS y a un nuevo CONPES | Concepto técnico de viabilidad de MinSalud (control especial de oferta), Documento de Capacidad Instalada concertado, inclusión en el PMIDS de Antioquia, MGA, diseños firmados o ru… | Radicar entre nov-2027 y abr-2028; recursos 2028-2029 (o vigencias futuras). |
| Gobernación de Antioquia – Secretaría Seccional de Salud (cofinanciación de infraestructura y dotación) | $700 M–$4.000 M | $2.300 M | media | Proyecto viabilizado por la Secretaría Seccional, contrapartida municipal o de la E.S.E., coherencia con el programa de red (PTRRM) y con el PMIDS. | Anual; cambia con el gobernador 2028-2031. |
| Obras por Impuestos (Yondó es PDET y ZOMAC) | $500 M–$4.500 M | $2.500 M | media | Proyecto viabilizado por el ministerio del sector (MinSalud para salud) y registrado en el banco de Obras por Impuestos de la ART; un contribuyente que lo financie. Revisar primero… | Convocatorias anuales de la ART; inscribir en 2027-2028. |
| FENOGE / programa Con Energía y MinEnergía (solar, baterías y eficiencia en edificaciones públicas de municipios PDET) | $600 M–$1.734 M | $1.000 M | media | Solicitud de la entidad territorial con certificado de planeación, línea base de consumo y capacidad de conexión; ejecución directa de FENOGE en algunos programas. | Programas continuos; preparar la solicitud con el diseño eléctrico (2027). |
| MinTIC (cofinanciación FUTIC de territorios inteligentes, conectividad) y programa departamental de telemedicina | $100 M–$900 M | $400 M | media | Proyecto de conectividad, IoT y telemedicina; habilitación de telemedicina (Res. 2654 de 2019). FUTIC no financia plataformas propias. | Convocatorias 2027-2028. |
| Recursos propios del Municipio de Yondó (contrapartida) y aporte del lote | $500 M–$2.000 M | $1.000 M | alta | Certificado de disponibilidad presupuestal y acuerdo del Concejo si compromete vigencias futuras; título del lote a nombre de la E.S.E. o del municipio. | 2027-2029. |
| Recursos propios de la E.S.E. y saneamiento (art. 156 de la Ley 2294 de 2023: condonación si se invierte en infraestructura) | $0 M–$1.500 M | $400 M | baja-media | La E.S.E. está en Programa de Saneamiento Fiscal y Financiero: su aporte es pequeño. El art. 156 vence hacia may-2027. | Antes de may-2027 para el art. 156; luego, excedentes de operación. |
| Crédito: Findeter con tasa compensada para infraestructura y dotación en salud (Res. 2316 de 2025) o IDEA | $0 M–$5.000 M | $1.500 M | baja-media | Concepto técnico de la Secretaría Seccional de Salud y concepto de MinSalud (responde en 20 días hábiles), MGA web, diseños y presupuesto con APU, dos cotizaciones por equipo; capa… | 2028, para el cierre financiero de P2. |
| Ecopetrol – inversión social en su área de influencia (campos Casabe y Llanito) o como contribuyente de Obras por Impuestos | $0 M–$2.000 M | $300 M | baja | Convenio con Ecopetrol o selección como contribuyente en Obras por Impuestos; alineación con sus programas sociales. | Gestión desde 2027. |
| Cooperación internacional (OPS, bancos de desarrollo, agencias y embajadas; donación de equipos) | $0 M–$800 M | $200 M | baja | Proyecto con enfoque de hospital seguro y resiliente o de atención primaria rural; contrapartida local. | Variable. |
| **Total** | | **$37.137 M** | | | |

**Nota: la torre ya no cuenta con el Incentivo a la Producción del SGR.** Antes, los $5.500 millones de la segunda fila salían del saldo del incentivo para el OCAD Paz (≈ $13.694 millones: $14.025 asignados menos $331 aprobados en 2025-2026). La propuesta integral 2028–2031 (`docs/17`; las cifras están en `data/propuesta/modulos/tic.json` y `saneamiento.json`) reserva ese incentivo para sus dos granjas solares, la municipal del módulo de TIC (≈ $2.799 millones) y la del relleno clausurado del módulo de Saneamiento (≈ $1.747 millones): son 2 proyectos de energía por $4.546 millones, y la convocatoria admite hasta 2 proyectos y $8.000 millones por municipio, así que la torre sería un tercer proyecto. Dentro del atlas pasa lo mismo, porque el incentivo ya está en la Red Energética Pública (`docs/05`, que ya no incluye el nodo del hospital: pasó a la P7 de esta torre, que no usa el incentivo) y en la granja solar del relleno (`docs/12`). Los $5.500 millones pasan a la Asignación para la Paz, que la fila ya incluía y que es la fuente que usa el módulo de Salud de la propuesta para la torre y los puestos rurales (`data/propuesta/modulos/salud.json`); el monto y el total de la mezcla no cambian.

**Datos clave detrás de los montos:**

- **SGR – Asignaciones Directas:** Bienio 2025-2026 (MinHacienda): al 27-oct-2026 quedan ≈ $7.297 millones de asignaciones directas sin aprobar (cálculo propio de la propuesta 2028–2031, `docs/17`; la cifra está en `data/propuesta/modulos/salud.json`, sin desglose entre directas y anticipadas), y alcanzan para P1. No hay que confundirlos con los $7.337 millones de directas de la mezcla: de este saldo sale solo P1 ($1.832 millones); los otros $5.505 millones (P2, $5.128 millones, y P6, $377 millones) son de los bienios siguientes, porque P2 se radica en 2027-2028 y P6 empieza a mediados de 2029. Con el corte de MinHacienda del 21-oct-2026, que es el que usó este documento, el saldo era ≈ $9.569 millones (directas: $34.178 millones presupuestadas y $26.481 aprobadas; anticipadas: $15.162 y $13.290); la cifra que rige es la del 27 de octubre. Bienio 2027-2028: el proyecto de ley de presupuesto del SGR (radicado el 2-oct-2026) baja 11 % el total nacional (de $30,96 a $27,54 billones) y asigna $5,37 billones a asignaciones directas; si Yondó baja en la misma proporción, tendría ≈ $28.000-36.000 millones de directas (estimación).
- **SGR – Asignación para la Paz por convocatoria del OCAD Paz:** Es una bolsa nacional que el OCAD Paz asigna por convocatorias a proyectos de los municipios PDET, no un saldo propio de Yondó. En 2025-2026 le aprobó a Yondó $36.228 millones en 7 proyectos, casi todo en dos vías: la Ye de Marley-San Francisco ($16.050 millones) y la de la Ruta del Cacao a San Miguel del Tigre ($19.027 millones). Ese antecedente sostiene la probabilidad media y el tope del rango ($12.000 millones, menos que cualquiera de las dos), pero ninguna fue de salud y no hay un cupo reservado para Yondó (sección 11). El saldo del incentivo a la producción para el OCAD Paz (≈ $13.694 millones) ya no se cuenta para la torre: ver la nota debajo de la tabla.
- **Presupuesto General de la Nación – MinSalud:** El CONPES 4169 (vigencias futuras 2026-2030 por $3,02 billones para 102 sedes) no incluye a Yondó; Guarne recibió $35.059 millones y Santa Bárbara $13.500 millones. Pero el proyecto de presupuesto 2027 baja la inversión propia de MinSalud de $2,6 a $1,6 billones y debe atender la reconstrucción de hospitales dañados por el terremoto del 10-ago-2026 (≈ $1 billón).
- **Gobernación de Antioquia – Secretaría Seccional de Salud:** Cofinanciación promedio por proyecto: infraestructura $729 millones (2024) y $2.322 millones (2025); dotación $716-737 millones (informe SSSA 2026, cálculo propio en docs/anexos/C-hospital-2028.md).
- **Obras por Impuestos:** Cupo CONFIS 2025: $1,1 billones (Decreto 178 de 2025); en 2025 se aprobaron 137 proyectos por ≈ $1,6 billones. El proyecto PDET de dotación de Antioquia (21 municipios, Yondó incluido) vale $44.059 millones según el DNP. Yondó (código DANE 05893) está en la lista ZOMAC del Decreto 1650 de 2017, Anexo 2 (verificado en el normograma de la DIAN; verificación V2).
- **Crédito: Findeter con tasa compensada para infraestructura y dotación en salud:** En 2026 Yondó ya paga $1.718,5 millones de servicio de deuda con un instituto de desarrollo departamental (probablemente el IDEA).

**Si MinSalud no pone nada:** Cubre la torre solo si el municipio dedica ≈ $11.637 millones de directas y el OCAD Paz le aprueba ≈ $9.000 millones de la Asignación para la Paz, más de lo que la propuesta 2028–2031 le pide al OCAD Paz para la torre y los puestos rurales juntos ($8.300 millones, `data/propuesta/modulos/salud.json`). Si no, se puede partir la obra en dos etapas: pisos 1 a 3 con bloque técnico primero (≈ 85 % del valor, porque la cimentación, los núcleos y los equipos se hacen completos) y el piso 4 después. Urgencias, partos, hospitalización, consulta y laboratorio quedarían habilitados en la primera etapa; odontología, terapias y telemedicina seguirían un tiempo en el edificio actual.

**Escenario probable (coherente con `docs/06`):** Con los montos 'probables' de docs/06 para MinSalud ($3.000 millones) y Obras por Impuestos ($1.800 millones), sin crédito ni aportes de Ecopetrol o cooperación, y con las demás fuentes como en el escenario base, faltan ≈ $11.700 millones. Esa brecha se cubre con más regalías (escenario sin MinSalud), con un CONPES o asignación de MinSalud o partiendo la obra en etapas.

**Quién paga qué proyecto en el escenario base** (cálculo propio: cada fuente va solo a los proyectos que puede financiar y se usa una sola vez):

| Proyecto | Valor | Fuentes |
|---|---:|---|
| P1 | $1.832 M | SGR asignaciones directas $1.832 M |
| P2 | $22.197 M | MinSalud (PGN) $5.828 M; SGR Asignación para la Paz (OCAD Paz) $5.500 M; SGR asignaciones directas $5.128 M; Gobernación de Antioquia $1.740 M; SGR inversión regional $1.500 M; Crédito (Findeter o IDEA) $1.500 M; Municipio de Yondó $1.000 M |
| P3 | $6.172 M | MinSalud (PGN) $6.172 M |
| P4 | $3.676 M | Obras por Impuestos $2.066 M; SGR inversión local $1.051 M; Gobernación de Antioquia $560 M |
| P5 | $549 M | E.S.E. $400 M; SGR inversión local $149 M |
| P6 | $977 M | MinTIC $400 M; SGR asignaciones directas $377 M; Cooperación $200 M |
| P7 | $1.734 M | FENOGE $1.000 M; Obras por Impuestos $434 M; Ecopetrol $300 M |

### 8.1 Qué cambió frente a `docs/06-hospital-2028-financiacion.md`

- docs/06 y data/hospital2028.json calculaban un proyecto de $9.470 millones (reforzar y adecuar el hospital actual, energía, telesalud y equipos) con un escenario probable de $13.100 millones para 2027-2029. La torre nueva cuesta $37.137 millones más $2.613 millones de proyectos complementarios: se acerca al escenario ambicioso de docs/06 ($34.550 millones) y lo supera.
- El componente 'reforzamiento y adecuaciones' ($3.000 millones) de docs/06 se reemplaza por la torre (P2-P3) y por la adecuación del edificio actual para usos no asistenciales (P8, ≈ $1.963 millones).
- MinSalud: docs/06 suponía $3.000 millones (probable) y $13.500 millones (ambicioso). Aquí se suben a $12.000 millones en el escenario base porque una reposición de torre es la tipología que MinSalud cofinancia (Guarne, $35.059 millones), pero su probabilidad baja: el presupuesto 2027 recorta la inversión de MinSalud (de $2,6 a $1,6 billones) y el terremoto del 10-ago-2026 compite por esos recursos.
- Regalías: docs/06 suponía $1.000-5.500 millones. Se suben a $7.337 millones de directas más $5.500 millones de la Asignación para la Paz del OCAD Paz, porque la torre sería la inversión principal del bienio y porque en 2025-2026 el OCAD Paz le aprobó a Yondó, municipio PDET, $36.228 millones de esa asignación. Esos $5.500 millones salían antes del incentivo a la producción para el OCAD Paz (saldo ≈ $13.694 millones sin aprobar en 2025-2026), pero la propuesta 2028–2031 (`docs/17`) reserva el incentivo para sus dos granjas solares por el tope de 2 proyectos por municipio (nota de la sección 8). El bienio 2027-2028 trae 11 % menos a nivel nacional.
- PMIDS: el anexo C (`docs/anexos/C-hospital-2028.md`, sección 3.4) señalaba el plazo de remisión de iniciativas hacia el 10-oct-2026 (Res. 592 de 2026; docs/06 no da esa fecha). Si no se registró, la torre debe entrar en la actualización obligatoria del primer semestre de 2028 (o en un ajuste que permita la Secretaría Seccional).
- MinTIC se mantiene en el mismo rango de docs/06 ($100-900 millones). FENOGE baja: docs/06 lo ponía entre $700 y $3.150 millones ($2.100 millones en el escenario probable) para un hospital solar y eficiente; aquí va de $600 a $1.734 millones ($1.000 millones en el escenario base), porque solo cubre la solar, las baterías y la gestión energética de la torre (P7, $1.734 millones). La solar y las baterías del hospital ahora se instalan en la torre (P7) y no en el edificio actual.
- Findeter: docs/06 lo ponía en $0-2.000 millones; aquí $0-5.000 millones, como deuda del municipio (la Res. 2316 también admite a la E.S.E. en saneamiento si avisa a MinHacienda, pero su caja no lo soporta).
- Coherencia (verificación V2): los montos por fuente del escenario base superan los 'probables' de docs/06 en MinSalud ($12.000 frente a $3.000 millones), Obras por Impuestos ($2.500 frente a $1.800) y crédito ($1.500 frente a $0). Por eso se presenta también el escenario probable de docs/06, con una brecha de ≈ $11.700 millones.

## 9. Proyectos a articular

Hay que articular 9 proyectos: 7 forman la torre ($37.137 millones) y 2 la complementan (edificio actual y ambulancia, $2.613 millones). Se pueden presentar en 7 fichas MGA uniendo P2 con P3 (proyecto mixto) y P4 con P5. Lo mínimo para abrir la torre son 3: estudios y diseños (P1), construcción con equipamiento fijo (P2+P3) y dotación con laboratorio (P4+P5).

| # | Proyecto | Valor | Rango | Fuente más adecuada | Quién lo presenta | Concepto (Res. 485) | MGA | Depende de | Fechas |
|---|---|---:|---|---|---|---|---|---|---|
| P1 | Estudios y diseños integrales, formulación y licencia de la torre de primer nivel | $1.832 M | $1.143 M–$2.704 M | SGR – Asignaciones Directas (saldo 2025-2026) o recursos propios del municipio; apoyo técnico de la Secretaría Seccional de Salud. | Municipio de Yondó (ejecutor) con la E.S.E. Hospital Héctor Abad Gómez | Num. 7.1.9 (estudios y diseños e interventoría como proyecto separado). Con recursos territoriales y menos de 5.000 SMMLV, el concepto lo emite la Secretaría Seccional de Salud de Antioquia (Res. 485, arts. 5 y 6). | Sector 19 Salud y Protección Social; programa 1906; producto 1906034 'Estudios de preinversión' (código 190603400). | Título del lote; Certificado de uso del suelo y de riesgo; Decisión sobre el uso del edificio actual | 2026-11 a 2027-12 |
| P2 | Demolición del antiguo Centro Vida y construcción de la torre de servicios de primer nivel (infraestructura física y redes) | $22.197 M | $17.103 M–$28.905 M | MinSalud (PGN) + SGR (directas, Asignación para la Paz del OCAD Paz, inversión regional) + Gobernación de Antioquia + crédito del municipio + recursos propios. | E.S.E. Hospital Héctor Abad Gómez ante MinSalud; Municipio de Yondó para la parte de regalías | Num. 7.1.2 (infraestructura física: reposición con fortalecimiento de capacidad instalada) o num. 7.1.12 (llave en mano). Control especial de oferta (> 5.000 SMMLV): concepto de MinSalud e inclusión en el PMIDS o Plan Bienal (art. 4; num. 7.1.1.6). | Sector 19; programa 1906; producto 1906047 'Hospitales de primer nivel de atención construidos' (190604700). | P1 terminado (diseños y licencia); Documento de Capacidad Instalada concertado; Registro en el PMIDS; Cierre financiero | 2027-11 a 2030-01 |
| P3 | Equipamiento fijo e industrial y sistemas especiales de la torre | $6.172 M | $4.311 M–$8.927 M | Recomendado: dentro del proyecto mixto con P2 (MinSalud o SGR). El generador PSA puede ir por Obras por Impuestos. | E.S.E. Hospital Héctor Abad Gómez | Num. 7.1.5 (equipamiento fijo: listado, 2 cotizaciones de 2 marcas, planos de ubicación) y 7.1.6 b para la red de datos. Cuenta para el umbral de 5.000 SMMLV de infraestructura y equipamiento fijo. | Sector 19; programa 1906; producto 1906047 (actividad de equipamiento del proyecto de construcción) o 1906005 'Hospitales de primer nivel de atención dotados' si se presenta aparte. | P2 con obra negra y cuartos técnicos listos | 2028-11 a 2030-01 |
| P4 | Dotación biomédica, mobiliario clínico y puesta en marcha de la torre | $3.676 M | $2.556 M–$5.374 M | Obras por Impuestos + Gobernación de Antioquia + SGR (inversión local); MinSalud si entra en el proyecto mixto. | E.S.E. Hospital Héctor Abad Gómez | Num. 7.1.6 a (dotación biomédica: listado por servicio, inventario actual, 2 cotizaciones). La dotación de baja complejidad no es de control especial de oferta; la ecografía es de mediana complejidad (normas.json). Con Obras por Impuestos o PGN, concepto de MinSalud. | Sector 19; programa 1906; producto 1906005 'Hospitales de primer nivel de atención dotados' (190600500). | P2 con 70 % de avance físico (Res. 2373 de 2025); Inventario de la dotación actual | 2029-03 a 2030-04 |
| P5 | Laboratorio clínico de 24 horas con tamizaje (equipos propios, puesta en marcha y comodato de analizadores) | $549 M | $401 M–$742 M | SGR inversión local + recursos propios de la E.S.E.; reactivos con la venta de servicios (≈ $435 millones/año, laboratorio.json). | E.S.E. Hospital Héctor Abad Gómez | Num. 7.1.6 a (dotación) y 7.1.6 b (LIS). Puede ir dentro de P4. | Sector 19; programa 1906; producto 1906005. | Piso 2 terminado; LIS (P6); Contrato de comodato firmado | 2029-06 a 2030-03 |
| P6 | Sistemas de información, telemedicina y conectividad de la torre | $977 M | $635 M–$1.450 M | MinTIC (FUTIC) + SGR + cooperación. | E.S.E. Hospital Héctor Abad Gómez (con el municipio para MinTIC) | Num. 7.1.6 b (dotación TIC con certificación de protección de datos) y 7.1.10 (telesalud como proyecto propio: concepto de pertinencia de MinSalud). | Sector 19; programa 1906 (por verificar el producto de telesalud en el catálogo vigente) o sector 23 TIC para la conectividad. | Red de voz y datos instalada (P3, ítem 11.01) | 2029-06 a 2030-03 |
| P7 | Solar de 100 kWp, baterías de 400 kWh y gestión energética de la torre (nodo hospital de la microrred) | $1.734 M | $1.214 M–$2.498 M | FENOGE / Con Energía + SGR u Obras por Impuestos (MinEnergía). | Municipio de Yondó o E.S.E., articulado con el proyecto de la Red Energética Pública (docs/05) | Hace parte del equipamiento fijo (num. 7.1.5) si va con MinSalud; con FENOGE o MinEnergía sigue sus propios requisitos. | Sector 21 Minas y Energía (producto por verificar en el catálogo vigente). | Cubierta de la torre terminada (P2); Trámite de conexión con EPM; Descontar el nodo hospital del proyecto de microrred | 2029-03 a 2030-01 |
| P8 | Adecuación del edificio actual para administración, archivo, almacén y central de distribución, cocina, lavandería y mantenimiento *(fuera de la torre)* | $1.963 M | $1.178 M–$3.337 M | Gobernación de Antioquia + municipio + E.S.E. (art. 156 de la Ley 2294 si se usa antes de may-2027). | E.S.E. Hospital Héctor Abad Gómez | Num. 7.1.7 (adecuaciones: tope de 500 SMMLV = $875 millones salvo justificación) y num. 7.1.2.7 / 7.1.4 si incluye reforzamiento. | Sector 19; programa 1906; producto 1906007 'Hospitales de primer nivel de atención restaurados' (por verificar si aplica a usos no asistenciales). | Traslado de los servicios a la torre (P4); Resultados del estudio de vulnerabilidad de 2024 | 2030-05 a 2030-12 |
| P9 | Transporte asistencial: ambulancia medicalizada (TAM) o reposición de ambulancia básica *(fuera de la torre)* | $650 M | $460 M–$750 M | Obras por Impuestos o Gobernación de Antioquia (proyecto tipo DNP de ambulancias). | E.S.E. Hospital Héctor Abad Gómez | Dotación de transporte asistencial: concepto según la fuente (MinSalud con PGN u Obras por Impuestos; Secretaría Seccional con recursos territoriales). El proyecto de 2024 fue devuelto a la MGA: corregirlo con el proyecto tipo DNP. | Sector 19; programa 1906 (producto de transporte asistencial por verificar). | — | 2027-03 a 2028-06 |

**Orden:** P1 → (P2 + P3) → P7 y P6 durante la obra → P4 + P5 al 70 % de avance → puesta en marcha → P8. P9 va por su cuenta.

## 10. Cronograma y flujo de caja

| Etapa | Desde | Hasta | Meses | Proyecto |
|---|---|---|---:|---|
| 0. Gestión previa: titularidad del lote, certificado de uso del suelo y de riesgo por inundación, publicar el estudio de vulnerabilidad de 2024, decidir el uso del edificio actual y registrar la iniciativa en el PMIDS de Antioquia | 2026-11 | 2027-03 | 5 | P1 |
| 1. Formulación y aprobación del proyecto de estudios y diseños (MGA, SGR o recursos propios) | 2026-11 | 2027-02 | 4 | P1 |
| 2. Estudios y diseños integrales con interventoría (Res. 485, num. 7.1.9) | 2027-03 | 2027-10 | 8 | P1 |
| 3. Documento de Capacidad Instalada concertado con MinSalud (Res. 1211 y 1519 de 2025) | 2027-04 | 2027-09 | 6 | P1 |
| 4. Licencia de construcción y aprobaciones | 2027-11 | 2027-12 | 2 | P1 |
| 5. Radicación ante MinSalud (concepto técnico de viabilidad, control especial de oferta), cofinanciación y cierre financiero | 2027-11 | 2028-04 | 6 | P2, P3 |
| 6. Licitación de obra e interventoría | 2028-05 | 2028-07 | 3 | P2, P3 |
| 7. Demolición del antiguo Centro Vida (con retiro de asbesto) y cimentación | 2028-08 | 2028-12 | 5 | P2 |
| 8. Estructura, mampostería, redes y cubierta | 2028-11 | 2029-08 | 10 | P2 |
| 9. Acabados, equipamiento fijo, ascensores, gases, aire, solar y pruebas | 2029-05 | 2030-01 | 9 | P2, P3, P7 |
| 10. Compra e instalación de dotación biomédica, laboratorio y TIC (desde el 70 % de avance de obra, Res. 2373 de 2025) | 2029-07 | 2030-02 | 8 | P4, P5, P6 |
| 11. Puesta en marcha, habilitación y traslado de servicios | 2030-02 | 2030-04 | 3 | P4 |
| 12. Adecuación del edificio actual para administración, archivo y bodega | 2030-05 | 2030-12 | 8 | P8 |

**Ruta más rápida:** Ruta llave en mano a precio global fijo (Res. 485, num. 7.1.12, agregado por la Res. 1211): se radica con anteproyecto, memorias y Documento de Capacidad Instalada hacia jun-2027; el contratista diseña y construye (diseño 5 meses traslapado con 16 de obra). Apertura posible hacia dic-2029. Riesgo: precio global fijo sin reajuste con un anteproyecto débil; exige estudio del sector y 3 cotizaciones por componente.

| Año | Pagos del año | Acumulado | Qué se paga |
|---|---:|---:|---|
| 2026 | $73 M | $73 M | Formulación |
| 2027 | $1.576 M | $1.649 M | Estudios, diseños y formulación |
| 2028 | $4.931 M | $6.580 M | Cierre de diseños, licencia, inicio de obra (demolición, cimentación) |
| 2029 | $25.151 M | $31.731 M | Estructura, redes, acabados, equipamiento fijo, solar; inicio de dotación |
| 2030 | $5.407 M | $37.137 M | Cierre de obra, dotación, laboratorio, TIC y puesta en marcha |

Pesos constantes de 2026: los presupuestos de cada año deben indexarse. La compra de equipos empieza cuando la obra tenga 70 % de avance (Res. 2373 de 2025).

## 11. Lo que falta verificar

- Cantidades de prediseño sin planos ni estudio de suelos: el prediseño estructural que cumple la NSR-10 ya sube el costo directo $1.310 M a $1.390 M (sección 6.3); el número y el largo de los pilotes, la cuantía de acero y si la torre requiere pilotes los fijan el estudio geotécnico (con análisis de licuación) y el diseño estructural.
- NSR-10 (citada de memoria; el Título A no se pudo abrir): numerales de amenaza intermedia, de la fila del sistema dual DMO (R0 = 6,0 y Ω0 = 2,5), de las irregularidades, del umbral de daño y de C.21, C.15 y el Título H; si el grupo IV pide algo más en amenaza intermedia.
- Norma de habilitación: texto oficial de las 199 exigencias de la Res. 3100; la modificación de 2022 (1138 o 1410); la publicación de la Res. 2080 de 2026 en el Diario Oficial; el manual de la Res. 914 de 2025 para la esterilización; si el mínimo de área de la Res. 1633 se mide libre o a ejes (47 recintos); los códigos REPS; las reglas 3, 4, 5, 8 y 14 y el art. 2 del Decreto 4725 (documento 15).
- Proyecto tipo: el PDF del DNP (áreas por ambiente, lista de 59 ítems de dotación, cuantías y AIU) y las capacidades instaladas tipo de la Res. 1211 y 1519.
- Sismotectónica: centro y profundidad del nido de Bucaramanga, distancias y magnitudes máximas de las fallas cercanas, y el epicentro, la profundidad y el tipo de magnitud del terremoto del 10-ago-2026 (sección 1.2).
- Altura del ±0,00 sobre el mar y levantamiento topográfico (el modelo BIM supone 75 m).
- La titularidad del lote, el uso del suelo, la amenaza por inundación y la norma del EOT no están verificados (normas.json).
- Las estampillas, el ICA y el impuesto de delineación de Yondó no se revisaron.
- El estudio de vulnerabilidad de 2024 del edificio actual no es público: el costo de P8 es un supuesto.
- Los precios de los equipos de la dotación son en su mayoría estimaciones (37 de las 236 líneas de los servicios con referencia SECOP).
- Los comparables por m² con cifra oficial son pocos: el área de Monguí sale de la prensa sectorial y no se sabe cuánta dotación trae el proyecto de Quimbaya. Hay que confirmarlos en los pliegos de SECOP II (piden captcha y no se pudieron abrir desde este entorno) y en la MGA del BPIN 2024000040010.
- El AIU completo sobre los equipos de P3 es conservador: contratándolos como suministro e instalación aparte se podrían ahorrar del orden de $600-1.000 millones (supuesto del presupuesto sobre el AIU de los equipos).
- El presupuesto del SGR 2027-2028 por municipio no está publicado; la cifra de Yondó es una estimación proporcional.
- La Asignación para la Paz se reparte por convocatorias del OCAD Paz: no hay un cupo reservado para Yondó, no se sabe si las convocatorias de 2027-2028 admitirán infraestructura de salud y no se revisó si el PATR del PDET Sur de Bolívar trae una iniciativa hospitalaria para Yondó.
- La ley de presupuesto 2027 y el PND 2026-2030 pueden cambiar las líneas de MinSalud y los PMIDS.
- La base oficial de Antioquia usada es de 2020: la actualización por salario mínimo e IPC no capta cambios de precios relativos (el acero y el cemento subieron más que el IPC en 2021-2022). Se contrasta con compras de 2025-2026 de la Tienda Virtual.
- Los acabados hospitalarios (vinilo, cielo de alta higiene, guardacamillas), la ventanería y los equipos especiales no tienen precio oficial publicado: son estimaciones con rango que deben confirmarse con 2-3 cotizaciones (Res. 485, num. 7.1.1.4 y 7.1.12).

## 12. Fuentes

- Res. 485 de 2025, MinSalud: <https://www.minsalud.gov.co/Normatividad_Nuevo/Resolucion%20No%20485%20de%202025.pdf>
- Res. 1519 de 2025, MinSalud (art. 7 vigente): <https://www.minsalud.gov.co/Normatividad_Nuevo/Resolucion%20No%201519%20de%202025.pdf>
- Res. 1211 de 2025, MinSalud: <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_1211_2025.htm>
- Res. 1633 de 2025, MinSalud, y sus anexos: <https://www.minsalud.gov.co/Normatividad_Nuevo/Resolucion%20No%201633%20de%202025.pdf>
- Res. 3100 de 2019 (compilada): <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_3100_2019.htm>
- Res. 2080 de 2026, MinSalud (revoca la Res. 1732 de 2026): <https://www.minsalud.gov.co/Normatividad_Nuevo/Resoluci%C3%B3n%20No%202080%20de%202026.pdf>
- Res. 914 de 2025 (reprocesamiento de dispositivos médicos): <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_0914_2025.htm>
- Res. 1811 de 2025 (radiaciones ionizantes; reemplazó a la Res. 482 de 2018): <https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/DIJ/resolucion-1811-de-2025.pdf>
- Decreto 4725 de 2005 (compilación del INVIMA): <https://normograma.invima.gov.co/normograma/compilacion/docs/decreto_4725_2005.htm>
- NSR-10, Título A (Decreto 926 de 2010): <https://www.idrd.gov.co/sites/default/files/documentos/Construcciones/titulo-a-nsr-100.pdf>
- OPS, monitoreo del terremoto del 10-ago-2026 (3-sep-2026): <https://www.paho.org/es/monitoreo-amenazas-naturales/monitoreo-amenazas-naturales-4-septiembre-2026>
- Documentos del atlas: simulación sísmica (`docs/14-simulacion-sismica.md`), dotación y habilitación (`docs/15-dotacion-y-habilitacion.md`) y modelo BIM (`docs/16-bim-torre.md`).
- Proyecto tipo DNP de infraestructura básica en salud (2018): <https://proyectostipo.dnp.gov.co/images/pdf/salud/PTsalud.pdf>
- Puesto de salud tipo, MinSalud (2017): <https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/VS/PSA/puesto-salud-tipo.pdf>
- Gobernación de Antioquia, Base de APU SIF 2020-II (ítems 1.2, 2.7, 2.8, 2.9, 2.11, 3.2, 3.3, 4.2.3, 5.1.3, 6.1.10, 6.1.19, 6.2.15, 6.2.30, 7.1.15, 10.1): <https://www.antioquia.gov.co/images/PDF2/Infraestructura/2020/08-agosto/apu-base-referencia-sif-2020-semestre-ii.pdf>
- Tienda Virtual del Estado Colombiano, compras por ítem (órdenes 162740, 162775, 163083 y 152787 de Antioquia): <https://www.datos.gov.co/d/3hdv-smhz>
- MinHacienda, ejecución presupuestal del SGR 2025-2026 (Yondó): <https://www.datos.gov.co/d/g4qj-2p2e>
- Proyecto de presupuesto del SGR 2027-2028 (Portafolio, oct-2026): <https://www.portafolio.co/economia/gobierno/presupuesto-de-regalias-2027-2028-seria-de-27-54-billones-11-menos-503793>
- Presupuesto de salud 2027 (Minuto30, 9-sep-2026): <https://www.minuto30.com/amp/presupuesto-salud-2027/1718556/>
- CONPES 4169 (vigencias futuras para 102 sedes hospitalarias): <https://consultorsalud.com/wp-content/uploads/2025/11/4169.pdf>
- Guarne: aporte de MinSalud de $35.059 M (El Colombiano, 5-may-2026): <https://www.elcolombiano.com/antioquia/guarne-antioquia-nuevo-hospital-millones-ministerio-de-salud-EG36212125>
- Monguí: contrato de obra de $11.966.541.300 firmado el 16-abr-2025 (SECOP II, CO1.NTC.7482028; datos.gov.co jbjy-vk9h): <https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.7482028>
- Monguí: sede de 2.400 m² (Consultorsalud, 25-jun-2025): <https://consultorsalud.com/salud-en-boyaca-minsalud-300-mil-millones/>
- Quimbaya: $28.274 M de regalías para un hospital de 4.456 m² (DNP, 25-jul-2025): <https://www.dnp.gov.co/Prensa_/Noticias/Paginas/regalias-apuestan-salud-quindio-28-mil-millones-nuevo-hospital-quimbaya.aspx>
- Quimbaya: producto MGA 'construidos y dotados', BPIN 2024000040010 (DNP Mapa Inversiones): <https://www.datos.gov.co/d/8kfp-z3my>
- Pasacaballos: hospital de 4.500 m² por $48.372 M con dotación (El Universal, 30-jul-2026): <https://www.eluniversal.com.co/cartagena/2026/07/30/asi-va-el-proceso-para-financiar-el-nuevo-hospital-de-pasacaballos/>
- Yondó en la lista ZOMAC (Decreto 1650 de 2017, Anexo 2, código 05893): <https://normograma.dian.gov.co/dian/compilacion/docs/decreto_1650_2017.htm>
- Ley 2101 de 2021 (jornada de 42 horas desde el 15-jul-2026): <http://www.secretariasenado.gov.co/senado/basedoc/ley_2101_2021.html>
- Ley 1738 de 2014, art. 8 (vigencia permanente de la contribución de obra pública): <http://www.secretariasenado.gov.co/senado/basedoc/ley_1738_2014.html>
- Hospital Santa Catalina de Sena, Sucre (El Universal, 13-oct-2017): <https://www.eluniversal.com.co/regional/2017/10/13/comenzara-construccion-del-nuevo-hospital-de-sucre-con-millonaria-inversion/>
- SECOP II, construcción de la E.S.E. Álvaro Ramírez González (San Martín, Cesar): <https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.5438578>
- Hospital de Majagual (El Heraldo, 30-oct-2025): <https://www.elheraldo.co/sucre/2025/10/30/arranca-construccion-de-un-hospital-en-la-mojana-de-sucre/>
- Obras por Impuestos, cupo 2025 (Decreto 178 de 2025): <https://www.ambitojuridico.com/sites/default/files/2025-02/D-178-2025.pdf>
- Findeter, tasa compensada en salud (Res. 2316 de 2025): <https://consultorsalud.com/minsalud-lineamientos-redescuento-findeter/>
- FENOGE, programa Con Energía: <https://fenoge.gov.co/proyectos/conenergia/>
- Ley 1106 de 2006 (contribución de obra pública): <http://www.secretariasenado.gov.co/senado/basedoc/ley_1106_2006.html>
- Ley 1796 de 2016 (supervisión técnica independiente): <http://www.secretariasenado.gov.co/senado/basedoc/ley_1796_2016.html>
- Ley 1968 de 2019 (prohibición del asbesto): <http://www.secretariasenado.gov.co/senado/basedoc/ley_1968_2019.html>
- Catálogo de productos MGA, programa 1906 (matriz SGR de Norte de Santander, 2024): <https://administrador.nortedesantander.gov.co/wp-content/uploads/2024/05/MATRIZ_SGR_DEFINITIVA.pdf>
- Puente Barrancabermeja-Yondó en riesgo (Vanguardia, 4-jun-2026): <https://www.vanguardia.com/santander/barrancabermeja/2026/06/04/por-que-sigue-en-riesgo-el-puente-que-conecta-a-barrancabermeja-con-yondo-ruta-del-cacao-explico-las-causas/>

Fecha de consulta de todas las fuentes: 22 de octubre de 2026, salvo el saldo de asignaciones directas al 27 de octubre de 2026 y la reserva del incentivo a la producción para las dos granjas solares (sección 8), que vienen de la propuesta integral 2028–2031 (`data/propuesta/modulos/`; conciliación del 28 de octubre de 2026). Las demás fuentes (REPS, DANE, BDUA, SECOP del hospital, normas técnicas) están citadas con numeral y página en los JSON de `data/proyectos/torre_hospital/`.
