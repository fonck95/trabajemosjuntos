# El presentador

Una caricatura en 3D del candidato que explica, en la presentación técnica, lo que narra el asistente. Está hecha con
three.js a partir de su foto:

- **La cara**: un óvalo ancho, de lados casi rectos de la sien a la mejilla, con la mandíbula llena y el mentón ancho y
  redondo (en U, no en V), la frente alta y las orejas despegadas; las mejillas que sube la sonrisa, los pliegues de la
  nariz a la boca, los ojos almendrados entrecerrados (el párpado de abajo casi recto, el iris café oscuro) con sus
  patas de gallo y el pliegue del párpado, las cejas castañas de borde ralo, casi rectas, con un arco suave hacia la
  cola, bajas y cerca de los ojos, la nariz ancha y trapezoidal (la punta redonda fundida con las aletas, las fosas a la
  vista, el puente ancho y recto hasta el entrecejo) y la sonrisa ancha y plana, de medialuna, con el labio de abajo
  lleno y rosado y los dientes muy blancos; las mejillas en «manzanas», algo exageradas (el rasgo que lo distingue). La
  piel tostada rosada clara, con volumen (más clara en la frente, los pómulos y la nariz; más oscura hacia la mandíbula,
  en las cuencas, en el párpado de arriba y en la banda del pliegue de la sonrisa), un calor suave en las mejillas y la
  cara de abajo casi tan clara como la frente, como en la foto de estudio; los brazos y las manos, más tostados. El cuello grueso, casi tan ancho como la mandíbula, y más oscuro que la cara (a la sombra de la mandíbula).
- **El pelo**: casi negro, corto y con gel, peinado hacia arriba y algo hacia su izquierda. Manda el volumen: de frente
  es un domo ancho y redondeado, casi liso (la silueta calza con la de la foto), con una textura de puntitas cortas y
  finas que apenas rompen el borde, más paradas y apretadas al frente-centro y hacia su izquierda; el brillo del gel
  son vetas finas que siguen el peinado, de poco contraste (no manchones). La línea de la frente es una curva suave con
  un pico de viuda chico y redondeado; las esquinas retroceden en curva (entradas suaves, más la de su derecha) y bajan
  por la sien hasta la patilla, que llega al borde de arriba de la oreja y termina en un degradé hacia un gris de canas.
  Los lados son cortos y oscuros, pegados a la cabeza, con trazos cortos de pelo; solo el borde, donde el pelo es ralo,
  se aclara un poco. De perfil es un casco corto y continuo: el frente nace en una rampa desde la línea y queda apenas
  más alto que la coronilla (sin visera).
- **Las orejas**: grandes y despegadas, abiertas hacia adelante (de frente se les ve la concha), anchas y redondas
  arriba y angostas hacia el lóbulo, pegado; van de entre la ceja y el ojo a entre la nariz y la boca. La derecha se
  despega algo menos que la izquierda, como en la foto.
- **El cuerpo**: el de un hombre adulto y robusto, aunque con la cabeza grande de caricatura (mide unas tres cabezas y
  media): hombros anchos que bajan en pendiente suave desde el cuello, sin bultos; brazos y antebrazos fuertes y manos
  grandes, de dedos gruesos; muslos y cadera a juego con el torso.
- **La ropa**: la polo carmesí, suelta sobre la cadera, con el cuello grande de la foto: rodea el cuello por detrás y
  por los lados casi hasta la mandíbula, parado alrededor del cuello (no cae sobre los hombros), y adelante se abre en
  una V honda que deja ver la piel; sus bordes bajan hasta juntarse sobre el botón de arriba (que asoma bajo las
  puntas) y las puntas se apoyan en el pecho, junto a la tapeta. La tapeta larga, con dos botones blanco rosado (con su
  costura roja en cruz) y el pespunte en cuadro, abajo y a los lados; las mangas rectas, algo
  sueltas, con el puño acanalado del mismo rojo, y el jinete bordado (un caballo parado, mirando a la derecha, y el
  jinete derecho, de azul oscuro y pantalón blanco). El jean stonewash, desteñido casi celeste en los muslos y las
  rodillas y oscuro en los costados; el reloj negro grande en la muñeca izquierda (bisel gris, esfera gris carbón con
  doce marcas, la fecha y la corona) y la manilla roja, fina, con cuentas color oro champaña y dos cabos que cuelgan,
  en la derecha (cuelgan de verdad: en cada cuadro apuntan hacia abajo, también con la mano en alto). Al caminar, la
  polo se aparta del muslo que va adelante (o atrás): la tela pasa por encima de la pierna en vez de dejarla asomar.

