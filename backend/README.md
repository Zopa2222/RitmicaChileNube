# Flask Backend API - Gymnastics Scoring System

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
