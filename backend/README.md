# Flask Backend API - Rítmica Chile

## Implementación cloud en transición

El backend conserva temporalmente las rutas MongoDB de la aplicación local y
ya incorpora el modelo cloud normalizado en PostgreSQL. Los nuevos modelos
están en `app/models`, las reglas decimales de puntaje en
`app/services/cloud_scoring_service.py` y las migraciones en `migrations`.

### Configuración local

Desde la raíz del repositorio:

```bash
docker compose up --build
docker compose exec backend flask --app run.py db upgrade
```

Sin Docker, configure `DATABASE_URL` usando `.env.example` y ejecute:

```bash
cd backend
python -m pip install -r requirements.txt
python -m flask --app run.py db upgrade
python run.py
```

### Pruebas

```bash
cd backend
python -m pytest -q
```

Las pruebas usan SQLite en memoria para validar el dominio y las restricciones
portables. Para repetirlas contra una base PostgreSQL aislada:

```bash
TEST_DATABASE_URL=postgresql+psycopg://usuario:clave@localhost/ritmica_chile_test \
  python -m pytest -q
```

La migración oficial apunta a PostgreSQL y debe ejecutarse en staging antes de
desplegar rutas cloud.

### Cuentas fijas y autenticación

Después de aplicar la migración, configure las cuatro variables secretas y
ejecute una sola vez:

```bash
flask --app run.py bootstrap-fixed-users
```

Variables requeridas:

- `SUPER_ADMIN_USERNAME`
- `SUPER_ADMIN_PASSWORD`
- `GLOBAL_ADMIN_USERNAME`
- `GLOBAL_ADMIN_PASSWORD`

El ingreso administrativo está en `/administracion/ingresar` y usa
`POST /api/v1/auth/admin/login`. La ruta anterior `/api/v1/auth/login` es un
alias también exclusivo para administrador y superadministrador; rechaza
cuentas de juez incluso si su antigua contraseña es correcta. La sesión se guarda en una
cookie HttpOnly y las escrituras autenticadas requieren el encabezado
`X-CSRF-TOKEN` con el valor de la cookie `ritmica_csrf`. En producción las
cookies son Secure y las rutas MongoDB heredadas no se registran, salvo que se
habiliten explícitamente con `ENABLE_LEGACY_ROUTES=True`.

Los jueces ingresan abriendo `/acceso-juez#<token>`; no hay formulario de
usuario/contraseña para ellos. El cliente retira el fragmento del historial y
envía el token por `POST /api/v1/auth/judge/link`. Se persiste sólo su hash
SHA-256; el secreto aleatorio tiene 256 bits y nunca se registra en auditoría.
El enlace es personal y reutilizable: funciona en cada ventana de acceso
asignada mientras el campeonato esté ACTIVE o PAUSED. Entre turnos, al finalizar
la última ventana, al cerrar el campeonato o al retirar las asignaciones, no
permite entrar ni operar. Las nuevas asignaciones usan el mismo enlace.
Una desactivación manual siempre bloquea el acceso.

Desde Administración → Jueces, «Generar enlace» entrega un enlace nuevo y
revoca tanto el anterior como sus sesiones. Las cuentas existentes necesitan
que el administrador genere y entregue su primer enlace; la migración no
genera secretos ni modifica asignaciones. Los enlaces recién creados o
importados permanecen sólo en la bandeja de la sesión administrativa: se pueden
copiar y, en Jueces, exportar a Excel. No se pueden recuperar desde el hash.
Usar el origen público HTTPS al abrir la administración para compartir URLs
accesibles desde los celulares; `localhost` no sirve desde otro dispositivo.
Quien posee el enlace puede entrar durante esos turnos, por lo que se entrega
individualmente. La sesión de juez dura hasta 24 horas, pero cada operación
vuelve a comprobar turno, estado y versión del enlace. Tras expirar la sesión,
el juez puede abrir nuevamente el mismo enlace durante un turno vigente.

### Campeonatos e importación cloud

