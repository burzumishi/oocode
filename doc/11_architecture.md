# 11 — Arquitectura interna

## Visión general

OOCode es un agente LLM local que combina un TUI interactivo (prompt_toolkit + Rich), un bucle de inferencia con Ollama y un ecosistema de herramientas via MCP.

```
oocode.py  →  agent/runtime.py  →  agent/loop.py  →  Ollama API
                                        │
                              tool dispatch (MCP + nativos)
                                        │
                    tools/           mcp_servers/        agent/lsp_client.py
                    registry.py      (stdio JSON-RPC)    (Language Servers)
                                        │
                    WebUI (Flask + SSE)     extensiones (VIM / VSCode)
```

## Estructura de módulos

```
oocode/
├── oocode.py              # Entry point: CLI args, wiring de componentes, REPL
├── config.py              # OOConfig (Pydantic): carga/guarda oocode.json
│
├── agent/
│   ├── loop.py            # AgentLoop: turno completo con Ollama + tool dispatch
│   ├── context.py         # ConversationContext: historial + compactación
│   ├── memory.py          # MemorySystem: ficheros .md + embeddings + búsqueda semántica
│   ├── embeddings.py      # EmbeddingClient: wrapper de Ollama embeddings API
│   ├── session.py         # SessionManager: persistencia JSONL de sesiones
│   ├── runtime.py         # RuntimeSettings: estado en memoria (think, color, dirs…)
│   ├── branches.py        # BranchManager: snapshots de conversación
│   ├── tasks.py           # TaskManager: lista todo/wip/done persistente + AgentTeam
│   ├── scheduler.py       # Scheduler: jobs periódicos
│   ├── subagent.py        # SubAgentRunner: lanza AgentLoop aislado para spawning
│   ├── mcp_client.py      # MCPClient: cliente stdio JSON-RPC 2.0 para servidores MCP
│   ├── lsp_client.py      # LSP client: Language Server Protocol sobre stdio/socket
│   └── logger.py          # Logger: RotatingFileHandler + funciones info/debug/error
│
├── tools/
│   ├── registry.py        # ToolRegistry: nombre→función, genera schemas Ollama
│   ├── permissions.py     # PermissionManager: modos auto/ask/deny por herramienta
│   ├── filesystem.py      # read_file, write_file, edit_file, edit_files, list_dir
│   ├── bash.py            # bash_execute + factory build_bash_schema
│   ├── search.py          # web_search (DuckDuckGo/SearXNG), web_fetch
│   ├── code_search.py     # code_search via ripgrep — streaming con Popen
│   ├── hooks.py           # HookManager: 18 hooks built-in
│   ├── progress.py        # Thread-local progress callbacks
│   └── diff_renderer.py   # Visual diff rendering con colores Rich
│
├── ui/
│   ├── repl.py            # REPL: prompt_toolkit input, routing /slash vs agente
│   ├── renderer.py        # Rich: markdown, tablas, spinners, status, config
│   ├── commands.py        # Registro + handlers de /slash commands
│   └── console.py         # Shared Rich Console (todos los módulos usan éste)
│
├── mcp_servers/           # Servidores MCP bundled (proceso stdio independiente)
│   ├── oocode_assistant.py    # ~35 tools: git, docker, fs, grep, symbols, utils
│   ├── system_assistant.py    # systemctl, journalctl, red, disco, procesos
│   ├── word_assistant.py     # 29 tools: Word/PDF + doc_create + núcleo O365
│   ├── excel_assistant.py    # 16 tools: hojas .xlsx + CSV
│   ├── pptx_assistant.py     # 7 tools: presentaciones .pptx
│   ├── mail_assistant.py      # 11 tools: email/calendario/notas/contactos
│   ├── cmdb_assistant.py      # 3 tools: inventario IT (CMDB/asset register)
│   ├── security_assistant.py  # 24 tools: nmap, web, crypto, CTF
│   └── iot_assistant.py       # 25 tools: TAPO, Alexa, HA, MQTT, ESPHome
│
├── webui/
│   └── app.py             # Flask + SSE: WebUI completa con chat, config, agentes
│
├── extensions/
│   ├── vim/               # Plugin VIM v3.0.0: comandos, mappings, SSE streaming
│   └── vscode/            # Extensión VSCode
│
├── plugins/
│   └── manager.py         # PluginManager: carga dinámica, hooks, herramientas
│
├── skills/
│   └── manager.py         # SkillManager: carga dinámica de herramientas Python
│
└── workspace/
    └── manager.py         # WorkspaceManager: OOCODE.md, MEMORY.md, log diario
```

## Flujo de arranque

