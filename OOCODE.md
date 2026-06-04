# OOCODE.md — OOCode Project Instructions

## Estado Actual (2026-06-04)

| Item | Valor |
|------|-------|
| **Versión** | 0.4.3 |
| **Tests** | 4509 (100% pasando, sin LLM ni servidor externo) |
| **Backend LLM** | Ollama (estable). OpenAI-compatible y Anthropic (experimentales) — configurable en `api.type` |
| **MCP oocode_assistant** | 53 tools: code analysis, edit, utilidades, linting, prompts/resources |
| **MCP devops_assistant** | 66 tools: git (16), docker/compose (23), build/debug (11), archive (3), fs (13) |
| **MCP database_assistant** | 20 tools: SQLite, PostgreSQL/MySQL opcionales (desactivado por defecto) |
| **MCP system** | systemctl, paquetes, red, disco, procesos |
| **MCP home_office** | 66 tools Word/Excel/PPT/email/calendario (O365 nativo) |
| **MCP security** | 24 tools recon/web/crypto/CTF |
| **MCP iot** | 25 tools TAPO/Alexa/HA/MQTT/ESPHome |
| **MCP http_client** | 17 tools HTTP/APIs: request, diff, openapi, curl, websocket, mock, graphql, jwt |
| **Hooks** | 18 hooks built-in (ver sección Hooks) |
| **Agentes** | main, coding, reasoning, home_office, webcrawler |
| **WebUI** | Puerto 4000 *(beta)* (`python oocode.py --webserver start`); paridad TUI: status bar bajo el prompt, "Pensando" como estado, subagentes en bloques de conversación (ver `doc/19_webui.md`) |
| **Tests WebUI** | Cubierto por la suite (`tests/test_*webui*`, `test_63/64/65/73/75/76`) sin servidor externo |

## Comandos Rápidos

```bash
python oocode.py                     # Agente main
python oocode.py --agent coding      # Agente coding
python oocode.py --agent home_office # Agente home_office
python oocode.py --doctor            # Diagnóstico del sistema
python oocode.py --webserver start   # WebUI Flask
python -m pytest tests/ -q           # Suite de tests (4509 tests)
```

## Cambio de Agente en Runtime

```
/switch <id>    # Cambia agente recargando workspace y sesión
/agents         # Lista todos los agentes disponibles
```

## Reglas Críticas

- `compose_down -v` DESTRUYE volúmenes — PROHIBIDO sin confirmación explícita
- Archivos >1000 líneas: `code_outline(path)` + `read_sections(path, [...])` PRIMERO
- PROHIBIDO bash para: git/grep/find/ls/cat/sed-i/make/pytest/docker → usar tools nativas
- Declarar completado SOLO tras verificar con `run_tests` / `lint_file` / `lsp_diagnostics`
- Antes de editar: verificar con `grep_code` que el patrón existe exactamente

---

## Arquitectura

```
oocode.py  →  agent/runtime.py  →  agent/loop.py (AgentLoop)  →  api/ (BackendClient)
                                        │  ┌─ ui/loop_tui.py (TUIDisplayMixin)        ├─ api/ollama.py
                                        │  └─ webui/loop_webui.py (WebUIMixin)         ├─ api/openai.py
                                   tool dispatch (MCP + nativos)                       └─ api/anthropic.py
                                        │
                    tools/           mcp_servers/        agent/lsp_client.py
                    registry.py      (stdio JSON-RPC)    (Language Servers)
```

### Módulos clave

