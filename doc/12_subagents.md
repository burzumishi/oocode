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
  timeout_seconds=180     # opcional: mata el subagente si un PASO no progresa en 3 min
)
```

El parámetro `timeout_seconds` activa un **watchdog por inactividad**: un thread que
dispara el `kill_event` del subagente solo si pasa `timeout_seconds` **sin progreso**.
Es un timeout **por paso / petición al LLM, no por tiempo total**: el `AgentLoop` del
subagente emite un *heartbeat* al iniciar cada iteración, al recibir la respuesta del
LLM y tras cada tool, así que un subagente que avanza de forma sostenida **no se
detiene** aunque la tarea completa dure mucho más que `timeout_seconds`. Solo se mata
si una sola petición al LLM (o una tool) se cuelga más de `timeout_seconds`. El
subagente termina limpiamente en la siguiente iteración de su loop y el padre recibe
un mensaje de error de timeout en lugar de bloquearse indefinidamente.

## Configurar límites de subagentes (`subagents` en `oocode.json`)

Desde v0.4.0 el bloque `subagents` de `oocode.json` expone tres campos nuevos para controlar el comportamiento de los subagentes de forma independiente al agente principal:

```json
{
  "subagents": {
    "maxConcurrent":    4,
    "autoContMax":      16,
    "inferenceTimeout": 0,
    "defaultTimeout":   0
  }
}
```

| Campo | Default | Descripción |
|-------|---------|-------------|
| `maxConcurrent` | 4 | Subagentes corriendo en paralelo simultáneamente |
| `autoContMax` | 16 | **Auto-continues máximos para subagentes.** A diferencia del agente principal (`context.autoContinueMax: 8`), los subagentes tienen un límite más alto porque suelen ejecutar tareas largas de varios pasos. Con 0, hereda el valor del agente principal. |
| `inferenceTimeout` | 0 | **Timeout de inferencia** en segundos, solo para subagentes. Útil cuando los subagentes hacen razonamiento complejo que tarda más de lo normal por turno. **Desde v0.4.1** se aplica con máxima prioridad (`inference_timeout_override`): supera al timeout per-modelo y al de fallback, y funciona aunque no haya modelo de fallback configurado. Con 0, hereda el timeout del agente principal. |
| `defaultTimeout` | 0 | **Timeout por paso/petición al LLM** (inactividad), **no** por tiempo total. El watchdog mata el subagente solo si un paso pasa este número de segundos **sin progreso** (sin heartbeat); un subagente que avanza no se detiene aunque la tarea total dure más. Se usa si el LLM llama `spawn_subagent`/`spawn_fanout` sin `timeout_seconds`. Con 0 no hay watchdog. |

### Ejemplo: subagentes con 5 minutos de inferencia y sin límite de tarea

```json
{
  "subagents": {
    "autoContMax":      20,
    "inferenceTimeout": 300,
    "defaultTimeout":   0
  }
}
```

### Ejemplo: matar un subagente si un paso se cuelga más de 10 minutos

```json
{
  "subagents": {
    "defaultTimeout": 600
  }
}
```

Con esto, un subagente puede trabajar horas en una tarea larga siempre que cada paso
(petición al LLM o tool) progrese; solo se mata si **un único paso** se cuelga más de
600 s. Esto evita que tareas legítimamente largas se detengan «por acumular tiempo».

> **Nota:** `timeout_seconds` explícito en la llamada `spawn_subagent(timeout_seconds=N)` siempre tiene precedencia sobre `defaultTimeout`. En ambos casos la semántica es **por paso sin progreso**, no tiempo total.

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
  "api": {
    "type":            "ollama",
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

Para no inundar el terminal, el streaming `│` muestra **hasta 12 líneas por turno** del sub-agente; al alcanzar el límite aparece `… buffer lleno (ctrl+o para ver completo)` y el resto de ese turno se omite del live view (sigue completo en el historial expandible con `Ctrl+O`). El presupuesto se **refresca en cada turno** del sub-agente: a medida que avanza (auto-continue), las líneas nuevas siguen apareciendo y las antiguas hacen scroll hacia arriba — así siempre ves su actividad reciente, no solo el primer turno.

Todo el bloque del sub-agente comparte la columna `│`, incluido su `●` de texto y su continuación:

```
  │ ● Tarea 6 activa: Documentar cambios en doc/interaccion_social.md.
  │   Voy a crear la documentación con todos los cambios del Sprint 9.
  │   ◐  Write(interaccion_social.md)
  │   │  Fichero escrito: /ruta/doc.md (8292 caracteres)
```

## Directorio de trabajo (cwd de las tools)

El sub-agente carga **su propio** workspace de identidad (`~/.oocode/workspace/<id>/`), pero ejecuta las tools (`bash`, `python_exec`, `workspace_remember`) en el **`project_dir` del padre** — el mismo proyecto en el que trabaja el agente principal, no su carpeta de identidad. Así un sub-agente `coding` que hace `bash("mkdir -p doc")` lo crea en el proyecto, no en `~/.oocode/workspace/coding/`.

## Delegación consciente de agentes

El LLM ve el **rol de cada agente disponible** (leído de su `IDENTITY.md`) tanto en los schemas de `spawn_subagent`/`create_team`/`spawn_fanout` como en una sección "Agentes disponibles para delegar" del system prompt (cuando hay >1 agente). Así puede decidir delegar en el agente más afín a la tarea (p.ej. una búsqueda web en `webcrawler`) en vez de resolverlo todo él mismo — sin necesidad de prompts específicos. Puedes afinar esta preferencia en la sección `## Notas` de `AGENTS.md` (ver doc 16).

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
