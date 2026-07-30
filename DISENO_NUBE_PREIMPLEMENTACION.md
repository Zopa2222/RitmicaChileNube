# Diseño previo a implementación — Rítmica Chile Nube

Este documento consolida los requerimientos funcionales, las decisiones posteriores y las reglas verificadas en el repositorio. Es la base de datos, permisos y flujos que deben aprobarse antes de implementar la nube.

## 1. Decisiones confirmadas

- Rítmica Chile es una sola entidad. No habrá multiempresa ni clubes que administren sus propios datos.
- Solo puede existir un campeonato **activo** a la vez.
- Hay exactamente una cuenta fija de **superadministrador** y una de **administrador global**; son cuentas distintas.
- Los campeonatos cloud empiezan limpios: no se migrarán históricos.
- En cada campeonato varían nombre, tipo (clasificatorio/final), zona y fechas.
- El administrador recupera su acceso mediante verificación y restablecimiento realizado por el superadministrador. Los jueces tampoco recuperan claves por sí solos.
- Una reasignación de juez comienza en la **siguiente categoría** de su banca, día y jornada. No altera notas previas.
- Cada pulsación de «Publicar categoría completa» crea una nueva fotografía de toda la categoría. Una corrección privada llega al público solo al publicar nuevamente. No existe publicación parcial, automática ni despublicación manual.
- Un borrador offline del juez solo se sincroniza si continúa vigente la misma activación de la gimnasta. Si se cambió de gimnasta, incluso si luego se volvió a seleccionar, no se aplica automáticamente.
- La plataforma objetivo es Google Cloud.

## 2. Arquitectura propuesta

Se recomienda una única base relacional en Cloud SQL para PostgreSQL y UUID como identificadores. El modelo MongoDB actual, con una base y colecciones dinámicas por campeonato, funciona para la versión local pero dificulta permisos, reasignaciones temporales, publicaciones congeladas, auditoría y la regla de un solo campeonato activo.

La migración no exige trasladar datos históricos, por lo que es el momento adecuado para normalizar:

- Frontend Angular estático en Cloud Storage + Cloud CDN, o Firebase Hosting.
- API Flask contenerizada en Cloud Run.
- Datos en Cloud SQL para PostgreSQL.
- Excel originales, exportaciones y archivos temporales en un bucket privado de Cloud Storage.
- Secret Manager para secretos y Cloud Logging para observabilidad técnica.
- Cloud Scheduler ejecuta la purga definitiva de campeonatos después de 14 días.

La zona horaria de negocio es America/Santiago. Los instantes técnicos se guardan en UTC.

## 3. Modelo de datos

### 3.1 Cuentas y seguridad

| Entidad | Campos principales | Regla |
|---|---|---|
| users | id, account_type, first_name, last_name, rut_normalized, username, password_hash, status, last_login_at | account_type: SUPER_ADMIN, GLOBAL_ADMIN o JUDGE. Nunca se guarda una contraseña legible. |
| system_roles | super_admin_user_id, global_admin_user_id | Una única fila, que referencia dos usuarios distintos: garantiza que solo haya una cuenta de cada tipo fijo. |
| credential_events | id, user_id, event_type, created_by_user_id, created_at | Registra creación, entrega y regeneración de credenciales sin registrar la contraseña. |
| auth_recovery_requests | id, user_id, requested_at, verified_by_user_id, resolved_at | Solicitud que solo el superadministrador puede verificar y resolver. |

Para jueces, el nombre de usuario se crea como PRIMERNOMBREPRIMERAPELLIDORUT, en mayúsculas y sin tildes, puntos ni guion. Si existiera una colisión, el sistema debe detenerse e informar; no debe agregar un sufijo sin avisar.

### 3.2 Campeonato e importación

| Entidad | Campos principales | Regla |
|---|---|---|
| championships | id, name, kind, zone, start_date, timezone, status, responsible_admin_id, created_at, closed_at, deletion_requested_at, purge_after | Estados: DRAFT, ACTIVE, PAUSED, CLOSED, PENDING_DELETION y DELETED. Un índice único parcial sobre ACTIVE permite como máximo un activo. |
| import_previews | id, championship_draft_id, source_file_id, detected_data, decisions, expires_at | Conserva el análisis previo: hojas, días, bancas, categorías, gimnastas, corte AM/PM y correcciones manuales. |
| files | id, championship_id, kind, bucket_object, original_name, sha256, created_at | kind: SOURCE_EXCEL, EXCEL_EXPORT o PDF_EXPORT. Ningún objeto es público. |
| competition_days | id, championship_id, sequence, competition_date, source_sheet_name | Una fila por hoja, en el orden del Excel. La fecha se deriva de la fecha inicial más sequence menos uno. |

