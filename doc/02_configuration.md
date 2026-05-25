# 02 — Configuración

La configuración de OOCode reside en `~/.oocode/oocode.json`. Se genera automáticamente con valores por defecto en el primer arranque y se puede editar manualmente o con `/config edit`.

## Estructura completa de oocode.json

```json
{
  "ollama": {
    "host": "http://localhost:11434"
  },

  "agents": {
    "defaults": {
      "model": "qwen2.5-coder:14b",
      "workspace": "~/.oocode/workspace/main"
    },
    "list": [
      {
        "id":        "main",
        "name":      "OOCode",
        "emoji":     "🤖",
        "model":     "qwen2.5-coder:14b",
        "workspace": "~/.oocode/workspace/main"
      }
    ]
  },

  "permissions": {
    "bash":              "ask",
    "write_file":        "ask",
    "edit_file":         "ask",
    "read_file":         "auto",
    "list_dir":          "auto",
    "web_search":        "auto",
    "web_fetch":         "auto",
    "searxng_search":    "auto",
    "spawn_subagent":    "ask",
    "lint_file":         "auto",
    "lint_project":      "auto",
    "git_status":        "auto",
    "git_diff":          "auto",
    "git_log":           "auto",
    "git_commit":        "ask",
    "git_push":          "ask",
    "git_pull":          "ask",
    "git_add":           "ask",
    "git_branch":        "auto",
    "git_stash":         "ask",
    "git_patch":         "ask",
    "git_clone":         "ask",
    "run_tests":         "ask",
    "test_file":         "ask",
    "docker_ps":         "auto",
    "docker_logs":       "auto",
    "docker_inspect":    "auto",
    "docker_images":     "auto",
    "docker_exec":       "ask",
    "docker_stop":       "ask",
    "docker_rm":         "ask",
    "compose_version":   "auto",
    "compose_services":  "auto",
    "compose_status":    "auto",
    "compose_config":    "auto",
    "compose_images":    "auto",
    "compose_top":       "auto",
    "compose_logs":      "auto",
    "compose_up":        "ask",
    "compose_down":      "ask",
    "compose_stop":      "ask",
    "compose_restart":   "ask",
    "compose_build":     "ask",
    "compose_pull":      "ask",
    "compose_exec":      "ask",
    "compose_run":       "ask",
    "index_workspace":   "auto",
    "semantic_search":   "auto",
    "build_symbol_index":"ask",
    "find_symbol":       "auto",
    "list_symbols":      "auto",
    "extract_functions": "auto",
    "extract_classes":   "auto",
    "extract_imports":   "auto",
    "ast_summary":       "auto",
    "todo_list":         "auto",
    "todo_add":          "ask",
    "todo_done":         "auto",
    "todo_sync":         "auto",
    "changelog_today":   "auto",
    "changelog_session": "auto",
    "changelog_week":    "auto",
    "clipboard_copy":    "auto",
    "clipboard_paste":   "auto",
    "vault_list":        "auto",
    "vault_get":         "auto",
    "encode_base64":     "auto",
    "decode_base64":     "auto",
    "url_encode":        "auto",
    "url_decode":        "auto",
    "compute_hash":      "auto",
    "to_base":           "auto",
    "format_json":       "auto",
    "escape_string":     "auto",
    "hex_encode":        "auto",
    "hex_decode":        "auto",
    "snippet_save":      "auto",
    "snippet_get":       "auto",
    "snippet_list":      "auto",
    "snippet_delete":    "auto"
  },

  "context": {
    "minKeep":             6,
    "compactThreshold":    0.85,
    "maxSummaryChars":     2100,
    "maxToolResultTokens": 2048,
    "autoContinueMax":     8
  },

  "embeddings": {
    "model":               "nomic-embed-text-v2-moe:latest",
    "maxInputChars":       12000,
    "similarityThreshold": 0.30,
    "snippetChars":        800,
    "topK":                3
  },

  "tools": {
    "readFileLinesDefault":   300,
    "readFileLinesWarnLarge": 2000,
    "webFetchMaxChars":       16000,
    "webFetchTimeout":        15,
    "webSearchMaxResults":    5,
    "bashMaxOutputChars":     75000
  },

  "workspace": {
    "maxMemoryLines": 12,
    "maxDailyChars":  400
  },

  "models": {
    "systemOverhead": 4000,
    "configs": {
      "qwen2.5-coder:14b": {
        "contextWindow":  32768,
        "maxTokens":      8192,
        "timeoutSeconds": 180,
        "params": {
          "num_ctx":     32768,
          "num_predict": 8192,
          "temperature": 0.5
        }
      }
    }
  },

  "fallback": {
    "enabled":        false,
    "model":          "qwen3.5:4b",
    "timeoutSeconds": 120
  },

  "searxng": {
    "url":        "",
    "enabled":    false,
    "maxResults": 5,
    "categories": "general",
    "language":   "auto",
    "safeSearch": 0,
    "timeout":    10
  },

  "logging": {
    "enabled":   true,
    "file":      "",
    "level":     "info",
    "maxSizeMb": 5,
    "maxFiles":  3
  },

  "appearance": {
    "accentColor": "cyan"
  },

  "plugins": {
    "enabled": ["git", "linter", "todo", "changelog"]
  },

  "skills": {
    "enabled": []
  },

  "pluginOptions": {
    "linter": {
      "auto":      true,
      "maxOutput": 4000,
      "timeout":   30
    },
    "git": {
      "autostage": false,
      "showDiff":  true
    },
    "searxng": {
      "enabled": false
    }
  }
}
```

