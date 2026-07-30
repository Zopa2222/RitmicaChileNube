# Requerimientos funcionales — Rítmica Chile Nube

## 1. Propósito y alcance

Rítmica Chile Nube es la evolución en la nube del sistema actual de gestión
de puntajes de gimnasia rítmica. Conserva el flujo deportivo ya implementado
(orden de paso, bancas, jornadas, cálculo, exportaciones), y lo extiende con
usuarios, permisos, operación simultánea de bancas, publicación controlada y
consulta pública.

Los campeonatos se mantendrán **aislados lógicamente**: sus categorías,
gimnastas, asignaciones, notas y resultados pertenecen a un único
campeonato. No es requisito generar reportes globales entre campeonatos.

No se migrarán campeonatos históricos desde la instalación local. La
plataforma cloud comenzará limpia.

## 2. Roles y acceso

### Administrador global

- Existirá un único usuario administrador global de Rítmica Chile.
- Puede visualizar y editar cualquier campeonato, trabajando con uno a la
  vez en su interfaz.
- Cada campeonato tendrá a ese mismo administrador como responsable único.
- Puede crear, pausar, cerrar, editar, publicar y exportar campeonatos.
- Puede agregar o eliminar gimnastas desde la pantalla de puntajes en tiempo
  real.
- Puede modificar cualquier nota ingresada por un juez.

### Juez evaluador

- Tiene una cuenta reutilizable en distintos campeonatos.
- Solo puede ver la gimnasta activa de la banca, día, jornada y puesto que
  tiene asignado.
- Solo puede ingresar o actualizar su propia nota mientras esa gimnasta esté
  activa.
- No ve el listado de gimnastas ni notas de otros jueces; contará con su
  listado físico de apoyo.
- No dispone de recuperación autónoma de contraseña.

### Espectador

- No requiere inicio de sesión.
- Solo puede consultar el campeonato activo y sus resultados publicados.
- No puede ver notas privadas ni resultados de campeonatos cerrados.

### Super administrador

- Puede consultar todos los campeonatos y cada puntaje con una vista
  equivalente a la del administrador.
- Realiza CRUD global de jueces y puede regenerar credenciales cuando sea
  necesario.
- Ve en tiempo real los logs operativos.
- Puede exportar, recuperar y eliminar campeonatos.

## 3. Campeonatos, días, bancas y jornadas

### Ciclo de vida

1. El administrador carga un Excel de orden de paso en una etapa de
   previsualización.
2. Confirma la detección de días, bancas, jornadas y categorías.
3. Al confirmar, se crea el campeonato y queda disponible para operar.
4. El administrador puede pausarlo o cerrarlo en cualquier momento.
5. Un campeonato cerrado queda consultable y exportable por administrador y
   super administrador, pero deja de estar visible al público.

### Días

- Al crear el campeonato se define su fecha de inicio.
- Cada hoja del Excel representa un día de competencia.
- Las hojas se asignan en orden: hoja 1 = día 1, hoja 2 = día 2, etc.
- Un campeonato puede durar uno o más días; la cantidad de días proviene de
  la cantidad de hojas del orden de paso.

### Bancas y gimnastas activas

- Cada categoría pertenece a Banca A o Banca B, detectada desde los grupos
  de columnas del Excel, como en el sistema actual.
- Cada banca tiene una gimnasta activa independiente. Por lo tanto, en un
  campeonato pueden existir dos gimnastas activas simultáneamente: una por
  banca.
- El administrador selecciona manualmente cuál gimnasta está activa o
  disponible para recibir notas.
- No existe un cierre automático de rutina: cambiar la gimnasta activa es la
  decisión operativa del administrador.

### Jornadas AM y PM desde el Excel

La jornada no se determina por el reloj del dispositivo. Cada categoría toma
su jornada del tramo donde aparece en la hoja del orden de paso:

- Las categorías anteriores al primer marcador principal de cambio se
  asignan a **AM**.
- Las categorías posteriores se asignan a **PM**.
- El marcador puede contener variaciones normalizadas de expresiones como
  `PREMIACIÓN`, `ALMUERZO`, `JUECES` o una pausa principal.
