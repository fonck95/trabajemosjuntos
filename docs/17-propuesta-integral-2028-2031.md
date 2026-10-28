# Propuesta integral Yondó 2028–2031: presentación para gestionar recursos con el nivel central

Esta es una presentación aparte del atlas. El atlas cuenta qué pasó con la plata pública desde 2004 y qué proyectos
caben en 2028. Esta presentación va dirigida a quienes gestionan recursos en el nivel central: DNP, ministerios, OCAD,
Findeter, la Gobernación de Antioquia, los fondos nacionales y la cooperación. Junta siete propuestas en un solo
paquete. Cada una tiene un sitio real en el municipio, un costo de referencia, el proyecto tipo o referente que aplica,
una mezcla de fuentes, su grado de madurez y un pedido concreto.

- **Página:** `web/propuesta.html`. En el sitio publicado es `propuesta.html`, y el atlas la enlaza desde su cabecera con
  «Propuesta 2028–2031 ↗». No comparte vistas, rutas ni estado con el atlas.
- **Datos:** los archivos de `data/propuesta/` se juntan en `web/data/propuesta.json` con `python3 scripts/build_data.py`, que llama a `scripts/build_propuesta.py`.
- **Corte:** 28 de octubre de 2026. Cifras en millones de pesos constantes de 2026.

## Cómo se recorre

La presentación tiene once capítulos: portada, los siete módulos, financiación, hoja de ruta y lo que se pide. Cada
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

## Las siete propuestas

| Módulo | Inversión central | Rango | Madurez | Fuentes principales |
|---|---:|---:|---|---|
| Vivienda | 106.271 | 75.252 – 137.693 | Perfil | SGR 37.200, Nación 31.900, Gobernación 15.900 |
| Urbanismo | 26.200 | 17.250 – 39.600 | Perfil | SGR 8.200, Fondos 6.600, Nación 4.700 |
| Agroindustria | 77.000 | 60.000 – 106.000 | Perfil | SGR 27.400, Privados 13.000, OxI 12.000 |
| Salud | 48.679 | 34.635 – 65.640 | Prefactibilidad | SGR 18.337, Nación 17.200, OxI 3.750 |
| Aguas | 11.950 | 8.316 – 17.741 | Perfil | SGR 4.850, Municipio 2.643, Nación 2.500 |
| Aseo y saneamiento | 60.717 | 42.392 – 87.025 | Perfil | Nación 16.372, SGR 14.600, Gobernación 10.800 |
| Infraestructura TIC | 6.733 | 5.511 – 9.066 | Perfil | SGR 3.807, Fondos 1.726, Findeter 1.000 |
| **Total** | **337.550** | | | |

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
- **PTAR central (la primera del municipio).** Va en el sitio B, un potrero de 6,8 ha al nororiente del casco.
  - Queda aguas abajo, a 476 m de la edificación mapeada más cercana y a 0,8 km del Magdalena.
  - Las cuatro estaciones de bombeo dejan de verter: un interceptor occidental de 1.703 m y uno oriental de 1.334 m
    llegan a una estación central, que bombea a la PTAR por una impulsión de 911 m. Un emisario de 825 m lleva el agua
    tratada al río.
  - Se evaluaron otros dos sitios: A, la alternativa, y C, descartado por estar cerca de viviendas. B se prefiere a la
    reserva del EOT, que queda pegada al borde norte del casco, junto a la unión de los caños.
- **Vivienda.** Son dos lotes reales:
  - *Lote 1, predio José Domingo Oliveros:* 1,71 ha con el terraplén ya construido (BPIN 2023058930018). Allí van 200 VIP
    en 10 bloques de 5 pisos.
  - *Lote 2, lote occidental:* 2,54 ha en una loma seca. Caben 128 casas en serie de 6 × 12 m; la primera etapa hace 100,
    y hay dos manzanas de cesión.
