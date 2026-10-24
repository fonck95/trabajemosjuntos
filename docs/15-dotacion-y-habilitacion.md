# 15 · Dotación para la habilitación de la torre, servicio por servicio

**Qué pide la norma de habilitación vigente en dotación e infraestructura para cada servicio de la torre de primer nivel de Yondó, qué equipo, mueble o instalación de la torre lo cubre, dónde queda en el recorrido 3D y qué falta. Con la clase de riesgo y el registro de cada equipo según el Decreto 4725 de 2005, y los implementos internos (carros de paro, equipos de parto, kits, reactivos) a la vista.**

> Estado: **esqueleto de la ola 1** de la especificación de integración (`data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md`, secciones 4, 11.4 y 16), con fecha de corte del 24 de octubre de 2026. El texto que no depende de las cifras finales ya está escrito; lo que se marca **«[CIFRA]»** se llena en la ola 2 con `exigencias_3100.json`, `inventario_dotacion.json`, `habilitacion.json` y el cierre de brechas de `dotacion.json`, y lo comprueba `scripts/torre/verificar_cifras_docs.py`.
>
> Cada cifra dice si es un **dato oficial** (copiado de la fuente), un **cálculo propio** (operación sobre datos citados, con el método a la vista) o una **estimación** (supuesto con rango, por confirmar). Pesos constantes de 2026 (IPC del DANE). **Los textos normativos vienen de compilaciones oficiales vistas a través del buscador o de guías secundarias: cotejar con el Diario Oficial antes de radicar o de la visita previa.** Ninguno se presenta como «verificado».

## En pocas palabras

- **Norma que rige:** la Res. 3100 de 2019 con sus modificaciones. La Res. 1732 de 2026, que iba a reemplazarla, fue **revocada** por la Res. 2080 del 8 de septiembre de 2026 antes de regir: se informa, no se aplica.
- **Alcance:** la matriz revisa **cumplimiento en dotación e infraestructura**. No revisa talento humano, historia clínica ni interdependencia: no dice si un servicio se puede habilitar.
- **Inventario:** [CIFRA: unidades físicas ubicadas] unidades en [CIFRA: recintos] recintos de los cuatro pisos, el bloque técnico, la cubierta y los exteriores, cada una con su exigencia, su nivel de verificación, su clase de riesgo y su registro.
- **Lo que falta:** el cierre de brechas suma [CIFRA: inversión con precio por proyecto P4, P5 y P6] más [CIFRA: ítems por cotizar] ítems por cotizar y [CIFRA: operación anual] de operación anual aparte. No toca el total de la dotación ($4.294 M de los 15 servicios; dato del repositorio, `dotacion.json`) ni el presupuesto de la torre.

## 1. Qué es habilitar y qué norma rige

**Habilitar** es inscribirse en el Registro Especial de Prestadores (REPS) y declarar, servicio por servicio, que se cumplen las condiciones mínimas de la norma. La Secretaría Seccional de Salud de Antioquia verifica en la visita previa antes de prestar un servicio nuevo. La Res. 3100 pide siete estándares en cada servicio: talento humano, infraestructura, dotación, medicamentos y dispositivos, procesos prioritarios, historia clínica y registros, e interdependencia.

