# Reuniones con horario, traza de lo que se hace en ellas y líderes

## Reuniones con rango de tiempo

Cada reunión tiene fecha, **hora de inicio** (`hora`) y **hora de fin** (`hora_fin`), en formato HH:MM de 24 horas y
en hora de Colombia. La API normaliza «9:30» a «09:30» y responde 422 si:

- la hora no es válida;
- hay hora de fin sin hora de inicio;
- la hora de fin no es posterior a la de inicio.

Al editar, la regla se revisa contra lo que ya está guardado. Una hora mal escrita de antes (la API no la revisaba)
cuenta como vacía y no impide editar lo demás.

Duración:

- Sin hora de fin, la reunión dura **2 horas** desde su inicio (`modelo.DURACION_REUNION`).
- Sin hora de inicio no tiene rango, así que solo se traza lo que la nombra (ver abajo).

`GET /api/reuniones` y `GET /api/reuniones/{id}` devuelven `hora_fin` y `en_curso`: si la reunión está ocurriendo
ahora. La agenda y el modo reunión muestran el rango («09:00–11:00») y el chip **En curso**. El asistente
(`crear_reunion`) también acepta `hora_fin`.

## Traza: qué se hizo durante cada reunión

Toda entrada de la auditoría sobre una persona que hace alguien del equipo lleva en `reuniones` los ids de las
reuniones en que se hizo. Se calcula en `db.auditar` con `trazas.reuniones_del_cambio`. Una reunión entra en la traza
de un cambio si se cumple cualquiera de estas condiciones:

1. **La ruta la nombra.** Es el caso de registrar o quitar a un asistente, de una nota escrita en la reunión y del
   alta de una persona en la reunión.
2. **El cambio se hace desde la pantalla de la reunión** (el modo reunión, `/reuniones/N`) y quien lo hace puede ver
   esa reunión: es suya, está abierta al equipo, o quien lo hace es A o K. El consultor, que no trabaja con reuniones,
   no marca ninguna. `web/js/api.js` manda la cabecera
   `X-Reunion` en las escrituras de esa pantalla. La reunión entra aunque el cambio se haga fuera de su horario, por
   ejemplo al completar perfiles al día siguiente.
3. **La reunión está en curso**, y la persona es asistente de ella o quien hace el cambio la creó.
   - Si la persona asiste a una reunión en curso, cuentan solo esas.
   - Si no, cuentan las que creó quien hace el cambio.
   - Una reunión en curso de otra persona del equipo, a la que la persona no asiste, no cuenta: el cambio puede venir
     de otro lugar.

Qué no lleva traza:

- Las lecturas, como ver los datos sensibles.
- La supresión.
- Lo que hace el sistema.
- Las importaciones de planillas: subir una planilla durante una reunión no es intervenir a cada persona de la
  planilla.

Si algo falla al calcular la traza, el cambio se guarda igual, sin ella.

Dónde se ve:

- **Ficha → Cambios (A y K).** Cada cambio con su reunión:
  - **«Durante «X»»** si se hizo dentro del horario;
  - **«Desde «X»»** si se hizo desde la pantalla de la reunión, fuera de hora.
- **Ficha → Historial (A y K).** Por cada reunión, «Intervenida en «X»», con:
  - cuántos cambios tuvo y de qué tipo;
  - si **asistió** o está **sin asistencia registrada**.

  Con eso se sabe si la persona estuvo ese día y si se la intervino. Registrar o quitar la asistencia no cuenta como
  intervención: está en «Asistió a «X»».
- **Modo reunión** (quien ve la reunión):
  - cada asistente dice cuántos cambios tuvo en ella;
  - **«Intervenidas sin asistencia registrada»** lista a quienes se les hizo algo en la reunión sin estar como
    asistentes, con el botón **Registrar asistencia**.

  Las filas van con la proyección del rol, como los asistentes. A y K tienen además el enlace a Habitantes con el
  filtro `intervenida_en`.
- **Habitantes.** El filtro `intervenida_en=<reunión>` muestra las personas intervenidas en esa reunión. Es solo para
  A y K: P y C reciben 403, como con `creado_por`.
- **Ajustes → Auditoría.** El filtro «Reunión» (`GET /api/auditoria?reunion_id=`) muestra lo que se hizo en esa
  reunión, y cada fila lleva su reunión.

Otros casos:

- **Borrar una reunión.** Su id sale de la traza (`$pull`), como ya salía de las notas.
- **Suprimir a una persona.** Se borra su traza junto con el detalle de su auditoría: la traza diría en qué reuniones
  estuvo.
- **Unir fichas.** Lo que se le hizo a la ficha que se unió cuenta para la ficha que queda: en sus intervenciones, en
  las intervenidas de la reunión y en el filtro `intervenida_en`.

## Líderes: quién trajo a quién

Una persona marcada como **Líder comunitario** (`lider`, en su ficha) trae a otras. Cada ficha guarda en `lideres` a
los líderes que la trajeron, **uno o varios**, cada uno con quién lo asignó y cuándo. Si una persona tiene más de un
líder, varios líderes la están captando.

- **Asignar.** Se hace desde la ficha (tarjeta **Líderes → Asignar líder**) o al registrar a alguien (**Traída por
  (líder)**, en el alta). Solo se puede elegir una ficha activa marcada como líder, y nadie es su propio líder.
  Asignar el mismo líder dos veces no cambia nada. El límite es de 10 líderes por persona.
  - Rutas: `POST /api/personas/{pid}/lideres` con `{lider_id}`, y `DELETE /api/personas/{pid}/lideres/{lid}` para
    quitarlo.
- **Ver.**
  - La ficha dice quién la trajo y muestra el aviso **«Captada por N»** si tiene más de un líder.
  - La ficha de un líder dice cuántas personas trajo y cuántas de ellas trae también otro líder, con enlaces a
    Habitantes.
  - En Habitantes:
    - los filtros `lider_id` (las que trajo ese líder) y `varios_lideres=1` (las que trae más de un líder);
    - el chip «N líderes» en la fila;
    - el botón **Líderes**, que lista cada líder con cuántas personas trajo y cuántas comparte con otro
      (`GET /api/lideres`), y cuántas personas tienen más de un líder.
  - La exportación de la base única lleva la columna «Traído por (líderes)».
- **Quitar la marca de líder** no les quita el líder a las personas que trajo. La ficha lo muestra como «ya no
  marcado como líder».
- **Unir fichas.** Los líderes del origen pasan al destino. Quien tenía como líder a la ficha que se unió pasa a
  tener a la que queda, sin repetir; nadie queda como su propio líder (`db.reapuntar_lideres`).
- **Suprimir.** La ficha suprimida sale de los líderes de todas las demás (`db.limpiar_ligados`).

### Privacidad

El liderazgo es un dato político, como `lider`:

- **A y K** lo ven y lo cambian. Las rutas usan `requiere("admin")`.
- **P y C** nunca reciben `lideres`, `lideres_n`, `traidas` ni `intervenciones`. Les está vedado usar los filtros
  `lider_id`, `varios_lideres` e `intervenida_en`, y no pueden mandar `lideres` al registrar a alguien.
- **El asistente** no lo recibe. `minimizar` es una lista blanca, `lideres` está en sus `OCULTOS`, y sus filtros
  vedados y `CLAVES_FILTRO` no incluyen estos filtros.
- **La auditoría** guarda que se asignó o se quitó un líder, pero oculta cuál: `lider_id` y `lideres` quedan
  «(oculto)».
