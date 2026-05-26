# Rediseño del Sistema de Jueces: Bancas, Jornadas, Planilla y Línea

## Contexto

Actualmente el campeonato tiene una **lista plana de jueces** compartida por todas las categorías. El nuevo diseño requiere:

1. **2 Bancas (A y B)** — cada una con su propio set de jueces (personas distintas)
2. **Jornada AM/PM** — un mismo juez puede tener un rol distinto en AM vs PM, o trabajar solo en una jornada
3. **Rol "Planilla"** (nuevo) — 0 a 2 por banca, solo se registran, no afectan puntaje ni aparecen en scoring
4. **Jueces de Línea (L)** — 0 o más, solo se registran, no tienen columna (el descuento se escribe manualmente en "Desc")

### Decisiones de diseño resueltas

| Pregunta | Respuesta |
|---|---|
| ¿Cómo se asigna categoría a banca? | **Automático desde el Excel**: columnas izquierda = Banca A, derecha = Banca B |
| ¿Columna para jueces L? | **No**. L se suma manualmente y se escribe en Desc |
| ¿Planilla en UI de scoring? | **No**. Solo se registran al crear campeonato |
| ¿Rol puede ser solo AM o solo PM? | **Sí**. roleAM o rolePM pueden ser vacíos |

---

## Proposed Changes

### 1. Modelos de Datos (Frontend)

---

#### [MODIFY] [judge.model.ts](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/core/models/judge.model.ts)

```typescript
export type JudgeRole = 'DA' | 'DB' | 'E' | 'A' | 'L' | 'P';

// Judge as registered per banca (setup)
export interface BancaJudge {
    name: string;
    roleAM: JudgeRole | null;  // null = no trabaja en AM
    rolePM: JudgeRole | null;  // null = no trabaja en PM
}

// Judge resolved for scoring (runtime) — existing interface, kept as-is
export interface Judge {
    name: string;
    role: JudgeRole;
    index?: number;
}
```

- Mantener `Judge` y `getJudgeDisplayName()` tal como están (usados por el scoring service)
- Agregar `BancaJudge` para la configuración de setup
- Ya no se usan `DA2` / `DB2` como roles separados; si hay 2 DA, son 2 jueces con role `DA`

#### [MODIFY] [championship.model.ts](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/core/models/championship.model.ts)

```typescript
export interface Championship {
    id?: string;
    name: string;
    bancaA: BancaJudge[];
    bancaB: BancaJudge[];
    categoriasBanca: { [catName: string]: 'A' | 'B' };  // from Excel parsing
    categories: Category[];
}
```

---

### 2. Excel Parser (Backend) — Asignación automática de banca

---

#### [MODIFY] [excel_service.py](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/backend/app/services/excel_service.py)

El parser ya detecta `column_groups` (grupos de columnas NOMBRE/CLUB/CATEGORIA). Cambios:

- Trackear el índice del grupo al parsear datos:
  ```python
  for group_idx, (nombre_idx, club_idx, cat_idx) in enumerate(column_groups):
      banca = 'A' if group_idx == 0 else 'B'
  ```
- Retornar un diccionario adicional `categorias_banca: { cat_name: 'A' | 'B' }` junto con `categories`
- `parse_excel_file()` retorna `(categories, categorias_banca)` en vez de solo `categories`

#### [MODIFY] [championships.py](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/backend/app/routes/championships.py)

- `upload_orden_paso`: Guardar `categorias_banca` en metadata
- `list_categories` y `list_championships`: Devolver `categorias_banca` en la respuesta
- `add_judge`: Aceptar campos `banca`, `rol_am`, `rol_pm`:
  ```json
  { "nombre": "María", "banca": "A", "rol_am": "DA", "rol_pm": "DA" }
  ```
  - `rol_am` y `rol_pm` pueden ser `null`
  - Almacenar en MongoDB: `{ nombre, banca, rol_am, rol_pm }`
  - Ya no validar por rol único (un rol puede tener varios jueces)

