# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proyecto

**OOCode** — Asistente de programación local con soporte multi-backend (Ollama estable; OpenAI-compatible y Anthropic **experimentales**). TUI/REPL interactivo con un agente LLM que dispone de más de 157 herramientas MCP (filesystem, git, docker, LSP, ofimática, seguridad, IoT, bases de datos, HTTP/APIs).

- Backend LLM: configurable en `~/.oocode/oocode.json` → `api.type` (`ollama` | `openai` | `anthropic`)
- Protocolo de herramientas: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0)
- Tests: pytest, 4509 tests sin LLM ni servidor externo
- WebUI: **beta** (v0.4.0) — Flask + SSE, `http://localhost:4000`
- Versión actual: **0.4.3** (`config/constants.py` → `VERSION`)

---

## Comandos de desarrollo

```bash
# Ejecutar suite completa (sin LLM)
python -m pytest tests/ -q --tb=short

# Ejecutar un fichero de test concreto
python -m pytest tests/test_45_home_office_mcp.py -q --tb=short

# Filtrar por nombre de test
python -m pytest tests/ -k "home_office" -q --tb=short

# Ejecutar con output completo de fallos
python -m pytest tests/ --tb=long -x

# Lanzar el agente interactivo
python oocode.py [directorio_de_proyecto]

# Agente nombrado (coding, reasoning, home_office, webcrawler)
python oocode.py --agent coding

# Verificar configuración e instalación
python oocode.py --doctor

# Iniciar como servidor WebUI (puerto 4000)
python oocode.py --webserver start
```

---

## Arquitectura

### Flujo principal

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

#### api/ — backends LLM intercambiables

| Módulo | Responsabilidad |
|--------|-----------------|
| `api/__init__.py` | `build_client(config)` factory — instancia el backend según `config.api_type` |
| `api/base.py` | `BackendClient` ABC, `Chunk`, `Response`, `ToolCall`, `_ToolFunction` normalizados |
| `api/ollama.py` | `OllamaBackend` — envuelve `ollama.Client`; normaliza `Chunk`/`Response` |
| `api/openai.py` | `OpenAIBackend` — httpx directo, compatible con llama.cpp / LM Studio / vLLM |
| `api/anthropic.py` | `AnthropicBackend` — SDK anthropic; convierte mensajes y tool schemas al formato Anthropic |

Todos los backends emiten `Chunk(text, tool_calls, thinking, done, input_tokens, output_tokens)`. `ToolCall` expone `.function.name` / `.function.arguments` (dict) y `.model_dump()` — misma interfaz que los objetos nativos de Ollama.

#### agent/

| Módulo | Responsabilidad |
|--------|-----------------|
| `agent/loop.py` | `AgentLoop`: bucle LLM principal, streaming, dispatch, auto-continue, plan tracker, compactación. Hereda de `TUIDisplayMixin` y `WebUIMixin` |
| `agent/loop_helpers.py` | Constantes (`_SPINNER_FRAMES`, `SYSTEM_RULES`, `_TOOL_ALIASES`…) y funciones puras (`_make_compact_summary`, `_make_tool_preview`, `_ctx_bar`, `_sfmt`…). Re-exportadas por `agent/loop.py` para compatibilidad |
| `agent/runtime.py` | Estado de sesión, permissions, elevated mode, config runtime |
| `agent/context.py` | Ventana de contexto: añadir mensajes, compactación automática/manual |
| `agent/memory.py` | Memoria persistente (diaria + embeddings semánticos) |
| `agent/subagent.py` | Lanzamiento y comunicación con subagentes paralelos. Aplica `subagents_auto_cont_max` e `subagents_inference_timeout` al sub_config antes de arrancar el AgentLoop. |
| `agent/mcp_client.py` | Cliente MCP: conecta con servidores stdio, despacha tool calls |
| `agent/mcp_manager.py` | Catálogo de servidores MCP externos (catalog.json), hot-add sin reiniciar |
| `agent/session.py` | Snapshots de sesión, historial de conversaciones |
| `agent/tasks.py` | Tracker de tareas del plan (`_plan_tasks`): estados pending/active/done |

#### ui/ y webui/

| Módulo | Responsabilidad |
|--------|-----------------|
| `ui/loop_tui.py` | `TUIDisplayMixin`: todo el rendering Rich/ANSI del terminal (● ⎿ ◈, diffs, spinners, live block, compact reset). Accede a atributos de `AgentLoop` vía `self` |
| `webui/loop_webui.py` | `WebUIMixin`: emite eventos SSE al navegador (`_webui_emit`, `_webui_status`, plan progress, `inference_done`). Accede a atributos de `AgentLoop` vía `self` |
| `ui/repl.py` | TUI con prompt_toolkit: prompt sticky, status bar |
| `ui/renderer.py` | Renderizado Rich de headers, diffs, tool output |