Las rutas de este bloque exigen sesión de superadministrador o administrador
global:

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/v1/championships` | Lista campeonatos. |
| `POST` | `/api/v1/championships` | Crea un campeonato en borrador. |
| `GET` | `/api/v1/championships/{id}` | Entrega datos y conteos importados. |
| `POST` | `/api/v1/championships/{id}/import-previews` | Analiza un `.xlsx` sin crear todavía días, categorías ni gimnastas. |
| `GET` | `/api/v1/championships/{id}/import-previews/{preview_id}` | Consulta la detección y el resumen AM/PM por banca. |
| `PATCH` | `/api/v1/championships/{id}/import-previews/{preview_id}` | Confirma los cortes detectados o define cortes manuales. |
| `POST` | `/api/v1/championships/{id}/import-previews/{preview_id}/confirm` | Persiste el orden de paso completo en una transacción. |

Ejemplo para crear el borrador:

```json
{
  "name": "Clasificatorio Zona Centro 2026",
  "kind": "CLASIFICATORIO",
  "zone": "CENTRO",
  "start_date": "2026-08-15"
}
```

La carga usa `multipart/form-data` con el campo `file`. Si todas las hojas
tienen un corte automático correcto, se pueden confirmar juntas enviando:

```json
{
  "accept_detected": true
}
```

Para corregir una hoja manualmente se envía su secuencia y la fila de
separación; toda fila de datos anterior queda en AM y las siguientes quedan
en PM:

```json
{
  "sheets": [
    {
      "sequence": 1,
      "cutoff_row": 92,
      "confirmed": true
    }
  ]
}
```

En desarrollo los originales se guardan localmente. En Cloud Run se configura
`FILE_STORAGE_BACKEND=gcs` y `GCS_BUCKET` para usar un bucket privado.

### Operación del campeonato, jueces y bancas

| Método | Ruta | Uso |
| --- | --- | --- |
| `POST` | `/api/v1/championships/{id}/activate` | Activa un borrador o reanuda uno pausado. Rechaza la operación si ya existe otro activo. |
| `POST` | `/api/v1/championships/{id}/pause` | Pausa el campeonato activo. |
| `POST` | `/api/v1/championships/{id}/close` | Cierra el campeonato y termina sus activaciones abiertas. |
| `GET` | `/api/v1/championships/{id}/competition-days` | Lista los días disponibles para configurar. |
| `GET` | `/api/v1/judges?query=...` | Busca cuentas de juez por nombre, usuario o RUT. |
| `POST` | `/api/v1/judges` | Crea una cuenta global de juez; solo superadministrador. |
| `POST` | `/api/v1/admin/judges/{id}/access-link` | Genera o reemplaza el enlace personal e invalida sus sesiones; administrador o superadministrador. |
| `POST` | `/api/v1/admin/judges/access-links` | Reemplaza atómicamente los enlaces de hasta 100 jueces; administrador o superadministrador. |
| `GET/POST` | `/api/v1/championships/{id}/judge-assignments` | Lista o crea asignaciones por día, banca, jornada y rol. |
| `POST` | `/api/v1/championships/{id}/judge-assignments/{assignment_id}/reassign` | Reasigna el rol desde la categoría siguiente a la gimnasta activa. |
| `GET` | `/api/v1/championships/{id}/competition-days/{day_id}/operations` | Entrega categorías, gimnastas y activación actual de ambas bancas. |
| `PUT` | `/api/v1/championships/{id}/competition-days/{day_id}/benches/{A\|B}/active-gymnast` | Selecciona la gimnasta activa de una banca. |

El administrador global puede crear una cuenta nueva solamente dentro de una
asignación. Para ello, en vez de `judge_id`, envía:

```json
{
  "competition_day_id": "uuid-del-dia",
  "bench": "A",
  "session": "AM",
  "role": "DA",
  "judge": {
    "first_name": "María",
    "last_name": "Pérez",
    "rut": "12.345.678-5"
  }
}
```

La respuesta incluye `credentials: { username, access_path }` una sola vez,
sin contraseña. Si el juez ya existe, se envía `judge_id` y no se reemplaza su
enlace. Las asignaciones y sus ventanas horarias determinan el acceso.
Las asignaciones iniciales se crean mientras el campeonato está en borrador;
una vez iniciada la competencia, los cambios usan la ruta de reasignación y
comienzan automáticamente en la categoría siguiente. Un juez con una
asignación vigente puede iniciar o recuperar sesión durante sus ventanas del campeonato
activo (y mientras esté pausado), pero solo puede registrar notas cuando el
campeonato está activo y su asignación corresponde a la categoría en curso.

El cambio de gimnasta es idempotente si se selecciona nuevamente la que ya está
activa. Si se cambia a otra y luego se vuelve a la anterior, se crea un nuevo
`activation_id`; de ese modo el servidor puede rechazar borradores offline
asociados a una activación antigua.

### Cabina del juez

Estas rutas solo admiten una sesión de tipo `JUDGE` con una asignación vigente
en un campeonato activo o pausado. Las notas se aceptan únicamente mientras el
campeonato está activo y para la asignación efectiva de la categoría:

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/v1/judge/contexts` | Entrega únicamente las asignaciones propias y la gimnasta activa aplicable. |
| `PUT` | `/api/v1/judge/scores/{score_entry_id}` | Guarda o actualiza una nota propia. |