---

### 3. Setup Component — UI de inscripción de jueces

---

#### [MODIFY] [setup.component.html](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/features/setup/setup.component.html)

Dos secciones para Banca A y Banca B, cada juez con nombre + rol AM + rol PM:

```
┌────────────────────────────────────────────────────────┐
│  🏷 BANCA A                         [+ Agregar Juez]  │
│  ┌─────────────┬───────────┬───────────┬────┐         │
│  │ Nombre      │ Rol AM ▼  │ Rol PM ▼  │ 🗑 │         │
│  │ María López │ DA        │ DA        │ 🗑 │         │
│  │ Juan Pérez  │ E         │ A         │ 🗑 │         │
│  │ Ana Silva   │ E         │ — (vacío) │ 🗑 │         │
│  └─────────────┴───────────┴───────────┴────┘         │
│                                                        │
│  🏷 BANCA B                         [+ Agregar Juez]  │
│  ┌─────────────┬───────────┬───────────┬────┐         │
│  │ Nombre      │ Rol AM ▼  │ Rol PM ▼  │ 🗑 │         │
│  │ Carlos Díaz │ DA        │ DA        │ 🗑 │         │
│  │ Laura Muñoz │ E         │ E         │ 🗑 │         │
│  └─────────────┴───────────┴───────────┴────┘         │
│                                                        │
│  📋 Reglas de Jueces (por banca+jornada):             │
│  • DA: 1–2 · DB: 1–2 · E: 1–4 · A: 1–4              │
│  • L: 0+ (Línea, no genera columna)                   │
│  • P: 0–2 (Planilla, solo registro)                   │
│  • Rol AM o PM pueden quedar vacíos                   │
└────────────────────────────────────────────────────────┘
```

- Opciones del dropdown de rol: `DA, DB, E, A, L, P` + opción vacía `"—"`
- Al seleccionar rol AM, auto-completar rol PM con el mismo valor (editable)
- Al menos un rol (AM o PM) debe estar definido por juez

#### [MODIFY] [setup.component.ts](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/features/setup/setup.component.ts)

- Form: `bancaA: FormArray`, `bancaB: FormArray` (cada item: `name`, `roleAM`, `rolePM`)
- `addJudge(banca: 'A' | 'B')`, `removeJudge(banca, index)`
- Validación por banca+jornada (AM y PM independientes):
  - DA: 1–2, DB: 1–2, E: 1–4, A: 1–4, L: 0+, P: 0–2
  - Validar solo los jueces que tienen rol asignado para esa jornada
- `onSubmit()`: enviar jueces al backend con `{ nombre, banca, rol_am, rol_pm }`

---

### 4. Scoring Component — Selector de jornada

---

#### [MODIFY] [scoring.component.html](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/features/scoring/scoring.component.html)

- Mostrar en el header: etiqueta de banca (auto-detectada, no editable) + selector de jornada AM/PM:
  ```html
  <div class="banca-jornada-info">
      <span class="banca-badge">Banca {{ currentBanca }}</span>
      <mat-button-toggle-group [(ngModel)]="currentJornada" (change)="onJornadaChange()">
          <mat-button-toggle value="AM">AM</mat-button-toggle>
          <mat-button-toggle value="PM">PM</mat-button-toggle>
      </mat-button-toggle-group>
  </div>
  ```

#### [MODIFY] [scoring.component.ts](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/features/scoring/scoring.component.ts)

- Nuevas propiedades: `currentBanca: 'A' | 'B'`, `currentJornada: 'AM' | 'PM' = 'AM'`
- `categoriasBanca: { [name: string]: 'A' | 'B' }` — cargado desde backend
- Al seleccionar categoría:
  1. Detectar banca automáticamente: `this.currentBanca = this.categoriasBanca[category.name]`
  2. Resolver jueces activos con `resolveActiveJudges()`
  3. Recalcular `scoreColumns`
