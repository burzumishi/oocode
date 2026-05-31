# 18 — Equipos de agentes (AgentTeam)

## Los 5 agentes de OOCode

OOCode incluye 5 agentes especializados que pueden trabajar de forma coordinada:

| ID | Emoji | Nombre | Especialidad |
|----|-------|--------|-------------|
| `main` | 🤖 | OOCode | Asistente general, orquesta a otros agentes |
| `coding` | 💻 | OOCode Coder | Programación, refactorización, LSP, tests |
| `home_office` | 📋 | OOCode Office | Documentación corporativa O365 (Word/Excel/PPT), email, calendario |
| `reasoning` | 🧠 | OOCode Reasoning | Razonamiento profundo, coordinación de equipos, análisis complejo |
| `webcrawler` | 🕷️ | WebCrawler | Búsqueda web con SearXNG, generación de informes, investigación |

## Configuración de agentes

Cada agente se define en `~/.oocode/oocode.json`:

```json
{
  "agents": {
    "list": [
      {
        "id":        "main",
        "name":      "OOCode",
        "emoji":     "🤖",
        "model":     "qwen3.5:9b",
        "workspace": "~/.oocode/workspace/main"
      },
      {
        "id":        "coding",
        "name":      "OOCode Coder",
        "emoji":     "💻",
        "model":     null,
        "workspace": "~/.oocode/workspace/coding"
      },
      {
        "id":        "home_office",
        "name":      "OOCode Office",
        "emoji":     "📋",
        "model":     null,
        "workspace": "~/.oocode/workspace/home_office"
      },
      {
        "id":        "reasoning",
        "name":      "OOCode Reasoning",
        "emoji":     "🧠",
        "model":     null,
        "workspace": "~/.oocode/workspace/reasoning"
      },
      {
        "id":        "webcrawler",
        "name":      "WebCrawler",
        "emoji":     "🕷️",
        "model":     null,
        "workspace": "~/.oocode/workspace/webcrawler"
      }
    ]
  }
}
```

Los agentes con `"model": null` heredan el modelo del padre cuando se lanzan como subagentes.

## Coordinación de agentes

### Cambio manual con `/switch`

```
/switch coding        # pasar al agente de programación
/switch reasoning     # pasar al agente de razonamiento
/switch main          # volver al agente principal
```

### Lanzamiento como subagente con `/spawn`

```
/spawn coding "refactoriza el módulo agent/loop.py para reducir complejidad"
/spawn home_office "genera un informe ejecutivo del proyecto en DOCX"
/spawn webcrawler "investiga las mejores prácticas de streaming SSE en Flask"
```

### Lanzamiento automático por el LLM

El agente principal puede lanzar subagentes directamente usando la herramienta `spawn_subagent`:

```
spawn_subagent(
  agent_id="coding",
  task="Analiza src/main.py y propone mejoras de rendimiento"
)
```

## AgentTeam — equipos programáticos

`AgentTeam` en `agent/tasks.py` permite coordinar múltiples agentes con persistencia:

```python
from agent.tasks import AgentTeam

# Crear equipo con lead agent
team = AgentTeam(
    team_id="refactor-2026-05-27",
    lead_agent_id="coding",
    members=["coding", "reasoning"]
)

# Añadir subtareas
team.add_subtask("Refactorizar agent/loop.py", "coding")
team.add_subtask("Analizar impacto de los cambios", "reasoning")

# Ejecutar y monitorizar
while not team.is_all_completed():
    pending = team.get_pending_subtasks()
    for subtask in pending:
        # ejecutar subtarea...
        team.complete_subtask(subtask["id"], resultado)

team.mark_completed()
```

### Métodos de AgentTeam

| Método | Descripción |
|--------|-------------|
| `add_subtask(description, assign_to)` | Añade subtarea asignada a un agente |
| `complete_subtask(subtask_id, result)` | Marca subtarea como completada con resultado |
| `get_pending_subtasks()` | Devuelve lista de subtareas pendientes |
| `is_all_completed()` | True si todas las subtareas están completadas |
| `mark_completed()` | Marca el equipo como completado |
| `to_dict()` | Serialización del equipo (guardado automático en JSON) |

### Persistencia

El estado del equipo se persiste en `~/.oocode/teams/<team_id>.json`:

```json
{
  "team_id": "refactor-2026-05-27",
  "lead_agent_id": "coding",
  "members": ["coding", "reasoning"],
  "subtasks": [
    {
      "id": "abc123",
      "description": "Refactorizar agent/loop.py",
      "assign_to": "coding",
      "status": "completed",
      "result": "Refactorización completada: 850→650 líneas",
      "created_at": "2026-05-27T10:00:00Z",
      "completed_at": "2026-05-27T10:30:00Z"
    }
  ],
  "status": "completed"
}
```

## Patrones de uso

### Patrón 1: Análisis + Implementación

El agente `reasoning` analiza y el agente `coding` implementa:

```bash
/spawn reasoning "analiza los requisitos del módulo de cache y diseña la arquitectura"
# (recibe el resultado del análisis)
/spawn coding "implementa el módulo de cache según el diseño: [resultado del reasoning]"
```

### Patrón 2: Desarrollo + Documentación

```bash
/spawn coding "implementa la nueva API REST en api/v2.py"
/spawn home_office "documenta la API en formato Word con ejemplos de uso"
```

### Patrón 3: Investigación + Implementación

```bash
/spawn webcrawler "investiga las mejores librerías Python para procesamiento de PDFs"
/spawn coding "integra la librería recomendada en mcp_servers/home_office_assistant.py"
```

### Patrón 4: Equipo completo con lead agent

```python
from agent.tasks import AgentTeam

team = AgentTeam(
    team_id="migration-api-v2",
    lead_agent_id="reasoning",
    members=["webcrawler", "coding", "home_office"]
)

team.add_subtask("Investigar estándares de migración", "webcrawler")
team.add_subtask("Implementar endpoints v2", "coding")
team.add_subtask("Generar documentación de migración", "home_office")
team.add_subtask("Revisar y coordinar resultados", "reasoning")
```

## Restricciones y consideraciones

### VRAM y paralelismo con multi-servidor

Los subagentes comparten el modelo de inferencia del padre (siempre `qwen3.5:9b` si el padre usa ese modelo). Con un solo servidor Ollama, los subagentes ejecutan en cola en la misma GPU.

Con varios servidores Ollama configurados (`extraHosts`), los subagentes se distribuyen en round-robin y ejecutan **en paralelo real**, uno por GPU:

```
equipo: [webcrawler, coding, home_office]  →  3 GPUs  →  ejecución simultánea
```

Ver `doc/12_subagents.md#multi-servidor-ollama-para-sub-agentes` para la configuración.

### Ejecución síncrona

Cuando el LLM lanza `spawn_subagent`, el agente padre bloquea hasta recibir el resultado. Los subagentes lanzados con `/spawn` corren en background (el REPL sigue respondiendo).

### Contexto independiente

Cada subagente comienza con un contexto vacío (solo su workspace propio). No hereda la conversación del padre, solo recibe la tarea como primer mensaje.

### Permisos heredados

El subagente hereda los permisos del padre, incluyendo el modo `elevated` si está activo.
