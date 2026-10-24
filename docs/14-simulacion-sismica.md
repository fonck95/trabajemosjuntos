# 14 · Simulación sísmica de la torre del hospital

**Qué le pasaría a la torre de servicios de primer nivel de Yondó en un sismo, calculado paso a paso: un movimiento del suelo sintetizado con la física de la fuente y del camino, y un modelo no lineal de la estructura de prediseño que se integra en el tiempo. En la pantalla no hay animaciones: todo lo que se mueve es el resultado del cálculo en ese instante.**

> Estado: **esqueleto de la ola 1** de la especificación de integración (`data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md`, secciones 7, 8 y 11.3), con fecha de corte del 24 de octubre de 2026. El texto que no depende de los resultados del motor ya está escrito; lo que se marca **«[CIFRA]»** se llena en la ola 2 con las salidas de `scripts/sismo/estructura_torre.py`, del motor (`web/js/sismo/`) con Δt = 0,005 s y de `scripts/sismo/validar_opensees.py`, y lo comprueba `scripts/torre/verificar_cifras_docs.py`.
>
> Cada cifra dice si es un **dato oficial** (copiado de la fuente), un **cálculo propio** (operación sobre datos citados, con el método a la vista) o una **estimación** (supuesto con rango, por confirmar). Lo que no se pudo leer en la fuente dice **por confirmar**: las páginas `.gov.co` no abrieron desde el entorno de investigación (23-oct-2026) y los numerales de la NSR-10 se citan como los registra el repositorio.

**Modelo de prediseño (sin estudio de suelos ni diseño estructural firmado). Idealización estándar de ingeniería: diafragmas rígidos, pórticos planos, rótulas concentradas, núcleos como muros planos con aletas efectivas (su resistencia no cambia con la carga axial del sismo), sin interacción suelo-estructura, sin componente vertical, sin degradación de resistencia. Amortiguamiento del 5 % proporcional a la masa y a la rigidez inicial de la parte elástica de los elementos (las rótulas no amortiguan). Los colores comparan con la resistencia esperada y con el límite de ocupación inmediata de un hospital. El contexto sísmico (nido de Bucaramanga, fallas cercanas) está por confirmar con el Servicio Geológico Colombiano. Validado contra soluciones exactas y contra OpenSees (ver documento 14).**

## En pocas palabras

- La torre es una **edificación indispensable** (grupo de uso IV de la NSR-10): tiene que seguir funcionando después de un sismo fuerte y quedar **sin daño** en uno frecuente. El simulador muestra por qué el prediseño cumple o dónde no.
- El movimiento del suelo se fabrica con el **método estocástico de Boore (2003)**: magnitud de momento Mw, profundidad, distancia y suelo cambian el sismo de forma continua. La magnitud que se mueve es **Mw**, no la «escala de Richter», que se satura en sismos grandes.
- La estructura es un **modelo pseudotridimensional no lineal** (Wilson y Dovey, 1972) con rótulas de Giberson y propiedades esperadas del concreto y del acero; se integra con Newmark y Newton-Raphson, con P-Delta y con el balance de energía cerrado.
- En el escenario por defecto (nido de Bucaramanga, como el 10-mar-2015), la torre [CIFRA: deriva vectorial máxima y si queda en el rango elástico]. En el sismo local hipotético, [CIFRA: deriva máxima, rótulas y equipos que deslizan].
- El motor se validó contra soluciones exactas (22 pruebas) y contra OpenSees 3.8 con la misma idealización: [CIFRA: errores de períodos, deriva y cortante basal].

## 1. Para qué sirve y qué no es

**Para qué sirve.** Para ver, con la física a la vista, cómo responde el prediseño de la torre a sismos posibles en Yondó: cuánto se desplaza cada piso, cuánto se tuerce por tener los núcleos al oriente, qué columnas, vigas y muros se acercan a su resistencia, dónde se formarían rótulas plásticas, qué equipos sueltos deslizarían o empezarían a balancearse, y cómo se reparte la energía que entra. Sirve para discutir el diseño con la comunidad, la E.S.E. y el diseñador estructural, y para explicar por qué la NSR-10 pide lo que pide a un hospital.

