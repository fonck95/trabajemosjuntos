# Acercamientos, trabajo de campo y proyección por rol

Cómo funcionan en el panel los acercamientos (llamadas, mensajes, visitas y reuniones), las colas del consultor,
«Mi trabajo» y lo que cada rol ve de una persona. Código: `app/api/acercamientos.py`, `app/api/personas.py`,
`app/api/reuniones.py`, `app/api/filtros.py` y `app/proyeccion.py`.

## Roles en el manejo de datos

- **A** (administrador de `.env`) y **K** (coordinador) manejan los datos igual: ficha y filas completas, datos
  políticos, la fuente «base con cédula», la cédula completa, el mapa y el tablero, sin alcance ni presupuesto
  diario. En el código se comprueba con `quien.puede(...)` o `quien.administra`, nunca con el rol.
- **P** (planillero) trabaja en campo: Habitantes limitado a su asignación (lugares y áreas), búsqueda y ficha
  abiertas a toda la base (con presupuesto y registro), visitas y reuniones.
- **C** (consultor) llama y escribe: trabaja la persona que tomó de su cola o con la que habló en los últimos 30 días.

## Lo que ve cada rol (`app/proyeccion.py`)

Toda respuesta con una ficha o con filas se arma con la lista de campos permitidos del rol (`CAMPOS_FICHA`,
`CAMPOS_FILA`, `CAMPOS_COLA`), nunca copiando el documento. `fila_completa` calcula todos los valores posibles y
`filas_para` toma solo los del rol; `ficha_de` calcula cada valor solo si el rol lo puede ver.

- Nadie recibe `sensibles` ni `cedula_en_traspaso`. A y K ven `sensibles_registrados` y leen los valores con
  `GET /api/personas/{pid}/sensibles`, que queda auditado sin los valores.
- P: sin `lider`, `listas`, `origen`, `procedencia`, `historial`, `coincidencias`, `cedulas_anteriores`, `fuentes`
  ni etiquetas o campos propios sensibles. La fuente «cedulas» se muestra como «otra_base». No ve los teléfonos de un
  menor ni los toca: `telefono`/`telefono2` en PATCH, agregar un número, cambiarlo o hacerlo principal dan el mismo
  403 para todo menor, y su ficha y su fila no dicen si tiene alguno: `faltan` y `editables` van sin teléfono, y la
  `completitud` de un menor se le calcula sin teléfono, también para ordenar por ella (`completitud`, `-completitud`,
  `por_llamar`), filtrar con `completitud_max` y ordenar la búsqueda (`proyeccion.completitud_vista` y su gemela
  `filtros.expr_completitud_vista`). Tampoco lo saca de la minoría: un PATCH de `edad`, `fecha_nacimiento` o
  `tipo_documento` que lo dejaría adulto da 403 «Pida la corrección al administrador», y lo que P edita de un menor
  se le responde como de un menor. Sus filas llevan la cédula y el teléfono enmascarados (`···123`, `···2233`).
- C: nombre, cédula enmascarada, rango de edad, sexo, barrio, puesto, la autorización, solo los números usables
  (`numero`, `tipo`, `whatsapp`, `estado` e `indice`), el abordaje y lo que le falta (cédula, puesto y mesa).
- Quien dijo «no» sale para P y C como `{id, nombre, cedula_ult3, lugar, consentimiento, abordaje: {estado}}`, y
  toda escritura suya sobre esa persona da 409 `no_contactable` (salvo registrar su «sí» con evidencia).
- Cada ficha y cada fila servida queda en `lecturas` y cuenta en el presupuesto diario de P y C. Después del primer
  429 por volumen del día, P y C ya no reciben listas (Habitantes y colas) hasta el día siguiente; una ficha ya vista
  se puede volver a abrir.

## Registrar un acercamiento

`POST /api/personas/{pid}/acercamientos` (con `Idempotency-Key`):

```json
{"canal": "llamada", "telefono_indice": 0, "resultado": "contesto", "nota": "…", "confirma_numero": true,
 "proximo": null, "proximo_franja": null, "alcance": null, "pedir_actualizacion": false,
 "se_fue_del_municipio": false, "autorizacion": null, "datos_dictados": null}
```

- `telefono_indice` es la posición entre los **números usables** de la ficha (el campo `indice` de cada teléfono);
  también se acepta `telefono`. Es obligatorio en llamada, WhatsApp y SMS.
- P registra solo visitas y reuniones, sin número (`telefono_indice` o `telefono` → 422); C, llamadas y mensajes.
  En la ficha y en el historial, P no ve el número de los acercamientos de un menor y C lo ve enmascarado (y de un
  menor, nada).
- Para C la persona debe ser contactable; si no, 409 `{codigo: "no_contactable", motivo}` con `no_autorizo`,
  `menor`, `edad_desconocida`, `reclamo`, `situacion`, `pendiente`, `no_habilitado` o `canal`.
- Efectos: el número queda confirmado, equivocado, inexistente o con «no contactar»; `volver_llamar` agenda
  `proximo`; `no_contactar` con `alcance: "persona"` registra la revocación (solicitud de revocatoria); `fallecio` y
  `no_vive_aqui` (con «se fue del municipio») reportan la situación sin confirmar; `solicitud_derechos` crea la
  solicitud; un resultado efectivo actualiza `ultimo_contacto`. Llegar al máximo de intentos sin éxito, o quedarse sin
  números usables, deja a la persona «pendiente de actualizar» para la lista de visitas de P.
