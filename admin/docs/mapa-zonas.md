# Mapa y zonas

El mapa 3D y las zonas son del administrador (A) y del coordinador (K): permisos `mapa.ver` y `zonas.gestionar`.
Planilleros y consultores no ven el mapa: reciben las zonas como **asignación** (alcance de sus listas y colas).

## Dibujar una zona

En el mapa, **Medir zona** (abajo). Al entrar:

- el mapa se aplana (sin inclinación, sin relieve y sin columnas) para que lo que se ve coincida con lo que se cuenta;
  **Ver en 3D** lo vuelve a inclinar con la zona pegada al relieve, y al cerrar la herramienta se restaura la vista;
- los puntos aproximados (barrio o vereda) se pintan en su coordenada guardada, sin dispersar;
- se cierra el globo, se detiene «Girar» y, en el celular, se pliega el panel izquierdo.

Tres modos:

| Modo | Para | Cómo |
|---|---|---|
| **Mira** (por defecto con el dedo) | celular | Una cruz queda fija en el centro y el mapa se arrastra normal. «+ Punto» agrega el vértice en la cruz, «Deshacer» quita el último y «Terminar» cierra. Preciso al píxel. |
| **Por puntos** (por defecto con ratón) | escritorio | Un clic o toque por esquina. Se cierra tocando el primer punto (22 px con el dedo, 8 px con el ratón), con doble clic o doble toque, con Enter o con «Terminar». Esc cancela; Retroceso o Ctrl+Z deshacen. |
| **Lazo** | ambos | Se arma con el botón y sirve para un trazo: se rodea la zona sin soltar y, al soltar, vuelve el arrastre del mapa. El trazo se simplifica (Douglas-Peucker, 100 vértices o menos) y queda para ajustar. Un segundo dedo cancela el trazo y deja pellizcar. |

Después de cerrar, la zona se ajusta: arrastrar un vértice, **+** en el medio de cada lado para agregar uno, tocar un
vértice para **Quitar punto** (mínimo 3) y **Deshacer**. Los lados que se cruzan ponen el borde en rojo y no dejan
terminar; un punto encima del anterior no se repite. Se aceptan de 3 a 150 vértices, todos dentro de Yondó, con un
área entre 100 m² y 4 000 km².

Se dibuja y se edita al píxel con el mapa plano o inclinado. Con **Ver en 3D** y el relieve encendido la zona solo se
mira (MapLibre no ubica con exactitud un punto sobre el relieve): para mover puntos, **Volver a plano**. Cada
**Dibujar otra** empieza con el mapa plano.

Atajos: **Usar este hexágono** (o «Medir este hexágono» desde su detalle), **Usar vereda** (el anillo exterior más
grande, simplificado a 150 vértices) y **Usar lo que se ve**.

## Qué se mide

- **Área** esférica (la de Turf y d3) y **perímetro** haversine; el servidor (`app/geometria.py`) y el navegador
  (`web/js/zona.js`) usan las mismas fórmulas, y una prueba las compara.
- **Mientras se dibuja**, el navegador cuenta sin consultar al servidor: personas dentro, exactas y aproximadas, casco
  urbano y rural, los 6 barrios o veredas con más personas, quienes asistieron a reuniones y la completitud media.
- **Al terminar** (o 400 ms después de soltar un vértice) se pide la distribución completa a
  `GET /api/indicadores?alcance=zona&poligono=…` (o `area_id=…`), con los filtros del mapa: sexo, pirámide de edades,
  puestos y mesas, cédula, abordaje, autorización, fuentes, necesidades y demografía; listas y datos sensibles solo
  si el servidor los manda. Con menos de 10 personas no hay desgloses. Las respuestas viejas se descartan.
- **Conteo oficial**: el del servidor (`$geoWithin` con aristas geodésicas). El navegador usa aristas planas: puede
  diferir en pocos metros.

Resumen fijo: «X exactas · Y aproximadas, contadas en el punto de su barrio o vereda (caen enteras dentro o fuera) · Z
sin ubicación, que no se cuentan».

## Acciones

- **Ver en Habitantes**: la lista con el filtro geométrico real (`poligono` o `area_id`), sin el tope de 500 ids del
  hexágono.
- **Exportar**: el Excel de esas personas (`/api/exportar.xlsx` con el polígono).
- **Guardar zona**: nombre (único), descripción, color de una paleta fija y **Asignar a** planilleros y consultores.
- Zona guardada: **Editar**, **Guardar cambios**, **Nombre y asignación** y **Borrar** (el dibujo queda en el mapa).
- **Zonas guardadas** (panel izquierdo) encuadra la elegida; `/mapa?area_id=3` abre una guardada y
  `/mapa?poligono=lon,lat;…` una dibujada.

Si el servidor todavía no filtra por polígono, el panel lo dice y deja «Ver en Habitantes» y «Exportar»
deshabilitados: nunca se exporta toda la base creyendo que es la zona.

## Celular

El detalle (hexágono o zona) va en una **hoja inferior** de 60 % del alto como máximo. Mientras se dibuja muestra
Modo · Deshacer · (+ Punto) · Terminar · Cancelar; al terminar, el total y el área plegados y **Ver distribución**.
Los controles del mapa suben con la hoja (`--alto-hoja`) y ningún botón mide menos de 44 px.

## API (`app/api/zonas.py`)

| Ruta | Qué hace |
|---|---|
| `GET /api/areas` | `{tope, paleta, areas: [área]}` |
| `POST /api/areas` | `{nombre, descripcion?, color?, poligono, asignada_a?}` → 201 área |
| `GET /api/areas/{id}` | área (404 si no existe) |
| `PATCH /api/areas/{id}` | cambios parciales; el polígono recalcula área y perímetro |
| `DELETE /api/areas/{id}` | `{ok, desasignados}` |

Área: `{id, nombre, descripcion, color, poligono, codificado, vertices, area_m2, perimetro_m, asignada_a, asignados,
creado_por, creado_en, actualizado_en}`.

- `poligono` llega como anillo `[[lon, lat], …]`, texto «lon,lat;…» o GeoJSON Polygon; 422 `{codigo: "poligono"}` si
  no cumple las reglas de arriba.
- Tope de 200 zonas (409); nombre repetido sin distinguir mayúsculas (409); color fuera de `^#[0-9a-fA-F]{6}$` (422).
- La asignación se guarda igual en `areas.asignada_a` y en `usuarios.asignacion.areas`, que es de donde sale el
  alcance; al leer, los asignados salen de `usuarios`. Solo se asignan planilleros y consultores.
- Auditoría: `crear_area`, `editar_area` (con antes y después) y `borrar_area` (con la zona completa y su polígono
  codificado), con `uid` y `rol`.
