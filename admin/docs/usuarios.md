# Usuarios, sesiones y permisos del panel

El panel tiene cuatro roles:

- El **administrador** entra con la credencial de Railway (`ADMIN` y `password`). Puede todo.
- Los **coordinadores** los crea el administrador. Tienen **todos los permisos del administrador** (importar, unir,
  suprimir, mapa y zonas, tablero, calidad, auditoría, ver los datos políticos, la cédula completa y los sensibles,
  crear planilleros y consultores…) **salvo** cuatro cosas que son solo del administrador:
  - **descargar** datos de personas: la base única y lo filtrado en Excel, y los asistentes de una reunión en CSV.
    Los demás consultan en pantalla (la plantilla vacía de la planilla sigue disponible);
  - crear, editar, desactivar, reactivar o restablecer la clave de un **coordinador**;
  - **cambiar el rol** de cualquier usuario (el rol se fija al crearlo);
  - cambiar los **ajustes que son permisos**: presupuestos diarios, sesiones, política de contacto del consultor,
    datos sensibles, tope de cédulas dictadas, versión del compromiso y qué campos propios son sensibles. El
    coordinador los ve en **Ajustes**, en solo lectura.
- Los **planilleros** (trabajo de campo) y los **consultores** (llaman y escriben) los crean el administrador o un
  coordinador en **Usuarios**.

El servidor impone todo esto (responde 403 «Su rol no permite esta acción»); la interfaz solo oculta lo que no se puede.

## Alta de un usuario

1. **Usuarios › Nuevo usuario**: usuario (minúsculas, números, punto, guion o guion bajo; de 3 a 40), nombre, rol,
   teléfono de contacto y **asignación** (barrios, veredas y áreas dibujadas en el mapa). El coordinador solo puede
   elegir planillero o consultor. Un coordinador no tiene asignación: trabaja sobre toda la base.
2. El panel muestra **una sola vez** una clave temporal de 12 caracteres, que vence a las **72 horas**. Entréguela en
   persona o por un medio seguro: no queda en la auditoría ni en ninguna pantalla.
3. En su primer ingreso, el usuario (también el coordinador) **cambia la clave** y **acepta el compromiso de
   confidencialidad**. Hasta hacerlo, solo puede abrir **Mi cuenta**.

No se pueden usar los nombres reservados (`sistema`, `consola`, `desconocido`, `admin`, `migracion`) ni el del
administrador, sin distinguir mayúsculas. Si al arrancar un usuario tiene el nombre del administrador, queda
desactivado y el registro lo dice.

## Acciones sobre un usuario

El coordinador ve a todos los usuarios y sus indicadores, pero solo actúa sobre planilleros y consultores: en la fila de
un coordinador no aparecen acciones, y **Cambiar rol** no aparece nunca.

| Acción | Efecto |
|---|---|
| Desactivar | No puede ingresar; sus sesiones caen en la siguiente acción que haga. Los usuarios **nunca se borran**. |
| Cambiar rol | Solo el administrador: coordinador, planillero o consultor. Cierra sus sesiones. Quien pasa a coordinador deja su asignación. |
| Restablecer clave | Nueva clave temporal (72 h). Cierra sus sesiones. |
| Cerrar sesiones | Cierra todas sus sesiones abiertas. |
| Desbloquear | Borra sus ingresos fallidos recientes (si se equivocó varias veces y quedó esperando). |
| Editar | Nombre, teléfono y asignación. No cierra sesiones: la asignación vale en la petición siguiente. |

Cambiar la clave del administrador en Railway cierra **todas** las sesiones, también las de los usuarios.

## Sesiones

- Las de coordinadores, planilleros y consultores duran como mucho **10 horas** (una jornada de campo), caen tras
  **60 minutos sin uso** y cada usuario tiene como mucho **2** abiertas: al abrir una tercera se cierra la más vieja.
  Los tres valores los cambia el administrador en **Ajustes** (`sesion.horas_max`, `sesion.inactividad_min`,
  `sesion.max_por_usuario`).
- Si la sesión vence con un formulario a medias, el panel pide la clave en un diálogo y guarda lo escrito; sin nada
  pendiente, vuelve a la pantalla de ingreso.
- Sin señal, una petición se corta a los 15 s (lecturas) o 30 s (escrituras) con «Sin conexión. Lo escrito sigue aquí;
  intente de nuevo». Los formularios envían una `Idempotency-Key`: reintentar no duplica nada.

## Ingreso y bloqueos

- Cinco fallos desde una misma red en 15 minutos hacen esperar a esa red. Un navegador que ya entró antes a **su**
  cuenta solo cuenta sus propios fallos: en una red compartida (datos móviles), los errores de otros no lo bloquean.
- No hay bloqueo por nombre de usuario: nadie puede dejar a otro sin entrar a propósito. Si un nombre suma más de 20
  fallos en 24 horas, el administrador ve la alerta **Ingresos** en Usuarios.
- La respuesta es la misma, y tarda lo mismo, para un usuario que existe y uno inventado.

