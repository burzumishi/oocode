# 02 — Configuración

La configuración de OOCode reside en `~/.oocode/oocode.json`. Se genera automáticamente con valores por defecto en el primer arranque. Edita con `/config edit` desde el REPL o directamente con cualquier editor.

## Estructura completa de oocode.json

```json
{
  "api": {
    "type":             "ollama",
    "key":              "",
    "host":             "http://localhost:11434",
    "extraHosts":       [],
    "embedHost":        "",
    "subagentRouting":  "round-robin",
    "ollamaRetryCount": 2,
    "ollamaRetryDelay": 3.0
  },

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
  },

  "permissions": {
    "bash":              "ask",
    "write_file":        "ask",
    "edit_file":         "ask",
    "edit_files":        "ask",
    "read_file":         "auto",
    "list_dir":          "auto",
    "web_search":        "auto",
    "web_fetch":         "auto",
    "searxng_search":    "auto",
    "spawn_subagent":    "ask",
    "code_search":       "auto",
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
    "git_worktree":      "ask",
    "run_tests":         "ask",
    "docker_ps":         "auto",
    "docker_logs":       "auto",
    "docker_exec":       "ask",
    "docker_stop":       "ask"
  },

  "context": {
    "minKeep":             6,
    "compactThreshold":    0.80,
    "maxSummaryChars":     2100,
    "maxToolResultTokens": 800,
    "autoContinueMax":     8,
    "highWater":           0.70,
    "toolMaxChars":        3000
  },

  "embeddings": {
    "model":               "nomic-embed-text-v2-moe:latest",
    "maxInputChars":       12000,
    "similarityThreshold": 0.30,
    "snippetChars":        800,
    "topK":                3,
    "memoryEmbedEnabled":  true,
    "ramCacheMax":         256
  },

  "rag": {
    "enabled":            true,
    "topK":               20,
    "similarityThreshold":0.35,
    "maxSnippetChars":    28000,
    "topKComplex":        35,
    "thresholdComplex":   0.25,
    "complexMinChars":    120,
    "maxFileChars":       6000,
    "chunkChars":         512,
    "chunkOverlap":       64,
    "maxFiles":           2000,
    "minSlotChars":       200
  },

  "tools": {
    "readFileLinesDefault":   300,
    "readFileLinesWarnLarge": 2000,
    "webFetchMaxChars":       16000,
    "webFetchTimeout":        15,
    "webSearchMaxResults":    5,
    "bashMaxOutputChars":     75000,
    "codeSearchMaxResults":   120,
    "codeSearchContextLines": 4,
    "toolCacheEnabled":       true,
    "toolCacheTTL":           300,
    "toolCacheMaxSize":       600
  },

  "workspace": {
    "maxMemoryLines": 12,
    "maxDailyChars":  400
  },

  "models": {
    "systemOverhead": 4000,
    "configs": {
      "qwen3.5:9b": {
        "contextWindow":  131072,
        "maxTokens":      50000,
        "timeoutSeconds": 600,
        "params": {
          "num_ctx":     131072,
          "num_predict": 50000,
          "temperature": 0.7,
          "top_k":       20,
          "top_p":       0.95
        }
      }
    }
  },

  "fallback": {
    "enabled":        true,
    "model":          "qwen3.5:4b",
    "timeoutSeconds": 600
  },

  "mcp": {
    "oocodeAssistant":    { "enabled": true  },
    "systemAssistant":    { "enabled": true  },
    "wordAssistant":      { "enabled": false },
    "excelAssistant":     { "enabled": false },
    "pptxAssistant":      { "enabled": false },
    "mailAssistant":      { "enabled": false },
    "cmdbAssistant":      { "enabled": false },
    "securityAssistant":  { "enabled": false },
    "iotAssistant":       { "enabled": false },
    "requestTimeout": 30.0,
    "servers": []
  },

  "lsp": {
    "enabled": true,
    "autoStart": true
  },

  "hooks": {
    "builtins": [
      "lint_after_write",
      "quick_syntax",
      "config_syntax_after_write",
      "log_tool_calls"
    ]
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
    "enabled": ["lsp", "embeddings_search", "todo", "changelog"]
  },

  "skills": {
    "enabled": []
  },

  "snapshots": {
    "enabled": true,
    "maxSnapshots": 40
  }
}
```