Se arma entera con geometrías (sin modelos, sin imágenes y sin nada de afuera). La cabeza es una esfera esculpida (de
frente, una superelipse de lados casi rectos, con el relieve de pómulos, mejillas, cuencas, hocico, mentón y pliegues);
la nariz, una sola superficie suave (la unión de seis elipsoides), sin el casco del contorno: su borde se oscurece en el
sombreado donde queda de canto, una línea entera que la sigue desde cualquier lado; lo que va dibujado sobre la piel (ojos, cejas, boca,
pliegues, sombras suaves) son tiras pegadas a la superficie con una grilla de alturas que se mide una vez rasterizando
la cara. La piel lleva sombreado suave (una rampa de doce tonos, con las sombras más rojizas, como la piel de verdad);
la ropa, por tonos, como caricatura; todo con un contorno de grosor fijo, café rojizo en la piel y casi negro en el
pelo y la ropa (corrido un poco hacia atrás, para que no asome en motas en las zonas cóncavas; no baja hasta el borde
del pelo, que se funde con la piel). Lo dibujado sobre la piel no se pinta donde queda de canto a la cámara: de perfil, la ceja y el ojo
del otro lado no asoman por el borde de la frente.

| Archivo | Qué hace |
|---|---|
| `web/js/presentador/personaje.js` | El modelo y su esqueleto: pivotes para cadera, columna, pecho, cuello, cabeza, hombros, codos, muñecas, muslos, rodillas y tobillos; dos falanges por dedo y el pulgar. Los ojos, la boca y los pliegues van dibujados sobre la piel y se rehacen en cada cuadro (parpadear, mirar, hablar) |
| `web/js/presentador/animador.js` | Lo que lo mueve: una pose por capas (reposo, respiración, caminar, hablar, gesto, hacia dónde mira) que las articulaciones siguen con suavidad |
| `web/js/presentador/presentador.js` | El presentador dentro de la presentación: su lienzo sobre el subtítulo y lo que hace con cada orden del recorrido |
| `web/js/presentador/perezoso.js` | La carga del módulo recién cuando el mando lo necesita (la presentación pública no lo descarga) |
| `web/presentador.html` + `web/js/presentador/taller.js` | El taller: el personaje solo, para verlo, moverlo y probar cada gesto |

## La serie de gestos

El asistente puede pedir uno en cada paso del plan (`gesto`); son los de `GESTOS` en `admin/app/recorrido.py` (que le
llegan al modelo con el guion, con lo que expresa cada uno) y de `GESTOS_AGENTE` en `animador.js`:

| Gesto | Qué hace | Para |
|---|---|---|
| `saludar` | saluda con la mano | empezar |
| `senalar` | señala con el dedo lo resaltado o, sin resaltado, la obra en la maqueta | «esta es…» |
| `presentar` | presenta con la palma abierta la obra en la maqueta | mostrar una obra |
| `mostrar_panel` | señala el texto y las cifras del panel | un dato del panel |
| `mirar_maqueta` | las manos en la cintura, mira la maqueta | dejar que la sala mire |
| `explicar` | las dos manos adelante, las palmas arriba | explicar |
| `destacar` | levanta el índice | «esto es clave» |
| `comparar` | una mano y luego la otra | hoy y con el proyecto, antes y después |
| `enumerar` | cuenta con los dedos, uno por cada frase del paso | una lista |
| `crecer` | sube las manos | crece, aumenta, mejora |
| `grande` | abre los brazos | una obra grande |
| `detalle` | los dedos en pinza | un detalle preciso |
| `construir` | martilla con el puño | lo que se construye |
| `pensar` | la mano en la barbilla | «¿por qué?» |
| `preguntar` | las palmas arriba, la cabeza ladeada | una pregunta a la sala |
| `asentir` / `negar` | asiente; niega con la cabeza y el dedo | sí; eso no |
| `calmar` | las palmas hacia abajo | «tranquilos, está previsto» |
| `aprobar` | pulgar arriba | listo, aprobado |
| `celebrar` | los puños arriba y un saltito | un logro |
| `aplaudir` | aplaude | un reconocimiento |
| `juntos` | junta las manos | «trabajemos juntos» |
| `corazon` | la mano en el pecho | un compromiso |
| `invitar` | abre los brazos | bienvenida o «¿preguntas?» |
| `despedirse` | se despide con la mano | terminar |