La previsualización no crea categorías ni gimnastas definitivas. Al confirmar todas las decisiones se persiste el Excel y se crean campeonato, días, categorías y gimnastas en una transacción.

### 3.3 Orden de paso, categorías y bancas

| Entidad | Campos principales | Regla |
|---|---|---|
| categories | id, championship_id, competition_day_id, name, bench, session, passing_order, source_row, deleted_at | bench: A/B; session: AM/PM. El orden es el de paso del Excel, no el ranking. |
| gymnasts | id, category_id, full_name, club_name, passing_order, created_at, deleted_at, deleted_by_user_id | La identidad es UUID, no el nombre; se admiten nombres repetidos. Al eliminar, deja de verse y de publicarse, pero queda trazabilidad. |
| bench_activations | id, championship_id, competition_day_id, bench, gymnast_id, activated_by_user_id, activated_at, deactivated_at | Solo puede haber una activación abierta por día y banca. Cada activación nueva produce un identificador distinto. |

Una categoría pertenece a un día, banca y jornada. Si el Excel detecta la misma categoría en ubicaciones incompatibles, la previsualización requiere que el administrador la separe o renombre antes de confirmar.

### 3.4 Jueces y asignaciones

| Entidad | Campos principales | Regla |
|---|---|---|
| judge_assignments | id, championship_id, judge_user_id, competition_day_id, bench, session, role, effective_from_category_id, effective_to_category_id, assigned_by_user_id, created_at, superseded_at | role: DA, DB, A, E, L o P. L y P no generan una nota. El inicio de una reasignación es la siguiente categoría. |
| judge_access_windows | id, judge_user_id, championship_id, competition_day_id, starts_at, ends_at | Se deriva de las asignaciones: 08:00–16:00 para una sola jornada y 08:00–00:00 cuando tiene AM y PM. |

Una misma combinación efectiva de juez, día, banca y jornada no puede tener dos roles simultáneos. Sí puede tener roles distintos en otros días, jornadas o bancas.

### 3.5 Notas, cálculo y publicación

| Entidad | Campos principales | Regla |
|---|---|---|
| score_entries | id, gymnast_id, judge_assignment_id, activation_id, value, submission_status, submitted_at, last_modified_by_user_id, updated_at | Una fila por gimnasta y asignación calificadora. value inicia en 0; submission_status distingue PENDING de SUBMITTED. |
| role_score_resolutions | gymnast_id, role, effective_value, source, is_discrepant, acknowledged_at, acknowledged_by_user_id, updated_at | Solo DA/DB. Reúne las notas individuales y conserva el valor efectivo para el cálculo; source: AUTO o ADMIN. |
| score_summaries | gymnast_id, da_score, db_score, a_score, e_score, discount, total_score, calculation_status, calculated_at | Solo el backend puede recalcular y persistir el resultado oficial. |
| publication_batches | id, championship_id, category_id, mode, up_to_gymnast_id, published_by_user_id, published_at | La implementación expone únicamente FULL_CATEGORY y crea un lote nuevo por cada acción manual. |
| published_results | publication_batch_id, gymnast_id, category_id, display_name, club_name, passing_order, total_score, rank_key, published_at | Fotografía del resultado para no alterar lo público con correcciones privadas. |

La vista pública combina todas las gimnastas no eliminadas con su última fotografía publicada. Si una gimnasta aún no tiene publicación, expone puntaje 0 sin revelar notas ni estados internos. Eliminar una gimnasta publicada la oculta de inmediato.

### 3.6 Auditoría y eliminación

| Entidad | Campos principales | Regla |
|---|---|---|
| audit_logs | id, occurred_at, actor_user_id, action, championship_id, entity_type, entity_id, metadata | Registra accesos, activaciones, reasignaciones, pausas, cierres, publicaciones, eliminaciones y recuperaciones. La corrección ordinaria de nota no aparece en la bitácora operativa visible. |
| championship_deletion_confirmations | id, championship_id, confirmed_by_user_id, confirmation_step, confirmed_at | Obliga las confirmaciones explícitas antes de PENDING_DELETION. |