```
python oocode.py [args]
  │
  ├── OOConfig.load(agent_id)           # carga oocode.json
  ├── log.init(...)                      # inicializa logger rotativo
  ├── print_banner(config)
  ├── WorkspaceManager.init()           # crea OOCODE.md y workspace files si no existen
  ├── select_model_interactive()        # si no hay modelo configurado
  │
  ├── PermissionManager(permissions)
  ├── EmbeddingClient(host, embed_model)  # una sola instancia — compartida
  ├── MemorySystem(embed_client, ...)
  ├── build_registry(workspace, config) # registra todas las herramientas nativas
  ├── MCPClient(config) → spawn MCP servers (stdio JSON-RPC)
  ├── SubAgentRunner(config, ..., embed_client)  # recibe el mismo embed_client
  │     └── registry.register("spawn_subagent", ...)
  │
  ├── SessionManager.start()
  ├── AgentLoop(config, registry, ...)
  ├── BranchManager / TaskManager / Scheduler
  │
  ├── SkillManager(enabled_override=config.skills_enabled)
  ├── PluginManager(enabled_override=config.plugins_enabled)
  │
  ├── (si --webserver) → run_webserver_standalone()
  └── run_repl(agent, config)           # bucle REPL
```

## Flujo de un turno de conversación

```
run_repl()
  │
  ├── prompt_toolkit Input
  ├── si empieza con "/" → handle_slash(cmd, agent, config)
  │
  └── si es texto → AgentLoop.run(mensaje)
        │
        ├── context.add("user", mensaje)
        ├── session.log_message("user", ...)
        ├── inject RAG snippets si rag.enabled
        │
        └── while True:
              │
              ├── context.should_compact() → _do_compact()
              ├── messages = context.get_messages(system=_system_prompt())
              ├── _stream_response(messages, tools)  → Ollama.chat()
              │
              ├── si text → Markdown render + session.log_message("assistant")
              │
              └── para cada tool_call:
                    ├── _show_tool_call(name, args)   # spinner ◐
                    ├── permissions.check(name)
                    │     ├── auto → ejecuta
                    │     ├── ask  → pide confirmación al usuario
                    │     └── deny → "Operación denegada"
                    ├── registry.call(name, args)
                    │     ├── busca en tools nativos
                    │     └── si no encuentra → MCPClient.call(name, args)
                    ├── hooks.post_tool(name, args, result)
                    ├── _truncate_tool_result(result)
                    └── context.add_tool_result(...)
              │
              ├── auto-continue si respuesta vacía y autoContinueMax > 0
              └── si no hay tool_calls → break
```

## Componentes clave

### `AgentLoop` (agent/loop.py)

El corazón de OOCode. Implementa:
- Streaming de respuestas del LLM
- Dispatch de tool calls (nativas + MCP)
- TUI: live block con preview de herramientas, auto-split bullet, spinner ◐ pulsante, display compacto (`⎿`), plan tracker (`◈`)
- Auto-continuación en tareas largas
- Compactación de contexto
- Checkpoint de tarea en auto-continúas

El indicador visual durante tools (modo TUI):
```
  ● Texto del agente (pulsante en verde/cyan)
  |  ◐ Bash:
  |     $ grep -rn "gethostname" src/    ← preview de args, desaparece al terminar
  ⎿ Used 2 tools (ctrl+o to expand)
```

El auto-split separa planning text largo de las ediciones concretas:
```
  ● Voy a refactorizar el módulo completo corrigiendo todos los warnings...

  ● Updating handlers.c:         ← auto-generado cuando el texto no menciona el fichero
  |  ◐ Update:
  |     handlers.c
  ⎿ Updated handlers.c (ctrl+o to expand)
```

Ver `doc/24_tui_display.md` para la documentación completa del live block.

### `MCPClient` (agent/mcp_client.py)

Gestiona los servidores MCP bundled y externos:
- Protocolo MCP 2024-11-05 sobre stdio (JSON-RPC 2.0)
- Arranque de procesos independientes (`subprocess.Popen`)
- Reconexión automática
- Paginación de tools/resources
- Reenvío transparente al `ToolRegistry`

### `ToolRegistry` (tools/registry.py)

Diccionario `nombre → (función, schema)`:
- `ollama_schemas()` devuelve schemas en formato Ollama para `chat()`
- `call(nombre, args)` invoca la función con `**args` y captura excepciones
- Filtrado adaptativo: reduce ~4-6K tokens enviando solo schemas relevantes para el tipo de tarea

### `ConversationContext` (agent/context.py)

Lista de mensajes + resumen acumulado:
- `should_compact()` compara tokens estimados con el umbral `compactThreshold`
- `compact(summarize_fn)` elimina mensajes y llama opcionalmente al LLM
- `get_messages(system=...)` antepone el system prompt

### `HookManager` (tools/hooks.py)

18 hooks built-in con sistema pre/post:
- `pre_tool(name, args)` — ejecutado antes de la tool
- `post_tool(name, args, result)` — ejecutado después de la tool
- Hooks con par pre+post: `interface_change_detector`, `test_suite_delta`
- Activación/desactivación dinámica con `/hooks builtin <nombre>`

