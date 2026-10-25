# 14 · Simulación sísmica de la torre del hospital

**Qué le pasaría a la torre de servicios de primer nivel de Yondó en un sismo, calculado paso a paso: un movimiento del suelo sintetizado con la física de la fuente, del camino y del sitio, y un modelo no lineal de la estructura de prediseño que se integra en el tiempo. En la pantalla no hay animaciones: todo lo que se mueve es el resultado del cálculo en ese instante.**

> Estado: **prediseño** (cálculo propio, estimación sin firmar), con fecha de corte del 25 de octubre de 2026. Las cifras de este documento salen de los datos generados del atlas: el prediseño estructural de la torre (con su cimentación y su refuerzo), los escenarios de referencia calculados con el motor del simulador (Δt = 0,005 s) y la comparación con OpenSees 3.8. Las comprueba un control automático que falla si una cifra no coincide con los datos.
>
> Cada cifra dice si es un **dato oficial** (copiado de la fuente), un **cálculo propio** (operación sobre datos citados, con el método a la vista) o una **estimación** (supuesto con rango, por confirmar). Lo que no se pudo leer en la fuente dice **por confirmar**: las páginas `.gov.co` no abrieron desde el entorno de investigación (23 y 24-oct-2026) y los numerales de la NSR-10 se citan de memoria, cada uno marcado.

**Modelo de prediseño (sin estudio de suelos ni diseño estructural firmado). Idealización estándar de ingeniería: diafragmas rígidos, pórticos planos, rótulas concentradas, núcleos como muros planos con aletas efectivas (su resistencia no cambia con la carga axial del sismo), sin interacción suelo-estructura, sin componente vertical, sin degradación de resistencia. Amortiguamiento del 5 % proporcional a la masa y a la rigidez inicial de la parte elástica de los elementos (las rótulas no amortiguan). Los colores comparan con la resistencia esperada y con el límite de ocupación inmediata de un hospital. El contexto sísmico (nido de Bucaramanga, fallas cercanas) está por confirmar con el Servicio Geológico Colombiano. Validado contra soluciones exactas y contra OpenSees (ver documento 14).**

## En pocas palabras

- La torre es una **edificación indispensable** (grupo de uso IV de la NSR-10): tiene que seguir funcionando después de un sismo fuerte y quedar **sin daño** en uno frecuente. Yondó está en **amenaza sísmica intermedia** (Aa = Av = 0,15), así que el concreto se diseña con **capacidad moderada de disipación de energía (DMO)**.
- El prediseño que cumple es un **sistema dual**: 5 muros de concreto de 0,35 m en los núcleos de escaleras y pórticos con columnas de 0,80 m (0,90 m en la fachada occidental), sobre 146 pilotes de 15 m. Con las secciones del presupuesto (columnas de 0,60 m) la deriva llegaba a 2,09 % y no cumplía el 1 %; con las adoptadas queda en **0,939 %** (cálculo propio).
- El movimiento del suelo se fabrica con el **método estocástico de Boore (2003)**: la magnitud de momento Mw, la profundidad, la distancia y el suelo cambian el sismo de forma continua. La magnitud que se mueve es **Mw**, no la «escala de Richter», que se satura en sismos grandes.
- En el escenario por defecto (nido de Bucaramanga, como el 10-mar-2015) la torre se mueve muy poco: deriva vectorial máxima de **0,056 %** y ningún elemento fluye. En el sismo local hipotético bajo Yondó (Mw 6,0 a 10 km), la deriva llega a **0,416 %** y fluyen 40 elementos, ninguno más allá de ocupación inmediata; 260 equipos sueltos deslizan (cálculo propio con el motor).
- El motor se validó contra soluciones exactas (44 pruebas en verde) y contra OpenSees 3.8 con la misma idealización: los 6 primeros períodos difieren a lo sumo **0,054 %**, la deriva y el cortante basal elásticos **0,16 %** y **0,047 %**, y en la corrida no lineal fluyen los mismos 155 elementos en los dos programas (cálculo propio).

## 1. Para qué sirve y qué no es

**Para qué sirve.** Para ver, con la física a la vista, cómo responde el prediseño de la torre a sismos posibles en Yondó: cuánto se desplaza cada piso, cuánto se tuerce por tener los núcleos al oriente, qué columnas, vigas y muros se acercan a su resistencia, dónde se formarían rótulas plásticas, qué equipos sueltos deslizarían o empezarían a balancearse, qué muros de mampostería se agrietarían y cómo se reparte la energía que entra. Sirve para discutir el diseño con la comunidad, la E.S.E. y el diseñador estructural, y para explicar por qué la NSR-10 pide lo que pide a un hospital.

**Qué no es.**

- No es el diseño estructural ni lo reemplaza: el diseño lo firma un ingeniero con matrícula, con estudio de suelos y con el análisis que exige la NSR-10 (Título A). El prediseño del atlas es una estimación para dimensionar, presupuestar y explicar.
- No es una amenaza sísmica oficial: los escenarios son ilustrativos y su contexto (nido de Bucaramanga, fallas cercanas) está **por confirmar** con el Servicio Geológico Colombiano.
- No es una predicción: un sismo real con la misma magnitud y distancia puede sacudir más o menos (la dispersión de las ecuaciones de predicción es de un factor de 2 hacia arriba o hacia abajo). Una sola semilla da un registro posible, no «el» registro.
- No es una animación: el deslizador recorre los pasos que el motor calculó, y cada línea se dibuja en la posición que dio el cálculo.

**Dónde corre.** En el navegador, en un trabajador en segundo plano (Web Worker); si no hay trabajador, la misma lógica corre en el hilo principal por tramos de unos 12 ms. El mismo escenario con la misma semilla da el mismo resultado en cualquier dispositivo, bit a bit (prueba T17 y QA en Chromium). En un escritorio, 40 s de sismo con Δt = 0,005 s se calculan en menos de un segundo (930 ms medidos el 25-oct-2026); en un teléfono simulado con la CPU 4 veces más lenta, en 1,9 s con la calidad baja.

## 2. Richter y Mw: qué magnitud se mueve

La «escala de Richter» (magnitud local ML, 1935) mide la amplitud que marca un sismógrafo Wood-Anderson a cierta distancia. Funciona bien en sismos pequeños y cercanos, pero **se satura** por encima de magnitud 6,5 a 7: sismos muy distintos marcan casi lo mismo, porque el aparato solo «ve» ondas de alrededor de un segundo. Hoy el Servicio Geológico Colombiano y el USGS reportan los sismos grandes en **magnitud de momento Mw**, que sale del momento sísmico M0 = μ·A·D (rigidez de la roca × área de la falla que se rompió × cuánto se desplazó). Mw no se satura y es la que usan la física de la fuente y las ecuaciones de predicción del movimiento; por eso el simulador usa Mw (dato publicado: Hanks y Kanamori, 1979).

