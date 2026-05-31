# 🔄 Workflows de Análisis Multi-Fase

**Fecha:** 2026-05-25  
**Estado:** ✅ DOCUMENTADO  
**Objetivo:** Crear workflows de análisis multi-fase con `AgentTeam`

---

## 📋 Introducción

Los workflows de análisis multi-fase permiten ejecutar tareas complejas en múltiples fases, coordinadas por un lead agent.

**Características:**
- ✅ Análisis en fases secuenciales
- ✅ Coordinación con `AgentTeam`
- ✅ Persistencia entre fases
- ✅ Reportes intermedios

---

## 🎯 Ejemplo 1: Análisis de Rendimiento Multi-Fase

**Fases:**
1. **Fase 1:** Análisis de métricas
2. **Fase 2:** Identificación de cuellos de botella
3. **Fase 3:** Propuesta de optimizaciones
4. **Fase 4:** Validación de cambios

```python
from agent.tasks import AgentTeam

# 1. Crear equipo de análisis
team = AgentTeam(
    team_id="analisis-rendimiento-2026-05-25",
    lead_agent_id="reasoning",
    members=["reasoning", "coding", "main"]
)

# 2. Añadir subtasks por fase
team.add_subtask(
    description="Fase 1: Análisis de métricas",
    assign_to="reasoning"
)

team.add_subtask(
    description="Fase 2: Identificar cuellos de botella",
    assign_to="reasoning"
)

team.add_subtask(
    description="Fase 3: Proponer optimizaciones",
    assign_to="coding"
)

team.add_subtask(
    description="Fase 4: Validar cambios",
    assign_to="main"
)

# 3. Ejecutar workflow
while not team.is_all_completed():
    pending = team.get_pending_subtasks()
    for subtask in pending:
        # Ejecutar análisis de la fase
        result = ejecutar_fase(subtask["description"])
        team.complete_subtask(subtask["id"], result)

# 4. Generar informe
team.generar_informe()
```

---

## 🎯 Ejemplo 2: Refactorización Multi-Fichero

**Fases:**
1. **Fase 1:** Análisis de impacto
2. **Fase 2:** Refactorización
3. **Fase 3:** Tests
4. **Fase 4:** Validación

```python
from agent.tasks import AgentTeam

# 1. Crear equipo de refactorización
team = AgentTeam(
    team_id="refactor-mud-2026-05-25",
    lead_agent_id="coding",
    members=["coding", "reasoning", "main"]
)

# 2. Añadir subtasks por fichero
team.add_subtask(
    description="Fase 1: Analizar mud.h",
    assign_to="reasoning"
)

team.add_subtask(
    description="Fase 2: Refactorizar mud.h",
    assign_to="coding"
)

team.add_subtask(
    description="Fase 3: Ejecutar tests mud.h",
    assign_to="main"
)

team.add_subtask(
    description="Fase 4: Validar mud.h",
    assign_to="main"
)

# 3. Repetir para cada fichero
for fichero in ["mud.h", "mud2.h", "mud3.h"]:
    team_id = f"refactor-{fichero}-2026-05-25"
    team = AgentTeam(team_id, "coding", members=["coding", "reasoning", "main"])
    
    # Añadir subtasks...
    # Ejecutar workflow...
```

---

## 🎯 Ejemplo 3: Testing Multi-Fichero

**Fases:**
1. **Fase 1:** Ejecutar tests unitarios
2. **Fase 2:** Ejecutar tests de integración
3. **Fase 3:** Generar reporte de cobertura
4. **Fase 4:** Validar resultados

```python
from agent.tasks import AgentTeam

# 1. Crear equipo de testing
team = AgentTeam(
    team_id="testing-multiphase-2026-05-25",
    lead_agent_id="main",
    members=["coding", "reasoning", "main"]
)

# 2. Añadir subtasks por fichero
for fichero in ["src/*.py", "tests/*.py"]:
    team.add_subtask(
        description=f"Fase 1: Tests unitarios {fichero}",
        assign_to="coding"
    )
    
    team.add_subtask(
        description=f"Fase 2: Tests integración {fichero}",
        assign_to="reasoning"
    )
    
    team.add_subtask(
        description=f"Fase 3: Reporte cobertura {fichero}",
        assign_to="main"
    )

# 3. Ejecutar testing
while not team.is_all_completed():
    # Ejecutar tests...
    team.complete_subtask(...)
```

---

## 🎯 Ejemplo 4: Documentación Multi-Agente

**Fases:**
1. **Fase 1:** Documentar API
2. **Fase 2:** Documentar arquitectura
3. **Fase 3:** Documentar ejemplos
4. **Fase 4:** Revisión y formato