#### tools/ y mcp_servers/

| Módulo | Responsabilidad |
|--------|-----------------|
| `tools/registry.py` | Registro de todas las herramientas nativas (filesystem, git, docker…). `tool_schemas()` devuelve schemas en formato OpenAI/Ollama; `ollama_schemas()` es alias de compatibilidad |
| `tools/hooks.py` | 18 hooks built-in: lint_after_write, test_after_write, lsp_after_write, etc. |
| `workspace/manager.py` | Gestión de workspaces por agente (OOCODE.md, IDENTITY.md, SOUL.md) |
| `mcp_servers/oocode_assistant.py` | MCP principal: 53 tools de análisis de código, edit, utilidades, linting, prompts/resources |
| `mcp_servers/devops_assistant.py` | MCP DevOps: 66 tools — git (16), docker/compose (23), build/debug (11), archive (3), fs-mutations (13) |
| `mcp_servers/database_assistant.py` | MCP bases de datos: 20 tools — SQLite (stdlib), PostgreSQL/MySQL (opcionales) |
| `mcp_servers/system_assistant.py` | MCP sistema: servicios, paquetes, red, disco, firewall, monitoring |
| `mcp_servers/home_office_assistant.py` | MCP ofimática: 66 tools para Word/Excel/PPT/email/calendario (solo O365 nativo) |
| `mcp_servers/security_assistant.py` | MCP seguridad: 24 tools recon/web/crypto/CTF |
| `mcp_servers/iot_assistant.py` | MCP IoT: 25 tools TAPO/Alexa/HA/MQTT/ESPHome |
| `mcp_servers/http_client_assistant.py` | MCP HTTP: 17 tools — http_request/get/upload, response_diff, openapi_validate, curl_import, websocket_send, sse_listen, mock_server, graphql_query, jwt_decode, http_batch, http_history |

### Estructura de AgentLoop (herencia Mixin)

```python
class AgentLoop(TUIDisplayMixin, WebUIMixin):
    # TUIDisplayMixin  →  ui/loop_tui.py        (rendering Rich/ANSI: ● ⎿ ◈ diffs spinners)
    # WebUIMixin       →  webui/loop_webui.py   (SSE events para navegador)
    # Núcleo           →  agent/loop.py         (turno LLM, dispatch, auto-continue)
    # Constantes/puras →  agent/loop_helpers.py (_make_compact_summary, _make_tool_preview…)
```

Los mixins acceden a atributos definidos en `AgentLoop.__init__` vía `self` (sin clases abstractas). Los docstrings de cada mixin documentan explícitamente los atributos que esperan. `agent/loop.py` re-exporta todo lo de `loop_helpers.py` con `# noqa: F401` para mantener compatibilidad de imports en tests y código externo.

### Sistema de herramientas

Las herramientas nativas (no MCP) están en `tools/registry.py` como funciones `_execute_*`. Los servidores MCP corren como procesos independientes y se comunican por stdio con `agent/mcp_client.py`.

El dispatch en `agent/loop.py` llama `_execute_tool(name, args)` que primero busca en el registry nativo y si no encuentra, lo reenvía al MCP client correspondiente.

### TUI rendering

El TUI usa `_flush_turn_block()` (en `TUIDisplayMixin`) para agrupar outputs de tools entre dos mensajes `●`. Los planes se renderizan con `◈ Plan de ejecución` diferido hasta después del `⎿` del turno. El spinner multitarea usa `_plan_tasks` con estados `pending/active/done`.

#### Live block (ui/app.py)

El live block es la zona dinámica al final del output mientras el agente ejecuta tools. Muestra:

```
  ● Texto del agente (pulsante en verde/cyan)
  |  ◐ Bash:
  |     $ grep -rn "pattern" src/
  ⎿ Used 2 tools (ctrl+o to expand)
```

Callbacks de AgentLoop inyectados por `OOCodeApp.__init__`:

| Callback | Propósito |
|----------|-----------|
| `_start_live_block_cb(bullet)` | Inicia el bloque con el texto del ● |
| `_update_live_tool_start_cb(label, preview)` | Actualización atómica: nombre de tool + líneas de preview |
| `_update_live_bullet_cb(action)` | Sobreescribe el ● con verbo en gerundio mientras corre |
| `_update_live_tools_cb(count)` | Incrementa contador de tools completadas + limpia preview |
| `_flush_live_block_cb(summary)` | Cierra el bloque y lo mueve al buffer estático |

**Preview de herramientas**: `_make_tool_preview(name, args)` en `loop_helpers.py` genera 1-4 líneas de contexto (args) visibles bajo `|  ◐ tool:` mientras corre; desaparecen al completarse. Los write tools (edit_file, smart_replace…) no generan preview — muestran el diff en su lugar.

