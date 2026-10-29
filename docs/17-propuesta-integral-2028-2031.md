# Propuesta integral Yondó 2028–2031: presentación para gestionar recursos con el nivel central

Esta es una presentación aparte del atlas. El atlas cuenta qué pasó con la plata pública desde 2004 y qué proyectos
caben en 2028. Esta presentación va dirigida a quienes gestionan recursos en el nivel central: DNP, ministerios, OCAD,
Findeter, la Gobernación de Antioquia, los fondos nacionales y la cooperación. Junta siete áreas, cada una con varios
proyectos, en un solo paquete. Cada área tiene un sitio real en el municipio, un costo de referencia, el proyecto tipo
o referente que aplica, una mezcla de fuentes, su grado de madurez y un pedido concreto.

- **Página:** `web/propuesta.html`. En el sitio publicado es `propuesta.html`, y el atlas la enlaza desde su cabecera con
  «Propuesta 2028–2031 ↗». No comparte vistas, rutas ni estado con el atlas.
- **Datos:** los archivos de `data/propuesta/` se juntan en `web/data/propuesta.json` con `python3 scripts/build_data.py`, que llama a `scripts/build_propuesta.py`.
- **Corte:** 28 de octubre de 2026. Cifras en millones de pesos constantes de 2026.

## Cómo se recorre

La presentación tiene once capítulos: portada, las siete áreas, financiación, hoja de ruta y lo que se pide. Cada
capítulo se divide en pasos. En cada paso pasan tres cosas:

- el panel cambia con animaciones de GSAP (telón de capítulo, titulares palabra por palabra, cifras que cuentan y barras que crecen);
- la cámara vuela sobre la maqueta 3D del territorio real: casco urbano, río Magdalena, puente y vías;
- aparecen las capas 3D de ese paso.

La maqueta reutiliza el motor del atlas (`web/js/core.js`) y las réplicas de las sedes públicas, incluida la torre del
hospital de `docs/11`.

| Tecla o control | Acción |
|---|---|
| → / ← · Re Pág / Av Pág · espacio | Paso siguiente o anterior |
| 0–9 | Ir a un capítulo |
| I | Índice de capítulos |
| H | Ocultar el panel (solo 3D) |
| F | Pantalla completa |
| Fichas | Vista para imprimir o guardar en PDF, una ficha por módulo |

La dirección guarda el paso (`propuesta.html#urbanismo/4`), así se puede enviar un enlace directo a un punto de la
presentación.

## Las siete áreas

| Área | Inversión central | Rango | Madurez | Fuentes principales |
|---|---:|---:|---|---|
| Vivienda | 106.271 | 75.252 – 137.693 | Perfil | SGR 37.200, Nación 31.900, Gobernación 15.900 |
| Urbanismo | 26.200 | 17.250 – 39.600 | Perfil | SGR 8.200, Fondos 6.600, Nación 4.700 |
| Agroindustria | 77.000 | 60.000 – 106.000 | Perfil | SGR 27.400, Privados 13.000, OxI 12.000 |
| Salud | 48.679 | 34.635 – 65.640 | Prefactibilidad | SGR 18.337, Nación 17.200, OxI 3.750 |
| Aguas | 11.950 | 8.316 – 17.741 | Perfil | SGR 4.850, Municipio 2.643, Nación 2.500 |
| Aseo y saneamiento | 70.537 | 48.412 – 105.295 | Perfil | Nación 18.122, SGR 16.500, Gobernación 12.955 |
| Infraestructura TIC | 6.733 | 5.511 – 9.066 | Perfil | SGR 3.807, Fondos 1.726, Findeter 1.000 |
| **Total** | **347.370** | | | |

Cada módulo trae sus componentes con costo mínimo, central y máximo y la base del cálculo. También trae el proyecto
tipo del DNP o un referente con su enlace, los pasos de gestión, las metas, los riesgos y las fuentes citadas. Todo está
en `data/propuesta/modulos/<id>.json`.

## Dónde va cada cosa

Las ubicaciones salen de un levantamiento propio sobre OpenStreetMap, las huellas de edificaciones del repositorio y
la imagen satelital de referencia (Esri World Imagery de 2020 y de septiembre de 2025). La imagen se usó solo para
medir y no se publica. Están en `data/propuesta/geo.json`, en metros del modelo (x al oriente, y al norte).