| Norma | Estado al 24-oct-2026 | Cómo entra en este trabajo | Fuente (verificación) |
|---|---|---|---|
| **Res. 3100 de 2019** (manual de inscripción de prestadores y habilitación) con sus modificaciones: 2215 de 2020, 1317 de 2021, una de 2022 (**1138 o 1410; por confirmar** en el normograma de Supersalud), 544 de 2023, 465 de 2025 y 914 de 2025, entre otras | Vigente «sin solución de continuidad» (texto citado de la Res. 2080 de 2026) | Base de la matriz de cumplimiento | <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_3100_2019.htm> (compilación vista por buscador) |
| **Res. 1732 de 2026** (nuevo manual, Tomos I y II, 5-ago-2026) | **Revocada** en su integridad por la Res. 2080 de 2026; nunca se publicó en el Diario Oficial (oficio de la Imprenta Nacional 20261400007931 del 3-sep-2026, según las fuentes citadas) | Se informa; **no se usa como requisito**. Su Plan de Adecuación Progresiva quedó sin efecto: la torre debe cumplir completo desde la visita previa | <https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp?i=193984&dt=S> |
| **Res. 2080 de 2026** (8-sep-2026) | Vigente; su publicación en el Diario Oficial está por confirmar | Revoca la 1732 y deja la 3100 vigente | <https://www.minsalud.gov.co/Normatividad_Nuevo/Resoluci%C3%B3n%20No%202080%20de%202026.pdf> (art. 1, texto de compilación) |
| **Decreto 4725 de 2005** (registro sanitario, permiso de comercialización y vigilancia de dispositivos médicos), modificado por los Decretos 4562 de 2006, 3275 de 2009 y 582 de 2017 | Vigente; hay un proyecto de reemplazo sin expedir | Clase de riesgo (arts. 5 a 7, 18 reglas), registro INVIMA, prohibición de usados IIb y III (art. 37, sustituido por el Decreto 582 de 2017; 36 o 37 por confirmar), mantenimiento por personal inscrito (art. 39), posventa (art. 38) y tecnovigilancia (art. 61) | <https://normograma.invima.gov.co/normograma/compilacion/docs/decreto_4725_2005.htm> |
| **Res. 4816 de 2008** (tecnovigilancia) | Vigente | Programa institucional y reporte de eventos serios en 72 horas (artículo por confirmar) | <https://normograma.invima.gov.co/compilacion/docs/resolucion_minproteccion_4816_2008.htm> |
| **Decreto 3770 de 2004** (reactivos de diagnóstico *in vitro*), modificado por el Decreto 581 de 2017 | Vigente | Registro de reactivos y analizadores del laboratorio en comodato; reactivovigilancia | <https://www.invima.gov.co/node/71> (artículos por confirmar) |
| **Res. 914 de 2025** (manual de reprocesamiento de dispositivos médicos, DMER) | Rige desde el 3-ene-2027 (art. 15); su art. 14 deroga los numerales de esterilización de la 3100 | La matriz se calcula en dos cortes: al 23-oct-2026 con la 3100 y a la apertura (hacia abril de 2030) con la 914, **por confirmar** hasta leer el manual | <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_0914_2025.htm> |
| **Res. 1811 de 2025** (radiaciones ionizantes) | Rige desde el 6-mar-2026 según MinSalud; reemplazó a la Res. 482 de 2018 | Licencia de rayos X y periapical, dosimetría personal y control de calidad (exigencias documentales y de operación) | <https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/DIJ/resolucion-1811-de-2025.pdf> (artículos por confirmar) |
| **Res. 2065 de 2025** (sedes transitorias en emergencias) | Vigente; un proyecto de octubre de 2026 la llevaría al manual de la 3100 | Marco de la sala de expansión, que no es un servicio de la 3100 | <https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp?dt=S&i=191017> |
| **Res. 1633 de 2025** (marco técnico de infraestructura) | Vigente | Áreas mínimas, módulo de 1,20 m, puertas, corredores y señalización por colores de la planta | <https://www.minsalud.gov.co/Normatividad_Nuevo/Resolucion%20No%201633%20de%202025.pdf> |

## 2. Alcance: qué revisa la matriz y qué no

**Esta matriz revisa la dotación y la infraestructura. No revisa talento humano, historia clínica ni interdependencia (por ejemplo, urgencias depende de imágenes, laboratorio y transporte asistencial): no dice si un servicio se puede habilitar.**

Por eso su estado se llama **«cumplimiento en dotación e infraestructura»**. Los estándares evaluados son dotación, infraestructura, medicamentos y dispositivos (en parte) y procesos prioritarios (en parte). Las investigaciones de base no traen filas de talento humano ni de interdependencia, y de historia clínica solo dos de TIC.

