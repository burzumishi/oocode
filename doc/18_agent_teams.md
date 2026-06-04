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

El agente puede lanzar subagentes y equipos directamente como herramientas nativas:

**Un subagente:**
```
spawn_subagent(
  agent_id="coding",
  task="Analiza src/main.py y propone mejoras de rendimiento",
  timeout_seconds=300
)
```

**Equipo paralelo** (subtareas independientes en agentes especializados):
```
create_team(
  team_id="mi-equipo",
  lead_agent_id="reasoning",
  subtasks=[
    {"description": "Refactoriza agent/loop.py", "assign_to": "coding"},
    {"description": "Genera informe de cambios", "assign_to": "home_office"},
    {"description": "Investiga mejores prácticas", "assign_to": "webcrawler"}
  ]
)
run_team(team_id="mi-equipo")
```

**Fanout** (mismo agente, N chunks del mismo problema en paralelo):
```
spawn_fanout(
  agent_id="coding",
  task_chunks=[
    "Analiza agent/loop.py: detecta code smells",
    "Analiza ui/app.py: detecta code smells",
    "Analiza mcp_servers/: detecta code smells"
  ],
  timeout_seconds=120
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

## Herramientas LLM de orquestación

Desde v0.3.7 el agente puede usar estas herramientas de orquestación como cualquier otra herramienta nativa:

| Herramienta | Descripción | Cuándo usar |
|-------------|-------------|-------------|
| `spawn_subagent` | Lanza un subagente y espera resultado | Tarea delegada a un agente especializado |
| `create_team` | Crea equipo con subtareas para múltiples agentes | Tarea descomponible en partes paralelas independientes |
| `run_team` | Ejecuta el equipo y devuelve resultados | Tras `create_team` |
| `spawn_fanout` | N chunks del mismo problema en paralelo (mismo agente) | Análisis de repo grande, divide-and-conquer |
| `explore` | Exploración profunda de solo lectura en una llamada | Mapear código/fuentes antes de decidir |

> **Dispatch secuencial (v0.4.2):** las herramientas de orquestación nunca se ejecutan en paralelo dentro del `ThreadPoolExecutor`, aunque el LLM las batchee con `read_file`/`grep_code`. Su cabecera y su streaming `│` solo se renderizan en la rama secuencial; paralelizarlas dejaba el output del subagente "encerrado" en el bloque anterior. Para paralelismo real usa `spawn_fanout` (mismo agente, N chunks) o `create_team` (dominios distintos), que tienen concurrencia interna.

### Narración del equipo (v0.4.2)

Para que el usuario siga lo que hace el equipo, el agente coordinador debe:

1. **Antes** de `create_team`/`run_team`/`spawn_fanout`: anunciar en una frase la composición y el reparto ("Monto un equipo: Coder → API, Office → informe").
2. **Después** de `run_team`/`spawn_fanout`: **sintetizar** qué aportó cada agente (combinar hallazgos, destacar lo completado, mencionar errores) antes de cerrar la tarea con `task_done()` — nunca cerrar en silencio saltándose la síntesis.

En el WebUI, la **team-bar** (cabecera de equipo bajo el prompt) muestra en vivo una línea compacta `📋 Agente principal 💬 💻 Subagente · N subagente(s)`. El detalle de cada subagente —su tarea, plan, texto y herramientas— vive en su propio **bloque dentro de la conversación**, no en la barra de estado.

### `spawn_subagent` — parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `agent_id` | str | ID del agente destino |
| `task` | str | Tarea a ejecutar |
| `timeout_seconds` | int | Segundos máximos (0 = sin límite) |

### `spawn_fanout` — parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `agent_id` | str | Agente para todos los chunks |
| `task_chunks` | list[str] | Cada chunk es una subtarea independiente |
| `timeout_seconds` | int | Timeout por chunk (0 = sin límite) |
| `max_concurrent` | int | Máximo paralelo (default: semáforo global) |

### Timeout y watchdog

Todos los métodos de spawn aceptan `timeout_seconds`. Al expirar, un watchdog thread dispara el `kill_event` del subagente, que termina limpiamente en la siguiente iteración del loop. El resultado indica el error de timeout.

### Plan ↔ TaskManager

Cuando el agente ejecuta un plan multi-tarea con `_plan_tasks`, las tareas se sincronizan automáticamente con `TaskManager`:
- Visibles en `/task list` durante la ejecución
- Sobreviven un reinicio del agente — se restauran en el siguiente arranque
- Distinguidas del resto de tareas con el marcador interno `__plan__`

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