- **Momento sísmico:** M0 = 10^(1,5·Mw + 16,05) dina·cm (= 10^(1,5·Mw + 9,05) N·m). Cada punto de Mw es unas **32 veces** más energía; 0,2 puntos son el doble (cálculo propio con la fórmula de Kanamori, 1977: energía radiada Es ≈ M0/20.000).
- **Ejemplo:** Mw 6,2 (el sismo del nido de Bucaramanga del 10-mar-2015, según el USGS; por confirmar) da M0 ≈ 2,24 × 10¹⁸ N·m y una energía radiada del orden de 1,1 × 10¹⁴ J, la que muestra la vista (cálculo propio).
- Para sismos moderados, ML y Mw suelen diferir en pocas décimas, pero no son iguales; la relación ML-Mw de la red colombiana está **por confirmar**. Si alguien dice «un sismo de 6 en la escala de Richter», lo que el simulador puede reproducir es un Mw parecido, no el mismo número.

## 3. De dónde sale el movimiento del suelo

### 3.1 El método (Boore, 2003)

El acelerograma se sintetiza en el dominio de la frecuencia: se arma el espectro de Fourier que tendría el sismo en Yondó y se le da forma en el tiempo a un ruido aleatorio con ese espectro. Los pasos:

1. **Fuente** de Brune (1970): espectro con frecuencia de esquina f0 = 4,906·10⁶·βs·(Δσ/M0)^(1/3), que depende de la magnitud y de la caída de esfuerzos Δσ (más Δσ, más alta frecuencia).
2. **Camino:** dispersión geométrica por tramos y atenuación anelástica Q(f) = Q0·f^η.
3. **Sitio:** amplificación de la corteza genérica (Boore, 2016), factor del suelo lineal y no lineal de BSSA14 (Seyhan y Stewart, 2014) y filtro κ0 de las altas frecuencias.
4. **Duración:** 1/f0 más la duración del camino (Boore y Thompson, 2014, en sismos corticales; 0,05·R en intraplaca).
5. **Ventana de Saragoni y Hart (1974)** sobre ruido gaussiano con semilla (generador mulberry32 y Box-Muller), normalizado en frecuencia; dos componentes horizontales con semillas s y s + 1; salida en m/s² con Δt = 0,005 s.

**Parámetros, con su fuente** (ningún número se cambió al copiarlo de la investigación de amenaza):

| Parámetro | Cortical (h ≤ 40 km) | Intraplaca profunda (h ≥ 70 km) | Tipo de dato y fuente |
|---|---|---|---|
| Caída de esfuerzos Δσ | 100 bar (rango 50-150) | 800 bar (rango 450-1.100) a 120 km o más; menos por encima (sección 3.4) | Cálculo propio de la investigación: calibrado contra BSSA14 (cortical) y contra BC Hydro 2016 y Zhao 2006 (intraplaca) |
| Densidad y velocidad de la fuente | 2,8 g/cm³ y 3,5 km/s | 3,35 g/cm³ y 4,5 km/s (manto a ≈ 150 km) | Dato publicado (Campbell, 2003) / estimación (PREM, por confirmar) |
| Atenuación Q(f) | 180·f^0,45 | 251·f^0,58 | Dato publicado (Campbell, 2003) / valor de sismos intraplaca del centro de México (García et al., 2004; por confirmar) |
| Filtro κ0 | 0,04 s (0,03-0,05) | 0,035 s (0,025-0,045) | Dato publicado / cálculo propio (ajustado con Δσ) |
| Dispersión geométrica | 1/R hasta 40 km y 1/√R después | 1/R | Dato publicado / estimación |
| Patrón de radiación, superficie libre y partición | 0,55; 2,0; 1/√2 | Iguales | Dato publicado (Boore, 2003) |
| Región análoga | Oeste de Norteamérica (corteza activa) | Manto y Q de sismos intraplaca del centro de México | Estimación: no se encontró un modelo estocástico calibrado para el norte de los Andes |

### 3.2 El sitio

Yondó (lat 7,005271; lon −73,914597), sobre depósitos aluviales del Magdalena. **Perfil de suelo D** de la NSR-10 (180 ≤ Vs30 < 360 m/s) con **Vs30 = 270 m/s** (estimación; rango 180-360 m/s): el estudio geotécnico lo define. Si resulta perfil E (Vs30 < 180 m/s), el simulador permite bajar a 150 m/s, con el aviso de que la ecuación de predicción y el factor de suelo se extrapolan. El suelo no lineal se resuelve con dos pasadas: la primera calcula la aceleración en roca y la segunda amplifica con el factor que corresponde a esa aceleración.

### 3.3 Los escenarios de referencia

Ocho escenarios ilustrativos (todo el contexto sismotectónico está **por confirmar**). La aceleración pico (PGA) es la media geométrica de 24 simulaciones de la investigación en Vs30 = 270 m/s (cálculo propio de la investigación del 23-oct-2026, una componente):

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

**El terremoto del 10 de agosto de 2026 (magnitud 7,4) no es un escenario del simulador.** Las fuentes del atlas dan dos epicentros: la OPS (informe del 3-sep-2026) lo ubica en San José del Palmar (Chocó) y una nota de El Tiempo dice «epicentro en Pereira». El atlas no escoge uno sin fuente primaria: las dos distancias quedan a la vista (≈ 342 km a San José del Palmar y ≈ 313 km a Pereira; cálculo propio de la investigación), las dos en el borde o fuera del rango de 0 a 300 km del control, y su profundidad, su tipo de magnitud y sus efectos en Yondó están por confirmar.

### 3.4 Cómo la profundidad cambia el movimiento, sin saltos

La profundidad entra por tres vías, todas continuas:

1. **La distancia al foco.** El suelo de Yondó está a la distancia hipocentral √(distancia epicentral² + profundidad²): un sismo del nido a 92 km del sitio y 150 km de profundidad llega desde ≈ 176 km. Más lejos, menos sacudida: por la dispersión geométrica, por la atenuación (las ondas pierden energía al viajar, más las de alta frecuencia) y porque el movimiento dura más y se reparte en más tiempo.
2. **El tipo de sismo.** Hasta 40 km de profundidad el sismo es **cortical**; desde 70 km, **intraplaca profundo** (como los del nido de Bucaramanga, a unos 140-160 km). Un sismo intraplaca suelta su energía con más caída de esfuerzos y desde roca más densa y rápida: a igual distancia, sacude más en alta frecuencia que uno cortical. Entre 40 y 70 km hay una **banda de transición** en la que el espectro es una mezcla con peso w = (h − 40)/30: ln A(f) = (1 − w)·ln A_cortical(f) + w·ln A_intraplaca(f), cada término con sus propios parámetros.
3. **La caída de esfuerzos intraplaca.** Las ecuaciones de predicción intraplaca (BC Hydro 2016 y Zhao 2006) dicen que los sismos más profundos sacuden más, hasta unos 120 km. El motor lo reproduce con Δσ(h) = 800 bar·exp(1,5·0,0135·(min(h, 120) − 120)): a 120 km o más vale 800 bar (los escenarios del nido no cambian) y a 70 km, ≈ 290 bar (cálculo propio con las pendientes de profundidad de esas dos ecuaciones).

Así, mover la profundidad 1 km cambia la aceleración pico a lo sumo un 9 % entre 5 y 199 km de profundidad (prueba T19: PGA(h + 1)/PGA(h) entre 0,910 y 1,036 en 6 combinaciones de magnitud y distancia, con tolerancia de 0,85 a 1,18). Con un umbral brusco en 50 km, el PGA de un Mw 6,2 a 92 km pasaba de 0,025 g a 0,080 g con un solo kilómetro (prueba de la revisión de la especificación, cálculo propio). Si la persona fuerza un tipo de sismo incompatible con la profundidad, la vista lo avisa.

### 3.5 Escala «nivel de diseño NSR-10» (hipotética)

El escenario por defecto casi no produce esfuerzos (PGA ≈ 0,028 g). Para ver la estructura cerca de su diseño, el control de escala multiplica el registro para que su espectro, entre 0,8 y 1,2 veces el período fundamental en cada dirección, iguale en promedio el espectro de diseño de Yondó con I = 1,5 (rango de A.2.7, por confirmar). No cambia la física de la fuente: es un escenario hipotético. La vista muestra el factor y cuántas vueltas dio el ajuste del suelo no lineal (5 vueltas y un factor de 18,04 para el nido; 2,85 para Cimitarra y 2,46 para el sismo local, cálculo propio).

## 4. La norma: amenaza intermedia, DMO y grupo IV

| Qué | Valor en la torre | Norma y tipo de dato |
|---|---|---|
| Aceleración pico efectiva Aa y velocidad Av | 0,15 y 0,15 | NSR-10, Apéndice A-4 (Yondó, 05893); dato oficial ya registrado en el atlas |
| Zona de amenaza sísmica | **Intermedia** (0,10 < Aa ≤ 0,20) | NSR-10 A.2.3 (numeral por confirmar) |
| Grupo de uso | **IV, edificación indispensable** (tiene urgencias, partos e internación), coeficiente de importancia I = 1,5 | NSR-10 A.2.5.1.1 y A.2.5.2; dato oficial |
| Umbral de daño | Ad = 0,04; deriva ≤ 0,4 % con muros aislados y ≤ 0,2 % con mampostería adherida | NSR-10 A.12 y Tabla A.12.5-1 (espectro y rigidez por confirmar) |
| Capacidad de disipación de energía | **Moderada (DMO)**, la mínima que piden las tablas de sistemas para el concreto en zona intermedia | NSR-10 A.3.1 y Tablas A.3-1 a A.3-4 (por confirmar); detallado del capítulo C.21 |
| Sistema estructural | **Dual**: muros de concreto DMO con pórticos de concreto DMO, sin límite de altura en zona intermedia; R0 = 6,0 y Ω0 = 2,5 | NSR-10 Tabla A.3-4, fila 1.c (valores por confirmar) |
| Suelo | Perfil D, Fa = 1,5 y Fv = 2,2 | Estimación hasta el estudio geotécnico; tablas A.2.4 por confirmar |

**¿Pide más el grupo IV?** Según la revisión de memoria del Título A (el 24-oct-2026 no se pudo abrir el PDF), el grupo IV no cambia la capacidad de disipación exigida en zona intermedia; sí exige I = 1,5, el umbral de daño, el grado de desempeño superior de los elementos no estructurales (A.9) y la supervisión técnica (Título I y Ley 400 de 1997). **Por confirmar con el texto oficial.** Por ser un hospital, el prediseño adopta además criterios más exigentes que el mínimo DMO, todos declarados: confinamiento de las columnas con el refuerzo de capacidad especial (C.21.6.4.4), cortante por capacidad con 1,25·fy en vigas, columnas y muros, columna fuerte-viga débil en todos los nudos, sin irregularidad torsional extrema y cimentación revisada con el sismo de capacidad.

**Espectro de diseño de Yondó** (cálculo propio, prueba T14 del motor): Sa = 0,844 g en la meseta con I = 1,5 (0,5625 g sin I), Sa(1,0 s) = 0,594 g y Sa(2,0 s) = 0,297 g. El umbral de daño usa Sa = 3,0·Ad·Fa = 0,180 g hasta 0,733 s y amortiguamiento del 2 %.

## 5. El modelo de la torre (prediseño)

### 5.1 Geometría, niveles y masas

Pisos 1 a 3 de 21,60 × 42,00 m y piso 4 de 21,60 × 30,00 m (retrocede 12 m en el sur); retícula con ejes A-D (x = −13,0; −5,8; 1,4; 8,6) y 1-7 (y = −19,6 a 22,4); luces de 7,20 m en x y de 4,80 a 8,40 m en y; losas a 4,5; 8,7; 12,9 y 17,1 m (dato del proyecto). Núcleos de escaleras y ascensores al oriente (x = 3,1 a 8,6). La torre es un solo bloque con retroceso, con junta solo hacia el edificio actual, la galería y el bloque técnico (por confirmar con el diseño).

**Masas por nivel** (carga muerta desde las cantidades del presupuesto más el 25 % de la viva; cálculo propio, estimación):