---

## Secciones

### `api` *(nuevo en v0.4.0)*

Selecciona el backend LLM. OOCode soporta tres tipos:

Un único bloque `api` define el backend LLM **y** todos los parámetros del servidor.

| Campo | Tipo | Defecto | Descripción |
|-------|------|---------|-------------|
| `type` | string | `"ollama"` | Backend: `"ollama"` \| `"openai"` \| `"anthropic"` |
| `key` | string | `""` | API key (necesaria para OpenAI cloud y Anthropic; vacía para Ollama o servidores locales) |
| `host` | string | `"http://localhost:11434"` | URL del servidor. Con `type: "ollama"` es el host de Ollama; con `type: "openai"` es el `baseUrl` (p.ej. `"http://localhost:8080/v1"` para llama.cpp; vacío usa la URL oficial de OpenAI). Con `type: "anthropic"` se ignora |
| `extraHosts` | list[string] | `[]` | **(solo Ollama)** Servidores adicionales para subagentes (round-robin). Cada subagente nuevo recibe el siguiente host de la lista |
| `embedHost` | string | `""` | Servidor Ollama dedicado para embeddings (memoria/RAG, siempre protocolo Ollama). Vacío: con `type: "ollama"` usa `host`; con `type: "openai"`/`"anthropic"` cae a `http://localhost:11434` (v0.4.1) en vez de `host` (que apunta al servidor de chat) |
| `subagentRouting` | string | `"round-robin"` | **(solo Ollama)** Política de distribución: `"round-robin"` rota entre todos los hosts disponibles; `"primary-only"` usa siempre el host principal |
| `ollamaRetryCount` | int | `2` | **(solo Ollama)** Reintentos automáticos en timeout (0 = sin retry) |
| `ollamaRetryDelay` | float | `3.0` | **(solo Ollama)** Segundos de espera base entre reintentos (se duplica con backoff) |

**Ejemplos de backend:**

```json
// Ollama local (default)
{ "api": { "type": "ollama", "host": "http://localhost:11434" } }

// llama.cpp / LM Studio / vLLM (OpenAI-compatible local)
{ "api": { "type": "openai", "host": "http://localhost:8080/v1" } }

// OpenAI cloud
{ "api": { "type": "openai", "key": "sk-...", "host": "https://api.openai.com/v1" } }

// Anthropic (Claude cloud)
{ "api": { "type": "anthropic", "key": "sk-ant-..." } }
```

Ver `doc/25_api_backends.md` para referencia completa de backends.

#### Multi-servidor Ollama

Cuando tienes varias GPUs o varias máquinas con Ollama, OOCode puede distribuir la carga de los subagentes entre todos los servidores disponibles. El servidor principal (`host`) siempre recibe el agente interactivo. Los subagentes se asignan en round-robin entre `host` + `extraHosts`.

**Ejemplo: 3 GPUs locales**
```json
{
  "api": {
    "type":            "ollama",
    "host":            "http://localhost:11434",
    "extraHosts":      ["http://localhost:11435", "http://localhost:11436"],
    "subagentRouting": "round-robin"
  }
}
```

**Ejemplo: 2 máquinas en red + servidor CPU para embeddings**
```json
{
  "api": {
    "type":            "ollama",
    "host":            "http://gpu-server-1:11434",
    "extraHosts":      ["http://gpu-server-2:11434"],
    "embedHost":       "http://cpu-server:11434",
    "subagentRouting": "round-robin"
  }
}
```

**Ejemplo: un servidor, deshabilitar distribución**
```json
{
  "api": {
    "type":            "ollama",
    "host":            "http://localhost:11434",
    "subagentRouting": "primary-only"
  }
}
```

La propiedad `embedHost` también se aplica a los subagentes: cada subagente que necesita crear su propio `EmbeddingClient` usa el host de embeddings efectivo (`config.effective_embed_host`), independientemente del host asignado por el round-robin para las inferencias LLM.

El `/doctor` (adaptado al backend) verifica la conectividad del backend de chat y del host de embeddings, y con Ollama muestra cuántos modelos tiene cada host.

### `agents`

