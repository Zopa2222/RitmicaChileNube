# 📄 Formato de Archivo Excel Requerido

Para que la carga de datos funcione correctamente, tu archivo Excel debe seguir esta estructura:

## 📋 Estructura Básica del Excel

### Hoja 1: "Categorías" (Obligatorio)
Debe contener las categorías del campeonato:

| Categoría | Edad Mínima | Edad Máxima |
|-----------|------------|------------|
| Infantil A | 6 | 7 |
| Infantil B | 8 | 9 |
| Pre-Júnior | 10 | 12 |
| Júnior | 13 | 15 |
| Senior | 16 | 999 |

---

### Hoja 2: "Orden de Paso" o "Gymnasts" (Obligatorio)
Contiene las gimnastas participantes:

| ID | Nombre | Apellido | Categoría | Club |
|----|--------|----------|-----------|------|
| 001 | María | López | Infantil A | Club A |
| 002 | Ana | García | Infantil B | Club B |
| 003 | Rosa | Martínez | Pre-Júnior | Club A |

---

## ✅ Requisitos Importantes

1. **Primera fila**: Debe contener los encabezados (nombres de columnas)
2. **Sin filas vacías**: Las filas en blanco pueden causar errores
3. **Formato**: Formato Excel estándar (.xlsx o .xls)
4. **Nombres únicos**: Cada gymnasta debe tener un ID único
5. **Categoría válida**: El nombre de la categoría debe coincidir exactamente con la definida

---

## ⚠️ Errores Comunes

| Error | Causa | Solución |
|-------|-------|----------|
| "Archivo no procesado" | Formato no es Excel | Guarda como .xlsx |
| "Categoría no válida" | Nombre no coincide | Verifica exactamente el nombre |
| "Datos duplicados" | Mismo ID dos veces | Asigna IDs únicos |
| "Fila vacía detectada" | Hay espacios en blanco | Elimina filas vacías |

---

## 📝 Descarga Plantilla

Se proporciona una **plantilla.xlsx** como referencia. Puedes:
1. Duplicarla
2. Completarla con tus datos
3. Subirla al sistema

---

## 🔍 Validaciones Automáticas

El sistema verifica automáticamente:
- ✓ Que todos los campos obligatorios estén completos
- ✓ Que los datos estén en el formato correcto
- ✓ Que no haya duplicados
- ✓ Que las categorías existan

Si hay errores, recibirás un mensaje especificando qué está mal.

---

**¿Tu Excel no carga?** Revisa esta checklist:
- [ ] El archivo es .xlsx o .xls
- [ ] Tiene encabezados en la primera fila
- [ ] No tiene filas vacías en medio de los datos
- [ ] Las categorías coinciden exactamente (mayúsculas/minúsculas)
- [ ] Todos los campos obligatorios están completos