El contexto no contiene listados de gimnastas, notas de otros jueces ni el
puntaje total. Una asignación puede responder `WAITING_FOR_GYMNAST`,
`WAITING_FOR_SESSION`, `WAITING_FOR_EFFECTIVE_CATEGORY` o `ACTIVE`. Los roles
Línea y Planilla reciben el contexto activo con `can_score=false`.

Ejemplo de guardado:

```json
{
  "activation_id": "uuid-de-la-activacion-visible",
  "value": "1,15"
}
```

La nota acepta coma o punto, rango inclusivo de 0 a 20 y hasta dos decimales.
Repetir exactamente el mismo `PUT` devuelve `changed=false` y conserva la hora
del primer guardado. Si la administración cambió de gimnasta —aunque luego
vuelva a la anterior— el `activation_id` antiguo recibe
`STALE_ACTIVATION` y nunca se aplica.

Cada cambio válido actualiza el estado `PENDING/SUBMITTED`, las resoluciones
DA/DB y el resumen autoritativo en la misma transacción. La corrección normal
de una nota no genera una entrada de auditoría operativa.

### Cabina administrativa de puntajes

Estas rutas exigen una sesión de superadministrador o administrador global:

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/v1/championships/{id}/categories/{category_id}/scoring` | Entrega la grilla completa de la categoría: jueces efectivos, notas individuales, pendientes, alertas A/E, resoluciones DA/DB, descuento y total. |
| `POST` | `/api/v1/championships/{id}/categories/{category_id}/gymnasts` | Agrega una gimnasta al final o en una posición específica e inicializa sus notas. |
| `DELETE` | `/api/v1/championships/{id}/gymnasts/{gymnast_id}` | Elimina lógicamente una gimnasta, conserva sus notas y cierra su activación si estaba en banca. |
| `PUT` | `/api/v1/championships/{id}/categories/{category_id}/gymnasts/order` | Guarda el orden manual completo de la categoría. |
| `POST` | `/api/v1/championships/{id}/categories/{category_id}/gymnasts/order-by-score` | Ordena persistentemente por total, luego E y finalmente A. |
| `PUT` | `/api/v1/championships/{id}/score-entries/{score_entry_id}` | Completa o corrige una nota individual. |
| `PUT` | `/api/v1/championships/{id}/gymnasts/{gymnast_id}/discount` | Actualiza el descuento y recalcula el total. |
| `PUT` | `/api/v1/championships/{id}/gymnasts/{gymnast_id}/role-resolutions/{DA\|DB}` | Reconoce una discrepancia; opcionalmente fija otro valor efectivo. |

Al crear una asignación puntuable se inicializa una nota `0.00/PENDING` para
cada gimnasta alcanzada. Línea y Planilla no generan notas. Las reasignaciones
respetan el corte por categoría: la grilla histórica conserva al juez anterior
en las categorías ya recorridas y usa al nuevo desde la categoría siguiente;
una nota precargada que quedó fuera de ese alcance no participa en los
cálculos ni puede editarse.

Las notas y descuentos aceptan coma o punto, rango inclusivo de 0 a 20 y hasta
dos decimales. Enviar `0` cambia correctamente una nota de `PENDING` a
`SUBMITTED`. Las operaciones son idempotentes y responden `changed=false`
cuando el valor y el estado ya coinciden.

La grilla puede consultarse en cualquier estado para revisar resultados
históricos. Las correcciones, descuentos y resoluciones solo se admiten con el
campeonato `ACTIVE` o `PAUSED`. Una corrección ordinaria no crea un log de
auditoría.

Agregar, eliminar y reordenar gimnastas está disponible en `DRAFT`, `ACTIVE`
y `PAUSED`. El alta admite nombres repetidos porque la identidad es el UUID:

```json
{
  "full_name": "Nombre de la gimnasta o conjunto",
  "club_name": "Club",
  "passing_order": 3
}
```

`passing_order` es opcional; si no se envía, se agrega al final. Para el orden
manual debe enviarse una permutación completa, sin omisiones ni duplicados:

```json
{
  "gymnast_ids": [
    "uuid-primera",
    "uuid-segunda",
    "uuid-tercera"
  ]
}
```

La eliminación conserva `score_entries` y `score_summaries` para trazabilidad,
pero la gimnasta deja de aparecer en las grillas. La acción
`GYMNAST_DELETED` queda en `audit_logs`.

Ejemplo de resolución que conserva la primera nota recibida:

```json
{}
```

Ejemplo de resolución que fija otro valor:

```json
{
  "value": "5,30"
}
```

### Publicación manual de categoría completa

No existe publicación parcial ni automática. Cada llamada autenticada crea una
fotografía nueva e inmutable de todas las gimnastas activas de la categoría:

| Método | Ruta | Uso |
| --- | --- | --- |
| `POST` | `/api/v1/championships/{id}/categories/{category_id}/publish` | Publica manualmente la categoría completa. Solo admite el campeonato `ACTIVE`. |
| `GET` | `/api/v1/public/championships/active` | Entrega el campeonato activo y sus categorías. Admite `query` para buscar por categoría, gimnasta o club. |
| `GET` | `/api/v1/public/championships/active/categories/{category_id}/results` | Lee sin autenticación la última fotografía de la categoría del campeonato activo. |

El `POST` no recibe cuerpo ni se ejecuta como efecto de guardar una nota. Cada
pulsación crea un `publication_batch` distinto con modo `FULL_CATEGORY`,
incluye los totales `0.00` y registra `CATEGORY_PUBLISHED` en auditoría.

Los resultados públicos solo contienen nombre, club, orden, posición y total;
no exponen notas individuales, DA/DB/A/E ni estados pendientes. Una corrección
posterior permanece privada hasta otro `POST`. Una gimnasta agregada después
de la última publicación aparece públicamente con `0.00` hasta republicar, y
una gimnasta eliminada desaparece inmediatamente.

La consulta de una categoría admite `query` y
`sort=passing_order|score`. El orden por puntaje utiliza total, E y A sin
exponer esos valores de desempate. La ruta Angular pública es `/resultados`;
funciona sin sesión, permite buscar, cambiar de categoría, ordenar y actualizar
manualmente la consulta.

---

API REST en Python Flask con MongoDB para el sistema de puntajes de gimnasia rítmica.

## Requisitos

- Python 3.8+
- MongoDB ejecutándose en `localhost:27017`
- pip

## Instalación

```bash
cd backend
pip install -r requirements.txt
```

## Configuración

El archivo `.env` contiene la configuración:

```
MONGODB_URI=mongodb://localhost:27017/
FLASK_PORT=8080
FLASK_DEBUG=True
CORS_ORIGINS=http://localhost:4200
```

## Ejecutar

```bash
python run.py
```

La API estará disponible en `http://localhost:8080`