Define los agentes disponibles. Cada agente tiene su propio modelo y workspace. Se selecciona con `--agent <id>` en CLI o `/switch <id>` en el REPL.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | string | Identificador único del agente |
| `name` | string | Nombre mostrado en el prompt |
| `emoji` | string | Emoji del agente (mostrado en TUI y WebUI) |
| `model` | string\|null | Modelo Ollama (null = heredar de `defaults.model`) |
| `workspace` | string | Directorio de trabajo del agente |

Los 5 agentes incluidos por defecto:

| ID | Emoji | Especialidad |
|----|-------|-------------|
| `main` | 🤖 | Asistente general, coordina otros agentes |
| `coding` | 💻 | IT, programación, refactorización, LSP |
| `home_office` | 📋 | Documentación corporativa O365 |
| `reasoning` | 🧠 | Razonamiento, coordinación de equipos |
| `webcrawler` | 🕷️ | Búsqueda web con SearXNG, informes |

### `permissions`

Modo de permiso por herramienta. Los permisos disponibles dependen de los plugins y MCP servers activos.

| Modo | Comportamiento |
|------|---------------|
| `auto` | Se ejecuta siempre sin preguntar |
| `ask` | Solicita confirmación (con opción "siempre" para la sesión) |
| `deny` | Siempre denegado |

**Herramientas principales y sus permisos por defecto:**

| Herramienta | Defecto | Descripción |
|-------------|---------|-------------|
| `bash` | `ask` | Ejecutar comandos de shell |
| `read_file` | `auto` | Leer ficheros |
| `write_file` | `ask` | Crear o sobreescribir ficheros |
| `edit_file` | `ask` | Edición por reemplazo exacto |
| `edit_files` | `ask` | Edición atómica multi-fichero |
| `list_dir` | `auto` | Listar directorios |
| `web_search` | `auto` | Búsqueda DuckDuckGo/SearXNG |
| `web_fetch` | `auto` | Descargar URLs |
| `code_search` | `auto` | Búsqueda con ripgrep |
| `spawn_subagent` | `ask` | Lanzar subagente |
| `git_status/diff/log/branch` | `auto` | Lectura git |
| `git_commit/push/pull/add` | `ask` | Escritura git |
| `docker_ps/logs/images` | `auto` | Lectura Docker |
| `docker_exec/stop/rm` | `ask` | Control Docker |

### `context`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `minKeep` | 6 | Mensajes mínimos a conservar tras compactar |
| `compactThreshold` | 0.80 | Fracción del límite que dispara compactación automática |
| `maxSummaryChars` | 2100 | Chars máximos del resumen acumulado |
| `maxToolResultTokens` | 800 | Tokens máximos de un resultado de herramienta en el contexto |
| `autoContinueMax` | 8 | Auto-continuaciones máximas (0 = desactivado) |
| `highWater` | 0.70 | Fracción a partir de la cual se dispara la pre-compactación en background al volver a idle |
| `toolMaxChars` | 3000 | Chars máximos de un resultado de herramienta en la ventana de contexto compactada |
| `compactTarget` | 0.50 | Fracción **objetivo tras compactar**: la 2ª pasada trunca resultados de herramientas largos (salvo los 2 más recientes) hasta bajar de aquí, dejando headroom antes de `compactThreshold`. Súbela si prefieres conservar más contexto reciente; bájala para compactaciones más agresivas |
| `ctxMode` | `"mini"` | Modo de contexto del workspace al arrancar (`mini`\|`full`); equivale a `/ctx` |
| `planApproval` | `false` | Plan-mode al arrancar: si `true`, el agente pide tu aprobación antes de ejecutar cada plan (equivale a `/plan on`) |

> **Si tras compactar el contexto se queda alto (50–70%) con ficheros grandes:** es el síntoma de
> que la 2ª pasada no reducía lo suficiente. Desde v0.4.5 `compactTarget` (0.50) fuerza el truncado
> de los resultados de herramientas grandes conservados hasta bajar de ese objetivo. Combínalo con
> un `maxToolResultTokens` moderado (~8000) y un `minKeep` contenido (~9) para que las lecturas no
> inflen el contexto de trabajo entre compactaciones (los ejemplos de `doc/examples/` ya usan estos valores).

### `embeddings`