- **Ciudadela deportiva (4,78 ha, sin manzanas de vivienda).** Une el estadio de sóftbol, el coliseo Benito Arias, el
  Parque Educativo, la biblioteca, la cancha de fútbol, el parque principal, el tramo del caño junto al estadio y el CIC.
  - *Cancha de Sóftbol Casabe.* Sigue el plano propuesto: home al sur, medidas reglamentarias, graderías con cubierta
    tensada, dugouts, baños, parqueadero de 20 cupos en la esquina suroccidental, cancha múltiple, zona infantil y
    biosaludable, marcador «CASABE», torres LED y portal con letrero. El lote de 109 × 110 m no cabe exacto en la
    manzana del estadio. Con 109 m de ancho caben 102,9 m de fondo dentro del cerramiento actual (rumbo 346,5°), y eso
    alcanza para la cerca de 76,2 m del jardín central. Para meter los 110 m habría que correr la malla hasta 3,5 m
    sobre los andenes.
  - *Parque lineal del Caño Colector Shell, fase 1.* Son ≈530 m, del bosque del sur a la Calle 55. Lleva sendero y
    ciclorruta por la orilla occidental, que es la que está libre de casas, una laguna de retención de 893 m² junto al
    CIC y el bosque inundable del sur. Los puentes PP1 (vía a Barrancabermeja), PP2 (prolongación de la Calle 51,
    estadio–CIC) y PP3 (Calle 54) cosen el estadio con el occidente. El corredor varía de ancho por tramos (de 12 a 40 m
    en la fase 1). En la fase 1 solo toca una casa (sobre la orilla, junto a la vía a Barrancabermeja) y roza el borde de
    otra edificación. El estrechamiento de la Calle 55 a la 57 (6 m, con casas en las dos orillas) queda para la fase 2,
    con desvío por la Carrera 57.
  - *Alameda de 483 m.* Va solo por calles existentes: Calle 50, Carrera 54, carriles del coliseo y Calle 49 peatonal.
    Las calles miden 6,5 m entre fachadas, así que es calle compartida a nivel (zona 30), sin ensanches ni demoliciones.
    Los árboles de la maqueta se ponen solo donde no hay construcciones.
  - *Canchas cubiertas y skatepark.* Van en la explanada al sur del CIC (≈75 × 54 m), a un puente del estadio. No hay
    lote libre para una pista atlética a menos de 400 m.
- **Mirador Puerta del Magdalena.** Está junto al estribo de Yondó del puente Guillermo Gaviria Correa, aguas abajo,
  sobre el embarcadero informal que ya existe.
  - *Zona A.* Protege 283 m de orilla en una franja de 36 m: los 30 m de ronda más el pie de enrocado. No lleva
    pavimento.
  - *Zona B.* Es una plaza de 0,46 ha detrás de la ronda, con las letras «YONDÓ» de cara a la plaza y el puente a la
    derecha.
  - Un deck curvo de 82 m lleva a un mirador de 10 × 10 m sobre pilotes, y hay un muelle flotante de 30 × 5 m donde hoy
    atracan las lanchas.
  - Lo que más pesa ante el nivel central es que la zona A se diseñe con la solución definitiva del estribo, que la ANI y
    la concesión Ruta del Cacao tienen pendiente tras el cierre de marzo de 2026.
- **Parque agroindustrial.** Ocupa un lote de 8,31 ha al suroriente de la vía del puente, de 200 a 700 m del estribo y a
  más de 300 m del río. Tiene tres zonas en fila (logística, limpia y sucia), dos accesos y el muelle de carga 140 m
  aguas arriba del puente.
  - El documento base ponía el parque sobre la orilla. Pero todo el entorno es el campo petrolero Casabe, con una
    plataforma de pozo cada ~200 m, y la orilla se socava.
  - Dentro del lote quedan dos pozos (Casabe 980 y 394) cuyo retiro debe confirmar Ecopetrol.
