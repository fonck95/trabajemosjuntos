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
3. **El cambio coincide en el tiempo con la reunión**: está en curso. Se queda lo más preciso:
   - Si la persona asiste a una reunión en curso, cuentan solo esas.
   - Si no, cuentan las que creó quien hace el cambio.
   - Si no, y ni la ruta ni la pantalla nombran una reunión (reglas 1 y 2), cuentan todas las reuniones en curso que
     quien hace el cambio puede ver: la suya, una abierta al equipo, o A y K todas. Así, lo que se edita, se completa o
     se da de alta mientras dura una reunión queda ligado a ella aunque la persona no sea asistente. El consultor no
     marca ninguna, y la reunión de otra persona del equipo que P no puede ver tampoco.

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

## Tipo de persona y líderes: quién trajo a quién

Cada ficha tiene tres marcas de sí o no, el **tipo de persona** en la campaña (`modelo.TIPOS_PERSONA`; no son usuarios
del panel): **concejal** (`concejal`), **líder** (`lider`) y **votante** (`votante`). Una persona puede ser varias cosas
(un concejal que además es líder). Líderes y concejales traen a otras personas, en general votantes: cada ficha guarda
en `lideres` (su **«Liderado por»**) a quienes la trajeron, **uno o varios**, cada uno con quién lo asignó y cuándo. Si
una persona tiene más de un líder, varios la están captando.

- **Marcar el tipo.** En la ficha (Datos principales → Tipo de persona), en el alta, en «Completar» o al importar la
  base general. A y K lo marcan y lo quitan. P (`personas.tipo`) lo marca en las personas de su zona y en las que
  registra, pero no lo quita: un tipo ya marcado le sale fijo y quitarlo lo hacen A o K. Lo que marca o quita una
  persona del equipo queda con su procedencia (`procedencia.<tipo>`): la importación nunca lo cambia. «Completar» solo
  suma tipos.
- **Asignar.** Desde la ficha (Datos principales → **Liderado por**: una barra para buscar al líder o concejal) o al
  registrar a alguien: el alta trae la misma barra (al marcar **Votante** o Líder se enfoca); en Habitantes, **Nuevo
  votante** abre el alta con Votante marcado, y la ficha de un líder o concejal tiene **Registrar votante liderado**.
  Solo se puede elegir una ficha activa marcada como líder o como concejal, y nadie es su propio líder. Asignar el
  mismo líder dos veces no cambia nada. El límite es de 10 líderes por persona. A y K asignan y quitan; P
  (`lideres.asignar`) asigna en las personas de su zona y en las que registra, pero no quita.
  - La barra: A y K buscan por nombre o cédula en la lista completa (`GET /api/lideres`); P le pregunta al servidor
    por el nombre (3 letras o más) o por la cédula completa y recibe unos pocos de toda la campaña
    (`GET /api/lideres/candidatos?q=`, ver «Privacidad»).
  - Rutas: `POST /api/personas/{pid}/lideres` con `{lider_id}`, y `DELETE /api/personas/{pid}/lideres/{lid}` para
    quitarlo (solo A y K). Quitar uno lo anota en `lideres_quitados`: la importación de la base general no lo vuelve a
    poner, ni P (409 `lider_quitado`); asignarlo de nuevo A o K lo borra de ahí.
  - La importación de la base general enlaza a cada persona con el líder de su columna «Líder» («cédula - nombre») y
    marca como líder a quien figura ahí (ver el README, «Base general de la campaña»).
- **Ver.**
  - La ficha dice quién la lidera (con su tipo: líder o concejal) y muestra el aviso **«Captada por N»** si tiene más
    de un líder: A y K en toda la base; P en las personas de su zona y en las que registra, sin quién asignó cada
    líder ni el enlace a su ficha.
  - La ficha de un líder o concejal dice a cuántas personas lidera, sus votantes y cuántas trae también otro líder, con
    enlaces a Habitantes (A y K). P ve ahí solo **Registrar votante liderado**, sin conteos.
  - En Habitantes (solo A y K):
    - los filtros `tipo` (concejal, lider, votante o sin_tipo), `lider_id` (las que lidera ese líder o concejal),
      `sin_lider=1` (nadie la lidera) y `varios_lideres=1` (las que trae más de uno);
    - la columna «Líder / votante · Liderado por», con el nombre de cada líder (`lideres` en la fila de A y K, con una
      sola consulta por página);
    - los chips del tipo y «N líderes» en la fila;
    - el botón **Líderes**, que lista cada líder y concejal con su tipo, cuántas personas lidera, cuántas son votantes
      y cuántas comparte con otro (`GET /api/lideres`, con la cédula para buscar), y cuántas personas tienen más de
      un líder.
  - La exportación de la base única (solo el administrador) lleva las columnas «Concejal», «Líder», «Votante» y
    «Liderado por».