- Solo el primer corte principal cambia de AM a PM. Pausas posteriores y la
  premiación final no vuelven a cambiar la jornada.

Ejemplo validado: en `CENTRO.xlsx`, hoja `SABADO`, la fila 92 contiene
`BREAK 1 HORA - PREMIACION - ALMUERZO JUECES`; las categorías previas son AM
y las posteriores son PM. La pausa de 15 minutos de la fila 147 permanece
dentro de PM.

### Previsualización del Excel y corrección del corte

Antes de crear el campeonato, el sistema debe:

- Informar por cada hoja/día el marcador detectado, su fila y su texto.
- Mostrar cuántas categorías y gimnastas se asignarán a AM y PM, separadas
  por banca.
- Permitir que el administrador acepte el corte, seleccione otro marcador
  reconocido o indique manualmente una fila de corte.
- Mostrar una vista previa de las categorías que quedarán en cada jornada.
- Advertir y exigir una decisión manual si no detecta un marcador válido.

No será necesario editar el Excel para corregir una detección.

## 4. Cuentas de jueces y ventanas de habilitación

### Creación de cuentas

- Al cargar jueces de un campeonato, el sistema verifica si cada juez ya
  tiene cuenta.
- Si no la tiene, la crea automáticamente y permite entregar sus credenciales
  por el medio externo que defina Rítmica Chile.
- Una cuenta persiste en la base de datos aunque termine su acceso a un
  campeonato.

### Formato propuesto de credenciales

- Usuario: primer nombre + primer apellido + RUT, todo en mayúsculas, sin
  tildes, puntos ni guion. Ejemplo: `MARIAPEREZ12345678K`.
- Contraseña: generada aleatoriamente, legible y sin derivarse de nombre ni
  RUT. Ejemplo de formato: `Brisa-Atlas-74-Lima`.
- La contraseña se entrega al crearla y no se guarda como texto legible.
- El juez no puede restablecerla por sí mismo; el super administrador puede
  regenerarla.

### Ventanas de acceso

Las ventanas se calculan por juez, día y jornadas asignadas, usando la hora
oficial de Chile:

- Si tiene asignada una sola jornada ese día, su acceso dura 8 horas desde
  las 08:00.
- Si tiene asignadas AM y PM el mismo día, su acceso dura 16 horas desde las
  08:00.
- Si participa en más días, se agregan ventanas independientes para cada día
  en que tenga una asignación.
- Tener varios roles dentro de la misma jornada no amplía la ventana; tener
  AM y PM sí.
- Fuera de las ventanas, la cuenta existe pero no puede acceder ni registrar
  puntajes de ese campeonato.

## 5. Asignaciones y notas de jueces

### Asignación

- Un juez se asigna por banca, día, jornada y rol.
- Los roles disponibles son `DA`, `DB`, `A`, `E`, Línea (`L`) y Planilla
  (`P`).
- Los roles Línea y Planilla se registran, pero no generan una columna de
  nota.
- El administrador puede reasignar a un juez durante el campeonato desde una
  pantalla avanzada, separada de la operación cotidiana.
- La reasignación debe quedar en los logs. Las notas anteriores se conservan
  y el nuevo juez solo afecta las notas pendientes desde su reasignación.

### Ingreso y estado de notas

- Todas las notas se inicializan en `0`.
- Cada nota también mantiene un estado de envío para distinguir una nota
  válida de `0` de una nota aún no ingresada.
- El juez envía actualizaciones mediante `PUT` únicamente cuando su valor
  cambia.
- Puede editar su nota mientras la gimnasta permanezca activa.
- Si el administrador cambia la gimnasta activa, la pantalla administrativa
  muestra en rojo las notas no enviadas de la gimnasta que quedó atrás.
- El administrador puede completar esas notas o volver a activar a la
  gimnasta anterior.

### Roles DA y DB

