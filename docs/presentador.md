# El presentador

Una caricatura en 3D del candidato que explica, en la presentación técnica, lo que narra el asistente. Está hecha con
three.js a partir de su foto:

- **La cara**: llena y ancha en los pómulos, con la mandíbula que se angosta sin hacer punta y el mentón redondo; las
  mejillas que sube la sonrisa, los pliegues de la nariz a la boca, los ojos almendrados entrecerrados con sus patas de
  gallo y el pliegue del párpado, las cejas oscuras casi rectas, la nariz ancha de punta redonda y la sonrisa amplia con
  el labio de arriba fino, el de abajo lleno y los dientes muy blancos. La piel tostada rosada, con el calor de las
  mejillas y la nariz.
- **El pelo**: negro, corto en cepillo, parado y peinado hacia arriba, con la línea de la frente recta y los lados cortos
  en degradé.
- **La ropa**: la polo carmesí con su cuello, la tapeta de dos botones (con su costura en cruz) y el jinete bordado; el
  jean desteñido adelante; el reloj negro grande en la muñeca izquierda y la manilla roja con cuentas doradas en la
  derecha.

Se arma entera con geometrías (sin modelos, sin imágenes y sin nada de afuera). La cabeza es una esfera esculpida (el
óvalo y el relieve de pómulos, mejillas, cuencas, hocico, mentón y pliegues); lo que va dibujado sobre la piel (ojos,
cejas, boca, pliegues, sombras suaves) son tiras pegadas a la superficie con una grilla de alturas que se mide una vez
rasterizando la cara. La piel lleva sombreado suave; la ropa, por tonos, como caricatura; todo con un contorno oscuro.

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

- Colores: `COLORES` en `personaje.js` (piel, pelo, polo, jean…).
- Forma de la cara: `deformarCabeza` (óvalo, pómulos, mandíbula, mentón), la línea del pelo (`limite` en `pelo`) y las
  medidas de ojos, cejas, nariz y boca en `construirCara` y `crearBoca`.
- Gestos: `GESTOS` en `animador.js`. Un gesto nuevo es una función que devuelve su pose (o sus claves), sus manos
  (`MANOS`), sus vaivenes y lo que hace la cara. Para que el asistente lo pueda pedir, va también en `GESTOS` de
  `admin/app/recorrido.py` (con lo que expresa), en `GESTOS_AGENTE` y en las listas de `mando.js` y del puente
  (`admin/web/js/agente-presentacion.js`): una prueba las compara. El taller lo muestra solo.
- Lo que hace en cada orden: los métodos de `crearPresentador` en `presentador.js`.

Las pruebas: `admin/tests/test_presentador.py` (con Node: el modelo y el animador sin WebGL, la carga perezosa y lo que
el mando le avisa en cada orden).
