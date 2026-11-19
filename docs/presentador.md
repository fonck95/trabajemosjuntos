# El presentador

Una caricatura en 3D del candidato que explica, en la presentación técnica, lo que narra el asistente. Está de pie
detrás del subtítulo como detrás de un atril y toma la vista que corresponde a lo que se está explicando: de frente a la
sala cuando habla en general, girado hacia el panel cuando señala una cifra, hacia la maqueta cuando presenta una obra,
entero cuando la maqueta ocupa toda la pantalla, de cerca en el cierre y, cuando el atlas ocupa la pantalla, solo su
cara en un círculo. Está hecho con three.js a partir de su foto:

- **La cara**: un óvalo ancho, de lados casi rectos de la sien a la mejilla, con la mandíbula llena y el mentón ancho y
  redondo (en U, no en V), la frente alta y las orejas despegadas; las mejillas que sube la sonrisa, los pliegues de la
  nariz a la boca, los ojos almendrados entrecerrados (el párpado de abajo casi recto, el iris café oscuro) con sus
  patas de gallo y el pliegue del párpado, las cejas castañas de borde ralo, casi rectas, con un arco suave hacia la
  cola, bajas y cerca de los ojos, la nariz ancha y trapezoidal (la punta redonda fundida con las aletas, las fosas a la
  vista, el puente ancho y recto hasta el entrecejo) y la sonrisa ancha y plana, de medialuna, con el labio de abajo
  lleno y rosado y los dientes muy blancos; las mejillas en «manzanas», algo exageradas (el rasgo que lo distingue). La
  piel tostada rosada clara, con volumen (más clara en la frente, los pómulos y la nariz; más oscura hacia la mandíbula,
  en las cuencas, en el párpado de arriba y en la banda del pliegue de la sonrisa), un calor suave en las mejillas y la
  cara de abajo casi tan clara como la frente, como en la foto de estudio; los brazos y las manos, más tostados. El
  cuello grueso, casi tan ancho como la mandíbula, y más oscuro que la cara (a la sombra de la mandíbula).
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
  media): hombros anchos que bajan en pendiente suave desde el cuello, sin bultos; brazos y antebrazos fuertes. Las
  manos van ×1.3 desde la muñeca (`ESCALA_MANO`: miden 0.26, el 11 % de su alto, como una mano real; de lejos se leen),
  con su propio tono de piel (`pielMano`, entre el del brazo y el de la cara) y los dedos estirados que se abren en
  abanico (`ABRE` en animador.js: la palma abierta no se lee como una manopla y los dedos que cuentan se separan).
- **La ropa**: la polo carmesí, suelta sobre la cadera, con el cuello grande de la foto: rodea el cuello por detrás y
  por los lados casi hasta la mandíbula, parado alrededor del cuello (no cae sobre los hombros), y adelante se abre en
  una V honda que deja ver la piel; sus bordes bajan hasta juntarse sobre el botón de arriba (que asoma bajo las
  puntas) y las puntas se apoyan en el pecho, junto a la tapeta, con un filo más claro en el borde (`poloFilo`) y una
  sombra suave sobre el pecho. La tapeta larga, con dos botones blanco rosado (con su costura roja en cruz) y el
  pespunte en cuadro, abajo y a los lados; la manga y la copa del hombro son una sola pieza (sin escalón) que se
  deforma al levantar el brazo, con el puño acanalado del mismo rojo, y el jinete bordado (un caballo parado, mirando a
  la derecha, y el jinete derecho, de azul oscuro y pantalón blanco). El jean stonewash, desteñido casi celeste en los
  muslos y las rodillas y oscuro en los costados; el reloj negro grande en la muñeca izquierda (bisel gris, esfera gris
  carbón con doce marcas, la fecha y la corona) y la manilla roja, fina, con cuentas color oro champaña y dos cabos que
  cuelgan, en la derecha (cuelgan de verdad: en cada cuadro apuntan hacia abajo, también con la mano en alto). Al
  caminar, la polo se aparta del muslo que va adelante (o atrás): la tela pasa por encima de la pierna en vez de
  dejarla asomar.

Se arma entera con geometrías (sin modelos, sin imágenes y sin nada de afuera). La cabeza es una esfera esculpida (de
frente, una superelipse de lados casi rectos, con el relieve de pómulos, mejillas, cuencas, hocico, mentón y pliegues);
la nariz, una sola superficie suave (la unión de seis elipsoides), sin el casco del contorno: su borde se oscurece en el
sombreado donde queda de canto, una línea entera que la sigue desde cualquier lado; lo que va dibujado sobre la piel
(ojos, cejas, boca, pliegues, sombras suaves) son tiras pegadas a la superficie con una grilla de alturas que se mide
una vez rasterizando la cara. La piel lleva sombreado suave (una rampa de doce tonos, con las sombras más rojizas, como
la piel de verdad); la ropa, por tonos, como caricatura; todo con un contorno de grosor fijo, café rojizo en la piel,
casi negro en el pelo, vino en la polo (`contornoPolo`) y azul oscuro en el jean (`contornoJean`); corrido un poco hacia
atrás, para que no asome en motas en las zonas cóncavas (el cuello de la polo, casi nada: su borde apoyado en el pecho
es una línea entera), y sin bajar hasta el borde del pelo, que se funde con la piel. Lo dibujado sobre la piel no se
pinta donde queda de canto a la cámara: de perfil, la ceja y el ojo del otro lado no asoman por el borde de la frente.

| Archivo | Qué hace |
|---|---|
| `web/js/presentador/personaje.js` | El modelo y su esqueleto: pivotes para cadera, columna, pecho, cuello, cabeza, hombros, codos, muñecas, muslos, rodillas y tobillos; dos falanges por dedo y el pulgar. Los ojos, la boca y los pliegues van dibujados sobre la piel y se rehacen en el lugar (parpadear, mirar, hablar, el nivel de detalle) |
| `web/js/presentador/animador.js` | Lo que lo mueve: una pose por capas (reposo vivo, caminar, agacharse, hablar, el gesto, la mirada, los pies) que cada articulación sigue con su muelle; el habla desde el texto; los 25 gestos y los automáticos |
| `web/js/presentador/vistas.js` | Las vistas, sin THREE ni DOM (se prueba con Node): qué vista toma con lo que se explica, dónde se para, hacia dónde apunta y cómo pasa de una vista a otra |
| `web/js/presentador/presentador.js` | El presentador dentro de la presentación: su lienzo detrás del subtítulo, la vista de cada escena, las transiciones, el programa de la escena, la luz y lo que hace con cada orden del mando |
| `web/js/presentador/perezoso.js` | La carga del módulo recién cuando el mando lo necesita (la presentación pública no lo descarga) |
| `web/presentador.html` + `web/js/presentador/taller.js` | El taller: el personaje solo, para verlo, moverlo y probar cada gesto |

## Vistas

El lienzo no muestra la figura entera fija: se encuadra por **planos** (una ventana vertical del personaje) y el borde de
arriba del subtítulo lo corta a una altura dada, como un atril. La cámara se recalcula en cada cuadro con la escala (px
por unidad), el ancla del mundo (el corte) y dónde cae ese ancla en el lienzo; el tamaño del lienzo (`setSize`, con el
DPR topado en `min(devicePixelRatio, Hc > 300 ? 1.5 : 2)`) solo cambia con la vista o la ventana. Lo que queda bajo el
corte nunca se ve (`clip-path: inset(0 0 bajo px 0)`: el subtítulo es vidrio y dejaría ver las piernas). La `y` del
lienzo se pega al borde del subtítulo en cada cuadro, sin retraso; la `x` la fija el lugar y solo la cambian las
transiciones.

| Plano | Ventana [yb, ya]·alto | Corte yc·alto | Ancho del lienzo (·pxAlto) | Se usa en |
|---|---|---|---|---|
| `entero` | [0, 1.10] | 0.05 (los pies) | 1.05 | `general` |
| `americano` | [0.26, 1.10] | 0.37 (la cadera, bajo la polo) | 1.10 | `anfitrion`, `senala`, `presenta` |
| `medio` | [0.34, 1.08] | 0.40 (bajo las manos de la casa) | 1.20 | `cerca`, `busto` |
| `primer` | [0.52, 1.06] | sin corte (va en un círculo) | cuadrado | `rotulo` |

