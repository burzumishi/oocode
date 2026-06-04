# OOCode v0.4.3 — Asistente de programación local multi-backend

Asistente de programación para la terminal con soporte de múltiples backends LLM: **[Ollama](https://ollama.com)** (100% local), servidores **OpenAI-compatible** (llama.cpp, LM Studio, vLLM) y **Anthropic** (Claude cloud). Sin restricciones de uso, sin enviar código a terceros salvo que elijas un backend externo.

## ¿Por qué OOCode?

| | OOCode | Claude Code |
|---|---|---|
| **Coste** | Gratis con modelos locales (Ollama); pay-per-token con cloud | $20/mes (Max) o pay-per-token |
| **Privacidad** | 100% local con Ollama — tu código no sale del equipo | El código se envía a servidores Anthropic |
| **Rate limits** | Sin límites con modelos locales | Límites por nivel de suscripción |
| **Modelos** | Cualquier modelo Ollama, OpenAI-compat o Anthropic Claude | Sólo Claude |
| **Offline** | Funciona sin internet (modo Ollama) | Requiere conexión |
| **Backends** | Ollama · llama.cpp · LM Studio · vLLM · Anthropic | Solo API Anthropic |
| **Plugins** | Sistema extensible con hooks Python | No extensible |
| **Memoria semántica** | Persistente entre sesiones con embeddings locales | Requiere Pro/Max |

---

## Características principales

- **Multi-backend LLM** — Ollama (local), OpenAI-compatible (llama.cpp, LM Studio, vLLM, koboldcpp), Anthropic; configurable en `oocode.json` con `api.type`
- **TUI avanzada** — live block con preview de herramientas, auto-header para ediciones, spinner pulsante, display compacto de resultados, task progress panel con planes multi-tarea
- **WebUI Flask** *(beta)* — interfaz web con salida idéntica al TUI (●/│/◐/⎿/◈), planes, bloques colapsables, status bar bajo el prompt (paridad TUI), indicador "Pensando" de estado, subagentes en bloques de conversación, configuración visual completa, evento `inference_done`
- **Tool calling nativo** — el modelo llama a herramientas reales: bash, ficheros, web, git, docker…
- **157+ tools MCP** — 8 servidores MCP bundled: oocode-assistant (53), devops-assistant (66), database-assistant (20), system-assistant, home-office, security, IoT, **http-client (17)**
- **HTTP Client MCP** — 17 tools para desarrollo de APIs: http_request, response_diff, openapi_validate, curl_import, websocket_send, sse_listen, mock_server, graphql_query, jwt_decode, http_batch
- **5 agentes especializados** — main, coding, home_office, reasoning, webcrawler; cada uno con workspace propio y personalizable sin tocar código (sección `## Notas` de `TOOLS.md`/`AGENTS.md`)
- **Delegación consciente de agentes** — el LLM conoce el rol de cada agente disponible y delega la tarea en el más afín (p.ej. búsqueda web → `webcrawler`), ahorrando contexto y herramientas
- **Multi-servidor Ollama** — distribuye subagentes y embeddings entre varios servidores en round-robin
- **LSP integration** — 30+ lenguajes con auto-arranque de servidores por extensión de fichero
- **RAG workspace** — indexa el proyecto con embeddings y auto-inyecta código relevante en cada turno
- **18 hooks built-in** — lint, lsp, backup, test, diff, verify, git_push_guard, security_audit_log y más
- **Memoria por agente** — dos sistemas: memoria del workspace (`~/.oocode/workspace/<agente>/MEMORY.md` + `memory/` diario) y memoria semántica con embeddings (`~/.oocode/memory/<agente>/`, tool `mem_save`)
- **Compactación inteligente de contexto** — 9 mejoras: estimación calibrada (CPT dinámico), resumen separado, serialización por turnos, min_keep adaptativo al plan, pre-compactación en idle, meta-header `[Compactación #N]`
- **Auto-continuación** — relanza el agente automáticamente en tareas largas (configurable hasta 16 veces)
- **Subagentes con paralelismo real** — cada subagente puede ejecutar en una GPU distinta (round-robin de hosts)
- **Extensiones VIM y VSCode** — panel lateral con streaming SSE, comandos y mappings de teclado
- **Catálogo MCP externo** — gestión de servidores MCP de terceros con `/mcp catalog/install/check`

---

## Requisitos

- Python 3.10+
- Un backend LLM (al menos uno):
  - **[Ollama](https://ollama.com)** — instalado y ejecutándose (recomendado para uso local)
  - **Servidor OpenAI-compatible** — llama.cpp, LM Studio, vLLM, koboldcpp, OpenAI cloud
  - **Anthropic** — API key en `oocode.json`

```bash
# Modelos recomendados (Ollama)
ollama pull qwen3.5:9b              # 16 GB VRAM — mejor equilibrio
ollama pull qwen2.5-coder:7b        # 8 GB VRAM
ollama pull nomic-embed-text-v2-moe # modelo de embeddings (memoria semántica)
```

---

## Instalación rápida

```bash
git clone https://github.com/burzumishi/oocode
cd oocode
./install.sh
```

O manualmente:

```bash
pip install -r requirements.txt
pip install -e .
```

El instalador:
1. Ejecuta `pip install -e .` — registra el comando `oocode` en `~/.local/bin/`
2. Crea `~/.oocode/oocode.json` con la configuración por defecto
3. Sincroniza plugins y skills a `~/.oocode/`
4. Comprueba herramientas opcionales (git, docker, ruff, etc.)

Como es una instalación editable, `git pull` actualiza OOCode inmediatamente sin reinstalar.

### Dependencias opcionales (Office)

Para el servidor MCP home-office-assistant:

```bash
pip install python-docx python-pptx openpyxl pillow docxtpl
# Verificar:
python -c "import docx, openpyxl, pptx, docxtpl; print('OK')"
```

---

## CLI — Argumentos

```bash
python oocode.py [proyecto_dir]              # lanzar agente en directorio
python oocode.py --agent coding              # agente específico
python oocode.py --model qwen2.5:14b         # override de modelo
python oocode.py --host http://...           # override de host Ollama
python oocode.py --new                       # nueva sesión limpia
python oocode.py --doctor                    # diagnóstico del sistema
python oocode.py --webserver start           # WebUI en puerto 4000
python oocode.py --webserver stop|restart|status
```

---

## Backends LLM *(nuevo en v0.4.0)*

OOCode soporta tres tipos de backend configurables en `oocode.json`:

> ⚠️ **Ollama es el backend estable.** OpenAI-compatible y Anthropic son **experimentales** (funcionan, pero el streaming, el conteo de tokens y la compactación están afinados para Ollama).

```json
{
  "api": {
    "type":            "ollama",
    "key":             "",
    "host":            "http://localhost:11434",
    "extraHosts":      [],
    "embedHost":       "",
    "subagentRouting": "round-robin"
  }
}
```

Un único bloque `api` define el backend **y** los parámetros del servidor. El campo `host` es universal: con Ollama es el host del servidor; con OpenAI es el `baseUrl`.

### Ollama (local, por defecto)

```json
{ "api": { "type": "ollama", "host": "http://localhost:11434" } }
```

### OpenAI-compatible (llama.cpp, LM Studio, vLLM, OpenAI cloud…)

```json
{
  "api": { "type": "openai", "host": "http://localhost:8080/v1" },
  "agents": { "defaults": { "model": "llama-3.3-70b" } }
}
```

Para OpenAI cloud:
```json
{ "api": { "type": "openai", "key": "sk-...", "host": "https://api.openai.com/v1" } }
```

### Anthropic (Claude cloud)

```json
{
  "api": { "type": "anthropic", "key": "sk-ant-..." },
  "agents": { "defaults": { "model": "claude-opus-4-8" } }
}
```

También editable con `/config edit` desde el REPL. Ver `doc/25_api_backends.md` para referencia completa.

---

## Multi-servidor Ollama

OOCode puede distribuir subagentes y embeddings entre varios servidores Ollama. Útil cuando tienes varias GPUs, varias máquinas en red local, o quieres dedicar un servidor CPU-only a los embeddings.

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

| Campo | Descripción |
|-------|-------------|
| `host` | Servidor principal — agente interactivo y fallback |
| `extraHosts` | Servidores adicionales — los subagentes rotan entre todos |
| `embedHost` | Servidor dedicado para embeddings (vacío = usa `host`) |
| `subagentRouting` | `"round-robin"` (por defecto) o `"primary-only"` |

Con un solo servidor (configuración por defecto) el comportamiento es exactamente el mismo que antes. Ver `doc/12_subagents.md` para detalles.

---

## Configuración básica (`~/.oocode/oocode.json`)

Se genera automáticamente al arrancar por primera vez. Edita con `/config edit` desde el REPL o directamente.

```json
{
  "api": {
    "type":            "ollama",
    "key":             "",
    "host":            "http://localhost:11434",
    "extraHosts":      [],
    "embedHost":       "",
    "subagentRouting": "round-robin"
  },

  "agents": {
    "list": [
      { "id": "main",       "name": "OOCode",        "emoji": "🤖", "model": "qwen3.5:9b" },
      { "id": "coding",     "name": "OOCode Coder",  "emoji": "💻", "model": null },
      { "id": "home_office","name": "OOCode Office", "emoji": "📋", "model": null },
      { "id": "reasoning",  "name": "OOCode Reason", "emoji": "🧠", "model": null },
      { "id": "webcrawler", "name": "WebCrawler",    "emoji": "🕷️", "model": null }
    ]
  },

  "mcp": {
    "oocodeAssistant":    { "enabled": true  },
    "systemAssistant":    { "enabled": true  },
    "homeOfficeAssistant":{ "enabled": false },
    "securityAssistant":  { "enabled": false },
    "iotAssistant":       { "enabled": false }
  },

  "context": {
    "autoContinueMax": 8,
    "compactThreshold": 0.80
  },

  "subagents": {
    "maxConcurrent":    4,
    "autoContMax":      16,
    "inferenceTimeout": 0,
    "defaultTimeout":   0
  }
}
```

| Campo `subagents` | Default | Descripción |
|-------------------|---------|-------------|
| `maxConcurrent` | 4 | Subagentes corriendo en paralelo simultáneamente |
| `autoContMax` | 16 | Auto-continues máximos para subagentes (evita paradas prematuras en tareas largas) |
| `inferenceTimeout` | 0 | Timeout de inferencia Ollama para subagentes en segundos (0 = hereda `fallback.timeoutSeconds`) |
| `defaultTimeout` | 0 | Timeout **por paso/petición al LLM** (inactividad), no por tiempo total: mata el subagente solo si un paso pasa N s sin progreso. Un subagente que avanza no se detiene aunque la tarea total dure más (0 = sin watchdog) |

---

## Los 5 agentes

| Agente | Emoji | Especialidad | Workspace |
|--------|-------|-------------|-----------|
| `main` | 🤖 | Asistente general, coordina otros agentes | `~/.oocode/workspace/main` |
| `coding` | 💻 | IT, programación, refactorización, LSP | `~/.oocode/workspace/coding` |
| `home_office` | 📋 | Documentación corporativa O365 (Word/Excel/PPT) | `~/.oocode/workspace/home_office` |
| `reasoning` | 🧠 | Razonamiento, coordinación de equipos de agentes | `~/.oocode/workspace/reasoning` |
| `webcrawler` | 🕷️ | Búsqueda web con SearXNG, generación de informes | `~/.oocode/workspace/webcrawler` |

Selección con `--agent <id>` en CLI o `/switch <id>` en el REPL. Sin `--agent` arranca el agente `main`.

**Ficheros del workspace** (`~/.oocode/workspace/<agente>/`): `IDENTITY.md` (quién eres — Rol/Vibe), `SOUL.md` (cómo actúas), `USER.md` (sobre tu usuario), `AGENTS.md` (delegación), `TOOLS.md` (entorno/herramientas), `HEARTBEAT.md` (tareas periódicas) y `MEMORY.md` + `memory/` (continuidad). Al arrancar, el contexto por defecto es **`mini`** (resumen ligero de identidad + memoria); `/ctx full` carga los ficheros completos.

**Personalizar un agente sin tocar código:** escribe en la sección `## Notas` de su `TOOLS.md` (preferencias de herramientas) o `AGENTS.md` (cuándo y en quién delegar). Lo que escribas se carga en su contexto automáticamente; las plantillas vacías no cuestan tokens.

---

## WebUI *(beta)*

```bash
# Arrancar WebUI daemon
python oocode.py --webserver start

# Acceder
http://localhost:4000
```

El WebUI ha alcanzado el estado **beta** (v0.4.0): cubierto por la suite de tests, paridad de características completa con el TUI e interfaz estable para uso diario desde navegador o extensiones de editor.

**Características:**
- Chat con streaming SSE en tiempo real; salida idéntica al TUI (●/│/◐/⎿/◈/✔/◼/◻), fuente monoespaciada
- Indicador "Pensando" con palabras ciclantes (`Cavilando…`, `Tokenizando…`) y frases de preflight encima del prompt — es estado puro: el detalle de cada herramienta aparece en su bloque dentro de la conversación, no en el prompt
- Status bar bajo el prompt (paridad TUI): agente · modelo · contexto · indicadores MCP/LSP/MEM/RAG/etc., con las filas de detalle MCP/LSP debajo
- Evento `inference_done`: al terminar cada turno el chat muestra "⚡ Inferencia completada."
- Planes multi-tarea con estado `✔/◼/◻` actualizables en tiempo real
- Archivos adjuntos con previsualización de imágenes en el chat
- Tarjetas de archivo siempre visibles con botón de descarga
- Bloques de tools colapsables (expandir con `▶`)
- Barra de contexto con alerta al acercarse al límite
- Temas claro/oscuro, diseño responsive para móvil
- Configuración visual completa de `oocode.json` en 17 secciones (~50 parámetros)
- Subagentes: cada uno en un bloque expandible en la conversación (con su tarea, plan, texto y herramientas); la status bar muestra una cabecera de equipo de una sola línea

**API endpoints principales:**

| Endpoint | Descripción |
|----------|-------------|
| `POST /api/chat/send` | Enviar mensaje (inicia streaming SSE) |
| `POST /api/chat/send_sync` | Enviar mensaje y esperar respuesta completa |
| `GET /api/chat/stream` | SSE: recibe chunks del turno activo |
| `GET /api/chat/history` | Historial de mensajes de la sesión |
| `GET /api/chat/status` | Estado: modelo, agente, contexto % |
| `GET /api/agents` | Subagentes activos |
| `GET /api/config` | Configuración actual |
| `POST /api/config/save` | Guardar cambios en `oocode.json` |

Ver `doc/19_webui.md` para la referencia completa de la API y arquitectura interna.

---

## TUI — Display en tiempo real

OOCode muestra lo que está haciendo mientras trabaja, con un live block que aparece mientras el agente ejecuta herramientas y desaparece limpiamente al terminar:

```
  ● Voy a revisar el código y corregir los errores de compilación.

  ● Updating act_comm.c:
  |  ◐ Bash:
  |     $ grep -rn "gethostname" src/
  ⎿ Used 2 tools (ctrl+o to expand)

  ● Updating comm.c, imc.c:
  |  ◐ Update:
  |     comm.c
  ⎿ Updated 2 files (ctrl+o to expand)
```

**Elementos del live block:**

| Elemento | Descripción |
|----------|-------------|
| `●` pulsante | Texto del agente (verde/cyan); cambia a verbo en gerundio mientras corre una tool |
| `\|  ◐ Tool:` | Nombre corto de la herramienta en ejecución |
| `\|     context` | 1-4 líneas de contexto (args): comando bash, ruta del fichero, patrón de búsqueda… |
| `⎿ Used N tools` | Contador de tools completadas; `ctrl+o` para expandir el historial |

**Auto-header para ediciones**: cuando el agente emite un texto de planificación largo (>60 chars) y a continuación llama a write tools, OOCode imprime el planning text como `●` estático y genera automáticamente un header `● Updating file.c:` específico para el bloque de edición. Esto evita que las ediciones queden "enterradas" bajo un texto de plan general.

**Preview oculto al terminar**: las líneas de contexto bajo `◐ tool:` desaparecen al completarse cada herramienta — no se acumulan en la conversación.

---

## MCP Servers (8 bundled)

| Servidor | Flag en oocode.json | Tools | Por defecto |
|----------|---------------------|-------|-------------|
| `oocode-assistant` | `oocodeAssistant.enabled` | 53 tools: code analysis, write/edit, rendering, linting, utilidades | activo |
| `devops-assistant` | `devopsAssistant.enabled` | 66 tools: git (16), docker/compose (23), build/debug (11), archive (3), fs-mutations (13) | activo |
| `system-assistant` | `systemAssistant.enabled` | systemctl, journalctl, red, disco, paquetes, procesos | activo |
| `database-assistant` | `databaseAssistant.enabled` | 20 tools: SQLite CRUD, pg/mysql opcionales, csv_to_sqlite, db_stats, sql_format | desactivado |
| `home-office-assistant` | `homeOfficeAssistant.enabled` | 66 tools O365 nativo: doc_create, insert_chart (OOXML), xlsx_create_report, pptx_create, email_send, cal_add | desactivado |
| `security-assistant` | `securityAssistant.enabled` | 24 tools: nmap_scan, web_scan, ssl_check, hash_crack, xss_test, ctf_decode | desactivado |
| `iot-assistant` | `iotAssistant.enabled` | 25 tools: TAPO, Blink, Alexa, Tuya, Home Assistant, MQTT, ESPHome | desactivado |
| `http-client-assistant` | `httpClientAssistant.enabled` | 17 tools: http_request/get, response_diff, openapi_validate, curl_import, websocket_send, sse_listen, mock_server, graphql_query, jwt_decode, http_batch, http_history | desactivado |

Para activar un servidor MCP:
```json
{ "mcp": { "databaseAssistant": { "enabled": true } } }
```

El comando `/mcp` muestra el estado de los 8 servidores (incluidos los desactivados) con `/mcp enable <nombre>` / `/mcp disable <nombre>`.

---

## Slash commands (resumen)

| Comando | Descripción |
|---------|-------------|
| `/new` | Nueva sesión limpia |
| `/switch <agent>` | Cambiar de agente en caliente |
| `/doctor` | Diagnóstico: Ollama, modelos, LSP, hooks, MCP |
| `/compact` | Compactar contexto con resumen LLM |
| `/hooks` | Ver y activar/desactivar hooks built-in |
| `/hooks list` | Lista completa de hooks disponibles |
| `/agents` | Lista agentes configurados |
| `/subagents` | Ver, steer y kill subagentes activos |
| `/model [nombre]` | Ver o cambiar modelo |
| `/models` | Seleccionar modelo de Ollama |
| `/rag` | Estado del índice RAG del workspace |
| `/rag reindex` | Re-indexar embeddings |
| `/mcp` | Estado de servidores MCP conectados |
| `/lsp` | Gestión de servidores LSP |
| `/context` | Estado del contexto (tokens, %) |
| `/ctx [mini|full]` | Modo de contexto inyectado |
| `/checkpoint` | Guardar checkpoint manual |
| `/steer` | Inyectar instrucciones al agente en curso |
| `/diff [fichero]` | Historial de diffs de la sesión |
| `/symbols [arg]` | Índice de símbolos del proyecto |
| `/lint [ruta]` | Linting manual |
| `/todo [subcmd]` | Gestión de TODOs/FIXMEs |
| `/clip <texto>` | Copiar texto al portapapeles |
| `/webserver start|stop|status` | Control del WebUI daemon |
| `/session [id]` | Sesión activa o restaurar sesión |
| `/sessions` | Historial de sesiones |
| `/clear` | Limpiar historial de conversación |
| `/copy [n]` | Copiar última respuesta al portapapeles |
| `/init [ruta]` | Generar `OOCODE.md` para el proyecto |
| `/help` | Ayuda completa |

---

## Extensiones

### VIM / Neovim *(v3.1 — streaming real)*

Requiere la WebUI activa (`oocode --webserver start`). Instalación con vim-plug:
```vim
Plug 'burzumishi/oocode', { 'rtp': 'extensions/vim' }
```

El panel lateral muestra en vivo (paridad con TUI/WebUI) el texto del agente, las herramientas, el plan y los subagentes (líneas con `│`) mientras trabajan — vía SSE (`g:oocode_stream = 1`, por defecto). Con `g:oocode_stream = 0` o sin `+job` cae a `send_sync` bloqueante.

Comandos principales: `:OOCode <msg>`, `:OOCodeAsk`, `:OOCodeContext`, `:OOCodeSelection`, `:OOCodeExplain`, `:OOCodeReview`, `:OOCodeTUI`, `:OOCodeOpen/Close/Toggle`, `:OOCodeStatus`, `:OOCodeConnect`, `:OOCodeKill`, `:OOCodeElevated [modo]`, `:OOCodeWebUI`, `:OOCodeWebServer`, `:OOCodeNew`, `:OOCodeSwitch <agent>`, `:OOCodeAgents`, `:OOCodeSessions`, `:OOCodeDoctor`, `:OOCodeCmd <slash_cmd>`

Mappings: `<Leader>oa` (ask), `<Leader>oc` (context), `<Leader>os` (selection), `<Leader>ox` (explain), `<Leader>or` (review), `<Leader>ot` (toggle panel), `<Leader>ow` (WebUI), `<Leader>ou` (TUI), `<Leader>on` (new session), `<Leader>ok` (connect), `<Leader>oK` (kill), `<Leader>oe` (elevated)

### VSCode

Extensión en `extensions/vscode/`. Instalación manual:
```bash
cd extensions/vscode && code --install-extension oocode-*.vsix
```

---

## Hooks (14 built-in)

| Hook | Cuándo | Descripción |
|------|--------|-------------|
| `lint_after_write` | post write/edit | ruff/mypy/eslint/shellcheck automático |
| `lsp_after_write` | post write/edit | Diagnósticos LSP al guardar |
| `quick_syntax` | post write .py | ast.parse instantáneo |
| `config_syntax_after_write` | post .json/.toml/.ini | Valida sintaxis de configs |
| `backup_before_write` | pre write | Crea copia `.bak` antes de sobreescribir |
| `test_after_write` | post .py | Ejecuta pytest asociado |
| `verify_after_edit` | post edit_file | Re-lee sección modificada con marcadores |
| `interface_change_detector` | pre+post .py | Detecta cambios de firma/API pública |
| `test_suite_delta` | pre+post | Detecta regresiones entre ediciones |
| `todo_scan` | post write | Muestra TODO/FIXME encontrados |
| `size_check` | post write | Avisa si el fichero supera 300 líneas |
| `log_tool_calls` | post todas | Registra en `~/.oocode/logs/tool_calls.jsonl` |
| `git_push_guard` | pre commit/push | Avisa si el mensaje es vacío o la rama protegida |
| `security_audit_log` | post Security MCP | Registra en `~/.oocode/logs/security_audit.log` |

```bash
/hooks                                   # ver hooks activos
/hooks builtin lint_after_write          # activar/desactivar
```

---

## LSP (30+ lenguajes)

Python (pylsp), JavaScript/TypeScript (typescript-language-server), C/C++ (clangd), Rust (rust-analyzer), Go (gopls), Java (jdtls), PHP (intelephense), Ruby (solargraph), C# (omnisharp), Lua (lua-language-server), YAML, JSON, TOML, Markdown, XML y más.

Los servidores LSP se arrancan automáticamente al abrir un fichero del lenguaje correspondiente.

---

## OOCODE.md — instrucciones por proyecto

Crea `OOCODE.md` en la raíz de tu proyecto (equivalente al `CLAUDE.md` de Claude Code). OOCode lo detecta e inyecta automáticamente como contexto del sistema:

```bash
cd /mi/proyecto && oocode          # detecta OOCODE.md automáticamente
oocode /mi/proyecto                # equivalente explícito
```

Genera una plantilla con `/init`. También puedes definir hooks personalizados:

```markdown
## Hooks
post write_file: ruff check {path} --fix
post edit_file:  mypy {path}
```

---

## Estructura del proyecto

```
oocode/
├── oocode.py              # Entry point — CLI, wiring, REPL
├── config.py              # OOConfig (Pydantic): carga/guarda oocode.json
├── requirements.txt       # Dependencias Python
├── install.sh             # Instalador
│
├── api/                   # Backends LLM intercambiables (nuevo en v0.4.0)
│   ├── base.py            # BackendClient ABC, Chunk, Response, ToolCall
│   ├── ollama.py          # OllamaBackend — usa ollama.Client
│   ├── openai.py          # OpenAIBackend — httpx, compatible con llama.cpp/vLLM/…
│   └── anthropic.py       # AnthropicBackend — SDK anthropic
│
├── agent/                 # Núcleo del agente
│   ├── loop.py            # AgentLoop: streaming, tool dispatch, TUI
│   ├── runtime.py         # Estado de sesión, permisos, elevated mode
│   ├── context.py         # Ventana de contexto, compactación
│   ├── memory.py          # Memoria persistente con embeddings
│   ├── subagent.py        # Lanzamiento y comunicación con subagentes
│   └── mcp_client.py      # Cliente MCP stdio (JSON-RPC 2.0)
│
├── tools/                 # Herramientas nativas
│   ├── registry.py        # Registro de todas las herramientas
│   ├── hooks.py           # 18 hooks built-in
│   └── ...
│
├── mcp_servers/           # Servidores MCP bundled (8)
│   ├── oocode_assistant.py    # 53 tools: code analysis, edit, utilities
│   ├── devops_assistant.py    # 66 tools: git, docker/compose, build, debug, fs
│   ├── database_assistant.py  # 20 tools: SQLite, PostgreSQL/MySQL opcionales
│   ├── system_assistant.py    # sistema, servicios, paquetes, red
│   ├── http_client_assistant.py  # 17 tools: HTTP/APIs, WebSocket, mock server
│   ├── home_office_assistant.py
│   ├── security_assistant.py
│   └── iot_assistant.py
│
├── webui/                 # WebUI Flask con SSE
│   └── app.py
│
├── extensions/            # Extensiones para editores
│   ├── vim/               # Plugin VIM (vim-plug compatible)
│   └── vscode/            # Extensión VSCode
│
├── ui/                    # TUI con prompt_toolkit + Rich
│   ├── repl.py
│   ├── renderer.py
│   └── commands.py        # Handlers de /slash commands
│
├── workspace/             # Gestión de workspaces por agente
│   └── manager.py
│
└── doc/                   # Documentación detallada
```

---

## Documentación completa

| Fichero | Contenido |
|---------|-----------|
| `doc/01_installation.md` | Instalación completa, dependencias, LSP servers |
| `doc/02_configuration.md` | Referencia completa de `oocode.json`, multi-servidor Ollama |
| `doc/03_commands.md` | Todos los slash commands |
| `doc/04_tools.md` | Herramientas nativas del agente |
| `doc/05_memory.md` | Memoria semántica persistente y embeddings |
| `doc/06_context.md` | Ventana de contexto, compactación, RAG |
| `doc/07_plugins.md` | Sistema de plugins |
| `doc/08_skills.md` | Skills personalizados |
| `doc/09_searxng.md` | Plugin SearXNG |
| `doc/10_logging.md` | Sistema de logs |
| `doc/11_architecture.md` | Arquitectura interna, patrones de diseño |
| `doc/12_subagents.md` | Subagentes: round-robin multi-GPU, aislamiento |
| `doc/13_git_plugin.md` | Herramientas Git MCP |
| `doc/14_diff_plugin.md` | Diffs visuales y herramientas de código |
| `doc/15_system_assistant.md` | System Assistant MCP |
| `doc/16_workspaces_agents.md` | Workspaces por agente, `/switch` |
| `doc/17_workflows_multifase.md` | Workflows de análisis multi-fase |
| `doc/18_agent_teams.md` | Equipos de agentes, AgentTeam, paralelismo multi-GPU |
| `doc/19_webui.md` | WebUI Flask *(beta)*: setup, API REST, SSE, eventos, subagentes |
| `doc/20_office_styles.md` | Estilos O365 en documentos Word/Excel/PPT |
| `doc/21_extensions.md` | Extensiones VIM y VSCode |
| `doc/22_mcp_servers.md` | 5 MCP servers bundled + catálogo de servidores externos |
| `doc/23_hooks.md` | Los 18 hooks built-in: configuración y custom hooks |
| `doc/24_tui_display.md` | TUI live block: preview de herramientas, auto-split bullet, static ANSI cache |
| `doc/25_api_backends.md` | Multi-backend LLM: Ollama, OpenAI-compatible, Anthropic; configuración y ejemplos |

---

## Changelog

**v0.4.3** (2026-06-04) — Robustez de subagentes, contexto y personalización de agentes. **Contenido web/PDF ya no se confunde con el usuario:** al descargar un documento (web_fetch/PDF), el resultado se etiqueta como salida de herramienta para que el modelo no responda como si la conversación empezara de cero; un hint reactivo lo reorienta si recae. **Compactación a mitad de turno:** el "último mensaje del agente" que se re-muestra tras compactar ahora es el más reciente real (antes, con auto-continue, repetía un mensaje obsoleto de la 1.ª compactación). **Delegación consciente de agentes:** el LLM ve el rol de cada agente disponible (leído de su `IDENTITY.md`) en los schemas de orquestación y en el system prompt, así delega en el más afín (p.ej. web → `webcrawler`) en vez de hacerlo todo él. **Capa de personalización por-agente:** cada agente carga la sección `## Notas` de su `TOOLS.md`/`AGENTS.md` (usos de herramientas y delegación) — personalizable sin tocar código ni `SYSTEM_RULES`, y coste cero hasta que escribes en ella. **bash de subagentes en el proyecto correcto:** los subagentes ejecutan las tools en el `project_dir` del padre, no en su carpeta de identidad (`~/.oocode/workspace/<id>` con `~` sin expandir hacía fallar `bash`). **Alineación del TUI:** el `●` de texto de los subagentes ya se alinea bajo su columna `│`. *(También en 0.4.3:)* timeout de subagentes por inactividad/paso (no tiempo total); el TUI no pierde el último mensaje al compactar; VIM/Neovim 3.1 con streaming real; render de orquestación; `/kill` instantáneo que mata turno, subagentes y equipos. 4509 tests.

**v0.4.2** (2026-06-03) — Flujo de conversación multidominio y paridad TUI/WebUI. OOCode es multi-agente: además del agente `main` de código, puedes crear agentes de cualquier dominio (oficina, seguridad, investigación web, IoT, datos) con `/agent new`, que ahora personaliza la persona según el dominio. El flujo de conversación (preflight, planificación, anuncios de acción, narración de equipos) ya no asume programación. Las tools de orquestación se ejecutan en modo secuencial para no romper el render de subagentes. WebUI: config consciente del backend, hooks de subagente visibles en su bloque, tarjetas de descarga solo para entregables, status bar única (paridad con el TUI) y team-bar con tarea/tiempo/estado/contexto por subagente. Anti-bucle unificado en ediciones: cuando el agente falla al modificar un fichero repetidamente, OOCode le inyecta el contenido real y para en seco si el cambio ya está aplicado. TUI: el streaming `│` de un subagente multi-turno ya no se congela tras las primeras líneas — el presupuesto de líneas se refresca por turno, así sigues viendo su actividad reciente mientras las antiguas hacen scroll. 4457 tests.

**v0.4.1** (2026-06-03) — Consistencia multi-backend: `/doctor`, `/config`, `/settings`, `/model` y `/switch` ahora funcionan correctamente con los backends OpenAI-compatible y Anthropic (antes asumían Ollama). Las embeddings usan siempre el host Ollama correcto sea cual sea el backend de chat. Correcciones: `doc_create` (Home Office), mensaje de timeout de subagentes, fuga de hilos watchdog. El instalador escribe el bloque `api` unificado. 4358 tests.

Ver [CHANGELOG.md](CHANGELOG.md) para el historial completo de versiones.

---

## Licencia

MIT — libre para uso personal y comercial.