**Auto-split bullet**: cuando el planning text (>60 chars) no menciona explícitamente el fichero que se va a editar, el sistema lo imprime como `●` estático y genera automáticamente un header `● Updating file.c:` para el live block de las write tools.

**Orquestación = mensaje nuevo (TUI):** las tools de `_ORCHESTRATION_TOOLS` (`spawn_subagent`/`explore`/`create_team`/`run_team`/`spawn_fanout`) renderizan su PROPIO bloque en la conversación (header `●`/`🔍`/`◈`/`⚡`, streaming `│` del subagente, footer `⎿`) vía `console.print` **durante su ejecución**. Por eso `_show_tool_running_header` cierra el live block del mensaje anterior (`_flush_turn_block()`) ANTES de ejecutarlas y NO las alimenta al `_update_live_tool_start_cb`: sin esto, todo su output caía en `_live_block_body` del `●` previo y quedaba enterrado — invisible hasta que el bloque de tools anterior hacía flush (el usuario no veía al subagente trabajar en tiempo real). El footer `⎿` de explore/team/fanout se imprime ESTÁTICO en `_show_tool_block` (rama `pre_shown`, antes que `_is_modify`), no se bufferiza en `_turn_block` (que ya no tiene live block donde renderizar). `spawn_subagent` imprime su propio `⎿ Done` dentro del closure y retorna antes. **Regla de uso (SYSTEM_RULES):** llamar la orquestación SOLO en su propio turno, nunca batcheada con `read_file`/`grep_code` (`_has_orchestration` ya fuerza modo secuencial en `_turn_dispatch_tools`).

**Streaming `│` del subagente — presupuesto por turno (2026-06-04):** `_print` con `is_subagent=True` envuelve cada línea en `│` y la cuenta contra `_MAX_SUB_LINES` (12); al alcanzarlo imprime `… buffer lleno (ctrl+o para ver completo)` y suprime el resto. Ese cap es **por turno**: `_sub_lines_shown` se resetea al inicio de cada iteración del bucle `run()` (`agent/loop.py`, junto a `_subagent_color_idx += 1`, gateado por `is_subagent`). Antes solo se reseteaba en `_turn_reset_state` (1 vez por `run()`) y al mostrar el header de spawn, así que un subagente multi-turno congelaba tras 12 líneas y ocultaba la actividad posterior. Las líneas `│` van a `console.print` → buffer estático scrollable del padre (cap 80 KB), de modo que las antiguas hacen scroll hacia arriba al llegar las nuevas. test_22 `TestSubagentLinePrintCap`.

**Alineación del `●` de subagentes (2026-06-04):** un subagente NO tiene live block (callbacks `None`), así que su `●` de texto caía en la rama `console.print` directa de `_turn_display_bullet` (columna 0), desalineado respecto a sus líneas de tool (`  │  …`). `_turn_display_bullet` ahora hace early-return a `_render_subagent_bullet` cuando `is_subagent`, que imprime el `●` + continuación vía `self._print` (prefijo `│`, respeta `_MAX_SUB_LINES`). Los avisos de retry XML usan el helper `_notice` (indenta para el principal, `│` para subagentes). Todo el bloque del subagente comparte la columna `│`. test_22 `TestSubagentBulletAlignment`.

**Static ANSI cache** (`_static_ansi_cache` en `OOCodeApp`): el historial estático (~80 KB) se re-parsea con `ANSI()` solo cuando cambia (`_output_static_key`). El blink de 350ms solo re-parsea el live block activo (~6 líneas). Evita parsear 80 KB en cada frame de animación.

### Configuración

- `~/.oocode/oocode.json` — config principal (modelo, backend, permisos)
- `~/.oocode/workspace/<agent>/OOCODE.md` — instrucciones por agente
- `.claude/settings.json` — permisos y hooks de Claude Code (este repo)
- `config/` — paquete de configuración (punto de entrada `config/__init__.py` re-exporta `OOConfig`, `AgentDef`, `DEFAULT_CONFIG`, `CONFIG_DIR`, … → `import config` no cambia). `config/constants.py` (rutas/VERSION), `config/defaults.py` (ensambla `DEFAULT_CONFIG`), `config/blocks/<bloque>.py` (un fragmento `DEFAULTS` por bloque del JSON), `config/model.py` (`OOConfig` con `load()`/`save()`)

### Arranque, agentes, workspaces y memoria

**Flujo de arranque (`oocode.py:main`):**