La planta en la que se ubica todo es un **anteproyecto ilustrativo** (estimación): respeta la retícula, los núcleos, la zonificación y las áreas del programa, pero el diseño real lo hace el arquitecto con matrícula.

## 3. Método: de la exigencia al lugar

```
exigencia de la norma → ítem de la dotación que la cubre → unidad física → recinto y posición en el recorrido 3D
```

1. **Exigencias.** Las tres investigaciones de la Res. 3100 (urgencias e internación; consulta y ambulatorio; apoyo diagnóstico) se normalizan en una sola lista sin perder filas: **199 filas de origen** (86 + 52 + 7 + 43 + 11; las 18 de «todos los servicios» son 7 de consulta y 11 de apoyo; dato de las investigaciones, conteo propio). Cada una con su servicio, su numeral, su texto (o «resumen; texto oficial no obtenido», nunca entre comillas), los ambientes del programa a los que aplica y una regla de cálculo (por recinto, por cama o camilla, por servicio, por piso, contenido de un carro, existencia de un ambiente, área libre por cama o documental).
2. **Niveles de verificación de los textos** (ninguno se presenta como «verificado»):

| Nivel | Qué quiere decir | Exigible |
|---|---|---|
| Texto de una compilación oficial | Frase vista en una compilación oficial (Cancillería, ICBF, INVIMA) a través del buscador | Sí |
| Contenido de una compilación oficial | Contenido confirmado; redacción o subnumeral por confirmar | Sí |
| Según guía secundaria | Guía o transcripción: no es texto normativo | Por confirmar |
| Paráfrasis | Sin texto | Por confirmar |

3. **Exigible frente a por confirmar.** De las 199 filas, **63 son de guía secundaria o paráfrasis** (43 del archivo de urgencias, 12 del de consulta y 8 del de apoyo; conteo propio): 61 lo son según las investigaciones y 2 más (EX-PAR-016 y EX-IMG-008) se marcaron como vistas en una compilación oficial pero solo citan un sitio privado de consultoría, y el normalizador las baja a guía secundaria. Quedan **por confirmar** y no cambian el color de un recinto; se cuentan aparte. [CIFRA: filas con texto disponible, numerales confirmados y porcentaje de las de dotación con regla automática].
4. **Unidades.** Cada línea de `dotacion.json` y de `laboratorio.json` se convierte en unidades físicas (una por objeto), ubicadas por reglas en su recinto; las de los kits y del laringoscopio neonatal llevan sus componentes. Nada se ubica a mano, salvo piezas compuestas justificadas (rayos X, unidad odontológica, autoclave de doble puerta).
5. **Estados:** cumple, parcial, falta, documento pendiente o no aplica, en dos escenarios (dotación actual y con el cierre de brechas) y dos cortes (23-oct-2026 y apertura hacia el 1-abr-2030, estimación tomada de `docs/11`).

### 3.1 Lo que se recorre y se inspecciona (alcance ampliado del 23-oct-2026)

- Se camina por **toda la torre**: exteriores inmediatos (plaza bajo el mango, patio y retorno de urgencias, bahía de ambulancias, galería al hospital actual), los cuatro pisos con todos sus recintos, las escaleras y los ascensores, el **bloque técnico** (subestación, planta, tableros y baterías del nodo hospital, central de gases, bombas, depósito de cadáveres y residuos) y la **cubierta técnica** (paneles solares, condensadoras, tanques, casetas).
- **Todo objeto visible tiene ficha:** nombre, servicio, recinto, cantidad, especificación, clase de riesgo y registro (Decreto 4725), exigencia (Res. 3100, numeral y nivel de verificación) o «recomendado», estado, precio y tipo de precio, mantenimiento, anclaje sísmico y contenido desplegable.
- **Capa de infraestructura** (aparte de la dotación, sin precio de dotación): lavamanos, unidades sanitarias, duchas, pocetas, lavachatas, tomas de gases medicinales por cama y camilla, tomas de la red de emergencia, llamado de enfermería, extintores y gabinetes, señalización de evacuación y cortinas antifluido. Sirve de evidencia de las exigencias de infraestructura; si el presupuesto de obra la paga, se cita su ítem.
- **Inventario navegable:** buscador y lista filtrable por piso o nivel, servicio, recinto, capa, clase de riesgo y estado, con el total de unidades y de valor de lo filtrado y un botón «Ir a» que lleva al caminante frente a la unidad.

