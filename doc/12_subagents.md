# 12 — Sub-agentes

Un sub-agente es una instancia aislada de `AgentLoop` que el agente principal puede lanzar para delegar una tarea. Tiene su propio workspace y su propio historial de conversación, pero comparte el modelo de inferencia y el cliente de embeddings del agente padre. Su output aparece en tiempo real en el terminal con el prefijo `│` para distinguirlo del agente principal.

## Cuándo usar un sub-agente

- Tareas que requieren un workspace diferente al actual (ej. revisar otro proyecto)
- Separar una subtarea larga sin contaminar el contexto del agente principal
- Agentes especializados por dominio: `coding` para programación, `home_office` para documentos, `reasoning` para análisis

## Agentes disponibles por defecto

| ID | Emoji | Especialidad |
|----|-------|-------------|
| `main` | 🤖 | Asistente general, coordina otros agentes |
| `coding` | 💻 | IT, programación, refactorización, LSP |
| `home_office` | 📋 | Documentación corporativa O365 (Word/Excel/PPT) |
| `reasoning` | 🧠 | Razonamiento, coordinación de equipos de agentes |
| `webcrawler` | 🕷️ | Búsqueda web con SearXNG, informes |

## Configurar agentes en `oocode.json`

```json
"agents": {
  "defaults": {
    "model": "qwen3.5:9b",
    "workspace": "~/.oocode/workspace/main"
  },
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
```

> **Nota:** el campo `model` de cada agente se ignora cuando se lanza como sub-agente. El sub-agente hereda siempre el modelo del agente padre para no descargar/recargar la GPU.

## Cambiar de agente en caliente con `/switch`

```
/switch coding        # cambiar al agente coding sin reiniciar
/switch home_office   # cambiar al agente home_office
/switch main          # volver al agente principal
```

`/switch` carga el workspace, la memoria y la identidad del agente seleccionado manteniendo la sesión activa.

## Lanzar un sub-agente desde el REPL

```
/spawn coding "analiza el fichero src/main.py y sugiere refactorizaciones"
/spawn home_office "crea un informe de estado del proyecto"
```

Equivale a `/subagents spawn <id> <tarea>`.

El LLM también puede lanzar sub-agentes directamente usando la herramienta `spawn_subagent`:

```
spawn_subagent(
  agent_id="review",
  task="revisa el diff actual y lista los riesgos",
  timeout_seconds=180     # opcional: mata el subagente si tarda más de 3 minutos
)
```

El parámetro `timeout_seconds` activa un **watchdog thread** que dispara el `kill_event` del subagente al expirar. El subagente termina limpiamente en la siguiente iteración de su loop y el padre recibe un mensaje de error de timeout en lugar de bloquearse indefinidamente.

## Control de sub-agentes con `/subagents`

```
/subagents                          # lista sub-agentes activos y recientes (30 min)
/subagents status [id]              # estado detallado de uno o todos
/subagents steer <id> <instrucción> # inyecta nueva instrucción al sub-agente en curso
/subagents kill <id>                # detiene un sub-agente
/subagents kill all                 # detiene todos los sub-agentes activos
/subagents output <id>              # muestra el resultado completo
```

El `id` puede ser un prefijo de 4+ caracteres del `run_id` mostrado en `/subagents`.

## Restricción de VRAM y modelo

El sub-agente hereda siempre el modelo LLM del padre para evitar cargar/descargar la GPU:

```python
sub_config.model       = self.config.model        # mismo LLM
sub_config.embed_model = self.config.embed_model  # mismo embed
```

El `EmbeddingClient` se crea una sola vez y se comparte entre el agente principal y sus sub-agentes (salvo que el sub-agente sea el primero que lo necesita y el padre aún no lo haya creado).

## Multi-servidor Ollama para sub-agentes

Con varios servidores Ollama configurados, OOCode distribuye los sub-agentes en **round-robin** entre todos los hosts disponibles. Esto permite paralelismo real cuando hay varias GPUs:

```
Agente principal    → host (localhost:11434)  — inferencia interactiva
Sub-agente #1       → host[0] = localhost:11434
Sub-agente #2       → host[1] = gpu2:11434
Sub-agente #3       → host[2] = gpu3:11434
Sub-agente #4       → host[0] = localhost:11434   ← vuelve al inicio
```

**Configuración en `oocode.json`:**

```json
{
  "ollama": {
    "host":            "http://localhost:11434",
    "extraHosts":      ["http://gpu2:11434", "http://gpu3:11434"],
    "embedHost":       "http://cpu-server:11434",
    "subagentRouting": "round-robin"
  }
}
```

La función `_pick_subagent_host(config)` en `agent/subagent.py` gestiona la selección de host de forma thread-safe mediante un contador global y `threading.Lock`. Cada sub-agente recibe su host asignado en `sub_config.ollama_host` antes de arrancar el `AgentLoop`.

Con `"subagentRouting": "primary-only"` todos los sub-agentes usan el host principal (comportamiento clásico de un solo servidor).

Los embeddings del sub-agente usan `ollama_embed_host` si está configurado, o `ollama_host` como fallback — independientemente del host LLM asignado por el round-robin.

## Ejecución y output

Los sub-agentes se ejecutan **de forma síncrona** cuando los lanza el LLM (via `spawn_subagent` tool): el padre espera a que el sub-agente termine y recibe el resultado como string. Los sub-agentes lanzados con `/spawn` se ejecutan en un thread de background.

El output del sub-agente **aparece en tiempo real** con el prefijo `│` coloreado:

```
Agente principal
  └── run("tarea compleja")
        └── tool_call: spawn_subagent("coding", "subtarea")
              │                                              ← padre bloqueado aquí
              ├── │  Cavilando…  (1.2s)
              ├── │  💻  read_file  "src/main.py"
              ├── │  ●  Aquí están mis sugerencias…
              └── return resultado_str
        └── context.add_tool_result(resultado_str)
        └── continúa con Ollama (mismo modelo)
```

## Aislamiento del sub-agente

| Recurso | Aislado | Detalle |
|---------|---------|---------|
| Historial de conversación | si | Contexto propio desde cero |
| Workspace / OOCODE.md | si | El definido en `oocode.json` para ese agente |
| Memoria (MEMORY.md) | si | Carpeta `~/.oocode/workspace/<id>/` propia |
| Modelo de inferencia | no | Forzado = modelo del padre |
| Modelo de embeddings | no | Forzado = embed del padre |
| EmbeddingClient | no | Instancia compartida (si el padre ya la tiene) |
| Host Ollama (LLM) | parcialmente | Asignado por round-robin entre `host` + `extraHosts` |
| Host Ollama (embeddings) | no | `embedHost` del padre (o `host` si vacío) |
| Permisos | no | Heredados del agente principal (elevated también) |
| Sesión | si | JSONL propio en `~/.oocode/sessions/<id>/` |
| Plugins y skills | no | Los mismos que el padre |

## Añadir un nuevo agente

1. Añadir entrada en `agents.list` de `~/.oocode/oocode.json`:

```json
{
  "id":        "docs",
  "name":      "DocWriter",
  "emoji":     "📝",
  "model":     null,
  "workspace": "/home/usuario/mi-proyecto/doc"
}
```

2. (Opcional) Crear un `OOCODE.md` en su workspace con instrucciones específicas.

3. (Opcional) Crear los ficheros de identidad del workspace (`IDENTITY.md`, `SOUL.md`, etc.).

4. El nuevo agente ya está disponible en `spawn_subagent` y `/switch` sin reiniciar.