| Nivel | Masa | Peso sísmico | Centro de masa (x; y) | Centro de rigidez (x; y) | Excentricidad (x; y) |
|---|---:|---:|---|---|---|
| Losa del piso 2 (4,5 m) | 1.370,2 t | 13.437 kN | (−1,64; 1,68) | (1,28; 5,22) | (2,92; 3,54) m |
| Losa del piso 3 (8,7 m) | 1.341,9 t | 13.160 kN | (−1,66; 1,69) | (0,68; 5,54) | (2,34; 3,85) m |
| Losa del piso 4 (12,9 m) | 1.295,4 t | 12.703 kN | (−1,66; 2,46) | (0,00; 5,47) | (1,66; 3,00) m |
| Cubierta (17,1 m) | 886,0 t | 8.688 kN | (−1,04; 7,39) | (−0,36; 5,70) | (0,68; −1,69) m |
| **Total** | **4.893,4 t** | **47.988 kN** | | | |

Con el retroceso, el centro de masa de la cubierta queda ≈ 5,7 m al norte del de los niveles de abajo. Los núcleos están al oriente y al norte del centro de masa: la torsión es física real del prediseño, no un error, y se ve en las esquinas.

### 5.2 Cómo se llegó al prediseño

El presupuesto traía columnas de 0,60 × 0,60 m, vigas de 0,40 × 0,60 m y ≈ 45 m de muro de 0,30 m. Con eso **no cumplía**: el prediseño se ajustó en cuatro pasos (cálculo propio):

| Paso | Cambio | T1 | Deriva máxima de diseño | Deriva del umbral de daño | Cociente torsional (x) |
|---|---|---:|---:|---:|---:|
| 0 | Secciones del presupuesto con los 7 paños de núcleo posibles | 0,571 s | 2,09 % | 0,295 % | 1,561 |
| 1 | Paños de muro que equilibran la torsión (sin la cara sur de la escalera norte ni el foso de ascensores) | 0,592 s | 2,17 % | 0,329 % | 1,397 |
| 2 | Pórticos más rígidos: columnas de 0,80 m y vigas de 0,40 × 0,80 m | 0,494 s | 1,18 % | 0,208 % | 1,314 |
| 3 | Pórtico de la fachada occidental (eje A, el más lejano de los núcleos) con columnas de 0,90 m y vigas de 0,50 × 0,90 m | 0,468 s | 0,94 % | 0,181 % | 1,296 |
| 4 | **Adoptado:** muros de 0,35 m (más alma para el cortante por capacidad) | 0,455 s | 0,94 % | 0,178 % | 1,306 |

### 5.3 Sistema estructural, R y período

- **Sistema adoptado: dual.** Con el modelo elástico, los pórticos toman en el entrepiso 1 el **16,3 %** del cortante en x y el **25,4 %** en y (el resto, los muros); en el entrepiso 4, el 56,5 % y el 84,3 %. La NSR-10 (A.3.2.1.4, por confirmar) no clasifica el sistema por esa fracción: exige que el pórtico, capaz de llevar las cargas verticales, se diseñe para resistir por sí solo al menos el 25 % del cortante de diseño. El prediseño lo hace (envolvente del modelo completo y del modelo de solo pórticos con el 25 % de la fuerza horizontal equivalente y su torsión accidental).
- **Coeficiente de capacidad de disipación:** R = φa·φp·φr·R0 = 0,9 × 0,9 × 1,0 × 6,0 = **4,86**. φa = 0,9 por la irregularidad geométrica en altura 3A (42/30 = 1,40 > 1,30); φp = 0,9 por la irregularidad torsional 1aP (cociente 1,306); φr = 1,0 porque ningún muro tiene relación altura del piso/longitud mayor que 1,0 (máximo 0,91) y perder el momento en los dos extremos de una viga quita a lo sumo el 9,6 % de la resistencia del piso (prueba de ASCE/SEI 7-16 a falta del texto de A.3.3.8, por confirmar). Con φr = 0,75, R sería 3,645 y las fuerzas de diseño, 33 % mayores.
- **Período:** con muros, la fila «otros sistemas» de la Tabla A.4.2-1 (Ct = 0,049; α = 0,75; por confirmar) da Ta = **0,412 s** y Cu·Ta = **0,558 s**, con Cu = 1,75 − 1,2·Av·Fv = 1,354. Períodos del modelo de prediseño: T1 = **0,455 s** (en y, con 43,0 % de la masa en y, 21,5 % en x y 12,5 % en torsión) y **0,444 s** en x; el tercero, 0,400 s, es torsional (58,7 % de la masa en giro). Los dos primeros están por debajo de Cu·Ta, así que la fuerza horizontal equivalente usa el período del modelo.
- **Cortante basal de diseño:** con Sa = 0,844 g y W = 47.988 kN, la fuerza horizontal equivalente sin reducir es Vs = **40.490 kN** (**8.331 kN** dividida por R), repartida en 5.023, 9.511, 13.614 y 12.342 kN de abajo arriba. El análisis modal (12 modos, CQC) da 30.026 kN en x y 28.578 kN en y; como la estructura es irregular, se ajusta al 90 % de la fuerza horizontal equivalente con factores de 1,214 y 1,275 (NSR-10 A.5.4.5, por confirmar).

### 5.4 Irregularidades, torsión y retroceso

- **Torsional (1aP/1bP):** deriva máxima en un borde frente al promedio de los dos bordes, contra 1,2 y 1,4: 1,306; 1,270; 1,217 y 1,171 en x (entrepisos 1 a 4) y 1,150 a 1,081 en y. Es irregular (1aP) pero no extrema (1bP), lo que el prediseño se impuso por ser edificación indispensable. La torsión accidental se amplifica con Ax = (δmax/1,2·δprom)²: hasta 1,185 en el entrepiso 1.
- **Geométrica en altura (3A):** el piso 4 tiene 30 m en y frente a 42 m de los pisos 1 a 3: 42/30 = 1,40 > 1,30 (NSR-10 Tabla A.3-7, por confirmar). Entra en φa.
- **Sin piso flexible (1A) ni irregularidad de masa (2A):** la rigidez de cada entrepiso es 1,54 a 2,11 veces la del de arriba, y la masa de un nivel es a lo sumo 1,46 veces la del de arriba (el límite es 1,5; Tabla A.3-7, por confirmar).

### 5.5 Secciones, núcleos y refuerzo