**Qué no es.** No es el diseño estructural ni lo reemplaza: el diseño lo firma un ingeniero con matrícula, con estudio de suelos y con el análisis que exige la NSR-10 (Título A). No es una amenaza sísmica oficial: los escenarios son ilustrativos y su contexto (nido de Bucaramanga, fallas cercanas) está **por confirmar** con el Servicio Geológico Colombiano. No es una animación: el deslizador recorre los pasos que el motor calculó.

**Dónde corre.** En el navegador, en un trabajador en segundo plano (Web Worker); si no hay trabajador, la misma lógica corre en el hilo principal por tramos. El mismo escenario con la misma semilla da el mismo resultado en cualquier dispositivo (la síntesis es siempre con Δt = 0,005 s).

## 2. Richter y Mw: qué magnitud se mueve

La «escala de Richter» (magnitud local ML, 1935) mide la amplitud que marca un sismógrafo Wood-Anderson a cierta distancia. Funciona bien en sismos pequeños y cercanos, pero **se satura** por encima de magnitud 6,5 a 7: sismos muy distintos marcan casi lo mismo, porque el aparato solo «ve» ondas de alrededor de un segundo. Hoy el Servicio Geológico Colombiano y el USGS reportan los sismos grandes en **magnitud de momento Mw**, que sale del momento sísmico M0 = μ·A·D (rigidez de la roca × área de la falla que se rompió × cuánto se desplazó). Mw no se satura y es la que usan la física de la fuente y las ecuaciones de predicción del movimiento; por eso el simulador usa Mw (dato publicado: Hanks y Kanamori, 1979).

- **Momento sísmico:** M0 = 10^(1,5·Mw + 16,05) dina·cm (= 10^(1,5·Mw + 9,05) N·m). Cada punto de Mw es unas **32 veces** más energía; 0,2 puntos son el doble (cálculo propio con la fórmula de Kanamori, 1977: log10 Es ≈ 1,5·Mw + 4,8, Es en julios).
- **Ejemplo:** Mw 6,2 (el sismo del nido de Bucaramanga del 10-mar-2015, según el USGS) da M0 ≈ [CIFRA: M0 en N·m que muestra la vista] y una energía radiada del orden de [CIFRA: energía en J].
- Para sismos moderados, ML y Mw suelen diferir en pocas décimas, pero no son iguales; la relación ML-Mw de la red colombiana está **por confirmar**.

## 3. De dónde sale el movimiento del suelo

### 3.1 El método (Boore, 2003)

El acelerograma se sintetiza en el dominio de la frecuencia: se arma el espectro de Fourier que tendría el sismo en Yondó y se le da forma en el tiempo a un ruido aleatorio con ese espectro. Los pasos (`data/sismo/amenaza.json → notas_para_implementar`):

1. **Fuente** de Brune (1970): espectro con frecuencia de esquina f0 = 4,906·10⁶·βs·(Δσ/M0)^(1/3), que depende de la magnitud y de la caída de esfuerzos Δσ.
2. **Camino:** dispersión geométrica por tramos y atenuación anelástica Q(f) = Q0·f^η.
3. **Sitio:** amplificación de roca genérica y del suelo (factor lineal y no lineal de BSSA14, Seyhan y Stewart, 2014) y filtro κ0 de altas frecuencias.
4. **Duración:** 1/f0 más la duración del camino (Boore y Thompson, 2014, en sismos corticales; 0,05·R en intraplaca).
5. **Ventana de Saragoni y Hart (1974)** sobre ruido gaussiano con semilla (generador mulberry32 y Box-Muller), normalizado en frecuencia; dos componentes horizontales con semillas s y s + 1; salida en m/s² con Δt = 0,005 s.

**Parámetros, con su fuente** (todos de `data/sismo/amenaza.json`; ningún número se cambió al copiarlo):

| Parámetro | Cortical (h < 40 km) | Intraplaca profunda (h > 70 km) | Tipo de dato y fuente |
|---|---|---|---|
| Caída de esfuerzos Δσ | 100 bar (rango 50-150) | 800 bar (rango 450-1.100) | Cálculo propio de la investigación: calibrado contra BSSA14 (cortical) y contra BC Hydro 2016 y Zhao 2006 (intraplaca) |
| Patrón de radiación, superficie libre y partición | 0,55; 2,0; 1/√2 | Iguales | Dato publicado (Boore, 2003; Boore y Boatwright, 1984) |
| Velocidad y densidad de la fuente, Q, κ0 y dispersión | [CIFRA: valores de amenaza.json que muestra la vista] | [CIFRA] | Dato publicado o estimación, según el bloque de `amenaza.json` |
| Región análoga | Oeste de Norteamérica (corteza activa) | Velocidades del manto y Q de sismos intraplaca del centro de México (por confirmar) | Estimación: no se encontró un modelo estocástico calibrado para el norte de los Andes |

