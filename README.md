# Gymnastics Scoring System - Angular Frontend

Sistema de puntajes para gimnasia rítmica desarrollado en Angular 17.

## Características

- ✅ Configuración de campeonatos con carga de Excel
- ✅ Gestión de jueces con validación de roles
- ✅ Grilla tipo Excel para ingreso de puntajes
- ✅ Cálculo automático de puntajes según reglas FIG
- ✅ Validación visual de diferencias >0.6 entre jueces
- ✅ Reordenamiento de gimnastas con drag & drop
- ✅ Exportación a Excel ordenada por puntaje
- ✅ Vista pública del campeonato activo en `/resultados`
- ✅ Inicio de sesión cloud con permisos por rol y protección CSRF

## Acceso cloud y rutas protegidas

La aplicación restaura la sesión desde `GET /api/v1/auth/me` antes de
resolver las rutas. La cookie de acceso es HttpOnly y Angular agrega
automáticamente `X-CSRF-TOKEN` a cada `POST`, `PUT`, `PATCH` o `DELETE`
dirigido al backend.

- `/ingresar`: inicio de sesión para superadministrador, administrador y juez.
- `/administracion`: inicio privado del administrador global.
- `/superadministracion`: inicio privado del superadministrador.
- `/cabina-juez`: inicio privado del juez dentro de su ventana vigente.
- `/resultados`: consulta pública, sin autenticación.

Las vistas privadas heredadas (`/championships`, `/setup`, `/scoring` y
`/export`) ya están protegidas para administrador o superadministrador. Su
contenido se irá conectando a PostgreSQL por bloques; las nuevas integraciones
deben utilizar los servicios `cloud-*-api.service.ts` y no ampliar
`api.service.ts`, que se conserva temporalmente para las rutas MongoDB.

En desarrollo Angular usa `http://localhost:8080`. La compilación de
producción usa `/api` en el mismo origen y Nginx conserva ese prefijo al
reenviarlo al backend, evitando cookies de sesión entre dominios distintos.

## Requisitos

- Node.js 18+
- npm 9+
- Angular CLI 17+

## Instalación

```bash
npm install
```

## Desarrollo

```bash
npm start
```

La aplicación estará disponible en `http://localhost:4200`

## Estructura del Proyecto

```
src/
├── app/
│   ├── core/
│   │   ├── models/          # Modelos de datos
│   │   └── services/        # Servicios (API, Excel, Scoring, State)
│   ├── features/
│   │   ├── setup/           # Vista de configuración
│   │   ├── scoring/         # Vista de ingreso de puntajes
│   │   └── export/          # Vista de exportación
│   ├── app.component.ts
│   ├── app.routes.ts
│   └── app.config.ts
└── styles.scss
```

## Reglas de Puntaje

- **DA/DB**: Se suman directamente al total
- **E/A con 1 juez**: 10 - nota
- **E/A con 2-3 jueces**: 10 - promedio(todas las notas)
- **E/A con 4 jueces**: 10 - promedio(excluyendo mayor y menor)
- **Desc**: Se resta del total final

## API Backend

La aplicación espera una API REST en `http://localhost:8080/api` con los siguientes endpoints:

- `POST /championships` - Crear campeonato
- `GET /championships/:id` - Obtener campeonato
- `POST /championships/:id/upload` - Subir Excel
- `GET /championships/:id/categories` - Obtener categorías
- `PUT /categories/:id` - Actualizar categoría
- `GET /championships/:id/export` - Exportar a Excel

## Build

```bash
npm run build
```

Los archivos de producción se generarán en `dist/gymnastics-scoring/`