1. **Selección de agente.** Sin `--agent`, se usa el agente por defecto `main` (`DEFAULT_AGENT_ID = "main"` en `config/constants.py`; `OOConfig.load(agent_id=None)` cae a él en `model.py:460`). `--agent <id>` carga otro agente definido en `oocode.json`.
2. **Workspaces.** `_ensure_all_workspaces(config)` crea (si faltan) los workspaces de **todos** los agentes; el workspace del agente activo se inicializa con output. Cada workspace vive en `~/.oocode/workspace/<agent>/` y contiene 7 ficheros (`WORKSPACE_FILES` en `workspace/manager.py`): `IDENTITY.md`, `SOUL.md`, `USER.md`, `AGENTS.md`, `HEARTBEAT.md`, `TOOLS.md`, `MEMORY.md`. **Estos ficheros son la identidad/continuidad del agente, NO código del proyecto.**
3. **Directorio de proyecto.** `project_dir = cwd` (o el argumento posicional `[dir]`, que hace `os.chdir`). Es el PWD donde arranca OOCode y donde se busca `OOCODE.md`. **Separado del workspace de identidad** — `bash`/`python_exec`/`workspace_remember` se ejecutan aquí (también para los subagentes, ver más abajo).
4. **Trust check de OOCODE.md.** Si no existe `OOCODE.md` en `project_dir` (y no es `~/.oocode`), se pregunta al usuario si crearlo. Al aceptar, `_cmd_init` (`ui/commands.py`) analiza el proyecto (lenguaje, estructura, comandos, git) y genera un `OOCODE.md` — el equivalente OOCode de `CLAUDE.md`. Se carga como sección "## Instrucciones del proyecto" del system prompt vía `config.load_oocode_md()`.

**Carga de ficheros del workspace al system prompt — modos `mini` (default) vs `full`:** el system prompt NO carga los 7 ficheros enteros cada turno. `_system_prompt` ramifica por `rt.ctx_mode` (default `"mini"`, configurable con `/ctx`):

| Modo | Tokens aprox. | Qué carga (`workspace/manager.py`) |
|------|---------------|-------------------------------------|
| `mini` (default) | ~150 | `load_mini_context()`: **resumen** de `IDENTITY.md` (Rol/Vibe), `SOUL.md` (1ª lista numerada → "## Comportamiento"), `USER.md` (Llamado/Idioma) + bloques de memoria (`MEMORY.md` "Memoria clave" + `memory/` "Sesión de hoy"). **NO** carga `AGENTS.md`, `HEARTBEAT.md` ni `TOOLS.md`. |
| `full` (`/ctx full`) | ~800 | `load_full_context()`: **todos** los `WORKSPACE_FILES` completos + 2 ficheros de memoria diaria recientes. |

Los 7 ficheros siempre existen y son editables por el usuario; en `mini` solo alimentan el prompt los 3 de persona (parcialmente) + memoria. `AGENTS.md`/`HEARTBEAT.md`/`TOOLS.md` son ficheros de referencia (`REFERENCE_FILES`) que el agente consulta bajo demanda o en `full`.

**Capa de personalización del usuario (v0.4.3):** modelo en capas — **código = base invariable** (disciplina/seguridad de tools en `SYSTEM_RULES` + enforcement en `tools/bash.py`); **ficheros = personalización por-agente encima**. `load_mini_context()` carga la sección **`## Notas`** de `TOOLS.md` (preferencias de uso de herramientas) y `AGENTS.md` (preferencias de delegación) si el usuario la ha rellenado — los placeholders de plantilla se filtran (`_extract_section`, acotado a 1500 chars), así que es **coste cero hasta que el usuario personaliza**. Esto permite ajustar agentes y usos de tools SIN editar código ni `SYSTEM_RULES`. El roster de agentes disponibles sigue generándose dinámicamente en `_system_prompt` (lee el `Rol` de cada `IDENTITY.md`, siempre al día). Las plantillas en `workspace/templates/` son la fuente real de los ficheros nuevos; los generadores `_agents()`/`_tools()` (`workspace/manager.py`) son el fallback.

**Dos sistemas de memoria (no confundir) — ambos usan los nombres `memory/` y `MEMORY.md`:**

| Sistema | Ubicación | Escritura | Lectura |
|---------|-----------|-----------|---------|
| **Memoria del workspace** | `~/.oocode/workspace/<agent>/memory/YYYY-MM-DD.md` (diario) + `~/.oocode/workspace/<agent>/MEMORY.md` (largo plazo) | `WorkspaceManager.write_daily_memory()`, tool `workspace_remember` | `load_mini_context()` (bloques "Memoria clave" / "Sesión de hoy") |
| **Memoria semántica** | `~/.oocode/memory/<agent>/*.md` + `MEMORY.md` índice + `*.emb.json` embeddings | tool `mem_save` | `MemorySystem.context_snippet()` (recuperación por embeddings, top-K por turno) |

