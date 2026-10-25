# Especificación de integración · Torre del hospital: plantas, dotación para la habilitación, recorrido 3D, simulador sísmico y contraste con el proyecto tipo

> Copia en el repositorio: `data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md`. La carpeta `investigacion/` que cita este documento quedó copiada así: `data/proyectos/torre_hospital/fuentes_investigacion/` (normas, proyecto tipo y mapa del código; `res3100_urgencias_e_internaci_n.json` → `res3100_urgencias_e_internacion.json`, `res3100_apoyo_diagn_stico.json` → `res3100_apoyo_diagnostico.json`) y `data/sismo/fuentes_investigacion/` (amenaza e implementación de referencia `sim.py`, `gmpe.py`, `build_amenaza.py`).

> Versión 2 · 23 de octubre de 2026 · arquitectura de software y de datos del repositorio `trabajemosjuntos` (Atlas Yondó 2028). Corrige la versión 1 con las 81 observaciones de la revisión (22 de física, 27 de normativa y 32 de integración) de física, normativa e integración (ver «Decisiones de la revisión», al final).
> Este documento es el **contrato** entre cinco equipos que trabajan en paralelo. Fija nombres de archivo exactos, formatos JSON con ejemplos, firmas de las API JavaScript y Python, quién es dueño de cada archivo, el orden de dependencias y los criterios de aceptación. Si un equipo necesita cambiar un contrato, propone el cambio por escrito al dueño del archivo y a D (integración); nadie cambia un contrato por su cuenta.
>
> Insumos leídos completos: `investigacion/res3100_urgencias_e_internaci_n.json`, `res3100_consulta_y_ambulatorio.json`, `res3100_apoyo_diagn_stico.json`, `normas_4725_1732.json`, `proyecto_tipo_contraste.json`, `amenaza.json` y `mapa_codigo.json` (carpeta `scratchpad/investigacion/`), más `data/sismo/ESQUEMA.md`, `data/proyectos/torre_hospital/{programa,dotacion,normas,laboratorio,presupuesto,proyecto_tipo}.json`, `data/edificios/torre_hospital.json`, `docs/11` y `docs/09`, `web/js/scenes/torre.js`, `web/js/core.js`, `web/index.html` (sección `#v-torre`), `scripts/build_data.py`, `scripts/build_site.py`, `Caddyfile` y `.github/workflows/pages.yml`.

---

## 0. Cómo leer este documento

- **Convenciones del repositorio (obligatorias en datos y en la web).** Todo texto para ciudadanos va en español claro. Cada cifra dice su tipo: **dato oficial** (copiado de una fuente), **cálculo propio** (operación sobre datos citados, con el método a la vista) o **estimación** (supuesto con rango). Cada requisito normativo cita norma, artículo o numeral y URL. Lo que no se pudo confirmar en la fuente dice **por confirmar**; no se inventan numerales.
- **Límite de la investigación de base (23-oct-2026).** Ninguna página `.gov.co` se pudo abrir desde el entorno de investigación (el proxy rechazó Supersalud, MinSalud, Función Pública, ICBF, Cancillería e Invima; WebFetch no resolvió DNS). La revisión de esta versión tampoco pudo cotejar el normograma de Supersalud (se agotó el cupo de búsquedas web de la corrida). Los textos de la Res. 3100, del Decreto 4725 y de las resoluciones de 2025-2026 vienen de fragmentos de compilaciones oficiales vistos a través del buscador, de guías secundarias o de paráfrasis. **Toda cita normativa que llegue a la web lleva su nivel de verificación** (ver 4.2) y la leyenda «cotejar con el Diario Oficial antes de radicar».
- **Palabras clave.** «Debe» = criterio de aceptación. «Conviene» = recomendado, no bloquea.
- **Marco de coordenadas.** Siempre el de la especificación del edificio: `x` al este, `y` al norte, `z` arriba, metros desde el ancla (lat 7,005271; lon −73,914597) (`programa.json → implantacion.marco_de_coordenadas`). En three.js: `(X, Y, Z) = (x, z, −y)`; un giro antihorario en planta de ángulo `θ` es `rotation.y = θ` (cálculo propio verificado con `frame()` de `scripts/modelos/build_edificios.mjs:45` y `torre.js:125,135`).
- **Ángulos y alturas (decisión de este contrato).** Todo ángulo en planta (`rotacion_z`, `mirando_deg`, `rumbo_deg`, `angulo_deg` del sismo) se mide **en sentido antihorario desde +x (el este)**. La `z` de una unidad del inventario es la **altura sobre el piso terminado de su nivel**; en three, `Y = nivel.z + z` (`aThree` recibe el nivel). Las cotas absolutas solo se usan en la planta (`niveles[].z`) y en la estructura.

### 0.1 Qué se le responde al usuario con este trabajo

| Pedido literal | Entregable | Equipo |
|---|---|---|
| «contrastes [la torre] con el proyecto tipo para este alcance» | `data/proyectos/torre_hospital/proyecto_tipo_contraste.json`, tarjeta de contraste, capa de colores en el recorrido y caja de área equivalente en 3D, sección nueva en `docs/11` | E |
| «se pueda navegar en 3D», «entrar en el edificio, andar por cada zona» | Plantas por piso (`data/edificios/torre_hospital_plantas.json`) y modo **Recorrer por dentro** en primera persona | B (plantas), C (recorrido) |
| «dotado cada servicio con los equipos para la habilitación», «inventario de dotación por servicio … según la norma», «pongas esto en cada lugar en 3D», «ir viendo la dotación» | `inventario_dotacion.json` (cada unidad física ubicada, con su exigencia y su nivel de verificación), `habilitacion.json` (matriz exigencia → ítems → estado de **cumplimiento en dotación e infraestructura**; no evalúa talento humano, historia clínica ni interdependencia, así que no dictamina si un servicio se puede habilitar), catálogo 3D de equipos y fichas en el recorrido | B (datos), C (3D y tarjeta) |
| «toda la dotación que requiere la torre con sus respectivos ítems e implementos internos» | Unidades con `contenido` (carro de paro, equipos de parto, kits, instrumental) desde `implementos.json`; los equipos biomédicos de los kits como unidades componentes con su registro | B, C |
| «busca las normas 4725 y el manual de habilitación con la 3100 de 2019 y la 1732 de 2026» | Decreto 4725 de 2005 aplicado a cada unidad (clase de riesgo, registro, mantenimiento); Res. 3100 como norma vigente; la Res. 1732 de 2026 **revocada** por la Res. 2080 del 8-sep-2026 (se informa, no se aplica) | B, E |
| «simulador … esfuerzos estructurales … variar la escala de Richter y la profundidad», «no animado … que literal se vean las variables y el comportamiento físico» | Motor sísmico en Web Worker (síntesis estocástica + análisis no lineal en el tiempo), vista con deformada real, demanda/capacidad por elemento, rótulas, derivas vectoriales, cortante basal, energía y espectros; la profundidad cambia la distancia y el tipo de sismo de forma continua; el deslizador recorre los pasos calculados | A (motor), D (vista) |
| «física realista del más alto nivel de simulación y aplicada» | Método de Boore (2003) para el movimiento, modelo pseudotridimensional no lineal (Wilson y Dovey) con rótulas de Giberson y propiedades esperadas, Newmark + Newton-Raphson, P-Delta con el peso de cada nivel, amortiguamiento sin componente espuria en las rótulas, balance de energía cerrado, validación contra soluciones cerradas y contra OpenSees 3.8 con la misma idealización | A |

---

## 1. Decisiones que fijan el contrato

### 1.1 Normas: qué rige

| Norma | Estado al 23-oct-2026 | Cómo entra en el trabajo | Verificación |
|---|---|---|---|
| Res. 3100 de 2019 (Manual de inscripción de prestadores y habilitación) con sus modificaciones: 2215 de 2020, 1317 de 2021, **una de 2022 (1138 según la investigación de urgencias; 1410 según `normas.json`: por confirmar en el normograma de Supersalud)**, 544 de 2023, 465 de 2025 y 914 de 2025, entre otras | **Vigente** «sin solución de continuidad» (texto citado de la Res. 2080 de 2026) | Base de la matriz de cumplimiento en dotación e infraestructura (4.8) | Compilaciones de Cancillería e ICBF vistas por buscador; cotejar con el normograma de Supersalud. La lista de modificaciones no se pudo cotejar el 23-oct-2026 (el proxy rechazó `normograma.supersalud.gov.co` y se agotó el cupo de búsquedas): queda en la sección 15 |
| Res. 1732 de 2026 (nuevo manual, Tomos I y II, 5-ago-2026) | **Revocada en su integridad** por la Res. 2080 del 8-sep-2026; nunca se publicó en el Diario Oficial (oficio de la Imprenta Nacional 20261400007931 del 3-sep-2026, según las fuentes citadas) | Se informa en la web y en `docs/15`; **no se usa como requisito**. El archivo `res3100_consulta_y_ambulatorio.json` dice que estaba en transición: ese dato quedó superado y `normalizar_exigencias.py` no lo propaga (4.2) | Sisjur (Alcaldía de Bogotá) y prensa especializada; publicación de la 2080 en el Diario Oficial por confirmar |
| Decreto 4725 de 2005 (registro sanitario, permiso de comercialización y vigilancia de dispositivos médicos) | Vigente; modificado sobre todo por los Decretos 3275 de 2009 y 582 de 2017; hay un proyecto de reemplazo sin expedir | Clase de riesgo (arts. 5-7, 18 reglas), registro INVIMA, prohibición de usados IIb y III, mantenimiento por personal inscrito (art. 39), posventa (art. 38), tecnovigilancia (art. 61 y Res. 4816 de 2008) | Extractos por buscador; reglas 3, 4, 5, 8 y 14 no leídas |
| Res. 914 de 2025 (manual de reprocesamiento de dispositivos, DMER) | Rige desde el 3-ene-2027 (art. 15); su art. 14 deroga los numerales de esterilización de la 3100 | Las exigencias de esterilización llevan `vigencia_hasta: "2027-01-02"`. Como la torre abriría hacia abril de 2030 (`docs/11`, «Cuándo»), la matriz se calcula en dos cortes (4.8, `fecha_referencia`): al 23-oct-2026 con la 3100 y a la apertura con la 914, en `por_confirmar` hasta leer el manual DMER | Compilación vista por buscador; una sola fila de la 914 en las investigaciones, y es paráfrasis |
| Res. 1811 de 2025 (radiaciones ionizantes) | Rige desde el 6-mar-2026 según MinSalud; derogó la Res. 482 de 2018 | Licencia de rayos X y periapical, dosimetría, control de calidad (exigencias documentales); corrige la cita a la 482 en `presupuesto.json` | Página de MinSalud vista por buscador |
| Res. 2065 de 2025 (sedes transitorias en emergencias) | Vigente; un proyecto de octubre de 2026 la llevaría al manual | Marco de la sala de expansión (no es servicio de la 3100) | Sisjur y prensa |
| Res. 1633 de 2025 (marco técnico de infraestructura) | Vigente | Áreas mínimas, módulo de 1,20 m, corredores, puertas, señalización por colores | Ya en `normas.json` |
| NSR-10 (títulos A, B, C, J, K) | Vigente | Prediseño estructural grupo IV, deriva, evacuación | Valores de Yondó ya en el repo; varios numerales por confirmar (ver `amenaza.json → nsr10`) |

### 1.2 Geometría de la torre (dato del proyecto, `programa.json`)

- Pisos 1 a 3: 21,60 × 42,00 m; `x ∈ [−13,0; 8,6]`, `y ∈ [−19,6; 22,4]`. Piso 4: `y ∈ [−7,6; 22,4]` (retrocede 12 m en el sur).
- **Ejes con nombre (decisión de este contrato, antes solo inferida del ejemplo de `ESQUEMA.md`):** líneas de x constante (van de sur a norte) `A = −13,0`, `B = −5,8`, `C = 1,4`, `D = 8,6`; líneas de y constante (van de occidente a oriente) `1 = −19,6`, `2 = −12,4`, `3 = −7,6`, `4 = 0,8`, `5 = 8,0`, `6 = 14,0`, `7 = 22,4`. Luces en x: 7,20 / 7,20 / 7,20 m; en y: 7,20 / 4,80 / 8,40 / 7,20 / 6,00 / 8,40 m.
- **Niveles (únicos para plantas, estructura, recorrido y vista sísmica):** piso 1 = 0,0; piso 2 = 4,5; piso 3 = 8,7; piso 4 = 12,9; cubierta del piso 4 = 17,1; cubierta del piso 3 (sur) = 12,9. El GLB actual reparte 4,30 m iguales (`build_edificios.mjs:559`): por eso **el recorrido y la vista sísmica ocultan `obra_nueva` del GLB** y dibujan su propia envolvente. Regenerar el GLB con los niveles reales queda **fuera de alcance** (ver 14).
- Núcleos (`programa.json → implantacion.nucleos_verticales`): escalera norte `x 3,1-8,6 · y 14,0-22,4`; escalera sur `x 3,1-8,6 · y −7,6-0,8`; ascensores `x 3,1-6,1 · y 1,6-7,2` con vestíbulo `x 6,1-8,6 · y 0,8-8,0`; montacargas de muestras entre la toma (piso 1, suroccidente) y el laboratorio (piso 2).
- Bloque técnico: `x −19,5-11,9 · y −24,8 a −20,8`, base −1,50 m (estimación del programa; el GLB lo pone en 0,0). Es estructura independiente con junta.
- Estructura (dato del prediseño en `presupuesto.json`, capítulo 3): pórticos de concreto de 28 MPa con **muros en los núcleos** («sistema combinado»), columnas de 0,60 × 0,60 m (28 en pisos 1-3 y 20 en el piso 4), ≈ 45 m lineales de muro de 0,30 m × 17,1 m, losa nervada (0,24 m³ de concreto por m² de placa con vigas), pilotes de 0,60 m bajo 28 dados. Juntas solo con el edificio actual, la galería y el bloque técnico: **la torre es un solo bloque con retroceso** (no hay junta en `y = −7,6`; por confirmar con el diseño). El retroceso deja el piso 4 con 30 m en y frente a 42 m de los pisos 1-3 (42/30 = 140 %, cálculo propio) y los núcleos están todos al oriente: son candidatos a irregularidad geométrica en altura (3A) y torsional (1aP/1bP) que A debe evaluar (7.2). «Sistema combinado» es el nombre del presupuesto; el sistema de la NSR-10 (dual o combinado) lo fija A en el paso 0 del prediseño (7.2).

### 1.3 Identificadores estables

| Objeto | Formato | Ejemplo | Regla |
|---|---|---|---|
| Recinto del programa | `P{piso}-A{fila:03d}-{k:02d}` | `P1-A015-02` | `fila` = índice (base 0) de la fila en `programa.json → ambientes`; `k` = 1…`cantidad`. El generador falla si `programa.json` se reordena (compara nombre y piso de la fila). Bloque técnico: `BT-A{fila:03d}-01`. |
| Circulación que no está en el programa | `P{piso}-CIRC-{nn:02d}` | `P3-CIRC-01` | Corredores, esclusas no programadas |
| Muro | `P{piso}-M-{nnnn}` | `P2-M-0137` | Se numeran en el orden del generador; **no** son estables entre versiones: nadie debe guardarlos fuera de la planta |
| Puerta / ventana | `P{piso}-PT-{nnn}` / `P{piso}-VN-{nnn}` | | Igual que muros |
| Línea de dotación | `L-{servicio}-{tipo}-{h6}` | `L-urgencias-e-3f2a1c`, `L-fijo-f-91b0de`, `L-laboratorio-c-0a77e2`, `L-hospitalizacion-x-5d13f8` | `tipo`: `e` equipo, `m` mobiliario, `f` equipamiento fijo, `c` equipo de `laboratorio.json`, `x` cierre de brechas. `h6` = 6 primeros caracteres hexadecimales del SHA-1 (UTF-8) de `origen\|servicio\|tipo\|nombre exacto`, con `tipo` en su letra (ejemplos calculados en el Anexo A.2). **No depende de la posición en la lista**: reordenar, agregar o quitar líneas no cambia los ids de las demás. Cada regla escrita a mano (`reglas_ubicacion.json`, `reglas_exigencias.json`, `cubre_con`) trae además el `nombre` de la línea, y `generar_inventario.py` falla si el nombre de la línea apuntada no coincide |
| Unidad física | `U-{servicio}-{h6}-{k:03d}` | `U-urgencias-3f2a1c-001` | `h6` = el de su línea; `k` = 1…cantidad. Componentes de una unidad (4.4, 4.7.3): `{id de la unidad}-c{n}` (`U-partos-7e21aa-001-c2`). La regla I1 falla si dos líneas producen el mismo `h6` (colisión) |
| Exigencia normativa | `EX-{SRV}-{nnn}` | `EX-URG-007`, `EX-TOD-C03` | `SRV` ∈ URG, HOS, PAR, EST, EXP, CEX, ODO (odontología del archivo de consulta), TEL, VAC, FAR, TER, LAB, TOM, IMG, ROD (radiología odontológica del archivo de apoyo), TIC. `nnn` = posición, contando desde 1, de la fila dentro de (archivo de investigación, servicio). Las filas de «todos los servicios» llevan prefijo por archivo: `EX-TOD-C{nn}` (consulta y ambulatorio) y `EX-TOD-A{nn}` (apoyo diagnóstico); el archivo de urgencias no tiene filas propias de «todos los servicios». La clave canónica es `origen` (4.2); los ids citados a mano se validan contra ella |
| Elemento estructural | ver 7.2 | `C-A3-1@X`, `VX-3-AB-1`, `MY-D6-1` | |

### 1.4 Áreas: a ejes y libres

Las áreas del programa son «útiles» con 33 % aparte para muros y circulación; los ambientes se modularon a ejes (consultorio de 3,60 × 3,60 = 12,96 m²). Con 0,12 m de muro el área libre de ese consultorio es ≈ 12,1 m². Este contrato fija:

- `area_ejes_m2`: área del polígono trazado sobre los ejes de los muros. **Debe** ser ≥ `m2_unitario` del programa − 0,05 m² y ≥ el mínimo de la Res. 1633 de ese ambiente.
- `area_libre_m2`: área interior entre caras de muro. Si queda bajo el mínimo de la Res. 1633, el validador **avisa** (no falla) y el recinto lleva la nota «por confirmar si el mínimo de la Res. 1633 se mide libre o a ejes (Anexo 1, definiciones)». Los pisos 1 (holgura 2,5 m²) y 2 (5,4 m²) no tienen espacio para agrandar todos los ambientes que están exactos en el mínimo (reanimación 20, ERA 9, EDA 12, yesos 9, aislamiento 16, observación 12…).

### 1.5 Estado de los datos que se publican

La planta es un **anteproyecto ilustrativo** (estimación) que respeta la retícula, los núcleos, la zonificación y las áreas del programa; no reemplaza el diseño arquitectónico firmado. La web lo dice en el recorrido («Planta ilustrativa: el diseño real lo hace el arquitecto con matrícula») y en `docs/15`.

---

## 2. Mapa de archivos y propietarios

Un archivo tiene **un solo dueño**. Los archivos compartidos se editan solo dentro de secciones marcadas creadas por su dueño (2.2).

### 2.1 Archivos nuevos o modificados por equipo

| Equipo | Archivo | Tipo | Nota |
|---|---|---|---|
| **A · Motor sísmico** | `data/sismo/ESQUEMA.md` | editar | Cambios del 7.1 |
| A | `data/sismo/amenaza.json` | nuevo | Desde `data/sismo/fuentes_investigacion/amenaza.json`, sin cambiar números; agrega lo marcado en 7.3 |
| A | `data/sismo/torre_hospital_estructura.json` | generado | Por `scripts/sismo/estructura_torre.py` |
| A | `data/sismo/validacion_opensees.json` | generado | Por `scripts/sismo/validar_opensees.py` |
| A | `data/sismo/fuentes_investigacion/` | nuevos (ola 0, antes de abrir ramas) | Copia literal de `investigacion/amenaza.json` y de `sismo_calc/sim.py` y `gmpe.py` (implementación de referencia de la investigación) |
| A | `web/js/sismo/movimiento.js`, `modelo.js`, `integrador.js`, `motor.js`, `trabajador.js` | nuevos | `motor.js` reúne la lógica que usan el trabajador y el respaldo (7.5). Puede añadir `web/js/sismo/fft.js`, `azar.js`, `algebra.js`, `histeresis.js` |
| A | `scripts/sismo/estocastico.py`, `estructura_torre.py`, `test_motor.mjs`, `validar_opensees.py`, `exportar_caso.mjs`, `validar_resultado.mjs`, `qa_worker.mjs`, `requisitos_validacion.txt` | nuevos | `qa_worker.mjs` importa `scripts/qa/comun.mjs` (D) |
| A | `scripts/fixtures/torre/estructura_min.json`, `resultado_min.json`, `serie_elemento_min.json`, `trabajador_simulado.js` | nuevos | Anexo A.3 y A.4; `trabajador_simulado.js` responde los mensajes del 7.5 con esos fixtures |
| **B · Plantas e inventario** | `data/edificios/torre_hospital_trazado.json` | nuevo (a mano) | El diseño: rectángulos y puertas (3.2) |
| B | `data/edificios/torre_hospital_plantas.json` | generado | Por `scripts/torre/generar_plantas.py` |
| B | `data/proyectos/torre_hospital/reglas_planta.json`, `reglas_ubicacion.json`, `reglas_exigencias.json`, `catalogo_equipos.json`, `implementos.json` | nuevos (a mano) | Insumos declarativos |
| B | `data/proyectos/torre_hospital/fuentes_investigacion/` | nuevos (ola 0, antes de abrir ramas) | Copia literal de `res3100_urgencias_e_internacion.json`, `res3100_consulta_y_ambulatorio.json`, `res3100_apoyo_diagnostico.json`, `normas_4725_1732.json` (nombres sin caracteres raros). Los datos superados que traen (Res. 482 de 2018, «transición» de la 1732) se corrigen al normalizar (4.2), no en la copia |
| B | `data/proyectos/torre_hospital/exigencias_3100.json`, `inventario_dotacion.json`, `inventario_dotacion.csv`, `habilitacion.json` | generados | Cada uno con `insumos_sha1` (10.1) |
| B | `data/proyectos/torre_hospital/dotacion.json` | editar | Solo lo del 4.7 |
| B | `data/proyectos/torre_hospital/presupuesto.json` | editar | Solo textos: «Res. 482 de 2018» → «Res. 1811 de 2025» (ítem 4.07 e indirecto de puesta en marcha) |
| B | `scripts/torre/comun.py`, `generar_plantas.py`, `validar_plantas.py`, `normalizar_exigencias.py`, `generar_inventario.py`, `validar_inventario.py`, `test_torre.py` | nuevos | Python 3.12, solo biblioteca estándar |
| B | `scripts/fixtures/torre/plantas_min.json`, `dotacion_min.json`, `inventario_min_datos.json`, `inventario_min.json`, `habilitacion_min.json` | nuevos | Anexo A.1 y A.2 |
| **C · Catálogo 3D y recorrido** | `web/js/equipos3d.js` | nuevo | 5.3 |
| C | `web/js/scenes/torre/recorrido.js`, `planta3d.js`, `controles_fp.js`, `minimapa.js`, `habilitacion.js` | nuevos | 6 |
| C | `scripts/qa/recorrido_qa.mjs` | nuevo | Importa `scripts/qa/comun.mjs` |
| **D · Vista sísmica e integración** | `web/js/scenes/torre.js` | editar | Dueño único |
| D | `web/js/scenes/torre/sismo.js`, `estructura3d.js`, `graficas.js` | nuevos | 8 |
| D | `web/js/scenes/torre/textos.js` | nuevo (ola 0) | Exporta `limpio`, `esc` y `escH` (hoy privadas de `torre.js`); `torre.js`, C y E lo importan (13.6) |
| D | `web/js/scenes/torre/_relleno.js` | nuevo (ola 0) | Único módulo de relleno («en construcción») mientras falten los de C y E (12.1) |
| D | `web/index.html` | editar | Dueño único; bloques marcados para C y E |
| D | `scripts/build_data.py` | editar | Exporta todo lo del 10 |
| D | `web/data/torre_*.json`, `web/data/sismo_*.json` | generados | Por `build_data.py` |
| D | `scripts/qa/comun.mjs`, `scripts/qa/LEEME.md`, `scripts/qa/torre_qa.mjs` | nuevos (`comun.mjs` y `LEEME.md` en la ola 0) | `comun.mjs`: servidor estático y desvío de jsdelivr, cdnjs y Google Fonts a copias locales (`--vendor <carpeta>`; módulo de Playwright en `PLAYWRIGHT_MODULE`). `LEEME.md`: cómo obtener three@0.160.0 y gsap@3.12.5 con `npm pack` y Playwright con Chromium. `torre_qa.mjs`: QA global de la vista |
| D | `web/js/core.js` | **congelado** | Solo D, solo si es imprescindible, con QA de las 10 vistas (ver 6.9) |
| **E · Contraste y documentos** | `data/proyectos/torre_hospital/proyecto_tipo_contraste.json` | nuevo | Desde `investigacion/proyecto_tipo_contraste.json`, con `ambientes_programa` exactos y los veredictos partidos (9.1) |
| E | `data/proyectos/torre_hospital/normas.json` | editar | Agrega normas y corrige `servicios_3100` (9.3) |
| E | `data/proyectos/torre_hospital/proyecto_tipo.json` | editar mínimo | Solo el campo nuevo `escalamiento_a_torre.estado` (9.1) |
| E | `data/proyectos/torre_hospital/programa.json` | editar mínimo | Solo `proyectos_tipo[1].costo_de_referencia` (costo por m² $4.555.806 sobre 320,6 m², con la nota del 9.1); el resto está congelado en esta iteración |
| E | `web/js/scenes/torre/contraste.js` | nuevo | 9.2 |
| E | `scripts/torre/validar_contraste.py`, `scripts/torre/verificar_cifras_docs.py` | nuevos | |
| E | `docs/11-torre-hospital-nivel-1.md`, `docs/09-motor-3d-y-modelos.md`, `docs/14-simulacion-sismica.md`, `docs/15-dotacion-y-habilitacion.md`, `README.md` (tabla de documentos), `docs/anexos/C-hospital-2028.md` (solo la nota del epicentro) | editar/nuevos | 11 |

Ningún equipo toca `web/js/data.js` (lo genera `build_data.py`), `web/js/main.js`, las demás escenas ni los GLB. `docs/09` (E) remite a `scripts/qa/LEEME.md` (D) para preparar las herramientas de QA; nada de lo que piden los criterios del 13 puede depender de archivos que estén solo en el *scratchpad* de una sesión o en `/opt` de una máquina.

### 2.2 Archivos compartidos: protocolo

- **`web/index.html` (dueño D).** En la ola 0, D crea dentro del `<style>` tres bloques vacíos y no los toca después:
  ```css
  /* >>> torre-recorrido (equipo C) */
  /* <<< torre-recorrido */
  /* >>> torre-sismo (equipo D) */
  /* <<< torre-sismo */
  /* >>> torre-contraste (equipo E) */
  /* <<< torre-contraste */
  ```
  C y E escriben su CSS solo entre sus marcas, usando los tokens existentes (`--good`, `--warn`, `--bad`, `--data`, `--s1…--s8`, fondos y textos de `:root`) y las clases existentes (`.seg`, `.ctl`, `.tiles`, `.fold`, `table.fichas`, `svg.mr-chart`, `.nav3d`). El HTML lo pone D según el 10.3.
- **`web/js/scenes/torre.js` (dueño D).** C y E entregan módulos con las firmas de este documento; D los importa de forma perezosa y los llama. Nadie más edita `torre.js`.
- **`scripts/build_data.py` (dueño D).** D implementa todas las exportaciones del 10.1 y las hace tolerantes a archivos que todavía no existen (si falta un insumo, no escribe ese archivo y sigue). Los dueños de los datos no editan este script.
- **`data/proyectos/torre_hospital/dotacion.json` (dueño B).** E y D lo leen. Si E necesita un cambio (por ejemplo, el posible duplicado de $67,5 M del kit de examen), lo pide a B.
- **`web/js/core.js`.** Congelado. El recorrido hace su propio *raycast* (no hace falta que `_hit` devuelva `instanceId`), vacía `st.pickables` mientras está activo y maneja la cámara a través de `OrbitControls` sin desactivarlos (6.8).
- **Contenedores de la vista (`torre.panel`, `torre.hud`, `torre.ficha`).** Cada modo escribe solo en su contenedor hijo (`[data-slot="torre.panel.recorrido"]`, `torre.panel.sismo`, `torre.hud.recorrido`, `torre.hud.sismo`, `torre.ficha.modo`), que D crea en la ola 0 (10.3). Nadie hace `innerHTML` sobre el contenedor padre.

---

## 3. Contrato 1 · PLANTAS

### 3.1 Archivos y flujo

```
data/edificios/torre_hospital_trazado.json   (B, a mano: el diseño)
data/proyectos/torre_hospital/reglas_planta.json (B, a mano: espesores, mínimos, puertas, zonas, accesos permitidos)
data/proyectos/torre_hospital/programa.json  (congelado)
        │  python3 scripts/torre/generar_plantas.py
        ▼
data/edificios/torre_hospital_plantas.json   (generado: muros, vanos, polígonos libres, ventanas, áreas, grafo)
        │  python3 scripts/torre/validar_plantas.py   (sale 1 si hay errores duros)
        ▼
web/data/torre_plantas.json                   (build_data.py, forma compacta del 3.3)
```

La planta no se dibuja con un algoritmo de acomodo automático: es un diseño (anteproyecto) escrito como datos compactos en el trazado; el generador deriva todo lo demás y el validador lo comprueba. Conviene que B use un ayudante opcional de franjas por zona para la primera propuesta, pero lo que se versiona es el trazado.

### 3.2 `torre_hospital_trazado.json` (insumo de B)

```json
{
  "id": "torre_hospital_trazado",
  "version": 1,
  "tipo_dato": "estimacion",
  "estado": "Anteproyecto ilustrativo para el atlas; no reemplaza el diseño arquitectónico firmado (Res. 485 de 2025, num. 7.1.2.6)",
  "niveles": [
    {
      "id": "P1", "piso": 1,
      "recintos": [
        { "fila": 15, "k": 1, "rect": [-13.0, 15.6, -9.4, 19.2] },
        { "fila": 16, "k": 1, "poligono": [[-9.4, 15.6], [-3.4, 15.6], [-3.4, 19.2], [-9.4, 19.2]] },
        { "circ": 1, "nombre": "Corredor transversal de urgencias", "tipo": "circulacion", "rect": [-13.0, 13.05, 3.1, 15.6], "evacuacion": true, "camillas": true }
      ],
      "puertas": [
        { "entre": ["P1-A015-01", "P1-CIRC-01"], "pos": 0.5, "abre": "adentro" },
        { "entre": ["P1-A003-01", "exterior"], "lado": "o", "pos": [-13.0, 15.0], "ancho": 1.8, "tipo": "automatica" }
      ],
      "sin_ventana": ["P1-A057-01"]
    }
  ]
}
```

- `fila` = índice en `programa.json → ambientes`; `rect` = `[x0, y0, x1, y1]` a ejes; `poligono` para formas en L (solo ortogonales). Coordenadas múltiplo de 0,05 m (duro) y, cuando se pueda, de 0,60 m desde los ejes (aviso).
- `puertas.entre` usa ids de recinto o `"exterior"`; `pos` es la fracción a lo largo del borde común (0-1) o un punto `[x, y]`; `ancho` es opcional (si falta, lo pone la regla de su categoría, 3.4); `abre` ∈ `adentro | afuera | corrediza | doble`.
- Las **ventanas** las pone el generador en los bordes de fachada de los recintos que no estén en `sin_ventana`: franja con antepecho de 1,0 m y 2,0 m de alto (igual que el GLB, `build_edificios.mjs:601`), en paños del ancho del borde menos 0,30 m a cada lado.

### 3.3 `torre_hospital_plantas.json` (generado)

```json
{
  "id": "torre_hospital_plantas",
  "version": 1,
  "generado_por": "scripts/torre/generar_plantas.py",
  "fecha": "2026-10-23",
  "tipo_dato": "estimacion",
  "estado": "Anteproyecto ilustrativo …",
  "marco": { "ancla": { "lat": 7.005271, "lon": -73.914597 }, "ejes": "x este, y norte, z arriba; metros", "a_three": "(X, Y, Z) = (x, z, -y)" },
  "modulo_m": 1.2,
  "reticula": {
    "ejes_x": [ { "id": "A", "x": -13.0 }, { "id": "B", "x": -5.8 }, { "id": "C", "x": 1.4 }, { "id": "D", "x": 8.6 } ],
    "ejes_y": [ { "id": "1", "y": -19.6 }, { "id": "2", "y": -12.4 }, { "id": "3", "y": -7.6 }, { "id": "4", "y": 0.8 }, { "id": "5", "y": 8.0 }, { "id": "6", "y": 14.0 }, { "id": "7", "y": 22.4 } ]
  },
  "tipos_muro": {
    "fachada":  { "espesor_m": 0.20, "material": "ladrillo a la vista 15 cm con pañete interior", "fuente": "presupuesto.json 4.03" },
    "nucleo":   { "espesor_m": 0.30, "material": "concreto 28 MPa (estructural)", "fuente": "presupuesto.json 3.02" },
    "bloque":   { "espesor_m": 0.15, "material": "bloque de arcilla No. 5 con pañete", "fuente": "presupuesto.json 4.01" },
    "liviano":  { "espesor_m": 0.12, "material": "placa de yeso RH doble cara", "fuente": "presupuesto.json 4.02" },
    "plomado":  { "espesor_m": 0.20, "material": "bloque con lámina de plomo ≈ 2 mm (cálculo de blindaje pendiente)", "fuente": "presupuesto.json 4.07" }
  },
  "niveles": [
    {
      "id": "P1", "piso": 1, "z": 0.0, "altura_entrepiso_m": 4.5, "altura_libre_m": 3.0,
      "contorno": [[-13.0, -19.6], [8.6, -19.6], [8.6, 22.4], [-13.0, 22.4]],
      "columnas": [ { "id": "A1", "x": -13.0, "y": -19.6, "b": 0.6, "h": 0.6 } ],
      "recintos": [
        {
          "id": "P1-A015-01", "fila": 15, "k": 1, "de": 2,
          "ambiente": "Consultorio de urgencias con unidad sanitaria",
          "servicio_programa": "Urgencias",
          "grupo_1633": "atencion_inmediata",
          "zona_acceso": "semirrestringido",
          "tipo": "recinto",
          "poligono": [[-13.0, 15.6], [-9.4, 15.6], [-9.4, 19.2], [-13.0, 19.2]],
          "poligono_libre": [[-12.9, 15.66], [-9.46, 15.66], [-9.46, 19.14], [-12.9, 19.14]],
          "area_ejes_m2": 12.96, "area_libre_m2": 11.97,
          "area_programa_m2": 13.0,
          "minimo_1633": { "m2": 10.0, "lado_m": 2.5, "cita": "Res. 1633 de 2025, Anexo 1, Cuadro 92", "tipo_dato": "dato oficial" },
          "acceso": ["P1-CIRC-01"],
          "puertas": ["P1-PT-014"],
          "ventanas": ["P1-VN-006"],
          "climatizacion": { "presion": "+", "fuente": "normas.json → climatizacion_cuadro4 (Urgencias)" },
          "notas": []
        }
      ],
      "nucleos": [ { "id": "P1-NUC-ESC-N", "tipo": "escalera", "recinto": "P1-A059-01", "poligono": [[3.1, 14.0], [8.6, 14.0], [8.6, 22.4], [3.1, 22.4]] } ],
      "muros": [
        { "id": "P1-M-0001", "a": [-13.0, 15.6], "b": [-9.4, 15.6], "tipo": "liviano", "espesor": 0.12, "altura": 3.0, "lados": ["P1-CIRC-01", "P1-A015-01"], "estructural": false }
      ],
      "puertas": [
        { "id": "P1-PT-014", "muro": "P1-M-0001", "centro": [-11.2, 15.6], "ancho": 1.0, "alto": 2.1, "hojas": 1,
          "desde": "P1-CIRC-01", "hacia": "P1-A015-01", "abre": "adentro", "bisagra": "izquierda", "tipo": "batiente",
          "categoria": "consultorio", "cita_ancho": "Res. 1633, Cuadro 1 (normas.json → puertas_ancho_min_m)" }
      ],
      "ventanas": [ { "id": "P1-VN-006", "muro": "P1-M-0002", "centro": [-13.0, 17.4], "ancho": 3.0, "antepecho": 1.0, "alto": 2.0 } ],
      "conexiones_verticales": [
        { "id": "ESC-N", "tipo": "escalera", "pisos": [1, 2, 3, 4], "puntos": { "1": [5.85, 16.2], "2": [5.85, 16.2] } },
        { "id": "ASC", "tipo": "ascensor", "pisos": [1, 2, 3, 4], "puntos": { "1": [7.35, 4.4] } },
        { "id": "ESC-P", "tipo": "escalera_abierta", "pisos": [1, 2], "puntos": { "1": [-8.0, -15.0], "2": [-8.0, -15.0] } }
      ],
      "entradas_recorrido": [ { "id": "principal", "punto": [-12.2, -13.0], "mirando_deg": 0, "nombre": "Puerta principal" } ],
      "obstaculos_recorrido": []
    }
  ],
  "grupos_1633": {
    "atencion_inmediata": { "nombre": "Atención inmediata", "color_hex": "(de normas.json → parametros_diseno.senalizacion_colores)", "cita": "Res. 1633 de 2025, Cuadros 2 y 3" }
  },
  "citas": ["Res. 1633 de 2025, Anexo 1, Cuadro 92", "Res. 1633, Cuadro 1 (normas.json → puertas_ancho_min_m)"],
  "resumen": { "recintos_por_nivel": { "P1": 82, "P2": 69, "P3": 69, "P4": 42, "BT": 6 }, "area_ejes_por_nivel_m2": {}, "avisos": 0 },
  "fuentes": ["programa.json", "normas.json → parametros_diseno", "presupuesto.json (capítulos 3 y 4)"]
}
```

Reglas del generador:

- **Niveles obligatorios:** `P1`, `P2`, `P3`, `P4` y `BT` (bloque técnico, `z = −1,5`, 6 recintos de la fila «bloque técnico» del programa). `BT` lleva su propia `entradas_recorrido` en su puerta exterior (el ascensor no llega a él). `CUB` (cubierta del piso 4 a 17,1 m y terraza del piso 3) es opcional en esta iteración; sus equipos (condensadoras, tanques) llevan `recinto: null` y `ubicacion: "cubierta (sin planta)"` en el inventario.
- **Recintos:** uno por cada unidad de `cantidad` de cada fila del programa de su piso (P1 = 82, P2 = 69, P3 = 69, P4 = 42, BT = 6; cálculo propio sobre `programa.json`). La «Escalera principal abierta del vestíbulo (pisos 1 y 2)» es un recinto en cada piso, unido por `ESC-P`; en el piso 2 su hueco es un obstáculo del recorrido (`obstaculos_recorrido`, salvo el descanso de llegada, donde está el punto de `ESC-P`). Las filas «exterior», «cubierta» y «subsuelo» no generan recintos.
- **Teselado:** la unión de recintos, circulaciones y núcleos de un nivel es el contorno (diferencia ≤ 0,5 % del área) y no hay traslapes. Así los muros salen de los bordes compartidos.
- **Muros:** en cada borde compartido entre dos recintos distintos, centrado en el eje, con `lados: [izquierdo, derecho]` mirando de `a` a `b`; en el contorno, `fachada` (un muro de fachada puede cubrir varios recintos de un mismo lado: `lados: [null, "exterior"]`); en el borde de un núcleo de escalera o ascensor, `nucleo`; alrededor de la sala de rayos X y del periapical, `plomado`; entre zonas húmedas, ductos, cuartos técnicos, depósitos de medicamentos y laboratorio, `bloque`; el resto, `liviano`. El tipo más exigente gana. Altura = altura libre (3,0 m) salvo `nucleo` y `fachada` (altura de entrepiso).
- **Polígono libre:** cada borde del polígono a ejes se desplaza hacia adentro la mitad del espesor del muro que lo ocupa.
- **Puertas y vanos:** cada puerta abre un vano en su muro; el vano se descuenta del muro en la geometría 3D (C). Las puertas de escalera abren en el sentido de la evacuación (hacia la escalera); las de unidades sanitarias PMR abren hacia afuera o son corredizas (NTC 6047; numeral por confirmar).
- **Grupos de color (Res. 1633, Cuadros 2 y 3, `normas.json → parametros_diseno.senalizacion_colores`):** `atencion_inmediata` rojo, `consulta_externa` naranja, `apoyo_diagnostico_y_terapeutico` amarillo, `internacion` azul, `quirurgico_y_esterilizacion` verde, `direccion_y_administracion` violeta, `apoyo_y_servicios_generales` café, `circulacion` gris. El generador escribe el bloque `grupos_1633: { id: { nombre, color_hex, cita } }` con el color tomado de `normas.json` (no se inventan tonos); C (piso y minimapa) y D (leyenda de «Pisos», 8.8) leen solo ese bloque, y la leyenda de los 7 grupos propios de `torre.js:13-21` deja de usarse donde se dibuje la planta real. El mapeo de servicio del programa a grupo va en `reglas_planta.json`.
- **Ángulos:** `mirando_deg` (entradas) y `rumbo_deg` (estado del recorrido) son antihorarios desde +x, como `rotacion_z` (0).
- **Forma web compacta** (`web/data/torre_plantas.json`, 10.1): las citas repetidas (`minimo_1633.cita`, `climatizacion.fuente`, `cita_ancho`) van una sola vez en la tabla `citas` y cada objeto lleva su índice (`"cita": 0`); se omite `poligono_libre` (solo lo usa el validador; C recalcula lo que necesite desde los muros) y las coordenadas van con 2 decimales.

### 3.4 `reglas_planta.json` (insumo de B)

```json
{
  "version": 1,
  "redondeo_m": 0.05,
  "minimos": [
    { "fila": 17, "ambiente": "Sala de reanimación, 2 camillas", "m2": 20.0, "lado_m": 3.0, "cita": "Res. 1633 de 2025, Anexo 1, Cuadro 92 (12 + 8 por camilla adicional); Res. 3100, num. 11.6.1, criterio 18.14 (según normas.json; por confirmar: la investigación de urgencias deja por confirmar los criterios de infraestructura) (12 m²)", "tipo_dato": "dato oficial (Res. 1633); por confirmar (Res. 3100)", "fuente": "normas.json → parametros_diseno.areas_minimas_m2.urgencias_reanimacion" }
  ],
  "puertas": [
    { "categoria": "camillas_procedimientos", "ancho_m": 1.40, "ambientes": ["Sala de reanimación, 2 camillas", "Sala de procedimientos (suturas, curaciones)", "Habitación de trabajo de parto, parto y recuperación (TPR)", "Sala de rayos X convencional digital (con blindaje en plomo)"], "cita": "Res. 1633, Cuadro 1 (procedimientos, reanimación, partos, recuperación, radiología: 1,40 m)" },
    { "categoria": "camas", "ancho_m": 1.20, "ambientes": ["Habitación doble de adultos con baño PMR y guardarropa (2 camas)", "Ambiente individual de aislamiento con baño PMR"], "cita": "Res. 1633, Cuadro 1 (aislamiento 1,20 m); NSR-10 K.3.14.2.3 (puertas de salida para camas ≥ 1,10 m); 1,20 m para todas las habitaciones y observación: decisión de este contrato" },
    { "categoria": "consultorio", "ancho_m": 1.00, "cita": "Res. 1633, Cuadro 1" },
    { "categoria": "bano", "ancho_m": 1.00, "cita": "Res. 1633, Cuadro 1" },
    { "categoria": "deposito", "ancho_m": 0.90, "cita": "Res. 1633, Cuadro 1" }
  ],
  "corredores": { "evacuacion_min_m": 2.40, "camillas_recomendado_m": 2.80, "interno_min_m": 1.20, "cita": "Res. 1633, num. 3.3.6 b.1; NSR-10 K.3.14.2.2 (normas.json → circulaciones_m)" },
  "evacuacion": { "puerta_a_escalera_max_m": 30.0, "cualquier_punto_max_m": 45.0, "cita": "NSR-10 K.3.14.1.2 y Tabla K.3.6-1 según programa.json → nucleos_verticales.evacuacion (numerales por confirmar en el texto)" },
  "zonas": {
    "P1": [ { "servicio_programa": "Urgencias", "x": [-13.0, 3.1], "y": [-10.0, 22.4] }, { "servicio_programa": "Vestíbulo y admisiones", "x": [-13.0, 3.1], "y": [-19.6, -10.0] } ]
  },
  "accesos_permitidos": [
    { "ambiente": "Unidad sanitaria PMR del consultorio especializado", "desde": ["Consultorio especializado (ginecobstetricia, pediatría y medicina interna por brigadas)"] },
    { "ambiente": "Ambiente individual de aislamiento con baño PMR", "desde": ["Antecámara del aislamiento"] }
  ],
  "servicio_a_grupo": { "Urgencias": "atencion_inmediata", "Atención del parto (TPR)": "atencion_inmediata", "Hospitalización (adultos, pediatría y obstetricia)": "internacion" },
  "decisiones": [
    "Consultorio especializado: si allí van el colposcopio y el equipo de termoablación, el Cuadro 7 pide 14 m² (normas.json); se traza de 3,60 × 3,90 m (14,04 m² a ejes). Cálculo propio."
  ]
}
```

**Referencias a ambientes (regla común a 3.4, 4.2, 4.6 y 9.1).** `programa.json` repite nombres entre servicios y pisos («Ambiente de aseo» en 8 filas, «Unidades sanitarias del personal» en 6, y «Lavapatos», «Antecámara del aislamiento», «Estación de enfermería: trabajo limpio» y «trabajo sucio», «Depósito de ropa limpia» y «sucia» o «Estacionamiento de camillas y sillas de ruedas» en urgencias y en hospitalización; dato del repositorio). Por eso todo archivo escrito a mano refiere un ambiente por su `fila` de `programa.json` o por el par `{ "servicio_programa": …, "nombre": … }`; el nombre solo basta si corresponde a una única fila. `validar_plantas.py` y `validar_inventario.py` fallan si un nombre corresponde a más de una fila sin desambiguar.

Las zonas salen del texto de `programa.json → implantacion.zonificacion_en_planta` (piso 1: urgencias de `y ≈ −10` a 22,4 y vestíbulo, admisiones y toma de muestras al sur con la puerta principal en `(−13,0; −13,0)`; piso 2: laboratorio en el suroccidente sobre la toma; piso 3: TPR y posparto al norte, esterilización al sur junto al montacargas; piso 4: terapias al occidente, telesalud y expansión al norte). **Esquema base sugerido** (cálculo propio, no obligatorio): crujía occidental `x −13,0 a −5,8` con fachada; corredor de 2,40 m **libres** (2,52 m a ejes con muros livianos de 0,12 m) o 2,80 m libres donde pasan camillas, pegado a la línea B; crujía central hasta `x 3,1`; franja oriental `x 3,1-8,6` con núcleos y cuartos técnicos. Con área a ejes, los corredores de cada piso caben si suman ≤ 188 m² en los pisos 1 a 3 (907,2 − 158,5 de núcleo − 560,8 útiles; cálculo propio).

### 3.5 Validación automática: `python3 scripts/torre/validar_plantas.py`

Solo biblioteca estándar. Imprime un informe JSON en la salida estándar y sale con código 1 si hay errores duros. Con `--fixture <archivo>` valida un fixture y omite las reglas que dependen de `programa.json` y de la retícula real (V2, V6, V15, V16 y V20). Geometría ortogonal: intersecciones por rectángulos y polígonos ortogonales; distancias por búsqueda en anchura (BFS) sobre una rejilla de 0,10 m.

| # | Regla | Tipo |
|---|---|---|
| V1 | Esquema: campos obligatorios, tipos, ids únicos, referencias válidas (recintos, muros, puertas, conexiones) | duro |
| V2 | Conteo: número de recintos de cada fila = `cantidad` del programa; nombre y piso coinciden con la fila | duro |
| V3 | Cada recinto dentro del contorno de su nivel (tolerancia 1 mm) | duro |
| V4 | Sin traslapes entre recintos, circulaciones y núcleos (intersección < 0,01 m²) | duro |
| V5 | Teselado: unión = contorno con diferencia ≤ 0,5 % | duro |
| V6 | `area_ejes_m2 ≥ area_programa_m2 − 0,05` | duro |
| V7 | `area_ejes_m2 ≥ minimo_1633.m2` y lado menor a ejes ≥ `minimo_1633.lado_m` | duro |
| V8 | `area_libre_m2 < minimo_1633.m2` | aviso (lista) |
| V9 | Cada recinto tiene al menos una puerta hacia una circulación o hacia un recinto de `accesos_permitidos` | duro |
| V10 | Conectividad: todos los recintos alcanzables desde las conexiones verticales de su nivel por puertas (grafo) | duro |
| V11 | Ancho de puerta ≥ el de su categoría; centro de la puerta sobre su muro; ancho ≤ largo del muro − 0,10 m; altura 2,10 m | duro |
| V12 | Abatimiento de hojas: el arco de una hoja no cruza otro arco ni un muro | duro |
| V13 | Corredores de evacuación con ancho **libre** (entre caras de muro) ≥ 2,40 m; corredores con `camillas: true` ≥ 2,80 m libres | duro / aviso |
| V14 | Recorrido desde la puerta de cada recinto hasta la puerta de la escalera protegida más cercana ≤ 30 m, y desde cualquier punto ≤ 45 m | duro |
| V15 | Núcleos iguales a `nucleos_verticales` en todos los pisos (exacto) y conexiones verticales con punto dentro de su núcleo | duro |
| V16 | Columnas en las 28 intersecciones (20 en el piso 4); cada columna dentro de un muro, en el contorno o en el borde de un corredor; si queda libre dentro de un recinto, solo en los de la lista permitida (gimnasio, salón de expansión, salas de espera) | duro |
| V17 | Centroide de cada recinto dentro de la zona de su servicio | aviso |
| V18 | Sala de rayos X y periapical con todos sus muros `plomado` | duro |
| V19 | Recintos de hospitalización, TPR, observación, consultorios y terapias con al menos una ventana a fachada o patio | aviso (Res. 1633, iluminación y ventilación natural; numeral por confirmar) |
| V20 | Suma de `area_ejes` útiles por piso ≥ `m2_util` del programa del piso | duro |

### 3.6 Uso de la planta en otros contratos

- C la convierte en geometría y rejilla de colisión (6.3-6.4).
- B la usa para ubicar la dotación (4.6).
- D la usa para «Pisos por servicio» (8.8).
- E colorea recintos con el contraste (9.2).

---

## 4. Contrato 2 · INVENTARIO de dotación y MATRIZ de cumplimiento para la habilitación

### 4.1 Archivos y flujo

```
fuentes_investigacion/res3100_*.json + reglas_exigencias.json
        │ python3 scripts/torre/normalizar_exigencias.py
        ▼
exigencias_3100.json   (199 filas de origen trazables)
        │
dotacion.json + laboratorio.json (equipos) + plantas + reglas_ubicacion.json + catalogo_equipos.json + implementos.json + exigencias_3100.json + fuentes_investigacion/normas_4725_1732.json
        │ python3 scripts/torre/generar_inventario.py
        ▼
inventario_dotacion.json · inventario_dotacion.csv · habilitacion.json
        │ python3 scripts/torre/validar_inventario.py   (sale 1 si hay errores duros)
        ▼
web/data/torre_inventario.json · web/data/torre_habilitacion.json   (build_data.py)
```

Nada se ubica a mano: las posiciones salen de las estrategias de `reglas_ubicacion.json` (4.6). Se permiten `posiciones_fijas` solo para piezas compuestas (rayos X, unidad odontológica, autoclave de doble puerta), con justificación en la misma regla.

### 4.2 `exigencias_3100.json`: normalización

Las tres investigaciones usan campos distintos: `nivel_verificacion` (urgencias) frente a `verificacion_texto` (consulta y apoyo); `ambiente_programa` como cadena con « | » o como lista con « (n)»; `item_dotacion` con « | », « ; » o «(n)». `normalizar_exigencias.py` los une en un solo formato y **no pierde ninguna fila**: 86 + 52 + 7 + 43 + 11 = **199 filas de origen** (cálculo propio; las 18 de «todos los servicios» son 7 de consulta y 11 de apoyo).

```json
{
  "id": "EX-URG-001",
  "origen": "res3100_urgencias_e_internacion.json#servicios[0].exigencias[0]",
  "servicio": "urgencias",
  "servicio_programa": "Urgencias",
  "codigo_reps": { "valor": "1102", "estado": "por confirmar en el REPS (tomado de programa.json)" },
  "numeral_grupo": "11.6.1",
  "estandar": "dotacion",
  "numeral": "11.6.1, estándar de dotación, criterio 22 según guía secundaria; numeral por confirmar",
  "numeral_confirmado": false,
  "texto": "Oxígeno medicinal y succión. Puede ser suministrado mediante salida de oxígeno medicinal y sistema de vacío o mediante oxígeno medicinal portátil y aspirador.",
  "texto_disponible": true,
  "verificacion_texto": "literal_compilacion",
  "exigible": "si",
  "que_exige": "Oxígeno y succión en el servicio, de pared o portátiles.",
  "ambientes": [ { "fila": 17, "nombre": "Sala de reanimación, 2 camillas" }, { "fila": 21, "nombre": "Observación adultos hombres, 2 camillas" } ],
  "cantidad_texto": "1 salida de oxígeno y 1 de vacío (o portátil) por camilla …",
  "regla": { "tipo": "por_puesto", "puestos": [ { "fila": 17, "n": 2 }, { "fila": 21, "n": 2 } ],
             "items": [ { "linea": "L-urgencias-e-a41c09", "nombre": "Flujómetro de oxígeno con humidificador" }, { "linea": "L-urgencias-e-7d2e50", "nombre": "Regulador de vacío con frasco" } ], "n_por_puesto": 1 },
  "cubre_con": [ { "tipo": "linea", "linea": "L-urgencias-e-a41c09", "nombre": "Flujómetro de oxígeno con humidificador" }, { "tipo": "linea", "linea": "L-fijo-f-1b9e04", "nombre": "Central de gases medicinales …" } ],
  "estado_investigacion": "cubierto",
  "comentario": "15 flujómetros = 2 reanimación + 6 observación + 1 procedimientos + 1 aislamiento + 3 ERA + 2 EDA …",
  "vigencia_hasta": null,
  "referencia": false,
  "fuente_url": "https://www.icbf.gov.co/cargues/avance/compilacion/docs/resolucion_minsaludps_3100_2019.htm"
}
```

(Los números de fila, los nombres de las líneas y los `h6` del ejemplo son ilustrativos.)

- **Escala única de verificación** (lo que la web muestra): `literal_compilacion` (frase vista en una compilación oficial —Cancillería, ICBF, Invima— a través del buscador; equivale a `fragmento_normograma` y a `literal_confirmado`), `contenido_compilacion` (contenido confirmado, redacción o subnumeral por confirmar; equivale a `contenido_confirmado_redaccion_por_confirmar`), `fuente_secundaria` (guía o transcripción: no es texto normativo; equivale a `fragmento_fuente_secundaria` y `solo_fuente_secundaria`) y `por_confirmar` (paráfrasis; equivale a `parafrasis_por_confirmar`). Ninguna se presenta como «verificada»: la web dice «tomado de una compilación oficial; cotejar con el Diario Oficial».
- **`exigible`** ∈ `si | por_confirmar`: `si` solo con `literal_compilacion` o `contenido_compilacion`; `por_confirmar` en los demás casos. De las 199 filas, 61 son de guía secundaria o paráfrasis (42 del archivo de urgencias, 12 del de consulta y 7 del de apoyo; dato de las investigaciones, conteo propio): quedan `por_confirmar`. La matriz (4.8), el cierre de brechas (4.7.1) y la web (6.5) usan este campo.
- **`numeral_confirmado`** = `false` si el numeral de origen contiene «por confirmar», «según guía», «según normas.json» o «por analogía»; `true` en los demás casos. No se fija a mano.
- **`texto`**: el texto literal de la fila. 22 filas de `res3100_consulta_y_ambulatorio.json` traen `texto_literal: null` (consulta externa, criterios 19 a 22; telemedicina; vacunación; farmacia; terapias; dato de la investigación): llevan `texto: null` y `texto_disponible: false`, y la web muestra `que_exige` con la etiqueta «resumen; texto oficial no obtenido», **nunca entre comillas**. El normalizador nunca copia `que_exige` en `texto`.
- **Ambientes** por `fila` de `programa.json` (regla común del 3.4). El `servicio` de cada investigación se traduce al `servicio_programa` con una **tabla cerrada** en `reglas_exigencias.json → servicio_a_programa` (no con la tabla orientativa del Anexo B); si un servicio de la investigación no está en la tabla, el normalizador falla.
- **Ids** según 1.3 (`nnn` por posición dentro de archivo y servicio; `EX-TOD-C…` y `EX-TOD-A…`). `reglas_exigencias.json` y la sección de cierre de `dotacion.json` citan exigencias por id **y** por `origen`; el normalizador falla si un id citado no existe o no coincide con su `origen`.
- `regla.tipo` ∈ `por_recinto` (n por cada recinto de los ambientes), `por_puesto` (n por camilla, cama o silla según `puestos`), `total_servicio` (n en el servicio), `por_piso` (n por piso del servicio, p. ej. carro de paro de hospitalización), `contenido` (el ítem debe estar `dentro_de` un contenedor: laringoscopio en el carro de paro), `existe_ambiente` (se verifica contra la planta), `area_libre_por_puesto` (área libre mínima por cama o camilla: `area_libre_m2` del recinto menos el baño y el guardarropa, dividida por los puestos; p. ej. 7 m² por cama de adultos y 6 m² en pediatría en hospitalización, que hoy viene de una guía secundaria y por eso queda `por_confirmar`), `documental` (programa de mantenimiento, hoja de vida, licencia de rayos X, protocolos: estado `documento_pendiente`) y `sin_regla` (se copia el estado de la investigación, marcado «estado tomado de la investigación»). `reglas_exigencias.json` (B, a mano) trae la `regla` y los `cubre_con` que no se pudieron resolver por nombre.
- **Vigencia:** `vigencia_hasta: "2027-01-02"` en las exigencias de esterilización que deroga la Res. 914 de 2025 (num. 25-27 de las generalidades de ambientes y num. 13, 13.1 y 14 de procesos, según la compilación de Cancillería; ubicación exacta por confirmar). En el corte de apertura (4.8) esas filas quedan `no_aplica` y se agrega una fila por cada requisito de la Res. 914 que se conozca, con `exigible: "por_confirmar"` hasta leer el manual DMER.
- **Exigencias por analogía** (las de dotación de la sala de expansión, «por analogía con 11.6.1» según la investigación): `referencia: true` y `estado: "no_aplica"`; no cuentan en los resúmenes (4.8).
- **Filas de «todos los servicios»** (`EX-TOD-…`, 18 filas): se conservan una sola vez y la matriz las muestra en un bloque «Todos los servicios», sin sumarlas a los resúmenes de cada servicio. Las exigencias que una investigación repite servicio por servicio se conservan una por servicio y se enlazan con `misma_que`.
- **Datos superados de las investigaciones** (la copia de `fuentes_investigacion/` es literal; la corrección se hace aquí): toda mención de «Res. 482 de 2018» se reescribe como «Res. 1811 de 2025 (reemplazó a la 482 desde el 6-mar-2026)», y el aviso de transición de la Res. 1732 de `res3100_consulta_y_ambulatorio.json` no se propaga.

### 4.3 `catalogo_equipos.json` (B, a mano) — lista cerrada de modelos 3D

Una entrada por `modelo3d` del Anexo C, con dimensiones nominales y datos físicos para el riesgo sísmico de los objetos no anclados. Las masas, alturas de centro de gravedad y fricciones son **estimaciones** (fichas típicas de fabricantes; se reemplazan por la ficha del equipo comprado).

```json
{
  "version": 1,
  "convencion_ejes": "Origen en el centro de la base; ancho en x local, fondo en y local, alto en z. La espalda (lo que va contra la pared o la cabecera) mira a −y local; el frente, a +y local.",
  "modelos": {
    "cama_hospitalaria": { "familia": "cama", "dim_m": [1.00, 2.20, 0.95], "montaje": "piso", "anclaje": "ruedas_con_freno",
      "masa_kg": 150, "h_cg_m": 0.55, "mu": 0.30, "contenedor": false, "tipo_dato": "estimacion" },
    "carro_paro": { "familia": "carro", "dim_m": [0.75, 0.55, 1.00], "montaje": "piso", "anclaje": "ruedas_con_freno",
      "masa_kg": 70, "h_cg_m": 0.50, "mu": 0.30, "contenedor": true, "compartimientos": ["superficie", "cajón 1", "cajón 2", "cajón 3", "cajón 4", "cajón 5", "lateral"], "tipo_dato": "estimacion" }
  }
}
```

`anclaje` ∈ `anclado | pared | cielo | apoyado | ruedas_con_freno | ruedas_sin_freno | dentro | sobre | en_nucleo`. Fricción por defecto (estimación): apoyado con patas de caucho sobre vinilo 0,5; metal sobre vinilo 0,3; ruedas con freno 0,3; ruedas sin freno 0,02 (rodadura). Cada modelo trae además `b_m` = semiancho de la base para el balanceo; si falta, `b_m = min(dim[0], dim[1]) / 2` (estimación), y el valor va también al catálogo web (10.2, campo `b`). `riesgoEquipos` usa `bx = dim[0]/2` y `by = dim[1]/2` en los ejes locales (7.4).

### 4.4 `implementos.json` (B, a mano) — implementos internos

Plantillas de contenido para contenedores y kits. Cada ítem tiene `tipo` ∈ `equipo_biomedico | dispositivo | instrumental | insumo | medicamento`.

- **Insumos, instrumental, medicamentos y dispositivos que no son equipo biomédico:** informativos; **no suman precio** (su costo va en la línea madre o en el inventario inicial de medicamentos e insumos de 72 horas, indirecto P4 de `presupuesto.json`).
- **Equipos biomédicos dentro de un kit** (oxímetro y termómetro infrarrojo, IIa; báscula digital; equipo de órganos de los sentidos portátil, entre otros): `generar_inventario.py` crea por cada unidad madre una **unidad componente** (`{id madre}-c{n}`) con precio 0 (el precio sigue en la línea madre), `clase_riesgo`, `registro_invima`, `mantenimiento` y `campos_al_comprar`; entran al CSV y les aplica la regla I8. Así lo pide `normas_4725_1732.json` para los 4 kits de examen (24 unidades): «El inventario y la hoja de vida deben llevar una línea por componente con su registro sanitario», y la Res. 3100 (num. 11.1.3 y 11.1.4, texto de compilación) pide marca, modelo, serie, registro y clase por equipo biomédico.
- Si un implemento es además una línea de `dotacion.json` (por ejemplo, el laringoscopio de urgencias), no se lista aquí: esa unidad existe por sí misma con `dentro_de` apuntando al contenedor.

```json
{
  "version": 1,
  "plantillas": {
    "carro_paro_adulto_pediatrico": {
      "lineas_que_la_usan": [ { "linea": "L-urgencias-m-…", "nombre": "Carro de paro (mueble) adulto-pediátrico con tabla de reanimación" }, { "linea": "L-hospitalizacion-m-…", "nombre": "Carro de paro (mueble) adulto-pediátrico para hospitalización" } ],
      "definicion": { "texto": "Conjunto de medicamentos, dispositivos médicos y equipos biomédicos utilizados en la reanimación cardio cerebro pulmonar.", "cita": "Res. 3100 de 2019, Manual, definiciones (texto de compilación; criterio 8 de todos los servicios según guía secundaria; por confirmar)" },
      "items": [
        { "nombre": "Tabla de reanimación", "cantidad": 1, "compartimiento": "lateral", "tipo": "dispositivo", "clase_riesgo": "I", "fuente": "el nombre de la línea de dotación", "verificacion": "dato del repositorio" },
        { "nombre": "Medicamentos del carro según el protocolo institucional de reanimación", "cantidad": null, "compartimiento": "cajón 1", "tipo": "medicamento", "fuente": "presupuesto, inventario inicial de 72 horas (indirecto P4)", "verificacion": "por_confirmar (la lista la fija el protocolo de la E.S.E.)" }
      ]
    },
    "kit_examen_basico": {
      "items": [
        { "nombre": "Oxímetro de pulso", "cantidad": 1, "compartimiento": "estuche", "tipo": "equipo_biomedico", "clase_riesgo": "IIa", "registro_invima": { "requerido": "si" },
          "mantenimiento": { "anual_pct": 5, "calibracion": true, "personal_inscrito_invima": false }, "fuente": "nombre de la línea y normas_4725_1732 (kits que se inventarían por componente)", "verificacion": "dato del repositorio" }
      ]
    }
  }
}
```

Las `fuente` de este archivo se escriben ya como texto para ciudadanos (sin rutas ni «→ clave»), porque llegan a la ficha (13.6). Plantillas mínimas: carro de paro adulto-pediátrico, carro de paro con módulo neonatal, kit de examen básico (8 componentes del nombre de la línea), equipo de órganos de los sentidos de pared, equipo de pequeña cirugía y sutura, equipo de toracostomía, equipo de partos (urgencias y partos), equipo de revisión uterina y sutura de desgarros, juego de instrumental básico de odontología, instrumental de operatoria, periodoncia, endodoncia y cirugía oral, elementos de inmovilización, sujeción mecánica, kit de rehabilitación, canecas de residuos con guardián, elementos de protección radiológica, maletín de reanimación de la sala de expansión. Los contenidos que no vienen de un texto normativo llevan `verificacion: "fuente_secundaria"` o `"por_confirmar"` y su fuente.

### 4.5 `inventario_dotacion.json` (generado)

Dos listas: `lineas` (todo lo que es común a las unidades de una línea, una sola vez) y `unidades` (una por objeto físico, con lo que es propio de cada uno). Así cada unidad tiene todos los campos pedidos por referencia, sin repetir textos ni sumas. Esta es la **forma de datos**; la web recibe la forma compacta del 10.2, que no copia precios (los toma de `dotacion.json` al exportar).

```json
{
  "id": "torre_hospital_inventario_dotacion",
  "version": 2,
  "generado_por": "scripts/torre/generar_inventario.py",
  "fecha": "2026-10-23",
  "insumos_sha1": { "dotacion.json": "…", "laboratorio.json": "…", "torre_hospital_plantas.json": "…", "reglas_ubicacion.json": "…", "catalogo_equipos.json": "…", "implementos.json": "…", "exigencias_3100.json": "…" },
  "sha256_dotacion": "…",
  "moneda_y_base": "Pesos constantes de 2026 (dotacion.json)",
  "norma_vigente": "Res. 3100 de 2019 y modificaciones (la Res. 1732 de 2026 fue revocada por la Res. 2080 de 2026)",
  "campos_res3100_decreto4725": ["servicio y ambiente", "nombre genérico", "marca", "modelo", "serie", "registro sanitario o permiso de comercialización INVIMA y vencimiento", "clase de riesgo", "tecnología controlada", "fecha de instalación y de compra", "hoja de vida", "responsable del mantenimiento (inscrito en el INVIMA si es IIb o III)", "referente de tecnovigilancia"],
  "lineas": [
    {
      "id": "L-urgencias-e-3f2a1c",
      "origen": "dotacion",
      "ref": { "servicio": "urgencias", "lista": "equipos", "idx": 0 },
      "servicio": "urgencias",
      "tipo": "equipo",
      "nombre": "Desfibrilador bifásico con monitor y marcapasos externo",
      "cantidad": 1,
      "especificacion": "Bifásico 1-360 J, modo DEA y manual, marcapasos transcutáneo, ECG de 3/5 derivaciones, oximetría, batería y registro.",
      "modelo3d": "desfibrilador",
      "clase_riesgo": { "repo": "IIb", "vigente": "IIb", "estado": "coherente", "regla": null, "fuente": "revisión del Decreto 4725 (sin observación)" },
      "clase_riesgo_revision": null,
      "es_dispositivo_medico": "si",
      "registro_invima": { "requerido": "si", "via": "evaluacion_tecnica (IIb, Decreto 4725 art. 18)", "usado_permitido": false, "nota": "Prohibido comprar o recibir en donación equipos usados IIb y III (Decreto 4725 modificado por el Decreto 582 de 2017; artículo 37 o 36 según la compilación, por confirmar)" },
      "tecnologia_controlada": null,
      "componentes": [],
      "exigencias": [ { "id": "EX-URG-012", "exigible": "si", "verificacion_texto": "literal_compilacion" }, { "id": "EX-URG-019", "exigible": "por_confirmar", "verificacion_texto": "fuente_secundaria" } ],
      "prioridad": "habilitacion",
      "prioridad_revisada": null,
      "norma_base": null,
      "justificacion_recomendado": null,
      "mantenimiento": { "anual_pct": 6, "vida_util_anios": 8, "preventivo": "según el manual del fabricante, con hoja de vida (Res. 3100, num. 11.1.3)", "personal_inscrito_invima": true, "calibracion": true, "cita_inscripcion": "Decreto 4725, art. 39" },
      "precio_unitario_cop_2026": 29126266,
      "rango_precio_unitario_cop_2026": [26955531, 31297000],
      "tipo_precio": "referencia_secop_ajustada_ipc",
      "metodo_precio": "Mediana de 2 referencias SECOP llevadas a pesos de 2026 con el IPC",
      "fuentes_precio": ["https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.10965672", "(segunda referencia del campo fuente de dotacion.json)"],
      "nota_interna": "Texto de la nota de dotacion.json; no se publica como sustento normativo (el sustento son las exigencias)",
      "plantilla_contenido": null
    },
    {
      "id": "L-laboratorio-c-0a77e2", "origen": "laboratorio", "ref": { "lista": "laboratorio.json → equipos", "idx": 9 },
      "servicio": "laboratorio", "tipo": "equipo", "nombre": "GeneXpert de 4 módulos (PCR en tiempo real en cartucho)", "cantidad": 1,
      "adquisicion": "programa_o_compra",
      "precio_unitario_cop_2026": 143967621, "tipo_precio": "valor_de_mercado",
      "en_presupuesto": false, "nota_precio": "No presupuestado; por confirmar con el programa nacional de tuberculosis (si se compra, sumar $144,0 millones al P5)"
    }
  ],
  "unidades": [
    {
      "id": "U-urgencias-3f2a1c-001", "linea": "L-urgencias-e-3f2a1c", "k": 1,
      "piso": 1, "recinto": "P1-A017-01", "ambiente": "Sala de reanimación, 2 camillas",
      "posicion": [-6.10, 17.35, 1.00], "rotacion_z": 1.5708, "montaje": "sobre",
      "apoyo": "U-urgencias-77c0d2-001", "dentro_de": null, "compartimiento": null,
      "riesgo_sismico": { "anclaje": "sobre", "masa_kg": 7, "h_cg_m": 0.15, "mu": 0.4, "b_m": 0.135, "bx_m": 0.16, "by_m": 0.135 },
      "contenido": null,
      "campos_al_comprar": { "marca": null, "modelo": null, "serie": null, "registro_sanitario": null, "vence_registro": null, "fecha_compra": null, "fecha_instalacion": null, "hoja_de_vida": null },
      "estado": "en_dotacion"
    }
  ],
  "fuera_de_la_torre": [ { "linea": "L-fijo-f-…", "nombre": "Lavandería: lavadora industrial de 28 kg y secadora de 30 kg", "ubicacion": "edificio actual (programa.json: la lavandería queda en el hospital actual)" } ],
  "totales": {
    "por_servicio": { "urgencias": { "unidades": 155, "equipos_cop_2026": 351786941, "mobiliario_cop_2026": 167461721, "coincide_con_dotacion": true } },
    "laboratorio_json": {
      "lineas": 11, "unidades": 12, "valor_mercado_cop_2026": 1249676210,
      "comodato": { "lineas": 9, "unidades": 10, "valor_mercado_cop_2026": 955708589 },
      "programa_o_compra": { "lineas": 1, "unidades": 1, "valor_mercado_cop_2026": 143967621, "en_presupuesto": false },
      "opcional": { "lineas": 1, "unidades": 1, "valor_mercado_cop_2026": 150000000, "nota": "Recomendado cuando haya más de 150 aislamientos al mes; fuera de la matriz" },
      "tipo": "dato del repositorio (laboratorio.json) y cálculo propio (sumas)"
    },
    "habilitacion_cop_2026": { "segun_dotacion": 3908496956, "sin_reclasificados": null, "tipo": "calculo_propio" },
    "cierre_brechas": { "por_proyecto": { "P4": null, "P5": null, "P6": null }, "operacion_anual_cop_2026": null, "items_sin_precio": null }
  }
}
```

(Las cifras de urgencias, los `h6` y el índice del GeneXpert son ilustrativos salvo los de `laboratorio.json`, que son dato del repositorio.)

Reglas:

- **Unidades:** Σ `cantidad` de las líneas = 509 equipos + 359 de mobiliario + 15 de equipamiento fijo (dato del repositorio, cálculo propio) + **12 unidades de `laboratorio.json` (10 en comodato, 1 por programa o compra y 1 opcional)** + las del cierre de brechas (`origen: "cierre_brechas"`, `estado: "cierre_brechas_propuesto"`) + las unidades componentes (4.4 y 4.7.3, precio 0).
- **Equipos de `laboratorio.json`:** `adquisicion` sale de `laboratorio.json → equipos[].modelo_de_compra`: `comodato` para las 9 líneas y 10 unidades que dicen «comodato» (el script valida que su valor de mercado sume $955.708.589, igual a `dotacion.json → totales_generales.analizadores_de_laboratorio_en_comodato_valor_de_mercado_cop_2026`); `programa_o_compra` para el GeneXpert ($143.967.621, «compra o entrega del programa nacional de tuberculosis»: «no presupuestado; por confirmar con el programa de TB»; `presupuesto.json`, P5, dice «si se compra, sumar $144,0 millones»); `opcional` para el sistema de identificación y antibiograma ($150.000.000, «opcional … cuando haya más de 150 aislamientos al mes»: recomendado, fuera de la matriz). Las tres sumas dan $1.249.676.210 (cálculo propio). Todas se inventarían con registro, hoja de vida y mantenimiento (a cargo del proveedor en las de comodato), pero ninguna suma a la dotación.
- **Precios sin duplicar:** cada unidad hereda el precio unitario de su línea; la suma por servicio debe ser **igual al peso** a `dotacion.json → servicios[].totales.equipos_cop_2026` y `mobiliario_cop_2026`, y la del equipamiento fijo a `totales_equipamiento_fijo.total_cop_2026`. Los implementos y las unidades componentes no tienen precio. El cierre de brechas suma aparte. `sha256_dotacion` es el hash del `dotacion.json` usado; `build_data.py` no exporta el inventario (y lo avisa) si no coincide con el archivo actual (10.1).
- **Fuente del precio:** `fuentes_precio[]` copia todas las URL o referencias del campo `fuente` de la línea (no solo la primera) y `metodo_precio` el método (p. ej. el desfibrilador: «mediana de 2 referencias llevadas a pesos de 2026 con el IPC», Tuluá y Cáqueza, según `dotacion.json`).
- **Clase de riesgo** (desde `normas_4725_1732.json → clases_riesgo_revisadas`, 49 filas): `clase_riesgo.vigente` es una **enumeración** ∈ `I | IIa | IIb | III | no_dm | ivd | por_confirmar`; `clase_riesgo.estado` ∈ `coherente | discrepancia | probable_discrepancia | regimen_distinto | por_confirmar | observacion`; el texto explicativo va en `clase_riesgo_revision.nota`, nunca en la clase. `vigente` = la clase de `dotacion.json` después del 4.7.3 (solo cambian las discrepancias firmes). `es_dispositivo_medico` ∈ `si | no | ivd | por_confirmar`.
- **Registro INVIMA:** `requerido: "si"` para clases I, IIa, IIb y III (registro automático para I y IIa no controlados, art. 17; evaluación técnica para IIb y III, art. 18) y para diagnóstico *in vitro* que la revisión no marque como `regimen_distinto` (Decreto 3770 de 2004); `"por_confirmar"` para las 8 filas `regimen_distinto` (IVD o equipo general de laboratorio, por confirmar) y donde la investigación pide concepto del INVIMA (central de gases, generador PSA, PACS, refrigeradores, cadena de frío); `"no"` para lo que no es dispositivo médico. `tecnologia_controlada` queda `null` (lista no verificada) salvo que B cite la fuente.
- **Mantenimiento:** `personal_inscrito_invima = true` para IIb y III (Decreto 4725, art. 39); `calibracion = true` para básculas, tensiómetros, termómetros, termohigrómetros, flujómetros, monitores, desfibriladores, bombas, oxímetros, monitores fetales, autoclaves, refrigeradores de vacunas y equipos de laboratorio (lista de B; estimación).
- **Exigencias:** el sustento normativo de una línea sale **solo** de sus `exigencias`, cada una con su `exigible` y su nivel (4.2). La `nota` de `dotacion.json` se guarda como `nota_interna` y no se publica como texto normativo. Cada línea `habilitacion` enlaza al menos una exigencia o lleva `exigencias: []` con la nota «habilitación según dotacion.json; sin exigencia literal encontrada». Las líneas `recomendado` llevan `justificacion_recomendado` desde `excesos_recomendados` de la investigación.
- **Reclasificaciones de la investigación** (sin cambiar `prioridad` en `dotacion.json`): `prioridad_revisada` y `norma_base` desde `excesos_recomendados`: incubadora neonatal ($26,2 M), lámpara de fototerapia ($15,0 M) y sillones de acompañante de TPR y hospitalización ($33,0 M) → `prioridad_revisada: "recomendado"`; equipo de otoemisiones ($30 M) → `norma_base: "Res. 3280 de 2018 (no la Res. 3100)"` (cifras de la investigación). `totales.habilitacion_cop_2026` da el valor de habilitación de `dotacion.json` ($3.908.496.956) y el mismo valor sin los reclasificados; la ficha y `docs/15` los muestran.
- **CSV** `inventario_dotacion.csv`: una fila por unidad (incluidas las componentes) con todos los campos de su línea expandidos (UTF-8 con BOM, separador «;», decimales con coma) para la E.S.E. y el ingeniero biomédico.

### 4.6 `reglas_ubicacion.json` (B, a mano) — cómo se ubica cada línea

```json
{
  "version": 2,
  "reglas": [
    {
      "linea": "L-urgencias-e-a41c09", "nombre": "Flujómetro de oxígeno con humidificador", "modelo3d": "toma_gases_pared",
      "reparto": [
        { "ambiente": { "fila": 17, "nombre": "Sala de reanimación, 2 camillas" }, "por_recinto": 2, "estrategia": "pared_altura", "junto_a": "camilla_reanimacion", "altura_m": 1.50 },
        { "ambiente": { "fila": 21, "nombre": "Observación adultos hombres, 2 camillas" }, "por_recinto": 2, "estrategia": "pared_altura", "junto_a": "camilla_observacion", "altura_m": 1.50 },
        { "ambiente": { "servicio_programa": "Urgencias", "nombre": "Atención de enfermedad respiratoria aguda (ERA), 3 sillas" }, "por_recinto": 3, "estrategia": "pared_altura", "junto_a": "sillon_reclinable", "altura_m": 1.50 }
      ],
      "fuente_reparto": "res3100_urgencias_e_internacion.json, EX-URG-001: '15 flujómetros = 2 + 6 + 1 + 1 + 3 + 2'"
    },
    { "linea": "L-urgencias-e-3f2a1c", "nombre": "Desfibrilador bifásico con monitor y marcapasos externo", "modelo3d": "desfibrilador",
      "reparto": [ { "ambiente": { "fila": 17 }, "por_recinto": 1, "estrategia": "sobre", "sobre": "carro_paro" } ] },
    { "linea": "L-tic_apoyo-e-…", "nombre": "Computador todo en uno", "modelo3d": "computador_aio",
      "reparto": [ { "ambiente": "*", "estrategia": "sobre", "sobre": "puesto_trabajo", "por_apoyo": 1 } ],
      "resto_en": [ { "nombre": "Oficina de coordinación médica, vigilancia epidemiológica y calidad (3 puestos)" } ] }
  ]
}
```

(`fila`, nombres y `h6` ilustrativos.) `fuente_reparto` es interno: `build_data.py` no lo exporta a la web.

Estrategias (lista cerrada; el generador las implementa de forma determinista): `cabecera_a_pared` (camas y camillas con la cabecera contra la pared más larga sin puerta, separadas 1,0 m entre camillas según la Res. 1633, Cuadro 92, y la Res. 3100, num. 11.6.1, criterio 18.15 (según normas.json; por confirmar), y con 0,9 m libres a cada lado, regla de este contrato), `contra_pared` (`pared`: `larga | opuesta_puerta | junto_puerta | n | s | e | o`), `pared_altura` (montado en el muro a `altura_m`), `cielo` (centro del recinto o sobre la cama de partos), `centro`, `esquina`, `junto_a` (al lado de la cabecera de otro modelo), `sobre` (descansa **encima** de otra unidad —escritorio, mesón, carro—: la unidad lleva `apoyo` = id de esa unidad, `z` = altura de su cara superior, y **sí se dibuja**), `dentro` (contenido de un contenedor: `dentro_de` = id del contenedor y `compartimiento`; **no se dibuja** salvo que se abra el contenedor), `fila` (estanterías, lockers, mesones a lo largo de muros), `cuadricula` (tándems en salas de espera con pasillo de 1,2 m), `en_nucleo` (cabinas de ascensor), `posiciones_fijas` (solo piezas compuestas, con `justificacion`).

Validación (`validar_inventario.py`; con `--fixture <inventario_min_datos.json> <dotacion_min.json>` valida el fixture de datos contra su propia dotación de prueba en lugar de `dotacion.json`, y con `--web <inventario_min.json>` valida la forma web del 10.2 con su esquema):

| # | Regla | Tipo |
|---|---|---|
| I1 | Unidades por línea = cantidad; ids únicos y estables (mismo resultado en dos corridas); sin colisiones de `h6` entre líneas | duro |
| I2 | Sumas de precio por servicio iguales a `dotacion.json` (o a `dotacion_min.json` con `--fixture`) | duro |
| I3 | Huella de cada unidad de piso dentro del `poligono_libre` de su recinto (tolerancia 2 cm); las de `pared` tocan una cara de muro; las de `cielo` a la altura libre | duro |
| I4 | Sin traslapes entre huellas de piso (se permiten `sobre`, `dentro`, `pared` y `cielo`) | duro |
| I5 | Área de barrido de cada puerta libre | duro |
| I6 | Paso libre ≥ 0,90 m desde la puerta hasta un costado de cada cama, camilla, cuna, sillón de paciente y unidad odontológica (BFS 0,10 m) | duro |
| I7 | Cada exigencia evaluada con estado; diferencias con `estado_investigacion` listadas y explicadas (contra el fixture con `--fixture`) | duro / aviso |
| I8 | Cada unidad (incluidas las componentes que son equipo biomédico) con `clase_riesgo.vigente` de la enumeración, `registro_invima.requerido` y `mantenimiento` | duro |
| I9 | `dentro_de` apunta a una unidad cuyo modelo tiene `contenedor: true`, del mismo recinto, y con un `compartimiento` de ese modelo | duro |
| I10 | `apoyo` apunta a una unidad del mismo recinto y la `z` de la unidad es la altura de la cara superior del apoyo (± 1 cm) | duro |
| I11 | Ninguna unidad sin recinto, salvo `fuera_de_la_torre` y equipos de cubierta | duro |
| I12 | Cada regla y cada `cubre_con` traen el `nombre` de su línea y coincide; cada ambiente referido por nombre corresponde a una sola fila | duro |
| I13 | Las líneas de `laboratorio.json` con `adquisicion: "comodato"` suman $955.708.589 | duro |

### 4.7 Cambios a `dotacion.json` (B)

#### 4.7.1 Sección nueva `cierre_brechas_habilitacion`

No toca `totales_generales`, para no mover `presupuesto.json`, `financiacion.json` ni el total de $37.137 M.

```json
{
  "cierre_brechas_habilitacion": {
    "fecha": "2026-10-23",
    "origen": "Cruce con la Res. 3100 (fuentes_investigacion/res3100_*.json) y con el proyecto tipo (proyecto_tipo_contraste.json)",
    "como_se_financia": "Cada ítem indica su proyecto (P4, P5 o P6 de presupuesto.json). Mientras no se actualice el presupuesto, la inversión podría salir de la contingencia de su proyecto (P4: $175.059.364; P5: $26.160.785), que es la reserva para riesgo de cantidades y precios: usarla reduce esa reserva. Los gastos de operación anual no se financian con contingencias. No se suma a totales_generales.",
    "items": [
      { "servicio": "hospitalizacion", "nombre": "Laringoscopio adulto y pediátrico (mango + hojas de fibra óptica)", "cantidad": 1,
        "ambiente": { "servicio_programa": "Hospitalización (adultos, pediatría y obstetricia)", "nombre": "Estación de enfermería: puesto central" },
        "dentro_de_linea": { "linea": "L-hospitalizacion-m-…", "nombre": "Carro de paro (mueble) adulto-pediátrico para hospitalización" },
        "especificacion": "Igual a la línea de urgencias.", "clase_riesgo": "I",
        "precio_unitario_cop_2026": 1800000, "rango_precio_unitario_cop_2026": [1800000, 1800000],
        "tipo_precio": "referencia_repo", "fuente": "Mismo ítem en dotacion.json (urgencias)",
        "exigencias": [ { "id": "EX-HOS-…", "origen": "res3100_urgencias_e_internacion.json#…" } ],
        "prioridad": "por_confirmar", "proyecto": "P4", "naturaleza": "inversion" },
      { "servicio": "esterilizacion", "nombre": "Secadora o gabinete de secado de instrumental", "cantidad": 1,
        "precio_unitario_cop_2026": null, "rango_precio_unitario_cop_2026": null, "tipo_precio": "por_cotizar",
        "exigencias": [ { "id": "EX-EST-…" } ], "depende_de": "Res. 914 de 2025 (rige desde el 3-ene-2027)",
        "prioridad": "por_confirmar", "proyecto": "P4", "naturaleza": "inversion" },
      { "servicio": "imagenes", "nombre": "Dosimetría personal (servicio anual)", "tipo": "servicio", "cantidad": 1,
        "precio_unitario_cop_2026": null, "tipo_precio": "por_cotizar", "prioridad": "habilitacion", "proyecto": "P4", "naturaleza": "operacion_anual" }
    ],
    "totales": {
      "por_proyecto": { "P4": { "habilitacion_cop_2026": 0, "recomendado_cop_2026": 0, "por_confirmar_cop_2026": 0 }, "P5": {}, "P6": {} },
      "operacion_anual_cop_2026": 0,
      "rango_cop_2026": [0, 0],
      "items_sin_precio": 0,
      "tipo": "calculo_propio",
      "nota": "Las sumas no incluyen ítems por cotizar; la operación anual va aparte y no se suma a la inversión."
    }
  }
}
```

Contenido mínimo (de las tres investigaciones; cantidades y ambientes exactos en ellas): urgencias (martillos de reflejos ×3, camilla con estribos ×1); hospitalización (laringoscopio y resucitador para el carro del piso 3, fonendoscopio pediátrico si el del kit no lo es); partos (laringoscopio y resucitador adultos, 2 cintas métricas, segundo oxímetro neonatal, segunda báscula e infantómetro, segundo laringoscopio neonatal, nevera de grado médico en el depósito de medicamentos con chapa); esterilización (secadora o gabinete de secado, lupa con iluminación, etiquetadora o software de trazabilidad: **dependen de la Res. 914**, que rige antes de la apertura); sala de expansión (DEA con maletín de reanimación, segundo aspirador, 2 kits de examen con glucómetro: **`prioridad: "recomendado"`** —hospital seguro—, porque la sala de expansión no es un servicio de la Res. 3100 y `dotacion.json` no le asigna ítems de habilitación); piso 4 (DEA, `recomendado`, por confirmar si lo exige el carro de paro del piso); todos (3 termohigrómetros para los depósitos de medicamentos; 2 para toma de muestras y almacenamiento de imágenes); consulta externa (12 fonendoscopios pediátricos, 13 martillos de reflejos —exigencia por confirmar—, 2 básculas pesabebés); terapias (toma de oxígeno con flujómetro en terapia respiratoria —la salida en la red de gases va en obra—, juego de valoración); imágenes (casilleros del vestidor, desinfección de alto nivel del transductor endocavitario, canecas por punto de generación, dosimetría personal y control de calidad periódico de rayos X como servicios anuales —`tipo: "servicio"`, `naturaleza: "operacion_anual"`, sin unidades 3D—); proyecto tipo (bebedero y punto ecológico en salas de espera, báscula de residuos, linterna de valoración pupilar).

Reglas del cierre:

- **Prioridad:** `habilitacion` solo si al menos una exigencia enlazada es `exigible: "si"` (4.2); si todas son de guía secundaria o paráfrasis (como el laringoscopio del carro del piso 3, la cinta métrica y el oxímetro y el laringoscopio neonatales, que vienen de `fragmento_fuente_secundaria`), `por_confirmar`; los de la sala de expansión y el proyecto tipo, `recomendado`.
- **Precio:** el del mismo ítem en `dotacion.json` cuando existe (`tipo_precio: "referencia_repo"`); si no, la estimación con rango de la investigación (`"estimacion"`); si no hay precio ni en el repositorio ni en la investigación (las 18 `compras_nuevas_minimas` de urgencias e internación no traen costo; `dotacion.json` no tiene secadora o gabinete de secado, lupa, etiquetadora o software de trazabilidad, martillo de reflejos, cinta métrica suelta, linterna, nevera pequeña de grado médico, bebedero, punto ecológico ni báscula de residuos), `tipo_precio: "por_cotizar"` y `precio_unitario_cop_2026: null`. Los `totales` informan `items_sin_precio` y **no suman cifras supuestas**.
- **Proyecto y naturaleza:** `proyecto` ∈ `P4 | P5 | P6` según el capítulo de `presupuesto.json` que corresponda (los termohigrómetros y recipientes de residuos de toma de muestras y laboratorio son P5); `naturaleza` ∈ `inversion | operacion_anual`. Los totales van por proyecto; la operación anual aparte.
- **Rango de referencia:** la investigación de consulta y ambulatorio estima los faltantes de sus seis servicios en $12,2 M a $22,6 M (1,4 % a 2,6 % de $852,5 M; cálculo propio de esa investigación), pero ese rango incluye un DEA para el piso 4 ($8 a $12 M) que no es exigencia confirmada: se cita como «**$4,2 a $10,6 M sin el DEA del piso 4**» (cálculo propio) y el DEA va aparte como `recomendado`.
- **Lavadora desinfectora** ($110 M, hoy `recomendado` en `dotacion.json`): la investigación sugiere pasarla a habilitación por la Res. 914. No se cambia su `prioridad` en esta iteración: `docs/15` documenta la decisión (queda `prioridad_revisada: "por_confirmar (Res. 914)"` en el inventario) y la retoma cuando se lea el manual DMER.

#### 4.7.2 Ajustes de especificación y de notas

Texto, sin cambiar precio; nota `ajuste_v2` en la línea: barandas y ruedas con freno en camilla de procedimientos (urgencias y consulta), camillas y cuna de observación, camilla de transporte de partos, camillas plegables de expansión; freno en la camilla de reanimación; paneles de alarma por zona en la central de gases; separar el examen ginecológico del equipo de parto de urgencias y nombrar el equipo de episiotomía y episiorrafia en partos; tallas adulto y pediátrica en la protección radiológica de imágenes y odontología; pliego con registro sanitario, clase de riesgo, manual en castellano, protocolo de mantenimiento, capacitación y calificación de autoclaves.

**Notas con citas no confirmadas:** las `nota` que citan la Res. 3100 sin sustento confirmado pasan a decir «según guía secundaria; por confirmar». Al menos: el desfibrilador («marcapasos externo» en 11.6.1 solo lo agrega una guía secundaria, y queda pendiente en la sección 15) y la planta eléctrica («11.1.2, criterio 14» es paráfrasis).

#### 4.7.3 Clases de riesgo

- Cada línea revisada gana `clase_riesgo_revision: { valor, estado, regla, fuente, nota }`; `clase_riesgo` sigue siendo una enumeración (`I | IIa | IIb | III | no_dm | ivd | por_confirmar`) y todo texto libre va en `nota`.
- Se cambia `clase_riesgo` **solo** en las discrepancias firmes apoyadas en reglas leídas: tensiómetro aneroide de pared IIa → I (regla 1; 3 servicios), báscula pesa bebés de urgencias IIa → I (regla 12), lavadora desinfectora IIb → IIa (regla 15).
- **Quedan sin cambio en la clase y con `clase_riesgo_revision.estado: "por_confirmar"`:** el refrigerador de vacunas (la investigación: «I (regla 2) si se considera dispositivo médico; probablemente no lo es») y la incubadora de indicadores biológicos («I por regla 12 o IIa por regla 15; por confirmar»).
- **No se parte** la línea «Laringoscopio neonatal y resucitador neonatal con mezclador de oxígeno» (`partos`, equipos, posición 10 de 21; dato del repositorio): partirla cambiaría `partos.totales.numero_de_items` (28) y el conteo de 236 líneas. Se le agrega `componentes: [ { "nombre": "Laringoscopio neonatal", "clase": "I" }, { "nombre": "Resucitador neonatal con mezclador", "clase": "IIa", "regla": "Decreto 4725, art. 6 y regla 2" } ]`, y `generar_inventario.py` crea una unidad componente por cada uno (precio 0, dentro de la línea), como en los kits (4.4).
- Las filas «no es dispositivo médico» (UPS, termohigrómetros, estabilizador, balanza y horno, nevera mortuoria, autoclave de residuos, puesto de trabajo y los **registradores de temperatura de 30 días y termómetros digitales de vacunación**) pasan a `clase_riesgo: "no_dm"` con la nota «No es dispositivo médico (por confirmar: definición del art. 2 del Decreto 4725 no leída en el texto oficial)».

#### 4.7.4 No se cambia

Precios, cantidades y número de líneas existentes (236 líneas de los 15 servicios: `items_estimados` 199 + `items_con_referencia_secop` 37, dato del repositorio), `prioridad` de las líneas existentes ni el posible duplicado del kit de examen ($67,5 M, cálculo propio de la investigación del proyecto tipo): se documenta como decisión pendiente de la E.S.E. (`docs/15`).

### 4.8 `habilitacion.json` (generado) — matriz de cumplimiento en dotación e infraestructura, por servicio

La matriz **no dice si un servicio se puede habilitar**: la Res. 3100 exige siete estándares y las investigaciones solo tienen filas de dotación, infraestructura, medicamentos y dispositivos, procesos prioritarios y «todos los servicios» (no hay filas de talento humano ni de interdependencia, y de historia clínica solo 2 de TIC). Por eso el estado se llama **«cumplimiento en dotación e infraestructura»** y la frase «servicio habilitado» está prohibida en la web (13.6).

```json
{
  "id": "torre_hospital_habilitacion",
  "version": 2,
  "insumos_sha1": { "inventario_dotacion.json": "…", "exigencias_3100.json": "…", "torre_hospital_plantas.json": "…" },
  "norma": "Res. 3100 de 2019 y modificaciones",
  "alcance": "Cumplimiento en dotación e infraestructura",
  "estandares_evaluados": ["dotación", "infraestructura", "medicamentos, dispositivos médicos e insumos (parcial)", "procesos prioritarios (parcial)"],
  "estandares_no_evaluados": ["talento humano", "historia clínica y registros", "interdependencia"],
  "texto_alcance": "Esta matriz revisa la dotación y la infraestructura. No revisa talento humano, historia clínica ni interdependencia (por ejemplo, urgencias depende de imágenes, laboratorio y transporte asistencial): no dice si un servicio se puede habilitar.",
  "fecha_referencia": [
    { "id": "corte_2026", "fecha": "2026-10-23", "regla": "Res. 3100 con sus modificaciones vigentes" },
    { "id": "apertura", "fecha": "2030-04-01", "tipo_dato": "estimacion (apertura «hacia abril de 2030», docs/11)", "regla": "Exigencias con vigencia_hasta anterior quedan no_aplica; esterilización con la Res. 914 de 2025, por_confirmar hasta leer el manual DMER" }
  ],
  "aviso_vigencia": "La Res. 1732 de 2026 fue revocada por la Res. 2080 del 8-sep-2026 antes de regir.",
  "aviso_textos": "Textos tomados de compilaciones oficiales vistas por buscador o de guías secundarias; cotejar con el Diario Oficial antes de radicar o de la visita previa.",
  "escenarios": ["dotacion_actual", "con_cierre_de_brechas"],
  "servicios": [
    {
      "id": "urgencias", "nombre": "Servicio de urgencias", "codigo_reps": "1102 (por confirmar)", "numeral": "11.6.1", "complejidad": "baja",
      "habilitable": "si", "marco": "Res. 3100, num. 11.6.1",
      "resumen": {
        "corte_2026": { "dotacion_actual": { "exigibles": { "cumple": 0, "parcial": 0, "falta": 0, "documento_pendiente": 0 }, "por_confirmar": { "cumple": 0, "parcial": 0, "falta": 0 } }, "con_cierre_de_brechas": {} },
        "apertura": {}
      },
      "exigencias": [
        { "id": "EX-URG-001", "numeral": "…", "texto_corto": "Oxígeno medicinal y succión…", "texto_disponible": true, "verificacion_texto": "literal_compilacion", "exigible": "si",
          "ambientes": [ { "fila": 17, "nombre": "Sala de reanimación, 2 camillas" } ], "recintos": ["P1-A017-01"],
          "requerido": 15, "encontrado": { "dotacion_actual": 15, "con_cierre_de_brechas": 15 },
          "unidades": ["U-urgencias-a1b2c3-001"],
          "estado": { "corte_2026": { "dotacion_actual": "cumple", "con_cierre_de_brechas": "cumple" }, "apertura": { "dotacion_actual": "cumple", "con_cierre_de_brechas": "cumple" } },
          "estado_investigacion": "cubierto", "diferencia": null, "referencia": false, "fuente_url": "…" }
      ]
    },
    { "id": "sala_expansion", "nombre": "Sala de expansión", "habilitable": "no", "marco": "Res. 2065 de 2025 (sedes transitorias en emergencias); sus exigencias de dotación son por analogía con 11.6.1 y van como referencia" },
    { "id": "esterilizacion", "nombre": "Esterilización", "habilitable": "sin_habilitacion_propia", "marco": "Proceso de la Res. 3100, num. 11.1, hasta el 2-ene-2027; Res. 914 de 2025 desde el 3-ene-2027" },
    { "id": "telemedicina", "nombre": "Telemedicina", "habilitable": "modalidad", "marco": "Modalidad de prestación, sin código de servicio propio" },
    { "id": "tic_apoyo", "nombre": "TIC y apoyo", "habilitable": "no", "marco": "Soporte de los demás servicios" },
    { "id": "imagenes_744", "nombre": "Imágenes diagnósticas ionizantes (rayos X)", "codigo_reps": "744 (por confirmar)", "numeral": "11.3.4.1", "complejidad": "baja", "habilitable": "si" },
    { "id": "imagenes_745", "nombre": "Imágenes diagnósticas no ionizantes (ecografía)", "codigo_reps": "745 (por confirmar)", "numeral": "11.3.4.2", "complejidad": "mediana", "habilitable": "si", "marco": "La compilación (num. 11.3.4) exige habilitar la ecografía en mediana complejidad" },
    { "id": "toma_muestras", "nombre": "Toma de muestras de laboratorio clínico", "codigo_reps": "712 (por confirmar)", "habilitable": "sin_habilitacion_propia", "marco": "No requiere habilitación propia si el laboratorio de la misma sede toma las muestras (Res. 3100, num. 11.3.12, texto de compilación)" }
  ],
  "todos_los_servicios": { "exigencias": ["EX-TOD-C01", "EX-TOD-A01"], "nota": "Se muestran una vez; no suman en los resúmenes por servicio" },
  "por_recinto": { "P1-A017-01": { "estado": { "corte_2026": "cumple", "apertura": "cumple" }, "exigencias": ["EX-URG-001", "EX-URG-024"], "por_confirmar": 1 } }
}
```

Reglas:

- **Estados:** `cumple | parcial | falta | documento_pendiente | no_aplica`, calculados para cada `fecha_referencia` y cada escenario.
- **Solo cuentan las exigibles.** El color de un recinto y el `resumen.…exigibles` de cada servicio cuentan solo las exigencias con `exigible: "si"`: un recinto es `falta` si alguna exigencia exigible de dotación de su ambiente falta, `parcial` si alguna es parcial y `cumple` si todas cumplen. Las `por_confirmar` van en un conteo aparte («además, N exigencias por confirmar: …») y no cambian el color. Las documentales no cambian el color pero se listan. Las de `referencia: true` (por analogía) y las de «todos los servicios» no cuentan.
- **Servicios no habilitables:** cada servicio lleva `habilitable` ∈ `si | no | modalidad | sin_habilitacion_propia` y `marco`. Los que no son `si` se muestran con su marco, sin estado de cumplimiento de servicio; sus exigencias propias (si las hay) se evalúan, pero la tarjeta dice el porqué. Imágenes se parte en **744** (rayos X, num. 11.3.4.1, baja complejidad) y **745** (ecografía, num. 11.3.4.2, mediana complejidad), cada uno con su `complejidad` (numerales de las investigaciones; por confirmar en el texto oficial).
- **`area_libre_por_puesto`** (4.2): se calcula con la planta y queda `por_confirmar` mientras el mínimo venga de una guía secundaria.
- **Imágenes 744 y 745:** las líneas del servicio `imagenes` de `dotacion.json` se asignan a uno u otro por el recinto donde quedan (sala de rayos X y su control, 744; ecografía, 745); las comunes (vestidor, protección radiológica, PACS) van a 744 y se listan también en 745 sin contarlas dos veces.
- **Texto obligatorio** (`texto_alcance`) en la tarjeta de C y en `docs/15`.

## 5. Contrato 3 · CATÁLOGO 3D de equipos (`web/js/equipos3d.js`, equipo C)

### 5.1 Principios

- Modelos **procedurales** de bajo costo hechos con cajas, cilindros y perfiles extruidos de three (sin texturas). Cada `modelo3d` tiene dos niveles de detalle: **LOD0** (detallado: barandas, ruedas, pantallas, brazos; ≤ 600 triángulos, ≤ 1.500 en rayos X, unidad odontológica y cabina de bioseguridad) y **LOD1** (≤ 4 cajas, ≤ 48 triángulos).
- Dimensiones **reales en metros** tomadas de `catalogo.modelos[...].dim_m` (llega en `torre_inventario.json`); el código no inventa medidas. Origen en el centro de la base, espalda hacia −y local (convención 4.3).
- **Un solo material opaco** con colores por vértice (`MeshStandardMaterial({ vertexColors: true, roughness: 0.7, metalness: 0.05 })`) para todo el equipo; uno transparente aparte para vidrios y acrílicos (incubadoras, cunas) y otro para las unidades fantasma del cierre de brechas (opacidad 0,35, `depthWrite: false`). Paleta fija: acero inoxidable, blanco clínico, tapiz azul, gris de equipo, pantalla oscura, verde de oxígeno, rojo de carro de paro, madera.
- **Geometrías compatibles para fundir:** `geometria()` normaliza cada pieza antes de `mergeGeometries` (que en three 0.160 devuelve `null` si unas tienen índice y otras no, o si no comparten atributos; `BufferGeometryUtils.js:125-150`): `g = g.index ? g.toNonIndexed() : g`, borra `uv`, agrega `color` a todas y llama `computeVertexNormals()` en las extruidas. Ninguna llamada a `geometria` puede devolver `null`.
- **Agrupación por calidad** (presupuesto del 5.2):
  - **baja:** todo el equipo estático del piso se funde en **una malla opaca y una transparente** (con tabla `rangos` `faceIndex → unidad` para la selección), más la malla fantasma.
  - **media y alta:** por piso, los modelos con ≥ 4 unidades van en un `InstancedMesh` (una llamada por modelo) y los demás en una malla fundida con `rangos`; si los instanciados superan el presupuesto de llamadas, se funden los modelos con menos unidades hasta entrar.
  - **Recinto actual:** los objetos de menos de 0,3 m y el LOD0 (en media) van en **una malla fundida por recinto que se arma al entrar en él** y se libera al salir; no se rehacen las instancias del piso.
- **Sin sombras de equipos en el recorrido** (la luz del sol se apaga, 6.7). Fuera del recorrido no se dibujan equipos.

### 5.2 Presupuesto por piso (recorrido)

| Calidad | Llamadas de dibujo del piso (equipos + muros, pisos, cielo, puertas y vidrios) | Triángulos del piso | LOD |
|---|---|---|---|
| baja (teléfono 390 × 844) | **≤ 30** (≤ 8 de la planta) | **≤ 120.000** | LOD1; objetos de menos de 0,3 m solo en el recinto actual |
| media (1400 × 900) | **≤ 45** | ≤ 150.000 | LOD0 en el recinto actual (malla por recinto); LOD1 en el resto |
| alta | ≤ 45 | ≤ 200.000 | LOD0 |

Estas son las únicas metas de rendimiento del recorrido (6.7 y 13.3 remiten aquí); quedan dentro del presupuesto de 50 llamadas de `docs/09:275`.

### 5.3 API

```js
// web/js/equipos3d.js — importa { THREE } de './core.js' y mergeGeometries de 'three/addons/utils/BufferGeometryUtils.js'
export const MODELOS;                         // Set con los ids de la lista cerrada (Anexo C); lanza error si llega uno desconocido
export function aThree([x, y, z], nivel /* { z } del nivel; z de la unidad es sobre el piso terminado */) { /* → new THREE.Vector3(x, nivel.z + z, -y) */ }
export function geometria(modelo, dim /* [ancho, fondo, alto] m */, lod /* 0 | 1 */) /* → THREE.BufferGeometry no indexada, con position, normal y color; nunca null */;
export function crearCapaEquipos(unidades /* UnidadWeb[] de un piso */, catalogo, nivel, {
  calidad = 'baja' /* 'baja' | 'media' | 'alta' */, minInstancias = 4, ocultarDentro = true /* oculta solo montaje === 'dentro' */,
} = {}) /* → CapaEquipos */;

/** @typedef {{
 *   objeto: THREE.Group,
 *   pick(raycaster: THREE.Raycaster): { unidad: string, punto: THREE.Vector3, distancia: number } | null,
 *   resaltar(ids: string[] | null): void,                                             // null quita el resaltado
 *   colorear(ids: string[] | null, color: THREE.ColorRepresentation | null): void,   // reemplaza (no multiplica) el color; null restaura
 *   fantasma(on: boolean): void,                                                      // muestra u oculta la malla del cierre de brechas
 *   entrarRecinto(id: string | null): void,                                           // arma la malla del recinto actual (objetos pequeños y LOD0)
 *   desplazar(id: string, dx: number, dy: number): void,                              // m en planta (vista sísmica)
 *   centro(id: string): THREE.Vector3,
 *   stats(): { llamadas: number, triangulos: number, instancias: number },
 *   dispose(): void
 * }} CapaEquipos */
```

- `UnidadWeb` es la fila compacta de `torre_inventario.json` (10.2). `pick` usa `intersection.instanceId` en las `InstancedMesh` y la tabla `rangos` en las mallas fundidas. Las unidades con `apoyo` se dibujan sobre su apoyo; las de `montaje: 'dentro'` no se dibujan con `ocultarDentro`.
- **Fantasma:** las unidades con `estado: 'cierre_brechas_propuesto'` van siempre en la malla fundida transparente propia; `fantasma(on)` solo la muestra u oculta (un `InstancedMesh` tiene un solo material: no se puede volver transparente una parte de sus instancias sin un *shader* propio).
- **Color y resaltado:** cada `InstancedMesh` se crea con `instanceColor` inicializado en blanco (así three no recompila el programa al primer `setColorAt`, `WebGLRenderer.js:1831`). `colorear` reescribe el color de vértice del rango en las mallas fundidas y usa `setColorAt` en las instancias, que multiplica: por eso `resaltar` no usa color sino una caja envolvente aparte (`Box3Helper` o contorno) alrededor de las unidades.
- **Desplazar:** después de `setMatrixAt`, `instanceMatrix.needsUpdate = true` y `computeBoundingSphere()` (si no, el recorte por pantalla y `raycast` usan la esfera vieja; `InstancedMesh.js:144-149`). En la malla fundida se reescriben las posiciones del rango.

## 6. Contrato 4 · RECORRIDO 3D (equipo C)

### 6.1 Módulos

| Archivo | Responsabilidad |
|---|---|
| `web/js/scenes/torre/recorrido.js` | Modo «Recorrer por dentro»: entra, sale, controla cámara, piso actual, panel, ficha, capas |
| `web/js/scenes/torre/planta3d.js` | Geometría de un piso desde `torre_plantas.json` (muros con vanos, piso por grupo, cielo, puertas, vidrios, escaleras) y rejilla de colisión; la reutiliza D en «Pisos por servicio» |
| `web/js/scenes/torre/controles_fp.js` | Primera persona: teclado, ratón con Pointer Lock opcional, joystick táctil y arrastre para mirar |
| `web/js/scenes/torre/minimapa.js` | Minimapa en `<canvas>` 2D |
| `web/js/scenes/torre/habilitacion.js` | Tarjeta «Dotación para la habilitación» (matriz de cumplimiento en dotación e infraestructura e inventario), con el `texto_alcance` del 4.8 siempre visible |

### 6.2 API

```js
// recorrido.js
export async function montar(ctx) /* → Promise<Recorrido>; se llama una sola vez por vista */;
/** ctx: {
 *   st: Stage,                        // el Stage de la torre (core.js)
 *   raiz: HTMLElement,                // section#v-torre
 *   hud: HTMLElement,                 // [data-slot="torre.hud.recorrido"] dentro del .stage (hidden hasta entrar)
 *   panel: HTMLElement,               // [data-slot="torre.panel.recorrido"]
 *   ficha: HTMLElement,               // [data-slot="torre.ficha.modo"]
 *   datos: { plantas, inventario, habilitacion, coloresContraste /* Map<idRecinto, THREE.Color> que calcula D (9.2); opcional */ },
 *   exterior: { ocultar(on: boolean): void },   // D: oculta obra_nueva del GLB, gPisos, hospital y árboles
 *   textos: { limpio, esc, escH },    // de web/js/scenes/torre/textos.js (D)
 *   alSalir(): void                   // D vuelve al modo «Con la torre»; solo se llama si la salida la pidió la persona
 * }
 * Recorrido: {
 *   entrar(op?: { piso?: number | 'BT', recinto?: string, unidad?: string }): void,   // llama ctx.exterior.ocultar(true)
 *   salir(op?: { porUsuario?: boolean }): void,                                     // llama ctx.exterior.ocultar(false); ctx.alSalir() solo si porUsuario
 *   irA(destino: { piso?: number | 'BT', recinto?: string, unidad?: string }): void,
 *   alReanudar(): void,               // D lo llama después de st.start(): Engine.attach reactiva OrbitControls (core.js:195)
 *   capa(nombre: 'faltantes' | 'contraste' | 'estado', on: boolean): void,
 *   estado(): { piso: number | 'BT', recinto: string | null, posicion: [number, number], rumbo_deg: number, en_muro: boolean },   // para QA
 *   libre(x: number, y: number): boolean,   // rejilla de colisión del piso actual (QA)
 *   dispose(): void                   // quita su función de st.frameFns, libera geometrías y oyentes
 * } */

// planta3d.js
export function construirPiso(nivel, { tier = 'media', colorPor = 'grupo' /* 'grupo' | 'estado' | 'contraste' | null */, grupos /* plantas.grupos_1633 */, cielo = true, envolvente = true } = {})
  /* → { grupo: THREE.Group, mallaMuros: THREE.Mesh, recintoEn(x, y): string | null, colorearRecintos(mapa: Map<string, THREE.Color>): void, etiquetas(): [{ recinto, texto, punto }], stats(), dispose() } */;
export function rejillaColision(nivel, { celda = 0.10, radio = 0.30, obstaculos = [] /* huellas de equipos grandes y obstaculos_recorrido */ } = {})
  /* → { libre(x, y): boolean, mover([x, y], [dx, dy]): [number, number], camino(a, b): [number, number][] | null } */;

// habilitacion.js
export function pintarHabilitacion(el, habilitacion, inventario, { verEn3D /* (destino) => void */, textos }) {}
```

### 6.3 Geometría del piso

- Muros desde `muros[]` con su espesor y altura; vanos de puertas (2,10 m) y ventanas (antepecho 1,0 m, alto 2,0 m) cortados en tramos; dintel encima. Todo fundido por material: pañete blanco (interiores), ladrillo (cara interior de fachada, color `#b5562f` de `programa.json`), concreto (núcleos), vidrio (transparente, doble cara). Puertas abiertas a 90° en el lado de `abre`, fundidas.
- Piso: un polígono por recinto con color de su grupo (tono suave del `color_hex` de `grupos_1633`) o del estado de cumplimiento o del contraste, en **una** malla con colores por vértice.
- Cielo a la altura libre (3,0 m), una cara hacia abajo; se oculta si la cámara sale por encima (vista de planta del minimapa no lo necesita).
- Escaleras de los núcleos como bloque de peldaños simple (LOD1) y cabinas de ascensor de 1,40 × 2,40 m. El hueco de la escalera abierta del vestíbulo en el piso 2 se dibuja con baranda y es obstáculo (3.3).
- La envolvente (fachada con ventanas) la dibuja `planta3d.js` con la cara interior visible: por eso el recorrido oculta `obra_nueva` del GLB (fachadas de una cara y entrepisos de 4,30 m).

### 6.4 Movimiento, teclado, selección y colisión

- **Altura de ojos** 1,60 m sobre el nivel del piso (`nivel.z + 1,60`).
- **Campo de visión:** al entrar, `camera.fov` (vertical) = `clamp(2·atan(tan(37,5°)/aspecto), 60°, 90°)`, que da ≈ 75° horizontales salvo en pantallas muy verticales, donde el límite de 90° deja ≈ 70° (cálculo propio: con la cámara de la torre, de 36°, el teléfono de ≈ 358 × 506 px del recuadro ve solo ≈ 26° horizontales). Se recalcula cuando cambia `camera.aspect` (comparándolo en la función de `onFrame`) con `updateProjectionMatrix()`. Al salir, y antes de cualquier `frameBox` (que clona la cámara, `core.js:415`), se restaura 36°.
- **Teclado.** Un solo oyente `keydown`/`keyup` en `window`, con el patrón de `ciudad.js:344` ampliado: atiende solo si `!raiz.hidden && st.isActive() && st.inView && modo === 'recorrido'`, sin `altKey`, `ctrlKey` ni `metaKey`, y si el destino no es `INPUT`, `TEXTAREA`, `SELECT` ni un elemento editable. Para moverse usa `ev.code` (`KeyW`, `KeyA`, `KeyS`, `KeyD`, `ArrowUp`…; así funciona con cualquier distribución de teclado) y llama `preventDefault()` solo en las teclas que atiende. Las flechas, `RePág`/`AvPág` y `Espacio` actúan solo si el foco está dentro de `.stage` (o con el puntero tomado); `Tab` pasa al panel (en pantalla completa recorre los controles del recuadro). El estado de teclas oprimidas se vacía en `blur`, `visibilitychange`, `pointerlockchange` y al detener la vista (`st.stop()`, que `main.js:58` llama al cambiar de vista).
  - Teclas: `W`/`↑` avanzar, `S`/`↓` retroceder, `A`/`D` paso lateral, `←`/`→` girar (120 °/s), `Shift` caminar rápido (1,4 m/s normal; 3,0 m/s rápido), `R`/`F` o `RePág`/`AvPág` subir o bajar de piso, `Espacio` saltar (en el modo espectador, subir; `Shift`, bajar), `V` modo espectador, `P` pantalla completa, `M` minimapa, `I` lleva el foco al panel (en pantalla completa, primero sale de ella), `Esc` suelta el puntero (si estaba tomado), luego sale de la pantalla completa (si lo estaba; el navegador puede hacer las dos cosas con un solo `Esc`) y, con el siguiente `Esc`, sale del recorrido. Atajos documentados con `title`, en la `aria-label` del recuadro y en la ayuda `.stage-hint`.
  - **Foco:** al entrar, C da a `.stage` `tabindex="-1"`, `role="application"` y una `aria-label` con los atajos, y la enfoca con `focus({ preventScroll: true })`; al salir quita esos atributos. El bloque CSS de C agrega un estilo `:focus-visible` para `.stage`.
- **Ratón.** Arrastrar para mirar (ángulo vertical limitado a ±80°). El clic simple **selecciona**; el Pointer Lock se pide con el botón «Mirar con el ratón» de la barra o con doble clic y, en pantalla completa, al entrar en ella y con un clic en el lienzo (que entonces no selecciona), solo en escritorio y si está disponible (puede estar bloqueado dentro de un iframe o un Artifact; si el navegador lo niega, no se vuelve a pedir solo y el clic selecciona): sin él, arrastrar sigue funcionando. Un clic selecciona solo si el puntero se movió menos de 5 px y pasaron menos de 300 ms entre `pointerdown` y `pointerup` (así terminar un arrastre no selecciona). Con el puntero tomado se muestra una retícula central y se selecciona con `raycaster.setFromCamera({ x: 0, y: 0 }, camara)`.
- **Qué se selecciona.** El recorrido hace su *raycast* contra `[planta.mallaMuros, capa.objeto]` y acepta la unidad solo si es el primer impacto (un clic sobre un muro no selecciona la cama del recinto vecino). Las unidades `dentro` de un contenedor resaltan su contenedor; la ficha del contenedor lista su contenido.
- **Táctil** (pantallas con `pointer: coarse`): joystick virtual abajo a la izquierda (110 px, avanza y gira; `left: 16px; bottom: 16px; touch-action: none`), arrastre en el resto para mirar, barra `.nav3d` con «Subir», «Bajar», «Minimapa», «Salir» y, a la derecha del recuadro, una columna de botones: saltar (en el espectador, subir y bajar) y, en pantallas de 720 px o menos, pantalla completa y modo espectador. La ayuda `.stage-hint` se oculta en el recorrido con puntero táctil.
- **Colisión:** rejilla de 0,10 m con muros (por espesor), columnas, núcleos cerrados (abiertos en puertas), `obstaculos_recorrido` (hueco de la escalera abierta en el piso 2) y huellas de equipos de piso de más de 0,5 m²; el obstáculo se infla el radio del caminante (0,30 m en la primera versión; 0,20 m desde el 25-oct-2026, porque con 0,30 m una puerta de 0,90 m dejaba 0,20 m de paso y ≈ 42 % del piso de los pisos 1 a 3 quedaba bloqueado) y el movimiento se resuelve por ejes (se desliza a lo largo del muro). El vano de cada puerta de un núcleo de escalera y 0,45 m a cada lado son piso (el descanso empieza en la cara libre de la estructura). Los equipos y los `obstaculos_recorrido` con altura dejan su altura en la rejilla (`alto`) y aparte va la rejilla inflada sin ellos (`duro`): quien salta (Espacio, 1,20 m) pasa por encima o se para sobre ellos; muros, columnas, barandas, vacíos y la vegetación no se saltan, y los dinteles de las puertas y lo que cuelga desde 1,80 m detienen la cabeza. El modo espectador (V) y la pantalla completa (P) están en `docs/09`. Las puertas a `exterior` no se cruzan: a menos de 0,6 m de una aparece el botón «Salir del edificio» (vuelve a la vista exterior, `salir({ porUsuario: true })`).
- **Cambio de piso:** en el vestíbulo de ascensores o en una escalera, o desde cualquier punto con `R`/`F` (lleva al vestíbulo de ascensores del piso destino). El **bloque técnico** se alcanza desde la lista «Ir a…» y desde la barra («Bloque técnico»), entrando por su puerta exterior. Con `prefers-reduced-motion` el salto es instantáneo; si no, un fundido de 250 ms (sin animar la cámara).

### 6.5 Panel del ambiente y ficha del equipo

- **Panel** (`torre.panel.recorrido`): nombre del recinto, servicio, piso, área a ejes y libre, estado de cumplimiento en dotación e infraestructura con su conteo (exigibles y, aparte, por confirmar) y la **lista de dotación del recinto** agrupada por línea (cantidad × nombre, clase de riesgo, «exigido (texto oficial)» o «según guía secundaria; por confirmar» según `exigible`, «recomendado», «faltante (cierre propuesto)»). Cada fila es un `<button>` que resalta la unidad y abre su ficha. Nombre del recinto en una región `aria-live="polite"` que cambia al entrar a otro recinto. Lista «Ir a…» de los recintos del piso y del bloque técnico (botones) para quien no puede caminar con teclado o joystick.
- **Ficha** (`torre.ficha.modo`): nombre, especificación, servicio, ambiente, clase de riesgo (vigente y revisión con su regla), registro INVIMA (requerido, vía, si se puede usado), exigencias (numeral; texto corto entre comillas solo si `texto_disponible`, y si no «resumen; texto oficial no obtenido»; nivel de verificación y enlace), prioridad (y `prioridad_revisada` con su `norma_base`, si la hay), mantenimiento (porcentaje anual, vida útil, personal inscrito, calibración), precio con su tipo y fuente, campos que se llenan al comprar, **implementos internos** agrupados por compartimiento (los equipos biomédicos componentes con su clase y registro) y, si aplica, «riesgo en un sismo» (anclaje y, si la vista sísmica ya corrió, lo que le pasó). La `nota_interna` de la línea no se muestra. Todos los textos pasan por `textos.limpio` (13.6).
- **Etiquetas 3D:** solo las del recinto actual y a menos de 6 m, máximo 12, con clase `lbl-node` (entra en el reacomodo de `core.js`). C debe reutilizar las etiquetas o sacarlas de `st._labels` al destruirlas (no hay función para quitarlas; `core.js:385-394`).
- **Capas** (botones en el panel): «Faltantes» (malla fantasma del cierre de brechas y recintos con exigencias exigibles que faltan, tintados), «Cumplimiento en dotación e infraestructura» (piso por estado), «Comparar con el proyecto tipo» (colores de `ctx.datos.coloresContraste`, que solo tiñen recintos con `veredicto_tipo`; 9.2).

### 6.6 Minimapa

`<canvas>` 2D dentro de `torre.hud.recorrido`, en `top: 44px; right: 10px` (debajo del botón «Rendimiento» de `core.js:587-593`, `index.html:75`); se oculta mientras el panel de rendimiento (`.hud`, `top: 42px`) está abierto. 160 × 300 px en escritorio, oculto por defecto en el teléfono. Recintos del piso con su color, el caminante como flecha, clic para ir a la puerta del recinto tocado. Toma sus colores de `tokens()` y se redibuja con `onTheme` (claro u oscuro) y cuando cambia la posición o el piso. Lleva `aria-hidden="true"`: su alternativa accesible es la lista «Ir a…».

**Distribución sobre el recuadro** (bloque CSS de C): `[data-scene="torre"] .torre-hud { position: absolute; inset: 0; pointer-events: none; z-index: 2 } [data-scene="torre"] .torre-hud > * { pointer-events: auto }`; `[data-scene="torre"] .nav3d` arriba a la izquierda en todos los anchos, con `max-width: calc(100% - 132px)` (en el teléfono, la regla de `index.html:270` la baja al borde inferior, donde iría el joystick: el bloque de C la sobrescribe para la torre); joystick como en 6.4.

### 6.7 Luz y rendimiento

- Al entrar: `st.sunLight.castShadow = false`, `st.hemi.intensity` × 3 y luz ambiental tenue propia; se restaura al salir. Sin sombras de equipos.
- Solo el piso actual es visible y tiene geometría en memoria; el siguiente se arma al pedirlo (≤ 300 ms en escritorio).
- Metas de llamadas y triángulos: las del 5.2 (panel Rendimiento de `core.js:585-613`).

### 6.8 Integración con `Stage` y `torre.js` sin romper los modos actuales

**Por qué no basta `controls.enabled = false`.** En three 0.160, `OrbitControls.update()` no mira `enabled` (`examples/jsm/controls/OrbitControls.js`, l. 186-283): en cada cuadro recalcula la posición desde `controls.target`, recorta la distancia a `minDistance` (6 m en la torre, `torre.js:50`) y el ángulo polar a `maxPolarAngle = 0,47π` (`core.js:287`) y hace `camera.lookAt(target)`. Como las `frameFns` corren antes de `update()` (`core.js:207-208`), una orientación puesta a mano se perdería en el mismo cuadro. Además, `adaptDepth` (`core.js:364-367`) calcula `near = distancia(cámara, controls.target) × 0,012`, y el radio de la oclusión ambiental (`post.js:113-114`) usa la misma distancia. Por eso el recorrido **conduce la cámara a través del objetivo de los controles**:

1. **Al entrar** (D): `st.stopFlight()` (detiene un vuelo GSAP en curso de la entrada de la vista o de `encuadre()`, `core.js:400`) y cancela los `setTimeout` de encuadre que `torre.js:300-303` deja pendientes al cambiar de modo; vacía la selección del Stage: `guardados = st.pickables.splice(0); st.hovered = null;` (los oyentes `pointermove` y `click` del lienzo, `core.js:323-324`, siguen activos y el `Raycaster` de three 0.160 no mira `visible`, `src/core/Raycaster.js:88-104`: sin esto, los grupos ocultos de «Pisos por servicio», `torre.js:143`, seguirían recibiendo clics y `fichaPiso` reescribiría la ficha); luego `const mod = await import('./torre/recorrido.js'); rec ??= await mod.montar(ctx); rec.entrar(op)`.
2. **En `entrar`** (C): guarda los parámetros de los controles (`target`, `minDistance`, `maxDistance`, `minPolarAngle`, `maxPolarAngle`, `enableDamping`, `enableRotate`, `enableZoom`, `enablePan`) y el `fov`; hace un `controls.update()` y luego `enableDamping = false` (vacía el giro residual); pone `enableRotate = enableZoom = enablePan = false`, `minDistance = 0.01`, `maxDistance = 10`, `minPolarAngle = 0.01`, `maxPolarAngle = Math.PI - 0.01`, el `fov` del 6.4 y `st.userMoved = true` (para que `resize`, `core.js:377-381`, no saque la cámara del edificio). `ctx.exterior.ocultar(true)` lo llama el propio modo.
3. **En cada cuadro:** C registra **una sola** función con `st.onFrame` en `montar` (no en cada `entrar`: `onFrame` solo agrega, `core.js:396`). La función mira una bandera `activo`; después de mover el ojo pone `controls.target.copy(ojo).addScaledVector(adelante, 0.5)`, con lo que `update()` reproduce la misma posición y orientación, `adaptDepth` da el mínimo de 0,05 m (`nearMin`, `core.js:264`) y la oclusión ambiental usa su radio mínimo. Devuelve **`false` explícito** cuando no hay movimiento ni fundido (el motor redibuja si la función no devuelve exactamente `false`, `core.js:207`). En `dispose` se quita con `st.frameFns.splice(st.frameFns.indexOf(fn), 1)`.
4. **`alReanudar`:** `Engine.attach` vuelve a activar los controles cada vez que la vista arranca (`core.js:195`): D envuelve `st.start` en `torre.js` y llama `modoActivo?.alReanudar?.()` después; el modo repite el ajuste del paso 2 (sin volver a guardar).
5. **Al salir** (`salir({ porUsuario })`): restaura los parámetros guardados, el `fov` (36°) con `updateProjectionMatrix()`, las luces y la visibilidad (`ctx.exterior.ocultar(false)`), libera las geometrías del piso (`disposeObject`) y llama `ctx.alSalir()` solo si `porUsuario` (Esc, botón «Salir», puerta a exterior). D restaura `st.pickables.push(...guardados)` y encuadra la torre con `frameBox`. Cuando D cambia de modo (por ejemplo, del recorrido al simulador), llama `salir({ porUsuario: false })` y luego entra al otro modo, sin `frameBox` ni `alSalir` intermedios.
6. **`torre.js:303`:** D quita la llamada a `encuadre()` de la rama `else` para los modos `recorrido` y `sismo` (hoy la hace para cualquier modo nuevo).
7. **Contenedores:** cada modo muestra u oculta solo sus contenedores hijos (2.2, 10.3); al volver a «Hoy», «Con la torre» o «Pisos», D oculta los de los modos y restaura la nota original de `torre.ficha`.

Lo mismo vale para el simulador (8.6): también vacía `st.pickables`, usa `torre.panel.sismo` y `torre.hud.sismo` y no deja vuelos en curso.

### 6.9 Si alguien cree que necesita tocar `core.js`

No hace falta para este contrato. Si en la integración aparece un caso real, solo D lo hace, en un cambio aparte, y repite la QA de las 10 vistas (claro, oscuro, teléfono; consola sin errores; sin desborde horizontal).

---

## 7. Contrato 5 · MOTOR SÍSMICO (equipo A)

### 7.1 Cambios a `data/sismo/ESQUEMA.md` (y por qué)

El contrato existente se respeta. Se **agregan** campos opcionales y una sección de resultados; ningún campo existente cambia de significado. Dos **reglas** del esquema sí cambian, y se dice en el propio `ESQUEMA.md`: la demanda/capacidad que se muestra (E16) y el anclaje del amortiguamiento (E8).

| # | Cambio | Por qué |
|---|---|---|
| E1 | Tipo de elemento `muro_concreto` (columna ancha: Timoshenko con `A`, `I·factor_fisuracion`, `Av`; rótula solo en la base) en «pórticos» de muros con id `MX-…` / `MY-…`. Cada paño lleva el **ancho efectivo de sus aletas** (los paños perpendiculares que llegan a sus bordes; NSR-10 C.21.9.5.2, numeral por confirmar) en `I`, `A` y en el momento-curvatura de la base, con `My_pos_kNm` y `My_neg_kNm` (aleta en compresión o en tracción, como en E3). En la rótula del muro, `k_e = EI_fis/lp` y `theta_y = My·lp/EI_fis`, con `lp = 0,5·lw ≤` altura del piso (ASCE/SEI 41-17, longitud de rótula de muros a flexión; por confirmar) | El prediseño de `presupuesto.json` tiene ≈ 45 m de muros de 0,30 m en los núcleos. Ignorarlos cambiaría la rigidez y, sobre todo, la torsión: los núcleos están todos al oriente (`x 3,1-8,6`) y el centro de masa cerca de `x ≈ −2`. Separar los núcleos (en C o en cajón) en muros planos **sin** aletas subestimaría su rigidez a flexión y a torsión, su carga axial de sismo y el `My` de la base; y `θy = My·L/(6EI)` es de doble curvatura, no de un muro en voladizo. Limitación declarada (8.5): sin compatibilidad vertical en las esquinas y sin variación de la resistencia con la carga axial del sismo |
| E2 | `brazo_rigido_m: [di, dj]` opcional en vigas y columnas | Zona rígida del nudo (columnas de 0,60 m): longitud flexible `L_f = L − di − dj` |
| E3 | `My_pos_kNm` y `My_neg_kNm` opcionales en secciones de viga y de muro (si faltan, se usa `My_kNm`) | En vigas el refuerzo superior y el inferior son distintos: la fluencia es asimétrica |
| E4 | `w_gravedad_kN_m` opcional en vigas y `carga_kN` opcional en nodos; el motor hace primero un análisis estático de gravedad y el dinámico parte de ese estado | Los momentos de gravedad en los extremos de las vigas adelantan o retrasan la fluencia; sin ellos las rótulas salen simétricas y falsas |
| E5 | `resortes[].aislado: true \| false` | Grupo IV: los muros de fachada y divisorios se separan de la estructura (NSR-10 A.9; numeral del grado de desempeño por confirmar). Aislado = sin rigidez, pero se evalúa su daño con la deriva del entrepiso (estados de daño del esquema). `false` permite el «qué pasa si no se aíslan» con el modelo de Tomaževič |
| E6 | Ejes con nombre (1.2) y convención de ids: pórticos `X-{n}` (a lo largo de x en la línea n) y `Y-{L}`; nodos `X-3/A0`; columnas `C-A3-1@X` y `C-A3-1@Y` con campo `fisico: "C-A3-1"`; vigas `VX-3-AB-1`, `VY-A-34-1`; muros `MY-D6-1` | La misma columna aparece en dos pórticos (TABS): los ids deben ser únicos y la vista necesita saber cuál es la columna física para dibujar una sola |
| E7 | `niveles[].contorno` (polígono del diafragma) | Dibujar la losa que se mueve, calcular `Jz` y medir la deriva en los vértices (E9); el piso 4 retrocede |
| E8 | `amortiguamiento: { "tipo": "rayleigh", "xi": 0.05, "periodos_ancla_s": [Ti, Tj] \| null, "rigidez": "inicial_parte_elastica" }`. Si `periodos_ancla_s` es `null`, el motor usa `Ti = T1` y `Tj` = el menor entre el período con el que la masa participativa acumulada llega a ≥ 90 % en x y en y y `0,2·T1`, con la rigidez inicial. `modos` sigue aceptándose, pero `periodos_ancla_s` manda si están los dos, y los validadores avisan si se usa `modos` | En el modelo pseudotridimensional los modos 1 a 3 suelen ser los tres fundamentales (x, y, torsión), con ω3 ≈ 1,2-1,5·ω1: anclar en 1 y 3 sobreamortigua los segundos modos (con ω3 = 1,3·ω1: ξ ≈ 7,5 % en 3ω1, 11 % en 5ω1 y ≈ 22 % en 10ω1; cálculo propio) y baja las aceleraciones de piso con las que se evalúa la dotación. «Parte elástica»: la matriz de amortiguamiento sale de la rigidez inicial de la parte elástica de cada elemento, **nunca de las rótulas** (7.4), para que OpenSees con `rayleigh(a0, 0, a1, 0)` y `zeroLength` sin Rayleigh sea réplica exacta y para evitar el amortiguamiento espurio después de la fluencia (Charney, 2008) |
| E9 | `limites.deriva_umbral_dano: 0.004` y `limites.deriva_umbral_dano_mamposteria: 0.002` (NSR-10, Tabla A.12.5-1: 0,40 %, y 0,20 % en mampostería que no cumpla A.12.5.3.1; `normas.json`, tema «Derivas», dato oficial). La deriva se compara como **vector**: `√(Δx² + Δy²)` en los vértices del `contorno` de cada nivel (NSR-10 A.6.3.1, ec. A.6.3-1; numeral por confirmar) | La vista, el prediseño y los criterios del 13.1 comparan con 1 % (sismo de diseño) y 0,4 % (umbral de daño). Con la torsión de los núcleos al oriente, las esquinas se mueven en las dos direcciones a la vez: comparar cada componente por separado subestima la deriva hasta en √2 |
| E10 | `secciones[].interaccion_PM` opcional (pares `[P_kN, My_kNm]`) — fase 2; el motor puede ignorarla y la validación corre sin ella | Variación de la fluencia de columnas y muros con la carga axial sísmica |
| E11 | Sección nueva «Resultados del motor» (7.6) y «Mensajes del trabajador» (7.5) | El esquema solo decía «devuelve resultados para animar» |
| E12 | Coordenada `s` de los nodos: `s = x` en pórticos X y `s = y` en pórticos Y | Estaba implícito |
| E13 | Bloques adicionales al esquema: `ejes`, `sistema` (7.2, paso 0), `prediseno`, `generado_por`, `fecha` | Trazabilidad |
| E14 | P-Delta por nivel con el peso y la posición del centro de masa de **cada** nivel de encima (7.4). `P_sobre_entrepiso_kN` se conserva como dato informativo; el motor usa `peso_sismico_kN`, `cm`, `masa_t` y `Jz_t_m2` de cada nivel | Con el retroceso, el centro de masa del piso 4 queda ≈ 6 m al norte del de los niveles 1-3 (estimación): la carga total por entrepiso no dice dónde actúa |
| E15 | Transición entre regímenes de profundidad en una banda de 40 a 70 km (7.4), sin cambiar ningún número de `amenaza.json` | Con un umbral brusco en 50 km, mover la profundidad 1 km cambiaba el PGA hasta 3 a 4 veces (prueba de la revisión con `sim.py`: Mw 6,2 a 92 km, 0,0247 g con h = 49,9 km y 0,0795 g con h = 50 km): era un artefacto del umbral, no física |
| E16 | Propiedades **esperadas** en las rótulas: `My_e_kNm` (y `My_e_pos_kNm`, `My_e_neg_kNm`), `Mn_e_kNm`, `Vn_e_kN`, `theta_y_e`, con los factores de material esperado de ASCE/SEI 41-17 para f'c y fy (declarados en `calculo`; por confirmar) y φ = 1; y límites de rotación plástica `theta_p_IO`, `theta_p_LS`, `theta_p_CP` además de los parámetros de modelado `theta_p_cap` («a») y `theta_p_b` («b»). Nueva regla de la demanda/capacidad que se muestra: flexión `\|M\|/Mn_e`, cortante `\|V\|/Vn_e`, rotación `θp/theta_p_IO` por defecto (grupo IV: ocupación inmediata), con marcas de LS y CP. `phiMn_kNm`, `phiVn_kN` y `My_kNm` conservan su significado y se usan en el prediseño | El cociente contra φMn y φVn con fluencia en `My` nominal mezcla criterios de diseño con respuesta; `theta_p_cap` («a») marca el inicio de la pérdida de resistencia, no un límite de desempeño: un elemento con θp ≈ 0,02 rad se pintaba «advertencia» cuando ya había pasado con creces el límite de ocupación inmediata (≈ 0,005-0,010 rad en vigas; por confirmar en ASCE/SEI 41-17) |

### 7.2 `data/sismo/torre_hospital_estructura.json` y `scripts/sismo/estructura_torre.py`

`estructura_torre.py` (Python 3.12, solo biblioteca estándar para que corra en cualquier lado; determinista: misma salida byte a byte) hace el **prediseño NSR-10, grupo IV, DES** con la retícula real y escribe el JSON. Pasos y fuentes:

0. **Sistema estructural (antes del prediseño):** con el modelo elástico, A calcula qué fracción del cortante sísmico resisten los pórticos solos. Si los pórticos resisten de forma independiente ≥ 25 % de las fuerzas sísmicas, el sistema es **dual** (Tabla A.3-4); si no, **combinado** (Tabla A.3-2) (R0, Ω0 y numerales por confirmar). El bloque `sistema` del JSON guarda la fracción calculada, la fila de la tabla, `R0`, `Ω0` y la justificación. Desde aquí todo usa ese sistema.
1. **Geometría:** ejes y niveles del 1.2; 7 pórticos X (líneas 1-7) y 4 pórticos Y (A-D); el nivel 4 solo en las líneas 3-7; columnas de 0,60 × 0,60 m (punto de partida de `presupuesto.json`); vigas que A dimensiona (ancho ≥ 0,25 m en DES); muros de núcleo de 0,30 m con sus aletas (E1): A escoge los paños estructurales cercanos a los 45 m lineales del presupuesto (paños posibles: `x = 3,1` en las dos escaleras y en el foso de ascensores, `x = 8,6`/`6,1`, y los paños en x de cada núcleo) y documenta la elección y la excentricidad resultante.
2. **Cargas (NSR-10 título B):** peso propio desde volúmenes (losa nervada con vigas 0,24 m³/m² × 24 kN/m³ = 5,76 kPa de cálculo propio sobre el dato del presupuesto; columnas y muros por volumen); acabados, cielo e instalaciones (estimación con su cita de la tabla de cargas muertas, por confirmar); muros divisorios y fachada desde las cantidades del capítulo 4 de `presupuesto.json` (3.892 m² interiores: 40 % bloque y 60 % liviano; 1.800 m² de fachada) con pesos unitarios citados; carga viva por ocupación hospitalaria (tabla del título B, por confirmar); equipos de cubierta desde `cubierta_tecnica` (2 tanques de 5 m³ = 10 t de agua, condensadoras, paneles: estimación con posición). Masa sísmica del simulador = muerta + 25 % de la viva (`detalle_masa.viva_25pct` del esquema; supuesto declarado). Cada nivel con `masa_t`, `Jz_t_m2`, `cm`, `peso_sismico_kN` y `contorno`.
3. **Fuerzas de diseño:** espectro de `amenaza.json → nsr10` (Aa = Av = 0,15; suelo D, Fa = 1,5, Fv = 2,2; I = 1,5). `Ct` y `α` de la fila de la Tabla A.4.2-1 que corresponde al sistema del paso 0 (numerales por confirmar): con muros, «otros sistemas», `Ct = 0,049` y `α = 0,75`, da `Ta = 0,049·17,1^0,75 ≈ 0,41 s` y `Cu·Ta ≈ 0,56 s` con `Cu = 1,75 − 1,2·Av·Fv = 1,354` (cálculo propio); la fila de pórticos de concreto (`Ct = 0,047`, `α = 0,9`: 0,605 s y 0,82 s) **no** aplica si los muros se modelan. El período para la FHE es el del modelo limitado a `T ≤ Cu·Ta`. FHE con exponente `k` y análisis modal espectral con el mismo modelo pseudotridimensional (implementado en Python); el cortante modal se ajusta para que sea ≥ 80 % de la FHE en estructura regular o ≥ 90 % en irregular (A.5.4.5; por confirmar). Torsión accidental del 5 %. `R = φa·φp·φr·R0` con cada factor justificado (irregularidades en altura, en planta y ausencia de redundancia). **Irregularidades** con sus cocientes: torsional 1aP/1bP (deriva máxima en un borde frente al promedio de los dos bordes, contra 1,2 y 1,4) y geométrica en altura 3A (42/30 = 140 % > 130 % por el retroceso del piso 4); numerales por confirmar. **Deriva** con fuerzas sin reducir, como vector en los vértices del contorno (E9): **≤ 1 %** en todos los entrepisos (Tabla A.6.4-1).
3b. **Umbral de daño (grupo IV):** análisis elástico con el espectro de umbral de daño (Ad = 0,04; forma, amortiguamiento y rigidez de A.12.3-A.12.4, por confirmar), deriva vectorial ≤ 0,4 % con los muros aislados y ≤ 0,2 % en el escenario con mampostería adherida (`aislado: false`). Resultado en `prediseno.derivas_umbral_dano`; es **criterio que bloquea** (13.1).
4. **Secciones:** refuerzo longitudinal y transversal con las cuantías y reglas del capítulo C.21 (numerales por confirmar); columna fuerte-viga débil (ΣMnc ≥ 1,2 ΣMnb) en cada nudo; cortante por capacidad con `Mpr` (1,25 fy, φ = 1).
5. **Propiedades de rótula (calculadas, no supuestas):** `momento_curvatura` por fibras (concreto confinado de Mander, acero bilineal con endurecimiento), con propiedades **nominales** para el prediseño (`My`, `Mn` con deformación última del concreto 0,003, `φMn`, `Mpr`, `Vn`, `φVn` del capítulo C.11/C.21) y **esperadas** para la simulación (E16: `My_e`, `Mn_e`, `Vn_e` con los factores de ASCE/SEI 41-17 para f'c y fy, por confirmar, y φ = 1). `theta_y = My·L_f/(6·EI_fis)` en vigas y columnas (doble curvatura; nominal, con el significado que ya tiene en el esquema) y `theta_y = My·lp/EI_fis` en muros (E1), más `theta_y_e` con `My_e` (la que usa la simulación). Parámetros de ASCE/SEI 41-17 (tablas de vigas, columnas y muros de concreto; numerales por confirmar): `theta_p_cap` («a»), `theta_p_b` («b») y los límites `theta_p_IO`, `theta_p_LS`, `theta_p_CP`. Factores de fisuración: columnas 0,70, vigas 0,35, muros 0,35 fisurados (estimación con cita de la NSR-10 C.10; numeral por confirmar). Núcleos con aletas efectivas (E1), con momento-curvatura positivo y negativo. Cada sección trae su campo `calculo` con fórmulas, factores y artículo.
6. **Muros de mampostería:** fachada (ladrillo 15 cm) y divisorios de bloque como `resortes` con `aislado: true` y sus estados de daño; un juego alterno con `aislado: false` para el escenario «sin aislar».
7. **Salida extra** `prediseno`: sistema y `R` con sus factores; período fundamental del modelo, `Ta` y `Cu·Ta` del sistema adoptado; cortante basal de diseño (FHE y modal, con el factor de ajuste); derivas vectoriales por entrepiso con el punto donde ocurren (`derivas_vector`) y por pórtico; `derivas_umbral_dano`; irregularidades con sus cocientes; relaciones columna-viga; cuantías; excentricidades y centro de rigidez por nivel; `periodos_ancla_s` del amortiguamiento (E8) con el ξ efectivo de los 12 primeros modos; y la lista de supuestos e incertidumbres (sin estudio de suelos: base empotrada sobre los dados de pilotes; sin interacción suelo-estructura).

### 7.3 `data/sismo/amenaza.json`

Copia de `data/sismo/fuentes_investigacion/amenaza.json` (84 KB) **sin cambiar números**. A agrega: el escenario del sismo de 7,4 del 10-ago-2026 en `escenarios_lejanos_sentidos` con la nota de la inconsistencia del epicentro (OPS: San José del Palmar; anexo C: Pereira) y su distancia (≈ 342 o 313 km, fuera del rango de 300 km; cálculo propio de la investigación); y `implementacion_de_referencia: "scripts/sismo/estocastico.py"` (puerto de `data/sismo/fuentes_investigacion/sim.py` y `gmpe.py`). La banda de transición de profundidad (E15) es una regla del motor, no un número nuevo de este archivo. Todo lo sismotectónico sigue **por confirmar** (centro del nido, distancias a fallas, magnitudes máximas).

### 7.4 Módulos JavaScript (puros: sin DOM, sin three, sin especificadores del importmap; imports relativos con extensión `.js`)

```js
// web/js/sismo/movimiento.js
export function regimenPorProfundidad(h_km) /* → { regimen: 'cortical' | 'transicion' | 'intraplaca_profunda', w: number } con w = clamp((h − 40)/30, 0, 1) */;
export function sintetizar(p, amenaza) /* → Registro; siempre con dt = 0,005 s */;
/** p: { Mw: 4..8, profundidad_km: 5..200, distancia_epicentral_km: 0..300, vs30_m_s: 150..760, semilla: entero, regimen?: 'auto'|'cortical'|'intraplaca_profunda', escala_pgar?: número (para la pasada de suelo con la escala «nsr10») }
 *  Registro: { dt, n, ax: Float64Array /* m/s² */, ay: Float64Array, meta: { M0_dina_cm, M0_N_m, energia_J_aprox, f0_Hz, delta_sigma_bar,
 *              beta_s_km_s, rho_s_g_cm3, Q0, eta, kappa0_s, Rhip_km, Ref_km, Tgm_s, t_eta_s, regimen, w_transicion, pga_roca_g },
 *              intensidades: { x: Intensidades, y: Intensidades }, avisos: string[] } */
export function intensidades(a, dt) /* → { pga_g, pgv_cm_s, pgd_cm, arias_m_s, d595_s, t5_s, t95_s } */;
export function espectroRespuesta(a, dt, periodos /* Float64Array s */, xi = 0.05) /* → { Sa_g: Float64Array, Sd_m: Float64Array }; método exacto para excitación lineal por tramos (Nigam y Jennings, 1969) */;
export function espectroFourier(a, dt) /* → { f_Hz: Float64Array, A_m_s: Float64Array } */;
export function espectroObjetivo(p, amenaza, f_Hz, { pgar_g } = {}) /* → { roca: Float64Array, suelo: Float64Array } (Boore 2003; en la transición, mezcla de 7.4) */;
export function gmpe(modelo /* 'bchydro2016_intraslab'|'zhao2006_intraslab'|'zhao2006_cortical'|'bssa14' */, esc, periodos) /* → { mediana_g, sigma_ln } */;
export function espectroNSR10(T, { Aa, Av, Fa, Fv, I }) /* → Sa en g (número o Float64Array) */;
export function filtrarYDiezmar(a, dt) /* → { a: Float64Array, dt: 2·dt }: FIR pasabajos de fase cero a 20 Hz y 1 de cada 2 muestras (calidad baja) */;
export function avisos(p, amenaza) /* → string[] (controles.avisos_de_combinacion y régimen forzado incompatible) */;

// web/js/sismo/modelo.js
export function armarModelo(estructura, { histeresis = 'bilineal' /* | 'clough' */, noEstructurales = 'aislados' /* | 'confinados' */, pDelta = true } = {}) /* → Modelo */;
export function rigidezLateral(modelo, estado /* opcional: estado de rótulas */) /* → Float64Array (3N × 3N, N niveles) */;
export function rigidezPDelta(modelo) /* → Float64Array (3N × 3N): K_PΔ del 7.4 (para pruebas y energía) */;
export function modos(modelo, n = 12) /* → { periodos_s, formas /* n × 3N */, masa_participativa: { x, y, rz }, factores, T1x, T1y } */;
export function amortiguamiento(modelo) /* → { a0, a1, periodos_ancla_s, xi_modos: Float64Array(12) } */;
export function gravedad(modelo) /* → EstadoInicial (momentos, axiales, desplazamientos u_g) */;
export function resumenModelo(modelo) /* → { niveles, porticos, nodos, elementos, gdl_dinamicos, gdl_condensados, masa_total_t, peso_kN, cm, centro_rigidez, excentricidad, sistema } */;
export function infoElementos(modelo) /* → [{ id, tipo, portico, nivel, fisico, i, j, xyz_i: [x,y,z], xyz_j: [x,y,z], seccion }] (para la vista) */;

// web/js/sismo/integrador.js
export function analizar(modelo, registro, op = {}, alProgreso, senal /* AbortSignal opcional */) /* → { resultados: Resultados (7.6), historia: Historia } */;
export async function analizarPorTramos(modelo, registro, op = {}, { presupuesto_ms = 12, ceder, alProgreso, senal } = {}) /* cede al bucle de eventos cada ≈ 12 ms de cálculo; → { resultados, historia } */;
export function osciladorNewmark({ m, c, k, fy, alfa = 0, dt, n, ag, p, u0 = 0, v0 = 0, P_h = 0 }) /* → { t, u, v, a_abs, fs, energia } (pruebas cerradas) */;
export function riesgoEquipos(estadoPiso /* aceleraciones del diafragma en un paso */, equipos, memoria) /* → actualiza memoria por paso; lo llama el integrador en cada Δt */;
/** op: { dt_s /* 0,005 normal; 0,01 en calidad baja */, dt_salida_s = 0.02, duracion_s, angulo_deg = 0 /* componente 1, antihorario desde el este */,
 *       escala = 1 /* número | 'nsr10' */, calidad = 'normal' /* | 'baja' */, tolerancia = 1e-6, max_iter = 20, max_subdiv = 4,
 *       equipos = [] /* EquipoRiesgo[] */, guardar_serie_completa = false }
 *  EquipoRiesgo: { unidad: string, piso: 1|2|3|4|'BT'|'CUB', x: number, y: number, z_sobre_piso: number, anclaje: string,
 *                  masa_kg: number, h_cg_m: number, mu: number, bx_m: number, by_m: number, rot_z: number /* rad, antihorario desde +x */ }
 *  (bx_m = dim[0]/2 y by_m = dim[1]/2 del catálogo, estimación; ver el ejemplo del Anexo A.2) */
```

**Física y numérica que el motor debe cumplir:**

- **Movimiento (Boore 2003, `amenaza.json → notas_para_implementar`, 12 pasos):** `M0 = 10^(1,5·Mw + 16,05)` dina·cm; fuente de Brune con `f0 = 4,906·10⁶·βs·(Δσ/M0)^(1/3)`; dispersión geométrica por tramos; `Q(f) = Q0·f^η`; κ0; duración `1/f0 + Tcamino(R)` (BT14 cortical, `0,05·R` intraplaca); ventana de Saragoni-Hart (ε 0,2; η 0,05; `tη = 2·Tgm`); ruido gaussiano con semilla (mulberry32 + Box-Muller) normalizado en frecuencia; dos pasadas (roca y suelo con el factor de BSSA14 lineal y no lineal); dos componentes con semillas `s` y `s+1`; salida en m/s². FFT radix-2 propia (determinista). **La síntesis es siempre con Δt = 0,005 s**, en cualquier dispositivo y calidad: misma semilla, mismo acelerograma.
- **Profundidad y régimen (E15):** la profundidad entra por la distancia hipocentral y por el tipo de sismo. Con `regimen: 'auto'`, entre 40 y 70 km hay una **banda de transición** con peso `w(h) = (h − 40)/30`: `ln A(f) = (1 − w)·ln A_cortical(f) + w·ln A_intraplaca(f)`, cada término con sus propios parámetros de `amenaza.json` (Δσ, βs, ρs, Q, κ0, dispersión, duración, `Fimp`), y `Tgm = (1 − w)·Tgm,cortical + w·Tgm,intraplaca`; fuera de la banda, un solo régimen. En la transición, la gráfica de espectros muestra las GMPE de los dos regímenes con su peso. Si la persona fuerza el régimen, `avisos` advierte «intraplaca con h < 40 km» o «cortical con h > 60 km». Texto del panel: «La profundidad cambia la distancia al foco y el tipo de sismo».
- **Calidad baja:** el registro se sintetiza a 0,005 s; el integrador usa Δt = 0,01 s sobre la señal filtrada (FIR pasabajos de fase cero a 20 Hz) y tomada cada 2 muestras (`filtrarYDiezmar`). Intensidades y espectros siempre con el registro de 0,005 s. `Resultados.opciones` guarda `dt_s` y `calidad`, y la tabla de variables muestra «calidad baja: paso de 0,01 s». Las cifras de `docs/14` y de T18 se generan con 0,005 s.
- **Modelo (pseudotridimensional de Wilson y Dovey, 1972):** diafragma rígido por nivel con `ux`, `uy`, `rz` en el centro de masa; pórticos planos con `v` y `θ` por nodo condensados por complemento de Schur en cada iteración (el equilibrio de los grados de libertad sin masa se impone en la misma iteración de Newton; no hay iteración anidada). Compatibilidad: `dx = ux − (yf − yc)·rz`, `dy = uy + (xf − xc)·rz`. Rigidez axial `EA/L` (limitación conocida de TABS: la columna compartida suma su rigidez axial en los dos pórticos; se documenta).
- **Elemento de Giberson** (vigas, columnas y muros; momentos y giros antihorarios positivos; `L_f` longitud flexible, E2): giros de los extremos respecto a la cuerda `θ = f_e·M + θ0(w) + θp`, con `f_e = (L_f/(6EI))·[[2,−1],[−1,2]] + (1/(G·Av·L_f))·[[1,1],[1,1]]` y, para `w` hacia abajo, `θ0 = c·[−1, +1]`, `c = w·L_f³/(24EI) + w·L_f/(2·G·Av)`; cortantes en los extremos `(M_i + M_j)/L_f ± w·L_f/2`; las fuerzas pasan al nudo a través de los brazos rígidos (`M_nudo = M + V·d`). Una rótula positiva dentro del vano (momento máximo por gravedad lejos de los extremos) **no** se captura: se documenta. Resortes de los extremos, con las propiedades esperadas (E16): rígidos mientras `−My_e,neg ≤ M − β ≤ My_e,pos` y con pendiente `H = α·k_e` después (`α` = `endurecimiento` > 0; si viene 0 se usa 10⁻⁴), con `k_e = 6EI_fis/L_f` en vigas y columnas y `k_e = EI_fis/lp` en muros (E1); `β` es el momento de retroceso (`bilineal`: endurecimiento cinemático, `β = H·θp`).
  - **Retorno al estado admisible (2 × 2):** con el momento de prueba elástico se prueban los 4 conjuntos activos (ninguno, i, j, ambos); en cada uno se resuelve el sistema lineal con `M_k − β_k = ±My_k` en las rótulas activas, y se acepta el conjunto con `Δλ_k ≥ 0` en las activas y `|M_k − β_k| ≤ My_k` en las inactivas (es único). Tangente consistente: `K_t = (f_e + diag(c_k))⁻¹`, con `c_k = 1/H_k` si la rótula k está activa y 0 si no.
  - **Clough** (`clough`): mientras el momento conserva el signo de la última excursión, el resorte es rígido (descarga y recarga rígidas hasta la rama de la que salió). Cuando el momento cruza cero, el resorte recarga en línea recta desde `(θp actual, 0)` hacia el pico anterior del sentido opuesto `(θp_pico, M_pico)`, o hacia `(0, ±My)` si en ese sentido no hubo fluencia; al llegar, sigue la envolvente monotónica bilineal (`M = ±(My + H·|θp − θp_origen|)`). No hay endurecimiento cinemático en `clough`. El lazo esperado de T7 está en la tabla del 7.8.
- **Gravedad primero:** análisis estático no lineal con `w_gravedad` y `carga_kN`; el dinámico arranca de ese estado (`u_g`, momentos y axiales).
- **P-Delta lineal por nivel (E14):** para cada entrepiso `k` (entre los niveles `k − 1` y `k`, altura `h_k`) y cada nivel `j ≥ k`, el peso `W_j` aporta `−(W_j/h_k)·(b_xᵀb_x + b_yᵀb_y)`, donde `b_x` y `b_y` dan la deriva del entrepiso `k` medida en el centro de masa `CM_j` con las ecuaciones de compatibilidad (`ux_k − (y_j − yc_k)·rz_k − ux_{k−1} + (y_j − yc_{k−1})·rz_{k−1}`, y la análoga en y), más `−(W_j/h_k)·(Jz_j/m_j)` sobre `(rz_k − rz_{k−1})²`. Es exactamente la rigidez geométrica de 4 columnas articuladas con `W_j/4` cada una en `CM_j ± r_j` en x y en y, `r_j = √(Jz_j/m_j)` (cálculo propio; así se modela en OpenSees, 7.9). El término `K_PΔ` es constante.
- **Amortiguamiento de Rayleigh (E8):** `a0 = 2ξωiωj/(ωi+ωj)`, `a1 = 2ξ/(ωi+ωj)`, ξ = 5 %, con los períodos ancla de E8 calculados con la rigidez inicial. `C = a0·M + a1·Σe K0,e`, donde `K0,e` es la rigidez inicial de la **parte elástica** de cada viga, columna y muro (flexión, cortante y axial); las rótulas nunca amortiguan. En el elemento de Giberson el momento de cada extremo equilibra la parte elástica y su amortiguamiento: `M = K_e·(e + a1·ė)` con `e = θ − θ0 − θp`; con Newmark, `ė_{n+1} = (γ/(βΔt))·(e_{n+1} − e_n) + (1 − γ/β)·ė_n + Δt·(1 − γ/(2β))·ë_n`, de modo que el retorno 2 × 2 se hace con `K̃_e = (1 + a1·γ/(βΔt))·K_e` más un término de historia conocido (sin iterar aparte). Así el amortiguamiento queda ensamblado sobre **todos** los gdl (diafragma, `v` y `θ`) y se condensa junto con la rigidez en cada iteración: `K_ef = K_t + (γ/(βΔt))·C_t + M/(βΔt²)`, con `a0·M` solo en los gdl del diafragma. Es la misma formulación que OpenSees con `rayleigh(a0, 0, a1, 0)` y `zeroLength` sin Rayleigh (7.9). El motor reporta el ξ efectivo de los 12 primeros modos en `listo`.
- **Integración:** Newmark de aceleración promedio (γ = 1/2, β = 1/4: incondicionalmente estable en lo lineal) con Newton-Raphson completo; convergencia `‖R‖∞ ≤ tolerancia·max(‖P‖∞, 1 kN)` y `‖Δu‖∞ ≤ 10⁻⁹ m`; si no converge en `max_iter`, el paso se parte en dos hasta `max_subdiv` veces; si aun así no converge, error `no_converge` con resultados parciales. Paso: `dt_s = 0,005 s` (igual al del registro) y `0,01 s` en calidad baja (con el registro filtrado y diezmado). **Alargamiento del período** de Newmark de aceleración promedio: `T̄/T − 1 = (ωΔt/2)/arctan(ωΔt/2) − 1 ≈ (π²/3)·(Δt/T)²`: 0,09 % en el modo 1 (`T ≈ 0,6 s`, `Δt = 0,01 s`) y ≈ 8,6 % en modos de 0,06 s (≈ 2,2 % con `Δt = 0,005 s`) (cálculo propio): aceptable porque esos modos casi no participan, y por eso las cifras de referencia usan 0,005 s.
- **Qué se evalúa en cada Δt** (dentro del integrador, no sobre la salida de 0,02 s): envolventes (`u_max`, derivas, `a_abs_max`, D/C, esfuerzos, θp), primera fluencia, bits de `rotulas` (con O lógico entre dos salidas: una fluencia breve entre muestras queda registrada), derivas vectoriales y `riesgoEquipos`. Las series de salida (cada `dt_salida_s`) son solo para dibujar. (Muestrear 1 de cada 4 puntos baja el PGA en promedio 2,6 % y hasta 8 %, según la prueba de la revisión con 20 realizaciones.)
- **Entrada sísmica:** `a1 = componente x`, `a2 = componente y`, giradas `angulo_deg` (antihorario desde el este); fuerzas efectivas `−M·ι·üg` en los grados de libertad del centro de masa.
- **Escala «nivel de diseño NSR-10»** (`op.escala = 'nsr10'`): `T1x` y `T1y` son los períodos de mayor masa participativa en x y en y (rigidez inicial). El factor `f` hace que la media del espectro de la **media geométrica** de las dos componentes (ξ = 5 %) en los períodos de `0,8·T1` a `1,2·T1` (de x y de y; rango de A.2.7, por confirmar) iguale la media del espectro de diseño con I = 1,5 en esos mismos períodos. Como el factor de suelo no lineal depende del PGA en roca, la pasada de suelo se repite con `PGAr × f` (`escala_pgar`) y se recalcula `f` hasta que cambie < 1 % (máximo 10 vueltas). El motor devuelve `Resultados.factor_escala` y `Resultados.iteraciones_escala`; la vista los muestra con el aviso de escenario hipotético.
- **Balance de energía (formulación relativa, Uang y Bertero 1990):** `E_entrada = −∫u̇ᵀMιüg dt = E_cinética + E_amortiguada + E_elástica + E_histerética + trabajo_PDelta`, con: `E_amortiguada = ∫u̇ᵀa0·M·u̇ dt + Σe ∫(a1·K_e·ė)ᵀ ė dt`; `E_histerética = Σ rótulas ∫(M) dθp`; `E_elástica = Σe ½(eᵀK_e e − e_gᵀK_e e_g) − F_g,cᵀ(u_c − u_c,g)` (energía de la parte elástica respecto al estado de gravedad, menos el trabajo de las cargas de gravedad sobre los gdl condensados que se mueven); `trabajo_PDelta = ½uᵀK_PΔu` (negativo: energía que la gravedad entrega por P-Delta). Control independiente: `E_deformación = ∫(F_r + F_PΔ)ᵀ du_m` sobre los gdl del diafragma desde el estado de gravedad (`F_r` es la fuerza condensada; ya descuenta la gravedad porque el residuo de los gdl condensados es cero) debe ser igual a `E_elástica + Σe ∫(a1·K_e·ė)ᵀ ė dt + E_histerética + trabajo_PDelta`. Error relativo máximo de las dos igualdades < 1 % (respecto al máximo de `E_entrada`).
- **Deriva vectorial:** en cada paso, en cada vértice del `contorno` de cada nivel, `Δ = √(Δx² + Δy²)/h` con la cinemática del diafragma de los dos niveles del entrepiso (en el piso 4, solo los vértices de su contorno); se guarda el máximo por entrepiso y su envolvente con el vértice donde ocurre.
- **Demanda/capacidad (E16):** `dc_flexion = |M|/Mn_e`, `dc_cortante = |V|/Vn_e`, `dc_rotacion = θp/θp_IO` (grupo IV), `dc` = el máximo; en muros de mampostería, deriva/deriva del estado de daño. La leyenda dice qué cociente y qué nivel muestra, y marca LS y CP.
- **Equipos no anclados** (`riesgoEquipos`, en cada Δt): aceleración absoluta en la posición del equipo `a = üg + (üx − (y − yc)·r̈z, üy + (x − xc)·r̈z)` del diafragma que lo sostiene (piso 1 = suelo, sin amplificación; piso N = nivel N−1; los de cielo usan el nivel de arriba; `CUB` = cubierta; `BT` = suelo, porque el bloque técnico es otra estructura). Bloque rígido en 2D: sea `ψ` la dirección de `a` en los ejes locales del equipo (con `rot_z`) y `b_ψ = min(bx/|cos ψ|, by/|sen ψ|)`. Si `μ < b_ψ/h_cg`, el bloque **desliza primero** y, mientras desliza, la aceleración que recibe queda limitada a `μg < g·b_ψ/h_cg`, así que no se balancea: solo se integra el deslizamiento (empieza si `|a| > μg`, fricción de Coulomb, hasta que se detiene). Si `μ > b_ψ/h_cg`, se **balancea primero**: solo se marca el **inicio** del balanceo (`|a| > g·b_ψ/h_cg`), sin calcular si cae (se dice en la web). Si los dos cocientes difieren menos de 10 %, el régimen es `frontera` y se reportan los dos indicadores (Shenton, 1996). Anclados: fuerza `m·|a|` que debe resistir el anclaje, **sin** los factores de la NSR-10 A.9.

### 7.5 Motor y trabajador (`web/js/sismo/motor.js`, `trabajador.js`) — mensajes

`motor.js` exporta `crearMotor()`, que devuelve `{ iniciar(op), movimiento(params), analizar(params, opciones, alProgreso, senal), serieElemento(id), cancelar() }`: toda la lógica (armar el modelo, gravedad, modos, amortiguamiento, síntesis, espectros, GMPE, escala, análisis, historia interna). `trabajador.js` solo traduce mensajes a esas llamadas, y el respaldo de D (hilo principal) usa **la misma** función: nadie duplica la lógica en `sismo.js`.

Se crea desde `web/js/scenes/torre/sismo.js` así:

```js
const w = new Worker(new URL('../../sismo/trabajador.js', import.meta.url), { type: 'module' });
const url = (r) => new URL(r, import.meta.url).href;   // URLs absolutas: dentro del trabajador la base sería web/js/sismo/
w.postMessage({ tipo: 'iniciar', v: 1, id, url_estructura: url('../../../data/sismo_torre_estructura.json'), url_amenaza: url('../../../data/sismo_amenaza.json'), opciones });
```

| Dirección | Mensaje | Respuesta |
|---|---|---|
| ← | (al evaluar el módulo) | `{ tipo: 'cargado' }` |
| → | `{ tipo: 'iniciar', v: 1, id, url_estructura, url_amenaza, opciones: { histeresis, noEstructurales } }` (URLs absolutas) | `{ tipo: 'listo', id, resumen: resumenModelo, elementos: infoElementos, nodos: [{ id, portico, xyz }], modos: { periodos_s, masa_participativa, formas, T1x, T1y }, amortiguamiento: { a0, a1, periodos_ancla_s, xi_modos } }` |
| → | `{ tipo: 'movimiento', id, params }` | `{ tipo: 'movimiento', id, registro: { dt, n, ax: Float32Array, ay: Float32Array, meta, intensidades, avisos }, espectro: { T, Sa_x, Sa_y }, fourier: { f, A_x, A_y }, gmpe: [{ nombre, peso, T, mediana_g, sigma_ln }], nsr10: { T, con_I, sin_I, umbral_dano } }` |
| → | `{ tipo: 'analizar', id, params, opciones }` | varios `{ tipo: 'progreso', id, fraccion, t_s }` (cada ≥ 250 ms) y al final `{ tipo: 'resultado', id, resultados }`. Usa el registro del último `movimiento` si sus `params` son iguales; si no, lo sintetiza antes |
| → | `{ tipo: 'serie_elemento', id, elemento }` | `{ tipo: 'serie_elemento', id, elemento, t, Mi, Mj, V, N, thp_i, thp_j, dc }` (Float32Array, copias de la historia interna) |
| ← | errores | `{ tipo: 'error', id, codigo: 'datos' \| 'no_converge' \| 'interno', mensaje, detalle }` |

- **Cancelar:** `analizar` corre de forma síncrona dentro del trabajador, así que un mensaje `cancelar` no se procesaría hasta el final. La vista cancela con `worker.terminate()` y crea otro trabajador con un `iniciar` nuevo (≤ 1,2 s en el teléfono). En el respaldo, `analizarPorTramos` revisa la `senal` (`AbortSignal`) entre tramos.
- **Transferencia sin perder la historia:** el trabajador guarda una `historia` interna propia (series `Float32` por elemento de `Mi`, `Mj`, `V`, `N`, `θp_i`, `θp_j` y D/C, cada `dt_salida_s`) que **nunca se transfiere**, y transfiere solo los búferes de `Resultados` (`postMessage(msg, [buffers])`). `serie_elemento` responde con copias de la historia, también después de haber enviado `resultado`.
- **Respaldo:** si `new Worker` lanza, si llega `error` antes de `listo` o si no llega `cargado` en 3 s, la vista hace `terminate()` del trabajador (si existe), importa `motor.js` en el hilo principal y usa `analizarPorTramos` cediendo por tiempo (`presupuesto_ms: 12`, con `requestAnimationFrame` o un `MessageChannel`), no por número de pasos: así no hay más de ≈ 12 ms seguidos sin dibujar. Los 3 s cuentan solo hasta `cargado` (la descarga de ≈ 340 KB de datos y el cálculo de `iniciar` no cuentan). Mismos resultados, bit a bit, en el mismo navegador. Sin `SharedArrayBuffer` (Pages no envía COOP/COEP).
- **Pruebas en `qa_worker.mjs`:** cancelar a la mitad de un análisis deja la vista en «cancelado» en ≤ 300 ms (terminate + aviso); `serie_elemento` funciona después de recibir `resultado`; con `Worker` deshabilitado, el respaldo da los mismos `Resultados`.

**Confirmación de publicación (prueba propia, 23-oct-2026):** con el binario de Caddy de Railpack y el `Caddyfile` del repositorio (raíz cambiada a una carpeta de prueba), un Worker de módulo creado con `new URL('../sismo/trabajador.js', import.meta.url)` cargó, importó `./modelo.js`, leyó un JSON con `fetch(new URL('../../data/…', import.meta.url))` y devolvió un `Float64Array` transferido, **tanto en la raíz como bajo la subruta `/trabajemosjuntos/`** (como en GitHub Pages), en Chromium 153 sin pantalla, sin errores de consola. El guion de esa prueba quedó en el *scratchpad* de la sesión de investigación; A lo reescribe en el repositorio como `scripts/sismo/qa_worker.mjs` sobre `scripts/qa/comun.mjs` (12.1). Caddy sirve `.js` como `text/javascript; charset=utf-8` con `X-Content-Type-Options: nosniff`, que no lo bloquea. GitHub Pages no se pudo probar desde este entorno; se infiere que funciona (mismo origen, sin CSP, tipo MIME JavaScript) y se confirma con la prueba de humo posterior al despliegue (13.6). En la publicación como Artifact de Claude el Worker puede no estar disponible: lo cubre el respaldo. Si algún día se agrega una CSP, hace falta `worker-src 'self' blob:` (Draco y KTX2 ya usan workers `blob:`).

### 7.6 Formato de resultados (`Resultados`)

`nt` = pasos de salida (`dt_salida_s = 0,02 s`), `N` = niveles, `nE` = elementos, `nN` = nodos de pórtico, `nP` = pórticos. Orden de los arreglos: tiempo primero (`[i_t][…]`). **Unidades de D/C:** los arreglos `dc*` por paso van en `Uint8Array` como cociente × 100 (255 = ≥ 2,55); las envolventes `dc_max` van en `Float32Array` como **cociente** (0,12 = 12 %).

| Campo | Tipo | Contenido |
|---|---|---|
| `version`, `id`, `params`, `opciones` (incluye `dt_s` y `calidad`), `duracion_calculo_ms`, `factor_escala`, `iteraciones_escala`, `amortiguamiento` (`a0`, `a1`, `periodos_ancla_s`, `xi_modos`) | | |
| `t` | `Float32Array(nt)` | s |
| `ag` | `Float32Array(nt·2)` | aceleración del suelo x, y (m/s²) |
| `u` | `Float32Array(nt·N·3)` | `ux`, `uy` (m) y `rz` (rad) del centro de masa, relativos al suelo |
| `a_abs` | `Float32Array(nt·N·3)` | aceleraciones absolutas del centro de masa (m/s², rad/s²) |
| `giros` | `Float32Array(nt·nN)` | θ de cada nodo en su plano (rad) |
| `v_nodos` | `Float32Array(nt·nN)` | desplazamiento vertical (m) |
| `dc`, `dc_flexion`, `dc_cortante`, `dc_rotacion` | `Uint8Array(nt·nE)` cada uno | cociente × 100: `\|M\|/Mn_e`, `\|V\|/Vn_e`, `θp/θp_IO`; `dc` = máximo de los tres; en muros de mampostería, deriva/deriva del estado de daño |
| `rotulas` | `Uint8Array(nt·nE)` | bits (O lógico de todos los Δt entre dos salidas): 1 fluencia en i, 2 fluencia en j, 4 θp_i > IO, 8 θp_j > IO, 16 θp_i > LS, 32 θp_j > LS, 64 θp (i o j) > CP, 128 V > Vn_e |
| `thp` | `{ elementos: Int32Array(k), valores: Int16Array(nt·k·2) }` | rotación plástica de los k elementos que fluyen alguna vez, en 10⁻⁵ rad |
| `derivas` | `Float32Array(nt·N·2)` | deriva máxima del entrepiso sobre todos los pórticos, componentes x e y |
| `derivas_vector` | `Float32Array(nt·N)` | máximo de `√(Δx² + Δy²)/h` sobre los vértices del contorno de cada entrepiso |
| `derivas_porticos_env` | `Float32Array(nP·N)` | envolvente por pórtico y entrepiso |
| `cortante_basal` | `Float32Array(nt·3)` | Vx, Vy (kN) y momento torsor (kN·m) |
| `energia` | `Float32Array(nt·6)` | entrada, cinética, elástica, amortiguada, histerética y trabajo_PDelta (kJ) |
| `envolventes` | objeto de `Float32Array` | `u_max (N·3)`, `deriva_max (N·2)`, `t_deriva_max (N·2)`, `deriva_vector_max (N)`, `punto_deriva_vector (N·2: x, y)`, `t_deriva_vector_max (N)`, `a_abs_max (N·3)`, `dc_max (nE, cociente)`, `t_dc_max (nE)`, `gobierna (nE: 0 flexión, 1 cortante, 2 rotación)`, `Mi_max (nE)`, `Mj_max (nE)`, `V_max (nE)`, `N_min (nE)`, `N_max (nE)`, `thp_max (nE·2)`, `t_primera_fluencia (nE·2; −1 si no fluye)` |
| `muros_mamposteria` | arreglo | `{ id, aislado, deriva_max, estado: 'sin_dano'\|'leve'\|'moderado'\|'extenso'\|'colapso' }` |
| `equipos` | arreglo | `{ unidad, anclaje, regimen: 'desliza'\|'balancea'\|'frontera'\|'anclado', a_max_m_s2, desliza: bool, deslizamiento_max_m, deslizamiento_final_m, inicia_balanceo: bool, razon_vuelco, fuerza_anclaje_kN }` |
| `calidad_numerica` | objeto | `{ pasos, iteraciones_promedio, subdivisiones, no_convergidos, error_energia_max, error_deformacion_max, indice_estabilidad_max }` |

Tamaño típico (cálculo propio): 40 s, `nt = 2.000`, `nE ≈ 420`, `nN ≈ 300`, `N = 4`: los 4 arreglos de D/C más `rotulas` suman 5 × 840.000 B = 4,2 MB; `giros` y `v_nodos`, 2 × 2,4 MB = 4,8 MB; el resto, ≈ 0,4 MB; y `thp`, 8 KB por elemento que fluye (hasta ≈ 3,4 MB si fluyen todos). Total ≈ **9,4 MB a 12,8 MB**. La `historia` interna del trabajador (≈ 23 MB en Float32 para Mi, Mj, V, N, θp i y j y D/C) se suma al pico de memoria del 7.7. `scripts/sismo/validar_resultado.mjs` comprueba tamaños, tipos, unidades y rangos de cualquier `Resultados` o del ejemplo del Anexo A.4, y que `estructura_min.json` y la estructura de la torre cumplan `theta_y = My·L_f/(6·EI_fis)` (o `My·lp/EI_fis` en muros) ± 1 %.

### 7.7 Tiempos objetivo

| Tarea | Escritorio | Teléfono (proxy: Chromium con CPU ×4 más lenta por CDP) |
|---|---|---|
| `iniciar` (armar modelo, gravedad, 12 modos, amortiguamiento) | ≤ 300 ms | ≤ 1,2 s |
| `movimiento` (2 componentes a 0,005 s, espectros de 60 períodos, GMPE) | ≤ 400 ms | ≤ 1,5 s |
| `analizar` de 40 s (`dt` 0,005 escritorio / 0,01 en calidad baja) | ≤ 2,5 s | ≤ 8 s |
| Memoria pico del trabajador (resultados + historia interna) | ≤ 80 MB | ≤ 80 MB |

### 7.8 Pruebas: `node scripts/sismo/test_motor.mjs`

Sin dependencias. Cada prueba imprime su error y su tolerancia; el proceso sale con código 1 si una falla.

| # | Prueba | Referencia | Tolerancia |
|---|---|---|---|
| T1 | Oscilador libre sin amortiguar, 50 ciclos, con Δt = T/20 y T/50 | `u = u0·cos ωt`; Newmark promedio no disipa: amplitud y energía constantes; período discreto exacto `T̄/T = (ωΔt/2)/arctan(ωΔt/2)` | Energía: 10⁻⁹ relativo. Período medido entre el primer y el último cruce por cero (interpolación lineal) contra la fórmula exacta: error < 10⁻⁴ sobre `T̄/T` |
| T2 | Oscilador libre amortiguado (ξ = 5 %) | `u = e^{−ξωt}[u0 cos ωd t + (v0 + ξωu0)/ωd · sen ωd t]` | Error máximo < 10⁻³·u0 con Δt = T/200 |
| T3 | Forzado armónico `p0 sen Ωt`, ξ = 5 %, Δt = T/100, 60 ciclos | Factor dinámico `1/√((1−r²)² + (2ξr)²)`; amplitud de los últimos 10 ciclos (el transitorio ya se apagó) | 0,5 % en la amplitud estacionaria (r = 0,5; 1; 2) |
| T4 | Escalón en la base sin amortiguar, Δt = T/100, 20 ciclos | `u = −(ag/ω²)(1 − cos ωt)` | 0,5 % |
| T5 | Convergencia con Δt sobre el caso de T2 | Error global ∝ Δt² con Δt = T/20, T/40 y T/80 (lineal: con fluencia se pierde el orden 2) | Cociente de errores al partir Δt entre 3,6 y 4,4 |
| T6 | Balance de energía | Elástico y elastoplástico (fy = 0,5 de la fuerza elástica máxima), **con y sin P-Delta** (`P/h` = 2 % de `k`) | Las dos igualdades del 7.4: < 0,5 % lineal; < 1 % no lineal |
| T7 | Ciclo cuasiestático de una rótula en serie con su parte elástica | Tabla de abajo (bilineal cinemático y Clough) | 10⁻⁶ |
| T8 | Pórtico de cortante de 4 pisos uniforme | `ω_r = 2√(k/m)·sen((2r−1)π/(2(2n+1)))`, con `EI_viga = 10⁵·EI_col`, `EA = 10⁶·12EI/h²`, `Av → ∞` y `k = Σ 12EI/h³` | Períodos < 0,1 % |
| T9 | Pórtico de un vano y un piso | Pendiente-deflexión: `k = (24EIc/h³)·(6β+1)/(6β+4)`, `β = (EIb/L)/(EIc/h)` (derivada en el propio test; con L = 2h coincide con el ejemplo del pórtico de Chopra, *Dynamics of Structures*, cap. 1), con `Av → ∞` | < 0,1 % |
| T10 | Un piso con rigidez excéntrica | Frecuencias del sistema acoplado `ux–rz` (determinante 2 × 2) | < 0,1 % |
| T11 | P-Delta | (a) Oscilador: rigidez efectiva `k − P/h`. (b) Dos niveles con los centros de masa desalineados (el de arriba 6 m al norte): `K_PΔ` del motor contra la de 4 columnas articuladas por nivel ensamblada a mano en el test | (a) Período < 0,1 %. (b) Términos de `K_PΔ` 10⁻⁹ relativo; períodos < 0,1 % |
| T12 | Equilibrio, con y sin P-Delta | `Σ m·a_abs = −(V_elem + V_a0 + V_PΔ,1)`, con `V_elem` los cortantes de los elementos en la base (incluido su amortiguamiento), `V_a0 = Σ a0·m·u̇` y `V_PΔ,1 = Σ_{j≥1} (W_j/h_1)·δ_1(CM_j)`; lo mismo para el momento torsor | 10⁻⁶ relativo |
| T13 | GMPE | Valores `prueba` de cada bloque de `amenaza.json → gmpe` | < 0,5 % |
| T14 | Espectro NSR-10 | `Sa(0,5) = 0,844 g`, `Sa(1,0) = 0,594 g` con I = 1,5 | 3 decimales |
| T15 | Síntesis estocástica (prueba de conjunto) | Media geométrica de 24 simulaciones de `nido_2015` en Vs30 270: PGA ≈ 0,028 g, Sa(0,2) ≈ 0,065, Sa(0,5) ≈ 0,061, Sa(1,0) ≈ 0,035 g, PGV ≈ 2,5 cm/s, D5-95 ≈ 9,4 s; `cimitarra`: PGA ≈ 0,17 g; `f0` de Mw 6,2 = 0,727 Hz | ±25 % (la semilla); `f0` ±0,5 % |
| T15b | Espectro objetivo (determinista) | `espectroObjetivo` en roca y en suelo para f = 0,1, 0,5, 1, 5 y 20 Hz, con `nido_2015` y `cimitarra` (PGAr fijo, para probar el término no lineal del suelo de BSSA14), contra `scripts/sismo/estocastico.py` | 0,1 % |
| T15c | Normalización del ruido | En 200 realizaciones, la media de `\|Δt·FFT(a)\|²/A(f)²`, promediada por bandas de un tercio de octava entre 0,2 y 20 Hz | Entre 0,9 y 1,1 en cada banda |
| T16 | Espectro de respuesta | 60 períodos logarítmicos entre 0,02 y 5 s; `espectroRespuesta` (Nigam y Jennings) contra el método por FFT con relleno de ceros suficiente (≥ 8 veces la duración) | 1 % para T ≥ 0,1 s; 3 % para 0,02 ≤ T < 0,1 s |
| T17 | Determinismo | Misma semilla y opciones → resultados idénticos | Bit a bit |
| T18 | Estructura real | Carga `torre_hospital_estructura.json`, corre `nido_2015` y `local_hip` con Δt = 0,005 s, con y sin P-Delta: 0 pasos sin converger, errores de energía < 1 %, `validar_resultado` pasa; reporta el índice de estabilidad máximo (del orden de 1 %, estimación) | — |
| T19 | Continuidad con la profundidad (E15) | Para Mw 5, 6,2 y 7 y Repi 0, 92 y 200 km, la mediana del PGA de 24 simulaciones con profundidad h + 1 km dividida por la de h | Entre 0,85 y 1,18 para todo h de 5 a 199 km |
| T20 | Calidad baja | Misma semilla: PGA de la señal filtrada y diezmada frente a la original, y deriva máxima con Δt = 0,01 s frente a 0,005 s (`nido_2015`, `cimitarra`) | < 3 % y < 5 % |
| T21 | Equipos no anclados | (a) `b/h = 0,5`, `μ = 0,3`, `\|a\| = 0,6 g`: solo desliza (`regimen: 'desliza'`, `inicia_balanceo: false`). (b) `μ = 0,6`, `b/h = 0,3`, `\|a\| = 0,4 g`: solo balancea. (c) cocientes a menos de 10 %: `frontera`. (d) Bloque en 2D con `a` a 45° de sus ejes: `b_ψ` según 7.4 | Exacto (régimen); deslizamiento contra la solución cerrada de Coulomb con pulso rectangular: 10⁻⁶ |
| T22 | Deriva vectorial | Un piso cuadrado de 10 m con solo `rz`: deriva de las esquinas = `rz·√(5² + 5²)/h`, y el vértice reportado es una esquina | 10⁻⁹ |

**Tabla de T7** (cálculo propio con las reglas del 7.4): resorte con `My = 100 kN·m` en serie con su parte elástica `k_e = 10⁴ kN·m/rad`, `α = 0,03` (`H = 300 kN·m/rad`; rigidez del conjunto después de la fluencia `k_e·H/(k_e + H) = 291,262 kN·m/rad`), giro total impuesto 0 → +0,030 → −0,030 → +0,030 rad.

| Punto | Bilineal: θ (rad) | M (kN·m) | θp (rad) | Clough: θ (rad) | M (kN·m) | θp (rad) |
|---|---|---|---|---|---|---|
| Primera fluencia | 0,010000 | 100,000 | 0 | 0,010000 | 100,000 | 0 |
| Pico + | 0,030000 | 105,825 | 0,019417 | 0,030000 | 105,825 | 0,019417 |
| M = 0 al descargar | 0,019417 | 0 | 0,019417 | 0,019417 | 0 | 0,019417 |
| Fluencia inversa / llegada al objetivo | 0,010000 | −94,175 | 0,019417 | −0,010000 | −100,000 | 0 |
| Pico − | −0,030000 | −105,825 | −0,019417 | −0,030000 | −105,825 | −0,019417 |
| M = 0 al descargar | −0,019417 | 0 | −0,019417 | −0,019417 | 0 | −0,019417 |
| Fluencia o llegada al objetivo | −0,010000 | 94,175 | −0,019417 | 0,030000 | 105,825 | 0,019417 |

(Clough: la recarga negativa va de (θp = 0,019417; 0) a (0; −100) con rigidez del conjunto 3.399,4 kN·m/rad; la positiva, de (−0,019417; 0) al pico (0,019417; 105,825) con 2.141,5 kN·m/rad. T7 compara además 200 puntos intermedios del lazo.)

### 7.9 Validación con OpenSees: `python3 scripts/sismo/validar_opensees.py`

- Requisitos: `scripts/sismo/requisitos_validacion.txt` con `openseespy==3.8.0.0` y `numpy`. Probado en este entorno: `openseespy` 3.8.0.0 se instala desde PyPI y resuelve un oscilador (T = 0,628319 s exacto). No corre en CI (las Pages solo instalan Python); el resultado se versiona en `data/sismo/validacion_opensees.json`.
- `node scripts/sismo/exportar_caso.mjs <escenario> <salida.json>` escribe el registro (mismo `dt`, ya filtrado si es calidad baja), `a0`, `a1` y el modelo condensado de referencia para que el script de Python no reimplemente la síntesis.
- **Réplica de la idealización** (modelo 3D, `ndm 3, ndf 6`):
  - Cada pórtico tiene **sus propios nodos** (como en TABS). Los nodos de un nivel son esclavos de `rigidDiaphragm 3` con el maestro en el centro de masa, con `mass(maestro, m, m, 0, 0, 0, Jz)` y `fix(maestro, 0, 0, 1, 1, 1, 0)`.
  - **En los esclavos no se restringe ningún gdl que controle el diafragma** (`ux`, `uy`, `rz`): con el manejador `Transformation`, fijarlos los deja en cero y además anula el `uz` del esclavo, con lo que desaparece la deformación axial de las columnas (prueba de la revisión, 1 piso y 3 pórticos: −0,5 % en `ux`, −1,4 % con viga rígida). Solo se fija el giro fuera del plano: `rx` en los nodos de los pórticos X y `ry` en los de los pórticos Y. Inercia fuera del plano y torsión de los elementos despreciables (`Iy = J = 10⁻⁶·I`). Bases empotradas en los 6 gdl.
  - Elementos: `ElasticTimoshenkoBeam` (o `elasticBeamColumn` con `Av → ∞` en la corrida de comparación sin cortante) con `I·factor_fisuracion` y `geomTransf Linear` en vigas, columnas y muros. Brazos rígidos como elementos elásticos 10³ veces más rígidos entre el nudo y la cara (no `rigidLink`, que chocaría con `rigidDiaphragm`).
  - Rótulas: `zeroLength` rotacional en la cara, entre el nodo de la cara y el nodo interno del elemento elástico (`equalDOF` para los otros 5 gdl), con `Steel01(My_e, k0 = 10³·k_e, b = α/10³)`, donde `k_e` es la misma del motor (`6EI_fis/L_f`; en muros `EI_fis/lp`): en `Steel01`, `b` es la razón entre la pendiente después de la fluencia y `k0` del propio resorte, y con `b = α` la pendiente quedaría 1.000 veces la del motor (prueba de la revisión: θp máximo de 0,00015 rad contra 0,0019 rad). Fluencia asimétrica con dos `Steel01` en paralelo o `Hysteretic`, documentado. Los `zeroLength` van **sin** `-doRayleigh` (por defecto no llevan amortiguamiento), y así se dice en el informe.
  - `rayleigh(a0, 0, a1, 0)` con los mismos `a0` y `a1` del motor (E8).
  - **P-Delta** con columnas de gravedad, no con `geomTransf PDelta` en las columnas de pórtico (cada copia de TABS llevaría solo la gravedad de las vigas de su pórtico, y su `N` cambia en el tiempo): por cada nivel `j`, 4 pilas de columnas articuladas (`geomTransf PDelta`, rigidez axial alta y flexión despreciable) en `CM_j ± r_j` en x y en y, `r_j = √(Jz_j/m_j)`, desde el nivel `j` hasta la base, con `W_j/4` cada una y sus nodos de cada nivel esclavos del diafragma (`W_j` constante).
  - Gravedad con `loadConst -time 0.0` antes del dinámico; `integrator Newmark 0.5 0.25`; `constraints Transformation`.
- **Casos de control** (antes de la torre): (1) 1 piso y 3 pórticos contra la condensación pseudotridimensional exacta: desplazamientos con error < 10⁻⁵; (2) ciclo cuasiestático de un elemento con rótula contra la tabla de T7: < 0,5 %.
- **Criterios** en la torre: períodos de los 6 primeros modos < 1 %; corrida elástica (`nido_2015`): deriva vectorial máxima por piso y cortante basal pico < 3 %; corrida no lineal (`local_hip` con escala que produzca fluencia, declarada): desplazamiento máximo de cubierta y deriva máxima < 10 %, mismo conjunto de elementos que fluyen (índice de Jaccard ≥ 0,8), primera fluencia ±0,1 s, energía amortiguada < 5 %.

---

## 8. Contrato 6 · VISTA SÍSMICA (equipo D)

### 8.1 Principio

Todo lo que se mueve en pantalla es **resultado del cálculo** en ese paso de tiempo. No hay animación decorativa: el deslizador de tiempo recorre los pasos calculados (`Resultados.t`); «Reproducir» solo avanza el índice con el reloj real (no con el `dt` acotado a 0,05 s de `core.js:203`). Con `prefers-reduced-motion` no hay reproducción automática.

### 8.2 Controles (`torre.panel.sismo`)

| Control | Rango | Texto visible |
|---|---|---|
| Escenario | Los 8 de `amenaza.json → escenarios` + «Personalizado» | Nombre, Mw, profundidad, distancia y aviso «por confirmar» del contexto |
| Magnitud **Mw** | 4,0-8,0 (paso 0,1; 6,2 por defecto) | «Magnitud de momento Mw (la que reemplazó a la escala de Richter: la de Richter se satura por encima de 6,5 a 7)». Muestra M0 en N·m y la energía aproximada; botón «¿Por qué no Richter?» con la explicación de `amenaza.json → magnitud.explicacion_ciudadana` |
| Profundidad | 5-200 km (150 por defecto) | «La profundidad cambia la distancia al foco y el tipo de sismo». Muestra el tipo resultante: cortical hasta 40 km, transición de 40 a 70 km (con el peso de cada tipo) e intraplaca desde 70 km (E15) |
| Tipo de sismo | automático (por defecto) / cortical / intraplaca | Si se fuerza un tipo incompatible con la profundidad, aviso (7.4) |
| Distancia epicentral | 0-300 km (92 por defecto) | Distancia hipocentral calculada |
| Suelo Vs30 | 150-760 m/s (270) | «Suelo D supuesto mientras no haya estudio geotécnico» |
| Semilla | entero (2028) | «Misma semilla, mismo sismo, en cualquier dispositivo» (la síntesis es siempre a 0,005 s) |
| Dirección | 0-180° | Ángulo de la componente 1, antihorario desde el este |
| Escala del registro | ×1 (físico) o «nivel de diseño NSR-10» | En el segundo caso: «escenario hipotético: el registro se multiplica para que su espectro, entre 0,8 y 1,2 veces el período fundamental en cada dirección, iguale en promedio el espectro de diseño de Yondó con I = 1,5; no cambia la física de la fuente». Se muestran el factor final y cuántas vueltas dio el ajuste del suelo (7.4) |
| Muros no estructurales | aislados / sin aislar | |
| Exageración de la deformada | ×1 a ×200 (automática por defecto: el desplazamiento máximo de cubierta se dibuja como ≈ 1,5 m, redondeado a 1-2-5) | «×50: 2,1 cm reales se dibujan como 1,05 m». ×1 siempre disponible |
| Colorear por | Máximo / Flexión / Cortante / Rotación plástica | La leyenda dice el cociente (`\|M\|/Mn esperado`, `\|V\|/Vn esperado`, `θp/θp de ocupación inmediata`) |
| Calcular / Cancelar | botones | Estado y barra de progreso con `aria-live`; avisos de combinación debajo; «calidad baja: paso de 0,01 s» cuando aplica |
| Tiempo | deslizador de pasos, Reproducir/Pausa, velocidad 0,25×/1× | Tiempo en s y PGA instantánea |

Los valores salen de `amenaza.json → controles`; los avisos, de `controles.avisos_de_combinacion` y de `avisos()` (7.4).

### 8.3 Qué se dibuja en 3D (`web/js/scenes/torre/estructura3d.js`)

```js
export function crearEstructura3D(info /* de 'listo': elementos, nodos, niveles */, { tier, colores /* tokens */, renderer })
  /* → { grupo, actualizar(i, R, escala, campo), seleccionar(id | null), pick(raycaster) → id | null, posicionCubierta(i) → [x, y, z], dispose() } */;
```

- **Columnas, vigas y muros** como líneas gruesas (`LineSegments2`/`Line2`, ya en el importmap de r160) con 8 tramos por elemento y color por vértice: posición por interpolación de Hermite con los desplazamientos laterales del diafragma (`dx`, `dy` del 7.4), los giros de los nodos y la rotación plástica de los extremos que fluyen (quiebre visible). Una sola columna física por eje (`fisico`): en x usa el pórtico X, en y el pórtico Y. Su demanda combinada para el color es `((dc_x)^1,5 + (dc_y)^1,5)^(1/1,5)` (contorno de carga de Bresler con α = 1,5; aproximación para mostrar, estimación).
- **Actualización sin reservar memoria:** la geometría de las líneas se crea **una vez**; en cada paso se escribe sobre `geometry.attributes.instanceStart.data.array` con `.set(...)` y se marca `data.needsUpdate = true` (lo mismo con `instanceColorStart`). No se llama `setPositions()` en la reproducción (en three 0.160 crea un `InstancedInterleavedBuffer` nuevo y recalcula las cajas en cada llamada, `lines/LineSegmentsGeometry.js:66-80`). `frustumCulled = false` (o una esfera envolvente fija calculada con la exageración máxima). `material.resolution` se actualiza desde `renderer.getSize()` en la función de `onFrame` cuando cambia el tamaño.
- **Losas** de cada nivel como placas translúcidas que se mueven como cuerpo rígido con `ux`, `uy`, `rz` (el diafragma rígido es la hipótesis del modelo).
- **Rótulas** como esferas instanciadas en los extremos con bit de fluencia; tamaño ∝ θp/θp_IO; anillo de color según el nivel superado (ocupación inmediata, seguridad de la vida, prevención del colapso).
- **Muros de mampostería** (si se eligen sin aislar o para mostrar su daño) como paneles con el color de su estado de daño.
- **Fantasma** de la estructura sin deformar en gris fino.
- **Dotación no anclada** (opcional, si el inventario está cargado): equipos del piso elegido desplazados lo que calculó `riesgoEquipos` (a escala real, con flecha) y coloreados «estable / desliza / empieza a balancearse / frontera». D arma los `EquipoRiesgo` (7.4) con las filas de `torre_inventario.json` (columnas `piso`, `x`, `y`, `z`, `rot_z`) y el catálogo web (`masa`, `hcg`, `mu`, `anc`, `dim`).
- **Leyenda** de colores con `--good` (≤ 0,5), un tono intermedio (0,5-0,8), `--warn` (0,8-1,0) y `--bad` (> 1,0) leídos con `tokens()` y recoloreados con `onTheme`. Con «Flexión», «Cortante» o «Rotación» la leyenda dice qué cociente y qué nivel de desempeño es.
- El GLB `obra_nueva` se oculta (entrepisos de 4,30 m que no coinciden); el hospital actual queda como contexto estático.
- Presupuesto: ≤ 60 llamadas de dibujo y ≤ 150.000 triángulos; `dynamicShadows = false` y `st.updateShadows()` al pausar.

### 8.4 Gráficas (`web/js/scenes/torre/graficas.js`, SVG con la clase `svg.mr-chart`)

```js
export function acelerograma(el, { t, ax, ay }) /* → Grafica */;
export function espectros(el, { T, sa_x, sa_y, nsr10: { con_I, sin_I, umbral_dano }, gmpe: [{ nombre, peso, mediana, sigma }], marcas: [{ T, etiqueta }] }) /* → Grafica */;
export function derivas(el, { pisos, x, y, vector, limite: 0.01, umbral: 0.004, umbral_mamposteria: 0.002 }) /* → Grafica */;
export function serieTiempo(el, { t, series: [{ nombre, y, unidad }] }) /* → Grafica */;
export function energia(el, { t, entrada, cinetica, elastica, amortiguada, histeretica, pdelta }) /* → Grafica */;
export function histeresis(el, { theta, M, My, limites: { IO, LS, CP } }) /* → Grafica */;
// Grafica: { cursor(i: number): void, dispose(): void }
```

En `torre.sismo` (tarjeta debajo del tablero): acelerograma de las dos componentes con cursor; **espectro de respuesta** del sismo contra el espectro de diseño NSR-10 de Yondó (con y sin I = 1,5, y el de umbral de daño con Ad = 0,04), la mediana ±1σ de las GMPE del régimen (las de los dos regímenes, con su peso, en la transición) y marcas en T1, T2, T3; espectro de Fourier contra el objetivo de Boore; **derivas por piso**: la deriva vectorial `√(Δx² + Δy²)` en los vértices (la que se compara) y, como referencia, las componentes x e y, contra 1 % y 0,4 % (0,2 % con mampostería adherida), con la explicación: «1 % es el límite para el sismo de diseño; 0,4 % para el sismo pequeño y frecuente del umbral de daño; la deriva se mide en las esquinas, donde la torsión la hace mayor»; **cortante basal** en el tiempo con el cortante de diseño `Vs` y `Vs/R`; **balance de energía** apilado (con el trabajo de P-Delta) y su error; tabla de variables (Mw, M0, f0, Δσ, Rhip, tipo de sismo y peso de la transición, Q(f), κ0, Tgm, PGA, PGV, Arias, D5-95, T1-T3 con masas modales, períodos ancla y ξ efectivo de los modos, factor de escala si aplica, paso de cálculo, deriva vectorial máxima y dónde, índice de estabilidad, elemento con mayor D/C y su criterio, número de rótulas por nivel de desempeño, muros por estado de daño, equipos que deslizan o empiezan a balancearse). Al tocar un elemento: serie de `Mi`, `Mj`, `V`, `N` y lazo `M–θp` de sus rótulas con las marcas IO, LS y CP (`serie_elemento`). Tablas con `table.fichas` y `data-th` en el teléfono.

### 8.5 Textos de honestidad (obligatorios en la vista y en `docs/14`)

«Modelo de prediseño (sin estudio de suelos ni diseño estructural firmado). Idealización estándar de ingeniería: diafragmas rígidos, pórticos planos, rótulas concentradas, núcleos como muros planos con aletas efectivas (su resistencia no cambia con la carga axial del sismo), sin interacción suelo-estructura, sin componente vertical, sin degradación de resistencia. Amortiguamiento del 5 % proporcional a la masa y a la rigidez inicial de la parte elástica de los elementos (las rótulas no amortiguan). Los colores comparan con la resistencia esperada y con el límite de ocupación inmediata de un hospital. El contexto sísmico (nido de Bucaramanga, fallas cercanas) está por confirmar con el Servicio Geológico Colombiano. Validado contra soluciones exactas y contra OpenSees (ver documento 14).»

### 8.6 Integración en `torre.js`

- Botón `data-modo-torre="sismo"`. Al elegirlo, D hace lo mismo que en el 6.8 (paso 1: detener vuelos y encuadres pendientes, vaciar `st.pickables`) y luego `const mod = await import('./torre/sismo.js'); sim ??= await mod.montar(ctx); sim.entrar()`. El propio modo llama `ctx.exterior.ocultar(true)` en modo parcial (oculta `obra_nueva`, deja el hospital y el terreno).
- `sismo.js` exporta `montar(ctx)` con la misma forma de `ctx` que el recorrido (6.2), con `hud = torre.hud.sismo`, `panel = torre.panel.sismo`, `ficha = torre.ficha.modo`, más `graficas: HTMLElement` y `motor: () => Promise<Motor>` (crea el trabajador o, si falla, el respaldo de `motor.js`, 7.5), y devuelve `{ entrar(), salir({ porUsuario }), alReanudar(), dispose() }`. Registra una sola función de `onFrame` en `montar` y la quita en `dispose` (6.8).
- La primera vez que se entra al modo se corre el escenario por defecto (`nido_2015`) para que la vista nunca esté vacía.
- En la ola 1, D trabaja con `scripts/fixtures/torre/trabajador_simulado.js` (A), que responde los mensajes del 7.5 con los fixtures del Anexo A.

### 8.7 Ganchos de QA

Con `index.html?qa=1#torre` (la marca va en la consulta, no en el *hash*: `main.js:85` toma la vista de `location.hash`, y `#torre?qa=1` cargaría «dinero»), `torre.js` lee `new URLSearchParams(location.search).has('qa')` y publica:

```js
window.__torreQA = {
  modo(m), stats() /* → { llamadas, triangulos } */,
  recorrido: { irA, estado /* → { piso, recinto, posicion, rumbo_deg, en_muro } */, libre(x, y) /* → boolean */ },
  sismo: { calcular(params) /* → Promise<resumen> */, ultimo(), motor() /* → 'trabajador' | 'hilo_principal' */, cubiertaDibujada(i) /* → [x, y, z] */ }
};
```

Sin `?qa` no existe.

### 8.8 «Pisos por servicio» con la planta real

Cuando exista `torre_plantas.json`, `armarPisos` (`torre.js:120-148`) usa `planta3d.construirPiso(nivel, { colorPor: 'grupo', grupos: plantas.grupos_1633, cielo: false })` en lugar de las franjas proporcionales (que hoy ponen el vestíbulo al norte cuando el programa lo pone al sur). Consecuencias que D resuelve:

- El arreglo `zonas` de las franjas deja de existir; de él dependen `armarLaboratorio` (`torre.js:155-157` sale sin dibujar si no hay zona), las etiquetas por servicio (`torre.js:111`) y la transparencia del modo «Laboratorio» (`torre.js:96`). **«Laboratorio» conserva su maqueta actual sobre las franjas** (que se siguen calculando solo para ese modo) en esta iteración; apoyarlo en los recintos reales del laboratorio queda para después.
- Las etiquetas por servicio salen de `construirPiso(...).etiquetas()` (recintos) y la leyenda de los 8 grupos de `grupos_1633`, no de los 7 grupos de `GRUPOS` (`torre.js:13-21`).
- Los pisos nuevos se registran como seleccionables quitando antes los anteriores de `st.pickables`.
- Meta: ≤ 60 llamadas de dibujo en ese modo (hoy 204, medición propia). Si la planta no está, se conserva el comportamiento actual.

---

## 9. Contrato 7 · CONTRASTE CON EL PROYECTO TIPO (equipo E)

### 9.1 `data/proyectos/torre_hospital/proyecto_tipo_contraste.json`

Copia de `investigacion/proyecto_tipo_contraste.json` (10 referentes, 40 filas por ambiente, 39 temas por capítulo, costo por m², dotación de 12 ambientes, escalamiento, 7 inconsistencias, capa de colores, conclusiones, fuentes) con estos agregados y correcciones:

- **Ambientes del programa.** En cada fila de `contraste_ambientes` y `dotacion_por_ambiente`: `ambientes_programa: [{ "fila": n } | { "servicio_programa": …, "nombre": … }]` (regla del 3.4; hoy `ambiente_torre` es texto libre, por ejemplo «Consultorio de medicina general (8), 3,60 × 3,60 m, piso 2»). Las filas sin recinto (la PTAR y la plaza de acceso, que no están en `programa.json`; la bahía de ambulancias, fila «exterior» que el 3.3 excluye de las plantas; la vivienda médica, que no existe en la torre) llevan `ambientes_programa: []` y `sin_recinto: "no está en el programa" | "exterior sin planta"`.
- **Dos veredictos.** De las 40 filas, 22 (urgencias, hospitalización, partos, laboratorio, imágenes, esterilización, vacunación, terapias, telemedicina, bahía y expansión) dicen «Sin ambiente equivalente en los proyectos tipo»: su veredicto es frente al mínimo de la Res. 1633, no frente al tipo (dato de la investigación, conteo propio). El campo se parte en `veredicto_tipo` (solo en las 18 filas con ambiente del tipo: 9 «mejora», 4 «cumple igual», 4 «se aparta», 1 «falta», y esa «falta» es un consultorio que el tipo no tiene) y `veredicto_norma` (frente a la Res. 1633: el de la investigación en las 22 filas sin ambiente del tipo y, en las 18 con tipo, el que E calcule comparando `m2_torre` con `m2_min_1633`, como cálculo propio). `validar_contraste.py` falla si una fila «Sin ambiente equivalente» tiene `veredicto_tipo`.
- **`resumen_para_la_web`**, 5 a 8 cifras, **cada una con su tipo y su base de área**:
  - Tamaño: la torre equivale a 10,5 veces el puesto del DNP (base 320,6 m² del texto del tipo y 3.369,6 m² de la torre) y a ≈ 56 de sus módulos de 59,65 m²; solo 30 % de su área útil tiene equivalente en el tipo.
  - Costo de obra civil: se publica como **rango**: «entre 0,8 % más (si el tipo se divide por los 269,6 m² de su presupuesto: $5.417.624 por m²) y 19,9 % más (si se divide por los 320,6 m² construidos: $4.555.806 por m²)» frente a $5.462.687 por m² de la torre (P2 con AIU sobre 3.620,6 m²). Obra completa: «1,34 a 1,59 veces» con las mismas dos bases (cálculos propios de la investigación, que da las dos razones: 1,008 y 1,199).
  - Dotación: 21,7 veces la del tipo ($4.294 M frente a $198,1 M) y 2,1 veces por m² (base 320,6 m² del tipo y 3.369,6 m² de la torre).
  - Ambientes: «frente al proyecto tipo (18 ambientes con equivalente): 9 mejoran, 4 igual, 4 se apartan, 1 falta» y, aparte, «frente al mínimo de la Res. 1633: …» con el conteo de `veredicto_norma`. Nunca «18 mejora, 15 cumple igual, 4 se aparta, 3 falta» como contraste con el tipo.
  - Todas son cálculos propios de la investigación del 23-oct-2026, salvo los conteos que E rehace.
- **Precios de la dotación por ambiente:** `dotacion_por_ambiente[].costo_torre_cop_2026` se reemplaza por `lineas_torre: [{ "linea": id, "nombre": … }]`; `build_data.py` calcula el valor al exportar desde `dotacion.json` (10.1).
- **`programa.json → proyectos_tipo[1].costo_de_referencia`:** E pone el valor por m² sobre 320,6 m² ($4.555.806, cálculo de la investigación; hoy el repositorio trae $4.555.830) con la nota «sobre 320,6 m² construidos; `docs/11` §6.2 usa $5,42 M por m² sobre los 270 m² del presupuesto del tipo». `verificar_cifras_docs.py` comprueba que las dos cifras aparezcan juntas.
- `novedades_2025_2026` se conserva: no se confirmó ningún proyecto tipo nuevo; la búsqueda no se pudo repetir el 23-oct-2026.
- **`proyecto_tipo.json → escalamiento_a_torre`** («torre de 3 pisos y ≈ 2.900 m²»): E agrega solo el campo `escalamiento_a_torre.estado` = «escenario inicial superado por programa.json (4 pisos, 3.369,6 m²)» (2.1); `build_data.py` lo exporta tal cual.

`python3 scripts/torre/validar_contraste.py`: cada `ambientes_programa` existe y corresponde a una sola fila (o la fila lleva `sin_recinto`); `veredicto_tipo` solo en filas con ambiente del tipo y `veredicto_norma` en todas las que tengan mínimo de la Res. 1633, ambos ∈ {mejora, cumple igual, se aparta, falta}; cada cifra con `tipo_dato` y base de área; cada fila con fuente; cada `lineas_torre` existe en el inventario.

### 9.2 Vista (`web/js/scenes/torre/contraste.js`)

```js
export function pintarContraste(el, c, { verEn3D, textos } = {}) {}          // tarjeta [data-slot="torre.tipo"]
export function coloresRecintos(c, plantas) /* → Map<idRecinto, { veredicto_tipo, color_hex, texto }> (solo recintos con veredicto_tipo) */;
export function modeloTipo3D(THREE, c) /* → THREE.Group centrado en el origen */;
```

- **Tarjeta «Contraste con el proyecto tipo»:** referente principal y por tema; fichas con las cifras del resumen y su base de área; tabla por ambiente (`table.fichas`; dos columnas de veredicto, «frente al tipo» y «frente a la Res. 1633», como píldoras; m² del tipo, de la torre y mínimo de la Res. 1633 con cita; botón «Ver en 3D» que abre el recorrido en ese recinto, oculto en las filas con `sin_recinto`); temas por capítulo plegados; costo por m² en barras con el método y las dos bases a la vista; dotación por ambiente (lo que trae el tipo, lo que trae la torre, faltantes y sobrantes); escalamiento por servicio; inconsistencias detectadas (quiebrasoles de 0,90 m en el modelo frente a 1,40 m presupuestados; muro cortina del piso 4 sin presupuesto; posible duplicado del kit; $4.555.830 frente a $4.555.806).
- **Colores en la web:** las píldoras usan los tokens del tema (`--good` mejora, `--s1` cumple igual, `--warn` se aparta, `--bad` falta) con texto `--ink`, para que el contraste valga en claro y oscuro; los colores fijos sugeridos por la investigación (mejora `#2f6b4f`, cumple igual `#6b8fb3`, se aparta `#c9a227`, falta `#b5562f`) quedan solo para el 3D.
- **Capa en el recorrido** «Comparar con el proyecto tipo»: D llama `coloresRecintos` y pasa a C un `Map<string, THREE.Color>` en `ctx.datos.coloresContraste` (así C no importa el módulo de E). Solo se tiñen los recintos con `veredicto_tipo`; el resto va en gris, con la leyenda «sin equivalente en el proyecto tipo». Una segunda leyenda, «frente a la Res. 1633», usa `veredicto_norma` en la tarjeta (no en el 3D).
- **En 3D a escala** (modo «Con la torre», botón `data-capa-torre="tipo"` con `aria-pressed`, que agrega D): una placa de 320,6 m² de un piso (cuadrada, 17,9 m de lado, porque la planta real del tipo está en el PDF que no se pudo abrir), con la etiqueta «Área equivalente del puesto tipo DNP 2018 (320,6 m², 1 piso) · la torre es 10,5 veces». D la coloca en una posición fija documentada en `torre.js` (por ejemplo, centro en `x = −30`, `y = 0`) y comprueba que no se traslape con el hospital, la galería ni el bloque técnico; si se traslapa, elige otra y la documenta. La forma real queda por confirmar.

### 9.3 Cambios a `normas.json` (E)

- **Normas que se agregan** a `normas[]`, con el esquema que ya existe (`id`, `numero`, `anio`, `fecha`, `emisor`, `objeto`, `estado`, `url`, `paginas`, `fecha_consulta`, `requisitos_aplicables: [{ …, cita, tipo }]`, `lo_que_no_trae`): Res. 2080 de 2026 (revoca la Res. 1732 de 2026, que se registra con `estado: "revocada"`); Decreto 4725 de 2005 con su modificación por el Decreto 582 de 2017 (y el 3275 de 2009); Res. 4816 de 2008 (tecnovigilancia); Res. 914 de 2025 (reprocesamiento, desde el 3-ene-2027); Res. 1811 de 2025 (radiaciones ionizantes, reemplazó a la 482 de 2018); Res. 2065 de 2025 (sedes transitorias en emergencias); Decreto 3770 de 2004 (reactivos de diagnóstico *in vitro*). Cada requisito con su nivel de verificación de la investigación; lo no leído en la fuente, «por confirmar».
- **Correcciones a `servicios_3100`:** el «marcapasos externo» en el carro de paro o la reanimación de 11.6.1 pasa a «según guía secundaria; por confirmar»; los «criterio 18.14 / 18.15» de 11.6.1 quedan «(por confirmar: la investigación de urgencias no confirmó los criterios de infraestructura)»; la lista de modificaciones de la Res. 3100 dice «una resolución de 2022 (1138 o 1410; por confirmar en el normograma de Supersalud)».

---

## 10. Datos publicados y `build_data.py` (equipo D)

### 10.1 Exportaciones

| Archivo web | Desde | Contenido | Tamaño máximo (sin espacios) |
|---|---|---|---|
| `web/data/torre.json` (existente) | igual que hoy | Sin cambios de forma; se agregan a `dotacion.servicios[].equipos` los campos `especificacion`, `nota` (ya corregida por B, 4.7.2) y `exigencias` (ids con `exigible`) y la lista `mobiliario` | ≤ 620 KB (hoy 560 KB) |
| `web/data/torre_plantas.json` | `data/edificios/torre_hospital_plantas.json` | Forma compacta del 3.3 (citas en tabla, sin `poligono_libre`, 2 decimales, sin `fuentes` largas). `build_data.py` mide el resultado y lo imprime | ≤ 500 KB (estimación de la revisión: ≈ 400-450 KB con el esquema completo; con la forma compacta debe quedar por debajo) |
| `web/data/torre_inventario.json` | `inventario_dotacion.json` + `dotacion.json` + `catalogo_equipos.json` + `implementos.json` | 10.2; precios tomados de `dotacion.json` al exportar | ≤ 700 KB |
| `web/data/torre_habilitacion.json` | `habilitacion.json` | Mismo esquema | ≤ 300 KB |
| `web/data/torre_contraste.json` | `proyecto_tipo_contraste.json` + `dotacion.json` | Sin `busquedas` ni `acceso_a_fuentes`; el costo de `dotacion_por_ambiente` se calcula desde `lineas_torre` | ≤ 150 KB |
| `web/data/sismo_torre_estructura.json` | `data/sismo/torre_hospital_estructura.json` | Igual | ≤ 250 KB |
| `web/data/sismo_amenaza.json` | `data/sismo/amenaza.json` | Igual | ≤ 90 KB |

Reglas de `build_data.py`:

- Se cargan solo al entrar a cada modo o al abrir cada tarjeta, nunca con `data.js`.
- **Una sola fuente de precio en la web:** precio, rango, tipo y fuente de cada línea salen de `dotacion.json` (y de `laboratorio.json` para sus equipos) en el momento de exportar, por la `ref` de la línea; ningún otro archivo web lleva un precio copiado a mano.
- **Archivos generados al día:** cada archivo generado (`torre_hospital_plantas.json`, `exigencias_3100.json`, `inventario_dotacion.json`, `habilitacion.json`, `torre_hospital_estructura.json`) guarda `insumos_sha1: { archivo: hash }`. `build_data.py` recalcula los hashes y, si no coinciden, imprime un aviso visible y **no exporta** ese archivo (el inventario, además, se compara con `sha256_dotacion`). Así no hacen falta pasos nuevos en CI (`pages.yml` y `railpack.json` solo corren `build_data.py` y `build_site.py`).
- **Sin campos internos:** no se exportan a `web/data` `origen`, `ref`, `fuente_reparto`, `nota_interna`, `insumos_sha1` ni rutas de archivo; los textos de `fuente` y `verificacion` pasan por el diccionario de `textos.js` (13.6).
- Tolerante a insumos que todavía no existen: si falta uno, no escribe ese archivo y sigue.

### 10.2 `torre_inventario.json` (forma web)

```json
{
  "v": 2,
  "catalogo": { "cama_hospitalaria": { "f": "cama", "dim": [1.0, 2.2, 0.95], "b": 0.5, "mont": "piso", "anc": "ruedas_con_freno", "masa": 150, "hcg": 0.55, "mu": 0.3, "cont": false, "comp": [] } },
  "lineas": [ { "id": "L-urgencias-e-3f2a1c", "nombre": "…", "servicio": "urgencias", "tipo": "equipo", "cantidad": 1, "modelo3d": "desfibrilador",
                "clase": { "vigente": "IIb", "estado": "coherente", "revision": null }, "registro": { "requerido": "si", "via": "…", "usado_permitido": false },
                "exigencias": [ { "id": "EX-URG-012", "exigible": "si" } ], "prioridad": "habilitacion", "prioridad_revisada": null, "norma_base": null,
                "mantenimiento": { "anual_pct": 6, "vida_util_anios": 8, "personal_inscrito_invima": true, "calibracion": true },
                "componentes": [], "plantilla": null,
                "precio": 29126266, "rango": [26955531, 31297000], "tipo_precio": "referencia_secop_ajustada_ipc", "fuentes_precio": ["…"], "metodo_precio": "…" } ],
  "columnas_unidades": ["id", "linea_idx", "piso", "recinto", "x", "y", "z", "rot_z", "apoyo_idx", "dentro_de_idx", "componente_de_idx", "montaje", "estado"],
  "unidades": [ ["U-urgencias-3f2a1c-001", 0, 1, "P1-A017-01", -6.10, 17.35, 1.00, 1.5708, 37, -1, -1, "sobre", "en_dotacion"] ],
  "implementos": { "carro_paro_adulto_pediatrico": [ { "n": "Tabla de reanimación", "c": 1, "comp": "lateral", "tipo": "dispositivo", "verif": "dato del repositorio" } ] },
  "recintos": { "P1-A017-01": { "estado": { "corte_2026": "cumple", "apertura": "cumple" }, "exig": ["EX-URG-001"], "por_confirmar": 1 } },
  "totales": {}
}
```

- En el archivo de datos (4.5) la línea trae `ref: { servicio, lista, idx }` hacia `dotacion.json`; `build_data.py` la resuelve contra el mismo `dotacion.json` cuyo hash coincide y escribe `precio`, `rango`, `tipo_precio`, `fuentes_precio` y `metodo_precio` en la forma web. Los demás campos de la línea son los propios del inventario (modelo 3D, clase revisada, registro, exigencias, plantilla, mantenimiento).
- `z` es la altura sobre el piso terminado del nivel (0). `apoyo_idx`, `dentro_de_idx` y `componente_de_idx` son índices en `unidades` o `-1`. `b` del catálogo es el semiancho para el balanceo (4.3). Los hash de los ids de los ejemplos son ilustrativos.

### 10.3 HTML que agrega D (ola 0) en `#v-torre`

- En `.seg.wrap-seg`: `<button type="button" data-modo-torre="recorrido" aria-pressed="false">Recorrer por dentro</button>` y `<button type="button" data-modo-torre="sismo" aria-pressed="false">Simulador sísmico</button>`.
- En los controles del modo «Con la torre»: `<button type="button" data-capa-torre="tipo" aria-pressed="false">Proyecto tipo</button>` (9.2).
- Dentro de `.stage[data-scene=torre]`: `<div class="torre-hud" data-slot="torre.hud"><div data-slot="torre.hud.recorrido" hidden></div><div data-slot="torre.hud.sismo" hidden></div></div>`.
- En `.folder`, antes de la ficha: `<div class="card" data-slot="torre.panel"><div data-slot="torre.panel.recorrido" hidden></div><div data-slot="torre.panel.sismo" hidden></div></div>`.
- Dentro de la ficha `torre.ficha`, después de la nota original: `<div data-slot="torre.ficha.modo" hidden></div>`. D restaura la nota original al volver a «Hoy», «Con la torre» o «Pisos».
- Debajo del tablero: `<div class="card" data-slot="torre.sismo" hidden><h3>Lo que calculó el simulador</h3><div data-slot="torre.sismo.graficas"></div></div>` y `<div class="card"><h3>Dotación para la habilitación, servicio por servicio</h3><div data-slot="torre.habilitacion"></div></div>`.
- El título de la tarjeta `torre.tipo` pasa a «Contraste con el proyecto tipo».
- La ayuda `.stage-hint` cambia según el modo (texto de cada modo en `torre.js`).
- Cada modo recibe en su `ctx` solo sus contenedores, los muestra u oculta él mismo y nunca escribe `innerHTML` en el contenedor padre.

---

## 11. Documentos (equipo E)

### 11.1 `docs/11-torre-hospital-nivel-1.md` — secciones nuevas o cambiadas

- «En pocas palabras»: dos viñetas nuevas (contraste con el tipo; dotación por servicio frente a la norma, con su cierre de brechas) y una sobre el simulador.
- **2.1 Qué norma de habilitación rige:** la Res. 3100 sigue; la 1732 de 2026 fue revocada por la 2080; la 914 de 2025 cambia esterilización desde 2027 (antes de la apertura prevista hacia abril de 2030); la 1811 de 2025 reemplazó a la 482 (corregir las menciones); la lista de modificaciones de 2022 (1138 o 1410) queda por confirmar.
- **3.1 Contraste ambiente por ambiente** (los dos veredictos del 9.1, «frente al tipo» y «frente a la Res. 1633»), **3.2 Costo por m² y dotación frente al tipo** (tablas resumidas de `proyecto_tipo_contraste.json`, con tipo y base de área de cada cifra; el costo como rango de 0,8 % a 19,9 % y la obra completa de 1,34 a 1,59 veces, y la aclaración de que el §6.2 actual usa $5,42 M por m² sobre 270 m²) y **3.3 Dónde se aparta y por qué**.
- **4.1 Plantas por piso (anteproyecto ilustrativo)**: criterios, zonificación, áreas a ejes y libres, evacuación, avisos del validador.
- **5.2 Inventario para la habilitación** (enlace a `docs/15`), **5.3 Cierre de brechas** con su valor por proyecto (P4, P5, P6), los ítems por cotizar, la operación anual aparte y la nota de que usar la contingencia reduce la reserva de riesgo; el GeneXpert como posible costo no presupuestado ($144,0 M si se compra); y corrección «236 ítems con el equipamiento fijo» → «236 líneas de los 15 servicios más 14 de equipamiento fijo (250)».
- **1.1 ¿Qué le pasa a la torre en un sismo?** (resumen de 5 líneas y enlace a `docs/14`).
- «11. Lo que falta verificar»: agregar lo del 15 de este documento.
- Nota sobre el epicentro del 10-ago-2026 (OPS: San José del Palmar; anexo C: Pereira) sin escoger uno sin fuente; la misma nota en `docs/anexos/C-hospital-2028.md`.

### 11.2 `docs/09-motor-3d-y-modelos.md`

- «Vista Torre del hospital»: los modos nuevos y la máquina de estados entre modos (6.8: `salir({ porUsuario })`, contenedores por modo, `st.pickables` vaciado).
- **Recorrido en primera persona:** controles (teclado con `ev.code`, foco en el recuadro, selección por clic corto, Pointer Lock opcional), campo de visión, conducción de la cámara a través del objetivo de `OrbitControls`, colisión, cambio de piso, bloque técnico, minimapa, capas, accesibilidad, presupuesto medido por piso y calidad.
- **Catálogo de equipos 3D:** lista cerrada, LOD, agrupación por calidad, normalización de geometrías para fundir, malla fantasma y tabla de selección.
- **Simulador sísmico en pantalla:** dibujo de la deformada (Hermite, diafragma rígido, exageración), actualización de líneas gruesas sin reservar memoria, colores D/C, rótulas, reproducción por pasos calculados.
- **Worker de módulo y publicación:** Pages, Railway con Caddy, Artifact (respaldo con `motor.js`), cancelación con `terminate()`, URLs absolutas y la regla de no usar el importmap dentro del trabajador.
- **Herramientas de QA:** remite a `scripts/qa/LEEME.md` (three@0.160.0 y gsap@3.12.5 con `npm pack`, Playwright).
- QA de las funciones nuevas con las cifras medidas.

### 11.3 `docs/14-simulacion-sismica.md` (nuevo)

1. Para qué sirve y qué no es. 2. Richter y Mw. 3. De dónde sale el movimiento (Boore 2003, parámetros con fuente, sitio, escenarios y sus avisos, y la transición de profundidad de 40 a 70 km). 4. El modelo de la torre (prediseño: sistema estructural adoptado y R con sus factores, `Ta` y `Cu·Ta` del sistema, irregularidades, secciones, refuerzo, masas por nivel, núcleos con aletas, excentricidad, retroceso, umbral de daño). 5. El modelo no lineal (Giberson, histéresis, propiedades esperadas, gravedad, P-Delta con el peso de cada nivel, amortiguamiento y sus períodos ancla con el ξ efectivo de cada modo). 6. El método numérico (Newmark, Newton-Raphson, paso, alargamiento del período, calidad baja, estabilidad, energía con el trabajo de P-Delta). 7. Cómo leer la pantalla (cada gráfica y cada color; deriva vectorial; niveles de desempeño). 8. Resultados de los escenarios de referencia (tabla generada desde el motor con Δt = 0,005 s: deriva vectorial máxima, cortante basal, rótulas por nivel, equipos que deslizan o se balancean). 9. Validación (pruebas cerradas y OpenSees con sus cifras y sus casos de control). 10. Limitaciones e incertidumbres. 11. Lo que falta verificar. 12. Fuentes.

### 11.4 `docs/15-dotacion-y-habilitacion.md` (nuevo)

1. Qué es habilitar y qué norma rige (3100 con sus modificaciones; 1732 revocada; 4725; 914; 1811; 2065; 4816; 3770). 2. **Alcance:** la matriz es de cumplimiento en dotación e infraestructura; no evalúa talento humano, historia clínica ni interdependencia (texto obligatorio del 4.8). 3. Método: exigencia → ítem → unidad → lugar; niveles de verificación de los textos y qué es «exigible» frente a «por confirmar». 4. Matriz por servicio (cumple, parcial, falta, documentos; exigibles y por confirmar) en los dos escenarios y en los dos cortes (23-oct-2026 y apertura); servicios que no se habilitan como tales (sala de expansión, esterilización, telemedicina, TIC, toma de muestras) y su marco. 5. Cierre de brechas: lista con precio (o «por cotizar»), tipo, fuente, proyecto y naturaleza; decisión sobre la lavadora desinfectora y dependencia de la Res. 914. 6. Clases de riesgo revisadas, lo que cambió en `dotacion.json` y lo que quedó por confirmar. 7. Campos del inventario (Res. 3100 num. 11.1.3 y 11.1.4 y Decreto 4725) y obligaciones del prestador (registro, usados, mantenimiento por personal inscrito, manuales en castellano, tecnovigilancia en 72 horas para eventos serios). 8. Implementos internos (carro de paro, partos, kits, instrumental), por qué no suman precio y por qué los equipos biomédicos de los kits sí se inventarían uno por uno. 9. Equipos de laboratorio: 10 en comodato, 1 por programa o compra (no presupuestado), 1 opcional. 10. Reclasificaciones de la investigación (incubadora, fototerapia, sillones; otoemisiones por la Res. 3280) y el valor de habilitación con y sin ellas. 11. Dotación frente al proyecto tipo. 12. Decisiones pendientes con la Secretaría de Salud (cama TPR como «mesa de partos», desfibrilador compartido en el piso 3, registro de las camas de posparto, toma de muestras sin habilitación propia, ecografía en mediana complejidad) y de la E.S.E. (duplicado del kit de examen, lavadora desinfectora, GeneXpert). 13. Lo que falta verificar. 14. Fuentes.

### 11.5 `README.md`

Dos filas nuevas en la tabla de documentos (14 y 15) y una línea en la descripción de la torre.

### 11.6 Control de cifras

`python3 scripts/torre/verificar_cifras_docs.py` lee las cifras clave de los JSON (totales de inventario, cierre de brechas por proyecto, conteos de la matriz, resumen del contraste con sus dos bases de área, resultados de escenarios del motor, validación OpenSees) y comprueba que aparecen tal cual (formato es-CO) en `docs/11`, `docs/14` y `docs/15`; que $4.555.806 (sobre 320,6 m²) y $5,42 M (sobre 270 m²) aparecen juntas; y sale 1 si alguna no coincide. Ninguna mención de la Res. 1732 la da como vigente y ninguna de la Res. 482 de 2018 la da como norma que rige (`grep` sobre `docs/`, los JSON generados de `data/proyectos/torre_hospital/` y `web/data/`).

---

## 12. Reparto del trabajo y orden de dependencias

### 12.1 Olas

**Paso previo de la ola 0 (antes de abrir ramas):** A y B suben los insumos de investigación a `data/sismo/fuentes_investigacion/` (con `sim.py` y `gmpe.py` como referencia) y a `data/proyectos/torre_hospital/fuentes_investigacion/`; E sube la copia literal de `proyecto_tipo_contraste.json` (que luego modifica según el 9.1); D sube `scripts/qa/comun.mjs` y `scripts/qa/LEEME.md`. Los insumos salen de la carpeta `investigacion/` de la sesión de investigación, que los demás equipos no ven. Ningún criterio de aceptación depende de archivos que solo estén en el *scratchpad* de la sesión de investigación (`medir_torre.mjs`, `wtest/prueba.mjs`, `vendor_x/`, `sismo_calc/`) o en `/opt/node-tools`.

| Ola | A · Motor | B · Plantas e inventario | C · Recorrido | D · Vista sísmica e integración | E · Contraste y documentos |
|---|---|---|---|---|---|
| **0** (≤ 1 día; bloquea a los demás) | `ESQUEMA.md` con E1-E16; fixtures `estructura_min.json`, `resultado_min.json` **calculado sobre `estructura_min.json`** y `serie_elemento_min.json`, que pasan `validar_resultado.mjs`; `trabajador_simulado.js` | `catalogo_equipos.json` (lista cerrada del Anexo C); fixtures `plantas_min.json` (2 niveles con escalera y ascensor), `dotacion_min.json` e `inventario_min_datos.json` (pasan `validar_inventario.py --fixture`), `inventario_min.json` (pasa `--web`) y `habilitacion_min.json` | — | Botones, contenedores por modo, bloques CSS marcados, `_relleno.js` y carga perezosa `import('./torre/recorrido.js').catch(() => import('./torre/_relleno.js'))` (así C y E no chocan con D al subir sus módulos), `textos.js`, gancho `alReanudar`, `__torreQA`, exportaciones tolerantes en `build_data.py` | Copia del contraste a `data/` |
| **1** (en paralelo) | `movimiento.js` + pruebas T13-T16, T19, T20; `modelo.js` + T8-T11, T22; `integrador.js` + T1-T7, T12, T21; `motor.js` y `trabajador.js` + T17; `estructura_torre.py`; `amenaza.json` | Trazado y plantas (validador en verde) → exigencias → inventario → matriz → cambios a `dotacion.json` | `equipos3d.js`, `planta3d.js`, controles, minimapa, recorrido y tarjeta de habilitación **con los fixtures** | `sismo.js`, `estructura3d.js`, `graficas.js` **con el fixture de resultados y `trabajador_simulado.js`**; «Pisos» con `plantas_min` y `planta3d.js` de C cuando esté | `ambientes_programa` y veredictos partidos, `validar_contraste.py`, `contraste.js`, `normas.json` (9.3), `proyecto_tipo.json` (9.1), esqueletos de `docs/14` y `docs/15` |
| **2** (integración) | T18 con la estructura real; validación OpenSees con sus casos de control; `qa_worker.mjs` | Ajustes que pidan C y D (huellas, rotaciones, contenedores, apoyos) | Datos reales de B; capas de faltantes y contraste | Motor real de A; recorrido de C; contraste de E; «Pisos» con la planta real | `docs/11` y `docs/09` con cifras de A y B |
| **3** (cierre) | Cifras de escenarios para `docs/14` (Δt = 0,005 s) | CSV final | QA del recorrido | QA global de las 10 vistas + modos nuevos; prueba de humo tras el despliegue | `verificar_cifras_docs.py` en verde; README |

### 12.2 Dependencias duras

- C depende de los fixtures de B (ola 0), de `textos.js` y `comun.mjs` de D (ola 0) y de los datos reales de B (ola 2).
- D depende de los fixtures y del trabajador simulado de A (ola 0), del motor de A (ola 2), de los módulos de C y E (ola 2; los colores del contraste llegan al recorrido a través de D) y de la planta de B para «Pisos».
- E depende de las cifras finales de A y B para los documentos (ola 2-3).
- A y B no dependen de nadie (salvo `comun.mjs` de D para `qa_worker.mjs`).

### 12.3 Reglas de colaboración

- Cada equipo trabaja en su rama y abre cambios que **solo** tocan sus archivos (2.1) o sus bloques marcados (2.2). D integra al final de cada ola. Ningún equipo sube un archivo en una ruta que el 2.1 da a otro (por eso el relleno de D es un solo archivo propio).
- Un cambio de contrato (formato, firma, id) se pide por escrito al dueño y a D; el dueño actualiza este documento (o `ESQUEMA.md`) en el mismo cambio que lo implementa.
- Los fixtures del Anexo A son el contrato mínimo: si un productor cambia su formato, actualiza su fixture y su validador a la vez.
- Nadie publica, despliega ni hace *push* a `main` sin que el usuario lo pida.

---

## 13. Criterios de aceptación

### 13.1 Equipo A

```bash
node scripts/sismo/test_motor.mjs                          # T1-T22 (con T15b y T15c) en verde, código 0
python3 scripts/sismo/estructura_torre.py --verificar      # regenera y compara byte a byte; imprime chequeos
node scripts/sismo/validar_resultado.mjs scripts/fixtures/torre/resultado_min.json
python3 -m venv /tmp/vo && /tmp/vo/bin/pip install -r scripts/sismo/requisitos_validacion.txt \
  && /tmp/vo/bin/python scripts/sismo/validar_opensees.py # escribe data/sismo/validacion_opensees.json
node scripts/sismo/qa_worker.mjs --vendor <carpeta>        # Worker de módulo en Chromium, raíz y subruta; cancelar; respaldo
```

- Tolerancias del 7.8 y del 7.9 cumplidas, incluidos los dos casos de control de OpenSees.
- Prediseño (todos bloquean):
  - sistema estructural fijado en el paso 0 con la fracción de cortante de los pórticos y la fila de la tabla;
  - `R = φa·φp·φr·R0` con cada factor justificado; irregularidades 1aP/1bP y 3A reportadas con sus cocientes;
  - `Ta` y `Cu·Ta` de la fila del sistema adoptado (≈ 0,41 s y ≈ 0,56 s si es «otros sistemas»; cálculo propio), `T1` del modelo reportado junto a `Cu·Ta`, y `T ≤ Cu·Ta` en la FHE;
  - cortante modal ajustado a ≥ 80 % o ≥ 90 % de la FHE según la regularidad;
  - deriva vectorial ≤ 1 % en todos los entrepisos con el espectro de diseño;
  - **umbral de daño:** deriva vectorial ≤ 0,4 % (≤ 0,2 % en el escenario con mampostería adherida);
  - columna fuerte-viga débil ≥ 1,2 en todos los nudos; cortante por capacidad cubierto; excentricidad reportada;
  - períodos ancla del amortiguamiento y ξ efectivo de los 12 primeros modos reportados.
- Tiempos del 7.7 medidos con `qa_worker.mjs` (incluye la corrida con CPU ×4).
- `amenaza.json` idéntico en números a la investigación (comparación por script).

### 13.2 Equipo B

```bash
python3 scripts/torre/generar_plantas.py && git diff --exit-code data/edificios/torre_hospital_plantas.json   # segunda corrida sin cambios
python3 scripts/torre/validar_plantas.py               # 0 errores duros; avisos listados
python3 scripts/torre/normalizar_exigencias.py && python3 scripts/torre/generar_inventario.py
python3 scripts/torre/validar_inventario.py            # 0 errores duros
python3 scripts/torre/validar_inventario.py --fixture scripts/fixtures/torre/inventario_min_datos.json scripts/fixtures/torre/dotacion_min.json
python3 scripts/torre/validar_inventario.py --web scripts/fixtures/torre/inventario_min.json
python3 scripts/torre/test_torre.py                    # pruebas de geometría y de reglas
```

- Recintos: P1 = 82, P2 = 69, P3 = 69, P4 = 42, BT = 6; reglas V1-V20 sin errores duros; los avisos V8 listados en `docs/15`.
- Exigencias: 199 filas de origen trazables (`origen`); `exigible` y `numeral_confirmado` calculados por regla (61 `por_confirmar` por nivel); ≥ 80 % de las de estándar `dotacion` con regla automática; ningún nombre de ambiente ambiguo.
- Unidades: 509 + 359 + 15 + 12 (10 en comodato, 1 por programa o compra, 1 opcional) + las del cierre + las componentes; sumas por servicio **iguales** a `dotacion.json`; comodato = $955.708.589; reglas I1-I13 sin errores duros.
- La matriz reproduce el estado de la investigación o explica cada diferencia; trae `estandares_no_evaluados`, los dos cortes de `fecha_referencia` y `habilitable` en cada servicio.
- `dotacion.json` sigue siendo JSON válido, con `totales_generales` sin cambios, el mismo número de líneas (236 en los 15 servicios) y la sección `cierre_brechas_habilitacion` con totales por proyecto, `items_sin_precio` y tipo de cada precio.

### 13.3 Equipo C

```bash
node scripts/qa/recorrido_qa.mjs --vendor <carpeta>   # Chromium sin pantalla (SwiftShader); three y GSAP locales vía scripts/qa/comun.mjs
```

- Entra al recorrido, camina por un guion de teclas en los 4 pisos y el bloque técnico y nunca queda dentro de una celda de muro (`__torreQA.recorrido.estado().en_muro === false` y `libre(x, y)`); cambia de piso por ascensor y por escalera; no puede pisar el hueco de la escalera abierta del piso 2; abre la ficha de una unidad con implementos (carro de paro) y comprueba que lista el contenido.
- **Cámara:** con el caminante a 0,30 m de un muro, `camera.near ≤ 0,06`; el rumbo leído tras 60 cuadros quieto es igual al pedido (± 0,1°); el campo horizontal es ≥ 70° en 390 × 844 y ≥ 75° en 1400 × 900; al salir, `fov` = 36° y los parámetros de los controles son los de antes.
- **Selección:** un clic en un punto donde hay un piso oculto de «Pisos por servicio» no cambia la ficha; terminar un arrastre no selecciona; un clic sobre un muro no selecciona la unidad del recinto vecino.
- **Teclado:** `Ctrl+R`, `Ctrl+F` y `Cmd+D` no los intercepta el recorrido; escribir en un campo del panel no mueve al caminante; al perder el foco de la ventana con una tecla oprimida, el caminante se detiene.
- Presupuesto del 5.2: baja en 390 × 844 ≤ 30 llamadas y ≤ 120.000 triángulos en cada piso; media en 1400 × 900 ≤ 45 llamadas. Ninguno de los 105 modelos del Anexo C hace que `mergeGeometries` devuelva `null`.
- Claro, oscuro y teléfono: consola sin errores; `scrollWidth = innerWidth`; etiquetas dentro del recuadro; el minimapa no tapa el botón «Rendimiento» y la barra `.nav3d` no tapa el joystick.
- Solo teclado: llegar al botón «Recorrer por dentro», entrar (el foco queda en el recuadro), moverse con flechas, pasar con Tab a la lista del panel y abrir una ficha con Enter. Con `prefers-reduced-motion`: cambios de piso sin fundido.
- Al salir, los modos «Hoy» y «Con la torre» se ven igual que antes (capturas comparadas). «Pisos» y «Laboratorio», que cambian con la planta real (8.8), tienen criterios propios en el 13.4.

### 13.4 Equipo D

```bash
python3 scripts/build_data.py && python3 scripts/build_site.py   # sin errores; tamaños del 10.1; avisos de insumos_sha1 en cero
node scripts/qa/torre_qa.mjs --vendor <carpeta>                    # 6 modos × claro/oscuro × escritorio/teléfono
```

- Modo sísmico: corre `nido_2015` y `local_hip`; aparecen las 6 gráficas; el deslizador recorre `nt` pasos y en cada uno `__torreQA.sismo.cubiertaDibujada(i)` coincide con `u` × escala; ≤ 60 llamadas de dibujo; un clic donde hay un piso oculto no cambia la ficha.
- Respaldo sin Worker (QA con `Worker` deshabilitado): `__torreQA.sismo.motor() === 'hilo_principal'` y el mismo resultado que con Worker; «Cancelar» a la mitad responde en ≤ 300 ms.
- Cambiar de modo en medio de un cálculo o de un vuelo de cámara no deja contenidos de un modo en los contenedores del otro ni mueve la cámara del modo nuevo.
- «Pisos por servicio» con la planta real: ≤ 60 llamadas (hoy 204), etiquetas dentro del recuadro y leyenda de los 8 grupos; «Laboratorio» visible con su maqueta.
- Textos de la vista: el texto visible de todos los modos no contiene `/\.json|→\s*[a-z]+_[a-z_]+|data\//` (13.6).
- Las otras 9 vistas sin cambios: consola sin errores y sin desborde (QA previa de los commits 0b11474 y 8005ef2).

### 13.5 Equipo E

```bash
python3 scripts/torre/validar_contraste.py
python3 scripts/torre/verificar_cifras_docs.py
grep -rn "1732" docs/*.md data/proyectos/torre_hospital/*.json web/data/torre*.json   # toda mención dice «revocada»
grep -rn "482 de 2018" docs/*.md data/proyectos/torre_hospital/*.json web/data/torre*.json   # solo como norma reemplazada
```

- `docs/14` y `docs/15` con todas las secciones del 11.3 y 11.4; cada cifra con su tipo y, si es por m², su base de área; cada requisito con norma, numeral (o «por confirmar») y URL.
- La tarjeta de contraste se ve en claro, oscuro y teléfono (píldoras con tokens del tema); en las filas con recinto, el botón «Ver en 3D» abre el recorrido en el recinto correcto (en las filas `sin_recinto` no aparece).

### 13.6 Globales

- `pages.yml` y `railpack.json` siguen construyendo el sitio solo con `build_data.py` y `build_site.py` (sin pasos nuevos en CI).
- Prueba de humo tras el primer despliegue en GitHub Pages: abrir `index.html?qa=1#torre` publicado, correr `__torreQA.sismo.calcular()` y confirmar `__torreQA.sismo.motor() === 'trabajador'`.
- Ningún texto de la web cita rutas de archivos ni claves internas: todos pasan por `textos.limpio` (`web/js/scenes/torre/textos.js`, de D, con el diccionario ampliado: inventario, catálogo, implementos, `normas_4725_1732` → «la revisión del Decreto 4725», `res3100_*` → «la revisión de la Res. 3100», sin tramos «→ clave»), y `torre_qa.mjs` busca la expresión del 13.4 en el texto visible.
- La frase «servicio habilitado» no aparece en la web; el estado de la matriz se llama «cumplimiento en dotación e infraestructura».
- `git status` limpio fuera de los archivos del 2.1.

---

## 14. Riesgos y fuera de alcance

| Riesgo | Mitigación |
|---|---|
| Pisos 1 y 2 sin holgura de área (2,5 y 5,4 m²) para que los ambientes en el mínimo de la Res. 1633 cumplan también en área libre | Regla V7 a ejes (duro) y V8 libre (aviso); decisión documentada en `docs/15` |
| Llamadas de dibujo (hoy «Pisos» usa 204) | Un piso visible, instanciado por modelo, malla fundida, LOD1 en baja |
| Fachadas del GLB de una cara y entrepisos de 4,30 m | Ocultar `obra_nueva` y dibujar la envolvente propia en recorrido y sismo |
| Torsión fuerte por núcleos al oriente | Es física real del prediseño; se muestra y se explica con la deriva vectorial en las esquinas; A reporta la irregularidad con su cociente y la refleja en φp |
| Escenario por defecto (`nido_2015`, PGA ≈ 0,028 g) casi no produce esfuerzos | Escenarios corticales (`cimitarra`, `local_hip`) y escala «nivel de diseño NSR-10» marcada como hipotética |
| Pointer Lock bloqueado (iframe, Artifact) | Arrastre para mirar y controles táctiles siempre disponibles |
| Worker no disponible (Artifact) | Respaldo en el hilo principal por tramos |
| Textos normativos no cotejados con el Diario Oficial | Nivel de verificación visible y aviso en cada ficha y en `docs/15` |
| Cambios de `dotacion.json` que muevan el presupuesto | Cierre de brechas aparte, por proyecto y con la operación anual separada; `totales_generales` intacto; aviso de que usar la contingencia reduce la reserva de riesgo |
| Leer «cumple» como «se puede habilitar» | Estado llamado «cumplimiento en dotación e infraestructura», estándares no evaluados a la vista, solo exigencias exigibles en el color, frase «servicio habilitado» prohibida |
| Precios que se desactualizan entre archivos | Una sola fuente de precio (`dotacion.json`) resuelta al exportar; `insumos_sha1` y `sha256_dotacion` en los generados |
| Diferencias de idealización entre el motor y OpenSees que se confundan con errores | Misma formulación de amortiguamiento y de P-Delta en los dos, `Steel01` con `b` escalado y dos casos de control antes de la torre (7.9) |
| Amortiguamiento que oculte aceleraciones de piso | Períodos ancla de E8 y ξ efectivo de cada modo publicado |

**Fuera de alcance de esta iteración:** regenerar el GLB de la torre con los niveles 4,5/4,2/4,2/4,2 m y nodos por piso (`build_edificios.mjs:559, 601, 654, 831, 902, 961`); la interacción suelo-estructura con pilotes; la componente vertical; la degradación de resistencia (modelo de Ibarra-Medina-Krawinkler); la interacción P-M en rótulas y muros (E10, fase 2); la compatibilidad vertical en las esquinas de los núcleos (se usan aletas efectivas); las rótulas dentro del vano de las vigas; actualizar `presupuesto.json`/`financiacion.json` con el cierre de brechas.

---

## 15. Pendientes por confirmar (heredados de la investigación)

- Texto oficial (normograma de Supersalud o Diario Oficial) de las 199 exigencias; subnumerales que difieren entre copias (12.1 frente a 9.2; 17.1.2.x frente a 17.2.1.x; criterio 8 frente a 11 del carro de paro); listas literales de infraestructura de urgencias y partos; num. 26 y 27 de esterilización.
- Códigos REPS (1102, 1101, 129, 130, 328, 312, 344, 333, 334, 748, 420, 714, 739, 729, 706, 712, 744, 745) tomados de `programa.json`.
- Contenido mínimo del carro de paro (si exige desfibrilador con marcapasos en baja complejidad: hoy «marcapasos externo» en 11.6.1 solo lo agrega una guía secundaria); kit de anafilaxia en vacunación; DEA o carro de paro en el piso 4; criterios 18.14 y 18.15 de infraestructura de urgencias; área libre mínima por cama en hospitalización (7 m² y 6 m² en pediatría, según guía secundaria); las 61 exigencias que hoy son de guía secundaria o paráfrasis.
- Decreto 4725: reglas 3, 4, 5, 8 y 14; definición del art. 2; artículo de equipos usados (37 o 36); lista de tecnología controlada; concepto del INVIMA sobre central de gases, generador PSA, PACS y refrigeradores; artículo de la Res. 4816 con las 72 horas.
- Publicación de la Res. 2080 de 2026 en el Diario Oficial; si los proyectos de julio (DMER) y octubre (emergencias) de 2026 se expidieron; probable manual nuevo antes de la apertura (hacia abril de 2030 según `docs/11`): repetir el cruce cuando salga.
- Lista de modificaciones de la Res. 3100: la de 2022 es la 1138 (investigación de urgencias) o la 1410 (`normas.json`); cotejar en el normograma de Supersalud (no se pudo el 23-oct-2026: el proxy rechazó el sitio y se agotó el cupo de búsquedas).
- Res. 914 de 2025: manual DMER (requisitos de esterilización al abrir la torre; prioridad de la lavadora desinfectora; secadora, lupa y etiquetadora del cierre).
- GeneXpert: si lo entrega el programa nacional de tuberculosis o se compra ($144,0 M no presupuestados).
- Res. 1633: si el mínimo de área es libre o a ejes; procesamiento de rayos X (Cuadro 22) y control y procesamiento de ecografía (Cuadros 26-27) en baja complejidad con equipos digitales.
- NSR-10: tablas de Fa y Fv para suelo D, numeración de A.2.6, filas de sistema dual y combinado (Tablas A.3-2 y A.3-4) con R0 y Ω0, Ct y α de la Tabla A.4.2-1, k de A.4.3, ajuste del cortante modal (A.5.4.5), rango de escalamiento de registros (A.2.7), deriva vectorial (A.6.3.1), espectro y rigidez del umbral de daño (A.12.3-A.12.4), irregularidades (Tablas A.3-6 y A.3-7), aletas efectivas de muros (C.21.9.5.2), numerales de C.21 y de A.9, cargas del título B; tipo de suelo real (estudio geotécnico).
- ASCE/SEI 41-17: factores de material esperado para f'c y fy; parámetros «a» y «b» y límites IO, LS y CP de vigas, columnas y muros de concreto; longitud de rótula de muros.
- Sismotectónica: centro y profundidad del nido de Bucaramanga, Mw del 10-mar-2015, distancias a las fallas, magnitudes máximas, GMPE del modelo nacional del SGC.
- Proyecto tipo: el PDF del DNP (áreas por ambiente de los 6 módulos, lista de 59 ítems, AIU) y las «capacidades instaladas tipo» de la Res. 1211/1519.

---

## 16. Alcance ampliado: recorrer TODA la torre (pedido del usuario, 23-oct-2026)

Pedido literal posterior: «Quiero poder caminar por cada parte de la torre e inspeccionar toda la dotación necesaria, así como el
laboratorio, pero con TODO lo de la torre». Esta sección **prevalece** sobre lo que diga en contra el resto del documento (incluidos 6, 8.8,
14 y el Anexo C) y la aplican B, C, D y E desde la ola 1.

### 16.1 Qué se recorre (todo caminable, con colisión)

| Nivel del recorrido | Qué tiene | Dueño de la planta |
|---|---|---|
| Exteriores inmediatos (cota 0) | Plaza de acceso bajo el mango grande, patio y retorno de urgencias, **bahía de ambulancias** con marquesina solar y 2 cupos (con 2 ambulancias como contexto, no dotación de la torre), galería cubierta al hospital actual, accesos de servicio, cerramiento | B (`trazado`, nivel `EXT`) |
| Pisos 1 a 4 | Todos los recintos del programa (incluidos baños, depósitos, cuartos de aseo, ductos visitables, vestíbulos, esclusas) | B |
| Núcleos | Escaleras norte y sur **caminables** entre pisos (rampa de colisión por tramo, o tramo con «subir/bajar» al llegar al descanso), vestíbulo de ascensores con cabinas y botón de piso, montacargas de muestras visible en la toma (piso 1) y en el laboratorio (piso 2) | B (geometría), C (interacción) |
| Bloque técnico (`BT`) | Subestación y transformador de 300 kVA, planta eléctrica con transferencia, tableros generales, **cuarto de baterías del nodo hospital (400 kWh, P7) y UPS**, central de gases (manifold y generador de oxígeno PSA), equipos de presión y bombas sobre las cisternas (40 m³ agua potable, ≈ 30 m³ contra incendio), depósito de cadáveres con nevera mortuoria, cuarto central de residuos con canecas y báscula | B |
| Cubierta técnica (`CUB`, piso 4 y terraza del piso 3 sur) | Caminable: **paneles solares** (los 182 módulos de 100,1 kWp, en filas con pasillos de mantenimiento), condensadoras de la climatización, tanques elevados si el programa los tiene, casetas de cubierta (107,4 m²), salida de escalera, baranda perimetral | B |

Las cifras y la ubicación salen de `programa.json` (implantación, núcleos, cubierta técnica, bloque técnico, patios), de `dotacion.json`
(`equipamiento_fijo`) y de `data/edificios/torre_hospital.json` (`adecuaciones`, solar y baterías). Si un dato no está, se marca
«estimación» y se dice en la ficha.

### 16.2 El laboratorio, completo y dentro del recorrido

- Los recintos reales del laboratorio del piso 2 (recepción y registro, toma o paso de muestras desde el montacargas, hematología,
  química, inmunología, microbiología y tamizaje con cabina de bioseguridad, biología molecular con el GeneXpert, uroanálisis y
  coprología, lavado y esterilización de material, depósito de reactivos, neveras, área administrativa del bacteriólogo, ducha y lavaojos)
  se dibujan con **todo** lo de `laboratorio.json` (analizadores en comodato, los de compra o programa y el opcional, marcados como tales)
  y lo de `dotacion.json` del servicio `laboratorio` y `toma_muestras`.
- **Implementos internos del laboratorio** (en `implementos.json`): por analizador, los reactivos, calibradores, controles y consumibles que
  usa según las pruebas de `laboratorio.json` (nombre, presentación, condición de almacenamiento, nevera donde se guarda); kits de
  tamizaje; material de vidrio y de toma; elementos de bioseguridad. Si `laboratorio.json` no detalla un insumo, se nombra genérico y
  se marca «estimación».
- El botón del modo **«Laboratorio»** abre el recorrido parado en la puerta del laboratorio (piso 2), mirando hacia adentro. La maqueta
  vieja deja de usarse (D decide si se retira o queda como vista de conjunto).

### 16.3 Infraestructura que se ve y se inspecciona (capa propia, no es dotación ni suma a su costo)

Lo que los estándares de infraestructura de la Res. 3100 y de la Res. 1633 piden en cada ambiente y que condiciona la habilitación:
lavamanos (con su regla por ambiente), unidades sanitarias, duchas, pocetas de aseo, lavachatas, **tomas de gases medicinales** (oxígeno,
vacío, aire) por cama y camilla, tomas eléctricas de la red de emergencia donde aplique, llamado de enfermería, extintores y gabinetes
contra incendio, señalización de evacuación, cortinas antifluido. Va en `inventario_dotacion.json` con `capa: "infraestructura"`
(sin precio de dotación; si el presupuesto de obra lo tiene, se cita el ítem de `presupuesto.json`) y en la matriz de cumplimiento como
evidencia de las exigencias de infraestructura. Se puede encender o apagar en el recorrido.

### 16.4 Inspección de TODO

- Todo objeto visible del recorrido (dotación, implemento a la vista, equipamiento fijo, infraestructura, recinto) se puede seleccionar y
  abre su ficha: nombre, servicio, recinto, cantidad, especificación, clase de riesgo (Decreto 4725) y registro INVIMA, exigencia
  (Res. 3100, numeral, nivel de verificación) o «recomendado», estado, precio y tipo de precio, mantenimiento, anclaje sísmico, y su
  contenido (implementos internos) desplegable.
- **Inventario completo navegable**: un buscador y una lista filtrable por piso/nivel, servicio, recinto, capa (dotación, fijo,
  infraestructura, laboratorio en comodato), clase de riesgo y estado de cumplimiento, con el total de unidades y de valor de lo filtrado;
  cada fila tiene «Ir a», que lleva al caminante frente a la unidad y la resalta.
- **Por servicio**: la tarjeta de cumplimiento en dotación e infraestructura lista cada exigencia con sus unidades (cada una con «Ir a»)
  y las faltantes resaltadas en el 3D.
- La lista del recinto actual se actualiza al caminar.

### 16.5 Catálogo 3D: modelos que se agregan al Anexo C

`lavamanos`, `lavamanos_quirurgico`, `inodoro`, `ducha`, `poceta_aseo`, `lavachatas`, `barra_apoyo`, `extintor`, `gabinete_incendio`,
`senal_evacuacion`, `toma_gases_cabecera` (panel de cabecera con O₂, vacío, aire y tomas), `llamado_enfermeria`, `transformador`,
`tablero_electrico`, `banco_baterias` (racks del BESS), `bomba_agua`, `tanque_agua` (elevado o tapa de cisterna), `panel_solar_fila`
(fila paramétrica de módulos sobre estructura), `caseta_cubierta`, `baranda`, `contenedor_residuos`, `bascula_residuos`,
`ambulancia` (contexto), `montacargas_muestras`, `escalera_tramo` (si la escalera se dibuja como modelo), `reactivo_caja` y
`frasco_reactivo` (implementos visibles en estantes y neveras del laboratorio, instanciados), `gradilla_tubos`, `pipeta_set`.
Mismas reglas del 5 (instanciado, LOD, dimensiones reales, `mergeGeometries` sin `null`).

### 16.6 Presupuesto y criterios que cambian

- Un solo nivel visible a la vez (exteriores, pisos 1-4, `BT`, `CUB`); el presupuesto del 5.2 aplica por nivel. Los implementos internos
  se dibujan solo en el recinto donde está el caminante (o como cajas resumen instanciadas) para no pasarse.
- 13.2: los conteos de recintos incluyen los niveles `EXT`, `BT` y `CUB`; todo `equipamiento_fijo` de `dotacion.json` queda ubicado.
- 13.3: el guion de QA recorre exteriores, los 4 pisos (incluido el laboratorio completo), el bloque técnico y la cubierta; abre la ficha de
  un analizador en comodato con sus reactivos, la de un panel solar, la del manifold de gases y la de un lavamanos; usa «Ir a» desde el
  buscador; sube y baja por una escalera caminando.

---

## 17. Modelo BIM, NSR-10 en amenaza intermedia, cimentación y refuerzo (pedido del usuario, 24-oct-2026)

Pedido literal: «En la torre, aplica la metodología BIM, para poder observar todo su comportamiento; incluye esto de manera profesional
cumpliendo la norma sismo resistente intermedia para la zona de Antioquia; deja ver los cimientos estructurales de manera clara, también su
refuerzo en metal y dónde va; todo esto alineado con el proyecto tipo». Esta sección **prevalece** sobre el 7.2 y el 14 donde choquen.

### 17.1 Norma y sistema estructural (cambia el 7.2)

- Yondó: Aa = Av = 0,15 → **zona de amenaza sísmica intermedia** (NSR-10 A.2.3: 0,10 < Aa ≤ 0,20; numeral por confirmar). La torre es
  grupo IV (I = 1,5). El prediseño se hace con **capacidad moderada de disipación de energía (DMO)**, que es lo que la NSR-10 exige como
  mínimo en amenaza intermedia, en lugar del DES que fijaba el 7.2. A2 debe **verificar** en la NSR-10 (A.3, tablas de sistemas, y C.21)
  que no haya una exigencia adicional para el grupo IV en zona intermedia; si la hay, se aplica y se explica. R0, Ω0 y Cd del sistema
  (combinado o dual) se toman de la fila DMO de la tabla correspondiente.
- Detallado con los requisitos DMO del capítulo C.21 (pórticos y muros estructurales DMO) y lo general de C.7 (ganchos, separación de
  barras, recubrimientos), C.12 (desarrollo y traslapos), C.10/C.11 (flexión, flexocompresión y cortante), C.13 (losas nervadas), C.15
  (cimentaciones: dados, **vigas de amarre** con la fuerza axial de C.15.13, numeral por confirmar) y el título H (pilotes). Todo numeral
  sin confirmar va marcado «por confirmar».

### 17.2 Cimentación (ahora en alcance; sin interacción suelo-estructura en el análisis dinámico)

- Supuesto de prediseño (de `presupuesto.json`, capítulo 2, **estimación** hasta el estudio geotécnico): pilotes preexcavados de concreto de
  0,60 m de diámetro, ≈ 12 m de largo, 3-4 por dado, bajo 28 dados de ≈ 2,2 × 2,2 × 1,1 m; vigas de cimentación/amarre entre dados en las
  dos direcciones; losa de contrapiso de 0,15 m; fosos de ascensor y cisternas.
- A2 los **dimensiona**: carga por columna (gravedad + sismo con Ω0 donde aplique), número de pilotes por dado con una capacidad de pilote
  estimada (fuste y punta con parámetros típicos de suelo aluvial tipo D, con fuente, «estimación — la fija el estudio geotécnico»),
  revisión de punzonamiento y flexión del dado, vigas de amarre con su fuerza axial y su momento por asentamiento diferencial estimado,
  refuerzo de pilotes (canasta: longitudinal y espiral o estribos, longitud armada). Salida en `torre_hospital_estructura.json →
  cimentacion` (elementos con geometría, cargas, chequeos y refuerzo). En la simulación la base sigue empotrada en la cara superior de
  los dados (se dice en la web).

### 17.3 Refuerzo: despiece por elemento

- A2 entrega en `torre_hospital_estructura.json → refuerzo` el armado de **cada** elemento (no solo secciones tipo): columnas (barras
  longitudinales por cara con diámetro, estribos y ganchos suplementarios, zona confinada lo y separación so, resto, traslapos en la mitad
  central), vigas (superior e inferior por tramo con bastones y cortes, estribos en 2h y en el centro, ganchos sísmicos de 135°), viguetas y
  loseta de la losa nervada (con malla de temperatura), muros (mallas, elementos de borde si aplican), escaleras, pilotes, dados y vigas
  de cimentación; con designación colombiana de barras (N° 3 a N° 8, NTC 2289, fy = 420 MPa) y recubrimientos. Debe ser coherente con las
  propiedades de rótula (My, Mn, Vn) que usa el motor.
- Cantidades: kg de acero y m³ de concreto por elemento y por tipo, comparados con las cuantías de `presupuesto.json` (kg/m³ por capítulo);
  si difieren, se informa la diferencia y su efecto en pesos (sin editar el presupuesto: queda como pendiente con su cifra).

### 17.4 Modelo BIM (equipo F, después de A y B)

- **Datos**: `data/bim/torre_hospital.bim.json` (generado por `scripts/bim/generar_bim.py` desde plantas, estructura con cimentación y
  refuerzo, inventario, presupuesto, APU y cronograma): modelo federado por disciplinas — ARQ (espacios = recintos, muros, puertas,
  ventanas, losas de piso y cubierta, escaleras), EST (columnas, vigas, losas nervadas, muros estructurales), CIM (pilotes, dados, vigas
  de cimentación, contrapiso, fosos), REF (refuerzo con parámetros compactos que la web convierte en barras), MEP/fijo (equipamiento fijo e
  infraestructura del inventario), DOT (dotación). Cada elemento: GlobalId IFC determinista de 22 caracteres, clase IFC4 (IfcColumn,
  IfcBeam, IfcSlab, IfcWall, IfcFooting, IfcPile, IfcReinforcingBar, IfcSpace, IfcDoor, IfcWindow, IfcStair, IfcMedicalDevice,
  IfcFurnishingElement, IfcFlowTerminal…), nivel (IfcBuildingStorey), geometría, material, conjuntos de propiedades (Pset comunes de IFC
  y uno propio con tipo de dato, fuente y norma), cantidades (Qto), vínculo **5D** (ítem de `presupuesto.json` y su APU), **4D** (fase y
  fechas del cronograma de `docs/11` sección 10) y vínculo con el **análisis** (id del elemento en la estructura sísmica, para pintar D/C,
  rótulas y derivas del último cálculo).
- **IFC4 real**: `scripts/bim/exportar_ifc.py` (Python, solo biblioteca estándar, escritor STEP propio) → `web/models/torre_hospital.ifc`
  (georreferenciado con IfcMapConversion al Origen Nacional, EPSG:9377, desde el ancla del 0) con todo lo anterior, incluido el refuerzo
  como IfcReinforcingBar con su geometría de barra. Validación con ifcopenshell en el venv de validación (no dependencia del sitio):
  esquema IFC4 sin errores, conteos por clase y cantidades iguales a las del JSON. Tamaño razonable para descargar (si pasa de ≈ 15 MB,
  dividir en un IFC de arquitectura+estructura+cimentación y otro de refuerzo).
- **Plan de ejecución BIM** en `docs/16-bim-torre.md`: alcance y usos del modelo (coordinación, cantidades 5D, 4D, análisis estructural,
  dotación y habilitación, mantenimiento), términos de ISO 19650 y del marco BIM de Colombia (Estrategia Nacional BIM 2020-2026; norma de
  la entidad si aplica, por confirmar), LOIN/LOD por disciplina (arquitectura ≈ 300, estructura ≈ 350, refuerzo ≈ 400 en el despiece,
  cimentación ≈ 350, dotación ≈ 200-300), codificación de elementos, georreferenciación, detección de interferencias y sus resultados,
  cantidades contra el presupuesto, y límites («modelo de prefactibilidad: no reemplaza los diseños firmados»).
- **Interferencias**: `scripts/bim/interferencias.py` (equipos o puertas contra columnas y muros estructurales, ductos y fosos contra
  vigas de cimentación, separación libre del refuerzo contra el mínimo de C.7.6 y el tamaño del agregado, recubrimientos); resultado en
  `data/bim/interferencias.json` y en la web.

### 17.5 Modo «Modelo BIM» en la vista (equipo F; D integra)

- Árbol del modelo por disciplina → nivel → clase → elemento, con contadores; buscar; aislar, ocultar y transparencia por disciplina.
- Panel de propiedades del elemento seleccionado (Psets, cantidades, 5D, 4D, norma) y su refuerzo.
- **Cortes**: planos de sección horizontales por nivel y verticales por eje (A-D, 1-7), con tapa de corte; vista de corte del elemento.
- **Cimentación clara**: terreno semitransparente o cortado, pilotes completos hasta la punta con su cota, dados, vigas de amarre, fosos y
  cisternas, con etiquetas de dimensiones y cargas.
- **Refuerzo y dónde va**: al seleccionar un elemento (o «refuerzo del eje») se ve su armado en 3D — barras longitudinales, estribos y
  ganchos, zonas confinadas, traslapos, canastas de pilotes, parrillas de dados — con etiquetas («12 N° 7», «E N° 4 c/0,10 en lo = 0,60 m»)
  y el concreto transparente; un esquema 2D del despiece (sección y alzado) al lado.
- **Comportamiento**: colorear la estructura con los resultados del último cálculo sísmico (D/C, rótulas, deriva) y abrir el simulador
  desde el elemento; **5D**: tabla de cantidades y costo por disciplina y capítulo, comparada con el presupuesto; **4D**: deslizador del
  cronograma (cimentación → estructura piso a piso → cerramientos → redes → dotación); **interferencias**: lista con «Ir a».
- Descarga del IFC. Presupuesto de dibujo: el refuerzo solo del elemento o eje elegido (instanciado), nunca de toda la torre a la vez.

### 17.6 Alineado con el proyecto tipo

- Se mantiene la lógica estructural del proyecto tipo DNP 2018 (pórticos de concreto reforzado modulares, retícula repetible) escalada a la
  retícula de 7,20 m múltiplo del módulo de 1,20 m (Res. 1633). El contraste (equipo E) agrega filas para sistema estructural, capacidad de
  disipación, cimentación, cuantías de acero y concreto por m², luces y alturas, frente al tipo (lo que el tipo traiga; lo que no, «por
  confirmar»), y `docs/16` lo resume.

### 17.7 Reparto y aceptación

- A2 (carril A) hace 17.1-17.3. F (carril BIM, después de A y B) hace 17.4-17.5 con permiso de editar `web/index.html` y
  `web/js/scenes/torre.js` solo dentro de bloques marcados `bim` (D revisa en la integración). E agrega 17.6 al contraste y a los documentos.
- Aceptación: `python3 scripts/sismo/estructura_torre.py --verificar` con los chequeos DMO, de cimentación y de refuerzo en verde;
  `python3 scripts/bim/generar_bim.py && python3 scripts/bim/exportar_ifc.py` deterministas; validación IFC sin errores con ifcopenshell;
  `python3 scripts/bim/interferencias.py` sin interferencias duras (o cada una explicada); QA del modo BIM en claro, oscuro y teléfono
  (cortes, cimentación, refuerzo de una columna, una viga, un dado y un pilote, 5D, 4D, colores del sismo, descarga del IFC).

---

## Anexo A · Ejemplos mínimos (fixtures del contrato)

Los productores los escriben completos en la ola 0 en `scripts/fixtures/torre/` (no se publican) y deben pasar sus validadores.

### A.1 `plantas_min.json` (B) — dos pisos de 9,60 × 8,55 m

Por piso: dos consultorios de 3,60 × 3,60 m a ejes, una sala de espera, un corredor de evacuación de 2,55 m a ejes (2,43 m libres con muros livianos de 0,12 m) y un núcleo con la escalera y el ascensor (comparten el núcleo para no agrandar el ejemplo). Muros de fachada fundidos por lado (`lados: [null, "exterior"]`, permitido en fachada); los interiores, uno por borde compartido. Se muestra `P1` completo; `P2` (`z = 4,5`) repite la misma geometría con ids `P2-…` y filas 4 a 7, y las conexiones verticales `ESC` y `ASC` van en los dos pisos. Como las filas de prueba no existen en `programa.json`, el fixture se valida con `validar_plantas.py --fixture`, que omite las reglas que dependen del programa y de la retícula real (V2, V6, V15, V16 y V20).

```json
{
  "id": "plantas_min", "version": 1, "tipo_dato": "estimacion", "estado": "Ejemplo de contrato",
  "marco": { "ancla": { "lat": 7.005271, "lon": -73.914597 }, "ejes": "x este, y norte, z arriba; metros", "a_three": "(X, Y, Z) = (x, z, -y)" },
  "modulo_m": 1.2,
  "reticula": { "ejes_x": [ { "id": "A", "x": 0.0 }, { "id": "B", "x": 9.6 } ], "ejes_y": [ { "id": "1", "y": 0.0 }, { "id": "2", "y": 8.55 } ] },
  "tipos_muro": { "fachada": { "espesor_m": 0.20 }, "nucleo": { "espesor_m": 0.30 }, "liviano": { "espesor_m": 0.12 } },
  "niveles": [ {
    "id": "P1", "piso": 1, "z": 0.0, "altura_entrepiso_m": 4.5, "altura_libre_m": 3.0,
    "contorno": [[0, 0], [9.6, 0], [9.6, 8.55], [0, 8.55]],
    "columnas": [ { "id": "A1", "x": 0, "y": 0, "b": 0.6, "h": 0.6 }, { "id": "B1", "x": 9.6, "y": 0, "b": 0.6, "h": 0.6 }, { "id": "A2", "x": 0, "y": 8.55, "b": 0.6, "h": 0.6 }, { "id": "B2", "x": 9.6, "y": 8.55, "b": 0.6, "h": 0.6 } ],
    "recintos": [
      { "id": "P1-A000-01", "fila": 0, "k": 1, "de": 1, "ambiente": "Consultorio de prueba A", "servicio_programa": "Consulta externa", "grupo_1633": "consulta_externa", "tipo": "recinto",
        "poligono": [[0, 4.95], [3.6, 4.95], [3.6, 8.55], [0, 8.55]], "poligono_libre": [[0.1, 5.01], [3.54, 5.01], [3.54, 8.45], [0.1, 8.45]],
        "area_ejes_m2": 12.96, "area_libre_m2": 11.83, "area_programa_m2": 12.96, "minimo_1633": { "m2": 10.0, "lado_m": 2.5, "cita": "Res. 1633, Anexo 1, Cuadro 5" }, "acceso": ["P1-CIRC-01"] },
      { "id": "P1-A001-01", "fila": 1, "k": 1, "de": 1, "ambiente": "Consultorio de prueba B", "servicio_programa": "Urgencias", "grupo_1633": "atencion_inmediata", "tipo": "recinto",
        "poligono": [[3.6, 4.95], [7.2, 4.95], [7.2, 8.55], [3.6, 8.55]], "poligono_libre": [[3.66, 5.01], [7.05, 5.01], [7.05, 8.45], [3.66, 8.45]],
        "area_ejes_m2": 12.96, "area_libre_m2": 11.66, "area_programa_m2": 12.96, "minimo_1633": { "m2": 10.0, "lado_m": 2.5, "cita": "Res. 1633, Anexo 1, Cuadro 92" }, "acceso": ["P1-CIRC-01"] },
      { "id": "P1-A002-01", "fila": 2, "k": 1, "de": 1, "ambiente": "Sala de espera de prueba", "servicio_programa": "Consulta externa", "grupo_1633": "consulta_externa", "tipo": "recinto",
        "poligono": [[0, 0], [7.2, 0], [7.2, 2.4], [0, 2.4]], "poligono_libre": [[0.1, 0.1], [7.05, 0.1], [7.05, 2.34], [0.1, 2.34]],
        "area_ejes_m2": 17.28, "area_libre_m2": 15.57, "area_programa_m2": 17.0, "minimo_1633": null, "acceso": ["P1-CIRC-01"] },
      { "id": "P1-CIRC-01", "tipo": "circulacion", "ambiente": "Corredor", "poligono": [[0, 2.4], [7.2, 2.4], [7.2, 4.95], [0, 4.95]], "area_ejes_m2": 18.36, "ancho_libre_m": 2.43, "evacuacion": true, "camillas": false },
      { "id": "P1-A003-01", "fila": 3, "k": 1, "de": 1, "ambiente": "Escalera de prueba", "servicio_programa": "Circulación vertical y ductos", "grupo_1633": "circulacion", "tipo": "nucleo",
        "poligono": [[7.2, 0], [9.6, 0], [9.6, 8.55], [7.2, 8.55]], "area_ejes_m2": 20.52 }
    ],
    "nucleos": [ { "id": "P1-NUC-ESC", "tipo": "escalera", "recinto": "P1-A003-01", "poligono": [[7.2, 0], [9.6, 0], [9.6, 8.55], [7.2, 8.55]] } ],
    "muros": [
      { "id": "P1-M-0001", "a": [0, 4.95], "b": [3.6, 4.95], "tipo": "liviano", "espesor": 0.12, "altura": 3.0, "lados": ["P1-CIRC-01", "P1-A000-01"], "estructural": false },
      { "id": "P1-M-0002", "a": [3.6, 4.95], "b": [7.2, 4.95], "tipo": "liviano", "espesor": 0.12, "altura": 3.0, "lados": ["P1-CIRC-01", "P1-A001-01"], "estructural": false },
      { "id": "P1-M-0003", "a": [3.6, 4.95], "b": [3.6, 8.55], "tipo": "liviano", "espesor": 0.12, "altura": 3.0, "lados": ["P1-A000-01", "P1-A001-01"], "estructural": false },
      { "id": "P1-M-0004", "a": [0, 2.4], "b": [7.2, 2.4], "tipo": "liviano", "espesor": 0.12, "altura": 3.0, "lados": ["P1-A002-01", "P1-CIRC-01"], "estructural": false },
      { "id": "P1-M-0005", "a": [7.2, 0], "b": [7.2, 2.4], "tipo": "nucleo", "espesor": 0.30, "altura": 4.5, "lados": ["P1-A002-01", "P1-A003-01"], "estructural": true },
      { "id": "P1-M-0006", "a": [7.2, 2.4], "b": [7.2, 4.95], "tipo": "nucleo", "espesor": 0.30, "altura": 4.5, "lados": ["P1-CIRC-01", "P1-A003-01"], "estructural": true },
      { "id": "P1-M-0007", "a": [7.2, 4.95], "b": [7.2, 8.55], "tipo": "nucleo", "espesor": 0.30, "altura": 4.5, "lados": ["P1-A001-01", "P1-A003-01"], "estructural": true },
      { "id": "P1-M-0008", "a": [0, 0], "b": [0, 8.55], "tipo": "fachada", "espesor": 0.20, "altura": 4.5, "lados": [null, "exterior"], "estructural": false },
      { "id": "P1-M-0009", "a": [0, 8.55], "b": [9.6, 8.55], "tipo": "fachada", "espesor": 0.20, "altura": 4.5, "lados": [null, "exterior"], "estructural": false },
      { "id": "P1-M-0010", "a": [9.6, 0], "b": [9.6, 8.55], "tipo": "fachada", "espesor": 0.20, "altura": 4.5, "lados": [null, "exterior"], "estructural": false },
      { "id": "P1-M-0011", "a": [0, 0], "b": [9.6, 0], "tipo": "fachada", "espesor": 0.20, "altura": 4.5, "lados": [null, "exterior"], "estructural": false }
    ],
    "puertas": [
      { "id": "P1-PT-001", "muro": "P1-M-0001", "centro": [1.8, 4.95], "ancho": 1.0, "alto": 2.1, "hojas": 1, "desde": "P1-CIRC-01", "hacia": "P1-A000-01", "abre": "adentro", "bisagra": "izquierda", "tipo": "batiente", "categoria": "consultorio" },
      { "id": "P1-PT-002", "muro": "P1-M-0002", "centro": [5.4, 4.95], "ancho": 1.0, "alto": 2.1, "hojas": 1, "desde": "P1-CIRC-01", "hacia": "P1-A001-01", "abre": "adentro", "bisagra": "derecha", "tipo": "batiente", "categoria": "consultorio" },
      { "id": "P1-PT-003", "muro": "P1-M-0004", "centro": [3.6, 2.4], "ancho": 1.8, "alto": 2.1, "hojas": 2, "desde": "P1-CIRC-01", "hacia": "P1-A002-01", "abre": "doble", "tipo": "batiente", "categoria": "deposito" },
      { "id": "P1-PT-004", "muro": "P1-M-0006", "centro": [7.2, 3.675], "ancho": 1.2, "alto": 2.1, "hojas": 1, "desde": "P1-CIRC-01", "hacia": "P1-A003-01", "abre": "adentro", "tipo": "cortafuego", "categoria": "evacuacion" }
    ],
    "ventanas": [ { "id": "P1-VN-001", "muro": "P1-M-0009", "centro": [1.8, 8.55], "ancho": 3.0, "antepecho": 1.0, "alto": 2.0 } ],
    "conexiones_verticales": [ { "id": "ESC", "tipo": "escalera", "pisos": [1, 2], "puntos": { "1": [8.4, 2.0], "2": [8.4, 2.0] } },
                               { "id": "ASC", "tipo": "ascensor", "pisos": [1, 2], "puntos": { "1": [8.4, 6.6], "2": [8.4, 6.6] } } ],
    "entradas_recorrido": [ { "id": "principal", "punto": [1.0, 3.675], "mirando_deg": 0, "nombre": "Corredor" } ],
    "obstaculos_recorrido": []
  },
  { "id": "P2", "piso": 2, "z": 4.5, "altura_entrepiso_m": 4.2, "altura_libre_m": 3.0, "...": "misma geometría que P1 con ids P2-… y filas 4 a 7" } ],
  "grupos_1633": {
    "consulta_externa": { "nombre": "Consulta externa", "color_hex": "(de normas.json → parametros_diseno.senalizacion_colores)", "cita": "Res. 1633 de 2025, Cuadros 2 y 3" },
    "atencion_inmediata": { "nombre": "Atención inmediata", "color_hex": "(ídem)", "cita": "Res. 1633 de 2025, Cuadros 2 y 3" },
    "circulacion": { "nombre": "Circulación", "color_hex": "(ídem)", "cita": "Res. 1633 de 2025, Cuadros 2 y 3" }
  }
}
```

### A.2 Fixtures de inventario y matriz (B)

Hay **dos formas** y cada una tiene su validador: la forma de datos (4.5), que se valida contra su propia dotación de prueba (I2 e I7 se comparan con `dotacion_min.json`, no con el `dotacion.json` del repositorio), y la forma web (10.2), que se valida con su esquema. Los ids usan servicios reales y el `h6` calculado (SHA-1 de `origen|servicio|tipo|nombre`, con `tipo` en su letra; cálculo propio): `dotacion|consulta_externa|m|Camilla de examen de prueba` → `2d1bfe`; `dotacion|urgencias|m|Carro de paro de prueba` → `a3f0fc`; `dotacion|urgencias|e|Desfibrilador de prueba` → `2cd8df`.

**`dotacion_min.json`** (forma de `dotacion.json`, recortada):

```json
{
  "id": "dotacion_min", "moneda_y_base": "Pesos constantes de 2026 (valores de prueba)",
  "servicios": [
    { "id": "consulta_externa", "equipos": [], "mobiliario": [ { "nombre": "Camilla de examen de prueba", "cantidad": 1, "precio_unitario_cop_2026": 1500000, "tipo_precio": "estimacion", "clase_riesgo": "I", "prioridad": "habilitacion", "fuente": "valor de prueba" } ],
      "totales": { "equipos_cop_2026": 0, "mobiliario_cop_2026": 1500000 } },
    { "id": "urgencias", "equipos": [ { "nombre": "Desfibrilador de prueba", "cantidad": 1, "precio_unitario_cop_2026": 29126266, "tipo_precio": "referencia_secop_ajustada_ipc", "clase_riesgo": "IIb", "prioridad": "habilitacion", "fuente": "valor de prueba" } ],
      "mobiliario": [ { "nombre": "Carro de paro de prueba", "cantidad": 1, "precio_unitario_cop_2026": 6000000, "tipo_precio": "estimacion", "clase_riesgo": "I", "prioridad": "habilitacion", "fuente": "valor de prueba" } ],
      "totales": { "equipos_cop_2026": 29126266, "mobiliario_cop_2026": 6000000 } }
  ]
}
```

**`inventario_min_datos.json`** (forma 4.5; se muestra una línea y una unidad completas, las otras dos con los mismos campos):

```json
{
  "id": "inventario_min_datos", "version": 2, "insumos_sha1": { "dotacion_min.json": "…", "plantas_min.json": "…" }, "sha256_dotacion": "…",
  "lineas": [
    { "id": "L-urgencias-e-2cd8df", "origen": "dotacion", "ref": { "servicio": "urgencias", "lista": "equipos", "idx": 0 }, "servicio": "urgencias", "tipo": "equipo",
      "nombre": "Desfibrilador de prueba", "cantidad": 1, "especificacion": "Bifásico, modo DEA y manual (prueba).", "modelo3d": "desfibrilador",
      "clase_riesgo": { "repo": "IIb", "vigente": "IIb", "estado": "coherente", "regla": null, "fuente": "valor de prueba" }, "clase_riesgo_revision": null,
      "es_dispositivo_medico": "si", "registro_invima": { "requerido": "si", "via": "evaluacion_tecnica", "usado_permitido": false }, "tecnologia_controlada": null,
      "componentes": [], "exigencias": [ { "id": "EX-URG-001", "exigible": "si", "verificacion_texto": "literal_compilacion" } ],
      "prioridad": "habilitacion", "prioridad_revisada": null, "norma_base": null, "justificacion_recomendado": null,
      "mantenimiento": { "anual_pct": 6, "vida_util_anios": 8, "preventivo": "según el manual del fabricante", "personal_inscrito_invima": true, "calibracion": true, "cita_inscripcion": "Decreto 4725, art. 39" },
      "precio_unitario_cop_2026": 29126266, "rango_precio_unitario_cop_2026": [26955531, 31297000], "tipo_precio": "referencia_secop_ajustada_ipc",
      "metodo_precio": "valor de prueba", "fuentes_precio": ["valor de prueba"], "nota_interna": null, "plantilla_contenido": null },
    { "id": "L-urgencias-m-a3f0fc", "...": "Carro de paro de prueba; modelo3d carro_paro; plantilla_contenido carro_paro_adulto_pediatrico" },
    { "id": "L-consulta_externa-m-2d1bfe", "...": "Camilla de examen de prueba; modelo3d camilla_examen" }
  ],
  "unidades": [
    { "id": "U-urgencias-2cd8df-001", "linea": "L-urgencias-e-2cd8df", "k": 1, "piso": 1, "recinto": "P1-A001-01", "ambiente": "Consultorio de prueba B",
      "posicion": [6.6, 7.9, 1.0], "rotacion_z": 3.1416, "montaje": "sobre", "apoyo": "U-urgencias-a3f0fc-001", "dentro_de": null, "compartimiento": null,
      "riesgo_sismico": { "anclaje": "sobre", "masa_kg": 7, "h_cg_m": 0.15, "mu": 0.4, "b_m": 0.135, "bx_m": 0.16, "by_m": 0.135 }, "contenido": null,
      "campos_al_comprar": { "marca": null, "modelo": null, "serie": null, "registro_sanitario": null, "vence_registro": null, "fecha_compra": null, "fecha_instalacion": null, "hoja_de_vida": null },
      "estado": "en_dotacion" },
    { "id": "U-urgencias-a3f0fc-001", "...": "carro de paro en P1-A001-01, posicion [6.6, 7.9, 0.0], montaje piso" },
    { "id": "U-consulta_externa-2d1bfe-001", "...": "camilla en P1-A000-01, posicion [1.8, 7.30, 0.0], rotacion_z 3.1416, montaje piso" }
  ],
  "totales": { "por_servicio": { "urgencias": { "unidades": 2, "equipos_cop_2026": 29126266, "mobiliario_cop_2026": 6000000, "coincide_con_dotacion": true },
                                 "consulta_externa": { "unidades": 1, "equipos_cop_2026": 0, "mobiliario_cop_2026": 1500000, "coincide_con_dotacion": true } } }
}
```

**`inventario_min.json`** (forma web del 10.2, completa):

```json
{
  "v": 2,
  "catalogo": {
    "camilla_examen": { "f": "camilla", "dim": [0.65, 1.85, 0.75], "b": 0.325, "mont": "piso", "anc": "apoyado", "masa": 40, "hcg": 0.45, "mu": 0.5, "cont": false, "comp": [] },
    "carro_paro": { "f": "carro", "dim": [0.75, 0.55, 1.0], "b": 0.275, "mont": "piso", "anc": "ruedas_con_freno", "masa": 70, "hcg": 0.5, "mu": 0.3, "cont": true, "comp": ["superficie", "cajón 1", "cajón 2", "cajón 3", "cajón 4", "cajón 5", "lateral"] },
    "desfibrilador": { "f": "equipo_mesa", "dim": [0.32, 0.27, 0.30], "b": 0.135, "mont": "sobre", "anc": "sobre", "masa": 7, "hcg": 0.15, "mu": 0.4, "cont": false, "comp": [] }
  },
  "lineas": [
    { "id": "L-consulta_externa-m-2d1bfe", "nombre": "Camilla de examen de prueba", "servicio": "consulta_externa", "tipo": "mobiliario", "cantidad": 1, "modelo3d": "camilla_examen",
      "clase": { "vigente": "I", "estado": "coherente", "revision": null }, "registro": { "requerido": "si", "via": "automatico", "usado_permitido": true },
      "exigencias": [], "prioridad": "habilitacion", "prioridad_revisada": null, "norma_base": null,
      "mantenimiento": { "anual_pct": 3, "vida_util_anios": 10, "personal_inscrito_invima": false, "calibracion": false }, "componentes": [], "plantilla": null,
      "precio": 1500000, "rango": [1200000, 1800000], "tipo_precio": "estimacion", "fuentes_precio": ["valor de prueba"], "metodo_precio": "valor de prueba" },
    { "id": "L-urgencias-m-a3f0fc", "nombre": "Carro de paro de prueba", "servicio": "urgencias", "tipo": "mobiliario", "cantidad": 1, "modelo3d": "carro_paro",
      "clase": { "vigente": "I", "estado": "coherente", "revision": null }, "registro": { "requerido": "si", "via": "automatico", "usado_permitido": true },
      "exigencias": [ { "id": "EX-URG-002", "exigible": "por_confirmar" } ], "prioridad": "habilitacion", "prioridad_revisada": null, "norma_base": null,
      "mantenimiento": { "anual_pct": 3, "vida_util_anios": 10, "personal_inscrito_invima": false, "calibracion": false }, "componentes": [], "plantilla": "carro_paro_adulto_pediatrico",
      "precio": 6000000, "rango": [5000000, 7000000], "tipo_precio": "estimacion", "fuentes_precio": ["valor de prueba"], "metodo_precio": "valor de prueba" },
    { "id": "L-urgencias-e-2cd8df", "nombre": "Desfibrilador de prueba", "servicio": "urgencias", "tipo": "equipo", "cantidad": 1, "modelo3d": "desfibrilador",
      "clase": { "vigente": "IIb", "estado": "coherente", "revision": null }, "registro": { "requerido": "si", "via": "evaluacion_tecnica", "usado_permitido": false },
      "exigencias": [ { "id": "EX-URG-001", "exigible": "si" } ], "prioridad": "habilitacion", "prioridad_revisada": null, "norma_base": null,
      "mantenimiento": { "anual_pct": 6, "vida_util_anios": 8, "personal_inscrito_invima": true, "calibracion": true }, "componentes": [], "plantilla": null,
      "precio": 29126266, "rango": [26955531, 31297000], "tipo_precio": "referencia_secop_ajustada_ipc", "fuentes_precio": ["valor de prueba"], "metodo_precio": "valor de prueba" }
  ],
  "columnas_unidades": ["id", "linea_idx", "piso", "recinto", "x", "y", "z", "rot_z", "apoyo_idx", "dentro_de_idx", "componente_de_idx", "montaje", "estado"],
  "unidades": [
    ["U-consulta_externa-2d1bfe-001", 0, 1, "P1-A000-01", 1.8, 7.30, 0.0, 3.1416, -1, -1, -1, "piso", "en_dotacion"],
    ["U-urgencias-a3f0fc-001", 1, 1, "P1-A001-01", 6.6, 7.9, 0.0, 3.1416, -1, -1, -1, "piso", "en_dotacion"],
    ["U-urgencias-2cd8df-001", 2, 1, "P1-A001-01", 6.6, 7.9, 1.0, 3.1416, 1, -1, -1, "sobre", "en_dotacion"]
  ],
  "implementos": { "carro_paro_adulto_pediatrico": [ { "n": "Tabla de reanimación", "c": 1, "comp": "lateral", "tipo": "dispositivo", "verif": "dato del repositorio" } ] },
  "recintos": { "P1-A000-01": { "estado": { "corte_2026": "cumple", "apertura": "cumple" }, "exig": [], "por_confirmar": 0 },
                "P1-A001-01": { "estado": { "corte_2026": "cumple", "apertura": "cumple" }, "exig": ["EX-URG-001"], "por_confirmar": 1 } },
  "totales": {}
}
```

**`habilitacion_min.json`** (forma 4.8): un servicio (`urgencias`) con dos exigencias, `EX-URG-001` (`exigible: "si"`, `cumple`) y `EX-URG-002` (`exigible: "por_confirmar"`, `falta`, que no cambia el color del recinto), un servicio `sala_expansion` con `habilitable: "no"`, el bloque `todos_los_servicios` con una fila, los dos cortes de `fecha_referencia`, `estandares_no_evaluados` y `texto_alcance`. Sirve para la tarjeta de C en la ola 1.

### A.3 `estructura_min.json` (A) — edificio de 2 pisos y 1 vano en cada dirección (5,0 × 5,0 m; entrepisos de 3,0 m)

Valores **de prueba**, no de diseño. Se muestra el pórtico `X-1` completo; `X-2` (y = 5,0), `Y-A` (x = 0) y `Y-B` (x = 5,0) son iguales con ids análogos (`Y-A/10`, `C-A1-1@Y`, `VY-A-12-1`…). `theta_y` es la nominal del esquema (`My·L_f/(6·EI_fis)`; `validar_resultado.mjs` la comprueba ± 1 %) y `theta_y_e` la de las propiedades esperadas que usa la simulación (E16). Para el fixture de resultados (A.4), A agrega un resorte de mampostería `aislado: false` en el nivel 1 de `X-1`.

```json
{
  "id": "estructura_min", "nombre": "Cubo de prueba de 2 pisos", "tipo_dato": "estimacion",
  "sistema_estructural": "pórticos de concreto (prueba)", "norma": "valores de prueba",
  "materiales": { "concreto_28": { "tipo": "concreto", "fc_MPa": 28, "Ec_MPa": 24870, "nu": 0.2, "peso_kN_m3": 24, "fuente": "NSR-10 C.8.5.1: Ec = 4700√f'c" } },
  "secciones": {
    "C40": { "tipo": "rectangular", "b": 0.40, "h": 0.40, "material": "concreto_28", "A": 0.16, "I": 0.0021333, "Av": 0.13333, "factor_fisuracion": 0.70,
             "P_gravedad_kN": 98.1, "My_kNm": 120, "Mn_kNm": 135, "phiMn_kNm": 120, "Mpr_kNm": 165, "theta_y": 0.0016, "theta_p_cap": 0.03, "theta_p_b": 0.05,
             "My_e_kNm": 150, "Mn_e_kNm": 165, "Vn_e_kN": 340, "theta_y_e": 0.0020, "theta_p_IO": 0.005, "theta_p_LS": 0.015, "theta_p_CP": 0.02,
             "Vn_kN": 300, "phiVn_kN": 225, "endurecimiento": 0.03, "histeresis": "bilineal",
             "calculo": "valores de prueba; theta_y = My·L_f/(6·EI_fis) = 120·3,0/(6·24.870.000·0,0021333·0,70) = 0,0016 rad; theta_y_e con My_e" },
    "V30x50": { "tipo": "rectangular", "b": 0.30, "h": 0.50, "material": "concreto_28", "A": 0.15, "I": 0.003125, "Av": 0.125, "factor_fisuracion": 0.35,
                "My_kNm": 140, "My_pos_kNm": 110, "My_neg_kNm": 140, "Mn_kNm": 155, "phiMn_kNm": 140, "Mpr_kNm": 190, "theta_y": 0.0039, "theta_p_cap": 0.025, "theta_p_b": 0.05,
                "My_e_kNm": 175, "My_e_pos_kNm": 138, "My_e_neg_kNm": 175, "Mn_e_kNm": 190, "Vn_e_kN": 300, "theta_y_e": 0.0049, "theta_p_IO": 0.01, "theta_p_LS": 0.02, "theta_p_CP": 0.025,
                "Vn_kN": 260, "phiVn_kN": 195, "endurecimiento": 0.03, "histeresis": "bilineal",
                "calculo": "valores de prueba; theta_y = My·L_f/(6·EI_fis) con L_f = 5,0 − 0,2 − 0,2 = 4,6 m: 140·4,6/(6·24.870.000·0,003125·0,35) = 0,0039 rad" }
  },
  "ejes": { "x": [ { "id": "A", "x": 0.0 }, { "id": "B", "x": 5.0 } ], "y": [ { "id": "1", "y": 0.0 }, { "id": "2", "y": 5.0 } ] },
  "bloques": [ {
    "id": "cubo",
    "niveles": [
      { "id": "N1", "z": 3.0, "altura_entrepiso": 3.0, "masa_t": 20.0, "Jz_t_m2": 83.33, "cm": [2.5, 2.5], "contorno": [[0, 0], [5, 0], [5, 5], [0, 5]], "peso_sismico_kN": 196.13, "P_sobre_entrepiso_kN": 392.27 },
      { "id": "N2", "z": 6.0, "altura_entrepiso": 3.0, "masa_t": 20.0, "Jz_t_m2": 83.33, "cm": [2.5, 2.5], "contorno": [[0, 0], [5, 0], [5, 5], [0, 5]], "peso_sismico_kN": 196.13, "P_sobre_entrepiso_kN": 196.13 }
    ],
    "porticos": [ {
      "id": "X-1", "direccion": "x", "coordenada": 0.0,
      "nodos": [ { "id": "X-1/A0", "s": 0.0, "nivel": 0 }, { "id": "X-1/B0", "s": 5.0, "nivel": 0 }, { "id": "X-1/A1", "s": 0.0, "nivel": 1 }, { "id": "X-1/B1", "s": 5.0, "nivel": 1 }, { "id": "X-1/A2", "s": 0.0, "nivel": 2 }, { "id": "X-1/B2", "s": 5.0, "nivel": 2 } ],
      "apoyos": { "X-1/A0": "empotrado", "X-1/B0": "empotrado" },
      "elementos": [
        { "id": "C-A1-1@X", "fisico": "C-A1-1", "tipo": "columna", "i": "X-1/A0", "j": "X-1/A1", "seccion": "C40", "eje": "A-1", "nivel": 1 },
        { "id": "C-B1-1@X", "fisico": "C-B1-1", "tipo": "columna", "i": "X-1/B0", "j": "X-1/B1", "seccion": "C40", "eje": "B-1", "nivel": 1 },
        { "id": "C-A1-2@X", "fisico": "C-A1-2", "tipo": "columna", "i": "X-1/A1", "j": "X-1/A2", "seccion": "C40", "eje": "A-1", "nivel": 2 },
        { "id": "C-B1-2@X", "fisico": "C-B1-2", "tipo": "columna", "i": "X-1/B1", "j": "X-1/B2", "seccion": "C40", "eje": "B-1", "nivel": 2 },
        { "id": "VX-1-AB-1", "tipo": "viga", "i": "X-1/A1", "j": "X-1/B1", "seccion": "V30x50", "eje": "1 entre A y B", "nivel": 1, "w_gravedad_kN_m": 6.0, "brazo_rigido_m": [0.2, 0.2] },
        { "id": "VX-1-AB-2", "tipo": "viga", "i": "X-1/A2", "j": "X-1/B2", "seccion": "V30x50", "eje": "1 entre A y B", "nivel": 2, "w_gravedad_kN_m": 6.0, "brazo_rigido_m": [0.2, 0.2] }
      ]
    } ],
    "resortes": []
  } ],
  "amortiguamiento": { "tipo": "rayleigh", "xi": 0.05, "periodos_ancla_s": null, "rigidez": "inicial_parte_elastica" },
  "p_delta": true,
  "limites": { "deriva": 0.01, "deriva_umbral_dano": 0.004, "deriva_umbral_dano_mamposteria": 0.002, "tipo_deriva": "vectorial en los vértices del contorno", "fuente": "NSR-10 A.6.3.1, A.6.4.1 y Tabla A.12.5-1" },
  "diseno": { "Aa": 0.15, "Av": 0.15, "suelo": "D", "Fa": 1.5, "Fv": 2.2, "I": 1.5, "Ta_s": 0.3, "Sa_g": 0.844, "R": 7, "Vs_kN": 0 },
  "fuentes": [], "supuestos": ["Valores de prueba"], "incertidumbres": []
}
```

### A.4 `resultado_min.json` y `serie_elemento_min.json` (A) — calculados sobre `estructura_min.json`

El fixture de resultados corresponde **al mismo modelo** del A.3, para que D pueda dibujar la deformada desde la ola 1: los `elementos` y `nodos` que llegan en `listo` son los de `estructura_min.json` (4 pórticos con 6 nodos y 6 elementos cada uno). Tamaños: `nt = 3` (0; 0,02; 0,04 s), `N = 2`, `nE = 24`, `nN = 24`, `nP = 4`. En la ola 0, A lo calcula con un cálculo de referencia (Python o a mano) que respete tamaños, unidades e ids; en la ola 2 lo regenera con el motor y lo vuelve a pasar por `validar_resultado.mjs`. Para que sirva de prueba, el escenario está escalado de modo que haya **al menos una rótula que fluye** (bits 1 o 2 en `rotulas`, `thp` con datos y `t_primera_fluencia ≥ 0`), **un equipo que desliza** (`regimen: "desliza"`), **un muro de mampostería con daño** (A agrega al A.3 un resorte `aislado: false` en el nivel 1 del pórtico `X-1` para este fin) y todas las envolventes del 7.6.

Forma (los campos escritos como texto dicen el tamaño y el contenido que trae el archivo real; los demás se muestran completos):

```json
{
  "version": 1, "id": "prueba", "duracion_calculo_ms": 1,
  "params": { "Mw": 6.2, "profundidad_km": 150, "distancia_epicentral_km": 92, "vs30_m_s": 270, "semilla": 2028 },
  "opciones": { "dt_s": 0.005, "dt_salida_s": 0.02, "calidad": "normal", "angulo_deg": 0, "escala": 25 },
  "factor_escala": null, "iteraciones_escala": 0,
  "amortiguamiento": { "a0": 0.0, "a1": 0.0, "periodos_ancla_s": [0.0, 0.0], "xi_modos": "Float32 (12) calculados" },
  "t": [0.0, 0.02, 0.04],
  "ag": [0.0, 0.0, 2.10, -1.05, 2.60, -1.30],
  "u": "Float32 nt·N·3 = 18",
  "a_abs": "Float32 nt·N·3 = 18",
  "giros": "Float32 nt·nN = 72", "v_nodos": "Float32 nt·nN = 72",
  "dc": "Uint8 nt·nE = 72 (cociente × 100)", "dc_flexion": "ídem", "dc_cortante": "ídem", "dc_rotacion": "ídem",
  "rotulas": "Uint8 nt·nE = 72; al menos un 1 o un 2 en el último paso",
  "thp": { "elementos": "Int32 (k ≥ 1)", "valores": "Int16 nt·k·2, en 10⁻⁵ rad" },
  "derivas": "Float32 nt·N·2 = 12", "derivas_vector": "Float32 nt·N = 6", "derivas_porticos_env": "Float32 nP·N = 8",
  "cortante_basal": "Float32 nt·3 = 9",
  "energia": "Float32 nt·6 = 18: entrada, cinética, elástica, amortiguada, histerética, trabajo_PDelta",
  "envolventes": { "u_max": "N·3", "deriva_max": "N·2", "t_deriva_max": "N·2", "deriva_vector_max": "N", "punto_deriva_vector": "N·2", "t_deriva_vector_max": "N",
                   "a_abs_max": "N·3", "dc_max": "nE, cociente (0,12 = 12 %)", "t_dc_max": "nE", "gobierna": "nE", "Mi_max": "nE", "Mj_max": "nE", "V_max": "nE",
                   "N_min": "nE", "N_max": "nE", "thp_max": "nE·2", "t_primera_fluencia": "nE·2" },
  "muros_mamposteria": [ { "id": "M-X1-1", "aislado": false, "deriva_max": 0.0015, "estado": "leve" } ],
  "equipos": [ { "unidad": "U-consulta_externa-2d1bfe-001", "anclaje": "apoyado", "regimen": "desliza", "a_max_m_s2": 6.0, "desliza": true, "deslizamiento_max_m": 0.004, "deslizamiento_final_m": 0.004, "inicia_balanceo": false, "razon_vuelco": 0.84, "fuerza_anclaje_kN": null } ],
  "calidad_numerica": { "pasos": 8, "iteraciones_promedio": 2, "subdivisiones": 0, "no_convergidos": 0, "error_energia_max": 0.0, "error_deformacion_max": 0.0, "indice_estabilidad_max": 0.0 }
}
```

`serie_elemento_min.json`: la respuesta del 7.5 para `C-A1-1@X` (`{ "tipo": "serie_elemento", "id": "prueba", "elemento": "C-A1-1@X", "t": [3], "Mi": [3], "Mj": [3], "V": [3], "N": [3], "thp_i": [3], "thp_j": [3], "dc": [3] }`, con valores coherentes con `resultado_min.json`). `trabajador_simulado.js` responde `cargado`, `listo` (con el resumen de `estructura_min.json`), `movimiento`, `resultado` y `serie_elemento` con estos archivos.

---

## Anexo B · Servicios: programa, dotación y señalización

| Servicio en `programa.json` | Servicios de `dotacion.json` que ubican unidades allí | Grupo de color (Res. 1633) |
|---|---|---|
| Vestíbulo y admisiones | `tic_apoyo` (tándems, sillas de ruedas, digiturno, computadores) | direccion_y_administracion |
| Urgencias | `urgencias`, `tic_apoyo` | atencion_inmediata |
| Imágenes diagnósticas ionizantes (rayos X) / no ionizantes (ecografía) | `imagenes` (en la matriz se parte en 744 y 745, 4.8), `tic_apoyo` | apoyo_diagnostico_y_terapeutico |
| Toma de muestras de laboratorio clínico | `toma_muestras` | apoyo_diagnostico_y_terapeutico |
| Consulta externa (piso 2) y consulta del piso 4 | `consulta_externa`, `telemedicina` (consultorio de telemedicina), `tic_apoyo` | consulta_externa |
| Toma de muestras de cuello uterino y ginecológicas | `consulta_externa` (camilla ginecológica) | consulta_externa |
| Laboratorio clínico | `laboratorio`, comodato de `laboratorio.json` | apoyo_diagnostico_y_terapeutico |
| Vacunación | `vacunacion` | consulta_externa |
| Servicio farmacéutico | `farmacia` | apoyo_diagnostico_y_terapeutico |
| Hospitalización | `hospitalizacion` | internacion |
| Atención del parto (TPR) | `partos` | atencion_inmediata |
| Esterilización | `esterilizacion` | quirurgico_y_esterilizacion |
| Odontología y radiología odontológica | `odontologia` | consulta_externa |
| Terapias | `terapias` | apoyo_diagnostico_y_terapeutico |
| Zona de expansión, telesalud y coordinación | `expansion_emergencias`, `tic_apoyo` | atencion_inmediata (salón) / direccion_y_administracion (oficinas) |
| Apoyo y áreas técnicas de cada piso | `tic_apoyo` (residuos, rack), equipamiento fijo (UPS central, tableros) | apoyo_y_servicios_generales |
| Circulación vertical y ductos | equipamiento fijo (ascensores, montacargas) | circulacion |
| Áreas técnicas y de servicio (bloque técnico) | equipamiento fijo (planta, gases, bombas, nevera mortuoria) | apoyo_y_servicios_generales |

El mapeo exacto por recinto lo fija `reglas_ubicacion.json`, y la traducción de servicios de las investigaciones a servicios del programa, la tabla cerrada `reglas_exigencias.json → servicio_a_programa` (4.2); esta tabla es orientativa.

## Anexo C · Lista cerrada de `modelo3d`

Dimensiones nominales `[ancho, fondo, alto]` en m y masa en kg: **estimación** (fichas típicas; se reemplazan con la ficha del equipo comprado). `anclaje` por defecto para el riesgo sísmico.

| Familia | `modelo3d` | dim (m) | anclaje | masa | Líneas típicas |
|---|---|---|---|---|---|
| cama | `cama_hospitalaria` | 1,00 × 2,20 × 0,95 | ruedas_con_freno | 150 | Cama eléctrica de 3 funciones |
| cama | `cama_pediatrica` | 0,90 × 1,80 × 1,10 | ruedas_con_freno | 110 | |
| cama | `cuna_hospitalaria` | 0,70 × 1,30 × 1,10 | ruedas_con_freno | 60 | |
| cama | `cuna_acrilico` | 0,50 × 0,85 × 0,95 | ruedas_sin_freno | 25 | Cuna de acrílico |
| cama | `cuna_observacion` | 0,65 × 1,20 × 1,00 | ruedas_con_freno | 35 | |
| cama | `cama_partos` | 0,95 × 2,10 × 1,00 | ruedas_con_freno | 200 | Cama TPR multiposición |
| camilla | `camilla_reanimacion` | 0,75 × 2,05 × 0,95 | ruedas_con_freno | 120 | |
| camilla | `camilla_observacion` | 0,75 × 2,00 × 0,90 | ruedas_con_freno | 110 | |
| camilla | `camilla_transporte` | 0,70 × 2,00 × 0,95 | ruedas_con_freno | 90 | |
| camilla | `camilla_procedimientos` | 0,70 × 1,95 × 0,85 | ruedas_con_freno | 100 | Procedimientos, yesos |
| camilla | `camilla_eda` | 0,70 × 1,90 × 0,80 | apoyado | 60 | |
| camilla | `camilla_examen` | 0,65 × 1,85 × 0,75 | apoyado | 40 | Camilla fija con portarrollo |
| camilla | `camilla_ginecologica` | 0,65 × 1,85 × 0,85 | apoyado | 60 | Con estribos |
| camilla | `camilla_ecografia` | 0,70 × 1,90 × 0,70 | apoyado | 70 | |
| camilla | `camilla_terapia` | 0,70 × 1,90 × 0,70 | apoyado | 45 | Dos cuerpos |
| camilla | `camilla_plegable` | 0,60 × 1,90 × 0,60 (plegada 0,60 × 0,20 × 1,90) | apoyado | 15 | Sala de expansión |
| asiento | `sillon_reclinable` | 0,75 × 0,95 × 1,10 | apoyado | 45 | ERA, transición, acompañante |
| asiento | `sillon_toma_muestras` | 0,70 × 0,90 × 1,20 | apoyado | 35 | |
| asiento | `silla_ruedas` | 0,65 × 1,05 × 0,90 | ruedas_sin_freno | 18 | |
| asiento | `tandem_4` | 2,30 × 0,65 × 0,80 | apoyado | 40 | |
| asiento | `silla_trabajo` | 0,60 × 0,60 × 0,95 | ruedas_sin_freno | 12 | |
| asiento | `silla_laboratorio` | 0,50 × 0,50 × 0,95 | ruedas_sin_freno | 10 | |
| mueble | `puesto_trabajo` | 1,20 × 1,60 × 0,75 (escritorio + 3 sillas) | apoyado | 60 | |
| mueble | `escritorio` | 1,20 × 0,60 × 0,75 | apoyado | 35 | Control de rayos X, oficinas |
| mueble | `mueble_recepcion` | 3,00 × 0,80 × 1,10 | apoyado | 150 | Admisión, SIAU, dispensación |
| mueble | `estacion_enfermeria` | 3,00 × 1,60 × 1,10 | apoyado | 200 | |
| mueble | `meson` | 1,50 × 0,70 × 0,90 (variantes: poceta, inoxidable, gavetas, laboratorio) | anclado | 80 | |
| mueble | `mueble_bajo` | 1,20 × 0,60 × 0,90 | apoyado | 50 | Trabajo limpio y sucio, descontaminación |
| mueble | `vitrina` | 0,90 × 0,40 × 1,80 | apoyado | 70 | Instrumental |
| mueble | `estanteria` | 1,00 × 0,45 × 2,00 (variante inoxidable) | apoyado | 40 | Farmacia, reactivos, estéril |
| mueble | `lockers_6` | 0,90 × 0,50 × 1,80 | apoyado | 60 | |
| mueble | `gabinete_seguridad` | 0,60 × 0,50 × 1,20 | anclado | 80 | Control especial |
| mueble | `mesa_noche` | 0,45 × 0,45 × 0,80 | ruedas_sin_freno | 20 | |
| mueble | `mesa_puente` | 0,90 × 0,45 × 0,95 | ruedas_sin_freno | 15 | |
| mueble | `mesa_mayo` | 0,50 × 0,35 × 1,10 | ruedas_sin_freno | 10 | |
| mueble | `mesa_auxiliar` | 0,60 × 0,45 × 0,85 | ruedas_sin_freno | 15 | |
| mueble | `riel_cortina` | largo × 0,05 × 2,20 (colgado del cielo) | cielo | 5 | Cortina antifluido, biombo |
| mueble | `escalerilla` | 0,40 × 0,50 × 0,45 | apoyado | 6 | |
| mueble | `estiba` | 1,20 × 1,00 × 0,15 | apoyado | 15 | |
| mueble | `canecas_residuos` | 0,95 × 0,35 × 0,65 | apoyado | 12 | 3 canecas + guardián (contenedor) |
| mueble | `lavaojos_ducha` | 0,60 × 0,60 × 2,20 | anclado | 30 | |
| terapia | `barras_paralelas` | 0,80 × 3,00 × 1,00 | anclado | 80 | |
| terapia | `escalera_rehabilitacion` | 0,90 × 2,40 × 1,40 | apoyado | 90 | |
| terapia | `banda_caminadora` | 0,80 × 2,00 × 1,40 | apoyado | 120 | |
| terapia | `bicicleta_estatica` | 0,55 × 1,10 × 1,30 | apoyado | 45 | |
| terapia | `espejo_postural` | 0,90 × 0,40 × 1,90 | ruedas_sin_freno | 25 | |
| terapia | `kit_rehabilitacion` | 1,00 × 0,40 × 1,00 | apoyado | 30 | Contenedor |
| terapia | `compresero` | 0,60 × 0,45 × 0,90 | apoyado | 45 | |
| carro | `carro_paro` | 0,75 × 0,55 × 1,00 | ruedas_con_freno | 70 | Contenedor (cajones) |
| carro | `carro_curaciones` | 0,60 × 0,45 × 0,90 | ruedas_sin_freno | 25 | |
| carro | `carro_medicamentos` | 0,70 × 0,50 × 1,00 | ruedas_con_freno | 45 | Contenedor; unidosis |
| carro | `carro_ropa` | 0,80 × 0,50 × 1,00 | ruedas_sin_freno | 20 | |
| carro | `carro_cerrado` | 0,90 × 0,60 × 1,20 | ruedas_con_freno | 50 | Material estéril y contaminado |
| carro | `carro_equipo` | 0,50 × 0,50 × 0,90 | ruedas_sin_freno | 15 | Base de ECG, monitor fetal, electroterapia |
| carro | `atril` | 0,55 × 0,55 × 2,00 | ruedas_sin_freno | 6 | |
| biomédico | `desfibrilador` | 0,32 × 0,27 × 0,30 | sobre | 7 | |
| biomédico | `dea_gabinete` | 0,40 × 0,20 × 0,45 | pared | 5 | |
| biomédico | `monitor_signos` | 0,30 × 0,18 × 0,30 (+ brazo de pared o pedestal 0,60 × 0,60 × 1,40) | pared / ruedas_sin_freno | 6 | Multiparámetro, básico |
| biomédico | `electrocardiografo` | 0,40 × 0,35 × 0,12 | sobre | 5 | |
| biomédico | `bomba_infusion` | 0,15 × 0,22 × 0,25 | dentro (atril) | 2,5 | |
| biomédico | `ventilador_transporte` | 0,30 × 0,20 × 0,30 | sobre | 5 | |
| biomédico | `aspirador_portatil` | 0,35 × 0,25 × 0,35 | sobre | 7 | |
| biomédico | `toma_gases_pared` | 0,10 × 0,10 × 0,25 | pared | 1 | Flujómetro de O₂, regulador de vacío |
| biomédico | `equipo_mesa` | 0,30 × 0,25 × 0,15 (paramétrico) | sobre | 3 | Oxímetro, nebulizador, glucómetro, Doppler, extractor, electrobisturí, lector POCT, CPAP, termoablación, selladora, lavadora ultrasónica, baño serológico, balanza, incubadora de indicadores, estabilizador |
| biomédico | `estuche` | 0,40 × 0,25 × 0,10 (paramétrico) | dentro | 2 | Instrumental, laringoscopio, resucitador, sujeción, traje antichoque, periféricos |
| biomédico | `tabla_espinal` | 0,45 × 1,85 × 0,06 | apoyado | 8 | Inmovilización |
| biomédico | `equipo_pared` | 0,35 × 0,10 × 0,25 (paramétrico) | pared | 3 | Órganos de los sentidos, tensiómetro de pared, termohigrómetro |
| biomédico | `lampara_rodable` | 0,60 × 0,60 × 1,80 | ruedas_sin_freno | 15 | Lámpara de procedimientos |
| biomédico | `lampara_cuello_cisne` | 0,50 × 0,50 × 1,40 | apoyado | 5 | |
| biomédico | `lampara_cielitica` | Ø 0,70, brazo 1,00 | cielo | 40 | Lámpara de techo de partos |
| biomédico | `bascula_pesabebes` | 0,55 × 0,35 × 0,15 | sobre | 5 | |
| biomédico | `bascula_piso` | 0,35 × 0,35 × 0,05 | apoyado | 2 | Componente del kit de examen |
| biomédico | `infantometro` | 0,30 × 1,00 × 0,15 | sobre | 3 | |
| neonatal | `servocuna` | 1,00 × 0,75 × 1,80 | ruedas_con_freno | 90 | Calor radiante |
| neonatal | `incubadora_neonatal` | 1,10 × 0,65 × 1,45 | ruedas_con_freno | 80 | |
| neonatal | `incubadora_transporte` | 1,30 × 0,60 × 1,30 | ruedas_con_freno | 60 | |
| neonatal | `fototerapia` | 0,60 × 0,60 × 1,70 | ruedas_sin_freno | 20 | |
| neonatal | `monitor_fetal` | 0,35 × 0,30 × 0,15 | sobre | 5 | |
| odontología | `unidad_odontologica` | 1,80 × 2,20 × 1,90 | anclado | 250 | Sillón, lámpara, módulo, escupidera, taburete; piezas de mano `sobre` |
| odontología | `compresor` | 0,55 × 0,45 × 0,65 | apoyado | 40 | |
| odontología | `rx_periapical` | 0,40 × 0,30 × 0,60 + brazo 1,50 | pared | 25 | |
| imágenes | `rayos_x_convencional` | huella 4,00 × 3,00 (mesa con bucky 2,20 × 0,80 × 0,75; columna portatubo; bucky mural 0,60 × 0,45 × 1,90) | anclado | 600 | Pieza compuesta con `posiciones_fijas` |
| imágenes | `ecografo` | 0,55 × 0,85 × 1,45 | ruedas_con_freno | 80 | |
| imágenes | `proteccion_radiologica` | perchero 0,60 × 0,30 × 1,60 (+ biombo plomado 0,80 × 0,50 × 1,90) | pared | 25 / 90 | |
| TIC | `monitor_escritorio` | 0,55 × 0,20 × 0,45 | sobre | 7 | DICOM, grado médico |
| TIC | `computador_aio` | 0,55 × 0,20 × 0,45 | sobre | 7 | |
| TIC | `estacion_telemedicina` | 1,20 × 0,60 × 1,30 | apoyado | 40 | |
| TIC | `impresora` | 0,40 × 0,40 × 0,30 | sobre | 10 | Láser, etiquetas, térmica |
| TIC | `rack` | 0,60 × 1,00 × 2,00 | anclado | 300 | PACS, red de datos |
| TIC | `digiturno` | pantalla 1,10 × 0,10 × 0,65 + kiosco 0,50 × 0,50 × 1,40 | pared | 30 | |
| laboratorio | `microscopio` | 0,25 × 0,35 × 0,45 | sobre | 8 | |
| laboratorio | `cabina_bioseguridad` | 1,35 × 0,80 × 2,10 | anclado | 250 | Clase II A2 de 4 pies |
| laboratorio | `centrifuga_mesa` | 0,45 × 0,55 × 0,35 (variante micro 0,30 × 0,35 × 0,25) | sobre | 30 | |
| laboratorio | `analizador_mesa` | 0,60 × 0,60 × 0,60 (paramétrico) | sobre | 40-90 | Hematología, inmunoensayo, HbA1c, orina, coagulómetro, gases, GeneXpert |
| laboratorio | `analizador_piso` | 1,20 × 0,80 × 1,20 (paramétrico) | apoyado | 200 | Química automatizada, hemocultivos |
| laboratorio | `incubadora_lab` | 0,60 × 0,60 × 0,80 | apoyado | 40 | |
| laboratorio | `ups` | 0,25 × 0,70 × 0,50 | apoyado | 60 | |
| frío | `nevera_vertical` | 0,70 × 0,75 × 1,95 | apoyado | 110 | Reactivos, farmacia 400-700 L |
| frío | `nevera_media` | 0,60 × 0,65 × 1,40 | apoyado | 70 | Farmacia 150-250 L |
| frío | `nevera_bajo_meson` | 0,60 × 0,60 × 0,85 | apoyado | 45 | Muestras, leche materna, depósito de partos |
| frío | `congelador_horizontal` | 0,90 × 0,65 × 0,85 | apoyado | 50 | |
| frío | `refrigerador_vacunas` | 1,00 × 0,75 × 0,95 | apoyado | 90 | PQS E003 |
| frío | `termo_vacunas` | 0,35 × 0,25 × 0,35 | sobre | 3 | |
| frío | `caja_termica` | 0,60 × 0,45 × 0,45 | apoyado | 8 | |
| esterilización | `autoclave_mesa` | 0,45 × 0,60 × 0,40 | sobre | 45 | Clase B de 23 L |
| esterilización | `autoclave_vertical` | 0,60 × 0,60 × 1,00 | apoyado | 90 | Laboratorio |
| esterilización | `autoclave_central` | 1,00 × 1,40 × 1,90 (doble puerta en muro) | anclado | 600 | `posiciones_fijas` |
| esterilización | `lavadora_desinfectora` | 0,65 × 0,75 × 1,85 | apoyado | 200 | |
| fijo | `planta_electrica` | 3,80 × 1,40 × 2,00 | anclado | 3.000 | Bloque técnico |
| fijo | `ups_central` | 1,20 × 0,90 × 2,00 | anclado | 800 | |
| fijo | `ascensor_cabina` | 1,40 × 2,40 × 2,30 | en_nucleo | — | |
| fijo | `montacargas` | 0,80 × 0,80 × 1,00 | en_nucleo | — | |
| fijo | `manifold_gases` | 2,50 × 0,50 × 1,80 | anclado | 300 | |
| fijo | `generador_psa` | 2,00 × 1,50 × 2,00 | anclado | 1.500 | |
| fijo | `equipo_presion` | 1,50 × 1,00 × 1,20 | anclado | 400 | |
| fijo | `tablero_sistema` | 0,60 × 0,25 × 0,80 | pared | 30 | Llamado de enfermería, incendio, CCTV (sistemas distribuidos: marcador en su cuarto técnico) |
| fijo | `condensadora` | 1,00 × 0,80 × 1,40 | anclado | 200 | Cubierta (sin planta en esta iteración) |
| fijo | `nevera_mortuoria` | 2,30 × 1,00 × 1,60 | anclado | 300 | |

Si una línea no encaja en ningún modelo, B lo pide a C y se agrega aquí antes de usarlo (`equipos3d.js` lanza error con un modelo desconocido).

---

## Decisiones de la revisión

La versión 2 aplica las 81 observaciones de la revisión (22 de física, 27 de normativa y 32 de integración). Antes de aplicarlas se verificaron contra el repositorio y contra cálculo propio: sumas de `laboratorio.json` (11 líneas y 12 unidades por $1.249.676.210; 9 líneas y 10 unidades en comodato por $955.708.589; GeneXpert $143.967.621; antibiograma $150.000.000), conteos de las investigaciones (61 de 199 filas de guía secundaria o paráfrasis; 22 filas con `texto_literal: null`; 22 de 40 filas del contraste «Sin ambiente equivalente», con 9/4/4/1 en las 18 restantes), `normas.json` (umbral de daño de 0,40 % y 0,20 %), `dotacion.json` (partos, equipos[10] de 21; `numero_de_items` 28; 199 + 37 = 236), nombres repetidos de `programa.json`, el código de three 0.160 (`OrbitControls.update()` no mira `enabled`; `Raycaster` no mira `visible`; `mergeGeometries` devuelve `null` con índices mezclados; `setPositions()` crea un búfer nuevo), las líneas citadas de `core.js`, `torre.js`, `main.js` e `index.html`, y las fórmulas (alargamiento del período de Newmark, ξ de Rayleigh con ω3 = 1,3·ω1, `Ta` con las dos filas de la Tabla A.4.2-1, `θy` de los fixtures, lazo de T7). **Ninguna observación se rechazó por completo.** Estas se aplicaron con un ajuste, por la razón que se da:

1. **Balance de energía (física).** Se aplicó el control `E_deformación = ∫(F_r + F_PΔ)ᵀ du_m` desde el estado de gravedad y el `trabajo_PDelta` aparte (energía en `nt·6`), pero **no** `E_elás = ½(u − u_g)ᵀK̂_el(u − u_g) + ½uᵀK_PΔu`: esa expresión solo vale mientras nada fluye (con desplazamiento permanente atribuiría energía elástica a la deformación plástica). La energía elástica se calcula por elemento respecto al estado de gravedad, menos el trabajo de la gravedad sobre los gdl condensados, y se comprueban dos igualdades (7.4).
2. **Amortiguamiento de la parte elástica (física).** Se aplicó `C = a0·M + a1·Σe K0,e` sin las rótulas, y se agregó cómo se discretiza dentro del elemento de Giberson (la rótula es interna: `M = K_e·(e + a1·ė)` con `K̃_e`), porque sin eso la «réplica exacta» de OpenSees no se podía implementar.
3. **OpenSees (física).** Además de no restringir `ux`, `uy`, `rz` en los esclavos, los brazos rígidos se piden como elementos elásticos muy rígidos y no como `rigidLink`, que chocaría con `rigidDiaphragm` en los mismos nodos. Las columnas de gravedad se escriben como pilas desde cada nivel hasta la base, que es lo que reproduce la fórmula del motor (verificado: 4 columnas en `CM ± r` dan exactamente `W/h·(dx² + dy² + r²·Δrz²)`).
4. **`theta_y` (física).** Se corrigieron los fixtures (0,0016 y 0,0039 rad) y la validación ± 1 %, pero `theta_y` conserva su significado nominal del esquema (regla del 7.1: ningún campo cambia de significado) y la de propiedades esperadas va en el campo nuevo `theta_y_e`.
5. **Pruebas nuevas con el mismo número (física e integración).** Dos observaciones proponían una «T19» (profundidad y calidad baja): quedaron T19 (continuidad con la profundidad) y T20 (calidad baja), más T21 (régimen de los equipos) y T22 (deriva vectorial), que pedían otras observaciones sin número.
6. **Partir el laringoscopio neonatal (normativa e integración).** Se aplicaron las dos correcciones a la vez: la línea no se parte (lleva `componentes`) y los ids de línea pasan a ser por hash de `origen|servicio|tipo|nombre`, para que ningún cambio futuro de orden rompa las reglas escritas a mano.
7. **Minimapa (integración).** La posición propuesta (`top: 44px; right: 10px`) cae sobre el panel de rendimiento (`.hud`, `top: 42px`, `index.html:77`) cuando está abierto: el minimapa se oculta mientras ese panel esté visible.
8. **Campo de visión (integración).** Con la fórmula propuesta y el límite de 90° del vertical, en el recuadro del teléfono (≈ 358 × 506 px) el campo horizontal queda en ≈ 70°, no en 75° (cálculo propio): el criterio del 13.3 es ≥ 70° en el teléfono y ≥ 75° en escritorio.
9. **Tamaño de `Resultados` (integración).** `thp` ocupa 8 KB por elemento que fluye (`Int16`, `nt·2`), no 16 KB: el total queda en ≈ 9,4 MB a 12,8 MB (cálculo propio con la tabla corregida, que además suma `derivas_vector` y la sexta columna de energía).
10. **«Pisos» y «Laboratorio» (integración).** De las dos opciones se escogió conservar la maqueta actual de «Laboratorio» sobre las franjas (que se siguen calculando solo para ese modo); apoyarlo en los recintos reales queda fuera de alcance.
11. **Veredicto frente a la norma en las 18 filas con tipo (normativa).** La investigación da un solo veredicto por fila; en las 18 filas con ambiente del tipo, `veredicto_norma` lo calcula E comparando áreas (cálculo propio), en vez de reutilizar el veredicto mezclado.
12. **Modificaciones de la Res. 3100 de 2022 (normativa).** No se pudo cotejar 1138 frente a 1410 en esta corrida (se agotó el cupo de búsquedas web); las dos quedan «por confirmar» en el 1.1, en `normas.json` (9.3) y en el 15, como pedía la observación.
13. **Fecha de apertura (normativa).** El segundo corte de la matriz usa el 1-abr-2030, tomado de `docs/11` («apertura hacia abril de 2030»), marcado como estimación.
14. **Fixtures de la ola 0 (integración).** `resultado_min.json` debe corresponder a `estructura_min.json`, pero en la ola 0 el motor aún no existe: se permite un cálculo de referencia que respete tamaños, unidades e ids, y se regenera con el motor en la ola 2. En `plantas_min.json`, la escalera y el ascensor comparten el núcleo para no agrandar el ejemplo, y el fixture se valida con `--fixture`, que omite las reglas que dependen del programa real.
15. **Bits de `rotulas` (física).** Para guardar IO, LS y CP sin cambiar de tipo, los 8 bits del `Uint8` quedan: fluencia i y j, IO i y j, LS i y j, CP (cualquier extremo) y cortante; el cortante dejó el bit 16 por el 128.