Además, solos: `contar` (los puntos del resumen), `escuchar` (en pausa), hablar (la boca por sílabas, la cabeza y las
manos que acompañan con un golpe cada tanto), parpadear, mirar a un punto (columna, cuello, cabeza y ojos se reparten el
giro), caminar hasta una x, entrar (sube con un rebote) y salir (baja).

Cada gesto es una pose (ángulos de cada articulación en el orden de su hueso) o varias encadenadas (`claves`: comparar,
crecer, juntos) que entran y salen sobre lo demás, con vaivenes opcionales; el brazo derecho es el espejo del izquierdo,
así los mismos números sirven para los dos lados. `senalar`, `presentar` y `mirar_maqueta` calculan el ángulo del
hombro (o de la cabeza) hacia el punto y usan el brazo de ese lado.

### Cómo lo pide el asistente

Cada paso del plan (`presentacion`, op `recorrido`) puede traer `"gesto": "comparar"`. Llega con tildes o en otras
palabras («señalar», «pulgar», «contar», «aplauso») y se resuelve al nombre; uno que no existe se descarta con un aviso
y el plan corre igual. Va al recorrido guardado (`recorrido.validar` lo revisa), a la tarjeta del chat (el chip «El
presentador hace un gesto»), al reproductor y a la orden `escena` de la presentación, que se lo pasa al presentador. Un
paso sin `gesto` (o un plan de antes, o la presentación automática) deja que el presentador elija solo, como antes.

## En la presentación

Solo aparece dentro de la vista Presentación del panel (la pestaña del chat, la ventana del proyector y la pantalla en
off), cuando hay algo que explicar. Es un `<canvas>` transparente con su propio WebGL, de pie detrás del borde de arriba
del subtítulo (los pies quedan detrás, como en un atril), sin tomar toques ni clics; solo dibuja mientras está a la
vista. En pantalla grande va en el extremo izquierdo del subtítulo, junto al panel; en el celular, en el derecho y más
chico. Sigue al subtítulo cuando se mueve.

Lo que hace con cada orden del mando (`web/js/propuesta/mando.js`):

| Orden | El presentador |
|---|---|
| `escena` con `gesto` | Hace ese gesto (si es el primero y es `saludar`, lo hace al subir) |
| `escena` sin `gesto`, el paso 1 | Sube y saluda |
| `escena` sin `gesto`, los demás | Señala lo que se resalta (`.foco`: una cifra, un punto, la leyenda, una especificación de la ficha) o, si la cámara va a una obra, un modelo del atlas o se mueve, la presenta con la palma; si no, explica con las dos manos |
| `narracion {frase}` | Habla: con voz, hasta que la vista avisa que terminó; sin voz, lo que tardaría en decirla |
| `narracion {habla}` | La voz del panel empieza (`true`) o termina (`false`) de decir algo: abre o cierra la boca |
| `narracion {pausa}` | Calla y escucha; al seguir, suelta las manos |
| `narracion {preparando}` | Piensa mientras el asistente prepara la explicación |
| `cierre {puntos}` | Cuenta los puntos del resumen con los dedos |
| `cierre {puntos: null}` | «¿Preguntas?»: abre los brazos |
| `explicar` | Dice la explicación suelta |
| `quitar_explicacion` | Se despide y baja (si el subtítulo no vuelve enseguida: un cambio de paso dentro del plan no lo despide) |
| `vista {presentador}` | Lo muestra u oculta (el botón **Presentador** del panel) |

`habla` es la única orden nueva del lado del panel: la vista envuelve la voz del reproductor y le avisa a la presentación
cuándo empieza y termina cada frase. No cambia los tiempos ni las fases del recorrido. Los planes del asistente y de
los agentes por MCP no traen nada nuevo: el presentador decide sus gestos con lo que el mando ya sabe de cada escena.