La memoria semántica (`MemorySystem`, `agent/memory.py`) está separada por agente (`MEMORY_DIR / config.agent_id`) para no mezclar memorias entre agentes. La del workspace es la "continuidad" descrita en `AGENTS.md` del propio agente.

**Subagentes — mismo proyecto, su propio workspace (v0.4.3):** un subagente carga SU workspace de identidad (`~/.oocode/workspace/<sub_id>/`) pero ejecuta las tools en el `project_dir` del **padre** (heredado en `sub_config.project_dir`). `SubAgentRunner._start_background_session` construye el registry con `build_registry_fn(os.path.expanduser(sub_config.project_dir or sub_config.workspace), …)` — antes pasaba el workspace de identidad con `~` literal y `bash` fallaba con `No such file or directory: '~/.oocode/workspace/<id>'`. Defensa adicional en `tools/bash.py`: `workdir` se normaliza (`expanduser`/`expandvars`) y cae a `None` si no existe.

**Bloque `api` en oocode.json (nuevo en v0.4.0):** bloque unificado backend + servidor. Internamente, el campo `host` alimenta tanto `config.ollama_host` (backend Ollama) como `config.api_base_url` (backend OpenAI). Los atributos Python conservan los nombres `ollama_*` / `api_base_url` (sin bloque `ollama` separado en el JSON).

| Campo JSON | Default | Descripción |
|------------|---------|-------------|
| `type` | `"ollama"` | Backend LLM: `"ollama"` \| `"openai"` \| `"anthropic"` |
| `key` | `""` | API key (OpenAI / Anthropic; vacío para Ollama) |
| `host` | `"http://localhost:11434"` | URL del servidor. Ollama → host; OpenAI → baseUrl; Anthropic → ignorado |
| `extraHosts` | `[]` | (solo Ollama) hosts adicionales para subagentes (round-robin) |
| `embedHost` | `""` | (solo Ollama) host dedicado para embeddings (vacío = `host`) |
| `subagentRouting` | `"round-robin"` | (solo Ollama) `"round-robin"` \| `"primary-only"` |
| `ollamaRetryCount` | `2` | (solo Ollama) reintentos en timeout |
| `ollamaRetryDelay` | `3.0` | (solo Ollama) delay base entre reintentos (s) |

**Embeddings siempre vía Ollama (v0.4.1):** `EmbeddingClient` envuelve `ollama.Client`, así que las embeddings (memoria + RAG) usan el protocolo Ollama sea cual sea el backend de chat. `config.effective_embed_host` lo resuelve: con `api.type != "ollama"` y sin `embedHost`, cae a `localhost:11434` (no a `api.host`, que apunta al servidor OpenAI/Anthropic). Todo `EmbeddingClient` del repo debe usar `effective_embed_host`, nunca `ollama_host` crudo.

**Comandos conscientes del backend (v0.4.1):** `/doctor`, `--doctor`, doctor WebUI (`_doctor_llm_backend_checks`), `/config`, `/settings`, `/model`, `/models` ramifican según `config.api_type` y no sondean Ollama cuando el backend es openai/anthropic.