### 3.2 La planta y sus avisos

Áreas a ejes (sobre el eje de los muros) y libres (entre caras de muro): el validador exige que el área a ejes no baje del programa ni del mínimo de la Res. 1633, y **avisa** cuando el área libre queda bajo el mínimo, con la nota «por confirmar si el mínimo de la Res. 1633 se mide libre o a ejes». Los pisos 1 (holgura de 2,5 m²) y 2 (5,4 m²) no tienen espacio para agrandar todos los ambientes que están exactos en el mínimo (reanimación 20 m², ERA 9, EDA 12, yesos 9, aislamiento 16, observación 12; dato del programa). Avisos del validador: [CIFRA: lista de avisos de área libre por recinto].

## 4. Matriz por servicio

Conteos de exigencias **exigibles** (cumple / parcial / falta / documento pendiente) y, aparte, **por confirmar**; en los dos escenarios y los dos cortes. Códigos REPS y numerales tomados del programa y de las investigaciones (por confirmar en el REPS y en el texto oficial). Fuente: `habilitacion.json` (cálculo propio).

| Servicio | Código REPS y numeral (por confirmar) | Complejidad | Corte 23-oct-2026, dotación actual | Corte 23-oct-2026, con el cierre de brechas | Apertura (hacia abril de 2030), dotación actual | Por confirmar (no cambian el estado) |
|---|---|---|---|---|---|---|
| Servicio de urgencias | 1102 · num. 11.6.1 | baja | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Hospitalización (adultos y pediátrica) | 129 y 130 · num. 11.4.1 | baja | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Atención del parto | 1101 · num. 11.6.4 | baja | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Consulta externa general | 328, 312 y 344 · num. 11.2.1 | baja | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Odontología general | 334 · num. 11.2.1 | baja | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Vacunación | 420 · num. 11.2.3 | baja | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Servicio farmacéutico | 714 · num. 11.3.2 | baja | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Terapias (fisioterapia y terapia respiratoria) | 739 y 729 · num. 11.3.1 | por confirmar | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Laboratorio clínico | 706 · num. 11.3.12 | por confirmar | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Imágenes diagnósticas ionizantes (rayos X) | 744 · num. 11.3.4.1 | baja | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Imágenes diagnósticas no ionizantes (ecografía) | 745 · num. 11.3.4.2 | mediana | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Radiología odontológica (periapical) | 748 · num. 11.3.3 | por confirmar | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |

Cada celda: exigencias exigibles «cumple / parcial / falta / documento pendiente» (cálculo propio sobre la matriz).

**Servicios que no se habilitan como tales** (se muestran con su marco, sin estado de servicio; sus exigencias propias sí se evalúan):

- **Sala de expansión:** no es un servicio de la Res. 3100; se activa en emergencias con la Res. 2065 de 2025. Sus exigencias de dotación son por analogía con el num. 11.6.1 (urgencias) y van como referencia.
- **Esterilización:** proceso de la Res. 3100 (num. 11.1) hasta el 2-ene-2027; desde el 3-ene-2027, Res. 914 de 2025. A la apertura sus exigencias quedan **por confirmar** hasta leer el manual DMER.
- **Telemedicina:** modalidad de prestación, sin código de servicio propio.
- **TIC y apoyo:** soporte de los demás servicios.
- **Toma de muestras de laboratorio:** no requiere habilitación propia si el laboratorio de la misma sede toma las muestras (Res. 3100, num. 11.3.12, texto de compilación).
- **Ecografía:** la compilación (num. 11.3.4) la admite solo en **mediana complejidad**, aunque la E.S.E. sea de primer nivel (por confirmar en el texto oficial).