## Secciones

### `ollama`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `host` | string | URL del servidor Ollama |

### `agents`

Define los agentes disponibles. Cada agente tiene su propio modelo y workspace. Se selecciona con `--agent <id>`.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | string | Identificador único |
| `name` | string | Nombre mostrado en el prompt |
| `emoji` | string | Emoji del agente |
| `model` | string\|null | Modelo Ollama (null = heredar de `defaults.model`) |
| `workspace` | string | Directorio de trabajo del agente |

### `permissions`

Modo de permiso por herramienta. Los permisos disponibles dependen de los plugins activos.

| Modo | Comportamiento |
|------|---------------|
| `auto` | Se ejecuta siempre sin preguntar |
| `ask` | Solicita confirmación (con opción "siempre" para la sesión) |
| `deny` | Siempre denegado |

**Permisos por categoría:**

| Herramienta | Defecto | Plugin |
|-------------|---------|--------|
| `bash` | `ask` | core |
| `read_file`, `write_file`, `edit_file`, `list_dir` | `ask`/`auto` | core |
| `web_search`, `web_fetch` | `auto` | core |
| `git_status`, `git_diff`, `git_log`, `git_branch` | `auto` | git |
| `git_commit`, `git_push`, `git_pull`, `git_add`, `git_stash`, `git_patch`, `git_clone` | `ask` | git |
| `lint_file`, `lint_project` | `auto` | linter |
| `run_tests`, `test_file` | `ask` | test_runner |
| `docker_ps`, `docker_logs`, `docker_inspect`, `docker_images` | `auto` | docker |
| `docker_exec`, `docker_stop`, `docker_rm` | `ask` | docker |
| `compose_version`…`compose_top`, `compose_logs` | `auto` | docker |
| `compose_up`, `compose_down`, `compose_stop`, `compose_restart`, `compose_build`, `compose_pull`, `compose_exec`, `compose_run` | `ask` | docker |
| `index_workspace`, `semantic_search` | `auto` | embeddings_search |
| `build_symbol_index` | `ask` | ctags |
| `find_symbol`, `list_symbols`, `extract_functions`, `extract_classes`, `extract_imports`, `ast_summary` | `auto` | ctags/tree_sitter |
| `todo_list`, `todo_done`, `todo_sync` | `auto` | todo |
| `todo_add` | `ask` | todo |
| `changelog_today`, `changelog_session`, `changelog_week` | `auto` | changelog |
| `clipboard_copy`, `clipboard_paste` | `auto` | clipboard |
| `vault_list`, `vault_get` | `auto` | vault |
| `encode_base64`, `decode_base64`, `url_encode`, `url_decode`, `compute_hash`, `to_base`, `format_json`, `escape_string`, `hex_encode`, `hex_decode` | `auto` | converters (skill) |
| `snippet_save`, `snippet_get`, `snippet_list`, `snippet_delete` | `auto` | snippets (skill) |
| `spawn_subagent` | `ask` | core |
| `searxng_search` | `auto` | searxng |