**Flujo de conversación agnóstico de dominio (v0.4.2):** OOCode es multi-agente y el agente puede ser de cualquier dominio (oficina/seguridad/web/datos/IoT), no solo código. `SYSTEM_RULES` (`agent/loop_helpers.py`) tiene un núcleo neutral (Clasifica→Reúne→Actúa→Verifica→Finaliza) y la disciplina de código en un bloque condicional **"Cuando trabajes con código"**. Los hints de `_turn_guidance` no asumen edición de código: el aviso de tests (#14) se gatea por extensión de fichero (`_modify_touches_code`), no por tipo de agente — **importante:** `build_registry` da TODAS las tools nativas a todos los agentes, así que el gating por presencia de tool NO distingue agente de código (sí sirve para git/docker/lsp, que pueden faltar y ya se filtran en `filter_system_rules`). `/agent new` clasifica el dominio (`_classify_agent_domain` + `_AGENT_DOMAIN_PROFILES` en `ui/commands.py`) y personaliza la persona (prompt LLM consciente del dominio + fallback `_write_domain_soul` sin LLM). Las tools de orquestación (`_ORCHESTRATION_TOOLS`) fuerzan modo secuencial en `_turn_dispatch_tools`.

**Comunicación continua (narración) — política (2026-06):** el agente debe narrar su trabajo de forma **concisa pero continua** (resumen de apertura → diálogo durante exploración/acción → resumen estructurado al cerrar), nunca trabajar en silencio; el ahorro de tokens va en floritura, NO en informar. Vive en 3 capas que deben mantenerse coherentes: (1) **persona** — bloque "## Comportamiento" del system prompt, extraído por `workspace/manager.py:_extract_soul_principles` de la 1ª lista numerada de `SOUL.md` + el `behavior_block` fallback (cuando SOUL no tiene lista numerada, p.ej. `coding`) + Vibe de `IDENTITY.md`; (2) **reglas** — bloque "Comunicación" de `SYSTEM_RULES` (`agent/loop_helpers.py`), siempre presente y sin refs a tools (sobrevive a `filter_system_rules`); (3) **backstop reactivo** — hint #15 de `_turn_guidance` (≥2 tools sin texto). El preflight enlatado (`_pick_preflight_phrase`) se mantiene como feedback instantáneo mientras el modelo piensa; el resumen real de apertura lo da el modelo vía la regla (1). `workspace/templates/SOUL.md` (persona del `main`) **sí se edita** para esta política — la antigua nota "intocable / no expliques lo que vas a hacer" queda revocada a propósito.

**WebUI paridad con TUI (v0.4.2):** una sola status bar (`tui-statusbar`; eliminada la `tui-bottom-bar` `bb-*` duplicada). El `case 'status'` solo actualiza la barra principal si NO es de subagente. Los hooks de subagente en el dispatch paralelo reinyectan `set_hook_print_fn(self._print)` por hilo worker (`threading.local` no se hereda). Las file-cards de descarga (`_show_tool_block`) solo se emiten para entregables ofimáticos/PDF, no para código ni temporales.

**WebUI flujo de conversación vs status (rev 2026-06-04, `webui/page_chat.py` + `agent/loop.py`):** principio rector — **lo que es estado va en la status; lo que es contenido va en la conversación**. (1) **Orden DOM** de `.tui-chat-wrap` (flex column): `Pensando → prompt → team-bar → #tui-statusbar → #tui-sb2-mcp → #tui-sb2-lsp` (la status bar se reubicó bajo el prompt y la team-bar, sobre las filas MCP/LSP; paridad con el toolbar TUI). (2) **`renderTeamBar` = solo cabecera de una línea** `📋 Main 💬 ✓ 💻 Sub · N subagente(s)` (`white-space:nowrap`+ellipsis); se REVIRTIÓ el detalle multilínea por subagente (eliminados `_fmtElapsed` y CSS `team-line`/`team-task`/`team-meta`). El detalle largo (tarea) se siembra en el bloque del subagente EN LA CONVERSACIÓN vía `_seedSubagentTask(emoji,name,task)` desde `case 'subagent_start'` (idempotente con `entry._taskSeeded`; clave `emoji|name` coincide porque el sub carga la config del agente destino). (3) **`spawn_subagent` NO emite `tool_start` de agente principal** (display="Subagent") — guard `name != "spawn_subagent"` en `_show_tool_running_header` + exclusión en el path paralelo; antes creaba un tool block que nunca recibía `tool_done` (se convierte en `subagent_done`) y dejaba textos del sub fuera de su bloque. (4) **La barra "Pensando" no muestra títulos de tools** — quitado `_setThinkingLabel('◐ '+tool)` del `case 'tool_start'`; el tool va solo a `appendToolStart` (conversación). (5) Limpieza de la rama muerta del `case 'preflight'` (IDs inexistentes `tui-thinking`/`.tui-thinking-label`). test_76 reescrito.

**Historial de prompt y sesiones compartidos TUI ↔ WebUI (2026-06-04):** (1) **Input del prompt** (recall flecha arriba) en `~/.oocode/history`: el TUI usa `prompt_toolkit FileHistory`; el WebUI escribe/lee el MISMO fichero con los helpers compartidos `append_input_history`/`load_input_history` (`agent/session.py`) que replican el formato exacto (`\n# ts\n` + `+linea` por cada línea → multilínea compatible). El WebUI guarda **solo input del usuario** (no respuestas; quitado el `+{slash_resp}`), en `/api/chat/send` y `/api/chat/send_sync`, y lo carga al conectar vía `GET /api/chat/input_history` → `loadInputHistory()` puebla `_inputHistory` (antes era solo en memoria de la pestaña). (2) **Sesiones** (conversación): JSONL `~/.oocode/sessions/<agent_id>/` ya era común (`SessionManager`); el WebUI ahora **restaura** de verdad — `POST /api/chat/load_session` y el slash `/session <id>` (`_handle_webui_slash`) reusan `AgentLoop.restore_session` + repueblan `sess["history"]`; el botón *Cargar* llama al endpoint y re-renderiza (`loadHistory`), y `/session` recarga al `done` vía flag `_pendingSessionReload`. test_78.

**Anti-bucle de ediciones (v0.4.2):** `agent/loop.py` mantiene `_failed_modify_by_path` (dict por fichero/turno) alimentado por los 3 caminos de fallo de modificación — PRE-EDIT FALLIDO (`_precheck_tool_call`), regex/bulk sin coincidencias y DUPLICADO BLOQUEADO (todas las `_WRITE_TOOLS`). `_modify_failure_guidance(path)` escala: 1.º leer · 2.º inyecta contenido real vía `_recovery_snippet` (ground truth, "puede estar ya aplicado") · 3.º parada en seco. Resetea por fichero en cada modificación exitosa y en `_turn_reset_state`. Helper defensivo (`getattr` lazy) porque los fixtures de test no inicializan el dict.

**Timeout de subagentes por inactividad (v0.4.3):** el watchdog de `spawn_background` (`agent/subagent.py`) mide tiempo SIN progreso, no tiempo total. Antes era `ev.wait(secs)` one-shot (mataba al alcanzar `secs` aunque progresara); ahora es un bucle `while not ev.wait(poll)` que mata solo si `now - sub.last_activity >= secs`. `ActiveSubAgent` tiene `last_activity` + `heartbeat()`. El `AgentLoop` llama `self._subagent_heartbeat()` (no-op si no es subagente; usa `_sub_stats_ref`) en 3 puntos de progreso del bucle `run()`: inicio de cada iteración, tras `_turn_llm_call` (respuesta del LLM), e inicio de `_execute_tool` (tras el precheck). Así `defaultTimeout`/`timeout_seconds` = "máx. s SIN progreso por paso". `timeout_seconds=0` → sin watchdog. test_subagent_integration `TestInactivityWatchdog`.

**Recuperar el último mensaje tras compactar (v0.4.3, solo TUI):** `_show_compact_reset` (`ui/loop_tui.py`) limpia el área visible; tras el banner + lista de ficheros, re-imprime `self._last_response` (sigue vivo en contexto; lo fija `run()` justo antes de `_maybe_precompact_idle`) como `Padding(Markdown, (0,0,0,2))` bajo el aviso "último mensaje del agente (antes de compactar)". Antes el resumen final del agente (p.ej. preguntando si continuar) se perdía y el usuario respondía a ciegas. El WebUI no lo necesita (conserva la conversación en el DOM). test_13 `TestShowCompactReset`.

**Extensión VIM 3.1 — streaming real (v0.4.3):** `extensions/vim/`. El flujo anterior abría un SSE persistente y enviaba por `send_sync`, pero acababan en sesiones Flask distintas (un curl SSE persistente nunca vuelca el cookie jar). Fix: `s:ensure_session()` (GET `/api/chat/status` que COMPLETA) fija la cookie ANTES del SSE; el envío pasa a `POST /api/chat/send` fire-and-forget y todo llega por el stream. Paridad de eventos (`status`/`preflight`/`plan_progress`/`subagent_start`+`done` con `│`/`embed_flash`). Nuevos `:OOCodeKill`/`:OOCodeElevated`, guard de turno y watchdog (`g:oocode_turn_timeout`). `g:oocode_stream=0` → fallback `send_sync` sin SSE. Ver `doc/21_extensions.md`.

**Campos clave del bloque `subagents`:**

| Campo JSON | Default | Descripción |
|------------|---------|-------------|
| `autoContMax` | 16 | `auto_continue_max` para subagentes (> 8 del agente principal, evita paradas prematuras) |
| `inferenceTimeout` | 0 | Timeout de inferencia para subagentes en segundos (0 = hereda `fallback.timeoutSeconds`). Desde v0.4.1 se aplica con máxima prioridad vía `inference_timeout_override` (override > per-model > fallback), independiente de si hay fallback configurado |
| `defaultTimeout` | 0 | Timeout **por paso/petición al LLM** (inactividad), NO por tiempo total: watchdog que mata el subagente solo si un paso pasa N s sin progreso. El AgentLoop emite `sub.heartbeat()` al iniciar cada iteración, al recibir respuesta del LLM y tras cada tool (`_subagent_heartbeat`). Un subagente que avanza no se detiene aunque la tarea total dure más; solo muere si una petición/tool se cuelga. 0 = sin watchdog; usado si el LLM no especifica `timeout_seconds` |

---

## Servidores MCP

Los MCP servers siguen el patrón: `_TOOLS` (lista de schemas), `_TOOL_FNS` (dict name→función), `_PROMPTS`, `_RESOURCES`. El servidor escucha en stdio y el bucle principal en `main()` despacha según `method`:

- `tools/list` → devuelve `_TOOLS`
- `tools/call` → llama `_TOOL_FNS[name](args)`
- `prompts/list` / `prompts/get` → gestión de prompts
- `resources/list` / `resources/read` → recursos estáticos

**Servidores bundled (8)** — activos por defecto: `oocode-assistant`, `devops-assistant`, `system-assistant`. Inactivos por defecto: `database-assistant`, `home-office-assistant`, `security-assistant`, `iot-assistant`, `http-client-assistant`.

Los servidores `oocode-assistant`, `devops-assistant`, `database-assistant` y `system-assistant` registran sus tools **sin prefijo** (ej. `git_status` en lugar de `mcp_devops_git_status`) para máxima usabilidad con el LLM.

### devops_assistant.py — estructura

Git (16), Docker/Compose (23), Debug strace/gdb/pdb/valgrind (4), Build make/run_script/format_code/mypy/python_exec/pip/npm (7), Archive tar/zip (3), FS-mutations chmod/chown/mv/cp/rm/mkdir/touch/symlink/readlink (13). Total: 66 tools.

### database_assistant.py — estructura

SQLite stdlib (sqlite_query, sqlite_schema, sqlite_tables, sqlite_export/import, sqlite_insert/update/delete, sqlite_vacuum, sqlite_create_table, sqlite_indices, sqlite_explain), PostgreSQL opcional (pg_query, pg_schema, pg_explain), MySQL opcional (mysql_query, mysql_schema), utilidades cross-DB (csv_to_sqlite, db_stats, sql_format). Total: 20 tools.

### http_client_assistant.py — estructura

http_request, http_get, http_headers, http_auth (bearer/basic/oauth2), http_upload (multipart), response_diff, openapi_validate, curl_import, websocket_send, sse_listen, mock_server_start, mock_server_stop, http_health_check, graphql_query, jwt_decode, http_batch, http_history. Total: 17 tools.

### home_office_assistant.py — estructura interna

```
_tool_doc_create()              — Word/Excel/PPT desde cero con content_blocks (O365 nativo)
_build_word_chart_xml()         — OOXML DrawingML para gráficas nativas en Word
_embed_word_chart_native()      — Inserta chart XML como Part en python-docx
_tool_doc_insert_chart_native() — Tool `insert_chart`: única gráfica Word OOXML nativa
_tool_doc_fill_template()       — docxtpl/Jinja2 para plantillas corporativas
_apply_o365_styles_to_new_doc() — Estilos Calibri/Calibri Light en Word nuevo
_md_fill_para_inline()          — Formato inline (**negrita**/*cursiva*/`code`) en runs nativos
_render_native_paragraphs()     — Vuelca texto como párrafos nativos (sin conversor markdown)
```

El MCP genera **solo contenido O365 nativo** — no convierte markdown→documento ni gráficas PNG matplotlib. Las gráficas Word son OOXML DrawingML editables vía la tool única `insert_chart` (bar/column/line/area/pie/doughnut/scatter/stacked/radar).

Los content_blocks de Word admiten: `title`, `heading`, `paragraph`, `bullet_list`, `numbered_list`, `checklist`, `table`, `chart`, `image`, `code_block`, `markdown` (texto plano nativo), `pagebreak`, `toc`, `signature_block`, `horizontal_rule`, `callout`.

---

## Tests

Los tests en `tests/` no requieren LLM, Ollama, SMTP ni servidor externo. Usan mocks mínimos y ficheros temporales.

Ficheros de test relevantes por módulo:
- `tests/test_71_api_backends.py` — api/ base, ollama, openai, anthropic, build_client, registry.tool_schemas
- `tests/test_68_devops_mcp.py` — schemas, git, docker (mocked), fs-mutations, build, archive
- `tests/test_69_database_mcp.py` — SQLite CRUD, export/import, pg/mysql sin deps, sql_format
- `tests/test_70_http_client_mcp.py` — 123 tests: http_request, response_diff, openapi_validate, curl_import, mock_server, jwt_decode, etc.
- `tests/test_45_home_office_mcp.py` — schemas, configuración, tools sin dependencias externas (66 tools)
- `tests/test_59_home_office_diagrams.py` — preservación de estilos en `doc_fill_template`

Al añadir tools nuevas: actualizar `test_tool_count` en `test_45_home_office_mcp.py`, y los conteos en `test_16`, `test_49`, `test_50`, `test_51` (que suman oocode + devops).

---

## Dependencias Office

```bash
# Verificar instalación de librerías Office
python -c "import docx, openpyxl, pptx, matplotlib, docxtpl; print('OK')"

# Versiones mínimas requeridas
# python-docx >= 1.0   (OOXML nativo, python-pptx >= 1.0, openpyxl >= 3.1)
```

## Dependencias opcionales por backend

```bash
# OpenAI-compatible (httpx ya incluido en requirements)
pip install httpx

# Anthropic
pip install anthropic

# WebSocket (para http_client_assistant / websocket_send)
pip install websocket-client
```