| Módulo | Propósito |
|--------|----------|
| `config/` | Paquete: `OOConfig` (Pydantic) + `DEFAULT_CONFIG` ensamblado desde `config/blocks/`. Config en `~/.oocode/oocode.json`. Bloque `api` unificado (`type`/`key`/`host`/`embedHost`). `effective_embed_host` resuelve el host de embeddings (siempre Ollama). |
| `api/` | `BackendClient` ABC + `OllamaBackend`/`OpenAIBackend`/`AnthropicBackend`. `build_client(config)` factory. |
| `agent/loop.py` | `AgentLoop(TUIDisplayMixin, WebUIMixin)`: streaming, dispatch, auto-continue, plan tracker, compactación. |
| `agent/loop_helpers.py` | Constantes y funciones puras re-exportadas por loop.py. |
| `agent/context.py` | `ConversationContext`: historial + compactación automática/manual. |
| `agent/memory.py` | `MemorySystem`: ficheros .md persistentes + embeddings semánticos. |
| `agent/subagent.py` | `SubAgentRunner`: lanza AgentLoop aislado, round-robin de hosts. Aplica `subagents_auto_cont_max` (default 16) e `subagents_inference_timeout` al sub_config. **Watchdog de timeout por INACTIVIDAD** (v0.4.3): `defaultTimeout`/`timeout_seconds` = máx. segundos SIN progreso por paso (no tiempo total); el loop emite `heartbeat()` por iteración/respuesta LLM/tool. |
| `agent/mcp_client.py` | `McpPool`: gestiona subprocesses MCP stdio JSON-RPC 2.0. |
| `agent/mcp_manager.py` | Catálogo de servidores MCP externos (catalog.json), hot-add sin reiniciar. |
| `agent/workspace_rag.py` | `WorkspaceRAG`: indexación semántica + auto-inject en system prompt. |
| `agent/session.py` | `SessionManager`: persistencia JSONL de sesiones. |
| `agent/lsp_client.py` | LSP client: 30+ lenguajes, auto-arranque por extensión de fichero. |
| `tools/registry.py` | `ToolRegistry`: name→fn map, cache intra-turn. `tool_schemas()` devuelve schemas en formato OpenAI/Ollama (`ollama_schemas()` alias de compatibilidad). |
| `tools/permissions.py` | `PermissionManager`: modos auto/ask/deny por herramienta. |
| `tools/hooks.py` | `HookManager`: 18 hooks built-in pre/post con par pre+post. |
| `ui/loop_tui.py` | `TUIDisplayMixin`: rendering Rich/ANSI (● ⎿ ◈ diffs spinners live block). |
| `ui/repl.py` | REPL prompt_toolkit: prompt sticky, status bar, toolbar. |
| `ui/app.py` | `OOCodeApp`: TUI full-screen con live block y task progress panel. |
| `webui/loop_webui.py` | `WebUIMixin`: SSE events al navegador, plan progress. |
| `mcp_servers/oocode_assistant.py` | Herramientas de desarrollo: git, docker, fs, grep, símbolos. |
| `mcp_servers/home_office_assistant.py` | 66 tools: doc_create, insert_chart (OOXML nativo), xlsx_*, pptx_*, email, calendario. |
| `mcp_servers/security_assistant.py` | 24 tools: nmap, web, crypto, CTF, defensivas. |
| `mcp_servers/iot_assistant.py` | 25 tools: TAPO, Alexa, HA, MQTT, ESPHome. |
| `mcp_servers/system_assistant.py` | systemctl, paquetes, red, disco, procesos, firewall. |
| `workspace/manager.py` | `WorkspaceManager`: OOCODE.md, IDENTITY.md, SOUL.md por agente. |

---

## Herramientas — USA SIEMPRE LA COLUMNA CORRECTA

| Necesidad | USA | NO |
|-----------|-----|-----|
| Leer fichero | `read_file(path, offset=N, limit=M)` | `bash cat/head/tail/sed -n` |
| Comparar ficheros | `diff_files(a, b)` | `bash diff` |
| Tests | `run_tests(path)` | `bash pytest / npm test` |
| Estructura fichero | `code_outline(path)` | `read_file` sin offset en ficheros grandes |
| Leer secciones | `read_sections(path, ['Clase.metodo'])` | `read_file(offset=N)` × N |
| Buscar en código | `grep_code` / `multi_grep(patterns=[…])` | `bash grep -rn` |
| Buscar símbolo | `lsp_workspace_symbols(q, path)` o `symbol_lookup` | `bash grep -rn` |
| Impacto de cambio | `affected_files(symbol, directory)` | `grep_code` + leer cada fichero |
| Callers/callees | `lsp_call_hierarchy(path, line)` | `bash grep -rn función` |
| Comparar código | `code_compare(a, b, symbol)` | grep+read×2 |
| Buscar ficheros | `find_file` / `find_files` / `find_dir` | `bash find -name` |
| Listar directorio | `ls_dir` | `bash ls -la` |
| Info fichero | `file_stat` | `bash wc -l / stat` |
| Editar fichero | `edit_file` / `regex_replace` / `smart_replace` | `bash sed -i` |
| Editar múltiples | `bulk_replace` / `edit_files` | `bash sed -i` en bucle |
| Crear fichero | `write_file` | `bash cat > f <<'EOF'` |
| Python puntual | `python_exec(code=…, workdir=…)` | `bash python3 -c/<<'EOF'` |
| Índice símbolos | `find_symbol` / `list_symbols` / `extract_functions` | `bash ctags` |
| Git | `git_status/diff/add/commit/log/branch/stash` | `bash git …` |
| Docker/compose | `docker_ps/logs/exec/inspect` / `compose_up/down/logs/…` | `bash docker …` |
| Compilar | `make_run` | `bash make/gcc/cc` |
| Linting | `lint_file` / `lint_project` | `bash ruff/mypy/…` |
| Paquetes Python | `pip_tool(action='install', packages=[…])` | `bash pip install` |
| Debug | `strace_run` / `gdb_run` / `pdb_run` / `valgrind_run` | `bash strace/gdb` |