### `context`

> **Nota:** El campo `maxTokens` (obsoleto) ha sido reemplazado por `models.configs.<modelo>.maxTokens`. OOCode lo migra automáticamente.

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `minKeep` | 6 | Mensajes mínimos a conservar tras compactar |
| `compactThreshold` | 0.85 | Fracción del límite que dispara compactación automática |
| `maxSummaryChars` | 2100 | Chars máximos del resumen acumulado (~600 tokens) |
| `maxToolResultTokens` | 2048 | Tokens máximos de un resultado de herramienta en el contexto |
| `autoContinueMax` | 8 | Auto-continuaciones máximas tras respuesta vacía del modelo (0 = desactivado) |

**Auto-continuación:** cuando el modelo produce una respuesta sin texto ni herramientas (frecuente al completar un batch largo de ediciones), OOCode inyecta automáticamente `"Continúa con la tarea."` y reanuda el bucle. El contador se resetea cuando el modelo produce respuesta no vacía.

### `embeddings`

Configura la memoria semántica. Requiere un modelo de embeddings en Ollama.

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `model` | `nomic-embed-text-v2-moe:latest` | Modelo de embeddings |
| `maxInputChars` | 6000 | Chars máximos de texto a embedar |
| `similarityThreshold` | 0.30 | Score mínimo para incluir un resultado |
| `snippetChars` | 400 | Chars del snippet por resultado de memoria |
| `topK` | 3 | Memorias máximas recuperadas por búsqueda |
| `memoryEmbedEnabled` | `true` | Usar embeddings vectoriales para búsqueda semántica en memorias; si `false`, `/mem search` y la inyección automática de memorias se desactivan |

### `tools`

Controla los límites de las herramientas core. Ajustar según la VRAM disponible y el tamaño de los ficheros de trabajo.

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `readFileLinesDefault` | 300 | Líneas por defecto en `read_file` sin `offset`/`limit` |
| `readFileLinesWarnLarge` | 2000 | Avisa (no bloquea) si el fichero supera este número de líneas |
| `webFetchMaxChars` | 16000 | Chars máximos extraídos de una URL |
| `webFetchTimeout` | 15 | Timeout en segundos de `web_fetch` |
| `webSearchMaxResults` | 5 | Resultados por defecto de `web_search` |
| `bashMaxOutputChars` | 75000 | Chars máximos de salida de bash (el resto se trunca) |

> **Ficheros grandes:** para proyectos con ficheros de 3000–8000 líneas, usar `readFileLinesDefault=300` y `readFileLinesWarnLarge=2000`. El modelo puede leer secciones con `offset`/`limit`.

### `workspace`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `maxMemoryLines` | 12 | Líneas de MEMORY.md incluidas en el system prompt |
| `maxDailyChars` | 400 | Chars del log diario incluidos en el system prompt |

### `models`

Configuración por modelo. OOCode usa estos valores para calcular el contexto disponible:

```
tokens_disponibles = contextWindow − maxTokens − systemOverhead
```

| Campo | Descripción |
|-------|-------------|
| `systemOverhead` | Tokens reservados para system prompt y schemas de tools |
| `configs.<modelo>.contextWindow` | Ventana de contexto total (igual a `num_ctx` enviado a Ollama) |
| `configs.<modelo>.maxTokens` | Tokens de salida reservados para la respuesta |
| `configs.<modelo>.timeoutSeconds` | Segundos sin tokens antes de activar el fallback |
| `configs.<modelo>.params` | Parámetros Ollama adicionales (num_ctx, temperature, top_k…) |
| `configs.<modelo>.thinking` | Sub-objeto opcional para `/think` y `/reasoning` (ver abajo) |