- `datos_dictados.cedula` (solo C, si falta y coincide con la confirmación) va **siempre** a revisión de A
  (`conflictos_cedula`, motivo `dictada`), con tope diario por consultor; la respuesta es la misma exista o no esa
  cédula. `puesto_id` y `mesa` dictados se escriben solo si faltan, con fuente `consultor`.
- Fuera de `ajustes.horario` queda `fuera_de_horario` y un aviso; no bloquea.
- La respuesta es la ficha del rol más `acercamiento_id` (para «Deshacer») y `avisos`.
- Si la ficha se unió con otra mientras se registraba, lo registrado (el acercamiento, su solicitud o su revocación)
  pasa a la ficha unida (`bd.unida_en`, `bd.recoger_tardios`) y la respuesta es 409 `{codigo: "unida", registrado:
  true, id: <ficha final>}` en vez de «la ficha se unió»: no hay que repetirlo. Lo mismo en `POST …/autorizacion` y en
  el PATCH (guardado con la `Idempotency-Key`, si la hay).
- Una solicitud de corrección, supresión o revocatoria deja `reclamo_en_tramite` en la ficha final, también si llega
  durante una unión (la unión la recalcula cada vez que mueve lo ligado): a quien pidió suprimir sus datos no se le
  llama.

**Anular** (`POST /api/acercamientos/{aid}/anular {motivo}`): el autor durante 24 h; A y K siempre. Revierte los
efectos sobre teléfonos y situación si siguen como los dejó; las autorizaciones y solicitudes no se revierten.
Nunca se borra.

**Resumen** (`abordaje`): insertar o anular hace `$inc abordaje_seq` y después se recalcula `resumen_abordaje` y se
escribe con el filtro `{_id, abordaje_seq}` (hasta 3 intentos).

**Reuniones**: agregar un asistente crea un acercamiento automático (`canal: reunion`, `resultado: contesto`); quitarlo
o borrar la reunión lo anula. P ve sus reuniones y las abiertas al equipo; de las demás recibe solo cuántas hay, en
la cabecera `X-Reuniones-Ajenas`.

## Colas del consultor

`BASE_COLA`: vigente, con un número usable, contacto habilitado (o pendiente con la política «contactar a pendientes» y
alguna fuente distinta de trámites), sin reclamo, adulto conocido, sin «no contactar», libre (sin `en_curso` vigente
de otro) y dentro de su asignación.

| Lista | Condición |
|---|---|
| `por_llamar` | Sin acercamientos |
| `volver_a_llamar` | Menos intentos que el máximo y `proximo` vencido, o el último fue «no contestó» o «buzón» hace `dias_entre_intentos` |
| `seguimiento` | Solo con `seguimiento_activo`: contactadas hace `dias_seguimiento` y que no están en la anterior |
| `mis_hoy` | Mis acercamientos de hoy |

- `GET /api/trabajo/cola?lista=&pagina=`: 20 por página, hasta 10 páginas.
- `POST /api/trabajo/siguiente?lista=`: toma de forma atómica la siguiente (nunca la que ya tiene en sus manos) y
  devuelve su ficha; 204 si la cola está vacía (`GET /api/trabajo` da los pendientes sin autorización).
- `POST /api/trabajo/tomar/{pid}`: para una llamada entrante; exige `BASE_COLA` (409 `tomada` si otro la tiene, 409
  `no_contactable` con el motivo, 403 fuera de su asignación). Como mucho 3 personas tomadas: al tomar una cuarta se
  libera la más vieja. `DELETE` la libera. Una toma dura 20 minutos.
- La búsqueda de C es por nombre (3 letras o más, 10 resultados) o por un número completo de 10 dígitos (3
  resultados, auditada como `buscar_telefono`); con otros dígitos responde 422.

## Mi trabajo e insignias

- `GET /api/trabajo`: tarjetas con conteos dentro del alcance (sin «no», sin no vigentes ni datos marcados «no
  disponible»), la política de contacto, los pendientes sin autorización y la actividad de hoy y de la semana. Las
  tarjetas de P enlazan a Habitantes con sus filtros (`sin_cedula`, `sin_puesto_mesa`, `votacion_estado`,
  `requiere_actualizacion`, `sin_telefono`, `consentimiento`, `sin_lugar`, `mios`) y cuentan lo mismo que ese enlace
  («Mis registros recientes» usa la misma consulta, con el alcance). A y K pasan `uid` para ver el de un usuario:
  entonces los enlaces llevan `como=<uid>`, que `GET /api/personas` acepta solo de A y K (403 para los demás) y que
  aplica el alcance, el rol y el uid (`mios`) de ese usuario, así abren lo mismo que cuenta la tarjeta.
- `GET /api/insignias`: `{calidad, conflictos, solicitudes, situaciones, trabajo}`; `trabajo` es, para P, las
  pendientes de actualizar en su alcance y, para C, las de «volver a llamar» vencidas.

## Filtros comunes

`filtros_query` lee los mismos parámetros en Habitantes, el mapa, la exportación y el tablero (8.3), incluidos
`poligono` (`"lon,lat;…"`, solo A y K) y `area_id` (404 si no existe; 403 si P o C no la tienen asignada). P y C
reciben 403 `permiso` con `poligono`, `ids`, `lista`, `lider`, `fuente=cedulas|ambas`, una etiqueta sensible,
`creado_por`, `actualizado_por` y `menor`. El alcance (`alcance_de`) une los lugares asignados (cubren a quien no
tiene coordenadas) y las áreas (por `punto`).