### Las siete vistas (`VISTAS`)

`p` es `pxAlto` (lo que mediría el personaje entero en la pantalla): `clamp(k·alto de la ventana, min, max)`. La cabeza
mide `0.312·p`. Medidas en la presentación real: cabeza de 101–106 px a 1440x900, 82–83 a 1280x720, 119–125 a
1920x1080, 69–73 en el busto del celular (390x844) y 107 en la tableta parada (980x2120).

| Vista | Plano y tamaño | Lugar preferido | Rumbo · apertura | Qué hace |
|---|---|---|---|---|
| `anfitrion` | americano, `clamp(0.36·VH, 220, 400)` (324 a 1440x900) | el centro del subtítulo | 0 · 0.55 | de frente a la sala: saluda, explica, pregunta, piensa, el lema |
| `senala` | americano, igual | del lado de lo que señala, a un brazo (lo más cerca que deje el alcance) | ±0.35 · 0.55 | señala lo resaltado del panel, la ficha o la leyenda y lo sostiene con la mano |
| `presenta` | americano, igual | por puntaje; de preferencia el extremo izquierdo del subtítulo | ±0.30 · 0.55 | presenta la obra de la maqueta con la palma y la mira |
| `general` | entero, `clamp(0.42·VH, 250, 460)` (378); celular `clamp(0.28·VH, 160, 280)` | el extremo izquierdo (`sub.left + 0.25p`; en el celular, el derecho) | ±0.30 · 0.55 | «Solo 3D»: la figura entera junto a la maqueta |
| `cerca` | medio, `clamp(0.5·VH, 280, 520)` (450) | el primer tercio del subtítulo | 0 · 0.55 | el cierre (cuenta los puntos) y «¿Preguntas?» |
| `rotulo` | primer plano en un círculo: bajo el panel `clamp(0.125·VH, 88, 128)` (113); acoplado 84; celular 64; de lado, el alto del subtítulo − 6 (44–64) | bajo el panel o acoplado al subtítulo | ±0.30 · 0.45 | con el atlas a la vista (o la ficha en el celular, o el celular de lado): solo la cara |
| `busto` | medio, `clamp(0.26·VH, 150, 240)` (219 a 390x844); en una pantalla alta, al menos `clamp(0.16·VH, 150, 360)`; en el cierre ×1.15 | el extremo derecho (`sub.right − 0.26p`), si no el izquierdo | ±0.25 · 0.50 | la pantalla chica: anfitrión, señala, presenta y cerca pasan a busto |

- Las tres primeras tienen el mismo plano y tamaño: pasar de una a otra es girar (y a veces caminar), nunca cambiar de
  tamaño.
- `apertura`: lo más que la cara se aparta de la sala (rad). El cuerpo puede girar más; la cara queda en 3/4, nunca de
  perfil, y los ojos hacen el resto.
- La pantalla chica es `innerWidth ≤ 1080` (`CHICA_PX`); de lado, además, `innerHeight < 520` (`HORIZONTAL_PX`).

### Cómo elige (`elegirVista`)

`elegirVista(d, ctx)` recibe lo que trae `narrar` (más `d.evento`: `narrar`, `cierre`, `preguntas`, `preparando`,
`explicar` o `pausa`) y el contexto (`chica`, `VW`, `VH`, `horizontal`, `nuevo`, `reducido`, las clases de `#pres`, la
escena anterior y `domManda`). Devuelve `{vista, lado, objetivo, gesto, frente, transicionCapitulo, saludoPrimero,
saludoCorto, regla}`. La primera regla que se cumple decide:

| Regla | Si | Vista · lado (objetivo), gesto por omisión |
|---|---|---|
| R1 | celular de lado | `rotulo` acoplado (`marco` si hay atlas; si no, `sala`) |
| R2 | un modelo del atlas a la vista (o cargando) | `rotulo` · `marco` |
| R3 | pantalla chica y la ficha abierta | `rotulo` · `ficha` |
| — | `cierre` / `preguntas` | `cerca` (celular: `busto` ×1.15) · `sala`, `contar` / `invitar` |
| — | `preparando` | `anfitrion` · `sala`, `pensar` |
| — | `explicar` | `anfitrion` · `sala`, `explicar` |
| — | `pausa` | la vista que tenía, `escuchar`, de frente |
| R4 | escritorio y lo resaltado está en la ficha o es la leyenda | `senala` · `ficha` / `leyenda` (`foco`) |
| R5 | escritorio y lo resaltado está en el panel (cifra, punto, componente, especificación del panel) | `senala` · `panel` (`foco`) |
| R5c | lo mismo en la pantalla chica | `busto` · `hoja` (`foco`), `destacar` |
| R4c | la leyenda en la pantalla chica | `busto` · `arriba` (`foco`), `senalar` |
| R6 | escritorio, la ficha abierta sin resaltado | `senala` · `ficha` (`ficha`), `presentar` |
| R7 | el panel oculto («Solo 3D») | `general` · `obra`, `presentar` |
| R8 | la escena pide la obra (`obraExplicita`: enfoque, cámara, partes, hoy/proyecto, simular en la maqueta, un movimiento que no es el suave del recorrido, o un gesto hacia la maqueta) | `presenta` · `obra`; `comparar` si cambió hoy/proyecto, `detalle` si aísla o quita partes, si no `presentar` |
| R9 | se pidió `senalar` o `mostrar_panel` sin resaltado | `senala` · `panel` (`bloque`) |
| R10 | por el tipo de paso (la presentación automática y los planes sin lo visual) | ver abajo |
| R11 | nada de lo anterior | `anfitrion` · `sala`, `explicar` |

R10, por `d.tipo`: `portada` → `anfitrion`; en la escena 1, `presentar` con un barrido por los pines de la maqueta; en
las demás, `explicar`. `portadilla` con cambio de capítulo o de paso → `anfitrion`, `explicar` (o `pensar` si la primera
frase pregunta o niega: «¿por qué…?», «hoy no hay…»); en las demás escenas del paso, `presenta`, `mirar_maqueta`.
`componentes`, `componente` e `inmersion` → `presenta`, `presentar`. `comparacion` → `senala` · `panel`, `comparar`.
`metas` → `senala` · `panel`, `mostrar_panel` (o `crecer` si una frase dice «→», «meta» o «de … a …»). `cronograma` →
`senala` · `panel`, `presentar` con un barrido por los años del Gantt. `texto` con lista → `senala` · `panel`,
`enumerar`; sin lista → `anfitrion`, `explicar`.

Después de elegir:

- En la pantalla chica, `anfitrion`, `senala`, `presenta` y `cerca` pasan a `busto` (el lado `panel` pasa a `hoja`).
- **Bienvenida** (`saludoPrimero`): recién sube en la escena 1, saluda en el lugar de la vista elegida (2.6 s; 1 s con
  movimiento reducido) y después hace lo de la vista. Si la escena ya trae un dato resaltado, un saludo corto
  (`saludoCorto`, 1.2 s) para no demorar el señalar. Una sola vez por recorrido (`rid`).
- **De cara a la sala** (`frente`): `DE_FRENTE` (saludar, invitar, celebrar, aplaudir, juntos, corazon, preguntar,
  asentir, negar, calmar, aprobar, pensar, explicar, destacar, crecer) se hace de frente mientras dura y después vuelve
  al rumbo de la vista.
- **Cambio de capítulo** (`transicionCapitulo`): antes del gesto mira el panel 0.6 s (cambió de color y de contenido)
  con las cejas arriba.
- **Lo que se ve manda** (`domManda`): si a mitad de una escena se abre o se cierra «Solo 3D», la ficha o el atlas (el
  botón, una orden `visual` del asistente), o cambia la ventana, la vista se vuelve a elegir con lo que hay en la página
  y no con lo que pedía la escena (un `MutationObserver` sobre las clases `sin-panel`, `con-detalle` y `con-inmersion` de
  `#pres`, y el `resize`, a los 0.5 s; nunca en los primeros 1.5 s de la escena, mientras la página se pone como la
  escena pide). Sin gesto de entrada: pasa al sostén hacia lo nuevo.

### El lugar (`lugares`, `elegirLugar`)

