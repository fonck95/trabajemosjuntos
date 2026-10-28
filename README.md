# Atlas Yondó 2028

Investigación abierta sobre **cómo se ha gastado el dinero público en Yondó (Antioquia) desde 2004**, qué hizo y qué dejó de hacer cada gobierno, y **qué proyectos concretos, con presupuesto, pueden financiarse a partir de 2028**, con la E.S.E. Hospital Héctor Abad Gómez como puerta de entrada de los recursos y una red energética pública con domótica apoyada por MinTIC como proyecto bandera.

El repositorio incluye un **atlas 3D interactivo** (Three.js + GSAP) que muestra los hallazgos y los proyectos propuestos:
- **La plata que no se volvió obra, gobierno por gobierno** (pesos constantes de 2026): pilas de billetes con lo que entró, lo que no se convirtió en obra según registros, lo estimado y lo que pudo gestionarse o ahorrarse, con equivalencias en aulas, viviendas, km de placa huella o plantas de tratamiento, y un **panel anual 2004–2026 de 132 indicadores** (`docs/10`).
- **Las sedes reales**: réplicas 3D de cada dependencia pública levantadas con satélite, Google Street View y fotos, en su posición real sobre el casco urbano, con el conmutador **Hoy / Con el proyecto** que muestra cuántos paneles caben de verdad en cada cubierta, dónde van las baterías y qué obras hay que hacer antes. Son 22 puntos: las sedes públicas, incluido el acueducto rural, más la torre del hospital y el parque del relleno que se proponen; se recorren uno por uno y cada uno muestra de cerca cómo se conecta: tablero con medidor bidireccional, gateway IoT, acometida de EPM y enlace de datos al centro de control (`docs/09`).
- **La torre del hospital por dentro**: recorrido en primera persona por los cuatro pisos con sus equipos, un simulador de sismos que mueve la estructura prediseñada con la NSR-10 y el modelo BIM federado con sus interferencias y cantidades (`docs/14`, `docs/15` y `docs/16`).
- **Propuesta integral 2028–2031** (`propuesta.html`, aparte del atlas y enlazada desde su cabecera): una presentación con GSAP para gestionar recursos con el nivel central. Siete áreas, cada una con varios proyectos, sobre la maqueta 3D del territorio real: vivienda en dos lotes reales, ciudadela deportiva con la Cancha de Sóftbol Casabe y el parque lineal del caño, Mirador Puerta del Magdalena, parque agroindustrial junto al puente, torre del hospital y salud rural, agua 24 horas, la primera PTAR del municipio y una granja solar centralizada. Cada uno trae costo, fuentes, proyecto tipo, madurez y pedido (`docs/17`).
- Flujos de contratación, el embudo estudio → obra, la microrred simulada hora a hora, el hospital como nodo financiero de 2028, la hoja de ruta con compuertas y un **visor de modelos 3D profesionales** (glTF/GLB con Draco, Meshopt y KTX2). El motor dibuja bajo demanda, ajusta la resolución según el rendimiento y comparte un solo contexto WebGL entre vistas.

## Hallazgos en cinco líneas

- **$1,01 billones** entraron a la caja municipal entre 2004 y 2024; Yondó sigue con más del doble de la pobreza de Antioquia.
- Desde 2020, el **83 %** del valor contratado por la alcaldía se adjudicó **sin competencia** (31 % en 2016–2019).
- **124 estudios y consultorías** ($24.409 M) desde 2008: solo el **22 %** tiene una obra posterior identificable en SECOP.
- **$84.016 M** pasaron por la EDU de Medellín (2021–2023); seis proyectos de regalías por $77.704 M tienen brecha entre obra y pagos.
- En 2028 el hospital puede canalizar entre **$13.100 M y $34.550 M** si llega con proyectos radicados. La propuesta es una **torre de primer nivel de $37.137 M** (`docs/11`), que supera el escenario ambicioso: con los montos probables le faltan unos $11.700 M. La Red Energética Pública ($5.829 M sin el nodo del hospital, que ahora va en la torre; $7.204 M en docs/05 con él) reduce un 57 % la compra de energía de las sedes oficiales.

## Qué hay aquí