Las 18 exigencias de «todos los servicios» se muestran una sola vez y no suman en los resúmenes de cada servicio.

## 5. Cierre de brechas

Lo que falta para cumplir (o lo que se recomienda) va en una sección aparte de `dotacion.json`, **sin tocar sus totales generales** (así no cambian el presupuesto, la financiación ni el total de la torre de $37.137 M; dato del repositorio).

- **Reglas:** prioridad «habilitación» solo si alguna exigencia enlazada es exigible; «por confirmar» si todas son de guía secundaria o paráfrasis; «recomendado» en la sala de expansión, el DEA del piso 4 y lo que viene del proyecto tipo. Precio: el del mismo ítem en `dotacion.json` cuando existe; si no, la estimación con rango de la investigación; si no hay ninguno, **por cotizar** (sin precio y sin sumar cifras supuestas). Cada ítem dice su proyecto (P4, P5 o P6 del presupuesto) y si es inversión u operación anual.
- **Totales por proyecto** (cálculo propio): [CIFRA: P4, P5 y P6 en habilitación, recomendado y por confirmar; ítems sin precio; rango].
- **Operación anual** (dosimetría personal y control de calidad de rayos X después del primer año): [CIFRA]; no se suma a la inversión.
- **Cómo se financia:** cada ítem indica su proyecto. Mientras no se actualice el presupuesto, la inversión podría salir de la contingencia de su proyecto, **que es la reserva para riesgo de cantidades y precios: usarla reduce esa reserva**. La operación anual no se financia con contingencias.
- **Referencia de la investigación de consulta:** sus faltantes de seis servicios se estimaban en $12,2 a $22,6 M, pero ese rango incluía un DEA para el piso 4 que no es exigencia confirmada: sin él, **$4,2 a $10,6 M** (cálculo propio); el DEA va aparte como recomendado.
- **Lista completa:** [CIFRA: tabla con servicio, ítem, cantidad, precio o «por cotizar», tipo de precio, fuente, proyecto y naturaleza].
- **Lavadora desinfectora** ($110 M, hoy «recomendado» en `dotacion.json`; dato del repositorio): la investigación sugiere pasarla a habilitación por la Res. 914 de 2025. **Decisión de esta versión:** no se cambia su prioridad; en el inventario queda «por confirmar (Res. 914)» y se retoma al leer el manual DMER. La secadora o gabinete de secado, la lupa con iluminación y la etiquetadora o el software de trazabilidad también dependen de la Res. 914, que rige antes de la apertura.
- **GeneXpert:** si no lo entrega el programa nacional de tuberculosis y hay que comprarlo, es un costo no presupuestado de **$144,0 M** ($143.967.621; dato del repositorio, `laboratorio.json`).

## 6. Clases de riesgo revisadas (Decreto 4725)

- Clases I (riesgo bajo), IIa (moderado), IIb (alto) y III (muy alto). La torre no tiene equipos de clase III; los IIb (desfibriladores, monitores, bombas, ventilador, incubadoras, rayos X…) no se pueden comprar ni recibir usados y su mantenimiento lo hace personal inscrito en el INVIMA. La clase que vale es la del registro sanitario del modelo comprado.
- **Cambios en `dotacion.json`** (solo discrepancias firmes apoyadas en reglas leídas): tensiómetro aneroide de pared IIa → I (regla 1; 3 servicios), báscula pesa bebés de urgencias IIa → I (regla 12) y lavadora desinfectora IIb → IIa (regla 15). [CIFRA: confirmar que quedaron aplicados].
- **Sin cambio y por confirmar:** el refrigerador de vacunas («I por regla 2 si se considera dispositivo médico; probablemente no lo es») y la incubadora de indicadores biológicos («I por regla 12 o IIa por regla 15»).
- **No son dispositivo médico** (por confirmar: definición del art. 2 del Decreto 4725 no leída en el texto oficial): UPS, termohigrómetros, estabilizador, balanza y horno, nevera mortuoria, autoclave de residuos, puesto de trabajo y registradores de temperatura y termómetros de vacunación. Los analizadores del laboratorio son de diagnóstico *in vitro* (Decreto 3770 de 2004) y algunos equipos industriales de uso hospitalario no llevan clase INVIMA.
- **Laringoscopio neonatal y resucitador neonatal con mezclador:** la línea no se parte (cambiaría el número de líneas); se inventarían sus dos componentes (laringoscopio clase I y resucitador clase IIa).
- [CIFRA: cuántas líneas quedaron coherentes, cuántas con discrepancia firme, cuántas probables, de otro régimen y por confirmar].