## Endpoints

### POST /campeonatos
Crea un nuevo campeonato

**Body:**
```json
{
  "nombre": "Campeonato Nacional 2024"
}
```

**Response:**
```json
{
  "campeonato": "Campeonato Nacional 2024",
  "id": "campeonato_campeonato_nacional_2024",
  "success": true
}
```

---

### POST /campeonatos/{campeonato}/jueces
Agrega un juez al campeonato

**Body:**
```json
{
  "nombre": "Pancha",
  "rol": "A1"
}
```

Roles válidos: `DA`, `DB`, `E1`, `E2`, `E3`, `E4`, `A1`, `A2`, `A3`, `A4`, `L`

---

### POST /campeonatos/{campeonato}/orden-paso
Sube archivo Excel con orden de paso

**Body:** FormData con archivo Excel

**Response:**
```json
{
  "success": true,
  "categorias": ["MINI F", "PEQUE F", "INFANTIL C", ...]
}
```

---

### GET /campeonatos/{campeonato}/categorias/{categoria}
Obtiene todos los datos de una categoría

**Response:**
```json
{
  "categoria": "Infantil A",
  "gimnastas": [
    {
      "nombre": "Pancha",
      "club": "Club XYZ",
      "DA": 8.4,
      "DB": 7.6,
      "E": [1.2, 1.4, 1.3],
      "A": [0.8, 1.0],
      "Desc": 0.2,
      "puntajeTotal": 23.6
    }
  ]
}
```