Configura la memoria semántica. Requiere un modelo de embeddings en Ollama.

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `model` | `nomic-embed-text-v2-moe:latest` | Modelo de embeddings |
| `maxInputChars` | 12000 | Chars máximos de texto a embeber |
| `similarityThreshold` | 0.30 | Score mínimo para incluir un resultado |
| `snippetChars` | 800 | Chars del snippet por resultado de memoria |
| `topK` | 3 | Memorias máximas recuperadas por búsqueda |
| `memoryEmbedEnabled` | `true` | Usar embeddings vectoriales para búsqueda semántica |
| `ramCacheMax` | 256 | Entradas máximas en la caché RAM de embeddings |

### `rag`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `enabled` | `true` | Activar RAG sobre el workspace |
| `topK` | 20 | Snippets máximos inyectados por turno |
| `similarityThreshold` | 0.35 | Score mínimo para incluir un snippet |
| `maxSnippetChars` | 28000 | Chars totales máximos de snippets RAG por turno |
| `topKComplex` | 35 | topK para tareas complejas (detectadas por longitud/keywords) |
| `thresholdComplex` | 0.25 | Threshold para tareas complejas |
| `maxFileChars` | 6000 | Chars máximos leídos de un fichero al indexar |
| `chunkChars` | 512 | Tamaño de cada chunk en chars |
| `chunkOverlap` | 64 | Solapamiento entre chunks consecutivos |
| `maxFiles` | 2000 | Número máximo de ficheros indexados en el workspace |
| `minSlotChars` | 200 | Chars mínimos de un chunk para ser indexado |
| `indexInterval` | 300 | Segundos mínimos entre re-indexaciones (incremental, en background) |

**Indexación del proyecto.** El RAG indexa el **directorio del proyecto** (no el workspace de identidad del agente) para que el agente recupere código relevante de forma semántica. Indexa solo ficheros con extensión de código y re-embebe en background, como máximo cada `indexInterval` segundos, **solo los ficheros cuyo `mtime` cambió** (incremental). El índice se **persiste** en `~/.oocode/search_index/` — la indexación inicial de un proyecto grande es un coste único; las siguientes son pequeñas. El estado se ve en la barra como `rag:idx(N)`. **Ignora artefactos de build/generados** (v0.4.8): `.git`, `node_modules`, `build`/`dist`/`target`, autotools (`.deps`/`.libs`/`autom4te.cache`), CMake, IDE (`.idea`/`.vscode`), `vendor`, y ficheros generados con extensión de fuente (`config.h`, `*_pb2.py`, `moc_*.cpp`, `ui_*.h`…) — para no malgastar embeds re-indexándolos en cada compilación. Si en un proyecto muy grande no necesitas recuperación semántica, sube `indexInterval`, baja `maxFiles`, o pon `enabled: false` (la memoria semántica `mem_save`/recuerdo es independiente).

### `tools`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `readFileLinesDefault` | 300 | Líneas por defecto en `read_file` |
| `readFileLinesWarnLarge` | 2000 | Avisa si el fichero supera este número de líneas |
| `webFetchMaxChars` | 16000 | Chars máximos extraídos de una URL |
| `webFetchTimeout` | 15 | Timeout en segundos de `web_fetch` |
| `webSearchMaxResults` | 5 | Resultados por defecto de `web_search` |
| `bashMaxOutputChars` | 75000 | Chars máximos de salida de bash |
| `codeSearchMaxResults` | 120 | Resultados máximos de `code_search` |
| `codeSearchContextLines` | 4 | Líneas de contexto en resultados |
| `toolCacheEnabled` | `true` | Caché intra-turno para evitar llamadas duplicadas |
| `toolCacheTTL` | 300 | Segundos de validez del caché |
| `toolCacheMaxSize` | 600 | Entradas máximas en el caché |

### `workspace`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `maxMemoryLines` | 12 | Líneas de MEMORY.md incluidas en el system prompt |
| `maxDailyChars` | 400 | Chars del log diario incluidos en el system prompt |

### `models`

Configuración por modelo. Formula del contexto disponible:
```
tokens_disponibles = contextWindow − maxTokens − systemOverhead
```