Las cajas se leen de la página una vez por escena (y otra vez cuando llega el aviso `encuadre`): el subtítulo, el panel
(su caja de ahora y la de cuando termine de deslizarse), la ficha, la leyenda, el HUD, el marco del atlas, la barra, el
control, la obra y los rótulos de la maqueta donde quedarán al final del viaje de la cámara (de cada uno, su título y su
caja entera; también donde empieza el viaje) y lo resaltado (`.foco`).

- **Candidatos**: cada 40 px a lo largo del subtítulo (señalando, cada 8) más el izquierdo, el centro, el derecho y el
  preferido. En la pantalla chica, solo los dos extremos.
- **Lo que descarta**: la huella fuera de la pantalla; la cadera fuera del subtítulo (se verían las piernas cortadas en
  el aire); tapar el panel, la ficha o el marco del atlas (también con los brazos abiertos del gesto: `ENVERGADURA`);
  señalando, la punta del dedo dentro de lo que señala o bajo el corte.
- **El puntaje** (menor es mejor): lo que la silueta (la cabeza y el torso; el brazo hacia el objetivo con la mitad del
  peso) tapa de la obra (peso 1), del título de cada rótulo (2) y de su caja entera (1), de lo resaltado (3), del HUD (3)
  y de la leyenda (3). Un rótulo o lo resaltado se mide sobre su propia área: poco si se tapa un poco, mucho pasado el
  25 % (ya no se lee). Más lo que se aleja del preferido (señalando pesa más).
- **Señalar**: el dedo «llega» si la punta del índice queda a no más de 90 px (`LLEGA_PX`) de lo que señala. Si desde
  algún lugar que deje leer los rótulos de la maqueta (el título y la caja tapados a lo sumo un 30 %) llega, se queda en
  la banda de los que más se acercan. Si lo señalado está más de 150 px (`ALTO_PX`) arriba del hombro, lo señala con el
  índice y el brazo estirado (la palma alzada se leería como una mano levantada). Si desde ningún lugar limpio el dedo
  llega (a más de 120 px, `LEJOS_PX`), señala **desde lejos**: la mano abierta hacia el borde de lo que explica que da a
  él, a la altura del hombro y nunca más de ~11° hacia arriba (`manoAbierta`), sin caer a menos de 60 px de un rótulo de
  la maqueta (se leería «esto de acá»); la cara mira lo que explica y vuelve a la sala, y lo resaltado late cuando se
  abre la palma. Se lee «miren ahí, en el panel» y no «esto del mapa».
- **Histéresis**: se queda donde está si sigue cumpliendo, lo que señala está del mismo lado, la punta queda a no más de
  40 px de la del mejor y su costo es ≤ 1.25·mejor + 0.02. No se mueve por poco (menos de 0.25·p, o menos de 60 px en
  contra de lo que explica: gira en el lugar). A lo sumo un cambio de lugar por escena y ninguno en una escena de menos
  de 3.5 s, salvo que el lugar de ahora deje de servir (la cadera en el aire, tapa el panel, la punta no llega) o que se
  haya elegido sin saber dónde quedaban la obra y sus rótulos (`ciego`: lo que llegó manda).
- **Cuándo**: la vista y el giro, al llegar `narrar`; el lugar, a los 150 ms o al llegar `encuadre` (lo que pase
  primero). Si el encuadre llegó sin rótulos y a los 0.7 s ya aparecieron, se vuelve a puntuar una vez, antes del gesto.
  Si lo resaltado aparece en otro lado del que se preveía (más de 40 px), también. Oculto o subiendo, elige sin
  histéresis (entre dos escenas se asoma ya en el lugar nuevo).

El objetivo (`objetivoDe`): lo resaltado, en su borde que da al hombro y a la altura del hombro; el `bloque` del panel
(`panel.right − 40`); el centro de la obra (la del encuadre recortada a la zona libre); el centro del marco o de la
ficha. La punta nunca baja del corte (`apuntable` levanta el punto lo justo).

### Las transiciones (`transicion`)

| Transición | Cuándo | Cómo y cuánto tarda |
|---|---|---|
| `giro` | mismo lugar y mismo plano | gira en el lugar (el rumbo con su muelle, ~0.5 s) |
| `acercar` | otro plano a no más de 0.2·p | la cámara pasa de un plano al otro en 0.7 s (`ACERCAR_MS`); el lienzo, el mayor de los dos mientras dura |
| `caminar` | mismo plano, otro lugar a no más de 0.8·p | camina detrás del subtítulo en 3/4 (rumbo 0.6, zancada 0.65) a 0.95 unidades por segundo (≈ 2.5 pasos por segundo); más rápido si es lejos, nunca más de 1.9 s (`CAMINAR_U_S`, `CAMINAR_MAX_S`). El lienzo y la cámara lo siguen |
| `saltar` | más lejos, u otro plano y otro lugar | se agacha detrás del subtítulo (0.3 s), el lienzo salta y gira en el acto, y se asoma (0.45 s) ya orientado |
| `rotulo` | de la figura al círculo o al revés | se agacha y el círculo aparece creciendo de 0.6 a 1 (0.25 s, `CRECE_S`); o el círculo se encoge (0.2 s, `ENCOGE_S`) y él se asoma |
| `fundido` | de un rótulo a otro, y con movimiento reducido todo lo que no es girar | se funde en 150 ms, cambia y vuelve |

- Ningún gesto de brazos arranca mientras camina, salta o se funde (el gesto de entrada espera como mucho 2 s). El brazo
  que apuntaba se suelta y vuelve a apuntar al llegar. Lo que llega mientras corre una transición reemplaza al destino
  si todavía no se ve; si no, queda pendiente. Si no se ve nada de él, el cambio va en el acto. Una transición sin
  cuadros se da por hecha a los 3 s.
- Si la ventana cambia durante un salto o un rótulo (abrir el chat cambia el ancho del iframe, girar el celular, pantalla
  completa), la transición se termina y se asoma en la vista nueva: nunca queda agachado con la frente asomando.
- **Entrar**: sube cuando el subtítulo terminó de aparecer (opacidad ≥ 0.98): de agachado a arriba sin pasarse, 0.8 s,
  con los brazos un poco detrás y un asentamiento de la columna; el saludo arranca 0.3 s antes de terminar de subir.
- **Salir**: si el subtítulo deja de verse o llega `quitar`, se agacha en el acto, sin subir antes (0.45 s); después del
  cierre o de «¿Preguntas?», con el «gracias» (un asentimiento) y la mano de `despedirse` que saluda mientras baja (0.6
  s). El vidrio del subtítulo lo espera hasta que bajó (`#pres.presentador-sale`): nunca queda el corte en el aire. Con
  muy pocos cuadros por segundo se esconde igual a los 750 ms (`FUERA_MS`). Si el subtítulo vuelve mientras se agacha, se
  asoma desde donde está.
- Cuánto se agacha: lo justo para que la cabeza, con el pelo y el contorno, quede bajo el corte (`(1 − yc)·alto + 0.12`).
- Si el subtítulo cambia de alto, el corte lo sigue en el acto y el cuerpo, en 0.15 s (la cabeza no salta).

### El rótulo

Cuando el atlas ocupa la pantalla (el simulador sísmico, el recorrido, el BIM, el parque), una figura detrás del
subtítulo taparía el marco y su barra de tiempo: queda solo la cara en un círculo (`rotuloDe`, `posRotulo`).

- **Escritorio**: bajo el panel, en la esquina de abajo a la derecha de su columna, si entre el panel y el pie del
  subtítulo cabe un círculo de al menos 88 px (113 a 900 de alto; si no entra entero, se achica). Si no cabe, va
  **acoplado** (84 px) al extremo izquierdo del subtítulo, centrado en su alto y nunca más alto que él: `#pres` lleva
  `.rotulo-acoplado` y `--pres-rotulo` (el diámetro + 10 px) y el subtítulo le hace lugar con su `padding`.
- **Celular**: acoplado a la derecha (64 px). **De lado**: del alto del subtítulo − 6 (44–64); con la ficha abierta, el
  círculo baja bajo ella (`techo`) y no pisa el renglón resaltado.