### 3.2 El sitio

Yondó (lat 7,005271; lon −73,914597), sobre depósitos aluviales del Magdalena. **Perfil de suelo D** de la NSR-10 (180 ≤ Vs30 < 360 m/s) con **Vs30 = 270 m/s** (estimación; rango 180-360 m/s): el estudio geotécnico lo define. Si resulta perfil E (Vs30 < 180 m/s), el simulador permite bajar a 150 m/s, con el aviso de que la ecuación de predicción y el factor de suelo se extrapolan.

### 3.3 Los escenarios de referencia

Ocho escenarios ilustrativos (`amenaza.json → escenarios`; todo el contexto sismotectónico está **por confirmar**). La aceleración pico (PGA) es la media geométrica de 24 simulaciones de la investigación en Vs30 = 270 m/s (cálculo propio de la investigación del 23-oct-2026, una componente):

| Escenario | Mw | Profundidad | Distancia epicentral | Tipo | PGA en el suelo | Aviso |
|---|---|---|---|---|---|---|
| Nido de Bucaramanga, sismo frecuente | 5,0 | 150 km | 92 km | Intraplaca profunda | 0,0043 g | Frecuencia por confirmar en el catálogo del SGC |
| **Nido de Bucaramanga, como el 10-mar-2015 (por defecto)** | 6,2 | 150 km | 92 km | Intraplaca profunda | 0,028 g | Profundidad y magnitud por confirmar |
| Nido de Bucaramanga, máximo hipotético | 7,0 | 150 km | 92 km | Intraplaca profunda | 0,076 g | Escenario hipotético |
| Falla de Cimitarra | 6,5 | 10 km | 20 km | Cortical | 0,17 g | Distancia y magnitud por confirmar |
| Falla de La Salina | 6,5 | 10 km | 47 km | Cortical | 0,079 g | Distancia y magnitud por confirmar |
| Falla de Palestina | 7,0 | 12 km | 70 km | Cortical | 0,087 g | Distancia y magnitud por confirmar |
| Falla Bucaramanga-Santa Marta | 7,0 | 12 km | 92 km | Cortical | 0,067 g | Magnitud por confirmar |
| Sismo local hipotético bajo Yondó | 6,0 | 10 km | 5 km | Cortical | 0,20 g | Escenario hipotético: no hay falla activa conocida bajo el casco urbano (por confirmar) |

**Avisos de combinación.** Toda combinación fuera de la sismicidad conocida (un sismo profundo fuera del nido, uno del nido mayor que Mw 6,8, uno superficial a menos de 15 km del casco urbano o uno cortical mayor que Mw 7,3) se muestra con la etiqueta «escenario hipotético: la física es la misma, pero no hay evidencia de que la naturaleza produzca este sismo aquí».

**El terremoto del 10 de agosto de 2026 (magnitud 7,4) no es un escenario del simulador:** sus dos distancias posibles a Yondó (≈ 342 km si el epicentro fue San José del Palmar, Chocó, según la OPS; ≈ 313 km si fue Pereira, según El Tiempo; cálculo propio de la investigación) quedan en el borde o fuera del rango de 0 a 300 km del control, y su profundidad y sus efectos en Yondó están por confirmar. El atlas no escoge un epicentro sin fuente primaria.

### 3.4 La profundidad cambia el tipo de sismo, sin saltos

La profundidad entra por dos vías: la distancia al foco (distancia hipocentral) y el **tipo de sismo**. Hasta 40 km el sismo es **cortical**; desde 70 km, **intraplaca profundo** (como los del nido de Bucaramanga, a unos 140-160 km); entre 40 y 70 km hay una **banda de transición** en la que el espectro es una mezcla con peso w = (h − 40)/30: ln A(f) = (1 − w)·ln A_cortical(f) + w·ln A_intraplaca(f), cada término con sus propios parámetros. Así, mover la profundidad 1 km cambia la aceleración de forma continua; con un umbral brusco en 50 km, el PGA de un Mw 6,2 a 92 km pasaba de 0,025 g a 0,080 g con un solo kilómetro (prueba de la revisión de la especificación con la implementación de referencia, cálculo propio). Si la persona fuerza un tipo incompatible con la profundidad, la vista lo avisa.

