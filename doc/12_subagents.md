# 12 — Sub-agentes

Un sub-agente es una instancia aislada de `AgentLoop` que el agente principal puede lanzar para delegar una tarea. Tiene su propio workspace y su propio historial de conversación, pero comparte el modelo de inferencia y el cliente de embeddings del agente padre. Su output aparece en tiempo real en el terminal con el prefijo `│` para distinguirlo del agente principal.

## Cuándo usar un sub-agente

- Tareas que requieren un workspace diferente al actual (ej. revisar otro proyecto)
- Separar una subtarea larga sin contaminar el contexto del agente principal
- Agentes especializados por dominio con sus propios `OOCODE.md`

## Configurar agentes en `oocode.json`

```json
"agents": {
  "defaults": {
    "model": null,
    "workspace": "~/.oocode/workspace/main"
  },
  "list": [
    {
      "id":        "main",
      "name":      "OOCode",
      "emoji":     "🤖",
      "model":     null,
      "workspace": "~/.oocode/workspace/main"
    },
    {
      "id":        "coding",
      "name":      "Coder",
      "emoji":     "⚙️",
      "model":     null,
      "workspace": "/home/usuario/mi-proyecto"
    },
    {
      "id":        "review",
      "name":      "Reviewer",
      "emoji":     "🔍",
      "model":     null,
      "workspace": "~/.oocode/workspace/review"
    }
  ]
}
```

> **Nota:** el campo `model` de cada agente se ignora cuando se lanza como sub-agente. El sub-agente hereda siempre el modelo del agente padre para no descargar/recargar la GPU.

## Lanzar un sub-agente desde el REPL

```
/spawn coding "analiza el fichero src/main.py y sugiere refactorizaciones"
```

Equivale a `/subagents spawn coding <tarea>`.

El LLM también puede lanzar sub-agentes directamente usando la herramienta `spawn_subagent`:

```
spawn_subagent(agent_id="review", task="revisa el diff actual y lista los riesgos")
```

## Control de sub-agentes con `/subagents`

```
/subagents                          # lista sub-agentes activos y recientes (30 min)
/subagents spawn <id> <tarea>       # lanza sub-agente
/subagents status [id]              # estado detallado de uno o todos
/subagents steer <id> <instrucción> # inyecta nueva instrucción al sub-agente en curso
/subagents kill <id>                # detiene un sub-agente
/subagents kill all                 # detiene todos los sub-agentes activos
/subagents output <id>              # muestra el resultado completo
```

El `id` puede ser un prefijo de 4+ caracteres del `run_id` mostrado en `/subagents`.

## Restricción de VRAM

La GPU tiene VRAM limitada. Solo pueden estar cargados simultáneamente el LLM activo y el modelo de embeddings. `SubAgentRunner.run()` sobreescribe los campos de modelo en la config del sub-agente antes de crear su `AgentLoop`:

```python
sub_config.model       = self.config.model        # mismo LLM
sub_config.ollama_host = self.config.ollama_host  # mismo servidor
sub_config.embed_model = self.config.embed_model  # mismo embed
```

El `EmbeddingClient` se crea una sola vez y se comparte entre el agente principal y sus sub-agentes.

## Ejecución y output

Los sub-agentes se ejecutan **de forma síncrona** cuando los lanza el LLM (via `spawn_subagent` tool): el padre espera a que el sub-agente termine y recibe el resultado como string. Los sub-agentes lanzados con `/subagents spawn` se ejecutan en un thread de background (el REPL sigue respondiendo mientras trabajan).

El output del sub-agente **aparece en tiempo real** con el prefijo `│` coloreado. Al terminar, el resultado se devuelve al agente principal como resultado de la herramienta.

```
Agente principal
  └── run("tarea compleja")
        └── tool_call: spawn_subagent("coding", "subtarea")
              │                                              ← padre bloqueado aquí
              ├── │  Cavilando…  (1.2s)
              ├── │  ⚙  read_file  "src/main.py"
              ├── │  ●  Aquí están mis sugerencias…
              └── return resultado_str
        └── context.add_tool_result(resultado_str)
        └── continúa con Ollama (mismo modelo)
```

## Aislamiento del sub-agente

| Recurso | ¿Aislado? | Detalle |
|---------|-----------|---------|
| Historial de conversación | ✓ | Contexto propio desde cero |
| Workspace / OOCODE.md | ✓ | El definido en `oocode.json` para ese agente |
| Memoria (MEMORY.md) | ✓ | Carpeta `~/.oocode/memory/<id>/` propia |
| Modelo de inferencia | ✗ | Forzado = modelo del padre |
| Modelo de embeddings | ✗ | Forzado = embed del padre |
| EmbeddingClient | ✗ | Instancia compartida (misma conexión) |
| Permisos | ✗ | Heredados del agente principal |
| Sesión | ✓ | JSONL propio en `~/.oocode/sessions/<id>/` |
| Plugins y skills | ✗ | Los mismos que el padre |

## Añadir un nuevo agente

1. Añadir una entrada en `agents.list` de `~/.oocode/oocode.json`:

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

3. El nuevo agente ya está disponible en `spawn_subagent` sin reiniciar.