- **PTAR central (la primera del casco urbano).** Va al norte del casco, aguas abajo de la unión del Caño Colector Shell
  con el canal oriental, en un predio de ≈4,2 ha junto a la Carrera 57.
  - Queda a ≈700 m de la edificación mapeada más cercana (la norma pide 200 m) y a ≈60 m del caño, fuera de su ronda.
  - Las cuatro estaciones de bombeo dejan de verter: un interceptor occidental de 1.634 m (por la Carrera 57) y uno
    oriental de 2.113 m (por el canal oriental) siguen los caños hasta su unión, donde una estación de llegada sube el
    agua a la planta. El agua tratada pasa por una laguna de pulimento y vuelve al mismo caño, ≈120 m más abajo.
  - Se evaluaron otros tres sitios: A, la alternativa, en la reserva del EOT pegada al casco; B, hacia el río,
    descartado porque exigía bombear 911 m y un emisario de 825 m al Magdalena; y C, descartado por estar cerca de
    viviendas.
- **Relleno sanitario nuevo (vereda Kilómetro Cinco) y cierre de Las Américas.** La basura de Yondó se queda en Yondó.
  El relleno Las Américas opera con la licencia vencida desde el 12 de noviembre de 2023 y ya no tiene vida útil. Llevar
  la basura al relleno San Silvestre, en Barrancabermeja, a 40 km por vía, la haría depender de un solo puente, que la
  socavación cerró del 16 al 20 de marzo de 2026, de otra autoridad ambiental (la CAS) y de un operador privado, en un
  sitio cuya licencia la Corte Constitucional mandó revisar ([Sentencia T-227 de
  2017](https://www.corteconstitucional.gov.co/relatoria/2017/t-227-17.htm)). Por eso el relleno nuevo va en el polígono
  que el EOT ya reserva para él (Acuerdo 013 de 2022, art. 17.4 y Tabla 35). `docs/12` evaluó llevar la basura a San
  Silvestre; la propuesta deja esa opción por las razones de arriba.
  - *Por qué ese sitio.* Para cofinanciar un relleno, la Nación pide que el área esté delimitada en el EOT y que el
    estudio de factibilidad evalúe la regionalización (Decreto 1077 de 2015, arts. 2.3.2.3.7 y 2.3.2.3.9, modificados
    por el Decreto 1784 de 2017). Kilómetro Cinco es la única área que el EOT ya delimita para el relleno nuevo, y el
    mismo artículo la nombra área de contingencia. Cumple los descartes de la Res. 938 de 2019 (art. 1) que se pudieron
    revisar: queda a 4,2 km del suelo urbano y de expansión y a 2,0 km del centro poblado más cercano, fuera de la
    reserva forestal de Ley 2.ª y fuera del radio de 13 km y del cono de aproximación del aeropuerto. En el análisis
    multicriterio de esa norma, ampliar junto a Las Américas iría primero por ser un área ya impactada, pero no sirve
    (ver abajo); entre los demás sitios, Kilómetro Cinco es el único que está en el EOT, tiene vía de acceso y da 25
    años o más de vida útil, aunque es el más lejano (7,6 km por vía). Falta cruzarlo con la recarga de acuíferos, el
    bosque protector y el riesgo no mitigable del EOT.
  - *Sitio.* La reserva tiene ≈16 ha junto a la vía a Puerto Berrío, a 7,6 km por vía del parque principal. El predio
    útil es de 8,8 ha y su lindero va a 44 m o más del eje de la vía: el EOT pone esa vía en segundo orden (faja de 45
    m) y, en otro artículo, la Transversal de las Américas en primer orden (60 m), y pide 14 m de franja de aislamiento
    en los corredores viales suburbanos, así que se tomó la lectura más exigente. Queda a 4,2 km del perímetro urbano, a
    4,3 km de los pozos y la PTAP, a 3,6 km del Caño Colector Shell, a 6,4 km de la PTAR del casco y a 16,2 km del
    aeropuerto Yariguíes, fuera del radio de 13 km en el que la Aerocivil debe autorizar un relleno (RAC 14). Está fuera
    de la Reserva Forestal del Río Magdalena, en una zona sustraída, y a 11,2 km del área protegida más cercana del
    RUNAP; el DRMI Ciénaga de Barbacoas queda a 27,8 km. Son lomas de 83 a 113 m que drenan directo al Magdalena, sin
    cauces mapeados, ciénagas ni humedales a menos de 1,4 km.
  - *Adentro.* Cinco celdas en ≈3 ha dan ≈266.000–287.000 m³ con 12 a 15 m de altura. Desde la apertura, en 2030, Yondó
    dispondría ≈144.000–218.000 m³ en 25 años sin aprovechar nada: los 25 años que pide la norma (Res. 938 de 2019)
    caben con holgura, y los 30 (≈178.000–277.000 m³), en el escenario alto, solo con la ECA y el compostaje. La celda
    de la fase 1 (≈0,6 ha y hasta ≈36.000 m³ con taludes 3H:1V) dura de 5 a 7 años sin aprovechar. Hay dos lagunas de
    lixiviados de 28 × 24 m, portería con báscula, vía interna, cuatro pozos de monitoreo y una franja de árboles de 15
    m. La ECA de 10 t/día va sobre la vía interna, entre la portería y las celdas, y la planta de compostaje, al norte
    de la celda de la fase 1; comparten vía, báscula y cerramiento.
  - *Otros sitios evaluados.* El occidente cercano (alternativa) drena por el valle que pasa a 418 m de los pozos del
    acueducto y no está en el EOT. Las lomas de Casabe (alternativa) tienen siete pozos petroleros a menos de 500 m y
    tampoco están en el EOT. Ampliar junto a Las Américas (descartado) es lo que la norma prioriza por ser un área ya
    impactada, pero el lote vecino es vega inundable, tiene un pozo petrolero y dos edificaciones adentro y choca con la
    clausura y el parque.
  - *Secuencia.* Ya no se pueden abrir celdas transitorias ([Res. 1529 de
    2010](https://normas.cra.gov.co/gestor/docs/resolucion_minambientevdt_1529_2010.htm) y 1890 de 2011), así que Las
    Américas recibe basura, con un plan de cierre acordado con Corantioquia, solo hasta que abra el relleno nuevo y solo
    en el frente activo: desde 2028 se cubren sus celdas viejas, empezando por la norte. Cruce con las zonas de recarga
    antes de comprar, predio y estudios en 2027–2028, licencia de Corantioquia en 2028–2029, obra de la fase 1, la vía,
    la ECA y el compostaje en 2029 y operación desde 2030. Entonces se cierra el frente activo de Las Américas
    (2030–2031). La granja solar de 997 kWp de `docs/12` se monta cuando la cobertura haya asentado: ≈530 kWp en 2031
    sobre las celdas cubiertas desde 2028 y el resto hacia 2033–2034. Por eso va a la convocatoria del Incentivo a la
    Producción de 2029–2030: un proyecto del SGR debe abrir su contratación en 6 meses, prorrogables 12 (Ley 2056 de
    2020, art. 37). El parque va en 2031, fuera de las celdas, y la posclausura sigue hasta ≈2051.
  - *Costo y límites.* El relleno nuevo cuesta $9.820 M (entre $6.020 M y $18.270 M) sin la ECA ni el compostaje; la vía
    (≈2,7 km en afirmado por mejorar) es la partida más incierta. Operarlo cuesta ≈$806 M al año: si la inversión llega
    como aporte, son ≈$320 M al año más que llevar la basura a Barrancabermeja (≈$485 M más con el costo regional de
    `docs/12`, que supuso $60.000/t de disposición y 20 km de tramo excedente, frente a $95.000/t, el incentivo regional
    y 33 km más de transporte en la investigación de costos); con la inversión, el relleno propio cuesta 2,5 a 3 veces
    la opción regional. La tarifa (Res. CRA 1040 de 2026) recogería ≈$681 M al año, ≈$100–150 M menos que la operación,
    más el cobro de lixiviados, que falta calcular. La decisión se sostiene en no depender del puente ni de otra
    autoridad ambiental, no en el costo. El sitio sale de un análisis propio con OpenStreetMap, el modelo de elevación
    Copernicus GLO-30, ESA WorldCover, huellas de Microsoft, Google y OSM y los polígonos del EOT, convertidos desde
    MAGNA-SIRGAS Bogotá. Antes de comprar hay que cruzarlo con las zonas de recarga de acuíferos del EOT (art. 42.2,
    mapa FR_1_2): el predio está sobre la Formación Mesa y, si cae en una zona de alto potencial de recarga, no sirve.
    Faltan además topografía 1:1.000, apiques, hidrogeología, el estudio de creciente de 100 años (el borde sur queda a
    4–6 m sobre el río en el modelo de elevación), el aprovechamiento forestal de ≈1,4 ha de bosque en la zona de celdas
    (sin las dos celdas que son bosque, los 25 años dependen de aprovechar el 15–20 %) y las determinantes de
    Corantioquia, y confirmar en campo las tres casas a 165–178 m del lindero, la planta de tratamiento y disposición de
    lodos del EOT al occidente (con una nave a ≈90 m del lindero), unos estanques al otro lado de la vía y la captación
    del acueducto veredal.
- **Vivienda.** Son dos lotes reales:
  - *Lote 1, predio José Domingo Oliveros:* 1,71 ha con el terraplén ya construido (BPIN 2023058930018). Allí van 200 VIP
    en 10 bloques de 5 pisos.
  - *Lote 2, lote occidental:* 2,54 ha en una loma seca. Caben 128 casas en serie de 6 × 12 m; la primera etapa hace 100,
    y hay dos manzanas de cesión.
- **Granja solar centralizada.** Reemplaza el modelo de paneles en cada sede. Tiene 1,2 MWp (1,0 MW CA) en el bloque A
  de 1,70 ha, frente a la subestación Yondó de EPM, conectada con 40 m de línea de 13,2 kV; el bloque B (0,49 ha) queda
  de reserva. El tope de 1 MW CA de la autogeneración colectiva (Res. CREG 101 072 de 2025) limita la granja a ese
  tamaño. Con la granja de 997 kWp del relleno Las Américas (`docs/12`), el municipio tendría ~2,2 MWp centralizados.
- **Fibra y Zonas Digitales.** Un anillo de 4,6 km por calles y un ramal de ≈280 m a la EBAR La Victoria unen la
  alcaldía, donde va el centro de control (CCED), con las sedes, las EBAR y la PTAR. La primera fase tiene 5 Zonas
  Digitales y la segunda, 3.
- **Sectores del acueducto (indicativos).** Son seis grupos de edificaciones del casco, sacados de las huellas por
  k-medias, cada uno con su entrada medida. El diseño de la sectorización los define de verdad.

## Cómo se financia

| Fuente | Monto | % |
|---|---:|---:|
| Sistema General de Regalías | 116.294 | 33,5 % |
| Presupuesto General de la Nación | 79.922 | 23,0 % |
| Gobernación de Antioquia | 39.874 | 11,5 % |
| Privados y comunidad | 25.771 | 7,4 % |
| Obras por impuestos | 25.520 | 7,3 % |
| Recursos del municipio | 25.468 | 7,3 % |
| Fondos y agencias nacionales | 13.776 | 4,0 % |
| Findeter | 9.445 | 2,7 % |
| Corantioquia | 7.500 | 2,2 % |
| Cooperación y responsabilidad social | 3.800 | 1,1 % |

El contexto aprieta, por eso los proyectos grandes van al OCAD Paz, a la inversión regional y a las obras por impuestos.

- El presupuesto del SGR 2027–2028 baja 11 % ($27,54 billones) y en 2027 solo se podrá aprobar hasta el 60 % de los
  ingresos del bienio.
- A Yondó le quedan ≈ $7.297 M de asignaciones directas 2025–2026 sin aprobar al 27 de octubre de 2026 (cálculo propio
  con datos de MinHacienda). El Incentivo a la Producción del SGR solo se pide para las dos granjas solares, en
  convocatorias distintas: la municipal ($2.799 M) en la de 2027–2028 y la del relleno Las Américas ($1.747 M) en la de
  2029–2030, porque se monta en 2031 sobre las celdas cubiertas desde 2028. Así cada convocatoria lleva un proyecto,
  dentro del tope de 2 proyectos y $8.000 M por municipio. La torre del hospital no lo usa.
- El PGN 2027 recorta 3 % en todas las entidades.
- La reconstrucción tras el terremoto del 10 de agosto de 2026 es la prioridad nacional.
- El crédito de Findeter ($9.445 M) cabe en la capacidad prudente del municipio ($5.141 M a $10.281 M), cerca de su
  techo, y va sobre todo a proyectos que generan ahorro o ingreso: las dos granjas solares y el parque agroindustrial
  (para este, la línea está por confirmar), más $1.500 M con tasa compensada de salud para cerrar la obra de la torre.

El capítulo «Lo que pedimos» resume un pedido por entidad, con su monto y los módulos que mueve.

## Hoja de ruta

La gestión empieza ya, mientras se arma el PND 2026–2030 «Colombia, la Patria Milagro». Las compuertas son:

- bases al Consejo Nacional de Planeación el 15-nov-2026;
- plazo del presupuesto del SGR el 5-dic-2026;
- radicación del PND el 7-feb-2027 y aprobación a más tardar el 5-may-2027;
- elecciones locales el 31-oct-2027;
- nuevos planes de desarrollo municipal y departamental en 2028.

Las obras van en dos olas:

- **2028–2030:** acueducto, sóftbol y alameda, torre, fibra y granja, rescate de las viviendas inconclusas, banco de
  maquinaria y acopios del parque agroindustrial, la fase 1 del relleno nuevo con su vía y la cobertura de las celdas
  viejas de Las Américas.
- **2029–2031:** interceptores y PTAR, parque lineal, mirador, plantas del parque agroindustrial, urbanizaciones y el
  cierre de Las Américas con su parque y la primera parte de su granja solar.

## Ideas incorporadas de los renders del usuario

- **Mirador Puerta del Magdalena.** Se mantuvo lo esencial del render: zona A de protección hidráulica, zona B de plaza
  turística junto al puente, letras «YONDÓ» de colores, deck curvo con barandas hasta un mirador elevado sobre el agua,
  muelle flotante con la chalupa de toldo azul y lanchas, jardineras, árboles, bancas y luminarias. La plaza se corrió
  detrás de la ronda de 30 m (Decreto-Ley 2811 de 1974), así que el deck la cruza. También se agregaron el parqueadero
  y el acceso desde la vía del puente.
- **Cancha de Sóftbol Casabe.** El modelo 3D sigue el plano de medidas principales y el render del portal, el letrero,
  las torres LED, la gradería cubierta y los dugouts. Lo único que cambió es el fondo del lote: 102,9 m en vez de 110 m,
  para que quepa en la manzana real. Por eso la cancha múltiple quedó de 22 × 12 m fuera de la cerca del jardín
  izquierdo, y la zona infantil en territorio de foul.

Los renders no se incluyen como imágenes en la presentación porque no están en el repositorio. Si se suben, pueden
mostrarse junto al modelo 3D.

## Método, fuentes y límites

- Cada cifra del panel lleva su fuente, y las que no la tienen están marcadas como estimación o cálculo propio. Los
  costos son de perfil o prefactibilidad. El parque agroindustrial usa los $77.000 M del documento base; la
  investigación lo contrasta en ≈$82.000 M y el documento advierte variaciones de 30 % a 50 %.
- Los sitios y trazados son prediseños. Faltan topografía, estudio de títulos, acotamiento de rondas con Corantioquia,
  estudios hidráulicos y de socavación, conceptos de Ecopetrol sobre los pozos y de EPM sobre la conexión de la granja.
- La línea base del acueducto se contradice entre fuentes: 9 h según el diagnóstico técnico del estado actual, 18 h
  según el PDM 2024 y 7 a 8 h según la Superservicios en 2019. La presentación lo dice.
- La presentación funciona sin red para la QA (`scripts/qa/comun.mjs` con `--vendor`) y en el sitio publicado carga
  three.js y GSAP desde los CDN del atlas.

## Archivos

| Ruta | Qué es |
|---|---|
| `web/propuesta.html` | Página de la presentación (documento HTML completo; `build_site.py` la copia tal cual) |
| `web/js/propuesta/main.js` | Capítulos, pasos, panel con GSAP, navegación, índice y fichas para imprimir |
| `web/js/propuesta/escena.js` | Escena 3D compartida: terreno, río, puente, vías, sedes y encuadre según el panel |
| `web/js/propuesta/geo3d.js` | Geometría procedural (losas, cintas, árboles, naves, graderías, letras) y animaciones |
| `web/js/propuesta/piezas/` | Cancha de sóftbol, mirador, parque lineal, PTAR, ampliación de la PTAP, parque agroindustrial, granja solar y relleno sanitario nuevo (`relleno.js`) |
| `web/js/propuesta/modulos/` | Lo 3D de cada capítulo: capas, vistas y animaciones por paso |
| `data/propuesta/general.json` | Portada, catálogo de fuentes, hoja de ruta y pedidos |
| `data/propuesta/modulos/*.json` | Un archivo por módulo |
| `data/propuesta/geo.json` | Sitios y trazados de cada propuesta |
| `data/propuesta/territorio.json` | Río, vías y puente (de `scripts/geo/territorio_propuesta.py` con `data/geo/osm_corredor_puente.xml`) |
| `scripts/build_propuesta.py` | Junta y valida (sumas, fuentes, componentes) y escribe `web/data/propuesta.json` |