- `resolveActiveJudges()`:
  - Toma `bancaA` o `bancaB` según `currentBanca`
  - Para cada `BancaJudge`, usa `roleAM` o `rolePM` según `currentJornada`
  - **Filtra** roles `null`, `'L'`, y `'P'` (no generan columna)
  - Asigna indexes: múltiples E → E1, E2...; múltiples A → A1, A2...
  - Retorna `Judge[]` compatible con `ScoringService`
- `onJornadaChange()`: recalcula jueces activos, columnas, y totales
- Import `MatButtonToggleModule`

#### [MODIFY] [scoring.component.scss](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/features/scoring/scoring.component.scss)

- Estilos para `.banca-badge` (pill con gradiente) y `.banca-jornada-info`

---

### 5. Scoring Service

---

#### [MODIFY] [scoring.service.ts](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/core/services/scoring.service.ts)

- `getScoreColumns()`: Remover la línea que añade columna `'L'` (L ya no genera columna)
- No necesita otros cambios — recibe `Judge[]` ya resueltos

---

### 6. Championship Service

---

#### [MODIFY] [championship.service.ts](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/core/services/championship.service.ts)

- Remover `getJudges()`
- Agregar `getBancaJudges(banca: 'A' | 'B'): BancaJudge[]`

---

### 7. Championships List (Retomar campeonatos)

---

#### [MODIFY] [championships-list.component.ts](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/features/championships-list/championships-list.component.ts)

- `ChampionshipItem.jueces` → formato nuevo: `{ nombre, banca, rol_am, rol_pm }[]`
- `editChampionship()`: Reconstruir `bancaA[]` y `bancaB[]` desde datos del backend
- Fallback para formato antiguo: si un juez no tiene `banca`, asumir Banca A

---

### 8. API Service (Frontend)

---

#### [MODIFY] [api.service.ts](file:///c:/Users/smedi/OneDrive/Desktop/RitmicaChile/Etapa1/RitmicaChile/src/app/core/services/api.service.ts)

- `addJudge()`: payload cambia a `{ nombre, banca, rol_am, rol_pm }`

---

## Resumen de archivos (12 archivos)

| Archivo | Cambio |
|---|---|
| `judge.model.ts` | Agregar `'P'`, `'L'`, crear `BancaJudge` |
| `championship.model.ts` | `bancaA/B` + `categoriasBanca` |
| `setup.component.html` | 2 secciones de banca con AM/PM |
| `setup.component.ts` | 2 FormArrays, validación por banca+jornada |
| `scoring.component.html` | Badge banca + selector jornada |
| `scoring.component.ts` | Auto-detect banca, resolver jueces activos |
| `scoring.component.scss` | Estilos selector |
| `scoring.service.ts` | Remover columna L |
| `championship.service.ts` | `getBancaJudges()` |
| `championships-list.component.ts` | Mapear formato nuevo |
| `api.service.ts` | Payload actualizado |
| `excel_service.py` | Trackear banca por grupo de columnas |
| `championships.py` | Almacenar banca por juez y categoría |

---

## Verification Plan

### Build
```bash
npx ng build
```

### Manual Testing
1. **Setup**: Crear campeonato con Banca A (DA, DB, 3E, 2A, 1L, 1P) y Banca B (DA, DB, 2E, 3A) con roles distintos AM/PM
2. **Excel**: Subir Excel con 2 grupos → verificar que categorías se asignan a bancas correctamente
3. **Scoring**: Seleccionar categoría → verificar que banca se auto-detecta y columnas son correctas
4. **Jornada**: Cambiar AM→PM → verificar que las columnas se actualizan según los roles PM
5. **Persistencia**: Guardar y recargar → verificar datos
6. **Retomar**: Abrir campeonato desde lista → verificar que carga correctamente