```python
from agent.tasks import AgentTeam

# 1. Crear equipo de documentación
team = AgentTeam(
    team_id="documentacion-2026-05-25",
    lead_agent_id="home_office",
    members=["home_office", "coding", "reasoning"]
)

# 2. Añadir subtasks por fase
team.add_subtask(
    description="Fase 1: Documentar API",
    assign_to="home_office"
)

team.add_subtask(
    description="Fase 2: Documentar arquitectura",
    assign_to="reasoning"
)

team.add_subtask(
    description="Fase 3: Documentar ejemplos",
    assign_to="coding"
)

team.add_subtask(
    description="Fase 4: Revisión y formato",
    assign_to="home_office"
)

# 3. Ejecutar documentación
while not team.is_all_completed():
    # Generar documentación...
    team.complete_subtask(...)
```

---

## 🔄 Flujo de Trabajo Multi-Fase

### 1. Crear Equipo

```python
team = AgentTeam(
    team_id="workflow-nombre",
    lead_agent_id="lead_agent",
    members=["member1", "member2", "member3"]
)
```

### 2. Añadir Subtasks por Fase

```python
for fase in ["fase1", "fase2", "fase3", "fase4"]:
    team.add_subtask(
        description=f"{fase}: Descripción",
        assign_to="agente_asignado"
    )
```

### 3. Ejecutar Workflow

```python
while not team.is_all_completed():
    pending = team.get_pending_subtasks()
    for subtask in pending:
        # Ejecutar fase
        result = ejecutar_fase(subtask["description"])
        team.complete_subtask(subtask["id"], result)
```

### 4. Generar Informe

```python
# Generar informe de todas las fases
informe = team.generar_informe()
print(informe)
```

---

## 📊 Reportes Intermedios

### Generar Reporte de Progreso

```python
def generar_reporte_progreso(team):
    """Genera reporte de progreso del workflow."""
    report = {
        "team_id": team.team_id,
        "status": team.status,
        "subtasks": team.subtasks,
        "results": team.results,
        "pending": len(team.get_pending_subtasks()),
        "completed": len([s for s in team.subtasks if s["status"] == "completed"]),
    }
    return report
```

### Generar Reporte Final

```python
def generar_reporte_final(team):
    """Genera informe final del workflow."""
    report = {
        "team_id": team.team_id,
        "status": team.status,
        "completed_at": team.completed_at,
        "subtasks": team.subtasks,
        "results": team.results,
        "summary": f"✅ {len(team.results)} subtasks completadas",
    }
    return report
```

---

## 📁 Persistencia entre Fases

**Estado guardado en:** `~/.oocode/teams/<team_id>.json`

**Estructura:**
```json
{
  "team_id": "analisis-rendimiento-2026-05-25",
  "lead_agent_id": "reasoning",
  "members": ["reasoning", "coding", "main"],
  "subtasks": [
    {
      "id": "fase1-123",
      "description": "Fase 1: Análisis de métricas",
      "assign_to": "reasoning",
      "status": "completed",
      "result": "✅ Métricas analizadas",
      "created_at": "2026-05-25T10:00:00Z",
      "completed_at": "2026-05-25T10:30:00Z"
    }
  ],
  "results": {
    "fase1-123": "✅ Métricas analizadas"
  },
  "status": "active",
  "created_at": "2026-05-25T10:00:00Z"
}
```

---

## 🎯 Consideraciones

### 1. Orden de Ejecución

- ✅ Fases secuenciales (1→2→3→4)
- ✅ Fases paralelas si no hay dependencias
- ✅ Lead agent coordina orden

### 2. Dependencias entre Fases

```python
# Fase 2 depende de Fase 1
team.add_subtask(
    description="Fase 2: Depende de Fase 1",
    assign_to="reasoning",
    depends_on="fase1-123"  # ID de subtask anterior
)
```

### 3. Rollback entre Fases

```python
# Si una fase falla, rollback automático
team.rollback(fase_id)
```

---

## 📚 Recursos Adicionales

### Documentación

- `agent/tasks.py` — Implementación de `AgentTeam`
- `agent/subagent.py` — Spawn con prioridades
- `agent/session.py` — BackgroundSession

### Hooks

- `/hooks builtin test_suite_delta` — Tests antes/después
- `/hooks builtin interface_change_detector` — Cambios de interfaz

### Plantillas

- `doc/AGENTTEAM_EJEMPLOS.md` — Ejemplos de uso
- `doc/WORKFLOWS_MULTI_FASE.md` — Este documento

---

*Este documento se actualiza automáticamente con cada sesión significativa.*

---

*Última actualización: 2026-05-25*