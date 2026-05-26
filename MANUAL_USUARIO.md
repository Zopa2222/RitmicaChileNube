# 📋 Manual de Usuario - Sistema de Puntajes Rítmica Chile

## 📌 PASO 1: Pantalla de Inicio

Al abrir la aplicación verá la **pantalla principal** con dos opciones:

### Opción A: "Crear Nuevo Campeonato"
- Haga clic en el botón **"Crear Nuevo Campeonato"**
- Se abrirá el formulario de configuración

### Opción B: "Ver Campeonatos"
- Accede al historial de campeonatos anteriores
- Puede revisar, editar o exportar resultados

---

## 🔧 PASO 2: Configurar Campeonato

### 2.1 Información Básica
1. **Nombre del Campeonato**
   - Escriba el nombre (ej: "1er Clasificatorio Zona Sur 2026")
   - Este nombre aparecerá en todos los reportes

### 2.2 Cargar Orden de Paso (Excel)
1. Haga clic en el área de **"Orden de Paso (Excel)"**
2. Seleccione su archivo Excel
3. El archivo debe contener:
   - Nombre de las categorías
   - Nombre de las gimnastas
   - Orden de presentación

> ⚠️ **Nota**: El archivo Excel debe respetar el formato estándar. 

### 2.3 Agregar Jueces
1. Haga clic en **"Agregar Juez"** (botón verde con +)
2. Complete los datos de cada juez:
   - **Nombre**: Nombre completo del juez
   - **Rol**: Seleccione entre las opciones disponibles (DA, DB, E, etc.)

3. Agregue todos los jueces necesarios siguiendo este proceso

### 2.4 Guardar Información
- Una vez completados todos los datos, haga clic en **"Iniciar Campeonato"**
- El sistema verificará los datos y confirmará que todo está correcto

---

## 🎯 PASO 3: Ingresar Puntajes

### 3.1 Interfaz de Puntajes
- Se abrirá una **grilla tipo Excel** con todas las gimnastas
- Cada fila es una gimnasta
- Cada columna es un juez

### 3.2 Cómo Ingresar Puntos
1. Haga clic en la celda correspondiente
2. Escriba el puntaje (números decimales, ej: 8.5)
3. Presione **Enter** para guardar
4. El sistema calculará automáticamente:
   - El promedio de jueces
   - Los puntajes finales según reglas FIG
   - Diferencias entre jueces (si supera 0.6 se marca en rojo)

### 3.3 Validaciones Automáticas
- **Diferencias >0.6**: Se marcan en rojo para revisar
- **Cálculos FIG**: Se aplican automáticamente según cantidad de jueces
- **Campos incompletos**: Se destacan en amarillo

### 3.4 Editar Orden (Opcional)
- Puede reordenar las gimnastas manualmente
- Use **arrastrar y soltar** (drag & drop) para cambiar posiciones
- El sistema actualizará automáticamente el ranking

---

## 📊 PASO 4: Mostrar Resultados

### 4.1 Generar Reporte
1. Haga clic en **"Exportar a Excel"**
2. El sistema generará un archivo Excel con:
   - Ranking final ordenado por puntaje
   - Detalles de puntajes por juez
   - Cálculos de DA, DB, E/A
   - Descuentos aplicados

### 4.2 Descargar Archivo
- El archivo se descargará automáticamente
- Nombre: `Resultados_[Nombre_Campeonato].xlsx`
- Listo para compartir con los participantes

---

## 💡 Tips Útiles

| Tip | Descripción |
|-----|------------|
| **Ctrl+S** | Guarda automáticamente los puntajes |
| **Filtrar jueces** | Use búsqueda para encontrar jueces rápidamente |
| **Historial** | Todos los campeonatos se guardan en "Ver Campeonatos" |
| **Revisar diferencias** | Las celdas rojas indican diferencias significativas entre jueces |
| **Respaldo** | Descargue los resultados en Excel como respaldo |

---

## ❓ Preguntas Frecuentes

**P: ¿Qué pasa si cometo un error al ingresar un puntaje?**
R: Simplemente haga clic en la celda nuevamente y escriba el valor correcto. El sistema se actualiza automáticamente.

**P: ¿Puedo editar campeonatos anteriores?**
R: Sí. En "Ver Campeonatos" encontrará todo el historial. Haga clic en cualquiera para editarlo.

**P: ¿Cómo se calculan los puntajes finales?**
R: El sistema aplica automáticamente las reglas FIG:
- DA/DB: Se suman directamente
- E/A con 1 juez: 10 - puntaje
- E/A con 2-3 jueces: 10 - promedio
- E/A con 4 jueces: 10 - promedio (sin máx y mín)
- Descuentos: Se restan del total

**P: ¿Qué hago si tengo problemas técnicos?**
R: Contacte al administrador del sistema. Adjunte el archivo del campeonato si es necesario.

---

## 📞 Soporte

Si tiene preguntas o enfrenta problemas:
- Consulte con su coordinador
- Verifique que el archivo Excel tenga el formato correcto
- Pruebe actualizando la página (F5)

---

**Última actualización**: Mayo 2026  
**Sistema**: Ritmica Chile - Puntajes v2.0