Al solicitar eliminar un campeonato, purge_after se fija a 14 días. Recuperarlo antes de esa fecha vuelve su estado atrás y queda auditado. Solo el trabajo programado de purga realiza la eliminación definitiva y de sus objetos asociados.

### 3.7 Restricciones e índices imprescindibles

- championships(status) único parcial para ACTIVE.
- competition_days(championship_id, sequence) único.
- categories(championship_id, passing_order) y gymnasts(category_id, passing_order) únicos.
- No se permiten intervalos de judge_assignments superpuestos para el mismo juez, día, banca y jornada.
- Una bench_activation abierta por campeonato, día y banca.
- score_entries(gymnast_id, judge_assignment_id) único.
- Índices de published_results por categoría/orden de paso y de audit_logs por campeonato/fecha descendente.

## 4. Reglas de puntaje

El código actual confirma estas reglas que se preservan:

1. Total = DA + DB + Puntaje A + Puntaje E - Descuento. El total no puede ser negativo y se redondea a dos decimales.
2. Para A/E, con una nota se usa 10 - nota; con dos o tres, 10 - promedio; con cuatro o más se excluyen la mayor y menor antes de promediar.
3. El ranking usa total descendente, luego Puntaje E y finalmente Puntaje A.
4. La advertencia A/E aparece si la diferencia relevante es estrictamente mayor que 0,6. Para dos jueces compara la pareja; para tres, pares consecutivos ordenados; con cuatro o más excluye mínimo y máximo y compara el rango restante.
5. DA/DB se ingresan individualmente por juez, aunque la administración vea una celda única por rol. La discrepancia nunca bloquea la publicación.
6. DA, DB, A, E y descuento aceptan valores entre 0 y 20, con hasta dos decimales. La interfaz acepta separador decimal coma o punto y el backend persiste un valor decimal exacto de dos posiciones.
7. Una nota PENDING conserva valor inicial 0 y participa provisionalmente como 0 en el cálculo. Su estado se muestra por separado para no confundirla con un cero enviado y confirmado.

El repositorio tiene dos diferencias que no deben trasladarse sin corregir: backend e interfaz hoy no comparten exactamente la regla de advertencia A/E, y no existe estado que diferencie una celda vacía de un cero válido. La versión cloud usa las reglas precedentes como única fuente de verdad en el backend.

La actualización de un juez es un PUT de una sola nota; el backend recalcula la gimnasta en la misma transacción. El total que pueda enviar la interfaz no es autoritativo.

Para DA y DB:

1. Si todos los valores individuales enviados coinciden, el valor efectivo se actualiza automáticamente.
2. Si difieren, la celda se marca roja y conserva como valor visible la **primera nota recibida**. Al reconocerla, el administrador puede fijar otro valor o confirmar ese valor visible. Luego queda verde hasta una nueva diferencia.
3. Al confirmar o fijar, source pasa a ADMIN: una nota posterior de juez no puede sobrescribir silenciosamente la decisión administrativa.

## 5. Matriz de permisos

| Acción | Superadministrador | Administrador global | Juez | Público |
|---|---:|---:|---:|---:|
| Iniciar sesión y ver perfil propio | Sí | Sí | Sí, solo en su ventana | No aplica |
| Crear, editar, activar, pausar y cerrar campeonato | Sí | Sí | No | No |
| Ver cerrados y exportar | Sí | Sí | No | No |
| Eliminar o recuperar campeonato | Sí | Sí, con confirmaciones | No | No |
| Purga definitiva después de 14 días | Sí, proceso autorizado | No | No | No |
| Cargar y confirmar orden de paso | Sí | Sí | No | No |
| Administrar gimnastas y categorías operativas | Sí | Sí | No | No |
| Activar gimnasta por banca | Sí | Sí | No | No |
| Ver y corregir cualquier nota | Sí | Sí | Solo la propia, activa y habilitada | No |
| Reasignar jueces | Sí | Sí, vista avanzada | No | No |
| Crear cuenta de juez al asignarlo | Sí | Sí, solo como efecto de asignación | No | No |
| CRUD global de jueces y regenerar credenciales | Sí | No | No | No |
| Recuperar acceso de administrador | Sí | No | No | No |
| Publicar categoría completa | Sí | Sí | No | No |
| Consultar resultados públicos | Sí | Sí | Solo consulta pública | Sí, solo activo |
| Ver logs operativos en tiempo real | Sí | No | No | No |