### 3.5 Escala «nivel de diseño NSR-10» (hipotética)

El escenario por defecto casi no produce esfuerzos (PGA ≈ 0,028 g). Para ver la estructura cerca de su diseño, el control de escala multiplica el registro para que su espectro, entre 0,8 y 1,2 veces el período fundamental en cada dirección, iguale en promedio el espectro de diseño de Yondó con I = 1,5 (rango de A.2.7, por confirmar). No cambia la física de la fuente: es un escenario hipotético, y la vista muestra el factor y cuántas vueltas dio el ajuste del suelo no lineal.

## 4. El modelo de la torre (prediseño)

### 4.1 Geometría y niveles

Pisos 1 a 3 de 21,60 × 42,00 m y piso 4 de 21,60 × 30,00 m (retrocede 12 m en el sur); retícula con ejes A-D (x = −13,0; −5,8; 1,4; 8,6) y 1-7 (y = −19,6 a 22,4); luces de 7,20 m en x y de 4,80 a 8,40 m en y; niveles a 0,0; 4,5; 8,7; 12,9 y 17,1 m (dato del proyecto, `programa.json`). Núcleos de escaleras y ascensores al oriente (x = 3,1 a 8,6). La torre es un solo bloque con retroceso, con junta solo hacia el edificio actual, la galería y el bloque técnico (por confirmar con el diseño).

### 4.2 Sistema estructural, R y período

- **Sistema adoptado:** [CIFRA: dual o combinado, con la fracción del cortante que toman los pórticos solos y la fila de la tabla de la NSR-10]. Regla (paso 0 del prediseño): si los pórticos resisten de forma independiente ≥ 25 % de las fuerzas sísmicas, el sistema es dual (Tabla A.3-4); si no, combinado (Tabla A.3-2) (numerales, R0 y Ω0 por confirmar).
- **Coeficiente de capacidad de disipación:** R = φa·φp·φr·R0 = [CIFRA: R con cada factor y su justificación].
- **Período:** con muros en los núcleos aplica la fila «otros sistemas» de la Tabla A.4.2-1 (Ct = 0,049; α = 0,75; numerales por confirmar): Ta = 0,049·17,1^0,75 ≈ 0,41 s y Cu·Ta ≈ 0,56 s, con Cu = 1,75 − 1,2·Av·Fv = 1,354 (cálculo propio de la especificación). Período fundamental del modelo: T1 = [CIFRA] s; en la fuerza horizontal equivalente se usa T ≤ Cu·Ta.
- **Espectro de diseño de Yondó:** Aa = Av = 0,15; perfil D con Fa = 1,5 y Fv = 2,2; I = 1,5 (dato oficial vía `normas.json` y `amenaza.json`; tablas de Fa y Fv por confirmar contra el PDF del Título A). Sa(0,5 s) = 0,844 g y Sa(1,0 s) = 0,594 g con I = 1,5 (cálculo propio, prueba T14 del motor).
- **Cortante basal de diseño:** [CIFRA: fuerza horizontal equivalente y modal, con el factor de ajuste al 80 % o 90 %].

### 4.3 Irregularidades, excentricidad y retroceso

- **Torsional (1aP/1bP):** deriva máxima en un borde frente al promedio de los dos bordes, contra 1,2 y 1,4: [CIFRA: cociente por piso]. Los núcleos están todos al oriente y el centro de masa cerca de x ≈ −2 m: la excentricidad es física real del prediseño y se ve en la deriva de las esquinas.
- **Geométrica en altura (3A):** el piso 4 tiene 30 m en y frente a 42 m de los pisos 1 a 3: 42/30 = 140 % > 130 % (cálculo propio; numeral por confirmar). Con el retroceso, el centro de masa del piso 4 queda ≈ 6 m al norte del de los niveles de abajo.
- **Excentricidad y centro de rigidez por nivel:** [CIFRA: tabla por nivel].

### 4.4 Secciones, refuerzo y masas

