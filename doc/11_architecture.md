# 11 — Arquitectura interna

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
│   ├── tasks.py           # TaskManager: lista todo/wip/done persistente
│   ├── scheduler.py       # Scheduler: jobs periódicos
│   ├── subagent.py        # SubAgentRunner: lanza AgentLoop aislado para spawning
│   └── logger.py          # Logger: RotatingFileHandler + funciones info/debug/error
│
├── tools/
│   ├── registry.py        # ToolRegistry: nombre→función, genera schemas Ollama
│   ├── permissions.py     # PermissionManager: modos auto/ask/deny por herramienta
│   ├── filesystem.py      # read_file, write_file, edit_file, edit_files, list_dir
│   ├── bash.py            # bash_execute + factory build_bash_schema
│   ├── search.py          # web_search (DuckDuckGo), web_fetch + factories
│   ├── code_search.py     # code_search via ripgrep — streaming con Popen + select
│   ├── progress.py        # Thread-local progress callbacks: set_progress_callback / report_progress
│   ├── hooks.py           # HookManager: 8 built-in hooks (diff, ctags, lint, lsp, autoformat, backup, secrets, log)
│   ├── diff_renderer.py   # Visual diff rendering con colores Rich
│   └── ctags_index.py     # Symbol indexing via universal-ctags
│
├── ui/
│   ├── repl.py            # REPL: prompt_toolkit input, routing /slash vs agente
│   ├── renderer.py        # Rich: markdown, tablas, spinners, status, config
│   └── commands.py        # Registro + handlers de /slash commands
│
├── plugins/
│   └── manager.py         # PluginManager: carga dinámica, hooks, herramientas, comandos
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
  ├── WorkspaceManager.init()           # crea OOCODE.md si no existe
  ├── select_model_interactive()        # si no hay modelo configurado
  │
  ├── PermissionManager(permissions)
  ├── EmbeddingClient(host, embed_model)  # una sola instancia — compartida
  ├── MemorySystem(embed_client, ...)
  ├── build_registry(workspace, config) # registra todas las herramientas
  ├── SubAgentRunner(config, ..., embed_client)  # recibe el mismo embed_client
  │     └── registry.register("spawn_subagent", ...)
  │
  ├── SessionManager.start()
  ├── AgentLoop(config, registry, ...)   # no crea EmbeddingClient propio
  │
  ├── BranchManager / TaskManager / Scheduler
  │
  ├── SkillManager(enabled_override=config.skills_enabled)
  │     └── load_tools() → registry.register(...)
  │
  ├── PluginManager(enabled_override=config.plugins_enabled)
  │     ├── load_all(config)   → on_start(config) por plugin
  │     └── get_tools() → registry.register(...) [sobreescribe]
  │
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
        ├── log.debug("user_message")
        │
        └── while True:
              │
              ├── context.should_compact() → _do_compact()
              ├── messages = context.get_messages(system=_system_prompt())
              ├── _stream_response(messages, tools)  → Ollama.chat(stream=False)
              │
              ├── si error → log.error("llm_error") → return error str
              │
              ├── si text → Markdown render + session.log_message("assistant")
              │
              └── para cada tool_call:
                    ├── _show_tool_call(name, args)
                    ├── permissions.check(name)
                    │     ├── auto → ejecuta
                    │     ├── ask  → pide confirmación al usuario
                    │     └── deny → "Operación denegada"
                    ├── registry.call(name, args)
                    ├── log.debug("tool_call", ...)
                    ├── _truncate_tool_result(result)
                    └── context.add_tool_result(...)
              │
              └── si no hay tool_calls → break