---

### PUT /campeonatos/{campeonato}/categorias/{categoria}
Actualiza puntajes de una categoría

**Body:**
```json
{
  "gimnastas": [
    {
      "nombre": "Pancha",
      "DA": 8.4,
      "DB": 7.6,
      "E": [1.2, 1.4, 1.3],
      "A": [0.8, 1.0],
      "Desc": 0.2,
      "puntajeFrontend": 23.6
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "gimnastas": [
    {
      "nombre": "Pancha",
      "puntajeTotal": 23.6
    }
  ]
}
```

---

### GET /campeonatos/{campeonato}/export
Exporta resultados a Excel

**Response:** Archivo Excel descargable

---

## Estructura de MongoDB

Cada campeonato tiene su propia base de datos:
- Database: `campeonato_{nombre_normalizado}`

### Colecciones:

**`jueces`**
```json
{
  "nombre": "Pancha",
  "rol": "A1"
}
```

**`{categoria_normalizada}`** (ej: `mini_f`, `infantil_a`)
```json
{
  "nombre": "Pancha",
  "club": "Club XYZ",
  "DA": 8.4,
  "DB": 7.6,
  "E": [1.2, 1.4, 1.3],
  "A": [0.8, 1.0],
  "Desc": 0.2,
  "puntajeTotal": 23.6,
  "order": 0
}
```

**`metadata`**
```json
{
  "nombre_campeonato": "Campeonato Nacional 2024",
  "categorias": ["MINI F", "PEQUE F", ...],
  "created_at": "2024-01-28T..."
}
```

## Reglas de Cálculo de Puntajes

- **DA/DB**: Se suman directamente al total
- **E/A con 1 juez**: `10 - nota`
- **E/A con 2-3 jueces**: `10 - promedio(todas las notas)`
- **E/A con 4+ jueces**: `10 - promedio(excluyendo mayor y menor)`
- **Desc**: Se resta del total final

## Testing

Puedes probar los endpoints con curl:

```bash
# Crear campeonato
curl -X POST http://localhost:8080/campeonatos \
  -H "Content-Type: application/json" \
  -d '{"nombre": "Test Championship"}'

# Agregar juez
curl -X POST http://localhost:8080/campeonatos/campeonato_test_championship/jueces \
  -H "Content-Type: application/json" \
  -d '{"nombre": "Judge 1", "rol": "DA"}'

# Subir Excel
curl -X POST http://localhost:8080/campeonatos/campeonato_test_championship/orden-paso \
  -F "file=@CENTRO.xlsx"
```
