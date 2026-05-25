# HEARTBEAT.md — 🤖 Tareas de Mantenimiento

_Tareas periódicas para mantener el workspace en buen estado._

## Tareas Diarias

### ✅ Verificar commits pendientes
```bash
git_status()
git_diff()
```

### ✅ Actualizar memoria si hay sesiones recientes
- Leer `memory/YYYY-MM-DD.md`
- Extraer decisiones y lecciones importantes
- Actualizar `MEMORY.md` con lo que merece la pena guardar

## Tareas Semanales

### ✅ Backup del workspace
```bash
git add -A
git commit -m "workspace backup"
```

### ✅ Revisar memoria de sesiones
- Leer `memory/YYYY-MM-DD.md` de las últimas 7 días
- Extraer decisiones, lecciones y eventos relevantes
- Actualizar `MEMORY.md` con lo que merece la pena guardar
- Eliminar de `MEMORY.md` lo que ya no es relevante

### ✅ Revisar TODOs
```python
todo_list(path="~/.oocode/workspace/main")
```

## Checklist de Mantenimiento

### Diario
- [ ] Revisar commits pendientes de push
- [ ] Comprobar tests fallidos
- [ ] Actualizar MEMORY.md si hay sesiones recientes sin procesar
- [ ] Limpiar ficheros temporales si es necesario

### Semanal
- [ ] Backup del workspace con git
- [ ] Revisar memoria de sesiones de la última semana
- [ ] Limpiar memoria obsoleta de MEMORY.md
- [ ] Revisar TODOs pendientes

### Mensual
- [ ] Revisar y actualizar OOCODE.md con nuevas herramientas
- [ ] Revisar IDENTITY.md y SOUL.md
- [ ] Actualizar USER.md con nuevos proyectos
- [ ] Revisar TOOLS.md con nuevas herramientas disponibles
- [ ] Limpiar memoria antigua de memory/YYYY-MM-DD.md

## Ejemplo de Checklist Personalizado

Añade aquí tareas específicas de tu proyecto:

```markdown
- [ ] Revisar commits pendientes de push
- [ ] Comprobar tests fallidos
- [ ] Actualizar MEMORY.md si hay sesiones recientes sin procesar
- [ ] Revisar TODOs pendientes
- [ ] Limpiar ficheros temporales
```

## Líneas Rojas de Mantenimiento

- **NUNCA** borrar `memory/YYYY-MM-DD.md` sin revisar primero
- **NUNCA** borrar de `MEMORY.md` decisiones técnicas importantes
- **SÍ** eliminar de `MEMORY.md` lo que es obsoleto o ya no relevante
- **SÍ** archivar decisiones en `MEMORY.md` antes de borrar de `memory/YYYY-MM-DD.md`

## Debug

- **Limpiar historial REPL:** `rm ~/.oocode/history`
- **Config:** `~/.oocode/oocode.json`
- **Memoria:** `~/.oocode/workspace/main/memory/`

## Proyectos Activos


## Líneas Rojas de Mantenimiento

- **NUNCA** borrar `memory/YYYY-MM-DD.md` sin revisar primero
- **NUNCA** borrar de `MEMORY.md` decisiones técnicas importantes
- **SÍ** eliminar de `MEMORY.md` lo que es obsoleto o ya no relevante
- **SÍ** archivar decisiones en `MEMORY.md` antes de borrar de `memory/YYYY-MM-DD.md`

---

*Última actualización: 2026-05-22*