- **Quitar la marca de líder** (o de concejal) no les quita el líder a las personas que trajo. La ficha lo muestra
  como «ya no marcado como líder ni concejal».
- **Unir fichas.** Los tipos se suman (basta que una de las dos sea votante, líder o concejal). Los líderes del origen
  pasan al destino. Quien tenía como líder a la ficha que se unió pasa a tener a la que queda, sin repetir; nadie queda
  como su propio líder (`db.reapuntar_lideres`).
- **Suprimir.** La ficha suprimida sale de los líderes (y de los líderes quitados) de todas las demás
  (`db.limpiar_ligados`).

### Privacidad

El tipo de persona y el liderazgo son datos políticos:

- **A y K** los ven en toda la base y los cambian: marcan y quitan un tipo, asignan y quitan un líder. Quitar un líder
  (`DELETE`) y la lista de líderes con sus conteos (`GET /api/lideres`) siguen con `requiere("admin")`, y solo ellos
  tienen los filtros por tipo y por líder, la columna «Líder / votante · Liderado por» de Habitantes, la tarjeta de la
  ficha con a cuántas lidera, el tablero y las listas. La exportación es solo del administrador.
- **P** solo suma, y solo en las personas de su zona y en las que registra (`proyeccion.tipo_visible`: las de su
  alcance, toda la base si no tiene asignación, y las que dio de alta él, por `creado_por`). Le puede cambiar el
  barrio, la dirección o la ubicación a cualquiera, como siempre, pero si no la veía, moverla no se la vuelve de su
  zona: su uid queda en `reubicada_por` de esa persona (en la misma escritura) y para él su zona ya no cuenta ahí. Si
  no, la traería, leería su tipo y la devolvería. Para otro planillero de ese barrio sí es de su zona:
  - con `personas.tipo` marca un tipo al registrar, en Completar y en la ficha. Fuera de Completar, un tipo en «no» es
    403 siempre, lo tenga o no la persona (en Completar se ignora, como siempre), y su `base` no compara el tipo: ni un
    403 ni un 409 dicen si alguien es líder, votante o concejal;
  - con `lideres.asignar` asigna un líder (`POST /api/personas/{pid}/lideres`, o `lideres` en el alta). `DELETE` le da
    403, y un líder que A o K le quitaron a esa persona, 409 `lider_quitado` (A y K sí lo vuelven a asignar);
  - en esas fichas recibe `lider`, `votante`, `concejal` y `lideres` (sin `asignado_por`: es el usuario de otra persona
    del equipo; sin los líderes que no autorizaron, que para P son la ficha mínima, sin tipo). Fuera de ellas las
    claves no salen, sus `editables` no traen tipos, y marcar o asignar es 403 `fuera_de_zona`, que depende de la zona
    y no del tipo;
  - busca al líder en toda la campaña con `GET /api/lideres/candidatos?q=`: por nombre (3 letras o más) o por la
    cédula completa, actual o anterior (nunca por partes de un número). Responde hasta 12 fichas activas marcadas como
    líder o concejal, sin las que no autorizaron, con nombre, tipo, lugar y los 3 últimos dígitos de la cédula, sin
    conteos, y cuenta en su presupuesto diario. Un `lider_id` que no saldría ahí (no existe, se unió o se suprimió, no
    está marcado o no autorizó) es un solo 422, «Elija un líder o concejal de la lista», sin el nombre de la ficha. Y
    va después de todo lo que no depende del líder (en el alta, las parecidas, la votación y las etiquetas; al asignar,
    el tope de 10): si no, seguir de largo diría sin costo si un id es un líder. El líder que se guarda sale con su
    nombre en la respuesta y cuenta en el presupuesto diario, como en los candidatos;
  - nunca recibe `lideres_n`, `traidas` ni `intervenciones`. Sus filas (Habitantes, `/api/buscar`, parecidas,
    reuniones) no traen el tipo ni los líderes, porque también recorren toda la base, y le está vedado usar los
    filtros `tipo`, `lider`, `lider_id`, `sin_lider`, `varios_lideres` e `intervenida_en`.
- **C** nunca recibe `lider`, `votante`, `concejal`, `lideres`, `lideres_n`, `traidas` ni `intervenciones`, no puede
  mandarlos al editar ni al registrar a alguien (403) y le están vedados los mismos filtros.
- P y C ven la base general («general») como «otra base» y no pueden filtrar por ella.
- **El asistente** no los recibe ni los escribe. `minimizar` es una lista blanca (tampoco pasan como nombres en
  `editables` ni en `faltan`: los de P traen solo los tipos que la persona todavía no tiene y dirían cuáles tiene), el
  tipo y `lideres` están en sus `OCULTOS`, y sus filtros vedados no incluyen estos filtros.
- **La auditoría** guarda que se cambió el tipo o que se asignó o se quitó un líder, pero oculta cuál, lo haga A, K o
  P: `lider`, `votante`, `concejal`, `lider_id` y `lideres` quedan «(oculto)».