El botón **Presentador** (en la barra de la pestaña, en la de la pantalla en off y entre los botones del proyector) lo
oculta o lo muestra; la preferencia queda en ese navegador (`yj_presentador`) y se le vuelve a mandar a la presentación
cada vez que carga.

Con `prefers-reduced-motion` entra y sale sin animación y sin saltos. Si el navegador no puede crear el contexto WebGL
(o lo pierde), no hay presentador y la presentación sigue igual.

## El taller

`presentador.html` (en `site/`, al lado del atlas y la propuesta; no se indexa) muestra el personaje solo:

- arrastrar gira la vista y la rueda la acerca;
- un clic hace que señale ese punto (con Mayúsculas, que lo presente con la palma);
- las flechas ← → lo hacen caminar;
- los botones disparan cada gesto de la serie (con su nombre en el plan en el title), la entrada y la salida;
- **Decir** le mueve la boca lo que tardaría en decir el texto y lo muestra abajo, como el subtítulo (la voz de verdad es
  la del panel, en el recorrido narrado); **Mover la boca** habla sin parar hasta apagarlo.

## Cómo cambiarlo

- Colores: `COLORES` en `personaje.js` (piel, pelo, polo, jean…). El volumen de la piel lo da `rampaPiel` (cuánto
  oscurece cada tono y el tinte de las sombras); las sombras y el calor pintados, los discos de `sombra` al principio de
  `construirCara`. La luz principal del presentador viene de la izquierda de quien mira (en la foto, de la derecha).
- Forma de la cara: `deformarCabeza` (la superelipse de frente, las sienes, el largo de la mandíbula y el mentón) y
  `RELIEVE` (los bultos y hundidos de la cara), el pelo (en `pelo`: la línea del pelo `lineaBase`/`limite`, el grueso
  del casco por meridianos `deLado`/`deFrente`/`deAtras`, sus colores en `tinte` y en `COLORES.pelo*`) y las medidas de ojos, cejas,
  orejas, nariz y boca en `construirCara` y `crearBoca`. La forma de la oreja (su silueta, el hélix, la concha y sus
  dos líneas) está en `ORE`; en `construirCara` solo se ubica y se gira (cuánto se despega).
- El cuerpo y la ropa: el torso es un torno (`perfil`) que `anchoTorso` y `fondoTorso` ensanchan y aplanan; las mismas
  funciones (`enTorso`, `zTorso`, `fueraDelTorso`, `sobreTorso`) sirven para apoyar cosas sobre la polo sin lanzar
  rayos (el jinete va pegado a la tela con `sobreTorso`). `apartarPolo` empuja la parte de abajo de la polo y el ruedo
  fuera de los muslos (`PERFIL_MUSLO`, con `HOLGURA_MUSLO`) justo antes de calcular la matriz de la polo (no recalcula
  si los muslos no se movieron desde la vez anterior, ni mientras no alcanzan a gastar la `holgura` que quedaba); `colgar`
  apunta los cabos de la manilla hacia abajo. El cuello
  de la polo se arma en `cuelloDeLaPolo`: el doblez de arriba (`arriba`, alrededor del cuello) y el borde de abajo
  (`BORDE`: dónde se apoya en los hombros, la punta y la V), y `ABRE_CUELLO` es la altura de la V (donde empieza la
  tapeta). La cabeza va al 0,94 (`craneo.scale`): más grande, el cuerpo parece de niño.
- Gestos: `GESTOS` en `animador.js`. Un gesto nuevo es una función que devuelve su pose (o sus claves), sus manos
  (`MANOS`), sus vaivenes y lo que hace la cara. Para que el asistente lo pueda pedir, va también en `GESTOS` de
  `admin/app/recorrido.py` (con lo que expresa), en `GESTOS_AGENTE` y en las listas de `mando.js` y del puente
  (`admin/web/js/agente-presentacion.js`): una prueba las compara. El taller lo muestra solo.
- Lo que hace en cada orden: los métodos de `crearPresentador` en `presentador.js`.

Las pruebas: `admin/tests/test_presentador.py` (con Node: el modelo y el animador sin WebGL, la carga perezosa y lo que
el mando le avisa en cada orden).