- Columnas de 0,60 × 0,60 m (28 en los pisos 1 a 3 y 20 en el piso 4), muros de núcleo de 0,30 m (≈ 45 m lineales en el presupuesto) con sus **aletas efectivas** (NSR-10 C.21.9.5.2, numeral por confirmar), vigas que dimensiona el prediseño (ancho ≥ 0,25 m en capacidad especial de disipación) y losa nervada (0,24 m³ de concreto por m² de placa con vigas, dato del presupuesto): [CIFRA: secciones y cuantías adoptadas].
- **Columna fuerte-viga débil** (ΣMnc ≥ 1,2·ΣMnb en cada nudo): [CIFRA: relación mínima]. Cortante por capacidad con Mpr (1,25·fy, φ = 1).
- **Masas por nivel:** muerta (peso propio, acabados, muros divisorios y fachada desde las cantidades del presupuesto) más 25 % de la viva (supuesto declarado): [CIFRA: masa, peso sísmico y momento polar por nivel]. Equipos de cubierta (tanques de 2 × 5 m³, condensadoras y paneles solares) con su posición (estimación).

### 4.5 Derivas y umbral de daño

- **Deriva de diseño** (fuerzas sin reducir, como vector en los vértices del contorno): ≤ 1 % en todos los entrepisos (Tabla A.6.4-1): [CIFRA: deriva máxima por entrepiso y dónde ocurre].
- **Umbral de daño** (grupo IV, cap. A.12, Ad = 0,04): deriva vectorial ≤ 0,4 % con los muros aislados y ≤ 0,2 % en el caso con mampostería adherida (NSR-10, Tabla A.12.5-1, vía `normas.json`): [CIFRA: derivas del umbral de daño]. Es criterio que bloquea el prediseño.

## 5. El modelo no lineal

- **Pseudotridimensional** (Wilson y Dovey, 1972): cada nivel es un diafragma rígido con tres grados de libertad (ux, uy, rz) en su centro de masa; los pórticos son planos y sus grados de libertad sin masa se condensan en cada iteración. La misma columna aparece en dos pórticos (como en TABS): su rigidez axial se suma dos veces (limitación conocida, documentada).
- **Elemento de Giberson (1969):** cada viga, columna y muro es una parte elástica (flexión y cortante, con zona rígida en los nudos) con un resorte plástico en cada extremo. Una rótula positiva dentro del vano (lejos de los extremos) no se captura.
- **Histéresis:** bilineal con endurecimiento cinemático (por defecto) o Clough (rigidez de recarga hacia el pico anterior). El lazo esperado de cada una está en la prueba T7.
- **Propiedades esperadas** (ASCE/SEI 41-17, factores de material por confirmar): la simulación compara con la resistencia esperada (My_e, Mn_e, Vn_e, φ = 1) y no con la nominal de diseño; los límites de rotación plástica son los de ocupación inmediata (IO), seguridad de la vida (LS) y prevención del colapso (CP).
- **Gravedad primero:** un análisis estático no lineal con las cargas de gravedad; el sismo arranca de ese estado (los momentos de gravedad adelantan o retrasan la fluencia en cada extremo de viga).
- **P-Delta con el peso de cada nivel:** cada entrepiso recibe el peso de todos los niveles de encima en la posición de su centro de masa (con el retroceso, el del piso 4 está desplazado), lo que equivale a cuatro columnas articuladas por nivel.
- **Amortiguamiento de Rayleigh del 5 %:** C = a0·M + a1·ΣK0,e, con la rigidez inicial de la **parte elástica** de los elementos; las rótulas nunca amortiguan (así no aparece una fuerza de amortiguamiento espuria cuando fluyen). Períodos ancla: [CIFRA: Ti y Tj]; amortiguamiento efectivo de los 12 primeros modos: [CIFRA: tabla de ξ por modo].

## 6. El método numérico