## 7. Campos del inventario y obligaciones del prestador

Cada unidad trae los campos que piden la Res. 3100 (num. 11.1.3 y 11.1.4) y el Decreto 4725: servicio y ambiente, nombre genérico, marca, modelo, serie, registro sanitario o permiso de comercialización y su vencimiento, clase de riesgo, tecnología controlada, fechas de instalación y de compra, hoja de vida, responsable del mantenimiento (inscrito en el INVIMA si es IIb o III) y referente de tecnovigilancia. Marca, modelo y serie se llenan al comprar.

Obligaciones del prestador (Decreto 4725 y Res. 4816 de 2008; artículos por confirmar donde se dice):

- Comprar solo con registro sanitario o permiso de comercialización vigente del INVIMA (arts. 17, 18 y 22), y pedir copia en cada pliego.
- No comprar ni recibir en donación equipos usados de clase IIb o III (art. 37 sustituido por el Decreto 582 de 2017; 36 o 37 por confirmar).
- Mantenimiento preventivo según el fabricante, con hoja de vida; el de IIb y III, por personal con responsable técnico inscrito en el INVIMA (art. 39; Res. 3100, num. 11.1.3).
- Manuales de operación y mantenimiento en castellano y soporte posventa (art. 38).
- Programa institucional de tecnovigilancia y reporte al INVIMA de los eventos serios **en las 72 horas** siguientes y de los no serios cada trimestre (Res. 4816 de 2008; el artículo del plazo, por confirmar).
- Reactivos del laboratorio con registro sanitario (Decreto 3770 de 2004) y programa de reactivovigilancia: el contrato de comodato debe exigirlos.

## 8. Implementos internos

Los carros de paro (adulto-pediátrico y neonatal), los equipos de parto, los kits (examen básico, hemorragia obstétrica, inmovilización, rehabilitación), el instrumental de odontología y los implementos del laboratorio (reactivos, calibradores, controles y consumibles por analizador; medios de microbiología; material de vidrio y de toma; elementos de bioseguridad) se listan dentro de su contenedor, con compartimiento y cantidad (`implementos.json`).

- **No suman precio:** el precio de un carro o de un kit en `dotacion.json` ya incluye su contenido, y los reactivos del laboratorio van en el comodato pagado con reactivos. Sumarlos aparte contaría dos veces.
- **Sí se inventarían uno por uno los equipos biomédicos que van dentro** (por ejemplo, el desfibrilador del carro de paro o el tensiómetro del kit), porque cada uno tiene su registro, su clase de riesgo y su mantenimiento.
- Cuando `laboratorio.json` no detalla un insumo, se nombra genérico y se marca **estimación**.
- [CIFRA: número de plantillas de implementos y de componentes inventariados].

## 9. Equipos del laboratorio

`laboratorio.json` trae 11 líneas y 12 unidades por $1.249.676.210 (dato del repositorio):

- **10 en comodato** (9 líneas): hematología de 5 partes y de 3 partes, química clínica, inmunoensayo, hemoglobina glicosilada, uroanálisis, coagulación, gases y electrolitos (2 lectores) y hemocultivos: **$955.708.589** de valor de mercado (dato del repositorio). El hospital no los compra: los paga con los reactivos.
- **1 por programa o compra:** GeneXpert de 4 módulos ($143.967.621), si no lo entrega el programa nacional de tuberculosis; **no está presupuestado**.
- **1 opcional:** identificación y antibiograma semiautomatizado ($150.000.000), en comodato cuando haya más de 150 aislamientos al mes.
- Lo demás del laboratorio (microscopios, cabina de bioseguridad, centrífugas, incubadoras, neveras, autoclave, mesones) está en la dotación del servicio y se compra.
- En el recorrido, el laboratorio del piso 2 se dibuja completo, recinto por recinto, con todo lo anterior marcado según cómo se adquiere, y sus reactivos en neveras y estantes.