`bash` = ÚLTIMO RECURSO — solo si ninguna tool de la tabla lo cubre.

---

## Añadir funcionalidad

### Nueva herramienta nativa
1. Implementar `fn(**kwargs) -> str` en `tools/`
2. Definir schema inner format: `{"name": "...", "description": "...", "parameters": {...}}` — NO doble wrapper
3. Registrar en `oocode.py:build_registry()` vía `registry.register(name, fn, schema)`
4. Añadir permission default en `config.py:DEFAULT_CONFIG["permissions"]`

### Nueva herramienta MCP
Añadir a `mcp_servers/oocode_assistant.py`:
1. Implementar función `_tool_<name>(...)` devolviendo string
2. Añadir dict schema a lista `_TOOLS`
3. Añadir `"<name>": _tool_<name>` a dict dispatch `_TOOL_FNS`

### Nuevo /slash command
1. Añadir entrada a `SLASH_HELP` en `ui/commands.py`
2. Añadir rama `elif cmd == "/newcmd":` en `handle_slash()`

---

## Schema de tools — CRÍTICO

`ToolRegistry.tool_schemas()` (antes `ollama_schemas()`) envuelve schemas como `{"type": "function", "function": schema}`.
Schemas deben usar **inner format only** (sin wrapper):

```python
# CORRECTO
{"name": "my_tool", "description": "...", "parameters": {...}}

# INCORRECTO — double-wrapping rompe resolución de nombre de tool
{"type": "function", "function": {"name": "my_tool", ...}}
```

---

## Multi-task detection y task progress panel

`AgentLoop._detect_tasks(text)` extrae listas numeradas/bullet (≥2 items, ≥10 chars cada uno) y:
- Puebla `_plan_tasks` con `{text, status}` (pending/active/done)
- Inyecta lista en `_turn_guidance()` (PLAN OBLIGATORIO)
- Auto-continue hasta `autoContinueMax` veces (default 8)

**Detección premature done:** `_PREMATURE_DONE_RE` detecta contradicción. `auto_continue_pending_task` relanza si hay items active/pending sin tools ejecutadas.

---

## Bash guards y /elevated mode

### Safety guards (siempre activos, incluso con `/elevated on`)
- `bash rm -rf` en paths de sistema → siempre bloqueado
- `bash docker compose down -v` → siempre bloqueado

### Redirect guards (bypass con `/elevated on` o `/elevated full`)
- `bash grep -r` → `grep_code` / `multi_grep`
- `bash find -name` → `find_files` / `find_file`
- `bash sed -i` → `edit_file` / `regex_replace`
- `bash ls` → `ls_dir`
- `bash cat <file>` → `read_file`
- `bash docker exec` → `docker_exec`

### Guards permanentes (inafectados por elevated)
- `docker_exec` con heredoc write patterns → siempre bloqueado
- `python_exec` con `subprocess.docker` → siempre bloqueado
- `write_file` a `_temp.py` / `_temp.sh` → siempre bloqueado

---

## Hooks built-in (18)

