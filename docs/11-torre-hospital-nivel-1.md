# 11 · Torre de servicios de primer nivel para el Hospital Héctor Abad Gómez

**Demoler las construcciones del antiguo Centro Vida, al lado del hospital, y levantar allí una torre de 4 pisos que cumpla la norma sismorresistente para hospitales y toda la norma de salud, con urgencias, partos, hospitalización, consulta, rayos X, ecografía y un laboratorio clínico de 24 horas con tamizaje. El edificio actual, al que según la E.S.E. no conviene invertirle porque no cumple la norma sismorresistente para un hospital (su estudio de vulnerabilidad de 2024 no es público), pasa a oficinas, archivo, bodega y central de distribución.**

> Estado: **prefactibilidad**, con fecha de corte del 22 de octubre de 2026. Cada cifra dice si es un **dato oficial** (copiado de la fuente), un **cálculo propio** (operación sobre datos oficiales, con el método a la vista) o una **estimación** (supuesto con rango, por confirmar). Pesos constantes de 2026 (IPC del DANE, base enero–septiembre de 2026). Los datos completos están en `data/proyectos/torre_hospital/`: `normas.json` y `proyecto_tipo.json` (norma y proyecto tipo), `programa.json` (demanda y programa por ambiente), `dotacion.json` y `laboratorio.json` (equipos y laboratorio), `presupuesto.json`, `apu.json`, `financiacion.json` y `proyectos.json` (este documento). El modelo 3D está en `data/edificios/torre_hospital.json`.
>
> **La “485”** es la Resolución 485 de 2025 de MinSalud: los requisitos para que el Ministerio (o la Secretaría Seccional de Salud) dé el *concepto técnico de viabilidad* a un proyecto de infraestructura, equipamiento fijo y dotación. La modificaron la Res. 1211 y la Res. 1519 de 2025 (esta última reescribió todo el artículo 7, que es el que rige hoy). El diseño sigue la Res. 1633 de 2025 (marco técnico de edificaciones de salud) y la habilitación, la Res. 3100 de 2019.

## En pocas palabras

- **Por qué una torre y no reforzar.** Un hospital con urgencias es una *edificación indispensable* (grupo IV de la NSR-10): debe seguir funcionando después de un terremoto. El edificio actual funciona desde 1989 (parte en el antiguo hospital de la Shell) y su estudio de vulnerabilidad de 2024 ($182,6 M) no es público. El terremoto de 7,4 del 10 de agosto de 2026 en el Chocó dejó más de 300 muertos y colapsó parcialmente un ala del Hospital Universitario del Valle: un hospital que se cae no atiende a nadie. Llevar lo asistencial a una torre nueva y dejar el edificio viejo para funciones de apoyo baja el riesgo y evita invertir en un edificio que no cumple.
- **Sí hay proyecto tipo, pero pequeño.** MinSalud y el DNP solo tienen proyectos tipo de **puesto o centro de salud** (MinSalud 2017, 128,5 m²; DNP 2018, 320,6 m²). No existe un “hospital de primer nivel tipo”. La torre **se inspira en el proyecto tipo del DNP** (pórticos de concreto modulares, circulación central con aleros, bioclimática de clima cálido, materiales durables, dotación por ambiente) y se escala con las áreas de la Res. 1633.
- **Qué tiene.** 3.369,6 m² en 4 pisos (más bloque técnico, residuos y exteriores: 3.620,6 m²). **15 camas** (13 generales y 2 habitaciones de parto TPR), 6 camillas de observación, 15 consultorios, 3 unidades odontológicas, rayos X digital, ecografía, laboratorio de 24 horas, vacunación, farmacia, terapias y una sala de expansión de 8 camillas para emergencias. Hoy (REPS 2022) hay 9 camas, 4 camillas y 13 consultorios.
- **Laboratorio con tamizaje.** 55 pruebas en sitio (unas 5.365 al mes) con tiempos de respuesta definidos: urgencias en 60 minutos o menos, rutina en 4 a 6 horas y tamizaje en 24 a 72 horas, incluidos VPH y tuberculosis por PCR, TSH neonatal, HbA1c, sangre oculta, sífilis, VIH, hepatitis, Chagas, toxoplasma y malaria. Los analizadores van en comodato pagado con reactivos. Hoy el hospital paga **$440 M al año** a un laboratorio externo (SECOP, 2025).
- **Cuánto cuesta.** **$36.536 M** (rango $26.894 M a $49.827 M). La obra vale $25.740 M con AIU ($19.361 M de costo directo); la dotación, el laboratorio, la TIC y el generador de oxígeno, $5.330 M; estudios, diseños y licencia, $1.803 M; interventoría, $1.802 M; puesta en marcha, $250 M; contingencias, $1.566 M. **$7,11 M de obra por m²** ($5,34 M sin equipos ni solar, parecido al de hospitales de primer nivel recientes).
- **Quién la paga.** Ninguna fuente sola alcanza. Escenario base: MinSalud $12.000 M, regalías de Yondó $13.436 M, inversión regional y Gobernación $3.800 M, Obras por Impuestos $2.500 M, crédito $1.500 M y el resto entre FENOGE, MinTIC, municipio, E.S.E. y otros. MinSalud es la fuente más incierta: su inversión propia baja de $2,6 a $1,6 billones en 2027 y el terremoto compite por esa plata.
- **Cuántos proyectos.** **9**: 7 forman la torre y 2 la complementan (adecuar el edificio actual y una ambulancia medicalizada, $2.613 M). Se pueden presentar en 7 fichas MGA. El primero —estudios y diseños, $1.803 M— cabe hoy en las asignaciones directas de regalías 2025-2026 que el municipio todavía no ha aprobado para proyectos (≈ $9.569 M a octubre de 2026, cálculo propio con datos de MinHacienda).
- **Cuándo.** Diseños en 2027, radicación ante MinSalud entre noviembre de 2027 y abril de 2028, obra de 18 meses desde agosto de 2028 y apertura hacia **abril de 2030**. Con la modalidad llave en mano (Res. 1211) podría abrir a finales de 2029.

## 1. Por qué la torre