| Ruta | Contenido |
|---|---|
| `docs/00-resumen-ejecutivo.md` | Las conclusiones en dos páginas |
| `docs/01-diagnostico-sectorial.md` | Diagnóstico detallado por sector con cifras y fuentes |
| `docs/02-marco-comparativo-2004-2027.md` | Seis gobiernos comparados: qué se hizo, qué pudo hacerse y no se hizo |
| `docs/03-ciclo-consultorias-ops-secop.md` | Análisis de 10.279 contratos de SECOP: OPS, estudios sin obra, contratación directa, administración delegada |
| `docs/04-hoja-de-ruta-2026-2031.md` | Fases, compuertas, reglas de oro y metas para romper el ciclo |
| `docs/05-microrred-domotica-mintic.md` | Proyecto 1: Red Energética Pública de Yondó (diseño, simulación, presupuesto) |
| `docs/06-hospital-2028-financiacion.md` | Proyecto 2: el hospital como puerta de entrada de los recursos en 2028 (el proyecto del hospital pasó a la torre de `docs/11`) |
| `docs/07-portafolio-presupuesto.md` | Portafolio priorizado con presupuesto y fuentes |
| `docs/08-metodologia-fuentes.md` | Método, fuentes, limitaciones y cómo verificar |
| `docs/09-motor-3d-y-modelos.md` | Motor 3D optimizado, modelos GLB, réplicas de las sedes reales (levantamiento con satélite y Street View) y diseño |
| `docs/10-dinero-no-hecho-por-gobierno.md` | La plata que no se convirtió en obra en cada gobierno, lo que pudo gestionarse y sus equivalencias en obras |
| `docs/11-torre-hospital-nivel-1.md` | Torre de servicios de primer nivel del hospital: norma, proyecto tipo, programa y plantas por piso, dotación, estructura y cimentación, presupuesto de $37.137 M (con un ajuste pendiente del prediseño estructural), APU, financiación y 9 proyectos a articular |
| `docs/12-parque-ecotecnologico-relleno.md` | Clausura del relleno Las Américas y parque ecotecnológico con granja solar de 997 kWp: $16.417 M |
| `docs/13-red-de-distribucion.md` | Red de distribución de 13,2 kV y fibra entre las sedes: precios, APU, 10,066 km de red nueva y presupuesto de $2.965 M |
| `docs/14-simulacion-sismica.md` | Simulador sísmico de la torre: Richter frente a magnitud de momento, efecto de la profundidad, NSR-10 (amenaza intermedia, DMO, grupo IV), prediseño con deriva de 0,939 % frente al límite de 1 %, escenarios con resultados y validación contra OpenSees |
| `docs/15-dotacion-y-habilitacion.md` | Dotación de la torre por servicio frente a la Resolución 3100 de 2019: 1.702 unidades en 270 recintos, matriz de habilitación y cierre de brechas |
| `docs/16-bim-torre.md` | Plan de ejecución BIM de la torre: modelo federado IFC4, nivel de información (LOIN), coordinación de interferencias (280 duras antes, 0 después), cantidades 4D/5D y el ajuste pendiente del prediseño estructural |
| `docs/17-propuesta-integral-2028-2031.md` | Presentación aparte para gestionar recursos con el nivel central (`web/propuesta.html`): siete áreas (vivienda, urbanismo, agroindustria, salud, aguas, aseo y saneamiento, TIC) por $337.550 M, cada uno con sitio real en 3D, costo, proyecto tipo, fuentes, madurez y pedido |
| `docs/anexos/` | Cinco informes de investigación con cada dato y su URL: gobiernos, finanzas y regalías, hospital, energía y MinTIC, indicadores sociales |
| `data/` | Datos estructurados (JSON) que alimentan el atlas y los documentos |
| `data/comparativa/` | Panel anual 2004–2026, fugas en la contratación (SECOP), regalías y fondos no gestionados, costo de no hacer y la síntesis por gobierno |
| `data/edificios/` | Levantamiento de cada sede pública (formato en `ESPECIFICACION.md`) |
| `scripts/geo/` | Herramientas de levantamiento: satélite, cobertura y vistas de Street View, superposición de la huella, calles de OpenStreetMap y huellas de edificaciones |
| `scripts/` | Descarga y análisis de SECOP, simulación de la microrred, construcción del sitio |
| `web/` | El atlas 3D (HTML + módulos JavaScript + Three.js + GSAP); `web/models/` modelos GLB; `web/vendor/` decodificadores Draco y Basis |
| `scripts/modelos/` | Generación y optimización de los modelos GLB (gltf-transform + Draco), réplicas de las sedes (`build_edificios.mjs`) y render de comparación con Street View (`render_vista.mjs`) |

## Ver el atlas 3D

```bash
python3 scripts/build_periodos.py  # matriz de seis gobiernos (data/periodos.json)
python3 scripts/build_marco_md.py  # regenera docs/02
python3 scripts/build_panel_anual.py       # panel anual 2004–2026 (data/comparativa/)
python3 scripts/build_dinero_no_hecho.py   # plata no hecha por gobierno + docs/10
(cd scripts/modelos && npm install && npm run build && node build_edificios.mjs)  # modelos GLB y réplicas (opcional: ya vienen generados)
python3 scripts/build_data.py      # genera web/js/data.js desde data/*.json
python3 scripts/build_site.py      # empaqueta el sitio autónomo en site/
cd site && python3 -m http.server 8000
# abrir http://localhost:8000
```

Al hacer *push* a `main`, el flujo `.github/workflows/pages.yml` publica el atlas en GitHub Pages (hay que activar Pages con origen "GitHub Actions" en la configuración del repositorio). Railway lo construye con Railpack: `railpack.json` corre los mismos dos scripts y `Staticfile` + `Caddyfile` sirven `site/` con Caddy.

## Reproducir el análisis de contratación

```bash
scripts/descargar_secop.sh                         # ~19 MB desde datos.gov.co, por páginas
python3 scripts/fugas_secop.py                     # fugas por año, periodo y entidad (data/comparativa/)
python3 scripts/secop_analisis.py data/secop/raw
mv data/secop/raw/secop_resumen.json data/secop/
python3 scripts/tablas_secop_md.py                 # tablas en Markdown
node scripts/verificar_sim.mjs                     # escenarios de la microrred
```

## Principios de esta investigación

1. **Datos abiertos y reproducibles.** Toda cifra tiene fuente; las estimaciones están marcadas como tales.
2. **Indicios, no acusaciones.** Los patrones de contratación son una agenda de verificación con expedientes; no se nombra a personas naturales.
3. **Proyectos que no repitan el ciclo.** Ninguna propuesta depende de contratar una nueva consultoría sin fuente para la obra.

## Fuentes de mapas e imágenes

- Calles, caños y cuerpos de agua: © colaboradores de OpenStreetMap (ODbL).
- Huellas de edificaciones del contexto urbano: Microsoft Global ML Building Footprints (ODbL).
- Imágenes satelitales (Esri World Imagery) y panoramas de Google Street View: solo se usaron como referencia de levantamiento y **no se publican** (`data/geo/img/` está fuera del repositorio); el atlas enlaza a cada panorama en Google Maps.

## Licencia

Documentos y datos: CC BY 4.0. Código: MIT.