- **Granja solar centralizada.** Reemplaza el modelo de paneles en cada sede. Tiene 1,2 MWp (1,0 MW CA) en el bloque A
  de 1,70 ha, frente a la subestación Yondó de EPM, conectada con 40 m de línea de 13,2 kV; el bloque B (0,49 ha) queda
  de reserva. El tope de 1 MW CA de la autogeneración colectiva (Res. CREG 101 072 de 2025) limita la granja a ese
  tamaño. Con la granja de 997 kWp del relleno (`docs/12`), el municipio tendría ~2,2 MWp centralizados.
- **Fibra y Zonas Digitales.** Un anillo de 4,6 km por calles y un ramal de 718 m a la EBAR La Victoria unen la
  alcaldía, donde va el centro de control (CCED), con las sedes, las EBAR y la PTAR. La primera fase tiene 5 Zonas
  Digitales y la segunda, 3.
- **Sectores del acueducto (indicativos).** Son seis grupos de edificaciones del casco, sacados de las huellas por
  k-medias, cada uno con su entrada medida. El diseño de la sectorización los define de verdad.

## Cómo se financia

| Fuente | Monto | % |
|---|---:|---:|
| Sistema General de Regalías | 114.394 | 33,9 % |
| Presupuesto General de la Nación | 78.172 | 23,2 % |
| Gobernación de Antioquia | 37.719 | 11,2 % |
| Privados y comunidad | 25.771 | 7,6 % |
| Recursos del municipio | 24.223 | 7,2 % |
| Obras por impuestos | 23.750 | 7,0 % |
| Fondos y agencias nacionales | 13.776 | 4,1 % |
| Findeter | 9.445 | 2,8 % |
| Corantioquia | 6.500 | 1,9 % |
| Cooperación y responsabilidad social | 3.800 | 1,1 % |

El contexto aprieta, por eso los proyectos grandes van al OCAD Paz, a la inversión regional y a las obras por impuestos.

- El presupuesto del SGR 2027–2028 baja 11 % ($27,54 billones) y en 2027 solo se podrá aprobar hasta el 60 % de los
  ingresos del bienio.
- El PGN 2027 recorta 3 % en todas las entidades.
- La reconstrucción tras el terremoto del 10 de agosto de 2026 es la prioridad nacional.
- El crédito de Findeter se limita a la capacidad prudente del municipio ($5.141 M a $10.281 M) y a proyectos que
  generan ahorro, como la granja solar.

El capítulo «Lo que pedimos» resume un pedido por entidad, con su monto y los módulos que mueve.

## Hoja de ruta

La gestión empieza ya, mientras se arma el PND 2026–2030 «Colombia, la Patria Milagro». Las compuertas son:

- bases al Consejo Nacional de Planeación el 15-nov-2026;
- plazo del presupuesto del SGR el 5-dic-2026;
- radicación del PND el 7-feb-2027 y aprobación a más tardar el 5-may-2027;
- elecciones locales el 31-oct-2027;
- nuevos planes de desarrollo municipal y departamental en 2028.

Las obras van en dos olas:

- **2028–2030:** acueducto, sóftbol y alameda, torre, fibra y granja, y rescate de las viviendas inconclusas.
- **2029–2031:** interceptores y PTAR, parque lineal, mirador, parque agroindustrial y urbanizaciones.

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
| `web/js/propuesta/piezas/` | Cancha de sóftbol, mirador, parque lineal, PTAR, ampliación de la PTAP, parque agroindustrial y granja solar |
| `web/js/propuesta/modulos/` | Lo 3D de cada capítulo: capas, vistas y animaciones por paso |
| `data/propuesta/general.json` | Portada, catálogo de fuentes, hoja de ruta y pedidos |
| `data/propuesta/modulos/*.json` | Un archivo por módulo |
| `data/propuesta/geo.json` | Sitios y trazados de cada propuesta |
| `data/propuesta/territorio.json` | Río, vías y puente (de `scripts/geo/territorio_propuesta.py` con `data/geo/osm_corredor_puente.xml`) |
| `scripts/build_propuesta.py` | Junta y valida (sumas, fuentes, componentes) y escribe `web/data/propuesta.json` |