| Hecho | Dato | Tipo y fuente |
|---|---|---|
| El hospital es la única IPS con urgencias del municipio | 9 camas, 4 camillas de observación, 13 consultorios, 1 sala de partos, 3 ambulancias básicas | Dato oficial, REPS (corte nov-2022), `programa.json` |
| Población a atender | 22.429 habitantes en 2026 (47 % rural) y 25.550 en 2035 | Dato oficial, DANE |
| Grupo de uso sísmico | Grupo IV (edificación indispensable), coeficiente de importancia 1,5; Yondó tiene amenaza sísmica intermedia (Aa = Av = 0,15) | Dato oficial, NSR-10 A.2.5.1.1 y Apéndice A-4 |
| Edificio actual | En uso desde 1989; estudio de vulnerabilidad sísmica contratado en 2024 por $182,6 M, sin publicar | Dato oficial, SECOP I (`docs/anexos/C-hospital-2028.md`) |
| Terremoto del 10-ago-2026 (magnitud 7,4, San José del Palmar, Chocó) | 331 muertos y 4.519 heridos (OPS, 3-sep-2026); colapso parcial de un ala del Hospital Universitario del Valle | Dato oficial (OPS) y prensa: [OPS](https://www.paho.org/es/monitoreo-amenazas-naturales/monitoreo-amenazas-naturales-4-septiembre-2026), [Infobae](https://www.infobae.com/colombia/2026/08/11/asi-amanecieron-las-ciudades-mas-afectadas-por-el-terremoto-de-74-que-sacudio-a-colombia-el-10-de-agosto/) |
| Demanda 2035 | 4 a 12 camas generales, 22.500 a 39.400 consultas médicas, 6.400 a 10.200 urgencias y 27.000 a 73.000 pruebas de laboratorio al año | Estimación con rango, `programa.json` |

**La alternativa de reforzar** el edificio actual para grupo IV obligaría a intervenir todo un edificio de un piso, de los años ochenta, con los servicios funcionando adentro, y al final seguiría siendo un edificio viejo con circulaciones y áreas por debajo de la Res. 1633. La torre libera ese edificio para funciones que no son esenciales (oficinas, archivo, almacén, cocina, lavandería, mantenimiento, base de ambulancias), donde la exigencia sísmica es menor. Aun así, el edificio actual necesita la intervención que diga el estudio de 2024 para su nuevo uso (proyecto P8).

## 2. Qué norma cumple: la lista de chequeo de la Res. 485

La Res. 485 (con el artículo 7 que reescribió la Res. 1519 de 2025) pide estos documentos. Hoy **todos están pendientes**: este estudio es el insumo para producirlos.

| Numeral | Qué pide | Cómo lo cumple la torre | Responsable |
|---|---|---|---|
| 7.1.1.1 | Carta de presentación dirigida a MinSalud con nombre, valor total, entidades que financian, fuentes, montos, tiempo de ejecución e instancia ejecutora. | La firma quien presente el proyecto (E.S.E. Hospital Héctor Abad Gómez o Municipio de Yondó). Debe cuadrar con la matriz de fuentes del proyecto. | Gerente de la E.S.E. / alcalde |
| 7.1.1.2 | Proyecto diligenciado en la Metodología General Ajustada (MGA web). | Formular la torre en MGA con su BPIN: problema (servicios asistenciales en un edificio que no cumple la NSR-10), alternativas (reforzar vs. torre nueva), productos y costos por etapa. | Oficina de planeación municipal / E.S.E. |
| 7.1.1.3 | Concepto técnico de quien presenta: conveniencia y coherencia con el Programa Territorial de Reorganización, Rediseño y Modernización de Redes de E.S.E. (PTRRM) vigente d… | Verificar que el documento de red de Antioquia contemple a Yondó con los servicios de la torre; si no, pedir su ajuste a la Secretaría Seccional de Salud antes de radicar. | E.S.E. + Secretaría Seccional de Salud de Antioquia |
| 7.1.1.4 | Certificación de que el presupuesto incluye todas las actividades y cantidades para la ejecución completa y el cierre financiero, con precios verificados como razonables … | Presupuesto con APU propios y precios de referencia del Magdalena Medio (Barrancabermeja / Gobernación de Antioquia), con fecha. | Entidad que presenta |
| 7.1.1.5 | Certificación de que el personal técnico de la entidad revisó y avala toda la documentación. | Revisión interna (o con apoyo de la Gobernación) antes de radicar. | Entidad que presenta |
| 7.1.1.6 | Inclusión y aprobación en el Plan Bienal de Inversiones Públicas en Salud si el proyecto es de control especial de oferta (art. 4). | Si la infraestructura o el equipamiento fijo superan 5.000 SMMLV ($8.754.525.000 en 2026, cálculo propio), es de control especial de oferta. Una torre de este tamaño casi seguro lo supera. | Secretaría Seccional de Salud de Antioquia |
| 7.1.1.7 | Documento que soporte la cofinanciación de fuentes distintas del PGN. | Certificados de disponibilidad, acuerdos o actos de las fuentes (municipio, Gobernación, SGR, Obras por Impuestos, recursos propios de la E.S.E.). | Cada cofinanciador |
| 7.1.2.1 | Certificado de tradición y libertad del predio (expedido hace menos de 3 meses) o documento equivalente de titularidad. | Establecer quién es dueño del lote del antiguo Centro Vida (¿E.S.E. o municipio?). Si es del municipio, formalizar la transferencia o el título que permita a la E.S.E. construir. | E.S.E. / Secretaría de Hacienda municipal |
| 7.1.2.2 | Certificado de planeación: cumplimiento del EOT/PBOT (uso del suelo y condiciones urbanísticas) y que el predio no está en riesgo no mitigable. | Yondó está a orillas del Magdalena: pedir explícitamente el concepto de amenaza por inundación del lote y su cota frente a las crecientes. | Secretaría de Planeación de Yondó |
| 7.1.2.3 | Certificación de disponibilidad de servicios (agua potable, alcantarillado, energía) o hoja de ruta para proveerlos. | Disponibilidad de acueducto y alcantarillado del prestador municipal y de energía de EPM para la nueva carga (incluida la planta y la solar). | Prestadores de servicios públicos |
| 7.1.2.4 | Documento de Capacidad Instalada concertado entre la E.S.E. y la Subdirección de Prestación de Servicios de MinSalud, en el marco del PTRRM. | Definir camas, camillas, consultorios, salas y equipos de la torre y concertarlo; puede partir de la 'capacidad instalada tipo' que publique MinSalud (parágrafo 1, Res. 1519). | E.S.E. + MinSalud (Subdirección de Prestación de Servicios) |
| 7.1.2.5 | Programa médico arquitectónico con áreas de cada ambiente, servicio y circulaciones. | Usar las áreas mínimas de la Res. 1633 (Anexo 1) y de la Res. 3100 (ver parametros_diseno). | Arquitecto diseñador |
| 7.1.2.6 | Diseños arquitectónicos (localización, plantas, cubiertas, cortes y fachadas) a escala 1:75, 1:100 o 1:125, acotados, amoblados y firmados con matrícula, que cumplan la n… | Diseño de la torre según Res. 1633 y 3100, NSR-10 Grupo IV y accesibilidad. | Arquitecto con matrícula |
| 7.1.2.8 | Implantación de la propuesta en el levantamiento topográfico con curvas de nivel. | Levantamiento del lote (el prado queda unos 2 m por encima de la vía occidental, según Street View). | Topógrafo + arquitecto |
| 7.1.2.9 | Estudios topográficos y de suelos; diseños estructural, hidrosanitario, contra incendio, eléctrico, redes de voz y datos, y mecánicos (gases medicinales, ventilación), fi… | Estructura Grupo IV (I = 1,5; umbral de daño), rociadores NFPA 13/NTC 2301, RETIE 3.28.3.2, gases medicinales, climatización según Cuadro 4 de la Res. 1633. | Especialistas con matrícula |
| 7.1.2.10 | Presupuesto detallado de obra, fechado y firmado por quien lo elaboró y por el profesional de la entidad que lo revisó. | Presupuesto por capítulos con APU (ver tareas de presupuesto del proyecto). | Presupuestador + profesional de la entidad |
| 7.1.2.11 | Mobiliario dentro del proyecto de infraestructura (solo para servicios exclusivos de primer nivel con desarrollo integral): listado con especificaciones y precios, cuadro… | Aplica si la torre se presenta como desarrollo integral (estudios, diseños y obra) de servicios exclusivos de primer nivel. Ojo: la ecografía es mediana complejidad en la Res. 3100 (ver servicios_3100… | E.S.E. |
| 7.1.5 | Equipamiento fijo: listado con especificaciones, cantidad, precio, justificación (nuevos servicios o incremento de capacidad), cuadro comparativo, planos con ubicación, c… | Planta eléctrica, transferencias y UPS, ascensor camillero, bombas y tanques, aire acondicionado y ventilación, central o manifold de gases, autoclave, lavachatas, sistema contra incendio. (Las autocl… | E.S.E. + ingeniería |
| 7.1.6 a | Dotación biomédica: listado por servicio con especificaciones, cantidades, precios, cuadro comparativo, justificación con inventario existente, certificación de disponibi… | Dotación de urgencias, parto, hospitalización, consulta, odontología, laboratorio clínico (con tamizaje y analizadores), rayos X, ecografía, esterilización, vacunación y farmacia. Incluir inventario a… | E.S.E. + ingeniero biomédico |
| 7.1.6 b | Dotación TIC: documento de software y hardware con licencias, especificaciones y manuales, plan de implementación y capacitación, listado con cotizaciones (2 marcas) y ce… | Sistema de información del laboratorio (LIS), PACS/RIS para imágenes, red de datos y telemedicina. | E.S.E. + ingeniero de sistemas |
| 7.1.7 | Adecuaciones: certificado de tradición, documento de evaluación del estado de la infraestructura (formato DPSAP), presupuesto aprobado (formato DPSAP); tope de 500 SMMLV … | Solo si se financia aparte la adecuación del edificio actual para archivo, bodega y administración. Tope: 500 SMMLV = $875.452.500 en 2026 (cálculo propio). | E.S.E. |
| 7.1.9 | Estudios y diseños e interventoría como proyecto separado: título, uso de suelo, servicios, Capacidad Instalada aprobada, programa médico arquitectónico, relación de prod… | Ruta recomendable si no hay diseños: un primer proyecto solo para estudios y diseños de la torre. | E.S.E. / municipio |
| 7.1.10 | Telesalud como proyecto propio: listado con cotizaciones, plataforma con certificación de datos, certificación de disponibilidad y modelo de operación (telemedicina artic… | Si la telemedicina se financia aparte (por ejemplo con MinTIC o MinSalud). | E.S.E. |
| 7.1.12 | Llave en mano a precio global fijo sin fórmula de reajuste: título, uso de suelo, servicios, Capacidad Instalada aprobada, estudio del sector, estudio de mercado (3 cotiz… | Ruta alterna a 7.1.2 cuando aún no hay diseños completos: se radica con anteproyecto y el contratista diseña y construye. Exige anteproyecto y memorias sólidas para no quedar corto en el precio global… | E.S.E. / municipio |
| Art. 6 / Art. 5 | Ruta del concepto según la fuente. | Con plata de MinSalud o por Obras por Impuestos: concepto de MinSalud. Solo con plata territorial y por debajo de 5.000 SMMLV: concepto de la Secretaría Seccional de Salud de Antioquia. Con regalías: … | E.S.E. + Gobernación |
| Res. 1633, art. 4 | Transición del marco técnico. | La torre no tiene licencia, concepto ni obra al 11-ago-2025: se diseña con la Res. 1633 completa. | Arquitecto diseñador |

**Control especial de oferta.** La infraestructura y el equipamiento fijo suman $25.740 M, más que el umbral de 5.000 salarios mínimos ($8.755 M en 2026): el proyecto necesita **concepto de MinSalud** y estar en el plan de inversiones del departamento (Plan Bienal o, desde 2025, el **PMIDS** de Antioquia). Cálculo propio.

**Otras normas de diseño** (detalle en `normas.json`): Res. 1633 de 2025 (áreas mínimas, módulo de 1,20 m, corredores de 2,40-2,80 m, climatización por ambiente, adaptación al cambio climático), Res. 3100 de 2019 (estándares de los 13 servicios), NSR-10 títulos A, J y K (sismo, fuego y evacuación: rociadores en todo el edificio), RETIE 2024 y su modificación de 2026 (planta que entra en menos de 10 segundos, UPS en áreas críticas), NTC 2050 sección 517, Índice de Seguridad Hospitalaria de la OPS (reserva de agua y combustible para 72 horas), Res. 591 de 2024 (residuos) y NTC 6047 (accesibilidad).

**Tres choques entre normas y cómo se resolvieron:** reserva de agua (24 h en la 3100, 48 h en la 1633, 72 h en el índice de la OPS: se adopta 72 h); áreas mínimas (se toma siempre la mayor, por ejemplo habitación TPR de 24 m² y no de 16); ecografía (la 3100 la trata como mediana complejidad: hay que decidirlo en el Documento de Capacidad Instalada).

## 3. El proyecto tipo que la inspira

| Proyecto tipo | Qué es | Qué se toma | Qué no se toma |
|---|---|---|---|
| **Construcción y dotación de infraestructura básica en salud**, DNP con MinSalud, v1.0 (ene-2018, precios de 2017) — [PDF](https://proyectostipo.dnp.gov.co/images/pdf/salud/PTsalud.pdf) | Puesto o centro de un piso, 320,6 m², con presupuesto de $885 M de 2017 ($1.461 M de 2026, $5,4 M por m²) | Módulo estructural repetible en pórticos de concreto; circulación central bajo aleros; fachadas largas al norte y al sur, aleros de 1/3 de la altura, ventilación cruzada y árboles al oriente y occidente; concreto a la vista, aluminio natural con vidrio laminado; torre técnica como hito; dotación por ambiente; presupuesto por actividades MGA | Sus normas de base (Res. 4445 de 1996 y 2003 de 2014, derogadas); la luz de 7,60 × 4,30 m (se cambia por 7,20 m, múltiplo del módulo de 1,20 m de la Res. 1633); la cubierta azul (pasa a blanca reflectiva) |
| **Puesto de salud tipo**, MinSalud (2017) — [PDF](https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/VS/PSA/puesto-salud-tipo.pdf) | 128,5 m² en sistema liviano de PVC, sin precios | Dotación mínima por ambiente; 39 % de circulación y muros como piso del factor; muros interiores livianos en seco | El sistema de paneles de PVC (no sirve para un edificio de grupo IV de varios pisos) |
| Proyectos tipo DNP de **ambulancias** (2018) y **cadena de frío** (2016) | Vehículos TAB/TAM y cuarto frío del PAI | Componentes y costos de referencia | Se articulan como proyectos aparte (P9 y opcional) |
| **CAPS** de MinSalud (2023-2025) | Política de centros de atención primaria; sin diseño tipo publicado | La torre como sede principal de la red de Yondó | — |

**Búsquedas sin resultado** (22-oct-2026): no hay “centro de salud tipo” ni “hospital de primer nivel tipo” en la biblioteca de MinSalud; la Gobernación de Antioquia no publica prototipos; las “capacidades instaladas tipo” que prometió la Res. 1211 no están publicadas (`proyecto_tipo.json`).

**Cómo se ve.** Volumen de concreto claro y pañete blanco con aleros y quiebrasoles; base y fachadas en ladrillo terracota que recuerdan las alas que se demuelen; celosías verticales en la fachada occidental; cubierta blanca con paneles solares; el mango grande del prado se conserva y da sombra a la plaza de entrada.

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

## 5. Dotación y laboratorio

La dotación biomédica y el mobiliario clínico suman **$4.269 M** (228 ítems; 35 con precio de referencia de SECOP y el resto estimados con rango). El equipamiento fijo (planta, UPS, ascensores, gases, aire, bombas, redes y sistemas especiales) se presupuesta dentro de la obra con los mismos precios de `dotacion.json` y no se suma dos veces.

| Servicio | Valor | Equipos más costosos |
|---|---:|---|
| Urgencias de baja complejidad | $516 M | Ventilador de transporte; Bomba de infusión volumétrica |
| Consulta externa general y especializada, procedimientos menores y promoción y prevención | $368 M | Kit de examen básico; Equipo de órganos de los sentidos de pared |
| Telemedicina (prestador remisor) | $71 M | Retinógrafo portátil; Estación de telemedicina |
| Odontología general y radiología odontológica | $201 M | Unidad odontológica completa; Rayos X periapical de pared con radiovisiógrafo |
| Toma de muestras de laboratorio clínico | $45 M | Nevera de muestras 2-8 °C con registrador de temperatura; Impresora de etiquetas con código de barras y lector |
| Laboratorio clínico (bienes que compra el hospital) | $357 M | Microscopio binocular con objetivo de inmersión; Cabina de bioseguridad clase II tipo A2 |
| Imágenes diagnósticas: rayos X digital y ecografía | $675 M | Equipo de rayos X digital fijo con detector plano; Ecógrafo multipropósito con 3 transductores |
| Atención del parto de baja complejidad y adaptación neonatal | $454 M | Cama de partos multiposición para habitación TPR; Lámpara de techo LED para atención del parto |
| Hospitalización general de baja complejidad | $391 M | Bomba de infusión volumétrica; Regulador de vacío de pared con frasco |
| Central de esterilización | $365 M | Autoclave de vapor central de carga frontal; Lavadora desinfectora de instrumental |
| Vacunación con cadena de frío | $53 M | Refrigerador de vacunas precalificado OMS; Registradores de temperatura de 30 días y termómetros digitales |
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

## 6. Presupuesto por capítulos

Presupuesto de prefactibilidad (clase 4: precisión esperada de −25 % a +35 %). Las cantidades salen del programa con rendimientos por m² escritos en cada ítem de `presupuesto.json` (por ejemplo: 0,36 m³ de concreto y 62 kg de acero por m² de placa; 0,33 ml de muro por m²; un rociador cada 9 m²).

| # | Capítulo | Costo directo | Peso | Con AIU |
|---|---|---:|---:|---:|
| 1 | Preliminares, campamento y demolición del antiguo Centro Vida | $564 M | 2,9 % | $749 M |
| 2 | Movimiento de tierras y cimentación | $1.868 M | 9,7 % | $2.484 M |
| 3 | Estructura en concreto reforzado (NSR-10, grupo IV, coeficiente de importancia 1,5) | $2.792 M | 14,4 % | $3.712 M |
| 4 | Mampostería, muros y fachadas | $1.360 M | 7,0 % | $1.807 M |
| 5 | Cubiertas e impermeabilización | $273 M | 1,4 % | $362 M |
| 6 | Pisos, acabados hospitalarios y cielos rasos | $1.868 M | 9,7 % | $2.484 M |
| 7 | Carpintería metálica y de madera, puertas y vidrios | $1.245 M | 6,4 % | $1.656 M |
| 8 | Instalaciones hidrosanitarias, agua caliente y aguas lluvias | $907 M | 4,7 % | $1.206 M |
| 9 | Red contra incendio (NSR-10 títulos J y K; NFPA 13, 14 y 20; NTC 2301) | $634 M | 3,3 % | $842 M |
| 10 | Instalaciones eléctricas, iluminación y sistema eléctrico esencial (RETIE 2024 y 2026, NTC 2050 sección 517, RETILAP) | $2.334 M | 12,1 % | $3.103 M |
| 11 | Voz, datos y comunicaciones | $361 M | 1,9 % | $480 M |
| 12 | Gases medicinales | $571 M | 3,0 % | $759 M |
| 13 | Aire acondicionado y ventilación mecánica (Res. 1633, Cuadro 4) | $1.550 M | 8,0 % | $2.060 M |
| 14 | Ascensores y montacargas | $780 M | 4,0 % | $1.037 M |
| 15 | Sistemas especiales | $482 M | 2,5 % | $641 M |
| 16 | Galería de conexión con el edificio actual y pasaje de servicio | $78 M | 0,4 % | $104 M |
| 17 | Urbanismo, bahía de ambulancias, parqueaderos, cerramiento, bloque técnico y residuos | $653 M | 3,4 % | $868 M |
| 18 | Paisajismo y arborización | $60 M | 0,3 % | $80 M |
| 19 | Solar fotovoltaica, baterías y conexión con la microrred | $982 M | 5,1 % | $1.306 M |
| | **Costo directo** | **$19.361 M** | 100 % | |
| | Administración (24 %) | $4.647 M | | |
| | Imprevistos (3 %) | $581 M | | |
| | Utilidad (5 %) e IVA sobre la utilidad (19 %) | $1.152 M | | |
| | **Valor de la obra** | | | **$25.740 M** |

**La administración de 24 % incluye** el personal de dirección (9 %), servicios y ensayos (2 %), pólizas (1 %), la **contribución de 5 % sobre los contratos de obra pública** de la Ley 1106 de 2006 (≈ 6,6 % del costo directo), estampillas (2,5 %, por verificar), ICA de Yondó (0,8 %) y gastos generales (2 %). Estimación.

### 6.1 Lo que va por fuera de la obra

| Componente | Valor | Cómo se calculó |
|---|---:|---|
| Estudios y diseños | $1.426 M | Topografía, geotecnia con análisis de licuación, diseños arquitectónico (2,0 % de la obra), estructural (0,7 %), técnicos (1,6 %), presupuesto (0,3 %) e interventoría de diseños (8 %) |
| Formulación y licencia | $377 M | Documento de Capacidad Instalada, estudio de mercado y MGA ($120 M) y licencia (1 % de la obra, por verificar) |
| Interventoría de obra | $1.802 M | 7 % del valor de obra con IVA, con la supervisión técnica independiente de la Ley 1796 de 2016 |
| Gestión ambiental y social | $45 M | Permiso forestal, plan de manejo ambiental y socialización |
| Dotación | $3.226 M | `dotacion.json`: todos los servicios menos laboratorio, toma de muestras y TIC |
| Laboratorio clínico | $523 M | Equipos propios del laboratorio y la toma de muestras + puesta en marcha (2 meses de reactivos, validación, control externo) |
| Sistemas de información | $931 M | Computadores, PACS/RIS y telemedicina de `dotacion.json` + LIS, interoperabilidad y ciberseguridad |
| Equipamiento fijo fuera de la obra | $650 M | Generador de oxígeno PSA (recomendado) |
| Puesta en marcha y habilitación | $250 M | Traslado, aseo terminal, licencia de rayos X, habilitación en el REPS, capacitación e inventario de 72 h |
| Contingencias | $1.566 M | 5 % de obra, dotación y equipos (no cubre inflación) |
| **Total de la torre** | **$36.536 M** | Rango $26.894 M–$49.827 M (suma de mínimos y máximos de cada ítem) |

**Para no contar dos veces:** la planta, la UPS, los ascensores, la central de gases, el aire acondicionado, las bombas, la red de datos y los sistemas especiales están en la obra con el mismo precio de `dotacion.json`; los analizadores del laboratorio van en comodato; la lavandería va con el edificio actual; y la solar, las baterías y el BMS de la torre se cuentan aquí, así que el proyecto de la microrred (`data/presupuesto_microrred.json`) debe descontar el nodo hospital.

### 6.2 ¿Es caro o barato? Comparación por m²

Valor de obra por m² construido: **$7,11 M** (rango $5,57 M–$9,31 M). Sin el equipamiento fijo ni la solar: **$5,34 M**. Costo total por m² (con dotación, diseños, interventoría y contingencias): $10,09 M. Todo sobre los 3.620,6 m² construidos del proyecto (cálculo propio).

| Proyecto | Año | Área | Costo por m² en pesos de 2026 | Qué incluye | Fuente |
|---|---|---:|---:|---|---|
| Proyecto tipo DNP-MinSalud de infraestructura básica en salud (puesto o centro de un piso) | 2017 | 270 m² | $5,42 M | Costo directo con AIU teórico y exteriores; sin dotación ni interventoría | [enlace](https://proyectostipo.dnp.gov.co/images/pdf/salud/PTsalud.pdf) |
| Nueva sede hospitalaria de Monguí (Boyacá), MinSalud: urgencias, hospitalización, partos y laboratorio | 2025 | 2.400 m² | $5,71 M | 'Inversión superior a $13 mil millones'; no dice si incluye dotación | [enlace](https://consultorsalud.com/salud-en-boyaca-minsalud-300-mil-millones/) |
| Hospital Santa Catalina de Sena, Sucre (Sucre), Fondo Adaptación: urgencias, consulta, laboratorio, imágenes, partos, hospitalización | 2017 | 2.032 m² | $4,80 M | Obra (la interventoría de $681,7 millones va aparte); edificio bajo | [enlace](https://www.eluniversal.com.co/regional/2017/10/13/comenzara-construccion-del-nuevo-hospital-de-sucre-con-millonaria-inversion/) |
| Hospital de Fusagasugá (Cundinamarca), Gobernación: mediana y alta complejidad | 2026 | 24.966 m² | $9,29 M | Inversión total anunciada; complejidad mayor que la torre; cifra tomada del extracto del buscador (el artículo respondió con error 403) | [enlace](https://cambiocolombia.com/contenido-especial/articulo/2026/9/cundinamarca-amplia-su-red-publica-de-salud-con-nuevos-hospitales-y-mas-dotacion-tecnologica) |
| Reposición del hospital de Guarne (Antioquia), MinSalud, CONPES 4169 | 2026 | no publicada | — (total $35.059 M) | Aporte de MinSalud con vigencias futuras hasta 2030; obra de ≈ 19 meses; área no publicada | [enlace](https://www.elcolombiano.com/antioquia/guarne-antioquia-nuevo-hospital-millones-ministerio-de-salud-EG36212125) |
| Construcción de la infraestructura física de la E.S.E. Álvaro Ramírez González, San Martín (Cesar) | 2024 | no publicada | — (total $34.119 M) | Valor adjudicado en SECOP II (15 meses); área no publicada | [enlace](https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.5438578) |
| Hospital de Majagual (Sucre): urgencias, consulta, obstetricia, cirugía ambulatoria, laboratorio | 2025 | no publicada | — (total $26.034 M) | Inversión total (Fondo Adaptación, MinSalud, Gobernación, Alcaldía y E.S.E.); 18 meses | [enlace](https://www.elheraldo.co/sucre/2025/10/30/arranca-construccion-de-un-hospital-en-la-mojana-de-sucre/) |

**Lectura.** La obra civil de la torre por m² queda entre la de Santa Catalina de Sena (un edificio bajo, de 2017) y la de Monguí (2025), y muy por debajo de un hospital de mediana y alta complejidad como el de Fusagasugá. Con ascensores, planta, aire acondicionado, gases, sistemas especiales, solar y baterías, sube un 25-50 %. También cae en el extremo bajo del orden de magnitud que se había estimado escalando el proyecto tipo DNP ($7,0–9,8 M por m², `proyecto_tipo.json`). Los totales de Guarne ($35.059 M), San Martín, Cesar ($34.119 M de 2026) y Majagual ($26.034 M de 2026) muestran que un hospital de primer nivel nuevo cuesta hoy entre $25.000 y $40.000 M.

## 7. Análisis de precios unitarios (APU) destacados

`apu.json` trae 19 APU completos. Precios oficiales de Antioquia: la **Base de APU de la Secretaría de Infraestructura Física de la Gobernación (2020-II)**, la más reciente descargable en su sitio, con la mano de obra actualizada por el **salario mínimo** (×1,9946: pasó de $877.803 a $1.750.905) y equipos y materiales por **IPC** (×1,5054); y las **compras de 2025-2026 de la Gobernación de Antioquia en la Tienda Virtual del Estado** (cemento a $32.896 el bulto, pintura epóxica antibacterial a $196.577 el galón, cable libre de halógenos a $2.687 el metro, entre otros). Jornal con prestaciones: ayudante $117.852, oficial $235.701, oficial especializado $285.981 (cálculo propio).

| APU | Ítem | Unidad | Materiales | Equipo | Mano de obra | Transporte y otros | Costo directo | Con AIU |
|---|---|---|---:|---:|---:|---:|---:|---:|
| APU-01 | Demolición de edificación de un piso (mampostería, estructura de concreto, pisos y cimientos) | m2 | $0 | $22.995 | $31.427 | $30.548 | **$84.970** | $112.967 |
| APU-02 | Retiro de cubierta de teja de fibrocemento con posible asbesto, embalaje y disposición como residuo peligroso | m2 | $11.958 | $12.000 | $22.231 | $32.612 | **$78.801** | $104.766 |
| APU-03 | Excavación mecánica en material común para cimentación y cisternas (hasta 3 m), con cargue y retiro | m3 | $0 | $15.048 | $15.714 | $38.456 | **$69.218** | $92.026 |
| APU-04 | Concreto de 28 MPa para columnas y muros estructurales (pórticos y núcleos, NSR-10 grupo IV) | m3 | $750.366 | $174.194 | $301.124 | $27.227 | **$1.252.911** | $1.665.746 |
| APU-05 | Concreto de 28 MPa para vigas y losa nervada de entrepiso y cubierta | m3 | $741.302 | $185.082 | $245.803 | $24.461 | **$1.196.648** | $1.590.943 |
| APU-06 | Acero de refuerzo fy = 420 MPa (grado 60) figurado y amarrado | kg | $5.012 | $45 | $2.288 | $391 | **$7.736** | $10.285 |
| APU-07 | Pilote preexcavado de 0,60 m de diámetro en concreto de 28 MPa | ml | $223.440 | $250.635 | $39.126 | $12.967 | **$526.168** | $699.540 |
| APU-08 | Muro en bloque de arcilla No. 5 (e = 15 cm) con refuerzo y anclaje a la estructura | m2 | $74.485 | $2.500 | $39.284 | $13.964 | **$130.233** | $173.145 |
| APU-09 | Muro liviano en placa de yeso resistente a humedad, doble cara, con aislamiento acústico | m2 | $93.717 | $1.500 | $29.463 | $7.723 | **$132.403** | $176.030 |
| APU-10 | Pintura epóxica antibacterial (2 manos) sobre estuco y sellador, en muros de áreas asistenciales | m2 | $29.138 | $800 | $17.678 | $1.134 | **$48.750** | $64.813 |
| APU-11 | Piso vinílico heterogéneo hospitalario de 2 mm con mediacaña sanitaria y autonivelante | m2 | $177.360 | $3.000 | $27.195 | $3.485 | **$211.040** | $280.578 |
| APU-12 | Cielo raso registrable en fibra mineral de alta higiene 61 × 61 cm con perfilería suspendida y arriostramiento sísmico | m2 | $79.570 | $1.000 | $16.071 | $2.304 | **$98.945** | $131.547 |
| APU-13 | Ventanería en aluminio anodizado natural con vidrio laminado de seguridad 4+4 mm | m2 | $360.550 | $0 | $67.306 | $9.615 | **$437.471** | $581.618 |
| APU-14 | Impermeabilización de cubierta plana con aislamiento térmico y acabado blanco reflectivo | m2 | $131.035 | $2.000 | $31.820 | $3.591 | **$168.446** | $223.948 |
| APU-15 | Red de gases medicinales en tubería de cobre tipo K desengrasada (oxígeno, aire medicinal y vacío) | ml | $83.753 | $8.358 | $26.922 | $1.646 | **$120.679** | $160.442 |
| APU-16 | Ducto de aire acondicionado y extracción en lámina galvanizada con aislamiento térmico | kg | $13.260 | $600 | $6.731 | $612 | **$21.203** | $28.189 |
| APU-17 | Salida para tomacorriente normal doble con polo a tierra 20 A en tubería EMT y cable libre de halógenos | un | $146.001 | $1.000 | $67.306 | $4.115 | **$218.422** | $290.392 |
| APU-18 | Salida para tomacorriente grado hospitalario del sistema eléctrico esencial (regulada, con tierra aislada) | un | $210.751 | $1.000 | $80.767 | $4.913 | **$297.431** | $395.435 |
| APU-19 | Punto hidráulico de agua fría en PVC presión de 1/2" con válvula de paso | un | $51.874 | $0 | $67.306 | $3.865 | **$123.045** | $163.588 |

**APU-04 · Concreto de 28 MPa para columnas y muros estructurales (pórticos y núcleos, NSR-10 grupo IV) (m3)**

| Componente | Cantidad | Precio | Valor | Fuente |
|---|---:|---:|---:|---|
| Concreto premezclado de 28 MPa (4.000 psi) puesto en Yondó | 1,000 m3 (+5 %) | $700.000 | $735.000 | estimacion |
| Curador de concreto tipo antisol blanco | 1,120 kg (+0 %) | $9.702 | $10.866 | calculo_propio sobre dato oficial |
| Desmoldante para formaleta | 0,500 l (+0 %) | $9.000 | $4.500 | estimacion |
| Vibrador de concreto | rend. 5,92 | $80.658/día | $13.625 | calculo_propio sobre dato oficial |
| Formaleta metálica para columnas y muros | rend. 0,71 | $96.796/día | $135.569 | calculo_propio sobre dato oficial |
| Bomba de concreto o elevación con winche y balde | 1,000 | $25.000/m3 | $25.000 | estimacion |
| Cuadrilla de concretos (1 oficial + 5 ayudantes (método SIF)) | rend. 2,86 m3/día | $860.310/día | $301.124 | cálculo propio |
| Herramienta menor (5 % de la mano de obra) | | | $15.056 | método SIF |
| Acarreo interno (1,05 m³) | | | $12.171 | cálculo propio |
| Incluido en el precio del material puesto en Yondó (el concreto premezclado ya trae ≈ $40.000/m³ de transporte desde la planta de Barrancabermeja) | | | $0 | estimación |
| **Costo directo** | | | **$1.252.911** | |
| AIU (24 % + 3 % + 5 % + IVA del 19 % sobre la utilidad) | | | $412.835 | |
| **Precio unitario** | | | **$1.665.746** | |

*Comparación:* SIF 2020-II ítem 6.2.30, concreto de 28 MPa en vigas y columnas: $735.062/m³; × IPC = $1.106.548. El APU es más alto porque la mano de obra se actualiza con el salario mínimo (que subió casi el doble desde 2020) y no con el IPC.

**APU-06 · Acero de refuerzo fy = 420 MPa (grado 60) figurado y amarrado (kg)**

| Componente | Cantidad | Precio | Valor | Fuente |
|---|---:|---:|---:|---|
| Acero corrugado G-60 (fy = 420 MPa) figurado | 1,000 kg (+5 %) | $4.600 | $4.830 | estimacion |
| Alambre negro recocido calibre 18 | 0,030 kg (+0 %) | $6.050 | $182 | calculo_propio sobre dato oficial |
| Cizalla y dobladora | 3,000 | $15/kg | $45 | calculo_propio sobre dato oficial |
| Cuadrilla de refuerzo (1 oficial + 2 ayudantes (método SIF)) | rend. 170,00 kg/día | $388.908/día | $2.288 | cálculo propio |
| Herramienta menor (5 % de la mano de obra) | | | $114 | método SIF |
| Transporte interno | | | $151 | cálculo propio |
| Flete del acero desde Barrancabermeja o Bucaramanga | | | $126 | estimación |
| **Costo directo** | | | **$7.736** | |
| AIU (24 % + 3 % + 5 % + IVA del 19 % sobre la utilidad) | | | $2.549 | |
| **Precio unitario** | | | **$10.285** | |

*Comparación:* SIF 2020-II ítem 10.1: $4.478/kg; × IPC = $6.741/kg. Del mismo orden; la diferencia es la mano de obra actualizada con el salario mínimo.

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
| Instalador especializado de vinilo (1 oficial especializado + 1 ayudante) | rend. 22,00 m2/día | $403.833/día | $18.356 | cálculo propio |
| Preparación de base y autonivelante (1 oficial + 1 ayudante) | rend. 40,00 m2/día | $353.553/día | $8.839 | cálculo propio |
| Herramienta menor (5 % de la mano de obra) | | | $1.360 | método SIF |
| Flete de vinilo y autonivelante desde Medellín o Bogotá | | | $2.125 | estimación |
| **Costo directo** | | | **$211.040** | |
| AIU (24 % + 3 % + 5 % + IVA del 19 % sobre la utilidad) | | | $69.538 | |
| **Precio unitario** | | | **$280.578** | |

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
| Cuadrilla capacitada en asbesto y alturas (1 oficial + 3 ayudantes) | rend. 40,00 m2/día | $589.257/día | $14.731 | cálculo propio |
| Profesional de seguridad y salud en el trabajo (1 profesional) | rend. 40,00 m2/día | $300.000/día | $7.500 | cálculo propio |
| Herramienta menor (5 % de la mano de obra) | | | $1.112 | método SIF |
| Transporte especializado y disposición en celda de seguridad (≈ 15 kg de teja por m²) | | | $31.500 | estimación |
| **Costo directo** | | | **$78.801** | |
| AIU (24 % + 3 % + 5 % + IVA del 19 % sobre la utilidad) | | | $25.965 | |
| **Precio unitario** | | | **$104.766** | |

*Comparación:* Rango de mercado del retiro de asbesto en Colombia: $60.000-$120.000/m² (estimación). Si el laboratorio confirma que la teja no tiene asbesto, el retiro baja a ≈ $25.000/m² como RCD común.

## 8. Fuentes de financiación

| Fuente | Rango posible | Escenario base | Probabilidad | Requisito principal | Cuándo |
|---|---:|---:|---|---|---|
| SGR – Asignaciones Directas (incluidas las anticipadas) del Municipio de Yondó como productor de hidrocarburos | $2.000 M–$12.000 M | $6.736 M | alta (depende solo de la decisión del municipio) | Proyecto en MGA y en el SUIFP-SGR con los requisitos sectoriales de salud (Acuerdo Único de la Comisión Rectora; normas.json advierte que hay que confirmar si se exige concepto de … | Ya: el saldo 2025-2026 sin aprobar alcanza para P1 (radicar nov-2026 a feb-2027). Bienio 2027-2028: el presupuesto se ap… |
| SGR – Incentivo a la producción asignado a Yondó para proyectos del OCAD Paz y Asignación para la Paz (municipio PDET) | $0 M–$12.000 M | $5.500 M | media | Iniciativa del PATR del PDET Sur de Bolívar (pilar de salud rural; verificar que exista o incluirla), proyecto en MGA y aprobación del OCAD Paz. | Convocatorias y sesiones del OCAD Paz en 2027-2028. |
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
| Crédito: Findeter con tasa compensada para infraestructura y dotación en salud (Res. 2316 de 2025) o IDEA | $0 M–$5.000 M | $1.500 M | baja-media | Concepto técnico territorial (MinSalud responde en 20 días hábiles); capacidad de endeudamiento (Ley 358 de 1997). Lo debe tomar el municipio: la E.S.E. está en saneamiento. | 2028, para el cierre financiero de P2. |
| Ecopetrol – inversión social en su área de influencia (campos Casabe y Llanito) o como contribuyente de Obras por Impuestos | $0 M–$2.000 M | $300 M | baja | Convenio con Ecopetrol o selección como contribuyente en Obras por Impuestos; alineación con sus programas sociales. | Gestión desde 2027. |
| Cooperación internacional (OPS, bancos de desarrollo, agencias y embajadas; donación de equipos) | $0 M–$800 M | $200 M | baja | Proyecto con enfoque de hospital seguro y resiliente o de atención primaria rural; contrapartida local. | Variable. |
| **Total** | | **$36.536 M** | | | |

**Datos clave detrás de los montos:**

- **SGR – Asignaciones Directas:** Bienio 2025-2026 (MinHacienda, corte oct-2026): Asignaciones Directas $34.178 millones presupuestadas y $26.481 aprobadas; anticipadas $15.162 y $13.290 → saldo sin aprobar ≈ $9.569 millones (cálculo propio). Bienio 2027-2028: el proyecto de ley de presupuesto del SGR (radicado el 2-oct-2026) baja 11 % el total nacional (de $30,96 a $27,54 billones) y asigna $5,37 billones a asignaciones directas; si Yondó baja en la misma proporción, tendría ≈ $28.000-36.000 millones de directas (estimación).
- **SGR – Incentivo a la producción asignado a Yondó para proyectos del OCAD Paz y Asignación para la Paz:** Bienio 2025-2026: incentivo a la producción para OCAD Paz de Yondó $14.025 millones con solo $331 aprobados (saldo ≈ $13.694 millones, cálculo propio); además, Yondó ejecutó $36.228 millones de la Asignación para la Paz en 2025-2026 (vía Ye de Marley-San Francisco). Por verificar si ese saldo ya está comprometido.
- **Presupuesto General de la Nación – MinSalud:** El CONPES 4169 (vigencias futuras 2026-2030 por $3,02 billones para 102 sedes) no incluye a Yondó; Guarne recibió $35.059 millones y Santa Bárbara $13.500 millones. Pero el proyecto de presupuesto 2027 baja la inversión propia de MinSalud de $2,6 a $1,6 billones y debe atender la reconstrucción de hospitales dañados por el terremoto del 10-ago-2026 (≈ $1 billón).
- **Gobernación de Antioquia – Secretaría Seccional de Salud:** Cofinanciación promedio por proyecto: infraestructura $729 millones (2024) y $2.322 millones (2025); dotación $716-737 millones (informe SSSA 2026, cálculo propio en docs/anexos/C-hospital-2028.md).
- **Obras por Impuestos:** Cupo CONFIS 2025: $1,1 billones (Decreto 178 de 2025); en 2025 se aprobaron 137 proyectos por ≈ $1,6 billones. El proyecto PDET de dotación de Antioquia (21 municipios, Yondó incluido) vale $44.059 millones según el DNP.
- **Crédito: Findeter con tasa compensada para infraestructura y dotación en salud:** En 2026 Yondó ya paga $1.718,5 millones de servicio de deuda con un instituto de desarrollo departamental (probablemente el IDEA).

**Si MinSalud no pone nada:** Cubre la torre solo si el municipio dedica ≈ $11.036 millones de directas y el OCAD Paz aprueba ≈ $9.000 millones. Si no, se puede partir la obra en dos etapas: pisos 1 a 3 con bloque técnico primero (≈ 85 % del valor, porque la cimentación, los núcleos y los equipos se hacen completos) y el piso 4 después. Urgencias, partos, hospitalización, consulta y laboratorio quedarían habilitados en la primera etapa; odontología, terapias y telemedicina seguirían un tiempo en el edificio actual.

### 8.1 Qué cambió frente a `docs/06-hospital-2028-financiacion.md`

- docs/06 y data/hospital2028.json calculaban un proyecto de $9.470 millones (reforzar y adecuar el hospital actual, energía, telesalud y equipos) con un escenario probable de $13.100 millones para 2027-2029. La torre nueva cuesta $36.536 millones más $2.613 millones de proyectos complementarios: se acerca al escenario ambicioso de docs/06 ($34.550 millones) y lo supera.
- El componente 'reforzamiento y adecuaciones' ($3.000 millones) de docs/06 se reemplaza por la torre (P2-P3) y por la adecuación del edificio actual para usos no asistenciales (P8, ≈ $1.963 millones).
- MinSalud: docs/06 suponía $3.000 millones (probable) y $13.500 millones (ambicioso). Aquí se suben a $12.000 millones en el escenario base porque una reposición de torre es la tipología que MinSalud cofinancia (Guarne, $35.059 millones), pero su probabilidad baja: el presupuesto 2027 recorta la inversión de MinSalud (de $2,6 a $1,6 billones) y el terremoto del 10-ago-2026 compite por esos recursos.
- Regalías: docs/06 suponía $1.000-5.500 millones. Se suben a $6.736 millones de directas más $5.500 millones del incentivo para OCAD Paz, porque la torre sería la inversión principal del bienio y porque se encontró un saldo de ≈ $13.694 millones de ese incentivo sin aprobar en 2025-2026. El bienio 2027-2028 trae 11 % menos a nivel nacional.
- PMIDS: docs/06 señalaba el plazo de remisión de iniciativas hacia el 10-oct-2026. Si no se registró, la torre debe entrar en la actualización obligatoria del primer semestre de 2028 (o en un ajuste que permita la Secretaría Seccional).
- Las fuentes de energía (FENOGE) y TIC (MinTIC) se mantienen en los mismos rangos de docs/06; la solar y las baterías del hospital ahora se instalan en la torre (P7) y no en el edificio actual.
- Findeter: docs/06 lo ponía en $0-2.000 millones; aquí $0-5.000 millones, siempre como deuda del municipio (la E.S.E. está en saneamiento).

## 9. Proyectos a articular

Hay que articular 9 proyectos: 7 forman la torre ($36.536 millones) y 2 la complementan (edificio actual y ambulancia, $2.613 millones). Se pueden presentar en 7 fichas MGA uniendo P2 con P3 (proyecto mixto) y P4 con P5. Lo mínimo para abrir la torre son 3: estudios y diseños (P1), construcción con equipamiento fijo (P2+P3) y dotación con laboratorio (P4+P5).

| # | Proyecto | Valor | Rango | Fuente más adecuada | Quién lo presenta | Concepto (Res. 485) | MGA | Depende de | Fechas |
|---|---|---:|---|---|---|---|---|---|---|
| P1 | Estudios y diseños integrales, formulación y licencia de la torre de primer nivel | $1.803 M | $1.124 M–$2.660 M | SGR – Asignaciones Directas (saldo 2025-2026) o recursos propios del municipio; apoyo técnico de la Secretaría Seccional de Salud. | Municipio de Yondó (ejecutor) con la E.S.E. Hospital Héctor Abad Gómez | Num. 7.1.9 (estudios y diseños e interventoría como proyecto separado). Con recursos territoriales y menos de 5.000 SMMLV, el concepto lo emite la Secretaría Seccional de Salud de Antioquia (Res. 485, arts. 5 y 6). | Sector 19 Salud y Protección Social; programa 1906; producto 1906034 'Estudios de preinversión' (código 190603400). | Título del lote; Certificado de uso del suelo y de riesgo; Decisión sobre el uso del edificio actual | 2026-11 a 2027-12 |
| P2 | Demolición del antiguo Centro Vida y construcción de la torre de servicios de primer nivel (infraestructura física y redes) | $21.707 M | $16.708 M–$28.295 M | MinSalud (PGN) + SGR (directas, incentivo OCAD Paz, inversión regional) + Gobernación de Antioquia + crédito del municipio + recursos propios. | E.S.E. Hospital Héctor Abad Gómez ante MinSalud; Municipio de Yondó para la parte de regalías | Num. 7.1.2 (infraestructura física: reposición con fortalecimiento de capacidad instalada) o num. 7.1.12 (llave en mano). Control especial de oferta (> 5.000 SMMLV): concepto de MinSalud e inclusión en el PMIDS o Plan Bienal (art. 4; num. 7.1.1.6). | Sector 19; programa 1906; producto 1906047 'Hospitales de primer nivel de atención construidos' (190604700). | P1 terminado (diseños y licencia); Documento de Capacidad Instalada concertado; Registro en el PMIDS; Cierre financiero | 2027-11 a 2030-01 |
| P3 | Equipamiento fijo e industrial y sistemas especiales de la torre | $6.115 M | $4.274 M–$8.844 M | Recomendado: dentro del proyecto mixto con P2 (MinSalud o SGR). El generador PSA puede ir por Obras por Impuestos. | E.S.E. Hospital Héctor Abad Gómez | Num. 7.1.5 (equipamiento fijo: listado, 2 cotizaciones de 2 marcas, planos de ubicación) y 7.1.6 b para la red de datos. Cuenta para el umbral de 5.000 SMMLV de infraestructura y equipamiento fijo. | Sector 19; programa 1906; producto 1906047 (actividad de equipamiento del proyecto de construcción) o 1906005 'Hospitales de primer nivel de atención dotados' si se presenta aparte. | P2 con obra negra y cuartos técnicos listos | 2028-11 a 2030-01 |
| P4 | Dotación biomédica, mobiliario clínico y puesta en marcha de la torre | $3.649 M | $2.536 M–$5.336 M | Obras por Impuestos + Gobernación de Antioquia + SGR (inversión local); MinSalud si entra en el proyecto mixto. | E.S.E. Hospital Héctor Abad Gómez | Num. 7.1.6 a (dotación biomédica: listado por servicio, inventario actual, 2 cotizaciones). La dotación de baja complejidad no es de control especial de oferta; la ecografía es de mediana complejidad (normas.json). Con Obras por Impuestos o PGN, concepto de MinSalud. | Sector 19; programa 1906; producto 1906005 'Hospitales de primer nivel de atención dotados' (190600500). | P2 con 70 % de avance físico (Res. 2373 de 2025); Inventario de la dotación actual | 2029-03 a 2030-04 |
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
| 2026 | $72 M | $72 M | Formulación |
| 2027 | $1.551 M | $1.623 M | Estudios, diseños y formulación |
| 2028 | $4.828 M | $6.450 M | Cierre de diseños, licencia, inicio de obra (demolición, cimentación) |
| 2029 | $24.738 M | $31.189 M | Estructura, redes, acabados, equipamiento fijo, solar; inicio de dotación |
| 2030 | $5.347 M | $36.536 M | Cierre de obra, dotación, laboratorio, TIC y puesta en marcha |

Pesos constantes de 2026: los presupuestos de cada año deben indexarse. La compra de equipos empieza cuando la obra tenga 70 % de avance (Res. 2373 de 2025).

## 11. Lo que falta verificar

- Cantidades de prediseño sin planos ni estudio de suelos: la cimentación (pilotes o zapatas) y la cuantía de acero pueden mover el presupuesto ±10 %.
- La titularidad del lote, el uso del suelo, la amenaza por inundación y la norma del EOT no están verificados (normas.json).
- Las estampillas, el ICA y el impuesto de delineación de Yondó no se revisaron.
- El estudio de vulnerabilidad de 2024 del edificio actual no es público: el costo de P8 es un supuesto.
- Los precios de los equipos de dotacion.json son en su mayoría estimaciones (35 de 228 ítems con referencia SECOP).
- El presupuesto del SGR 2027-2028 por municipio no está publicado; la cifra de Yondó es una estimación proporcional.
- No se verificó si el saldo del incentivo para OCAD Paz de 2025-2026 ya tiene destino.
- La ley de presupuesto 2027 y el PND 2026-2030 pueden cambiar las líneas de MinSalud y los PMIDS.
- La base oficial de Antioquia usada es de 2020: la actualización por salario mínimo e IPC no capta cambios de precios relativos (el acero y el cemento subieron más que el IPC en 2021-2022). Se contrasta con compras de 2025-2026 de la Tienda Virtual.
- Los acabados hospitalarios (vinilo, cielo de alta higiene, guardacamillas), la ventanería y los equipos especiales no tienen precio oficial publicado: son estimaciones con rango que deben confirmarse con 2-3 cotizaciones (Res. 485, num. 7.1.1.4 y 7.1.12).

## 12. Fuentes

- Res. 485 de 2025, MinSalud: <https://www.minsalud.gov.co/Normatividad_Nuevo/Resolucion%20No%20485%20de%202025.pdf>
- Res. 1519 de 2025, MinSalud (art. 7 vigente): <https://www.minsalud.gov.co/Normatividad_Nuevo/Resolucion%20No%201519%20de%202025.pdf>
- Res. 1211 de 2025, MinSalud: <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_1211_2025.htm>
- Res. 1633 de 2025, MinSalud, y sus anexos: <https://www.minsalud.gov.co/Normatividad_Nuevo/Resolucion%20No%201633%20de%202025.pdf>
- Res. 3100 de 2019 (compilada): <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_3100_2019.htm>
- Proyecto tipo DNP de infraestructura básica en salud (2018): <https://proyectostipo.dnp.gov.co/images/pdf/salud/PTsalud.pdf>
- Puesto de salud tipo, MinSalud (2017): <https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/VS/PSA/puesto-salud-tipo.pdf>
- Gobernación de Antioquia, Base de APU SIF 2020-II (ítems 1.2, 2.7, 2.8, 2.9, 2.11, 3.2, 3.3, 4.2.3, 5.1.3, 6.1.10, 6.1.19, 6.2.15, 6.2.30, 7.1.15, 10.1): <https://www.antioquia.gov.co/images/PDF2/Infraestructura/2020/08-agosto/apu-base-referencia-sif-2020-semestre-ii.pdf>
- Tienda Virtual del Estado Colombiano, compras por ítem (órdenes 162740, 162775, 163083 y 152787 de Antioquia): <https://www.datos.gov.co/d/3hdv-smhz>
- MinHacienda, ejecución presupuestal del SGR 2025-2026 (Yondó): <https://www.datos.gov.co/d/g4qj-2p2e>
- Proyecto de presupuesto del SGR 2027-2028 (Portafolio, oct-2026): <https://www.portafolio.co/economia/gobierno/presupuesto-de-regalias-2027-2028-seria-de-27-54-billones-11-menos-503793>
- Presupuesto de salud 2027 (Minuto30, 9-sep-2026): <https://www.minuto30.com/amp/presupuesto-salud-2027/1718556/>
- CONPES 4169 (vigencias futuras para 102 sedes hospitalarias): <https://consultorsalud.com/wp-content/uploads/2025/11/4169.pdf>
- Guarne: aporte de MinSalud de $35.059 M (El Colombiano, 5-may-2026): <https://www.elcolombiano.com/antioquia/guarne-antioquia-nuevo-hospital-millones-ministerio-de-salud-EG36212125>
- Monguí: sede de 2.400 m² por más de $13.000 M (Consultorsalud, 25-jun-2025): <https://consultorsalud.com/salud-en-boyaca-minsalud-300-mil-millones/>
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

Fecha de consulta de todas las fuentes: 22 de octubre de 2026. Las demás fuentes (REPS, DANE, BDUA, SECOP del hospital, normas técnicas) están citadas con numeral y página en los JSON de `data/proyectos/torre_hospital/`.