### `SubAgentRunner` (agent/subagent.py)

Gestiona el lanzamiento de subagentes:
- Los subagentes comparten el modelo de inferencia del padre (restricción VRAM)
- Comparten el `EmbeddingClient` del padre (sin conexiones adicionales)
- El historial y workspace son propios de cada subagente
- Ejecución síncrona cuando los lanza el LLM via `spawn_subagent`
- El host Ollama se asigna en **round-robin** entre `all_ollama_hosts` (función `_pick_subagent_host`) de forma thread-safe

```python
# Asignación de host en SubAgentRunner.run()
sub_config.ollama_host = _pick_subagent_host(self.config)
# → rota entre config.all_ollama_hosts = [host] + [h for h in extra_hosts if h]

# Embeddings siempre al host dedicado (o principal si no hay)
sub_config.embed_host = config.effective_embed_host
# → config.ollama_embed_host or config.ollama_host
```

### WebUI (webui/app.py)

Flask con SSE (Server-Sent Events):
- `AgentLoop` completo integrado (mismo comportamiento que el TUI)
- Streaming via SSE en `/api/chat/stream` y `/api/agents/stream`
- Conversación persistente en el servidor (sobrevive cambios de pestaña)
- Páginas: `/` (dashboard), `/chat`, `/config`, `/sessions`, `/agents`, `/doctor`, `/theme`
- Puerto por defecto: 4000

### Plugin VIM (extensions/vim/)

Versión 3.0.0:
- Comunicación via API REST y SSE del WebUI
- Auto-detección del servidor WebUI al arrancar
- Panel lateral con streaming en tiempo real
- Inyección automática de fichero actual + línea + filetype

## Patrones de diseño

### Factory functions para herramientas

Las herramientas se construyen con factories que capturan configuración en closures:

```python
def build_bash_schema(max_output_chars=20000, default_timeout=120) -> tuple:
    def _bash(command, timeout=default_timeout, workdir=None):
        return bash_execute(command, timeout=timeout,
                            max_output_chars=max_output_chars)
    return "bash", _bash, schema
```

### Gestión segura de procesos bash

`tools/bash.py` usa `subprocess.Popen` con:
- `start_new_session=True` — crea un grupo de procesos separado
- `stdin=subprocess.DEVNULL` — impide que hijos queden bloqueados
- Al timeout: `os.killpg(pgid, SIGKILL)` mata todo el árbol de procesos

### Progreso en tiempo real

Thread-local progress callbacks en `tools/progress.py`:
```python
set_progress_callback(lambda f: setattr(self, "_tool_current_file", f))
# En code_search.py (streaming con Popen):
for line in rg_stdout:
    if line["path"] not in seen_files:
        report_progress(line["path"])  # → actualiza status bar
```

### Shared console

Todos los módulos usan `from ui.console import console` — nunca `Console()` local. Esto evita conflictos con el TUI de prompt_toolkit.

### VRAM y subagentes — multi-servidor

Solo pueden estar cargados simultáneamente el LLM activo y el modelo de embeddings en cada servidor. Los subagentes fuerzan el modelo del padre pero pueden usar hosts distintos:

```python
sub_config.model       = self.config.model           # mismo LLM (restricción VRAM)
sub_config.embed_model = self.config.embed_model     # mismo embed model
sub_config.ollama_host = _pick_subagent_host(config) # host asignado por round-robin
```

Con un solo servidor (`extraHosts=[]`) el comportamiento es idéntico al clásico. Con varios servidores, cada subagente en paralelo ejecuta en una GPU diferente, eliminando el cuello de botella de inferencia.

## Añadir una nueva funcionalidad

### Nueva herramienta nativa
1. Implementar en `tools/`
2. Registrar en `build_registry()` de `oocode.py`
3. Añadir permiso por defecto en `DEFAULT_CONFIG["permissions"]`

### Nuevo servidor MCP bundled
1. Crear `mcp_servers/mi_servidor.py` siguiendo el patrón `_TOOLS`, `_TOOL_FNS`, `_PROMPTS`, `_RESOURCES`
2. Wiring en `oocode.py` similar a los servidores existentes
3. Añadir flag de activación en `DEFAULT_CONFIG["mcp"]`

### Nuevo comando `/slash`
1. Añadir entrada en `SLASH_HELP` en `ui/commands.py`
2. Implementar `_cmd_nombre(args, ...)` en `ui/commands.py`
3. Añadir `elif cmd == "/nombre":` en `handle_slash()`

### Nuevo hook built-in
1. Implementar `_hook_nombre_pre()` y/o `_hook_nombre_post()` en `tools/hooks.py`
2. Registrar en `_BUILTIN_HOOKS` con nombre y descripción
3. Añadir a `active_builtin_names()` para que aparezca en `/hooks list`
