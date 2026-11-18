# El presentador

Una caricatura en 3D del candidato que explica, en la presentación técnica, lo que narra el asistente. Está hecha con
three.js a partir de su foto: cabeza grande con el pelo corto y parado, cejas gruesas, la sonrisa ancha con los dientes a
la vista, la camiseta polo roja con su cuello, la tapeta de dos botones y el jinete bordado, el jean, el reloj negro en
la muñeca izquierda y la manilla roja con cuentas doradas en la derecha. Se arma entera con geometrías (sin modelos, sin
imágenes y sin nada de afuera) y se dibuja como caricatura: sombreado por tonos y un contorno oscuro.

| Archivo | Qué hace |
|---|---|
| `web/js/presentador/personaje.js` | El modelo y su esqueleto: pivotes para cadera, columna, pecho, cuello, cabeza, hombros, codos, muñecas, muslos, rodillas y tobillos; dos falanges por dedo y el pulgar. Los ojos, la boca y los pliegues van dibujados sobre la piel y se rehacen en cada cuadro (parpadear, mirar, hablar) |
| `web/js/presentador/animador.js` | Lo que lo mueve: una pose por capas (reposo, respiración, caminar, hablar, gesto, hacia dónde mira) que las articulaciones siguen con suavidad |
| `web/js/presentador/presentador.js` | El presentador dentro de la presentación: su lienzo sobre el subtítulo y lo que hace con cada orden del recorrido |
| `web/js/presentador/perezoso.js` | La carga del módulo recién cuando el mando lo necesita (la presentación pública no lo descarga) |
| `web/presentador.html` + `web/js/presentador/taller.js` | El taller: el personaje solo, para verlo, moverlo y probar cada gesto |

## Gestos

`saludar`, `despedirse`, `senalar` (con el dedo, hacia un punto), `presentar` (con la palma abierta, hacia un punto),
`explicar` (las dos manos, palmas arriba), `contar` (de 1 a 3 con los dedos), `pensar` (la mano en la barbilla),
`celebrar` (los puños arriba y un saltito), `invitar` (los brazos abiertos), `asentir`, `pulgar` (arriba) y `escuchar`
(las manos juntas; se sostiene hasta otro gesto). Además: hablar (la boca por sílabas, la cabeza y las manos que
acompañan), parpadear, mirar a un punto (columna, cuello, cabeza y ojos se reparten el giro), caminar hasta una x,
entrar (sube con un rebote) y salir (baja).

Cada gesto se escribe como una pose (ángulos de cada articulación en el orden de su hueso) que entra y sale sobre lo
demás, con vaivenes opcionales; el brazo derecho es el espejo del izquierdo, así los mismos números sirven para los dos
lados. `senalar` y `presentar` calculan el ángulo del hombro que apunta al punto y usan el brazo de ese lado.

## En la presentación

Solo aparece dentro de la vista Presentación del panel (la pestaña del chat, la ventana del proyector y la pantalla en
off), cuando hay algo que explicar. Es un `<canvas>` transparente con su propio WebGL, de pie detrás del borde de arriba
del subtítulo (los pies quedan detrás, como en un atril), sin tomar toques ni clics; solo dibuja mientras está a la
vista. En pantalla grande va en el extremo izquierdo del subtítulo, junto al panel; en el celular, en el derecho y más
chico. Sigue al subtítulo cuando se mueve.

Lo que hace con cada orden del mando (`web/js/propuesta/mando.js`):

| Orden | El presentador |
|---|---|
| `escena` (el paso 1) | Sube y saluda |
| `escena` (los demás) | Señala lo que se resalta (`.foco`: una cifra, un punto, la leyenda, una especificación de la ficha) o, si la cámara va a una obra, un modelo del atlas o se mueve, la presenta con la palma; si no, explica con las dos manos |
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
- los botones disparan cada gesto, la entrada y la salida;
- **Decir** lo hace hablar con la voz del navegador (si hay una en español) y **Mover la boca**, sin voz.

## Cómo cambiarlo

- Colores: `COLORES` en `personaje.js` (piel, pelo, polo, jean…).
- Forma de la cara: `deformarCabeza` (óvalo, pómulos, mandíbula, mentón), la línea del pelo (`limite` en `pelo`) y las
  medidas de ojos, cejas, nariz y boca en `construirCara` y `crearBoca`.
- Gestos: `GESTOS` en `animador.js`. Un gesto nuevo es una función que devuelve su pose, sus manos (`MANOS`), sus
  vaivenes y lo que hace la cara; el taller lo muestra solo.
- Lo que hace en cada orden: los métodos de `crearPresentador` en `presentador.js`.

Las pruebas: `admin/tests/test_presentador.py` (con Node: el modelo y el animador sin WebGL, la carga perezosa y lo que
el mando le avisa en cada orden).