## 10. Reclasificaciones que propone la investigación

La revisión de urgencias e internación propone pasar a **«recomendado»** (no exigido por la Res. 3100) la incubadora neonatal estacionaria y la lámpara de fototerapia de partos, y los sillones reclinables para acompañante de hospitalización y de las habitaciones TPR; y la de consulta y ambulatorio anota que el equipo de **otoemisiones acústicas** lo pide la Res. 3280 de 2018 (tamizaje auditivo neonatal), no la 3100. En esta versión **no se cambia la prioridad** de esas líneas en `dotacion.json` (4.7.4 de la especificación).

- Valor de los ítems de habilitación hoy: **$3.908.496.956** (dato del repositorio, `dotacion.json`).
- Sin las reclasificaciones propuestas: [CIFRA] (cálculo propio).

## 11. Dotación frente al proyecto tipo

El proyecto tipo del DNP con MinSalud (2018) solo trae la dotación de la consulta ambulatoria de un puesto de un piso. Frente a él (detalle en la tarjeta «Contraste con el proyecto tipo» y en `docs/11`):

- La dotación de la torre vale **21,7 veces** la del tipo ($4.294 M frente a $198,1 M de 2026) y **2,1 veces por m²** (base: 3.369,6 m² construidos de la torre y 320,6 m² construidos del tipo; cálculo propio de la investigación del 23-oct-2026).
- Ítem por ítem, en los consultorios faltan el martillo de reflejos, la linterna de valoración pupilar y el fonendoscopio pediátrico, y el infantómetro es compartido; en las salas de espera, el bebedero y el punto ecológico; en la toma de muestras, las canecas y los guardianes; en los residuos, la báscula. Están en el cierre de brechas (recomendados o por cotizar).
- Posible duplicado: el kit de examen trae tensiómetro y equipo de órganos portátiles y cada consultorio tiene además los de pared: **$67,5 M** si se deja una sola versión (cálculo propio de la investigación). Decisión pendiente de la E.S.E. (sección 12).
- [CIFRA: costo por consultorio, por unidad odontológica y por puesto de toma de la torre frente al tipo, con los precios de la dotación].

## 12. Decisiones pendientes

**Con la Secretaría Seccional de Salud de Antioquia:**

- Si la cama de trabajo de parto, parto y recuperación (TPR) cuenta como «mesa de partos».
- Si un desfibrilador compartido en el piso 3 basta para hospitalización y partos.
- El registro de las camas de posparto (hospitalización o partos).
- Que la toma de muestras no requiere habilitación propia con el laboratorio en la misma sede.
- Que la ecografía se habilita en mediana complejidad.

**De la E.S.E.:**

- El posible duplicado del kit de examen ($67,5 M): dejar una sola versión por consultorio o justificar los portátiles para la atención extramural.
- La lavadora desinfectora: pasarla a habilitación al leer el manual DMER de la Res. 914.
- El GeneXpert: confirmar si lo entrega el programa nacional de tuberculosis ($144,0 M si se compra).

## 13. Lo que falta verificar