- En una seguidilla de escenas con el atlas, el círculo no cambia con cada panel: acoplado sigue acoplado y bajo el
  panel conserva su tamaño mientras quepa (dos círculos que difieren en menos de 8 px son el mismo). Entre escenas
  espera hasta 2.5 s el subtítulo del paso siguiente antes de encogerse.
- Los brazos no se ven: el gesto pedido se hace con la cara y la cabeza (`CARAS`, ver los gestos). Lo que se señala o se
  presenta es mirar el modelo: un rato cuando el aviso `atlas` dice que cargó (mientras dice «Cargando…», mira a la
  sala) y después un vistazo al empezar cada frase.
- CSS (propuesta.html): `.presentador.rotulo` va sobre el subtítulo (z-index 10), redondo, con el fondo del color del
  capítulo al 12 % sobre blanco (en el tema oscuro, al 22 % sobre #3a3330), un anillo de 3 px del color del capítulo y
  una sombra. La luz del círculo es la de siempre (no está sobre la maqueta).

### La pantalla chica

- **Celular parado** (390x844): el `busto` en el extremo derecho del subtítulo (219 px de alto; cabeza de ~70). Lo
  resaltado del panel está en la hoja de abajo y no se alcanza sin cruzar el subtítulo: `destacar` con un vistazo a la
  hoja al empezar y en cada frase (la cara no queda mirando abajo, que se ve desde arriba y con ceño). Presentando, los
  títulos de la maqueta se miden donde empieza y donde termina el viaje de la cámara.
- Con la cabeza de menos de 70 px los gestos de dedos se reemplazan por los que se leen por la silueta (`CHICOS`).
- **La hoja grande**: si la hoja tapa el subtítulo, él se agacha (no queda nada a la vista arriba).
- **Celular de lado** (844x390): siempre el rótulo acoplado (R1).
- **Tableta parada** (980x2120): el busto crece con el alto (`clamp(0.16·VH, 150, 360)`): cabeza de ~107 px.

### Movimiento reducido

Con `prefers-reduced-motion`: entra y sale sin animación; no camina, no se agacha para cambiar de lugar, no se acerca ni
salta: cada cambio de lugar o de plano se funde (la opacidad no es movimiento) y el cuerpo gira en el acto. El rótulo
aparece sin escala. Los muelles van sin pasarse (ζ = 1), sin vaivenes; `celebrar` no se agacha ni salta; los
sostenidos no hacen su acento. El saludo de bienvenida dura 1 s. Lo señalado no late: queda con el anillo de 3 px.

## En la presentación

Solo aparece dentro de la vista Presentación del panel (la pestaña del chat, la ventana del proyector y la pantalla en
off), cuando hay algo que explicar. Es un `<canvas>` transparente con su propio WebGL, dentro de `#pres` justo antes del
panel (mismo z-index 8: el panel y la ficha quedan encima; la leyenda, el HUD y el atlas, debajo; el subtítulo, encima),
sin tomar toques ni clics; solo dibuja mientras está a la vista. Nunca queda a la vista sin el subtítulo.

### Lo que le avisa el mando (`web/js/propuesta/mando.js`)

`narrar` (cada escena) trae lo de siempre —`n`, `de`, `senal`, `gesto`, `frases` (cuántas), `obra`— y lo que se está
explicando, todo JSON plano:

| Campo | Qué es |
|---|---|
| `rid`, `ms` | el recorrido y lo que dura la escena |
| `capitulo`, `paso` (desde 1), `tipo`, `lista` | dónde está y el tipo de paso (`portada`, `portadilla`, `componentes`, `componente`, `comparacion`, `metas`, `cronograma`, `texto`, `inmersion`); `lista`: cuántos ítems tiene |
| `cambio` | `'capitulo'`, `'paso'` o `null` (calculado antes de ir a la escena) |
| `panel` | si el panel queda a la vista |
| `resaltar` | `{tipo, n}`, `{tipo: 'especificacion', n, en}` o `{tipo: 'componente', id}`, o `null` |
| `visual` | lo visual de la escena, ya depurado (enfoque, cámara, aislar, sin, comparar, detalle…) |
| `atlas`, `modo` | la inmersión del atlas que queda a la vista y su modo (torre, pisos, recorrido, sismo, bim, parque, hoy, laboratorio) |
| `animar`, `simular`, `mover` | si anima; `{modelo: 'atlas' \| 'maqueta', controles}`; `{giro?, zoom?, elevacion?}` |
| `textos` | las frases: el gesto por omisión, la tónica del golpe y la boca |

Y los avisos de la escena, que se mandan solo si hay de qué (una capa visual sin `cajaObra` ni `luz` no recibe nada
nuevo) y que no despiertan al módulo si todavía no cargó (cargando, de cada uno se guarda el último):

| Aviso | Cuándo | Qué hace el presentador |
|---|---|---|
| `encuadre {rid, n, caja}` | después de aplicar lo visual (en la escena y en la orden `visual`) | `caja = {obra, rotulos, titulos, titulosAhora}` (px de la ventana, donde los deja la cámara final; `titulosAhora`: donde están al empezar el viaje), o `null` con atlas o con la cámara movida. Vuelve a puntuar el lugar y la palma va a la obra real |
| `atlas {rid, n, listo}` | cuando el modelo del atlas se asentó | el rótulo lo mira cuando cargó |
| `simulacion {rid, n, modelo, controles}` | con lo que el modelo aceptó | en la última frase reacciona 0.3 s después de empezarla (las cejas y un asentimiento; en el rótulo, aprobar con la cara) |
| `ambiente {hora, luz, intensidad, cielo, piso, hemi, oscuridad, sol, solFin}` | tras aplicar, tras simular, con cada frase, en la orden `visual`, con `explicar`, con `preparando` y al cambiar el tema | su luz sigue a la de la maqueta (ver «La luz») |

`alturaMano()` (síncrono; perezoso.js devuelve `null` si no cargó): mientras señala el panel o la ficha en el
escritorio, `{lado: 'panel' | 'ficha', y}` con la altura de su hombro. main.js (`resaltar` → `aLaMano`) desplaza el
contenedor del panel para que lo resaltado quede a esa altura (si queda entero a la vista); el brazo queda casi
horizontal y la punta pegada a la tarjeta. Si no, `scrollIntoView({block: 'nearest'})` como siempre.

### Lo que hace con cada orden

| Orden | El presentador |
|---|---|
| `escena` | Elige la vista con lo que se explica, se ubica, se orienta y arma el gesto de entrada (el pedido, adaptado a la vista, o el de la vista; ver «El tiempo de una escena») |
| `narracion {frase}` | Habla por las sílabas de la frase (sin voz, lo que tardaría en decirla: `decirS`, 0.058 s por carácter, de 1.2 a 16 s). Cada frase que sigue empieza mirando a la sala 1 s y después un vistazo de 0.8 s a lo que explica; señalando, dos toques de la mano en la palabra clave. Con `enumerar`, un dedo más por frase |
| `narracion {habla}` | La voz del panel empieza (`true`) o termina (`false`) de decir algo: abre o cierra la boca; con voz, al ritmo que tuvo la voz en las frases anteriores |
| `narracion {pausa}` | Calla, queda de frente y escucha (`escuchar` sostenido); al seguir, inspira, suelta las manos y vuelve al sostén |
| `narracion {preparando}` | `anfitrion` pensando (`pensar` sostenido); al terminar, su «¡ya está!» |
| `cierre {puntos}` | `cerca` (celular: `busto` ×1.15): cuenta el resumen con los dedos, un dedo al empezar cada punto (por las sílabas de «En resumen. p1. p2. p3»: `tiemposDelResumen`; con voz, al ritmo de la voz; si la voz termina antes, los dedos que falten) |
| `cierre {puntos: null}` | «¿Preguntas?»: `cerca`, `invitar` sostenido (los dedos llaman despacio, la mirada recorre la sala); a los 4.5 s las cejas arriba y cada 3.5–5 s un asentimiento sin soltar las manos |
| `explicar` | `anfitrion`, `explicar` y habla (recién subido, espera 1.1 s a terminar de subir) |
| `quitar_explicacion` | Se agacha detrás del subtítulo en el acto (después del cierre, despidiéndose); un cambio de paso dentro del plan no lo despide: el subtítulo vuelve y se asoma |
| `vista {presentador}` | `false` lo oculta en el acto y lo deja quieto; `true` lo vuelve a mostrar en la última escena que llegó (no en la que estaba al apagarlo), sin volver a saludar |

`habla` es la única orden del lado del panel: la vista envuelve la voz del reproductor y le avisa a la presentación cuándo
empieza y termina cada frase. No cambia los tiempos ni las fases del recorrido. Los planes del asistente y de los agentes
por MCP no traen nada nuevo: el presentador decide con lo que el mando ya sabe de cada escena.

El botón **Presentador** (en la barra de la pestaña, en la de la pantalla en off y entre los botones del proyector) lo
oculta o lo muestra; la preferencia queda en ese navegador (`yj_presentador`) y se le vuelve a mandar a la presentación
cada vez que carga. Si el navegador no puede crear el contexto WebGL (o lo pierde), no hay presentador y la presentación
sigue igual.

### El tiempo de una escena

1. Al llegar `narrar`: la vista y el giro en el acto; el lugar a los 150 ms o con el encuadre.
2. El gesto de entrada espera la primera frase (o 0.8 s), a que termine la transición y, si señala lo resaltado, a que
   el `.foco` aparezca y deje de moverse (dos cuadros iguales, o uno con 100 ms; si se sigue moviendo, a los 2 s). Si a
   los 1.2 s de la escena (1.3 s después de aplicar lo visual) no hay `.foco`, sigue con la regla siguiente sin él.
3. Su golpe cae en la tónica de la palabra clave de la primera frase (la cifra, lo que sigue a «esta es», lo
   resaltado): arranca 0.4 s antes, nunca más de 2 s después de empezar a decirla. Cuando el dedo llega, lo resaltado
   late 0.9 s (`.foco.senalado`) y la cabeza vuelve a la sala al segundo (la mano sigue).
4. `senalar` y `presentar` se sostienen la primera frase (al menos 2.5 s; con barrido, 2.8 s); después, el **sostén**
   hasta la escena siguiente: la mano baja y abierta hacia lo que explica (`indicar`; desde lejos, hacia el borde del
   panel), mirando a la sala (o a la obra si la presenta; si la cámara viaja o la maqueta simula, la sigue con la mirada
   y un vistazo a la sala cada tanto). El anfitrión, el rótulo y el busto que mira la hoja, en la casa (la de hablar si
   habla). Lo señalado muy arriba del hombro sigue con el índice.
5. Sin un gesto pedido, el anfitrión hace el que pide el texto (`gestoDelTexto`): una pregunta → `preguntar`;
   «juntos» → `juntos`; «crece», «aumenta» → `crecer`; una cifra → `detalle`. («más» y «sube» no cuentan: están en casi
   todo.)
6. Presentando la portada, la palma barre los pines de la maqueta del lado donde hay más; en el cronograma, los años en
   diagonal, de 2027 a 2032 (`presentar` con `hasta`, `barridoDe`).

### Para medirlo (`estado()` y `?qa`)

`estado()` devuelve lo del animador (gesto, sostenido, hablando, caminando, entrando, rumbo, agachado, peso, casa,
mirada, pies, ritmo, variante, chica, boca, `cara`: el giro real de la cabeza…) y lo del presentador: `arriba`,
`saliendo`, `cuerpoY`, `lienzo`, `vista`, `plano`, `lado`, `regla`, `gestoVista`, `fase` (saludo, espera, gesto, sosten,
cierre, listo), `frente`, `lugar {x, cambios, razon, costo, hacia}`, `escala`, `pxAlto`, `cx`, `objetivo`, `transicion`,
`trans {tipo, fase, ms}`, `circulo {k, op, modo, lado}`, `acoplado`, `desfase`, `recorte`, `dpr`, `ancla`,
`redimensiones`, `msCuadro` (la media de los últimos 30 cuadros dibujados, sin los 3 primeros), `cuadros`, `luz`,
`detalle {pxCabeza, nivel}`, `escena`, `avisos`, `prog {t, frase0, encuadre, iguales, sinFoco, lejos, sosten, dedos,
barrido}` y, calculados solo si se leen, `cajas {figura, cabeza}` (px de la ventana, arriba del corte), `punta` (la del
índice que apunta) y `apunta`.

Con `?qa` en la dirección de la página: `window.__qaPresentador` (la API entera) con `rastrear(true)`/`rastrear(false)`
(anota cada cuadro: la cabeza en px, el lienzo, la transición, el gesto, la fase) y, del lado del mando,
`window.__qaMando = {avisos, visual, perezoso}` (cada aviso que recibe el presentador).

## Animación

`animador.js` arma en cada cuadro una pose por capas y cada articulación la sigue con su muelle: así salen solos el
arrastre del codo y de la muñeca, el sobrepaso y el asentamiento, y ningún cambio da un salto. Sin DOM ni reloj propio:
`actualizar(dt)` avanza (el presentador y el taller lo llaman en cada cuadro; las pruebas, con el dt que quieran).

### Muelles y retrasos

- `MUELLES`: `[ω, ζ]` por familia, sobre cuaterniones (con velocidad angular propia, en pasos de a lo sumo 1/120 s):
  cadera [6, 1], columna y pecho [8, 0.9], cuello [9, 0.85], cabeza [10, 0.8], hombro [12, 0.6], codo [14, 0.6], muñeca
  [18, 0.6], piernas [14, 1], dedos [22, 0.7], rumbo [7, 1]. Cuanto más lejos del centro, más rápido y más suelto. Con
  movimiento reducido, ζ = 1 en todos.
- `RETRASO`: el gesto nace en el cuerpo y termina en la mano: cadera −0.08 s, columna y pecho −0.06, hombro 0, codo
  0.08, muñeca 0.19, dedos 0.2.
- `CURVAS` de las claves: `suave`, `anticipa` (retrocede ~0.16 s antes de ir), `golpe`, `sosten` y `lineal`.

### El clip (el formato de un gesto)

Cada gesto es una función que devuelve su clip. Lo de siempre: `dur`, `pose` (ángulos por articulación; el brazo
derecho es el espejo del izquierdo), `manos` (formas de `MANOS` o sus cinco números), `entra`, `sale`, `sostener`,
`osc`. Lo ampliado:

- `claves: [[t, pose, curva]]` encadenadas; `retraso` propio por articulación o familia (y `dedosSale`).
- `cuerpo {columna, pecho, cadera, peso, alto}`: se suma al reposo (`peso` mueve el contrapposto, `alto` la pelvis).
- `golpes` (impulsos después del muelle, con `sosten`: se quedan en el pico), `golpesCallado` (solo callado) y `batuta`
  (el habla golpea con el brazo del gesto); `vaiven` con `decae`, `azar` y `cadena` (la articulación siguiente 85 ms
  después).
- `cara`: `cejas`, `cejasI`/`cejasD`, `abrir`, `sonrisa`, `labios`, `ancho`, `entrecierra`, `ceno`, `guino`,
  `duchenne`, `cierra` (los ojos), `ojos`. Cualquier valor de la cara o del cuerpo puede ser una línea en el tiempo
  `[[t, valor], …]`.
- `mirar` y `mirada`: el plan de la mirada (ver abajo); `resto` (mirando a la sala, la cara queda un poco hacia el
  objetivo); `deriva {amp, cada}` (la mirada recorre la sala); `cambiaMirada` (con cada `seguir`, al otro lado).
- Apuntar: `punto` (el hombro se reapunta en cada cuadro para que la recta del hombro a la punta del índice caiga en él,
  con una sola solución continua), `hasta` (un barrido de un punto a otro), `abajo`/`arriba`.
- `acento {cada, golpes}` y `relajada` (los sostenidos), `parpadeos [t]`, `salto {t, dur, alto}`, `alSoltar` (un clip
  corto al soltarlo: el «¡ya está!» de pensar), `alSeguir` (el golpe del número nuevo de enumerar y contar).

Un gesto nuevo entra desde lo que pedía el anterior, sin pasar por el reposo; lo que no usa vuelve a la casa mientras
entra. Si el mismo brazo cambia de lado, pasa por delante del pecho. Al terminar (o con `detenerGesto`) sale a la casa,
la de hablar si sigue hablando; un sostenido sale suave desde ese momento.

### El reposo y la casa

- **La casa**: las manos juntas al frente, a la altura del ombligo, la izquierda algo más alta sobre la derecha
  (`REPOSO`): arriba del corte del americano. Cada 10–20 s pasa un rato a `muneca` (la derecha toma la muñeca
  izquierda); con la figura entera, a veces a `sueltos`. Con el plano medio las manos suben un poco (`ALZAR_MEDIO`):
  quedan enteras sobre el subtítulo, sin muñones (no más: se leerían como brazos cruzados).
- **Vivo**: el peso cambia de pierna cada 6–10 s (contrapposto con anticipación), la respiración es asimétrica (1.6 s
  inspira, 2.4 s espira), la cabeza nunca está del todo quieta (ruido de Perlin), los ojos saltan cada 0.8–2.5 s y
  parpadea (cierra en 60 ms, abre en 120; a veces doble, y uno más en los giros grandes de la mirada).
- **Los pies** quedan apoyados en el mundo: las piernas los alcanzan con IK de dos huesos; caminando, el pie de atrás
  da el paso, cae media zancada delante de donde estará el cuerpo y no patina. Al final un paso junta los pies.

### El habla desde el texto

- `silabear`, `tonicaDe` y `planHabla(texto, {claves, dura})` (exportadas, puras): las sílabas del español (núcleos con
  hiato, la u muda de qu/gu, los grupos que no se separan), la tónica por tilde o terminación, las palabras átonas sin
  acento. Cada carácter dura `DECIR_S` (0.058 s); pausas con la boca cerrada: coma 0.16 s, punto 0.28 s.
- **Visemas**: la p, la b, la m y la v cierran los labios el primer 42 % de la sílaba; la a abre 0.55; la e y la i, 0.35
  y 0.3, más anchas; la o y la u, redondas (0.66 y 0.6 de ancho, con la sonrisa aflojada). La tónica abre ×1.3, con un
  tope de 0.75 (nunca grita). Entre sílabas la boca mezcla 35 ms.
- `hablar(seg | true, {texto, claves})`: con voz, al `ritmo` que tuvo la voz en la frase anterior (acotado a 0.7–1.4;
  `callar({dicha})` lo aprende, salvo de una frase cortada); si la voz sigue después del texto, sílabas al azar.
- **La casa de hablar**: asimétrica, la mano que manda más alta (la derecha, salvo que el gesto la ocupe), con una
  forma que cambia cada 3–4 golpes (la palma arriba, de canto, el índice con el pulgar).
- **Los golpes**: en la tónica de las palabras clave (cifras, palabras largas, nombres, lo que sigue a «esta es» o
  «aquí», lo resaltado), al menos 0.5 s entre uno y otro: la mano baja, los dedos se cierran un poco, la cabeza cabecea,
  las cejas suben y los ojos se entrecierran. La mirada deriva por la sala; en las preguntas, ladea; al terminar, asiente.

### La mirada y la apertura

Los ojos saltan en ~40 ms; la cabeza y el cuello los siguen 0.1 s después y la columna y la cadera 0.2 s después
(cadera 0.12, columna 0.18, cuello 0.3, cabeza 0.4 del giro). La cara nunca se aparta de la sala más que la `apertura`
de la vista: los ojos hacen el resto. Para mirar algo alto, la cabeza se alza a lo sumo 0.13 rad (`CABEZA_ARRIBA`): no
se pierde la mandíbula. Los planes: `vistazo` (mira el punto 0.8 s, vuelve a la sala y otro vistazo cada 2–3 s; el de
omisión), `sigue` (la obra mientras viaja la cámara), `sala`, `recorre` (mirar la maqueta: salta entre puntos de la
obra, asiente y vuelve a la sala, en ciclo). `mirarSala(seg)` y `mirarA(punto)` los pisan un rato.

### La cara

Cejas por lado, párpados que se entrecierran (y el de arriba que baja al mirar abajo), los ojos de Duchenne (con la
sonrisa amplia y los dientes), el guiño (también con movimiento reducido) y los ojos que se cierran de sonrisa
(`cierra`). Callado, la sonrisa de la foto: amplia, con los labios entreabiertos y la fila de los dientes de arriba
(`LABIOS_REPOSO` 0.38); los labios cerrados quedan para los gestos que los piden (pensar, escuchar, el corazón, negar,
calmar, preguntar, el detalle, construir) y para la p, la b y la m.

### Sostenidos, tamaño y variantes

- **Sostenidos vivos** (`gesto(nombre, {sostener: true})`): se mueven apenas (±0.03 rad), respiran más, asienten
  despacio cada 2.5–4 s, hacen su `acento` cada 4–6 s (pensar, un toque en la mejilla; invitar, los dedos que llaman;
  escuchar, ladea; indicar, dos toques de la muñeca: `acentuar()` lo hace ya) y a los 6–7 s aflojan (`relajada`).
- **Tamaño** (`tamano(pxAlto, {celular})`): con la cabeza de menos de 70 px (`chica`), `contar` y `enumerar` van con la
  mano abierta en un lugar por número delante del pecho, dentro del ancho de los hombros (la otra quieta abajo); `detalle` es
  un golpe con la mano alta; `aprobar`, el pulgar más alto y un asentimiento (`CHICOS`).
- **Variantes** (`VARIANTES`): explicar 3, presentar 3, asentir 2, destacar 2, mirar_maqueta 2, crecer 2, grande 2,
  negar 2. Cada vez una distinta de las dos últimas de ese gesto (`o.variante` la fija).
- `reaccionar(v)`: las cejas arriba y un asentimiento sin dejar el gesto; `alzarCejas(v)`.

## Los gestos

El asistente puede pedir uno en cada paso del plan (`gesto`); son los de `GESTOS` en `admin/app/recorrido.py` (que le
llegan al modelo con el guion, con lo que expresa cada uno) y de `GESTOS_AGENTE` en `animador.js`. Ninguno pasa por la
T, ninguno mete una mano en el cuerpo y la mano que lo hace queda arriba del corte del americano.

| Gesto | Qué hace | Para |
|---|---|---|
| `saludar` | El brazo sube en arco por delante (con un amague) hasta la mano abierta al costado de la cabeza (de cerca, a la altura de la cara), la palma a la sala desde el primer momento; el antebrazo va y viene tres veces, cada vez menos, con la muñeca detrás. «¡Hola!», la sonrisa con los ojos, la cabeza ladeada y un asentimiento; el pecho gira hacia la mano y el peso cambia de pierna. Corto (1.2 s), una sola ida y vuelta | empezar |
| `senalar` | Mira lo resaltado y prepara (la mano frente al pecho); en el golpe estira el brazo hasta que la recta del hombro a la punta del índice cae en lo que señala, pasa un poco y asienta. Las cejas y la boca de «¡esta!», el torso abierto y el peso en ese pie; hacia abajo, el codo más doblado. Sostenido, dos toques del índice cada tanto | «esta es…» |
| `presentar` | La palma sale del centro del pecho y se abre en arco hacia lo que presenta, la muñeca atrás y los dedos en abanico; nunca sube más de ~11° sobre el hombro (la palma mira la obra, no se lee como mano levantada). Mira la obra 0.7 s y vuelve a la sala. Con `hasta`, barre de un punto al otro en 1.2 s. Variantes: amplio, corto, barrido chico | mostrar una obra |
| `mostrar_panel` | Es `senalar` hacia el dato (o `presentar` sin punto) con las cejas más arriba, la boca de «fíjense» y dos toques en el golpe | un dato del panel |
| `mirar_maqueta` | Mira la obra saltando entre puntos de ella, asiente a la mitad y a los 1.2 s vuelve a la sala, en ciclo; el cuerpo en 3/4 y la mano de ese lado abierta y baja hacia la maqueta (variante: la palma arriba, «se los muestro»). Sin un punto, las manos en la casa | dejar que la sala mire |
| `explicar` | Las dos manos abiertas adelante, la derecha más alta, que golpean en las palabras que pesan (hablando, en las tónicas; la otra mano golpea cada 2–3); la palma pasa de arriba a de canto, «ordenando». Variantes: dos manos, una (la otra abajo), de canto | explicar |
| `destacar` | La mano va atrás y el índice sube adelante, frente al pecho; en la palabra, un golpe adelante con la cabeza y las cejas al máximo. Variantes: el índice, la mano de canto que corta | «esto es clave» |
| `comparar` | Las manos al centro; «hoy», la izquierda afuera y abajo con la cara seria (los labios juntos); «con el proyecto», la derecha al otro lado y más alta con la palma arriba y la sonrisa amplia. El torso y el peso van con cada una; las manos no se cruzan | hoy y con el proyecto, antes y después |
| `enumerar` | La izquierda frente al pecho cuenta (los dedos estirados en abanico: se lee el 2 en V y el 3), la derecha la acompaña abajo con la palma arriba sin taparla; con cada frase, un dedo más y un golpe | una lista |
| `crecer` | Las dos palmas adelante y bajas; una sube acelerando (o en tres escalones), con el codo doblado y la palma arriba, hasta la altura del hombro, y la otra se queda. Sube en puntas, cejas arriba y la boca se abre en la cima. Nunca el brazo estirado en alto ni la palma abajo sobre el hombro | crece, aumenta, mejora |
| `grande` | Las manos juntas frente al pecho se abren en arco adelante y afuera, bajo la horizontal (nunca en T), las palmas adentro; la boca redonda, «¡así de grande!», un pulso y baja. Variantes: dos manos, una hacia la maqueta | una obra grande |
| `detalle` | La mano en «ok» (índice y pulgar) al costado del mentón, sin tapar la boca, la palma a la sala; dos toques cortos; los ojos se entrecierran | un detalle preciso |
| `construir` | La palma izquierda arriba frente al ombligo y el puño derecho que la golpea tres veces como un martillo (a 2 Hz, en látigo); la palma cede, la cabeza asiente, la cara decidida | lo que se construye |
| `pensar` | La mano a la barbilla (el índice en la mejilla, el pulgar bajo el mentón) y el otro brazo cruzado por delante del vientre, con el codo afuera, sosteniendo el codo; la cabeza ladeada, los ojos arriba saltando, las cejas desparejas y la boca de lado, cerrada. Sostenido, un toque en la mejilla cada 1.2–2 s; al soltarlo, «¡ya está!»: la mano se abre a la sala | «¿por qué?», preparando |
| `preguntar` | Una palma adelante y arriba hacia la sala, el torso adelante, la cabeza ladeada, las cejas desparejas; espera (un parpadeo) y asiente apenas | una pregunta a la sala |
| `asentir` | Dos o tres asentimientos que decrecen (bajan rápido, suben despacio), los ojos que sonríen y la sonrisa que crece. Variantes: tres, dos más hondos | sí |
| `negar` | El índice frente al pecho que se menea desde la muñeca y la cabeza que niega a la mitad de esa frecuencia; boca cerrada con una sonrisa leve al final, nunca el ceño con los dientes. Variante: la mano plana que corta hacia afuera | eso no |
| `calmar` | Las palmas abajo y hacia la sala delante del vientre; dos presiones, el pecho que exhala y un asentimiento lento | «tranquilos, está previsto» |
| `aprobar` | El pulgar de canto a la altura del pecho, que llega de golpe y rebota; un guiño y la sonrisa con los dientes | listo, aprobado |
| `celebrar` | Se agacha un poco con los puños al pecho, los puños suben por delante y salta; aterriza con un rebote y bombea dos veces; «¡sí!» con los ojos cerrados de sonrisa | un logro |
| `aplaudir` | Las palmas enfrentadas (la izquierda más alta) se tocan seis veces a 3.5 por segundo, los dedos que se abren en cada choque, la sonrisa con los dientes | un reconocimiento |
| `juntos` | Abre las palmas hacia la sala, las trae y entrelaza los dedos frente al pecho; dos sacudidas, asiente, la sonrisa amplia y los ojos que sonríen | «trabajemos juntos» |
| `corazon` | La mano derecha plana sobre el pectoral izquierdo, apoyada con presión; la cabeza baja y se ladea, los ojos se cierran un momento, una respiración marcada | un compromiso |
| `invitar` | Los brazos bajos y adelante, las palmas arriba hacia la sala (nunca en T), el pecho abierto, la cabeza ladeada y un asentimiento. Sostenido, los dedos llaman despacio y la mirada recorre la sala. En el plano medio, a la altura del pecho | bienvenida o «¿preguntas?» |
| `despedirse` | La mano abierta sube enseguida al costado de la cabeza y va y viene dos veces mientras la cabeza asiente su «gracias»; la mano sigue abierta al bajar. En la salida, mientras se agacha | terminar |

Los que hace solo el presentador:

| Automático | Qué hace |
|---|---|
| `indicar` | El sostén: la mano abierta y baja hacia lo que se explica (desde lejos, hacia el borde del panel a la altura del hombro), la palma a la sala, mientras la otra habla; dos toques de la muñeca en cada frase que sigue |
| `contar` | El resumen del cierre: como enumerar (la izquierda frente al pecho cuenta, la derecha acompaña abajo con la palma arriba, lejos del reloj); un dedo al empezar cada punto, un cabeceo y la mirada que cambia de lado |
| `escuchar` | En pausa: las manos entrelazadas a la cintura (en el plano medio, más arriba), el peso en una pierna, la cabeza ladeada y la sonrisa cerrada; al soltarlo, inspira |
| El cambio de capítulo | Mira el panel 0.6 s con las cejas arriba antes del gesto |
| `reaccionar` | Tras una simulación, en la última frase: las cejas arriba y un asentimiento |

En el **rótulo**, `gesto(nombre, {soloCara: true})` hace el gesto con la cara y la cabeza (`CARAS`, 18 gestos): aprobar
asiente con un guiño; celebrar, las cejas y la sonrisa grande; pensar ladea la cabeza y mira arriba; calmar asiente
despacio; negar niega con la cabeza; saludar y despedirse, las cejas, la sonrisa y un ladeo; preguntar, ladeada con las
cejas desparejas; destacar, un cabeceo; grande y crecer, las cejas y la boca redonda; juntos y aplaudir, asienten
sonriendo; corazón, la cabeza baja y los ojos que se cierran; invitar, las cejas y un ladeo; escuchar; asentir; contar,
un cabeceo por punto. Los demás (señalar, presentar, mirar la maqueta) son mirar el modelo.

### Cómo lo pide el asistente

Cada paso del plan (`presentacion`, op `recorrido`) puede traer `"gesto": "comparar"`. Llega con tildes o en otras
palabras («señalar», «pulgar», «contar», «aplauso») y se resuelve al nombre; uno que no existe se descarta con un aviso
y el plan corre igual. Va al recorrido guardado (`recorrido.validar` lo revisa), a la tarjeta del chat (el chip «El
presentador hace un gesto»), al reproductor y a la orden `escena` de la presentación, que se lo pasa al presentador. El
gesto pedido se adapta a la vista (`senalar`, `presentar` y `mostrar_panel` apuntan al objetivo de la vista; en el
rótulo, con la cara; en el busto chico, `CHICOS`). Un paso sin `gesto` (o un plan de antes, o la presentación
automática) deja que la vista elija.

## El diseño en la página

- **La luz** sigue a la de la maqueta (`lucesDe`, exportada y pura; el aviso `ambiente`). La principal viene del lado
  del sol donde termina el viaje de la cámara (`lado = clamp(solFin.x / 0.25, −1, 1)`), mitad blanca y mitad del color
  del sol, con la intensidad del sol (con un piso); el relleno, del otro lado; la hemisférica toma un poco del cielo y
  la mitad del piso. `oscuridad` (0 de día, 0.5 al atardecer —el tema oscuro—, 1 de noche) mezcla sin saltos: al
  atardecer el relleno se entibia (#ffd9b0); de noche la principal y la hemisférica bajan a ×0.54, la luna y el cielo
  tiñen poco, la principal suma un tibio, el relleno sube a 0.85 y entra un contraluz frío suave (0.25) que separa el
  pelo del fondo: la cara baja ~27 % de luz y sigue siendo piel. Si se ve, la luz nueva llega en 0.6 s; si no, en el
  acto. Lo que no recibe luz (los ojos, los dientes, las cejas, los labios, el logo) se tiñe en proporción (el uniforme
  `personaje.tinte`). El rótulo usa la luz de siempre. Sin aviso (el taller), las de siempre.
- **La cara a tamaño chico** (`personaje.cara.nivel(pxCabeza)`, que el presentador llama con `0.312·pxAlto` cuando
  cambia el px): con la cabeza de 100 px o menos (k = 1; mezcla hasta 120 px) las cejas se engrosan hasta ×1.7 y se
  oscurecen, las pestañas de arriba ×1.5, el ojo 25 % más abierto, el iris y el brillo un 10 % más grandes y el
  pliegue de la sonrisa más marcado. En el americano a 1440x900 (101 px), el busto del celular y el rótulo, nivel
  chico; en `cerca` (140 px), el normal.
- **Los labios** (`boca.poner({abrir, ancho, sonrisa, labios})`): 0 es la sonrisa de la foto, con los dientes; 1, la
  sonrisa cerrada con la línea de los labios (sin el hondo ni los dientes, la boca un 7 % más angosta).
- **El filo de calcomanía** (propuesta.html): `.presentador:not(.rotulo)` lleva dos `drop-shadow` crema de 1 px (0.6 px
  desde 2dppx) y una sombra suave abajo: separa el pelo y la polo de la maqueta clara u oscura.
- **La sombra del atril**: lo que queda pegado al corte (los 0.12 del mundo sobre el borde del subtítulo) se oscurece
  hasta un 20 %, en degradé (un `onBeforeCompile` en los MeshToonMaterial, con el uniforme `corteAtril`).
- **El peso de línea**: el contorno mide 1.5 px CSS en todas las vistas (1.2 en el círculo chico).

## El taller

`presentador.html` (en `site/`, al lado del atlas y la propuesta; no se indexa) muestra el personaje solo, de cuerpo
entero y con la luz de siempre:

- arrastrar gira la vista y la rueda la acerca;
- un clic hace que señale ese punto (con Mayúsculas, que lo presente con la palma);
- las flechas ← → lo hacen caminar;
- los botones disparan cada gesto de la serie (con su nombre en el plan en el title), la entrada y la salida;
- **Decir** le mueve la boca por las sílabas del texto lo que tardaría en decirlo (con los golpes en sus palabras clave)
  y lo muestra abajo, como el subtítulo (la voz de verdad es la del panel, en el recorrido narrado); **Mover la boca**
  habla sin parar hasta apagarlo.

## Cómo cambiarlo

- Colores: `COLORES` en `personaje.js` (piel, pelo, polo, jean, contornos…). El volumen de la piel lo da `rampaPiel`
  (cuánto oscurece cada tono y el tinte de las sombras); las sombras y el calor pintados, los discos de `sombra` al
  principio de `construirCara`.
- Forma de la cara: `deformarCabeza` (la superelipse de frente, las sienes, el largo de la mandíbula y el mentón) y
  `RELIEVE` (los bultos y hundidos de la cara), el pelo (en `pelo`: la línea del pelo `lineaBase`/`limite`, el grueso
  del casco por meridianos `deLado`/`deFrente`/`deAtras`, sus colores en `tinte` y en `COLORES.pelo*`) y las medidas de
  ojos, cejas, orejas, nariz y boca en `construirCara` y `crearBoca`; el nivel chico, en `cara.nivel`. La forma de la
  oreja está en `ORE`; en `construirCara` solo se ubica y se gira.
- El cuerpo y la ropa: el torso es un torno (`perfil`) que `anchoTorso` y `fondoTorso` ensanchan y aplanan; las mismas
  funciones (`enTorso`, `zTorso`, `fueraDelTorso`, `sobreTorso`) sirven para apoyar cosas sobre la polo sin lanzar
  rayos. `apartarPolo` empuja la parte de abajo de la polo fuera de los muslos; `colgar` apunta los cabos de la
  manilla hacia abajo; el cuello de la polo se arma en `cuelloDeLaPolo` (`BORDE`, `ABRE_CUELLO`); las manos, con
  `ESCALA_MANO`. La cabeza va al 0,94 (`craneo.scale`).
- Las vistas: `PLANOS`, `VISTAS`, las reglas de `elegirVista`, los pesos del puntaje (`PESOS`), `LLEGA_PX`,
  `LEJOS_PX`, `ALTO_PX`, `TITULO_TAPADO` y `ENVERGADURA` en `vistas.js`; los tiempos de la escena y de las
  transiciones (`CAMINAR_U_S`, `ACERCAR_MS`, `CRECE_S`, `SOSTEN_MS`, `MIRAR_MS`…) al principio de `presentador.js`.
- Gestos: `GESTOS` en `animador.js`. Un gesto nuevo es una función que devuelve su clip (pose o claves, manos, cuerpo,
  cara, golpes, vaivenes); las poses de brazos se buscaron con el personaje para que las manos queden donde dicen, sin
  entrar en el cuerpo (`POSE`). Para que el asistente lo pueda pedir, va también en `GESTOS` de `admin/app/recorrido.py`
  (con lo que expresa), en `GESTOS_AGENTE` y en las listas de `mando.js` y del puente
  (`admin/web/js/agente-presentacion.js`): una prueba las compara. Si cambia lo que abre los brazos, hay que revisar su
  `ENVERGADURA`. Si tiene cara para el rótulo, va en `CARAS`. El taller lo muestra solo.
- Lo que hace en cada orden: los métodos de `crearPresentador` en `presentador.js`.

## Pruebas

`admin/tests/test_presentador.py`, con Node (three desde web/vendor, sin WebGL):

- `test_el_personaje_y_el_animador_con_node`: las medidas del personaje, cada gesto entra y sale (o se sostiene), nada
  queda sin número, hablar abre y callar cierra, el lado del brazo, entrar y salir.
- `test_detras_del_subtitulo_se_agacha_se_asoma_y_camina`: la entrada sin pasarse, agacharse sin subir antes, la salida
  con el «gracias», asomarse desde donde esté, caminar a la velocidad pedida, todo en el acto con movimiento reducido.
- `test_el_diseno_del_personaje_y_la_luz`: las medidas, los labios y el nivel de la cara sin NaN, `lucesDe` de día, al
  atardecer y de noche sin saltos.
- `test_los_gestos_de_mostrar_y_explicar` y `test_los_gestos_de_reaccionar_el_lema_y_el_cierre`: el criterio medido de
  cada gesto (sin T, sin penetrar, la mano arriba del corte, señalar apunta justo…).
- `test_los_gestos_no_se_leen_mal`: ningún brazo en alto con la mano plana, ningún puño en alto al saludar, ningún
  antebrazo dentro del torso, el índice nunca en el reloj, el brazo que apunta sin saltos, callado la sonrisa con los
  dientes, las manos del plano medio sobre el corte, la cabeza que no se alza de más, contar dentro del busto.
- `test_elegir_vista`: la vista, el lado y la regla de cada caso, el lugar (alcance, histéresis, «poco», desde lejos,
  los títulos y las cajas de los rótulos con las cajas reales de salud/2), las transiciones, el rótulo, `domManda`.
- `test_desde_lejos_la_mano_abierta_hacia_el_panel`, `test_el_vidrio_espera_al_presentador_que_baja`.
- `test_la_carga_perezosa`, `test_el_mando_le_avisa_al_presentador` (el `narrar` ampliado y los avisos),
  `test_la_vista_del_panel_le_da_la_boca_y_el_boton`, `test_el_presentador_solo_usa_lo_que_el_sitio_publica`.
- `test_los_giros_suaves_son_los_mismos` y las de las listas de gestos (servidor, puente, mando y animador; el guion y la
  tarjeta).

## Lo que falta ver en un equipo real

Todo se midió con WebGL por software (SwiftShader, 1–7 cuadros por segundo): las posiciones y las vistas en estado
estable se verificaron en la página real; los tiempos finos (el golpe en la tónica, los dedos del cierre, caminar, el
saludo) se midieron en Node, donde caen en su lugar. Conviene mirarlos en un equipo con GPU y en un teléfono. Quedan
además, menores: en el celular el busto no indica hacia abajo lo resaltado de la hoja (lo mira y vuelve a la sala); las
palmas abiertas de cerca todavía se leen algo gruesas; el borde de atrás del cuello de la polo puede salir cortado
1–2 px en algún ángulo; a 1920x1080 el subtítulo queda lejos del panel y lo resaltado del panel se señala desde lejos,
con la mano abierta.
