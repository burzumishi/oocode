# OOCode v0.3.6 — Asistente de programación 100% local

Asistente de programación local para la terminal, inspirado en Claude Code pero funcionando **100% con [Ollama](https://ollama.com)**. Sin API keys, sin suscripciones, sin enviar tu código a servidores externos.

## ¿Por qué OOCode?

| | OOCode | Claude Code |
|---|---|---|
| **Coste** | Gratis — corres tu propio modelo | $20/mes (Max) o pay-per-token |
| **Privacidad** | 100% local, tu código no sale del equipo | El código se envía a servidores Anthropic |
| **Rate limits** | Sin límites — tantas peticiones como quieras | Límites por nivel de suscripción |
| **Modelos** | Cualquier modelo Ollama (Qwen, DeepSeek, Llama…) | Sólo Claude |
| **Offline** | Funciona sin internet | Requiere conexión |
| **Plugins** | Sistema extensible con hooks Python | No extensible |
| **Memoria semántica** | Persistente entre sesiones con embeddings locales | Requiere Pro/Max |

---

## Características principales

- **100% local** — todo corre en tu máquina, nada sale a internet salvo búsquedas web explícitas
- **TUI avanzada** — live block con preview de herramientas, auto-header para ediciones, spinner pulsante, display compacto de resultados, task progress panel con planes multi-tarea
- **WebUI Flask** *(beta)* — interfaz web con SSE, Markdown, archivos adjuntos, panel MCP/LSP y modo "Pensando" *(funcionalidad en desarrollo, el TUI es la interfaz de referencia)*
- **Tool calling nativo** — el modelo llama a herramientas reales: bash, ficheros, web, git, docker…
- **103+ tools MCP** — 5 servidores MCP bundled: oocode-assistant, system-assistant, home-office, security, IoT
- **5 agentes especializados** — main, coding, home_office, reasoning, webcrawler; cada uno con workspace propio
- **Multi-servidor Ollama** — distribuye subagentes y embeddings entre varios servidores Ollama en round-robin
- **LSP integration** — 30+ lenguajes con auto-arranque de servidores por extensión de fichero
- **RAG workspace** — indexa el proyecto con embeddings y auto-inyecta código relevante en cada turno
- **14 hooks built-in** — lint, lsp, backup, test, diff, verify, git_push_guard, security_audit_log y más
- **Memoria semántica persistente** — ficheros `.md` en `~/.oocode/workspace/<agente>/` con búsqueda por embeddings
- **Compactación inteligente de contexto** — resumen automático con LLM cuando el contexto se llena
- **Auto-continuación** — relanza el agente automáticamente en tareas largas (configurable hasta 16 veces)
- **Subagentes con paralelismo real** — cada subagente puede ejecutar en una GPU distinta (round-robin de hosts)
- **Extensiones VIM y VSCode** — panel lateral con streaming SSE, comandos y mappings de teclado
- **Catálogo MCP externo** — gestión de servidores MCP de terceros con `/mcp catalog/install/check`

---

## Requisitos

- Python 3.10+
- [Ollama](https://ollama.com) instalado y ejecutándose
- Al menos un modelo con soporte de tool calling

```bash
# Modelos recomendados
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
pip install python-docx python-pptx openpyxl matplotlib pillow docxtpl
# Verificar:
python -c "import docx, openpyxl, pptx, matplotlib; print('OK')"
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

## Multi-servidor Ollama

OOCode puede distribuir subagentes y embeddings entre varios servidores Ollama. Útil cuando tienes varias GPUs, varias máquinas en red local, o quieres dedicar un servidor CPU-only a los embeddings.

```json
{
  "ollama": {
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
  "ollama": {
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
    "compactThreshold": 0.85
  }
}
```

---

## Los 5 agentes

| Agente | Emoji | Especialidad | Workspace |
|--------|-------|-------------|-----------|
| `main` | 🤖 | Asistente general, coordina otros agentes | `~/.oocode/workspace/main` |
| `coding` | 💻 | IT, programación, refactorización, LSP | `~/.oocode/workspace/coding` |
| `home_office` | 📋 | Documentación corporativa O365 (Word/Excel/PPT) | `~/.oocode/workspace/home_office` |
| `reasoning` | 🧠 | Razonamiento, coordinación de equipos de agentes | `~/.oocode/workspace/reasoning` |
| `webcrawler` | 🕷️ | Búsqueda web con SearXNG, generación de informes | `~/.oocode/workspace/webcrawler` |

Selección con `--agent <id>` en CLI o `/switch <id>` en el REPL.

---

## WebUI

```bash
# Arrancar WebUI daemon
python oocode.py --webserver start

# Acceder
http://localhost:4000
```

Características: chat con Markdown-to-HTML, archivos adjuntos, panel MCP/LSP status, barra de contexto, modo "Pensando" durante herramientas, temas claro/oscuro, responsive móvil.

API endpoints: `/api/chat/send_sync`, `/api/chat/sse`, `/api/sessions`, `/api/agents`, `/api/status`, `/api/config`.

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

## MCP Servers (5 bundled)

| Servidor | Flag en oocode.json | Tools | Por defecto |
|----------|---------------------|-------|-------------|
| `oocode-assistant` | `oocodeAssistant.enabled` | ~35 tools: git, docker, fs, grep, code_outline, read_sections, affected_files, symbol_lookup | activo |
| `system-assistant` | `systemAssistant.enabled` | systemctl, journalctl, red, disco, paquetes, procesos | activo |
| `home-office-assistant` | `homeOfficeAssistant.enabled` | 77+ tools: doc_create, xlsx_create_report, pptx_create, email_send, calendar_event_add, pdf_extract_text | desactivado |
| `security-assistant` | `securityAssistant.enabled` | 24 tools: nmap_scan, web_scan, ssl_check, hash_crack, xss_test, ctf_decode | desactivado |
| `iot-assistant` | `iotAssistant.enabled` | 25 tools: TAPO, Blink, Alexa, Tuya, Home Assistant, MQTT, ESPHome | desactivado |

Para activar un servidor MCP:
```json
{ "mcp": { "homeOfficeAssistant": { "enabled": true } } }
```

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

### VIM

Instalación con vim-plug:
```vim
Plug 'burzumishi/oocode', { 'rtp': 'extensions/vim' }
```

Comandos principales: `:OOCode <msg>`, `:OOCodeAsk`, `:OOCodeContext`, `:OOCodeSelection`, `:OOCodeExplain`, `:OOCodeReview`, `:OOCodeTUI`, `:OOCodeOpen/Close/Toggle`, `:OOCodeStatus`, `:OOCodeConnect`, `:OOCodeWebUI`, `:OOCodeWebServer`, `:OOCodeNew`, `:OOCodeSwitch <agent>`, `:OOCodeAgents`, `:OOCodeSessions`, `:OOCodeDoctor`, `:OOCodeCmd <slash_cmd>`

Mappings: `<Leader>oa` (ask), `<Leader>oc` (context), `<Leader>os` (selection), `<Leader>ox` (explain), `<Leader>or` (review), `<Leader>ot` (toggle panel), `<Leader>ow` (WebUI), `<Leader>ou` (TUI), `<Leader>on` (new session), `<Leader>ok` (connect)

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
│   ├── hooks.py           # 14 hooks built-in
│   └── ...
│
├── mcp_servers/           # Servidores MCP bundled
│   ├── oocode_assistant.py
│   ├── home_office_assistant.py
│   ├── security_assistant.py
│   ├── iot_assistant.py
│   └── system_assistant.py
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
| `doc/19_webui.md` | WebUI Flask: setup, API REST, SSE, subagentes |
| `doc/20_office_styles.md` | Estilos O365 en documentos Word/Excel/PPT |
| `doc/21_extensions.md` | Extensiones VIM y VSCode |
| `doc/22_mcp_servers.md` | 5 MCP servers bundled + catálogo de servidores externos |
| `doc/23_hooks.md` | Los 14 hooks built-in: configuración y custom hooks |
| `doc/24_tui_display.md` | TUI live block: preview de herramientas, auto-split bullet, static ANSI cache |

---

## Changelog

### v0.3.6 (2026-05-31)

- **TUI refinements** — `_update_live_bullet_cb` muestra la acción de la herramienta activa en el `●` pulsante; `●display(ctx)` como encabezado de tool; `⎿` sin `◐`; resumen compacto normalizado ("Searched for", "lines" en inglés)
- **WebUI print pollution fix** — `_print()` TUI-específicos (preflight/auto-continue/plan/resume/retry) filtrados con `if not _webui_queue`; JS de `thinking` preserva el label preflight
- **WebUI/TUI callbacks** — TUI sin `invalidate()` en callbacks intermedios del live block (blink timer suficiente); status SSE emitido al inicio de turno; file cards unificadas a `.tui-file-card`
- **Tests** — 3932 tests (100% pasando)

### v0.3.5 (2026-05-31)

- **Configuración completa desde oocode.json** — todos los parámetros internos (chunking RAG, caché embeddings, highWater de contexto) son ahora configurables en `~/.oocode/oocode.json`; eliminados todos los valores hardcodeados
- **Display compacto mejorado** — cada fichero en una línea separada con `│` (U+2502) y `⎿` en el último elemento; símbolo correcto `↻` para compactación en la barra de estado
- **Limpieza de código** — eliminados duplicados funcionales (`_fmt_tokens`, `_progress_bar`, `chunk_with_metadata` standalone); eliminadas 5 entradas no-op en `_TOOL_ALIASES`; unificadas 6 sets de write-tools en `_is_modify_tool()`; eliminado tracking dual `_task_modified_files`
- **Correcciones de robustez** — sincronizado `_RICH_TAG_RE` entre `loop.py` y `app.py`; corregido prefijo `[caché]` visible al LLM; eliminado bloque unreachable en el dispatch de tools; eliminado segundo `keep_alive` pop en `_chat_kwargs`

### v0.3.4 (2026-05-30)

- TUI Claude Code style: `●` sin sangría, `⎿` sin `◐`, resumen compacto
- WebUI + TUI fixes: collapse via `.expanded`, file cards unificadas, status al inicio de turno
- Home Office v5: `doc_create` + `template_path`, checklist/callout/highlight/toc en Word
- Home Office OOXML refactor: gráficas OOXML nativas (sin PNG), diagramas bar/pie/line
- External MCP support: `mcp_manager.py` + `catalog.json`, hot-add sin reiniciar
- WebUI refactorizada en 13 módulos Blueprint

---

## Licencia

MIT — libre para uso personal y comercial.