**Sub-objeto `thinking`** (opcional por modelo):

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `think_level` | `"low"` \| `"medium"` \| `"high"` | Nivel de razonamiento extendido para `/think` |
| `reasoning` | bool | `true` = activar `/reasoning` persistente para este modelo |

Configura desde el REPL con:
```
/model                          # muestra config del modelo activo
/model timeout 180              # timeout de 180s para el modelo activo
/model qwen3.5:9b-65k           # cambia al modelo indicado
```

### `fallback`

Si el modelo principal excede el timeout, OOCode reintenta automáticamente con el modelo de fallback.

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `enabled` | `false` | Activa el mecanismo de fallback |
| `model` | `""` | Modelo alternativo (p.ej. `"qwen3.5:4b"`) |
| `timeoutSeconds` | 120 | Timeout por defecto si el modelo no tiene `timeoutSeconds` en su config |

> **Nota:** el timeout per-modelo (`models.configs.<modelo>.timeoutSeconds`) tiene prioridad sobre `fallback.timeoutSeconds`.

### `searxng`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `url` | `""` | URL de la instancia SearXNG (vacío = desactivado) |
| `enabled` | `false` | `true` = reemplaza `web_search` con SearXNG |
| `maxResults` | 5 | Resultados máximos por búsqueda |
| `categories` | `"general"` | Categorías: `general`, `news`, `science`, `it`, `images` |
| `language` | `"auto"` | Idioma: `auto`, `es`, `en`, `fr`… |
| `safeSearch` | 0 | 0=off, 1=moderate, 2=strict |
| `timeout` | 10 | Timeout de conexión en segundos |

### `logging`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `enabled` | `true` | Activa/desactiva escritura en fichero |
| `file` | `""` | Ruta del log (vacío = `~/.oocode/logs/oocode.log`) |
| `level` | `"info"` | `debug` \| `info` \| `warn` \| `error` |
| `maxSizeMb` | 5 | Tamaño máximo antes de rotar |
| `maxFiles` | 3 | Ficheros rotados a conservar |

### `appearance`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `accentColor` | `"cyan"` | Color del prompt y del banner. Valores: `cyan`, `green`, `blue`, `magenta`, `yellow`, `red`, `white` |

### `plugins` y `skills`

Listas de extensiones activas. Se actualizan automáticamente con `/plugins enable/disable` y `/skills enable/disable`.

**Plugins disponibles:** `changelog`, `clipboard`, `ctags`, `diff`, `docker`, `embeddings_search`, `git`, `linter`, `searxng`, `test_runner`, `todo`, `tree_sitter`, `vault`

**Skills disponibles:** `converters`, `snippets`

### `pluginOptions`

Opciones por plugin. Se leen en el `on_start()` de cada plugin:

**`linter`:**
| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `auto` | `true` | Linting automático tras `write_file`/`edit_file` |
| `maxOutput` | 4000 | Chars máximos de salida del linter |
| `timeout` | 30 | Timeout en segundos por linter |

**`git`:**
| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `autostage` | `false` | `git add` automático tras editar |
| `showDiff` | `true` | Mostrar diff en commits |

**`searxng`:**
| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `enabled` | `false` | Activar SearXNG como fuente de búsqueda |

---

## Configuración por hardware

### 16 GB VRAM (recomendado — qwen3.5:9b)

Configuración actual de referencia. Permite contextos de 65K tokens y ficheros de varios miles de líneas.