- Se admiten hasta cuatro jueces por rol, banca y jornada para DA y DB.
- Cada juez DA o DB registra su nota individual, aunque la planilla principal
  muestre una única celda DA y una única celda DB.
- Los jueces DA/DB deben ingresar el mismo valor.
- Si existen valores distintos, la celda única se muestra en rojo como aviso
  al administrador.
- Al hacer clic en la celda, el administrador reconoce el aviso; puede
  editarla o dejarla como está. La celda pasa a verde y no existe bloqueo de
  publicación.
- Una discrepancia posterior vuelve a generar una advertencia roja, sin
  bloquear la publicación.

### Reglas actuales de cálculo a preservar

- DA y DB se incorporan al puntaje total.
- Para A y E: con un juez se usa `10 - nota`; con 2 o 3 se promedian todas
  las notas; con 4 o más se excluyen la mayor y la menor antes de promediar.
- El descuento se resta del total final.
- El sistema marca diferencias mayores que `0,6` entre notas de A o E.
- El orden de resultados usa puntaje total y conserva los desempates actuales
  por E y luego A.

## 6. Administración de gimnastas y resultados

- El administrador puede agregar o eliminar gimnastas dentro de la pantalla
  de puntajes en tiempo real, incluso después de cargar el Excel.
- Puede reordenarlas manualmente y ordenar por puntaje, con los desempates
  vigentes.
- El sistema conserva guardado manual y guardado automático.
- El backend sigue siendo la fuente autoritativa del cálculo final.
- Se mantienen las exportaciones a Excel y PDF para administrador y super
  administrador.

## 7. Publicación de resultados

- Solo se muestra públicamente el campeonato activo.
- El público abre una página con el listado de categorías de ese campeonato.
- Al seleccionar una categoría, ve todas las gimnastas de la categoría.
- Puede buscar por categoría o gimnasta.
- Puede ordenar por orden de paso o por puntaje.
- Las gimnastas que no tengan un resultado publicado se muestran con puntaje
  `0`.
- El público nunca ve notas privadas de jueces.

### Acción «Publicar categoría completa»

- Cada categoría tiene un único botón de publicación en la vista
  administrativa.
- Cada pulsación crea una nueva fotografía de todas las gimnastas activas de
  la categoría. No existe publicación parcial ni publicación automática.
- Se incluyen todos los resultados, también aquellos cuyo puntaje vigente sea
  `0`.
- Una corrección posterior a una publicación no llega al público hasta que el
  administrador vuelva a publicar.
- Si se elimina una gimnasta ya publicada, debe desaparecer de la vista
  pública.

## 8. Auditoría, eliminación y recuperación

### Logs

- El super administrador ve los logs operativos en tiempo real.
- Deben registrarse, como mínimo, accesos, activación de gimnastas,
  reasignaciones de jueces, pausas, cierres, publicaciones, eliminaciones y
  recuperaciones.
- Corregir una nota no exige motivo ni debe generar un historial de auditoría
  visible para la operación.

### Eliminación de campeonatos

- Eliminar un campeonato exige múltiples advertencias y confirmaciones
  explícitas del administrador o super administrador.
- La eliminación inicial es recuperable durante dos semanas.
- Después de ese plazo, el campeonato se elimina definitivamente.

## 9. Conectividad y dispositivos

- El administrador usará principalmente notebook.
- Los jueces usarán celular o tablet.
- Los espectadores usarán principalmente celular.
- Ante conectividad inestable, la pantalla del juez conserva la última nota
  como borrador local y la reintenta enviar automáticamente al recuperar
  conexión.
- La interfaz debe indicar claramente si una nota está pendiente de
  sincronización o confirmada por el servidor.

## 10. Fuentes funcionales existentes

Se preservarán del sistema actual, adaptándolas a los permisos y la operación
en nube:

- Importación de orden de paso desde Excel.
- Detección automática de Banca A y B.
- Configuración de jueces por banca y jornada.
- Ingreso de puntajes, advertencias de diferencia, autoguardado y cálculo en
  backend.
- Reordenamiento de gimnastas y desempates.
- Exportación de resultados a Excel y PDF.