| Campo | Descripción |
|-------|-------------|
| `systemOverhead` | Tokens reservados para system prompt y schemas de tools |
| `configs.<modelo>.contextWindow` | Ventana de contexto total (igual a `num_ctx` enviado a Ollama) |
| `configs.<modelo>.maxTokens` | Tokens de salida reservados para la respuesta |
| `configs.<modelo>.timeoutSeconds` | Segundos sin tokens antes de activar el fallback |
| `configs.<modelo>.params` | Parámetros Ollama: `num_ctx`, `temperature`, `top_k`, `top_p` |

### `fallback`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `enabled` | `false` | Activa el mecanismo de fallback por timeout |
| `model` | `""` | Modelo alternativo (ej. `"qwen3.5:4b"`) |
| `timeoutSeconds` | 120 | Timeout por defecto si el modelo no tiene config propia |

### `mcp`

| Campo | Descripción |
|-------|-------------|
| `oocodeAssistant.enabled` | Activar servidor oocode-assistant (activo por defecto) |
| `systemAssistant.enabled` | Activar servidor system-assistant (activo por defecto) |
| `wordAssistant.enabled` | Activar servidor word-assistant (Word/PDF + núcleo O365) |
| `excelAssistant.enabled` | Activar servidor excel-assistant (hojas .xlsx/CSV) |
| `pptxAssistant.enabled` | Activar servidor pptx-assistant (presentaciones .pptx) |
| `mailAssistant.enabled` | Activar servidor mail-assistant (email/calendario/notas) |
| `cmdbAssistant.enabled` | Activar servidor cmdb-assistant (inventario IT) |
| `securityAssistant.enabled` | Activar servidor security-assistant |
| `iotAssistant.enabled` | Activar servidor iot-assistant |
| `requestTimeout` | Timeout en segundos para llamadas MCP (defecto: 30.0) |
| `servers` | Lista de servidores MCP externos (ver abajo) |

**Servidores MCP externos:**
```json
{
  "mcp": {
    "servers": [
      {
        "name": "mi-servidor",
        "cmd": ["npx", "@modelcontextprotocol/server-filesystem", "/ruta"],
        "env": {"HOME": "/home/usuario"}
      }
    ]
  }
}
```

### `hooks`

```json
{
  "hooks": {
    "builtins": [
      "lint_after_write",
      "lsp_after_write",
      "quick_syntax",
      "config_syntax_after_write",
      "backup_before_write",
      "test_after_write",
      "verify_after_edit",
      "interface_change_detector",
      "test_suite_delta",
      "todo_scan",
      "size_check",
      "log_tool_calls",
      "git_push_guard",
      "security_audit_log"
    ]
  }
}
```

Los hooks se activan/desactivan con `/hooks builtin <nombre>` en el REPL. Ver `doc/23_hooks.md` para descripción completa de cada hook.

### `searxng`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `url` | `""` | URL de la instancia SearXNG (vacío = desactivado) |
| `enabled` | `false` | `true` = reemplaza `web_search` con SearXNG |
| `maxResults` | 5 | Resultados máximos por búsqueda |
| `categories` | `"general"` | Categorías: `general`, `news`, `science`, `it` |
| `language` | `"auto"` | Idioma: `auto`, `es`, `en`, `fr`… |
| `safeSearch` | 0 | 0=off, 1=moderate, 2=strict |
| `timeout` | 10 | Timeout de conexión en segundos |

### `logging`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `enabled` | `true` | Activa escritura en fichero |
| `file` | `""` | Ruta del log (vacío = `~/.oocode/logs/oocode.log`) |
| `level` | `"info"` | `debug` / `info` / `warn` / `error` |
| `maxSizeMb` | 5 | Tamaño máximo antes de rotar |
| `maxFiles` | 3 | Ficheros rotados a conservar |

### `appearance`

| Campo | Defecto | Descripción |
|-------|---------|-------------|
| `accentColor` | `"cyan"` | Color del prompt y del banner. Valores: `cyan`, `green`, `blue`, `magenta`, `yellow`, `red`, `white` |

---

## Configuración por hardware

> **Ejemplos listos para copiar:** en [`doc/examples/`](examples/) hay tres perfiles
> mínimos (`oocode.4b-q4_0.json`, `oocode.4b-q8_0.json`, `oocode.9b-q8_0.json`) para ~8/12/16 GB
> de VRAM, con un [README](examples/README.md) que explica la diferencia entre cuantizaciones
> `q4_0`/`q8_0` (se elige al hacer `ollama pull`, no en `oocode.json`).