- **Columnas** de 0,80 × 0,80 m (28 por piso en los pisos 1 a 3 y 20 en el piso 4) y de 0,90 × 0,90 m en el eje A; **vigas** de 0,40 × 0,80 m (0,50 × 0,90 m en el eje A) y vigas banda de 0,35 m entre la columna C y los muros; **losa nervada** de 0,45 m (nervios de 0,12 m cada 0,80 m y loseta de 0,05 m); concreto de 28 MPa y acero de fy = 420 MPa (NTC 2289).
- **Muros de núcleo:** 5 paños de 0,35 m que equilibran la torsión (las dos caras occidentales de las escaleras, al norte de sus puertas; la cara norte de la escalera norte y las caras sur y norte de la escalera sur): 27,42 m de alma y 29,0 m de concreto en planta, frente a ≈ 45 m del presupuesto. Los demás paños de los núcleos van en mampostería separada de la estructura. Cada muro trabaja con sus **aletas efectivas** (el menor entre 0,25 veces la altura, la longitud real y la mitad de la distancia al alma vecina; NSR-10 C.21.9.5.2, por confirmar): 4,28 m en las esquinas de las escaleras.
- **Refuerzo por elemento** (despiece del prediseño, con barras N.º 3 a N.º 8 de la NTC 2289): la columna típica lleva 24 N.º 6 (1,07 %) y estribos N.º 4 de 6 ramas cada 0,15 m en la zona confinada; las del eje A, 16 N.º 8 (1,01 %); las que rematan los muros, hasta 28 N.º 7 (1,69 %). La viga típica, 2 N.º 8 arriba y abajo con estribos N.º 3 cada 0,15 a 0,175 m en 2h. Los muros, dos cortinas N.º 4 (verticales cada 0,25 m y horizontales cada 0,15 m) y **elementos de borde especiales** en los 10 tramos (por esfuerzo, C.21.9.6.3; las barras de borde se unen con acopladores, sin traslapos). Cuantías: columnas de 1,01 % a 1,69 % (entre 1 % y 4 %) y vigas hasta 0,79 % (≤ 2,5 %).
- **Columna fuerte-viga débil:** ΣMnc ≥ 1,2·ΣMnb en todos los nudos con columna encima; el peor nudo da **1,886** (cabeza de la columna D3 del piso 1, en el plano y). El cortante por capacidad (con Mpr = 1,25·fy y φ = 1) queda cubierto en vigas, columnas y muros.

### 5.6 La cimentación (en el prediseño, no en el análisis dinámico)