El administrador puede crear una cuenta de juez solo al necesitar una asignación nueva. No puede editar globalmente la ficha de jueces existentes ni regenerar claves; eso queda en el superadministrador.

## 6. Flujos por vista

### 6.1 Inicio de sesión

1. La persona ingresa usuario y contraseña.
2. El servidor valida credenciales, cuenta activa y, para juez, ventana de acceso vigente.
3. Según tipo de cuenta, redirige a superadministración, administración o cabina de juez.
4. Fuera de ventana, el juez no recibe datos del campeonato; ve una explicación breve y la próxima ventana si corresponde.

### 6.2 Administración de campeonatos

1. Lista todos los campeonatos con estado, zona, fechas y responsable.
2. Activar uno exige pausar o cerrar el actual; la restricción de base también lo impide ante operaciones simultáneas.
3. Los cerrados se consultan y exportan, pero no son públicos ni habilitan jueces.
4. Eliminar solicita confirmaciones y muestra la fecha límite de recuperación.

### 6.3 Creación e importación de Excel

1. Se ingresan nombre, tipo, zona y fecha inicial; se adjunta el Excel.
2. El sistema analiza cada hoja, grupos de banca, categorías y el primer corte AM/PM.
3. La previsualización muestra texto y fila del marcador, además de categorías y gimnastas por día, jornada y banca.
4. El administrador acepta el corte, elige otro reconocido o define una fila manual. Sin decisión válida no se puede confirmar.
5. Al confirmar, se guarda Excel original y datos normalizados en una única operación.

### 6.4 Configuración y reasignación de jueces

1. El administrador busca por RUT o nombre; si no existe, ingresa datos mínimos para crear cuenta y credencial inicial.
2. Define día, banca, AM/PM y rol. L/P se registran sin columna de nota.
3. El sistema recalcula ventanas de acceso.
4. En la vista avanzada, una reasignación cierra la asignación actual y ofrece iniciar en la próxima categoría aplicable. Se registra en audit_logs.

### 6.5 Cabina administrativa de puntajes

1. Se muestran las dos bancas y se activa una gimnasta independiente por banca. Cada cambio genera una bench_activation.
2. La grilla muestra valores individuales, envío pendiente/confirmado, advertencias A/E, resolución DA/DB y cálculo del backend.
3. Si se cambia de gimnasta, las notas pendientes de la anterior quedan en rojo.
4. El administrador puede agregar, eliminar, mover, ordenar por ranking, corregir notas y resolver DA/DB.
5. El guardado manual y automático utiliza el mismo endpoint validado que usan los jueces.

### 6.6 Cabina del juez

1. Solo carga la gimnasta activa que corresponde a su banca, día, jornada y rol efectivo; no entrega listados ni notas de otras personas.
2. Al cambiar una nota realiza PUT solo si cambió, enviando activation_id.
3. Sin conectividad conserva el último valor como borrador local y avisa que está pendiente.
4. Al reconectar, el servidor acepta el borrador solo si sigue abierta esa misma activación. Si no, no lo aplica a otra rutina.
5. Tras confirmar, muestra estado Guardado y hora de confirmación.

### 6.7 Publicación y página pública

1. Desde una categoría, el administrador pulsa manualmente «Publicar categoría completa».
2. El backend crea una fotografía de todas las gimnastas activas, incluidos los resultados con puntaje 0, sin notas privadas.
3. Las correcciones posteriores permanecen privadas hasta otra publicación.
4. La página pública solo consulta el campeonato ACTIVE, permite buscar categoría o gimnasta, y ordenar por orden de paso o puntaje.

### 6.8 Superadministración

1. Permite CRUD global de cuentas de juez, regenerar credenciales y recuperar acceso del administrador previa verificación.
2. Muestra audit_logs filtrables y en actualización continua.
3. Permite exportar, recuperar y eliminar campeonatos, además de supervisar la purga programada.

## 7. Especificación de puntajes cerrada

La implementación deberá usar valores decimales exactos con precisión máxima de dos posiciones y rango inclusivo de 0 a 20 para DA, DB, A, E y descuento. Los valores iniciales pendientes participan como cero en el cálculo provisional, pero su estado permanece visible. Ante discrepancia de DA o DB, la primera nota recibida será el valor visible hasta que el administrador lo confirme o modifique.

Con estas reglas confirmadas, el modelo de datos, permisos y flujos puede pasar a la fase de implementación sin cambios estructurales.