### 16 GB VRAM — qwen3.5:9b con 131K contexto (recomendado)

```json
{
  "models": {
    "systemOverhead": 20000,
    "configs": {
      "qwen3.5:9b": {
        "contextWindow":  131072,
        "maxTokens":      50000,
        "timeoutSeconds": 600,
        "params": {
          "num_ctx":     131072,
          "num_predict": 50000,
          "temperature": 0.7,
          "top_k":       20,
          "top_p":       0.95
        }
      }
    }
  },
  "context": {
    "maxToolResultTokens": 7000,
    "autoContinueMax":     16,
    "compactThreshold":    0.82
  },
  "tools": {
    "readFileLinesDefault":   400,
    "readFileLinesWarnLarge": 2000,
    "bashMaxOutputChars":     130000,
    "webFetchMaxChars":       25000
  }
}
```

**Tokens disponibles para historial:** `131072 − 50000 − 20000 = 61072`

### 16 GB VRAM — qwen3.5:9b con 65K contexto (alternativa)

```json
{
  "models": {
    "systemOverhead": 4000,
    "configs": {
      "qwen3.5:9b": {
        "contextWindow":  65000,
        "maxTokens":      32768,
        "timeoutSeconds": 600,
        "params": {
          "num_ctx":     65000,
          "num_predict": 32768,
          "temperature": 0.5,
          "top_k":       20,
          "top_p":       0.95
        }
      }
    }
  },
  "context": {
    "maxToolResultTokens": 2048,
    "autoContinueMax":     8
  }
}
```

**Tokens disponibles para historial:** `65000 − 32768 − 4000 = 28232`

### 8 GB VRAM — qwen2.5-coder:7b

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
          "temperature": 0.5,
          "top_k":       20,
          "top_p":       0.95
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

**Tokens disponibles para historial:** `32768 − 8192 − 2000 = 22576`

---

## CLI (sobreescribe oocode.json)

```bash
python oocode.py \
  --host http://192.168.1.100:11434 \   # sobreescribe api.host
  --model qwen3.5:9b \                  # sobreescribe model del agente
  --agent coding \                      # selecciona agente por ID
  --new                                 # fuerza nueva sesión
```

## Edición interactiva

```
/config          # muestra configuración completa en tablas
/config edit     # panel interactivo sección por sección
```

## Ficheros del directorio `~/.oocode/`

```
~/.oocode/
├── oocode.json           # configuración principal
├── oocode.json.bak       # backup automático de la última versión
├── history               # historial del REPL (prompt_toolkit)
├── webui_secret.key      # clave secreta de la sesión Flask (WebUI)
├── webui_state.json      # estado runtime del WebUI
│
├── workspace/
│   └── <agent_id>/       # workspace por agente
│       ├── IDENTITY.md   # quién eres (nombre, emoji, principios)
│       ├── SOUL.md       # cómo actúas
│       ├── USER.md       # información sobre el usuario
│       ├── AGENTS.md     # instrucciones de arranque y memoria
│       ├── HEARTBEAT.md  # tareas periódicas del agente
│       ├── TOOLS.md      # entorno local (permisos, host Ollama)
│       ├── MEMORY.md     # memoria a largo plazo editable
│       └── memory/       # logs diarios (YYYY-MM-DD.md)
│
├── sessions/
│   └── <agent_id>/       # sesiones por agente (JSONL)
│       └── sessions.json # índice de sesiones
│
├── memory/
│   └── <agent_id>/       # memoria semántica aislada por agente
│       ├── MEMORY.md     # índice de memorias
│       ├── *.md          # ficheros de memoria individual
│       └── *.emb.json    # vectores de embedding
│
├── logs/
│   ├── oocode.log        # log rotativo de actividad
│   ├── tool_calls.jsonl  # registro de tool calls (hook log_tool_calls)
│   └── security_audit.log # auditoría de tools de seguridad
│
├── plugins/
│   ├── enabled.json      # plugins activos
│   └── *.py              # ficheros de plugin
│
└── skills/
    ├── enabled.json      # skills activos
    └── *.py              # ficheros de skill
```