**146 pilotes** preexcavados de 0,60 m de diámetro y **15 m** de largo (2.190 m) bajo 20 dados de 3 a 6 pilotes y 2 losas de pilotes bajo los núcleos de escaleras (30 y 36 pilotes), 37 vigas de amarre, 5 muros de contención junto al pasaje del bloque técnico, contrapiso de 0,15 m, foso de ascensores y cisternas. Capacidad estimada por pilote: 632 kN de servicio (factor de seguridad 3) y 1.265 kN con el sismo de servicio, con un suelo aluvial supuesto (relleno, limo arcilloso hasta 6 m y arena media a densa; nivel freático a 1,0 m). Con 12 m no alcanzaba; 15 m es el largo con menos metros totales que resuelve todos los grupos (cálculo propio con los métodos de O'Neill y Reese y de la FHWA; **estimación: la fijan el estudio geotécnico y las pruebas de carga**, NSR-10 H.4 y H.6, por confirmar). **En la simulación la base sigue empotrada en la cara superior de los dados**: la interacción suelo-estructura queda fuera de alcance.

### 5.7 Derivas y umbral de daño

- **Deriva de diseño** (espectro sin reducir, como vector en los vértices del contorno, con 100 % de una dirección y 30 % de la otra): 0,465 %, 0,842 %, **0,939 %** y 0,801 % en los entrepisos 1 a 4. La máxima está en el entrepiso 3, en la esquina suroccidental (−13,0; −19,6), la más lejana de los núcleos. Límite: 1 % (NSR-10 A.6.3.1 y Tabla A.6.4-1). Cumple.
- **Umbral de daño** (Ad = 0,04, ξ = 2 %): máxima de **0,178 %** con los muros de mampostería aislados (límite 0,4 %) y de **0,127 %** con la mampostería adherida (límite 0,2 %), las dos en el entrepiso 3 (NSR-10 A.12 y Tabla A.12.5-1). Cumple.
- **Estabilidad (P-Delta):** índice máximo θ = 0,0047 (entrepiso 2), muy por debajo de 0,10: no hace falta amplificar (A.6.2.3, por confirmar).

## 6. El modelo no lineal

- **Pseudotridimensional** (Wilson y Dovey, 1972): cada nivel es un diafragma rígido con tres grados de libertad (ux, uy, rz) en su centro de masa; los 16 pórticos y muros son planos y sus grados de libertad sin masa se condensan en cada iteración (370 elementos: 196 tramos de columna, 154 vigas y 20 tramos de muro, más 42 resortes de mampostería). La misma columna aparece en dos pórticos (como en TABS): su rigidez axial se suma dos veces (limitación conocida, documentada).
- **Elemento de Giberson (1969):** cada viga, columna y muro es una parte elástica (flexión y cortante, con zona rígida en los nudos e inercias fisuradas: 0,70 en columnas y 0,35 en vigas y muros) con un resorte plástico en cada extremo. Una rótula positiva dentro del vano (lejos de los extremos) no se captura.
- **Histéresis:** bilineal con endurecimiento cinemático (por defecto) o Clough (rigidez de recarga hacia el pico anterior). La mampostería de fachada y divisoria tiene su propio modelo (Tomaževič) con estados de daño leve, moderado, extenso y colapso.
- **Propiedades esperadas** (ASCE/SEI 41-17, factores 1,5·f'c y 1,25·fy; por confirmar): la simulación compara con la resistencia esperada y no con la nominal de diseño; los límites de rotación plástica son los de ocupación inmediata (IO), seguridad de la vida (LS) y prevención del colapso (CP).
- **Gravedad primero:** un análisis estático no lineal con las cargas de gravedad; el sismo arranca de ese estado.
- **P-Delta con el peso de cada nivel:** cada entrepiso recibe el peso de todos los niveles de encima en la posición de su centro de masa (con el retroceso, el de la cubierta está desplazado), lo que equivale a cuatro columnas articuladas por nivel.
- **Amortiguamiento de Rayleigh del 5 %:** C = a0·M + a1·ΣK0,e, con la rigidez inicial de la **parte elástica** de los elementos; las rótulas nunca amortiguan (así no aparece una fuerza de amortiguamiento espuria cuando fluyen). Períodos ancla: T1 = 0,456 s y 0,0912 s (el de 90 % de masa acumulada o 0,2·T1); a0 = 1,147 s⁻¹ y a1 = 0,00121 s. Amortiguamiento efectivo de los 12 primeros modos: 5,00; 4,92; 4,61; 4,27; 4,58; 4,94; 6,98; 8,01; 9,00; 9,73; 11,18 y 12,63 % (los 12 modos llevan el 94,5 % de la masa en x y el 94,2 % en y). Con los muros de mampostería «sin aislar», el motor recalcula las anclas para que el primer modo siga en 5 % (prueba S5).

## 7. El método numérico

- **Newmark de aceleración promedio** (γ = 1/2, β = 1/4): incondicionalmente estable en lo lineal y sin disipación numérica.
- **Newton-Raphson completo** en cada paso, con tangente consistente de las rótulas; si un paso no converge en 20 iteraciones, se parte en dos hasta 4 veces; si aun así no converge, el cálculo se detiene con resultados parciales y lo dice. En los seis escenarios de referencia ningún paso dejó de converger y el promedio fue de 1 a 1,21 iteraciones por paso.
- **Paso de tiempo:** 0,005 s (igual al del registro). En «calidad baja» (dispositivos lentos), 0,01 s sobre el registro filtrado a 20 Hz y tomado cada 2 muestras; la vista lo dice. Las cifras de este documento se calculan con 0,005 s.
- **Alargamiento del período** de Newmark: T̄/T − 1 ≈ (π²/3)·(Δt/T)²; con Δt = 0,005 s y T1 = 0,456 s es del orden de 0,04 % (cálculo propio; la prueba T1 mide el valor exacto contra la fórmula cerrada con error de 10⁻⁷).
- **Qué se evalúa en cada paso** (no en la salida cada 0,02 s): envolventes, primera fluencia, niveles de desempeño, derivas vectoriales y el riesgo de los equipos.
- **Balance de energía** (formulación relativa, Uang y Bertero, 1990): entrada = cinética + amortiguada + elástica + histerética + trabajo de P-Delta, con un control independiente por la energía de deformación. Error máximo en los escenarios de referencia: 2,5 × 10⁻¹⁴ (es decir, cerrado hasta la precisión de la máquina). Índice de estabilidad máximo en el tiempo: 0,0151 (sismo local a nivel de diseño).

## 8. Cómo leer la pantalla

- **Estructura deformada:** las líneas siguen los desplazamientos calculados del diafragma y los giros de los nudos (interpolación de Hermite); la exageración (×1 a ×200) se dice siempre en medidas reales («×50: 2,1 cm reales se dibujan como 1,05 m»). La estructura sin deformar queda como fantasma gris.
- **Colores de demanda/capacidad (D/C):** verde hasta 0,5; intermedio de 0,5 a 0,8; amarillo de 0,8 a 1,0; rojo por encima de 1,0. Se puede colorear por el máximo, por flexión (|M|/Mn esperado), por cortante (|V|/Vn esperado) o por rotación plástica (θp frente a ocupación inmediata).
- **Rótulas:** esferas en los extremos que fluyen, con tamaño según θp/θp de ocupación inmediata y anillo según el nivel superado (ocupación inmediata, seguridad de la vida, prevención del colapso).
- **Deriva vectorial:** √(Δx² + Δy²)/h en cada vértice del contorno de cada entrepiso; capta la torsión, que en las esquinas suma las dos direcciones. La gráfica de derivas trae el límite del 1 %, el umbral de daño del 0,4 % y el de mampostería del 0,2 %.
- **Gráficas:** acelerograma de las dos componentes; espectro de respuesta contra el de diseño de Yondó (con y sin I = 1,5 y el de umbral de daño), con la mediana ±1σ de las ecuaciones de predicción del tipo de sismo; espectro de Fourier contra el objetivo; derivas por piso; cortante basal y momento torsor en el tiempo; balance de energía; lazo de histéresis del elemento seleccionado.
- **Equipos sin anclar:** cada equipo del piso elegido muestra si queda estable, desliza o empieza a balancearse (bloque rígido con fricción de Coulomb y criterio de Shenton; datos físicos de catálogo, estimación). Los 212 equipos que el inventario marca como anclados no se mueven en la simulación: el anclaje lo define el diseño de los elementos no estructurales.
- **Modelo BIM:** desde el modo «Modelo BIM» se pueden pintar columnas, vigas y muros con el D/C, las rótulas y la deriva del último cálculo (documento 16).

## 9. Resultados de los escenarios de referencia

Calculados con el motor del simulador sobre el prediseño, con Δt = 0,005 s, semilla 2028, Vs30 = 270 m/s, ángulo de 0°, muros de mampostería aislados, la histéresis de cada sección y P-Delta (cálculo propio; una sola semilla por escenario: otra semilla da otras cifras). Peso sísmico: 47.988 kN; 785 equipos evaluados, de los cuales 212 están anclados.

| Escenario | PGA del registro (x / y) | Deriva vectorial máxima (entrepiso y vértice) | Cortante basal pico (x / y) y fracción del peso | Elementos que fluyen: total y por nivel (1 / 2 / 3 / 4) | Equipos sueltos que deslizan / se balancean |
|---|---|---|---|---|---|
| Nido de Bucaramanga, como el 10-mar-2015 | 0,037 g / 0,022 g | 0,056 % (entrepiso 3, esquina (−13,0; −19,6)) | 2.942 kN / 2.157 kN (6,1 % / 4,5 %) | 0 | 102 / 0 (máx. 1,3 cm) |
| Falla de Cimitarra | 0,224 g / 0,131 g | 0,304 % (entrepiso 3, esquina (−13,0; −19,6)) | 15.230 kN / 10.850 kN (31,7 % / 22,6 %) | 14: 9 / 2 / 3 / 0 (10 vigas y 4 muros); ninguno más allá de ocupación inmediata | 190 / 11 (máx. 22,6 cm) |
| Sismo local hipotético bajo Yondó | 0,271 g / 0,151 g | 0,416 % (entrepiso 3, esquina (−13,0; −19,6)) | 17.480 kN / 11.750 kN (36,4 % / 24,5 %) | 40: 17 / 10 / 11 / 2 (33 vigas, 2 columnas y 5 muros); ninguno más allá de ocupación inmediata | 260 / 15 (máx. 12,8 cm) |
| Nido de Bucaramanga con escala «nivel de diseño NSR-10» (×18,04, hipotético) | 0,488 g / 0,276 g | 0,841 % (entrepiso 2, esquina (−13,0; −19,6)) | 21.900 kN / 16.690 kN (45,6 % / 34,8 %) | 160: 69 / 31 / 37 / 23 (127 vigas, 28 columnas y 5 muros); 1 extremo más allá de ocupación inmediata | 491 / 1 (máx. 18,7 cm) |
| Falla de Cimitarra a nivel de diseño (×2,85, hipotético) | 0,532 g / 0,304 g | 0,874 % (entrepiso 2, esquina (−13,0; −19,6)) | 21.510 kN / 17.920 kN (44,8 % / 37,4 %) | 177: 77 / 36 / 37 / 27 (140 vigas, 32 columnas y 5 muros); 2 extremos más allá de ocupación inmediata | 533 / 1 (máx. 67,5 cm) |
| Sismo local a nivel de diseño (×2,46, hipotético) | 0,562 g / 0,304 g | 0,884 % (entrepiso 2, esquina (−13,0; −19,6)) | 21.910 kN / 16.970 kN (45,7 % / 35,4 %) | 155: 64 / 33 / 35 / 23 (125 vigas, 25 columnas y 5 muros); 3 extremos más allá de ocupación inmediata | 532 / 1 (máx. 29,0 cm) |

| Escenario | D/C máxima | Muros de mampostería | Energía que entra / disipada en las rótulas |
|---|---|---|---|
| Nido de Bucaramanga, como el 10-mar-2015 | 0,43 (flexión de una viga de la cubierta) | 42 sin daño | 28,1 kJ / 0 |
| Falla de Cimitarra | 0,91 (flexión de una viga de la fachada sur, en la losa del piso 2) | 37 con daño leve, 5 sin daño | 799,8 kJ / 121,7 kJ (15 %) |
| Sismo local hipotético | 0,95 (flexión de una viga de la fachada sur, en la losa del piso 4) | 33 leve, 6 moderado, 3 sin daño | 758,6 kJ / 196,5 kJ (26 %) |
| Nido a nivel de diseño | 1,14 (rotación plástica en la base del muro sur de la escalera sur) | 17 moderado, 13 leve, 12 extenso | 6.241 kJ / 3.927 kJ (63 %) |
| Cimitarra a nivel de diseño | 1,22 (el mismo muro) | 19 moderado, 15 extenso, 8 leve | 6.221 kJ / 4.020 kJ (65 %) |
| Sismo local a nivel de diseño | 1,24 (el mismo muro) | 16 extenso, 15 leve, 11 moderado | 4.707 kJ / 2.953 kJ (63 %) |

**Lectura.** Con los sismos que se esperan, la torre queda prácticamente elástica: el del nido de Bucaramanga la mueve 0,056 % (menos de un séptimo del 0,4 % del umbral de daño) y los corticales cercanos llegan a 0,304 % y 0,416 %, alrededor de ese 0,4 % (que la norma verifica con un sismo menor, Ad = 0,04), con rótulas casi solo en vigas y bases de muro, todas dentro de ocupación inmediata. Lo que sí sufre son los **contenidos y la mampostería**: en el sismo local deslizan 260 equipos sueltos y 6 muros de mampostería tienen daño moderado. Llevado al nivel de diseño de la NSR-10 (hipotético), la deriva llega a 0,84-0,88 %, todavía bajo el 1 %, fluyen 155 a 177 elementos y la base del muro sur de la escalera sur pasa un poco el límite de ocupación inmediata (D/C de 1,14 a 1,24), sin llegar a seguridad de la vida. Por eso el atlas insiste en **anclar los equipos** y en **separar la mampostería** de la estructura (Índice de Seguridad Hospitalaria y NSR-10 A.9).

## 10. Validación

### 10.1 Pruebas con solución exacta (44 pruebas en verde el 25-oct-2026)

| Grupo | Pruebas | Referencia | Resultado |
|---|---|---|---|
| Integrador | T1-T6 (oscilador libre, amortiguado, forzado, escalón, orden de convergencia, balance de energía) | Soluciones cerradas | En verde: período de Newmark exacto con error de 10⁻⁷; orden de convergencia 3,975 y 3,997 (teórico 4); balance de energía cerrado con error de 10⁻¹⁴ |
| Rótulas | T7 (ciclo cuasiestático, bilineal y Clough) | Tabla calculada a mano en la especificación | En verde: los 7 puntos dentro de media unidad de la última cifra y 200 puntos del lazo con error de 10⁻¹⁵ |
| Modelo | T8-T12 y T22 (pórtico de cortante, pórtico de un vano, excentricidad, P-Delta, equilibrio, deriva vectorial) | Fórmulas cerradas y ensamble a mano | En verde: períodos con error menor que 2 × 10⁻⁵; equilibrio en la base con error de 10⁻¹⁴ |
| Movimiento | T13-T16, T19, T19b, T20 (ecuaciones de predicción, espectro NSR-10, síntesis, normalización, espectro de respuesta, continuidad y tendencia con la profundidad, calidad baja) | Valores de prueba de la investigación de amenaza e implementación de referencia en Python | En verde: el espectro objetivo y los acelerogramas coinciden con la referencia en Python con error de 10⁻¹⁵; las intensidades de 24 simulaciones quedan a menos de 7 % de las de la investigación |
| Torre y otros | T17, T18, T21, S1-S6, R1 (determinismo, estructura real, equipos, esquema, períodos del prediseño, amortiguamiento, tiempos) | Prediseño en Python y contrato | En verde: el motor da los mismos períodos que el prediseño; 0 pasos sin converger con la torre real |

### 10.2 Comparación con OpenSees 3.8

Modelo tridimensional con la **misma idealización** (pórticos con nodos propios esclavos del diafragma, rótulas como resortes `Steel01` con la pendiente escalada, Rayleigh con los mismos a0 y a1, P-Delta con columnas de gravedad; openseespy 3.8.0.0). Cálculo propio:

| Qué se compara | Diferencia | Tolerancia |
|---|---:|---:|
| Control 1: un piso con tres pórticos contra la condensación exacta | 8,9 × 10⁻⁶ | 10⁻⁵ |
| Control 2: ciclo de una rótula contra la tabla de T7 | 0,20 % | 0,5 % |
| Torre: períodos de los 6 primeros modos (0,4562 s en el motor y 0,4564 s en OpenSees) | 0,054 % | 1 % |
| Torre elástica (nido_2015): deriva vectorial máxima por piso | 0,16 % | 3 % |
| Torre elástica: cortante basal pico | 0,047 % | 3 % |
| Torre no lineal (sismo local a nivel de diseño): desplazamiento de la cubierta | 0,084 % | 10 % |
| Torre no lineal: deriva vectorial máxima por piso | 0,12 % | 10 % |
| Torre no lineal: elementos que fluyen (índice de Jaccard) | 1,0: los mismos 155 elementos | ≥ 0,8 |
| Torre no lineal: primera fluencia | 3,39 s en los dos | ±0,1 s |
| Torre no lineal: energía amortiguada | 0,071 % | 5 % |

La energía histerética de la corrida no lineal es 2.953,4 kJ en el motor y 2.955,7 kJ en OpenSees.

## 11. Limitaciones e incertidumbres

- **Prediseño, no diseño:** secciones, refuerzo, masas y cimentación son de prediseño (estimación); sin estudio de suelos, la capacidad de los pilotes es supuesta y la base se supone empotrada sobre los dados.
- **Idealización:** diafragmas rígidos; pórticos planos; rótulas concentradas en los extremos (no dentro del vano); núcleos como muros planos con aletas efectivas, sin compatibilidad vertical en las esquinas y sin cambio de resistencia con la carga axial del sismo (interacción P-M en una fase posterior); sin degradación de resistencia (modelo de Ibarra-Medina-Krawinkler fuera de alcance); sin interacción suelo-estructura; sin componente vertical; la rigidez axial de una columna compartida se cuenta en sus dos pórticos.
- **Movimiento:** parámetros de regiones análogas (oeste de Norteamérica, centro de México), calibrados contra ecuaciones de predicción publicadas; sin registros locales para calibrar; las ecuaciones intraplaca se extrapolan a 150 km de profundidad (calibradas hasta ≈ 120-125 km); contexto sismotectónico por confirmar; una sola semilla por escenario.
- **Modelo del edificio en 3D:** el modelo GLB de la torre reparte entrepisos iguales de 4,30 m; el simulador lo oculta y dibuja su propia estructura con los niveles reales (regenerar el GLB queda fuera de alcance).
- **Equipos sin anclar:** bloque rígido con fricción de catálogo (estimación); el anclaje real lo define el diseño de los elementos no estructurales.
- **Costo:** el prediseño que cumple cuesta más que el presupuesto vigente; la diferencia está en el documento 11 (presupuesto) y en el 16 (cantidades del modelo BIM).

## 12. Lo que falta verificar

- NSR-10: tablas de Fa y Fv para suelo D, numeración de A.2.3 y A.2.6, fila 1.c de la Tabla A.3-4 con R0 = 6,0 y Ω0 = 2,5, si el grupo IV pide algo más en amenaza intermedia, Ct y α (Tabla A.4.2-1), exponente k (A.4.3), ajuste del cortante modal (A.5.4.5), rango de escalamiento de registros (A.2.7), deriva vectorial (A.6.3.1), espectro y rigidez del umbral de daño (A.12.3-A.12.4), irregularidades (Tablas A.3-6 y A.3-7), redundancia (A.3.3.8), aletas efectivas de muros (C.21.9.5.2), numerales de C.21, C.15 y del Título H, cargas del Título B.
- Tipo de suelo real (estudio geotécnico con análisis de licuación), capacidad de los pilotes con pruebas de carga y si la cimentación con pilotes cambia la respuesta (interacción suelo-estructura).
- ASCE/SEI 41-17: factores de material esperado para f'c y fy; parámetros «a» y «b» y límites IO, LS y CP de vigas, columnas y muros; longitud de rótula de muros.
- Sismotectónica: centro y profundidad del nido de Bucaramanga, Mw del sismo del 10-mar-2015, distancias a las fallas, magnitudes máximas y ecuaciones de predicción del modelo nacional del SGC.
- Epicentro, profundidad y tipo de magnitud del terremoto del 10-ago-2026 (OPS: San José del Palmar; anexo C: Pereira).
- El cruce de ductos y bandejas bajo las vigas de 0,80 y 0,90 m (quedan 0,40 m sobre el cielo raso en los pisos 2 a 4): pases en las vigas o cielos más bajos, en el diseño de redes.
- La base del muro sur de la escalera sur pasa el límite de ocupación inmediata en los tres escenarios a nivel de diseño (D/C de 1,14 a 1,24): el diseño definitivo debe revisar su refuerzo de borde o su longitud.

## 13. Fuentes

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
- Reglamento Colombiano de Construcción Sismo Resistente NSR-10, Títulos A, B, C y H (Decreto 926 de 2010): <https://www.idrd.gov.co/sites/default/files/documentos/Construcciones/titulo-a-nsr-100.pdf>
- Servicio Geológico Colombiano, Red Sismológica Nacional y mapas de fallas: <https://www.sgc.gov.co>
- Wilson, E. L. y Dovey, H. H. (1972). Three-dimensional analysis of building systems (TABS), Universidad de California, Berkeley (EERC 72-8).
- Giberson, M. F. (1969). Two nonlinear beams with definitions of ductility. *Journal of the Structural Division* (ASCE) 95(ST2).
- Newmark, N. M. (1959). A method of computation for structural dynamics. *Journal of the Engineering Mechanics Division* (ASCE) 85(EM3).
- Nigam, N. C. y Jennings, P. C. (1969). Calculation of response spectra from strong-motion earthquake records. *BSSA* 59(2).
- Uang, C.-M. y Bertero, V. V. (1990). Evaluation of seismic energy in structures. *Earthquake Engineering and Structural Dynamics* 19.
- Mander, J. B., Priestley, M. J. N. y Park, R. (1988). Theoretical stress-strain model for confined concrete. *Journal of Structural Engineering* 114(8).
- Haselton, C. B. et al. (2016). Calibration of model to simulate response of reinforced concrete beam-columns to collapse. *ACI Structural Journal* 113(6).
- Tomaževič, M. (1999). *Earthquake-Resistant Design of Masonry Buildings*. Imperial College Press.
- O'Neill, M. W. y Reese, L. C. (1999) y Brown, D. A. et al. (2010), *Drilled Shafts* (FHWA-NHI-10-016).
- ASCE/SEI 41-17, *Seismic Evaluation and Retrofit of Existing Buildings*, y ASCE/SEI 7-16 (12.3.4.2) (factores de material esperado, límites de rotación y redundancia; numerales por confirmar).
- OpenSees 3.8 (openseespy 3.8.0.0): <https://pypi.org/project/openseespy/3.8.0.0/>
- Datos del atlas: amenaza sísmica de Yondó, prediseño estructural de la torre, escenarios de referencia y validación con OpenSees (carpeta `data/sismo/`), y presupuesto y normas de la torre (`data/proyectos/torre_hospital/`).