## Permisos

El servidor decide: cada ruta de la API declara sus permisos (`app/acceso.py`, `PERMISOS`) y la interfaz solo oculta.

| Rol | Menú |
|---|---|
| Administrador y coordinador | Panel · Mapa 3D · Habitantes · Mi trabajo · Reuniones · Calidad de datos · Importar y exportar · Usuarios · Ajustes · Mi cuenta |
| Planillero | Mi trabajo (inicio) · Habitantes · Reuniones · Mi cuenta |
| Consultor | Mi trabajo (inicio) · Mi cuenta |

En el código, lo que el administrador hace con los datos se comprueba con `quien.puede(permiso)` o `quien.administra`
(administrador o coordinador), nunca con el nombre del rol; lo exclusivo del administrador son los permisos de
`SOLO_ADMIN` (`usuarios.coordinadores`, `usuarios.roles` y `permisos.modificar`). Un ajuste de permisos se valida con
`acceso.exigir_ajustes`.

Cada ficha o fila que el panel sirve queda en `lecturas` (también las del administrador y los coordinadores).
Planilleros y consultores tienen un **presupuesto diario** de personas distintas (1000 y 300, en **Ajustes**): al
pasarlo reciben «Llegó al tope de personas consultadas hoy», en Usuarios aparece la alerta **Volumen** y, con 20
rechazos en el día, se cierran sus sesiones. Las búsquedas y listas tienen además un límite de 120 consultas por minuto. El administrador y los
coordinadores no tienen presupuesto ni límite de frecuencia.

La búsqueda y los filtros de planilleros y consultores solo miran lo que su rol ve, para que no sirvan de oráculo
(armar una cédula o un teléfono oculto dígito a dígito con lo que aparece o con el total de Habitantes):

- El planillero busca un número **entero** (cédula, teléfono o ficha) o por los últimos dígitos que la fila ya muestra
  (los 3 de la cédula, los 4 del teléfono), nunca por un pedazo. La dirección, el lugar escrito y el correo cuentan
  solo de quien no dijo «no».
- A quien no autorizó se lo encuentra por el nombre (o los 3 últimos de la cédula); un filtro sobre algo que de esa
  persona no se ve (sexo, edad, teléfono, puesto, zona…) no la incluye, y en un orden por un dato oculto (perfil,
  dirección, abordaje, fechas) va al final, por nombre. De un menor, los filtros de teléfono no lo incluyen.
- El consultor busca por nombre o por un número completo de 10 dígitos que se pueda usar, de un adulto que no dijo
  «no».
- Parecidas y «la cédula ya pertenece a…» tampoco ubican a quien no autorizó por su cédula o su teléfono.

El administrador y los coordinadores buscan como siempre (prefijo de la cédula, pedazo del teléfono).

## Indicadores

**Usuarios** muestra, para el periodo elegido (por defecto, los últimos 30 días), los de todos los usuarios, también
los coordinadores (los ven el administrador y los coordinadores):

- **Administración** (administrador y coordinadores): importaciones, exportaciones, fichas unidas, supresiones y
  usuarios creados. Lo que crean o editan en las fichas cuenta como en los planilleros.
- **Planilleros**: fichas creadas (y netas, sin las que se unieron por duplicadas), personas actualizadas, personas con
  datos nuevos, datos completados por primera vez (cédula, teléfono, puesto, mesa…), teléfonos agregados,
  autorizaciones, asistencias, ubicadas y fichas vistas. Lo que se carga de una planilla con «Capturado por» cuenta
  para ese planillero. Vaciar un dato y volver a llenarlo no suma.
- **Consultores**: acercamientos (sin los anulados), personas, contactadas, por canal y por resultado, autorizaciones
  obtenidas, cédulas dictadas y fuera de horario.
- **Calidad**: números agregados que luego resultaron equivocados, cédulas en conflicto y fichas unidas por duplicadas.
- **Avance por zona**: por cada barrio, vereda o área asignada, sus responsables y el porcentaje de personas vigentes
  con cédula, con puesto y mesa, con teléfono usable y contactadas.

La serie por día (o semana, o mes) cuenta personas distintas en cada periodo: **no suma al total**. Cada usuario ve
los suyos en **Mi cuenta**. Los indicadores de los trabajadores son datos personales: el compromiso lo informa.

Crear, desactivar o cambiar el rol de un usuario (también de un coordinador) queda en la auditoría con quién lo hizo
(`uid` y `rol`).

## Exportación

Exporta solo el administrador: `GET /api/exportar.xlsx` y `GET /api/reuniones/{id}/asistentes.csv` piden el permiso
`exportar`, que nadie más tiene (el coordinador, los planilleros y los consultores reciben 403 y no ven los botones). Las **listas** y los **datos sensibles** salen solo si se marcan y se
escribe un motivo; incluir a quien no autorizó admite un motivo opcional (por defecto, «operación interna»). Todo queda
en la auditoría, y lo buscado se guarda solo como su largo, nunca en claro.