```json
{
  "models": {
    "systemOverhead": 4000,
    "configs": {
      "qwen3.5:9b-65k": {
        "contextWindow":  65000,
        "maxTokens":      32768,
        "timeoutSeconds": 600,
        "params": {
          "num_ctx":     65000,
          "num_predict": 32768,
          "temperature": 0.5,
          "top_k":       20,
          "top_p":       0.95
        },
        "thinking": {
          "think_level": "medium",
          "reasoning":   true
        }
      }
    }
  },
  "context": {
    "maxToolResultTokens": 2048,
    "autoContinueMax":     8
  },
  "tools": {
    "readFileLinesDefault":   300,
    "readFileLinesWarnLarge": 2000,
    "bashMaxOutputChars":     75000,
    "webFetchMaxChars":       16000
  }
}
```

**Tokens disponibles para historial:** `65000 − 32768 − 4000 = 28 232`

### 8 GB VRAM (qwen2.5-coder:7b / qwen3.5:4b)

Configuración conservadora para GPUs con 8 GB. Reduce el contexto y los límites de herramientas para no agotar la memoria.

```json
{
  "models": {
    "systemOverhead": 2000,
    "configs": {
      "qwen2.5-coder:7b": {
        "contextWindow":  32768,
        "maxTokens":      8192,
        "timeoutSeconds": 180,
        "params": {
          "num_ctx":     32768,
          "num_predict": 8192,
          "temperature": 0.5
        }
      }
    }
  },
  "context": {
    "maxToolResultTokens": 1024,
    "autoContinueMax":     5
  },
  "tools": {
    "readFileLinesDefault":   150,
    "readFileLinesWarnLarge": 500,
    "bashMaxOutputChars":     30000,
    "webFetchMaxChars":       8000
  }
}
```

**Tokens disponibles para historial:** `32768 − 8192 − 2000 = 22 576`

> **Compactación:** OOCode compacta automáticamente el historial cuando supera el 85 % del límite (`compactThreshold`). Para contextos pequeños, reducir `maxSummaryChars` a `1200` ayuda a que el resumen no consuma demasiado espacio.

---

## Edición interactiva

```
/config          # muestra configuración completa
/config edit     # panel interactivo sección por sección
```

## CLI (sobreescribe oocode.json)

```bash
python oocode.py \
  --host http://192.168.1.33:11434 \    # sobreescribe ollama.host
  --model qwen3.5:9b-65k \              # sobreescribe model del agente
  --agent coding \                       # selecciona agente por ID
  --workspace /mi-proyecto               # sobreescribe workspace
```

## Ficheros del directorio `~/.oocode/`

```
~/.oocode/
├── oocode.json           # configuración principal
├── oocode.json.bak       # backup automático de la última versión
├── history               # historial del REPL (prompt_toolkit)
├── themes.json           # temas de color guardados por el usuario
├── keybindings.json      # atajos de teclado personalizados
├── memory/
│   └── <agent_id>/       # memoria aislada por agente
│       ├── MEMORY.md     # índice de memorias
│       ├── *.md          # ficheros de memoria individual
│       └── *.emb.json    # vectores de embedding (para búsqueda semántica)
├── logs/
│   └── oocode.log        # log rotativo de actividad
├── sessions/
│   └── <agent_id>/       # sesiones por agente (JSONL)
│       └── sessions.json # índice de sesiones
├── branches/
│   └── <agent_id>/       # snapshots de conversación
├── plugins/
│   ├── enabled.json      # sincronizado con plugins.enabled de oocode.json
│   └── *.py              # ficheros de plugin
├── skills/
│   ├── enabled.json      # sincronizado con skills.enabled
│   └── *.py              # ficheros de skill
└── workspace/
    └── <agent_id>/       # workspace por agente
        ├── IDENTITY.md   # quién eres (nombre, emoji, principios)
        ├── SOUL.md       # cómo actúas
        ├── USER.md       # información sobre el usuario
        ├── AGENTS.md     # instrucciones de arranque y memoria
        ├── HEARTBEAT.md  # tareas periódicas del agente
        ├── TOOLS.md      # entorno local (permisos, host Ollama)
        ├── MEMORY.md     # memoria a largo plazo editable
        └── memory/       # logs diarios (YYYY-MM-DD.md)
```