- Texto oficial (normograma de Supersalud o Diario Oficial) de las 199 exigencias; subnumerales que difieren entre copias (12.1 frente a 9.2; 17.1.2.x frente a 17.2.1.x; criterio 8 frente a 11 del carro de paro); listas literales de infraestructura de urgencias y partos; numerales 26 y 27 de esterilización.
- Códigos REPS (1102, 1101, 129, 130, 328, 312, 344, 333, 334, 748, 420, 714, 739, 729, 706, 712, 744, 745), tomados del programa.
- Contenido mínimo del carro de paro (si exige desfibrilador con marcapasos en baja complejidad: el «marcapasos externo» del num. 11.6.1 solo lo agrega una guía secundaria; por confirmar); kit de anafilaxia en vacunación; DEA o carro de paro en el piso 4; criterios 18.14 y 18.15 de infraestructura de urgencias (por confirmar); área libre mínima por cama en hospitalización (7 m² y 6 m² en pediatría, según guía secundaria); las 63 exigencias de guía secundaria o paráfrasis.
- Decreto 4725: reglas 3, 4, 5, 8 y 14; definición del art. 2; artículo de los usados (37 o 36); lista de tecnología controlada; concepto del INVIMA sobre la central de gases, el generador PSA, el PACS y los refrigeradores; artículo de la Res. 4816 con las 72 horas.
- Publicación de la Res. 2080 de 2026 en el Diario Oficial; si los proyectos de julio (DMER) y de octubre (emergencias) de 2026 se expidieron; probable manual nuevo antes de la apertura (hacia abril de 2030): repetir el cruce cuando salga.
- La modificación de 2022 de la Res. 3100: 1138 (investigación de urgencias) o 1410 (normas del repositorio).
- Res. 914 de 2025: requisitos del manual DMER para la central de esterilización al abrir la torre.
- Res. 1633: si el mínimo de área es libre o a ejes; procesamiento de rayos X (Cuadro 22) y control y procesamiento de ecografía (Cuadros 26-27) en baja complejidad con equipos digitales.
- [CIFRA: pendientes que dejen la matriz y el inventario de la ola 2].

## 14. Fuentes

- Res. 3100 de 2019, MinSalud (compilada): <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_3100_2019.htm>
- Res. 2080 de 2026, MinSalud: <https://www.minsalud.gov.co/Normatividad_Nuevo/Resoluci%C3%B3n%20No%202080%20de%202026.pdf>; régimen legal de Bogotá: <https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp?dt=S&i=194230>
- Res. 1732 de 2026 (revocada), régimen legal de Bogotá: <https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp?i=193984&dt=S>
- Decreto 4725 de 2005 (compilación del INVIMA): <https://normograma.invima.gov.co/normograma/compilacion/docs/decreto_4725_2005.htm>
- Decreto 582 de 2017: <https://dapre.presidencia.gov.co/normativa/normativa/DECRETO%20582%20DEL%2004%20DE%20ABRIL%20DE%202017.pdf>
- Decreto 3275 de 2009: <https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=37226>
- Res. 4816 de 2008: <https://normograma.invima.gov.co/compilacion/docs/resolucion_minproteccion_4816_2008.htm>
- Decreto 3770 de 2004 (INVIMA): <https://www.invima.gov.co/node/71>
- Res. 914 de 2025: <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_0914_2025.htm>
- Res. 1811 de 2025: <https://www.minsalud.gov.co/sites/rid/Lists/BibliotecaDigital/RIDE/DE/DIJ/resolucion-1811-de-2025.pdf>
- Res. 2065 de 2025: <https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp?dt=S&i=191017>
- Res. 1633 de 2025 y sus anexos: <https://www.minsalud.gov.co/Normatividad_Nuevo/Resolucion%20No%201633%20de%202025.pdf>
- Res. 591 de 2024 (residuos): <https://normograma.supersalud.gov.co/compilacion/docs/resolucion_minsaludps_0591_2024.htm>
- Proyecto tipo DNP de infraestructura básica en salud (2018): <https://proyectostipo.dnp.gov.co/images/pdf/salud/PTsalud.pdf>
- Datos del atlas: `data/proyectos/torre_hospital/` (`dotacion.json`, `laboratorio.json`, `normas.json`, `exigencias_3100.json`, `inventario_dotacion.json`, `habilitacion.json`, `implementos.json`, `proyecto_tipo_contraste.json`) y las investigaciones de base en `data/proyectos/torre_hospital/fuentes_investigacion/`.