| Hook | Trigger | Acción |
|------|---------|--------|
| `diff_after_write` | post write | Render diff visual estilo Claude Code |
| `ctags_after_write` | post write | Rebuild ctags index |
| `lint_after_write` | post write | ruff/mypy/eslint/shellcheck |
| `quick_syntax_after_write` | post write .py | ast.parse instantáneo |
| `lsp_after_write` | post write | Diagnósticos LSP |
| `autoformat_after_write` | post write | Format vía LSP (off por defecto) |
| `backup_before_write` | pre+post write | Crea .bak antes; elimina en éxito |
| `check_secrets` | pre write_file | Bloquea si hay credenciales reales |
| `log_tool_calls` | post write | Append a ~/.oocode/logs/tool_calls.jsonl |
| `todo_scan_after_write` | post write | Muestra TODO/FIXME encontrados |
| `test_after_write` | post write .py | pytest en test file asociado |
| `size_check_after_write` | post write | Avisa si >300 líneas / 15 KB |
| `verify_after_edit` | post edit_file | Re-lee sección con marcadores ▶ |
| `test_suite_delta` | pre+post write | Detecta regresiones vs. baseline |
| `interface_change_detector` | pre+post write .py | Detecta cambios de firma/API pública |
| `config_syntax_after_write` | post write .json/.toml/.ini | Valida sintaxis de configs |
| `git_push_guard` | pre git_* | Avisa si rama protegida o mensaje vacío |
| `security_audit_log` | post Security MCP | Registra en security_audit.log |

Toggle: `/hooks builtin <nombre>`. Persiste en `~/.oocode/oocode.json`.

---

## Pre-edit verification

`_precheck_tool_call()` ejecuta antes de todas las guards:

**Path hallucination check** (para `read_sections`, `code_outline`, `code_compare`, `diff_files`):
- Si `os.path.exists(expanded_path)` es False → `⛔ RUTA NO ENCONTRADA`

**Old_string verification** (para `edit_file`):
- Solo cuando el fichero fue leído este turno (`_turn_read_paths`)
- Verifica `old_string in content` → `⛔ PRE-EDIT FALLIDO` con líneas similares como hints

---

## LSP — usar si hay servidor activo

| Tarea | Tool |
|-------|------|
| Funciones/structs del fichero | `lsp_symbols(path)` |
| Buscar símbolo en proyecto | `lsp_workspace_symbols(query, path)` |
| Callers/callees | `lsp_call_hierarchy(path, line)` |
| Tipo de variable | `lsp_hover(path, line, col)` |
| Errores/warnings | `lsp_diagnostics(path)` |
| Renombrar en todo el código | `lsp_rename(path, line, col, new_name, apply=true)` |

---

## Planificación autónoma — OBLIGATORIA para tareas complejas

Para cualquier consulta que implique ≥3 pasos distintos: ANTES de ejecutar NINGUNA herramienta, emite un plan detallado:

```
Plan:
1. [Acción]: [qué harás exactamente] — ficheros: [rutas exactas] — tools: [tools que usarás]
2. [Acción]: [cambios concretos] — ficheros: [rutas] — riesgo: [si puede romper algo]
```

Si hay bloqueadores: añade `⚠ REQUIERE REVISIÓN: [descripción]` — el sistema pausa y espera.

**Flujo con plan_create:**
1. Emite plan en texto — SIN llamar tools aún
2. Llama `plan_create(tasks=[...], summary="...")`
3. Ejecuta cada tarea anunciando "Tarea N: descripción breve"
4. Al terminar TODAS: "He completado todas las tareas."

---

## Flujo de trabajo

1. **Analiza y planifica** — si ≥3 pasos, crea plan numerado primero.
2. **Explora PRIMERO** — `read_file` + `grep_code` + `lsp_symbols` antes de editar.
   - NUNCA uses `edit_file` sin haber leído el fichero en este turno.
3. **Implementa** — `edit_file` / `write_file` / `bulk_replace`. Anuncia qué fichero editas y por qué.
4. **Verifica** — `run_tests` / `lint_file` / `lsp_diagnostics` / `make_run`.
5. **Finaliza** — informe: qué se hizo, ficheros cambiados (rutas exactas), resultado de tests, advertencias.

---

## Reglas generales

- **Antes de actuar**: anuncia brevemente qué vas a hacer (1 frase para simple, plan para ≥3 pasos).
- **Tras exploración**: describe qué encontraste — rutas, funciones, causas, fragmentos `ruta:línea`.
- **Tras implementación**: describe el cambio — función/clase modificada, qué hacía antes y qué hace ahora.
- **Al finalizar**: informe estructurado — qué se hizo, ficheros cambiados, tests (N/M), advertencias.
- **Ficheros >1000 líneas**: SIEMPRE `code_outline(path)` + `read_sections(path, [...])` primero.
- NUNCA inventes rutas, código ni resultados. NUNCA declares completado sin verificar con tools.
- Anti-bucle: si una tool falla 2 veces con el mismo argumento, CAMBIA estrategia.
- **PROHIBIDO emitir "He completado todas las tareas." si**: hay tareas pendientes, se menciona trabajo futuro, hay errores sin resolver, o la tarea requería editar ficheros y NO se llamó edit_file/write_file.
- **ANTES de declarar completado**: si se modificó código, DEBES llamar `run_tests` o `test_file`.
- El CWD es el directorio del proyecto. `~/.oocode/workspace/` = identidad del agente (NO código).
- `web_search` obligatorio ante errores HTTP/API/import desconocidos antes de probar estrategias.