- **Newmark de aceleración promedio** (γ = 1/2, β = 1/4): incondicionalmente estable en lo lineal y sin disipación numérica.
- **Newton-Raphson completo** en cada paso, con tangente consistente de las rótulas; si un paso no converge en 20 iteraciones, se parte en dos hasta 4 veces; si aun así no converge, el cálculo se detiene con resultados parciales y lo dice.
- **Paso de tiempo:** 0,005 s (igual al del registro). En «calidad baja» (dispositivos lentos), 0,01 s sobre el registro filtrado a 20 Hz y tomado cada 2 muestras; la vista lo dice. Las cifras de este documento se calculan con 0,005 s.
- **Alargamiento del período** de Newmark: T̄/T − 1 ≈ (π²/3)·(Δt/T)², 0,09 % en el modo 1 (T ≈ 0,6 s) con Δt = 0,01 s (cálculo propio de la especificación).
- **Qué se evalúa en cada paso** (no en la salida cada 0,02 s): envolventes, primera fluencia, niveles de desempeño, derivas vectoriales y el riesgo de los equipos.
- **Balance de energía** (formulación relativa, Uang y Bertero, 1990): entrada = cinética + amortiguada + elástica + histerética + trabajo de P-Delta, con un control independiente por la energía de deformación. Error máximo en los escenarios de referencia: [CIFRA]. Índice de estabilidad máximo: [CIFRA].

## 7. Cómo leer la pantalla

- **Estructura deformada:** las líneas siguen los desplazamientos calculados del diafragma y los giros de los nudos; la exageración (×1 a ×200) se dice siempre en pesos reales («×50: 2,1 cm reales se dibujan como 1,05 m»). La estructura sin deformar queda como fantasma gris.
- **Colores de demanda/capacidad:** verde hasta 0,5; intermedio de 0,5 a 0,8; amarillo de 0,8 a 1,0; rojo por encima de 1,0. Se puede colorear por el máximo, por flexión (|M|/Mn esperado), por cortante (|V|/Vn esperado) o por rotación plástica (θp frente a ocupación inmediata).
- **Rótulas:** esferas en los extremos que fluyen, con tamaño según θp/θp de ocupación inmediata y anillo según el nivel superado (ocupación inmediata, seguridad de la vida, prevención del colapso).
- **Deriva vectorial:** √(Δx² + Δy²)/h en cada vértice del contorno de cada entrepiso; capta la torsión, que en las esquinas suma las dos direcciones. La gráfica de derivas trae el límite del 1 %, el umbral de daño del 0,4 % y el de mampostería del 0,2 %.
- **Gráficas:** acelerograma de las dos componentes; espectro de respuesta contra el de diseño de Yondó (con y sin I = 1,5 y el de umbral de daño), con la mediana ±1σ de las ecuaciones de predicción del tipo de sismo; espectro de Fourier contra el objetivo; derivas por piso; cortante basal y momento torsor en el tiempo; balance de energía; lazo de histéresis del elemento seleccionado.
- **Equipos sin anclar:** cada equipo del piso elegido muestra si queda estable, desliza o empieza a balancearse (bloque rígido con fricción; datos físicos de catálogo, estimación).

## 8. Resultados de los escenarios de referencia

Tabla generada desde el motor con Δt = 0,005 s, semilla 2028, muros aislados, histéresis bilineal y P-Delta (cálculo propio): [CIFRA: tabla completa].

| Escenario | PGA del registro (x / y) | Deriva vectorial máxima (entrepiso y vértice) | Cortante basal pico (x / y) | Rótulas por nivel | Equipos que deslizan o se balancean |
|---|---|---|---|---|---|
| Nido de Bucaramanga, como el 10-mar-2015 | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Falla de Cimitarra | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Sismo local hipotético bajo Yondó | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |
| Nido de Bucaramanga con escala «nivel de diseño NSR-10» (hipotético) | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] | [CIFRA] |

Lectura: [CIFRA: dos o tres frases con lo que muestran los resultados, en lenguaje claro].

## 9. Validación

### 9.1 Pruebas con solución exacta (`node scripts/sismo/test_motor.mjs`)

| Grupo | Pruebas | Referencia | Resultado |
|---|---|---|---|
| Integrador | T1-T6 (oscilador libre, amortiguado, forzado, escalón, orden de convergencia, balance de energía) | Soluciones cerradas | [CIFRA] |
| Rótulas | T7 (ciclo cuasiestático, bilineal y Clough) | Tabla calculada a mano en la especificación (7.8) | [CIFRA] |
| Modelo | T8-T12 (pórtico de cortante, pórtico de un vano, excentricidad, P-Delta, equilibrio) | Fórmulas cerradas y ensamble a mano | [CIFRA] |
| Movimiento | T13-T16, T19, T20 (ecuaciones de predicción, espectro NSR-10, síntesis, normalización, espectro de respuesta, continuidad con la profundidad, calidad baja) | Valores de prueba de `amenaza.json` e implementación de referencia en Python | [CIFRA] |
| Otros | T17, T18, T21, T22 (determinismo, estructura real, equipos, deriva vectorial) | — | [CIFRA] |

