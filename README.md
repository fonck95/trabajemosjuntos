# Atlas Yondó 2028

Investigación abierta sobre **cómo se ha gastado el dinero público en Yondó (Antioquia) desde 2004**, qué hizo y qué dejó de hacer cada gobierno, y **qué proyectos concretos, con presupuesto, pueden financiarse a partir de 2028**, con la E.S.E. Hospital Héctor Abad Gómez como puerta de entrada de los recursos y una red energética pública con domótica apoyada por MinTIC como proyecto bandera.

El repositorio incluye un **atlas 3D interactivo** (Three.js + GSAP) que muestra los hallazgos y los proyectos propuestos: flujos de contratación, comparación entre periodos de gobierno, el embudo estudio → obra, la microrred simulada hora a hora, el hospital como nodo financiero de 2028, la hoja de ruta con compuertas y un **visor de modelos 3D profesionales** (glTF/GLB con Draco, Meshopt y KTX2). El motor dibuja bajo demanda, ajusta la resolución según el rendimiento y comparte un solo contexto WebGL entre vistas (`docs/09`).

## Hallazgos en cinco líneas

- **$1,01 billones** entraron a la caja municipal entre 2004 y 2024; Yondó sigue con más del doble de la pobreza de Antioquia.
- Desde 2020, el **83 %** del valor contratado por la alcaldía se adjudicó **sin competencia** (31 % en 2016–2019).
- **124 estudios y consultorías** ($24.409 M) desde 2008: solo el **22 %** tiene una obra posterior identificable en SECOP.
- **$84.016 M** pasaron por la EDU de Medellín (2021–2023); seis proyectos de regalías por $77.704 M tienen brecha entre obra y pagos.
- En 2028 el hospital puede canalizar entre **$13.100 M y $34.550 M** si llega con proyectos radicados; la Red Energética Pública ($7.204 M) reduce un 57 % la compra de energía de las sedes oficiales.

## Qué hay aquí

| Ruta | Contenido |
|---|---|
| `docs/00-resumen-ejecutivo.md` | Las conclusiones en dos páginas |
| `docs/01-diagnostico-sectorial.md` | Diagnóstico detallado por sector con cifras y fuentes |
| `docs/02-marco-comparativo-2004-2027.md` | Seis gobiernos comparados: qué se hizo, qué pudo hacerse y no se hizo |
| `docs/03-ciclo-consultorias-ops-secop.md` | Análisis de 10.279 contratos de SECOP: OPS, estudios sin obra, contratación directa, administración delegada |
| `docs/04-hoja-de-ruta-2026-2031.md` | Fases, compuertas, reglas de oro y metas para romper el ciclo |
| `docs/05-microrred-domotica-mintic.md` | Proyecto 1: Red Energética Pública de Yondó (diseño, simulación, presupuesto) |
| `docs/06-hospital-2028-financiacion.md` | Proyecto 2: el hospital como puerta de entrada de los recursos en 2028 |
| `docs/07-portafolio-presupuesto.md` | Portafolio priorizado con presupuesto y fuentes |
| `docs/08-metodologia-fuentes.md` | Método, fuentes, limitaciones y cómo verificar |
| `docs/09-motor-3d-y-modelos.md` | Motor 3D optimizado, pipeline de modelos GLB y diseño |
| `docs/anexos/` | Cinco informes de investigación con cada dato y su URL: gobiernos, finanzas y regalías, hospital, energía y MinTIC, indicadores sociales |
| `data/` | Datos estructurados (JSON) que alimentan el atlas y los documentos |
| `scripts/` | Descarga y análisis de SECOP, simulación de la microrred, construcción del sitio |
| `web/` | El atlas 3D (HTML + módulos JavaScript + Three.js + GSAP); `web/models/` modelos GLB; `web/vendor/` decodificadores Draco y Basis |
| `scripts/modelos/` | Generación y optimización de los modelos GLB (gltf-transform + Draco) |

## Ver el atlas 3D

```bash
python3 scripts/build_periodos.py  # matriz de seis gobiernos (data/periodos.json)
python3 scripts/build_marco_md.py  # regenera docs/02
python3 scripts/build_data.py      # genera web/js/data.js desde data/*.json
(cd scripts/modelos && npm install && npm run build)  # modelos GLB (opcional: ya vienen generados)
python3 scripts/build_site.py      # empaqueta el sitio autónomo en site/
cd site && python3 -m http.server 8000
# abrir http://localhost:8000
```

Al hacer *push* a `main`, el flujo `.github/workflows/pages.yml` publica el atlas en GitHub Pages (hay que activar Pages con origen "GitHub Actions" en la configuración del repositorio).

## Reproducir el análisis de contratación

```bash
scripts/descargar_secop.sh data/secop/raw          # ~19 MB desde datos.gov.co
python3 scripts/secop_analisis.py data/secop/raw
mv data/secop/raw/secop_resumen.json data/secop/
python3 scripts/tablas_secop_md.py                 # tablas en Markdown
node scripts/verificar_sim.mjs                     # escenarios de la microrred
```

## Principios de esta investigación

1. **Datos abiertos y reproducibles.** Toda cifra tiene fuente; las estimaciones están marcadas como tales.
2. **Indicios, no acusaciones.** Los patrones de contratación son una agenda de verificación con expedientes; no se nombra a personas naturales.
3. **Proyectos que no repitan el ciclo.** Ninguna propuesta depende de contratar una nueva consultoría sin fuente para la obra.

## Licencia

Documentos y datos: CC BY 4.0. Código: MIT.
