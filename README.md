# OOCode — Ollama Open Code

Asistente de programación local para la terminal, inspirado en Claude Code pero funcionando **100% con [Ollama](https://ollama.com)**. Sin API keys, sin suscripciones, sin enviar tu código a servidores externos.

## ¿Por qué OOCode frente a Claude Code u OpenClaw?

### Frente a Claude Code

| | OOCode | Claude Code |
|---|---|---|
| **Coste** | Gratis — corres tu propio modelo | $20/mes (Max) o pay-per-token |
| **Privacidad** | 100% local, tu código no sale del equipo | El código se envía a servidores Anthropic |
| **Rate limits** | Sin límites — tantas peticiones como quieras | Límites por nivel de suscripción |
| **Latencia** | Depende de tu hardware | Depende de la red y carga de Anthropic |
| **Modelos** | Cualquier modelo Ollama (Qwen, DeepSeek, Llama…) | Sólo Claude (Sonnet, Opus, Haiku) |
| **Offline** | Funciona sin internet | Requiere conexión |
| **Plugins** | Sistema extensible con hooks Python | No extensible por el usuario |
| **Memoria semántica** | Persistente entre sesiones con embeddings locales | Requiere Pro/Max |

**Cuándo usar Claude Code en vez de OOCode:** cuando necesitas la máxima calidad de razonamiento del estado del arte en tareas muy complejas y el coste/privacidad no son restricciones.

### Frente a OpenClaw (y otros wrappers de Ollama)

OOCode está diseñado específicamente para Ollama con las siguientes ventajas sobre alternativas más genéricas:

- **TUI completa con prompt_toolkit** — barra de estado, scroll, historial, atajos Emacs, input multilinea; no sólo un wrapper de `requests`
- **Sistema de plugins con hooks** (`on_start`, `on_tool_result`, `system_prompt_injection`) — extensible sin tocar el núcleo
- **Plugin Git nativo** — 12 herramientas git (status, diff, log, commit, push, pull, branch, stash, patch, clone, worktree) + `/worktree` para git worktrees
- **Plugin Docker completo** — 19 herramientas docker y docker-compose (v1 y v2) con auto-detección
- **Plugin Diff al estilo Claude Code** — diffs con colores Rich automáticos en cada edición, numerados por línea, historial con `/diff`
- **Plugin Changelog** — registro automático de todos los cambios de fichero por sesión
- **Plugin Linter** — linting automático tras cada edición (ruff, mypy, eslint, shellcheck…)
- **Plugin Test Runner** — ejecuta los tests relevantes tras editar código (pytest, jest, go test, cargo test)
- **Plugin Ctags** — índice de símbolos del proyecto (funciones, clases, variables) con `/symbols`
- **Plugin TODO** — escanea y gestiona TODOs/FIXMEs del código con `/todo`
- **Plugin Clipboard** — copia/pega con el portapapeles del sistema con `/clip` y `/paste`
- **Plugin Tree-sitter** — análisis AST del código para extracción precisa de funciones y clases
- **Plugin Embeddings Search** — búsqueda semántica en el workspace indexado localmente
- **LSP integration** — 14 herramientas LSP (go-to-definition, references, hover, diagnostics, rename, format, code actions, workspace symbols, call hierarchy, restart…) con auto-arranque de servidores por extensión
- **MCP client** — conecta a cualquier servidor MCP (tools + resources + prompts), con paginación, reconexión automática y recarga en background
- **RAG workspace** — indexa el workspace con embeddings y auto-inyecta código relevante en el system prompt cada turno; indicador en toolbar
- **Memoria semántica persistente** — ficheros `.md` en `~/.oocode/memory/<agente>/` con índice `MEMORY.md`, recuperados por similitud con embeddings en cada turno
- **Compactación inteligente de contexto** — resumen automático con LLM + barra de progreso por fases; el agente nunca pierde el hilo
- **Auto-continuación en tareas largas** — si el modelo completa un bloque de trabajo y se detiene, OOCode lo relanza automáticamente (configurable, hasta 16 veces por turno con 120K contexto)
- **Hooks PreToolUse/PostToolUse** — intercepta y modifica tool calls antes y después; **18 hooks built-in**: diff, ctags, lint, quick_syntax, config_syntax (.json/.toml/.ini), lsp, autoformat, backup, check_secrets, log, todo_scan, test_after_write, size_check, verify_after_edit, test_suite_delta, interface_change_detector, git_push_guard, security_audit_log
- **Multi-file edit atómico** — edita múltiples ficheros en una sola llamada; si falla alguno hace rollback automático; soporta create y delete en el mismo batch
- **code_search con ripgrep** — búsqueda estructurada con glob, context lines, regex, fixed-string y límites configurables; fallback a grep; **progress en tiempo real** — muestra cada fichero encontrado mientras la búsqueda avanza
- **Input de imágenes** — adjunta imágenes al chat con rutas absolutas, relativas o `~`; indicador `🖼 vision` en toolbar cuando el modelo lo soporta
- **Git worktrees** — gestiona worktrees con `git_worktree` (list/add/remove/prune/lock) + slash command `/worktree`
- **Caché intra-turno** — evita ejecutar la misma tool con los mismos args dos veces en el mismo turno; configurable y con stats de hits/misses
- **Skills personalizados** — añade skills Python sin tocar el core; sistema de prioridades, inyección de dependencias
- **Gestión de subagentes** — lanza agentes en background con `spawn_subagent`, controla con `/subagents steer|kill|status`
- **SearXNG integrado** — motor de búsqueda privado local como alternativa a DuckDuckGo
- **`OOCODE.md` por proyecto** — equivalente al `CLAUDE.md` de Claude Code; OOCode lo inyecta automáticamente al arrancar desde el directorio del proyecto
- **Fallback automático** — si el modelo principal excede el timeout, cambia automáticamente a un modelo más ligero

### Rendimiento con modelos locales

Los modelos de código de Ollama han mejorado drásticamente. Para tareas típicas (leer/editar ficheros, ejecutar bash, buscar en web) la calidad es comparable a Claude 3.5 Sonnet:

| Modelo | VRAM | Calidad código | Velocidad | Contexto máx. (16 GB) |
|--------|------|----------------|-----------|----------------------|
| `qwen2.5-coder:32b` | 20 GB | ★★★★★ | Media | 32K |
| `qwen3.5:9b` | ~15 GB con 131K KV | ★★★★★ | Alta | **131K** (techo 16 GB) |
| `qwen2.5-coder:14b` | 9 GB | ★★★★☆ | Alta | 32K |
| `deepseek-r1:8b` | 6 GB | ★★★★☆ | Media | 32K |
| `qwen3.5:4b` | ~9 GB con 131K KV | ★★★☆☆ | Muy alta | **131K** (en 16 GB ✓) |
| `qwen2.5-coder:7b` | 5 GB | ★★★☆☆ | Muy alta | 32K |

**Consejo:** `qwen3.5:9b` con `num_ctx=131072` es el mejor equilibrio calidad/velocidad/contexto en 2026. Qwen3.5 soporta 256K en teoría, pero **131072 (2¹⁷) es el límite práctico con 16 GB de VRAM** reservando espacio para el modelo de embeddings. Para GPU con 8 GB o menos, `qwen3.5:4b` con contexto 65K–131K es la mejor opción.

---

## Características

- **100% local** — todo corre en tu máquina, nada sale a internet (salvo búsquedas web explícitas)
- **Tool calling nativo** — el modelo llama a herramientas reales (bash, ficheros, web, git, docker…)
- **9 plugins incluidos** — lsp (14 tools), embeddings search, changelog, todo, clipboard, tree-sitter, test runner, vault, searxng
- **2 skills incluidos** — converters (base64/hash/url/json/hex), snippets (biblioteca personal de código)
- **103 tools MCP** — servidor `oocode-assistant` incluido: git, docker, filesystem, debug, build, system, symbols, utils y más; 32 prompts; 18 resources
- **Sistema de plugins extensible** — hooks `on_start`, `on_tool_result`, `system_prompt_injection` sin tocar el núcleo
- **Contexto persistente** — sesiones, memoria semántica con embeddings, compactación automática con LLM
- **Auto-continuación** — `autoContinueMax` (default 16) lanza al agente automáticamente si se para en mitad de una tarea larga
- **Diff al estilo Claude Code** — diffs numerados y con colores en cada edición de fichero
- **Docker completo** — docker y docker-compose v1/v2 con auto-detección, 22 herramientas
- **Búsqueda semántica local** — indexa el workspace con embeddings y busca por significado
- **SearXNG integrado** — motor de búsqueda privado local como alternativa a DuckDuckGo
- **Logs rotativos** — trazabilidad completa de la actividad
- **Compatible con `/slash` commands** al estilo Claude Code
- **Input multilinea con wrap** — el prompt crece hacia abajo al escribir texto largo
- **TUI avanzada** — spinner ◐ parpadeante; resultados inline compactos (⎿ N resultados en X ficheros); progreso de búsqueda en tiempo real; **task progress panel** ✔/◼/◻ con planes multi-tarea activos
- **Filtrado adaptativo de schemas** — reduce ~4–6K tokens de overhead enviando solo los schemas relevantes para el tipo de tarea (git, docker, sistema, etc.); sin coste cuando no aplica (fallback a todos los schemas)
- **Checkpoint de tarea** — rastrea ficheros ya modificados en cada tarea; en auto-continúas inyecta `📍 CHECKPOINT` con la lista para que el agente no repita trabajo ya hecho
- **Compactación estructurada** — al compactar el contexto, incluye lista de ficheros modificados y resultado de tests en el resumen para que el agente recuerde el estado tras la compactación
- **Guardas anti-alucinación** — verifica que `old_string` existe exactamente antes de `edit_file` (cuando el fichero ya fue leído); verifica que la ruta existe antes de `read_sections`/`code_outline`/`diff_files`; muestra líneas similares como pistas para corregir
- **Vault de credenciales cifrado** — contraseñas SSH, tokens Git, claves API protegidas con AES-Fernet + PBKDF2-SHA256
- **Input interactivo integrado en el TUI** — todos los comandos `/slash` que piden datos usan el prompt nativo sin bloquear el terminal
- **Memoria aislada por agente** — cada agente tiene su propia carpeta `~/.oocode/memory/<id>/`
- **Fallback automático por timeout** — configura un modelo ligero de reserva si el principal tarda demasiado
- **Caché de prompts** — optimiza tokens con caché de prompts frecuentes (`cache_dir` en `context`)
- **Contexto configurable** — ventana de contexto dinámica (`context_window_default`, `context_window_min`, `context_window_max`)

## Requisitos

- Python 3.10+
- [Ollama](https://ollama.com) instalado y ejecutándose (local o en red)
- Al menos un modelo con soporte de tool calling

---

## Despliegue de Ollama y SearXNG

OOCode necesita **Ollama** como backend de inferencia y, opcionalmente, **SearXNG** para búsquedas web privadas. Ambos se despliegan con Docker en cualquier sistema operativo.

### Nota sobre Windows

> **OOCode Python no funciona nativamente en Windows.** El agente depende de herramientas de sistema Unix (`bash`, `grep`, `find`, `ripgrep`, `ctags`, `ruff`, etc.) que no están disponibles de forma nativa. Hay dos opciones viables:
>
> - **WSL2 (recomendado)**: instala OOCode dentro de WSL2 (Ubuntu/Debian). Puede conectar a los contenedores Docker Desktop corriendo en el host Windows, ya que Docker Desktop expone el socket a WSL2 automáticamente.
> - **Contenedor Linux**: ejecuta OOCode dentro de un contenedor Linux que llame a Ollama y SearXNG en el host Windows vía red local (por ejemplo, `http://host.docker.internal:11434`).
>
> Ollama y SearXNG **sí funcionan** en Windows con Docker Desktop, y puedes acceder a ellos desde otros equipos de la LAN igual que en Linux o Mac.

---

### Despliegue de Ollama

#### Linux / Mac (nativo)

```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Iniciar el servidor (escucha en localhost:11434 por defecto)
ollama serve

# En otra terminal — descargar un modelo recomendado
ollama pull qwen3.5:9b          # 8 GB VRAM — recomendado para 16 GB RAM
ollama pull qwen2.5-coder:7b    # 5 GB VRAM — recomendado para 8 GB RAM
ollama pull nomic-embed-text-v2-moe  # embeddings semánticos (ligero)
```

Para escuchar en toda la red local (acceso desde otros equipos o contenedores):

```bash
# Opción A — variable de entorno (temporal)
OLLAMA_HOST=0.0.0.0 ollama serve

# Opción B — servicio systemd permanente
sudo systemctl edit ollama --force
# Añadir en la sección [Service]:
# Environment="OLLAMA_HOST=0.0.0.0"
sudo systemctl restart ollama
```

#### Linux / Mac (Docker)

```bash
# CPU only
docker run -d --name ollama \
  -p 11434:11434 \
  -v ollama-data:/root/.ollama \
  --restart unless-stopped \
  ollama/ollama

# GPU NVIDIA
docker run -d --name ollama \
  --gpus all \
  -p 11434:11434 \
  -v ollama-data:/root/.ollama \
  --restart unless-stopped \
  ollama/ollama

# Descargar modelo
docker exec ollama ollama pull qwen3.5:9b
docker exec ollama ollama pull nomic-embed-text-v2-moe
```

#### Windows (Docker Desktop)

1. Instala [Docker Desktop](https://www.docker.com/products/docker-desktop/) con soporte WSL2 activado.
2. Abre PowerShell o Windows Terminal:

```powershell
# CPU only
docker run -d --name ollama `
  -p 11434:11434 `
  -v ollama-data:/root/.ollama `
  --restart unless-stopped `
  ollama/ollama

# GPU NVIDIA (requiere CUDA drivers y nvidia-container-toolkit en WSL2)
docker run -d --name ollama `
  --gpus all `
  -p 11434:11434 `
  -v ollama-data:/root/.ollama `
  --restart unless-stopped `
  ollama/ollama

# Descargar modelo
docker exec ollama ollama pull qwen3.5:9b
docker exec ollama ollama pull nomic-embed-text-v2-moe
```

3. Ollama estará disponible en `http://localhost:11434` desde Windows, y en `http://host.docker.internal:11434` desde contenedores o WSL2.

Para acceder desde otros equipos de la LAN, expone el puerto indicando la IP local:
```powershell
docker run -d --name ollama `
  -p 192.168.1.33:11434:11434 `   # reemplaza con tu IP
  -v ollama-data:/root/.ollama `
  --restart unless-stopped `
  ollama/ollama
```

---

### Despliegue de SearXNG (búsqueda web privada)

SearXNG es opcional pero muy recomendado: elimina la dependencia de DuckDuckGo y permite búsquedas sin rate-limits ni tracking.

#### Docker Compose (recomendado en todos los SO)

Crea `docker-compose.searxng.yml`:

```yaml
version: "3.8"

services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    ports:
      - "8888:8080"
    volumes:
      - searxng-config:/etc/searxng
    environment:
      - SEARXNG_BASE_URL=http://localhost:8888/
      - SEARXNG_SECRET_KEY=cambiar-por-clave-aleatoria
    restart: unless-stopped

volumes:
  searxng-config:
```

```bash
# Linux / Mac
docker compose -f docker-compose.searxng.yml up -d

# Windows PowerShell
docker compose -f docker-compose.searxng.yml up -d
```

Luego habilita el formato JSON en SearXNG (necesario para que OOCode pueda leer los resultados):

```bash
# Edita el fichero de configuración
docker exec -it searxng sh -c "cat /etc/searxng/settings.yml" | grep -A2 "formats:"
# Si no aparece json, edita el fichero:
docker exec -it searxng sh -c \
  "sed -i 's/formats:/formats:\n  - json/' /etc/searxng/settings.yml"
docker restart searxng
```

O simplemente configura `settings.yml` con:
```yaml
search:
  formats:
    - html
    - json
```

#### Configurar OOCode para usar SearXNG

Edita `~/.oocode/oocode.json`:

```json
{
  "searxng": {
    "url": "http://localhost:8888",
    "enabled": true,
    "maxResults": 8,
    "categories": "general",
    "language": "auto",
    "safeSearch": 0,
    "timeout": 30
  }
}
```

Para conectar a SearXNG en otro equipo de la LAN (o desde WSL2 al host Windows):

```json
{
  "searxng": {
    "url": "http://192.168.1.33:8888",
    "enabled": true
  },
  "ollama": {
    "host": "http://192.168.1.33:11434"
  }
}
```

---

### docker-compose.yml todo-en-uno

Para levantar Ollama + SearXNG juntos:

```yaml
version: "3.8"

services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
    restart: unless-stopped
    # Para GPU NVIDIA: descomenta la siguiente línea
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]

  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    ports:
      - "8888:8080"
    volumes:
      - searxng-config:/etc/searxng
    environment:
      - SEARXNG_BASE_URL=http://localhost:8888/
      - SEARXNG_SECRET_KEY=cambia-esto-por-una-clave-aleatoria
    restart: unless-stopped

volumes:
  ollama-data:
  searxng-config:
```

```bash
# Arrancar todo
docker compose up -d

# Descargar modelos
docker exec ollama ollama pull qwen3.5:9b
docker exec ollama ollama pull nomic-embed-text-v2-moe

# Verificar que todo funciona
curl http://localhost:11434/api/tags          # Ollama
curl "http://localhost:8888/?q=test&format=json"  # SearXNG
```

---

## Instalación

```bash
git clone https://github.com/tu-usuario/oocode
cd oocode
./install.sh
```

El instalador:
1. Ejecuta `pip install -e .` — registra el comando `oocode` en tu PATH (vía `~/.local/bin/`)
2. Crea `~/.oocode/oocode.json` con la configuración por defecto (si no existe)
3. Sincroniza plugins y skills a `~/.oocode/plugins/` y `~/.oocode/skills/`
4. Comprueba herramientas opcionales (git, docker, ctags, ruff, etc.)

Como es una **instalación editable**, `git pull` actualiza OOCode inmediatamente sin reinstalar.

### Instalación manual con pip

```bash
pip install --user -e /ruta/a/oocode
```

Esto registra el comando `oocode` en `~/.local/bin/oocode`. Asegúrate de que `~/.local/bin` está en tu `PATH`.

### Uso sin instalar (desde el repo)

```bash
# Ejecutar directamente
python /ruta/a/oocode/oocode.py

# O añadir el repo al PATH
export PATH="/ruta/a/oocode:$PATH"
oocode
```

## Uso

```bash
# Desde cualquier directorio — selección interactiva de modelo
oocode

# Con modelo y directorio de proyecto
oocode --model qwen3.5:9b /ruta/a/tu/proyecto

# Servidor Ollama en red local
oocode --host http://192.168.1.33:11434

# Agente específico definido en oocode.json
oocode --agent coding
```

## Configuración por hardware

### 16 GB VRAM — configuración recomendada (131K contexto)

Permite `qwen3.5:9b` o `batiai/qwen3.5-9b` con el **contexto máximo de 131072 tokens** (2¹⁷) para hardware con 16 GB de VRAM. Qwen3.5 soporta hasta 256K según la documentación oficial, pero el límite práctico con 16 GB es 131K — más allá, el KV cache compite con el modelo de embeddings y se producen errores OOM.

Ideal para proyectos grandes: ficheros de 5000+ líneas, refactorizaciones extensas, tareas multi-fichero largas sin necesidad de compactar.

**Presupuesto de memoria (16 GB VRAM):**
| Componente | VRAM aprox. |
|------------|-------------|
| qwen3.5:9b pesos (Q4_K_M) | ~5.5 GB |
| KV cache a 131K tokens | ~9.5 GB |
| nomic-embed-text-v2-moe | ~0.7 GB |
| **Total** | **~15.7 GB** |

```json
{
  "ollama": { "host": "http://localhost:11434" },

  "agents": {
    "list": [
      {
        "id": "main", "name": "OOCode", "emoji": "🤖",
        "model": "qwen3.5:9b",
        "workspace": "~/.oocode/workspace/main"
      }
    ]
  },

  "context": {
    "minKeep": 10,
    "compactThreshold": 0.82,
    "maxSummaryChars": 14000,
    "maxToolResultTokens": 7000,
    "autoContinueMax": 16
  },

  "tools": {
    "readFileLinesDefault": 400,
    "readFileLinesWarnLarge": 2000,
    "webFetchMaxChars": 25000,
    "webFetchTimeout": 20,
    "webSearchMaxResults": 10,
    "bashMaxOutputChars": 130000,
    "codeSearchMaxResults": 120,
    "codeSearchContextLines": 4,
    "codeSearchMaxFilesize": "2M",
    "toolCacheMaxSize": 600
  },

  "workspace": {
    "maxMemoryLines": 150,
    "maxDailyChars": 8000
  },

  "models": {
    "systemOverhead": 20000,
    "configs": {
      "qwen3.5:9b": {
        "contextWindow": 131072,
        "maxTokens": 50000,
        "timeoutSeconds": 600,
        "params": {
          "num_ctx": 131072,
          "num_predict": 50000,
          "temperature": 0.7,
          "top_k": 20,
          "top_p": 0.95
        }
      },
      "qwen3.5:4b": {
        "contextWindow": 131072,
        "maxTokens": 50000,
        "timeoutSeconds": 600,
        "params": {
          "num_ctx": 131072,
          "num_predict": 50000,
          "temperature": 0.5,
          "top_k": 20,
          "top_p": 0.95
        }
      },
      "deepseek-r1:8b": {
        "contextWindow": 32768,
        "maxTokens": 12288,
        "timeoutSeconds": 300,
        "params": {
          "num_ctx": 32768,
          "num_predict": 12288,
          "temperature": 0.6,
          "top_k": 20,
          "top_p": 0.95
        }
      }
    }
  },

  "fallback": {
    "enabled": true,
    "model": "qwen3.5:4b",
    "timeoutSeconds": 600
  },

  "embeddings": {
    "model": "nomic-embed-text-v2-moe:latest",
    "maxInputChars": 20000,
    "similarityThreshold": 0.3,
    "snippetChars": 1200,
    "topK": 10
  },

  "rag": {
    "enabled": true,
    "topK": 20,
    "similarityThreshold": 0.35,
    "maxSnippetChars": 28000,
    "topKComplex": 35,
    "thresholdComplex": 0.25,
    "complexMinChars": 120
  },

  "snapshots": { "enabled": true, "maxSnapshots": 40 },

  "mcp": { "requestTimeout": 30.0 }
}
```

> **Fórmula del contexto disponible:**
> ```
> tokens disponibles = contextWindow − maxTokens − systemOverhead
>                    = 131072 − 50000 − 20000 = 61072 tokens para historial
> ```
> `compactThreshold=0.82` → compacta al llegar a **107K tokens acumulados**.
> Tras la compactación el historial baja a ~5K tokens, dejando 126K tokens libres para el turno siguiente.
>
> **¿Por qué 0.82 y no 0.85?** A 131K, un threshold de 0.85 disparó compactación a 111K pero la siguiente respuesta (máx. 50K tokens) podía sumar 161K > 131K en un turno pesado. Con 0.82 → 107K, el margen es 24K tokens — suficiente para salidas grandes sin riesgo de truncación.
>
> **RAG budget:** `maxSnippetChars=28000 ÷ topK=20 = 1400 chars/snippet ≈ 7000 tokens` de contexto semántico por turno.

---

### 16 GB VRAM — configuración alternativa (65K contexto)

Útil si el modelo sufre timeouts con 131K, si el servidor Ollama está en red local con latencia alta, o si necesitas ejecutar otro proceso pesado en paralelo.

```json
{
  "ollama": { "host": "http://localhost:11434" },

  "agents": {
    "list": [
      {
        "id": "main", "name": "OOCode", "emoji": "🤖",
        "model": "qwen3.5:9b-65k",
        "workspace": "~/.oocode/workspace/main"
      }
    ]
  },

  "context": {
    "minKeep": 6,
    "compactThreshold": 0.85,
    "maxSummaryChars": 2100,
    "maxToolResultTokens": 2048,
    "autoContinueMax": 8
  },

  "tools": {
    "readFileLinesDefault": 300,
    "readFileLinesWarnLarge": 2000,
    "webFetchMaxChars": 16000,
    "webFetchTimeout": 15,
    "webSearchMaxResults": 5,
    "bashMaxOutputChars": 75000
  },

  "models": {
    "systemOverhead": 4000,
    "configs": {
      "qwen3.5:9b-65k": {
        "contextWindow": 65000,
        "maxTokens": 32768,
        "timeoutSeconds": 600,
        "params": {
          "num_ctx": 65000,
          "num_predict": 32768,
          "temperature": 0.5,
          "top_k": 20,
          "top_p": 0.95
        }
      },
      "qwen3.5:4b": {
        "contextWindow": 32768,
        "maxTokens": 16384,
        "timeoutSeconds": 120,
        "params": {
          "num_ctx": 32768,
          "num_predict": 16384,
          "temperature": 0.5
        }
      }
    }
  },

  "fallback": {
    "enabled": true,
    "model": "qwen3.5:4b",
    "timeoutSeconds": 120
  },

  "embeddings": {
    "model": "nomic-embed-text-v2-moe:latest",
    "maxInputChars": 12000,
    "similarityThreshold": 0.30,
    "snippetChars": 800,
    "topK": 3
  }
}
```

> **Fórmula del contexto disponible:**
> `tokens_historia = contextWindow − maxTokens − systemOverhead`
> Con esta config: `65000 − 32768 − 4000 = 28232 tokens` para el historial de la conversación.

### 8 GB VRAM — configuración recomendada

Permite `qwen2.5-coder:7b` o `qwen3.5:4b` con contexto de 32K. Adecuado para la mayoría de tareas de programación.

```json
{
  "ollama": { "host": "http://localhost:11434" },

  "agents": {
    "list": [
      {
        "id": "main", "name": "OOCode", "emoji": "🤖",
        "model": "qwen2.5-coder:7b",
        "workspace": "~/.oocode/workspace/main"
      }
    ]
  },

  "context": {
    "minKeep": 6,
    "compactThreshold": 0.80,
    "maxSummaryChars": 1500,
    "maxToolResultTokens": 1024,
    "autoContinueMax": 5
  },

  "tools": {
    "readFileLinesDefault": 150,
    "readFileLinesWarnLarge": 500,
    "webFetchMaxChars": 8000,
    "webFetchTimeout": 15,
    "webSearchMaxResults": 5,
    "bashMaxOutputChars": 30000
  },

  "models": {
    "systemOverhead": 2000,
    "configs": {
      "qwen2.5-coder:7b": {
        "contextWindow": 32768,
        "maxTokens": 8192,
        "timeoutSeconds": 180,
        "params": {
          "num_ctx": 32768,
          "num_predict": 8192,
          "temperature": 0.5,
          "top_k": 20,
          "top_p": 0.95
        }
      },
      "qwen3.5:4b": {
        "contextWindow": 32768,
        "maxTokens": 8192,
        "timeoutSeconds": 120,
        "params": {
          "num_ctx": 32768,
          "num_predict": 8192,
          "temperature": 0.5
        }
      }
    }
  },

  "fallback": {
    "enabled": true,
    "model": "qwen3.5:4b",
    "timeoutSeconds": 120
  },

  "embeddings": {
    "model": "nomic-embed-text-v2-moe:latest",
    "maxInputChars": 6000,
    "similarityThreshold": 0.30,
    "snippetChars": 400,
    "topK": 3
  }
}
```

> **Fórmula del contexto disponible:**
> Con esta config: `32768 − 8192 − 2000 = 22576 tokens` para el historial de la conversación.

> **Nota:** Si tienes exactamente 8 GB de VRAM y el modelo no carga, prueba a reducir `contextWindow` a `16384` y ajusta `maxTokens` a `4096`.

---

## Plugins incluidos

| Plugin | Descripción | Herramientas | Comando |
|--------|-------------|--------------|---------|
| `lsp` | 14 tools LSP: definition, references, hover, rename, format, diagnostics, workspace symbols, call hierarchy, restart… | 14 LSP tools | `/lsp` |
| `embeddings_search` | Indexa el workspace y busca por similitud semántica | `index_workspace`, `semantic_search` | — |
| `changelog` | Registro automático de cambios de fichero por sesión | `changelog_today`, `changelog_session`, `changelog_week` | — |
| `todo` | Escanea y gestiona TODOs/FIXMEs del código fuente | `todo_list`, `todo_add`, `todo_done` | `/todo` |
| `clipboard` | Copiar/pegar con el portapapeles del sistema | `clipboard_copy`, `clipboard_paste` | `/clip`, `/paste` |
| `tree_sitter` | Análisis AST: extrae funciones, clases e imports con precisión | `extract_functions`, `extract_classes`, `extract_imports`, `ast_summary` | — |
| `test_runner` | Ejecuta tests tras editar código (pytest, jest, go, cargo) | `run_tests`, `test_file` | `/test` |
| `vault` | Vault cifrado de credenciales SSH, Git, DB y API | `vault_list`, `vault_get` | `/vault` |
| `searxng` | Búsqueda web privada con instancia SearXNG local | `searxng_search` | — |

> **Nota:** Git, Docker, Diff, Linter, Ctags ya no son plugins — sus funcionalidades se activaron como **hooks nativos** (`diff_after_write`, `lint_after_write`, `ctags_after_write`, `lsp_after_write`) y **tools MCP** (103 tools en `mcp_servers/oocode_assistant.py`).

Activa plugins con `/plugins enable <nombre>`. Los activos se persisten en `oocode.json`.

## Skills incluidos

Los skills añaden herramientas al agente (igual que los plugins, pero sin hooks de ciclo de vida).

| Skill | Descripción | Activar |
|-------|-------------|---------|
| `converters` | Base64, URL-encode/decode, hashes (md5/sha256…), bases numéricas, JSON, hex, escape | `/skills enable converters` |
| `snippets` | Biblioteca personal de fragmentos de código: guardar, buscar, recuperar | `/skills enable snippets` |

## Herramientas base disponibles

| Herramienta | Descripción | Permiso defecto |
|-------------|-------------|-----------------|
| `read_file` | Lee ficheros con números de línea | `auto` |
| `write_file` | Crea o sobreescribe ficheros | `ask` |
| `edit_file` | Edición por reemplazo exacto de cadena | `ask` |
| `edit_files` | Edición atómica multi-fichero con rollback; soporta `create`, `delete`, `replace_all` | `ask` |
| `list_dir` | Lista contenido de directorios | `auto` |
| `bash` | Ejecuta comandos de shell (timeout 120s) | `ask` |
| `web_search` | Busca en DuckDuckGo (sin API key) | `auto` |
| `web_fetch` | Descarga y extrae texto de URLs (timeout 15s) | `auto` |
| `code_search` | Busca en código fuente con ripgrep (regex, glob, context, fixed-string) | `auto` |
| `spawn_subagent` | Lanza un subagente con workspace aislado | `ask` |

## Configuración completa (referencia)

Todo se configura en `~/.oocode/oocode.json`. Se genera automáticamente al arrancar por primera vez. Edita con `/config edit` desde el REPL o directamente con cualquier editor.

Ver `doc/02_configuration.md` para la referencia completa de todos los campos.

## Comandos `/slash` (resumen)

| Comando | Descripción |
|---------|-------------|
| `/help` | Ayuda completa con todos los comandos |
| `/doctor` | Diagnóstico: Ollama, modelos, plugins, herramientas externas, dependencias |
| `/logs [n]` | Últimas n líneas del log de actividad |
| `/config [edit]` | Ver o editar configuración interactivamente |
| `/model [nombre]` | Ver o cambiar modelo; `/model timeout <s>` configura el timeout |
| `/model fallback <modelo>` | Configura modelo de reserva por timeout |
| `/models` | Seleccionar modelo de Ollama |
| `/think [off\|min\|low\|med\|high]` | Nivel de razonamiento interno (persiste por modelo) |
| `/reasoning [on\|off]` | Activa/desactiva tokens de razonamiento extendido |
| `/compact` | Compactar contexto con resumen LLM |
| `/mem` | Gestión de memoria persistente (list/search/show/save/rm/rebuild) |
| `/tasks` | Lista de tareas todo/wip/done |
| `/schedule` | Jobs periódicos |
| `/plugins` | Gestión de plugins (list/enable/disable/reload/create) |
| `/skills` | Gestión de skills (list/enable/disable/create) |
| `/subagents` | Ver, steer y kill subagentes activos |
| `/spawn <id> <tarea>` | Lanza un subagente con tarea específica |
| `/color [tema]` | Esquema de color del prompt |
| `/branch` | Ramas de conversación (save/load/list/rm) |
| `/btw <pregunta>` | Pregunta rápida sin interrumpir el contexto |
| `/init [ruta]` | Genera `OOCODE.md` para el proyecto |
| `/git [log\|diff\|staged]` | Estado del repositorio git actual |
| `/worktree [add\|remove\|prune]` | Gestiona git worktrees |
| `/diff [fichero]` | Historial de diffs de la sesión |
| `/mcp` | Estado de servidores MCP conectados |
| `/lsp [start\|stop\|restart\|status]` | Gestión de servidores LSP |
| `/rag [enable\|disable\|reindex]` | Control del índice RAG del workspace |
| `/hooks [builtin <nombre>]` | Ver y activar hooks PreToolUse/PostToolUse |
| `/docker [subcmd]` | Estado Docker/compose: `ps`, `up`, `down`, `logs`… |
| `/lint [fichero]` | Linting del fichero o proyecto actual |
| `/test [fichero]` | Ejecuta tests del proyecto o fichero indicado |
| `/symbols [ruta]` | Índice de símbolos del proyecto (ctags) |
| `/todo [add\|done\|sync]` | Gestión de TODOs/FIXMEs del código |
| `/clip <texto>` | Copia texto al portapapeles del sistema |
| `/paste` | Pega contenido del portapapeles como mensaje |
| `/vault [init\|unlock\|lock\|add\|show\|rm]` | Gestión del vault de credenciales cifrado |
| `/exit` | Sale de OOCode |

Ver `/help` en el REPL para la lista completa con todos los subcomandos.

## OOCODE.md — instrucciones por proyecto

Crea `OOCODE.md` en la raíz de tu proyecto (equivalente al `CLAUDE.md` de Claude Code). OOCode lo detecta e inyecta automáticamente como contexto del sistema al arrancar **desde ese directorio** o al pasar la ruta como argumento:

```bash
cd /mi/proyecto && oocode          # detecta OOCODE.md automáticamente
oocode /mi/proyecto                # equivalente explícito
```

Genera una plantilla con `/init`. También puedes definir hooks en el fichero:

```markdown
## Hooks
post write_file: ruff check {path} --fix
post edit_file:  mypy {path}
```

## MCP — Model Context Protocol

OOCode incluye 5 servidores MCP bundled y actúa como cliente para conectar a cualquier servidor externo.

### Servidores bundled

Los servidores incluidos se activan con flags en `oocode.json` — **no los listes en `mcp.servers`** o se arrancarán dos veces:

```json
{
  "mcp": {
    "oocodeAssistant":    { "enabled": true  },
    "systemAssistant":    { "enabled": true  },
    "homeOfficeAssistant":{ "enabled": false },
    "securityAssistant":  { "enabled": false },
    "iotAssistant":       { "enabled": false },
    "requestTimeout": 30.0
  }
}
```

| Servidor | Flag | Tools | Por defecto |
|----------|------|-------|-------------|
| `oocode-assistant` | `oocodeAssistant.enabled` | 103 tools — git, docker, fs, debug, build, symbols, utils | ✓ activo |
| `system-assistant` | `systemAssistant.enabled` | Systemctl, journalctl, red, disco, paquetes, procesos | ✓ activo |
| `home-office-assistant` | `homeOfficeAssistant.enabled` | Email, calendario, documentos, OCR, xlsx | desactivado |
| `security-assistant` | `securityAssistant.enabled` | nmap, nikto, gobuster, ssl, dns, hash, JWT, CTF | desactivado |
| `iot-assistant` | `iotAssistant.enabled` | TAPO, Blink, Alexa, Tuya, Home Assistant, MQTT, ESPHome | desactivado |

### Servidores externos

Usa `mcp.servers` solo para servidores externos (no bundled):

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

Gestiona servidores MCP con `/mcp` en el REPL.

## RAG — workspace semántico

OOCode indexa automáticamente tu workspace con embeddings y auto-inyecta código relevante en cada turno. El indicador `◈ rag:N` en la toolbar muestra los ficheros indexados.

```bash
/rag              # ver estado del índice
/rag enable       # activar (inicialización en caliente)
/rag reindex      # re-indexar con progreso
/rag disable      # desactivar
```

Parámetros configurables en `/config` → RAG: `topK`, `similarityThreshold`, `maxSnippetChars`, `indexInterval`.

## Hooks PreToolUse / PostToolUse

Intercepta tool calls antes o después de ejecutarlas. **18 hooks built-in** incluidos:

| Hook | Cuándo | Efecto |
|------|--------|--------|
| `diff_after_write` | post, todos los writes | Diff visual estilo Claude Code. **Activo por defecto.** |
| `ctags_after_write` | post, todos los writes | Reconstruye índice de símbolos (ctags). **Activo por defecto.** |
| `lint_after_write` | post, todos los writes | ruff/mypy/eslint/shellcheck/etc. **Activo por defecto.** |
| `quick_syntax_after_write` | post, .py | `ast.parse` instantáneo sin deps. **Activo por defecto.** |
| `config_syntax_after_write` | post, .json/.toml/.ini/.cfg | Valida sintaxis de configs con stdlib. **Activo por defecto.** |
| `lsp_after_write` | post, exts LSP | Ejecuta `lsp_diagnostics` al guardar. |
| `autoformat_after_write` | post, todos | Formatea vía LSP (black/prettier/gofmt…). |
| `backup_before_write` | pre, todos | Crea copia `.bak` antes de sobreescribir. |
| `check_secrets` | pre, write_file | Bloquea escrituras con credenciales reales. |
| `log_tool_calls` | post, todos | Registra en `~/.oocode/logs/tool_calls.jsonl`. |
| `todo_scan_after_write` | post, todos | Muestra TODO/FIXME/HACK encontrados (hasta 5). |
| `test_after_write` | post, .py | Ejecuta pytest del test file asociado (30s). |
| `size_check_after_write` | post, todos | Avisa si el fichero supera 300 líneas o 15 KB. |
| `verify_after_edit` | post, edit_file | Re-lee la sección modificada y marca cambios con `▶`. |
| `test_suite_delta` | **pre+post** pair | Captura baseline y reporta solo regresiones/fixes nuevos. |
| `interface_change_detector` | **pre+post** pair, .py | Detecta cambios de firma/API pública; busca callers con ripgrep. |
| `git_push_guard` | pre, git_commit/git_push | Avisa si el mensaje es vacío/genérico o si la rama es protegida. |
| `security_audit_log` | post, Security MCP tools | Registra en `~/.oocode/logs/security_audit.log` cada herramienta de seguridad usada. |

```bash
/hooks                                      # ver hooks activos
/hooks builtin lint_after_write             # activar/desactivar built-in
/hooks builtin backup_before_write          # crear .bak antes de cada edición
/hooks builtin check_secrets                # bloquear escrituras con credenciales
/hooks builtin test_suite_delta             # detectar regresiones automáticamente
/hooks builtin interface_change_detector    # vigilar cambios de API pública
```

También puedes definir hooks de shell en `OOCODE.md` (sección `## Hooks`).

## Fallback automático por timeout

Si el modelo principal no responde en el tiempo configurado, OOCode cambia automáticamente a un modelo más ligero:

```
/model timeout 600       # timeout de 600s para el modelo activo
/model fallback qwen3.5:4b  # modelo de reserva
```

O en `oocode.json`:
```json
"fallback": { "enabled": true, "model": "qwen3.5:4b", "timeoutSeconds": 120 }
```

## TUI — Visualización compacta de herramientas

OOCode usa un sistema de display de dos etapas para mostrar el progreso de las tools de forma eficiente:

### Spinner ◐ pulsante para todas las tools

Antes de ejecutar **cualquier** herramienta, el TUI muestra:
```
  ◐ code_search  [pattern="AgentLoop", glob="*.py"]
```
El círculo ◐ indica que la herramienta está ejecutándose. El color varía según el tipo:
- **Verde** (`◐`) — write, edit (ficheros)
- **Cyan** (`◐`) — memory tools
- **Dim** (`◐`) — resto de herramientas

### Progreso de búsqueda en tiempo real

Durante búsquedas (`code_search`, `grep_code`, `multi_grep`…), el status bar actualiza en tiempo real mostrando el fichero que se está leyendo:

```
  ◐ code_search…  ⎿ loop.py  ◐◑◒◓
```

Cada fichero nuevo encontrado por ripgrep se muestra inline a medida que se descubre, gracias al módulo `tools/progress.py` y al streaming de `subprocess.Popen`.

### Resultados compactos inline

Al terminar la ejecución, el header se reemplaza por un resultado compacto de una línea:

```
  ◐ code_search  [pattern="AgentLoop"]    →   ⎿ 47 resultados en 8 ficheros
  ◐ read_file    [path="agent/loop.py"]   →   ⎿ loop.py  [842 líneas]
  ◐ web_search   [query="ripgrep"]        →   ⎿ 5 resultados
```

Para expandir el output completo, usa **Ctrl+O** para alternar entre vista compacta y completa.

---

## Auto-continuación en tareas largas

Para migraciones, refactorizaciones o cualquier tarea que requiera muchos tool calls, el agente puede detenerse entre bloques de trabajo. OOCode retoma automáticamente:

```json
"context": {
  "autoContinueMax": 8
}
```

Con `autoContinueMax: 16` (valor por defecto), si el modelo completa un bloque y devuelve una respuesta vacía, OOCode lo relanza automáticamente hasta 16 veces antes de pedir intervención manual. El spinner muestra `↻ Auto-continúa (3/16)…` durante la reactivación. Pon `0` para desactivar.

Cuando hay un plan multi-tarea activo, el auto-continue usa mensajes específicos por tarea (`"Continúa con la tarea activa (N/M): texto. Anuncia 'Tarea N+1:' al avanzar."`) y el task progress panel muestra el estado ✔/◼/◻ en tiempo real.

### Checkpoint de tarea en auto-continúas

En cada auto-continúa, OOCode inyecta automáticamente un **📍 CHECKPOINT** con la lista de ficheros ya modificados en la tarea actual y el último resultado de tests:

```
📍 CHECKPOINT [auto-continúa 3]:
- Ficheros YA modificados en esta tarea:
  • agent/loop.py
  • tests/test_44_robustness.py
- Tests (último resultado): 43 passed in 0.12s
No reapliques cambios ya realizados. Continúa desde donde lo dejaste.
```

Esto evita que el modelo repita ediciones ya realizadas cuando el contexto es largo o tras una compactación.

## Plugins y Skills

Los plugins viven en `~/.oocode/plugins/` y pueden añadir herramientas, comandos y hooks de ciclo de vida.
Los skills son más simples: solo añaden herramientas, sin hooks.

```bash
# Plugins
/plugins list                # lista todos los disponibles
/plugins enable mi-plugin    # activa y guarda en oocode.json
/plugins disable mi-plugin   # desactiva
/plugins reload              # recarga todos los activos
/plugins create mi-plugin    # crea plantilla de plugin nuevo

# Skills
/skills list                 # lista todos los disponibles
/skills enable mi-skill      # activa y guarda en oocode.json
/skills disable mi-skill     # desactiva
/skills create mi-skill      # crea plantilla de skill nuevo
```

Los plugins del repositorio se sincronizan automáticamente a `~/.oocode/plugins/` al arrancar OOCode.
Los skills del repositorio se sincronizan automáticamente a `~/.oocode/skills/`.

## Subagentes

OOCode puede lanzar subagentes con workspaces aislados para delegar subtareas:

```
/spawn coding "analiza src/main.py y sugiere refactorizaciones"
/subagents                     # lista subagentes activos
/subagents steer <id> <instr>  # inyecta nueva instrucción
/subagents kill <id>           # detiene un subagente
/subagents output <id>         # muestra el resultado completo
```

El LLM también puede lanzar subagentes directamente como tool call (`spawn_subagent`).

## Documentación completa

Ver directorio `doc/` para documentación detallada de cada módulo y funcionalidad:

| Fichero | Contenido |
|---------|-----------|
| `01_installation.md` | Instalación y primeros pasos |
| `02_configuration.md` | Referencia completa de `oocode.json` |
| `03_commands.md` | Todos los comandos `/slash` |
| `04_tools.md` | Herramientas base del agente |
| `05_memory.md` | Sistema de memoria semántica |
| `06_context.md` | Gestión y compactación del contexto |
| `07_plugins.md` | Sistema de plugins con hooks |
| `08_skills.md` | Skills personalizados |
| `09_searxng.md` | Configuración de SearXNG |
| `10_logging.md` | Sistema de logs |
| `11_architecture.md` | Arquitectura interna |
| `12_subagents.md` | Sistema de subagentes |
| `13_git_plugin.md` | Plugin Git (tools vía MCP) |
| `14_diff_plugin.md` | Plugin Diff (builtin hook `diff_after_write`) |
| `15_system_assistant.md` | Servidor MCP bundled: 103 tools, 32 prompts, 18 resources |

## Licencia

MIT — libre para uso personal y comercial.