### 9.2 Comparación con OpenSees 3.8 (`python3 scripts/sismo/validar_opensees.py`)

Modelo tridimensional con la **misma idealización** (pórticos con nodos propios esclavos del diafragma, rótulas como resortes `Steel01` con la pendiente escalada, Rayleigh con los mismos a0 y a1, P-Delta con columnas de gravedad).

- **Casos de control** (antes de la torre): un piso con tres pórticos contra la condensación exacta (error < 10⁻⁵): [CIFRA]; ciclo de una rótula contra la tabla de T7 (< 0,5 %): [CIFRA].
- **Torre:** períodos de los 6 primeros modos (< 1 %): [CIFRA]; corrida elástica `nido_2015`, deriva vectorial y cortante basal pico (< 3 %): [CIFRA]; corrida no lineal `local_hip` con escala que produce fluencia (desplazamiento de cubierta y deriva < 10 %, mismos elementos que fluyen con índice de Jaccard ≥ 0,8, primera fluencia ±0,1 s, energía amortiguada < 5 %): [CIFRA].

## 10. Limitaciones e incertidumbres

- **Prediseño, no diseño:** secciones, refuerzo y masas son de prediseño (estimación); sin estudio de suelos, la base se supone empotrada sobre los dados de los pilotes.
- **Idealización:** diafragmas rígidos; pórticos planos; rótulas concentradas en los extremos (no dentro del vano); núcleos como muros planos con aletas efectivas, sin compatibilidad vertical en las esquinas y sin cambio de resistencia con la carga axial del sismo (interacción P-M en fase 2); sin degradación de resistencia (modelo de Ibarra-Medina-Krawinkler fuera de alcance); sin interacción suelo-estructura; sin componente vertical; la rigidez axial de una columna compartida se cuenta en sus dos pórticos.
- **Movimiento:** parámetros de regiones análogas (oeste de Norteamérica, centro de México), calibrados contra ecuaciones de predicción publicadas; sin registros locales para calibrar; contexto sismotectónico por confirmar.
- **Modelo del edificio en 3D:** el modelo GLB de la torre reparte entrepisos iguales de 4,30 m; el simulador lo oculta y dibuja su propia estructura con los niveles reales (regenerar el GLB queda fuera de alcance).
- **Equipos sin anclar:** bloque rígido con fricción de catálogo (estimación); el anclaje real lo define el diseño de los elementos no estructurales.

## 11. Lo que falta verificar

- NSR-10: tablas de Fa y Fv para suelo D, numeración de A.2.6, filas del sistema dual y del combinado (Tablas A.3-2 y A.3-4) con R0 y Ω0, Ct y α (Tabla A.4.2-1), exponente k (A.4.3), ajuste del cortante modal (A.5.4.5), rango de escalamiento de registros (A.2.7), deriva vectorial (A.6.3.1), espectro y rigidez del umbral de daño (A.12.3-A.12.4), irregularidades (Tablas A.3-6 y A.3-7), aletas efectivas de muros (C.21.9.5.2), numerales de C.21 y de A.9, cargas del Título B.
- Tipo de suelo real (estudio geotécnico) y si la cimentación con pilotes cambia la respuesta (interacción suelo-estructura).
- ASCE/SEI 41-17: factores de material esperado para f'c y fy; parámetros «a» y «b» y límites IO, LS y CP de vigas, columnas y muros; longitud de rótula de muros.
- Sismotectónica: centro y profundidad del nido de Bucaramanga, Mw del sismo del 10-mar-2015, distancias a las fallas, magnitudes máximas y ecuaciones de predicción del modelo nacional del SGC.
- Epicentro y profundidad del terremoto del 10-ago-2026 (OPS: San José del Palmar; anexo C: Pereira).
- [CIFRA: pendientes que deje el prediseño de la ola 2, por ejemplo derivas o relaciones columna-viga que no cumplan].

## 12. Fuentes