```

## Componentes clave

### `OOConfig` (Pydantic BaseModel)

Carga de `oocode.json` con validación. Los campos son atributos Python tipados. `config.save()` serializa de vuelta a JSON. Cada componente recibe exactamente los campos que necesita (no el objeto completo) excepto en `on_start(config)` de plugins.

### `ToolRegistry`

Diccionario `nombre → (función, schema)`. El método `ollama_schemas()` devuelve la lista de schemas en formato Ollama para pasarla a `chat()`. El método `call(nombre, args)` invoca la función con `**args` y captura excepciones.

### `ConversationContext`

Lista de mensajes + resumen acumulado. El método `get_messages(system=...)` antepone el system prompt. `should_compact()` compara tokens estimados con el umbral. `compact(summarize_fn)` elimina mensajes y llama opcionalmente al summarizador.

### `AgentLoop`

El corazón de OOCode. Mantiene el cliente Ollama, el contexto, la memoria y todos los managers. El método `run(mensaje)` ejecuta un turno completo. Los atributos `branches`, `tasks`, `scheduler`, `skills`, `plugins` se asignan desde `oocode.py` tras la construcción.

`AgentLoop` no crea ni posee ningún `EmbeddingClient`; toda la lógica de embeddings pasa por `MemorySystem`, que recibe el cliente compartido al construirse.

### `PluginManager` vs `SkillManager`

| | PluginManager | SkillManager |
|-|---------------|--------------|
| Fuente de verdad enabled | `oocode.json` + `enabled.json` | `oocode.json` + `enabled.json` |
| Hooks | on_start, on_message, etc. | No |
| Comandos /slash | Sí | No |
| Sobreescribir built-ins | Sí | No (usa `if not registry.has()`) |
| Inyección system prompt | Sí | No |

### `RuntimeSettings` (dataclass)

Estado de sesión en memoria (no persiste). Controla think_level, fast_mode, verbose, accent_color, extra_dirs, etc. Se pasa a los command handlers para que puedan modificarlo.

## Patrones de diseño usados

### Factory functions para herramientas

Las herramientas se construyen con factories que capturan los parámetros de config en closures:

```python
def build_bash_schema(max_output_chars=20000, default_timeout=120) -> tuple:
    def _bash(command, timeout=default_timeout, workdir=None):
        return bash_execute(command, timeout=timeout, workdir=workdir,
                            max_output_chars=max_output_chars)
    return "bash", _bash, schema
```

Esto evita hardcodear valores y hace cada herramienta configurable sin pasar el config completo.

### Gestión de procesos en `bash`

`tools/bash.py` usa `subprocess.Popen` con dos flags clave:
- `start_new_session=True` — crea un grupo de procesos separado
- `stdin=subprocess.DEVNULL` — impide que procesos hijos queden bloqueados esperando stdin

Al timeout, se mata todo el árbol con `os.killpg(pgid, SIGKILL)`, evitando procesos zombie a 100% CPU (problema habitual con `subprocess.run(shell=True)` que mata sólo el shell padre, no sus hijos).

```python
def _kill_group(proc):
    pgid = os.getpgid(proc.pid)
    os.killpg(pgid, signal.SIGKILL)  # mata shell + todos los hijos
    proc.communicate(timeout=5)       # espera a que liberen recursos
```

### TUI display system y progreso en tiempo real

`agent/loop.py` implementa dos modos de display según cómo se ejecutan las tools:

**Ejecución secuencial (pre_shown=True):**
- Antes de ejecutar: `  ◐ nombre_tool  [args]` — spinner ◐ parpadeante para **todas** las tools
- Durante búsqueda: el status bar muestra `⎿ filename` actualizando en tiempo real mediante `_tool_current_file`
- Después de ejecutar: `_show_inline_compact_result()` colapsa el resultado:
  - Búsquedas: `  ⎿ N resultados en X ficheros`
  - Lecturas: `  ⎿ filename  [N líneas]`
  - Write/edit: muestra diff (no se colapsa)
  - Error: `  ⎿ error: …` en rojo dim

**Ejecución paralela (pre_shown=False):**
- Los resultados se acumulan en `_turn_block[]`
- Al terminar el batch, `_flush_turn_block()` los muestra como resumen compacto
- `_make_compact_summary()` convierte el block en una línea

**Progreso de búsqueda en tiempo real** (`tools/progress.py`):

```python
# Thread-local — cada thread de tool tiene su propio callback
set_progress_callback(lambda f: setattr(self, "_tool_current_file", f))
# En code_search.py (streaming con Popen):
for line in rg_stdout:
    if line["path"] not in seen_files:
        report_progress(line["path"])  # → actualiza status bar