---

## Memoria e instrucciones persistentes

- `workspace_remember(note)` — instrucciones persistentes → OOCODE.md
- `mem_save(snake_case_name, content)` — hallazgos importantes (arquitectura, decisiones, bugs)

---

## Agentes y Workspaces

| Agente | Emoji | Workspace | Propósito |
|--------|-------|-----------|-----------|
| `main` | 🤖 | `~/.oocode/workspace/main` | Asistente general de programación |
| `coding` | 💻 | `~/.oocode/workspace/coding` | Desarrollo, refactoring, LSP |
| `home_office` | 📋 | `~/.oocode/workspace/home_office` | Documentación corporativa O365 |
| `reasoning` | 🧠 | `~/.oocode/workspace/reasoning` | Análisis lógico, coordinación de agentes |
| `webcrawler` | 🕷️ | `~/.oocode/workspace/webcrawler` | Búsqueda web, informes |

Sin `--agent` arranca `main`. Ficheros del workspace (`IDENTITY/SOUL/USER/AGENTS/HEARTBEAT/TOOLS/MEMORY.md` + `memory/`). El contexto por defecto es `mini` (resumen de identidad + memoria + sección `## Notas` de `TOOLS.md`/`AGENTS.md`); `/ctx full` carga todo.

**Capa de personalización (v0.4.3):** la sección `## Notas` de `TOOLS.md` (uso de herramientas) y `AGENTS.md` (delegación) se carga en el contexto del agente — personalizable sin tocar código ni `SYSTEM_RULES`, coste cero hasta que escribes contenido real (`_extract_section` en `workspace/manager.py`, cap 1500 chars). El roster de agentes (rol de cada `IDENTITY.md`) se inyecta dinámicamente para que el LLM delegue en el agente más afín.

**Subagentes (v0.4.3):** ejecutan las tools en el `project_dir` del padre, no en su workspace de identidad (`agent/subagent.py`: `build_registry_fn(os.path.expanduser(project_dir or workspace), …)`). Su `●` de texto se alinea bajo la columna `│` (`_render_subagent_bullet`).

---

## Documentación completa

Ver `doc/` para documentación detallada:
- `01_installation.md` — Instalación y dependencias
- `02_configuration.md` — Referencia completa de oocode.json
- `03_commands.md` — Todos los slash commands
- `04_tools.md` — Herramientas nativas
- `05_memory.md` — Memoria semántica y embeddings
- `06_context.md` — Ventana de contexto, compactación, RAG
- `11_architecture.md` — Arquitectura interna, patrones de diseño
- `12_subagents.md` — Subagentes, round-robin multi-GPU
- `16_workspaces_agents.md` — Workspaces por agente, /switch
- `19_webui.md` — WebUI Flask: setup, API REST, SSE
- `22_mcp_servers.md` — 5 MCP bundled + catálogo externos
- `23_hooks.md` — Los 18 hooks built-in
- `24_tui_display.md` — TUI live block, auto-split bullet

---

*OOCode v0.4.3 — Última actualización: 2026-06-04*

## Notas del usuario
- [2026-06-01 17:57] Plan activo WebCrawler: Tarea 5 (documentación y RFCs) en curso.
- [2026-06-01 17:57] Plan activo WebCrawler: Tarea 4 completada. Tarea 5 pendiente: generar documentación y RFCs.
- [2026-06-01 17:57] Plan activo WebCrawler: Tarea 4 (gestionar contenedores) completada - no hay docker-compose en proyecto. Tarea 5 pendiente: generar documentación y RFCs.
- [2026-06-01 17:57] Plan activo WebCrawler: Tarea 3 (analizar código) completada. Tarea 4 pendiente: identificar.
- [2026-06-01 17:57] Plan activo WebCrawler: Tarea 1 (búsqueda web) completada. Tarea 2 pendiente: identificar.
