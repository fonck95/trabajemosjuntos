# Usuarios, sesiones y permisos del panel

El panel tiene tres roles. El **administrador** entra con la credencial de Railway (`ADMIN` y `password`) y es el
único que gestiona usuarios, importa, exporta, une, suprime y ve el mapa y el tablero. Los **planilleros** (trabajo de
campo) y los **consultores** (llaman y escriben) son usuarios que crea el administrador en **Usuarios**.

## Alta de un usuario

1. **Usuarios › Nuevo usuario**: usuario (minúsculas, números, punto, guion o guion bajo; de 3 a 40), nombre, rol,
   teléfono de contacto y **asignación** (barrios, veredas y áreas dibujadas en el mapa).
2. El panel muestra **una sola vez** una clave temporal de 12 caracteres, que vence a las **72 horas**. Entréguela en
   persona o por un medio seguro: no queda en la auditoría ni en ninguna pantalla.
3. En su primer ingreso, el usuario **cambia la clave** y **acepta el compromiso de confidencialidad**. Hasta hacerlo,
   solo puede abrir **Mi cuenta**.

No se pueden usar los nombres reservados (`sistema`, `consola`, `desconocido`, `admin`, `migracion`) ni el del
administrador, sin distinguir mayúsculas. Si al arrancar un usuario tiene el nombre del administrador, queda
desactivado y el registro lo dice.

## Acciones sobre un usuario

| Acción | Efecto |
|---|---|
| Desactivar | No puede ingresar; sus sesiones caen en la siguiente acción que haga. Los usuarios **nunca se borran**. |
| Cambiar rol | Planillero ⇄ consultor. Cierra sus sesiones. |
| Restablecer clave | Nueva clave temporal (72 h). Cierra sus sesiones. |
| Cerrar sesiones | Cierra todas sus sesiones abiertas. |
| Desbloquear | Borra sus ingresos fallidos recientes (si se equivocó varias veces y quedó esperando). |
| Editar | Nombre, teléfono y asignación. No cierra sesiones: la asignación vale en la petición siguiente. |

Cambiar la clave del administrador en Railway cierra **todas** las sesiones, también las de los usuarios.

## Sesiones

- Las de planilleros y consultores duran como mucho **10 horas** (una jornada de campo), caen tras **60 minutos sin
  uso** y cada usuario tiene como mucho **2** abiertas: al abrir una tercera se cierra la más vieja. Los tres valores
  se cambian en **Ajustes** (`sesion.horas_max`, `sesion.inactividad_min`, `sesion.max_por_usuario`).
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
| Administrador | Panel · Mapa 3D · Habitantes · Mi trabajo · Reuniones · Calidad de datos · Importar y exportar · Usuarios · Ajustes · Mi cuenta |
| Planillero | Mi trabajo (inicio) · Habitantes · Reuniones · Mi cuenta |
| Consultor | Mi trabajo (inicio) · Mi cuenta |

Cada ficha o fila que el panel sirve queda en `lecturas` (también las del administrador). Planilleros y consultores
tienen un **presupuesto diario** de personas distintas (1000 y 300, en **Ajustes**): al pasarlo reciben «Llegó al tope
de personas consultadas hoy», el administrador ve la alerta **Volumen** y, con 20 rechazos en el día, se cierran sus
sesiones. Las búsquedas y listas tienen además un límite de 120 consultas por minuto.

## Indicadores

**Usuarios** muestra, para el periodo elegido (por defecto, los últimos 30 días):

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

## Exportación

Solo el administrador exporta. Las **listas** y los **datos sensibles** salen solo si se marcan y se escribe un motivo;
incluir a quien no autorizó admite un motivo opcional (por defecto, «operación interna»). Todo queda en la auditoría,
y lo buscado se guarda solo como su largo, nunca en claro.