```

Tools con progress: `code_search`, `grep_code`, `grep_file`, `multi_grep`, `symbol_lookup`, `semantic_search`.

**Palabras de progreso:**
- `_THINKING_WORDS` (24 palabras) — durante inferencia LLM (Cavilando, Tokenizando…)
- `_DONE_WORDS` (19 palabras) — al completar el turno (Neuroneado, Inferido…)

La barra de contexto en la status bar usa `_ctx_bar(plain=True)` para caracteres Unicode puros (`█░`) sin markup Rich, que prompt_toolkit no puede interpretar.

### Sub-agentes y restricción VRAM

Los sub-agentes se lanzan como herramienta (`spawn_subagent`) dentro del bucle principal. Su ejecución es **estrictamente secuencial**: el agente padre espera el resultado antes de continuar, por lo que nunca hay dos llamadas a Ollama activas al mismo tiempo.

**Restricción de modelos:** la GPU dispone de 16 GB de VRAM. Solo pueden estar cargados simultáneamente:
- El modelo de inferencia activo (ej. `qwen2.5-coder:14b`)
- El modelo de embeddings (ej. `nomic-embed-text-v2-moe`)

Para evitar solapamientos, `SubAgentRunner.run()` fuerza antes de crear el sub-agente:

```python
sub_config.model       = self.config.model        # mismo LLM que el padre
sub_config.ollama_host = self.config.ollama_host  # mismo servidor
sub_config.embed_model = self.config.embed_model  # mismo modelo embed
```

El sub-agente hereda también el `EmbeddingClient` del padre (instancia compartida), evitando conexiones duplicadas al servidor de embeddings. La diferencia entre agentes es únicamente el workspace y el contexto de conversación, nunca el modelo.

```
oocode.py
  │
  ├── EmbeddingClient ──────────────────────────────┐
  ├── MemorySystem(embed_client)                    │ (compartido)
  ├── SubAgentRunner(embed_client) ─────────────────┘
  │
  └── [turno agente padre]
        └── spawn_subagent("coding", tarea)   ← tool call síncrono
              │
              ├── sub_config.model = padre.model    ← modelo forzado
              ├── MemorySystem(embed compartido)
              └── AgentLoop.run(tarea)              ← secuencial, mismo LLM
```

### Plugin TOOLS dinámico via on_start

Los plugins reconstruyen su lista `TOOLS` en `on_start(config)`, lo que permite herramientas condicionales según la configuración (ej: SearXNG solo expone `web_search` si `enabled=True`).

### Plugins incluidos (`~/.oocode/plugins/`)

| Fichero | Activa con | Descripción |
|---------|-----------|-------------|
| `searxng.py` | `/plugins enable searxng` | Búsqueda SearXNG local; sobreescribe `web_search` si `enabled=true` |
| `git.py` | `/plugins enable git` | 11 herramientas git nativas + comando `/git` |
| `diff.py` | `/plugins enable diff` | Diffs con colores al editar ficheros; sobreescribe `write_file` y usa hook `on_tool_result` para `edit_file` |

El nombre del fichero (sin `.py`) es la clave usada en `_enabled` y en `oocode.json`. Siempre debe coincidir con el argumento de `/plugins enable <nombre>`.

### Overriding de herramientas built-in por plugins

Los plugins se cargan **después** de las herramientas base (`build_registry()`). Al llamar `registry.register(name, fn, schema)`, si el nombre ya existe simplemente lo sobreescribe. Esto permite que, por ejemplo, `diff.py` reemplace `write_file` con una versión que captura el contenido anterior y muestra el diff automáticamente.

El hook `on_tool_result(name, args, result)` complementa esto: se llama tras cada herramienta sin necesidad de sobrescribir su implementación, útil cuando el argumento (`old_string`) contiene la información necesaria para el diff.

### Shadowing del builtin `list` en clases

**Antipatrón a evitar:** no nombres métodos `list()` dentro de una clase si hay anotaciones `-> list[...]` en métodos posteriores. Python evalúa las anotaciones en el namespace de clase, donde `list` resuelve al método en lugar del builtin.

```python
# INCORRECTO
class Foo:
    def list(self) -> list[dict]: ...          # OK, list aún es builtin
    def other(self) -> list[tuple]: ...        # FALLA: list = el método anterior

# CORRECTO
class Foo:
    def all_items(self) -> list[dict]: ...     # nombre descriptivo
    def load_tools(self) -> list[tuple]: ...   # OK
```

## Añadir una nueva funcionalidad

### Nueva herramienta built-in
1. Implementar en `tools/`
2. Registrar en `build_registry()` de `oocode.py`
3. Añadir permiso por defecto en `DEFAULT_CONFIG["permissions"]`

### Nuevo comando `/slash`
1. Añadir entrada en `SLASH_HELP` en `ui/commands.py`
2. Implementar `_cmd_nombre(args, ...)` en `ui/commands.py`
3. Añadir `elif cmd == "/nombre":` en `handle_slash()`

### Nueva sección de config
1. Añadir a `DEFAULT_CONFIG` en `config.py`
2. Añadir campos a `OOConfig`
3. Añadir a `load()` y `save()`
4. Añadir a `print_config_full()` en `renderer.py`
5. Añadir al panel de `/config edit` en `commands.py`