- Boore, D. M. (2003). Simulation of ground motion using the stochastic method. *Pure and Applied Geophysics* 160: <https://doi.org/10.1007/PL00012553>
- Brune, J. N. (1970). Tectonic stress and the spectra of seismic shear waves from earthquakes. *JGR* 75: <https://doi.org/10.1029/JB075i026p04997>
- Hanks, T. C. y Kanamori, H. (1979). A moment magnitude scale. *JGR* 84: <https://doi.org/10.1029/JB084iB05p02348>
- Kanamori, H. (1977). The energy release in great earthquakes. *JGR* 82: <https://doi.org/10.1029/JB082i020p02981>
- Richter, C. F. (1935). An instrumental earthquake magnitude scale. *BSSA* 25: <https://doi.org/10.1785/BSSA0250010001>
- Saragoni, G. R. y Hart, G. C. (1974). Simulation of artificial earthquakes. *Earthquake Engineering and Structural Dynamics* 2: <https://doi.org/10.1002/eqe.4290020305>
- Boore, D. M. y Thompson, E. M. (2014). Path durations for use in the stochastic-method simulation of ground motions. *BSSA* 104: <https://doi.org/10.1785/0120140058>
- Boore, D. M., Stewart, J. P., Seyhan, E. y Atkinson, G. M. (2014). NGA-West2 equations (BSSA14). *Earthquake Spectra* 30: <https://doi.org/10.1193/070113EQS184M>
- Seyhan, E. y Stewart, J. P. (2014). Semi-empirical nonlinear site amplification. *Earthquake Spectra* 30: <https://doi.org/10.1193/063013EQS181M>
- Abrahamson, N., Gregor, N. y Addo, K. (2016). BC Hydro ground motion prediction equations for subduction earthquakes. *Earthquake Spectra* 32: <https://doi.org/10.1193/051712EQS188MR>
- Zhao, J. X. et al. (2006). Attenuation relations of strong ground motion in Japan. *BSSA* 96: <https://doi.org/10.1785/0120050122>
- Campbell, K. W. (2003). Prediction of strong ground motion using the hybrid empirical method. *BSSA* 93: <https://doi.org/10.1785/0120020002>
- García, D. et al. (2004). Inslab earthquakes of central Mexico. *BSSA* 94: <https://doi.org/10.1785/0120030125>
- Zarifi, Z., Havskov, J. y Hanyga, A. (2007). An insight into the Bucaramanga nest. *Tectonophysics* 443: <https://doi.org/10.1016/j.tecto.2007.06.004>
- Prieto, G. A. et al. (2012). Earthquake nests as natural laboratories. *Tectonophysics*: <https://doi.org/10.1016/j.tecto.2012.07.019>
- Paris, G. et al. (2000). Map and database of Quaternary faults and folds in Colombia (USGS): <https://pubs.usgs.gov/of/2000/ofr-00-0284/>
- Reglamento Colombiano de Construcción Sismo Resistente NSR-10, Título A (Decreto 926 de 2010): <https://www.idrd.gov.co/sites/default/files/documentos/Construcciones/titulo-a-nsr-100.pdf>
- Servicio Geológico Colombiano, Red Sismológica Nacional y mapas de fallas: <https://www.sgc.gov.co>
- Wilson, E. L. y Dovey, H. H. (1972). Three-dimensional analysis of building systems (TABS), Universidad de California, Berkeley (EERC 72-8).
- Giberson, M. F. (1969). Two nonlinear beams with definitions of ductility. *Journal of the Structural Division* (ASCE) 95(ST2).
- Newmark, N. M. (1959). A method of computation for structural dynamics. *Journal of the Engineering Mechanics Division* (ASCE) 85(EM3).
- Nigam, N. C. y Jennings, P. C. (1969). Calculation of response spectra from strong-motion earthquake records. *BSSA* 59(2).
- Uang, C.-M. y Bertero, V. V. (1990). Evaluation of seismic energy in structures. *Earthquake Engineering and Structural Dynamics* 19.
- ASCE/SEI 41-17, *Seismic Evaluation and Retrofit of Existing Buildings* (factores de material esperado y límites de rotación; numerales por confirmar).
- OpenSees 3.8 (openseespy 3.8.0.0): <https://pypi.org/project/openseespy/3.8.0.0/>
- Datos del atlas: `data/sismo/amenaza.json`, `data/sismo/torre_hospital_estructura.json`, `data/sismo/validacion_opensees.json`, `data/proyectos/torre_hospital/presupuesto.json` y `normas.json`.
