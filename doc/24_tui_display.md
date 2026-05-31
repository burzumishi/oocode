# 24 — TUI Live Block y Display de Herramientas

## Visión general

El TUI de OOCode muestra un **live block** al final del área de conversación mientras el agente ejecuta herramientas. El bloque es dinámico: se actualiza en tiempo real con el nombre de la tool activa, el fichero o comando inline, y hasta 4 líneas de contexto (diff, "Running…"), y desaparece limpiamente al completarse la tarea, dejando solo el resumen compacto `⎿`.

```
  ● Voy a revisar el código y corregir los errores de compilación.

  ● Updating act_comm.c:
  │ ◐ Replace: (act_comm.c)
  │ ◐ Bash: $ grep -rn "gethostname" src/
  │   Running…
  │ ◐ Read: (doc/api.md)
  ⎿ Used 3 tools (ctrl+o to expand)
```

---

## Anatomía del live block

```
  ●  Texto del agente (aparece cuando empieza el turno con tools)
  │  ◐ ToolAnterior: (path/cmd)   ← tool ya completada (greyed, hasta 3)
  │  ◐ NombreTool: (path)         ← tool activa — path/cmd inline
  │     Running…                  ← preview debajo: solo visible mientras corre
  ⎿  Used N tools (ctrl+o to expand)
```

**Máximo 8 líneas `│`** antes del `⎿`. El budget se distribuye: N tools completadas (hasta 3) + 1 tool activa + líneas de preview hasta completar 8.

### Alineación de columnas

Todos los marcadores se alinean en la columna 2 (0-indexed):

| Marcador | Posición | Estilo |
|----------|----------|--------|
| `●` | col 2 | bold + color de acento pulsante |
| `\|` | col 2 | dim — guía visual mientras hay tool activa |
| `⎿` | col 2 | dim — resumen compacto final |

La línea `|  ◐ Tool:` usa 2 espacios entre `|` y `◐`; las líneas de preview usan 5 espacios.

---

## Comportamiento del ● (bullet pulsante)

El `●` cicla entre tonos verde/cyan con una transición suave cada 350 ms mientras el live block está activo:

```
green → cyan → bright-cyan → cyan → green → dim-green → green → cyan → …
```

Al completarse el turno, el `●` final se fija en el color de acento del agente (configurable en `oocode.json` → `accentColor`).

Mientras una tool ejecuta, el `●` cambia temporalmente a un verbo en gerundio:

```
  ● Reading agent/loop.py…  (ctrl+o to expand)
  ● Running $ grep -rn…  (ctrl+o to expand)
  ● Searching for "_live_block"…  (ctrl+o to expand)
```

Al terminar la tool, el `●` recupera el texto original del agente.

---

## Preview de herramientas (`|  ◐ tool:` + líneas de contexto)

Cuando una tool empieza, el live block muestra:

```
  |  ◐ NombreTool: contexto extraído de los args
  |     líneas de preview debajo (solo para bash: Running…)
```

### Nombre de la herramienta

El nombre corto se obtiene de `_TOOL_DISPLAY_NAMES` en `agent/loop.py`:

| Tool interna | Nombre mostrado |
|---|---|
| `bash` | `Bash` |
| `read_file` | `Read` |
| `edit_file` | `Update` |
| `grep_code` | `Search` |
| `smart_replace` | `Replace` |
| `write_file` | `Write` |
| `python_exec` | `Python` |
| `code_search` | `CodeSearch` |
| `find_file` | `Find` |

### Líneas de preview (contexto de args)

La función `_make_tool_preview(name, args)` en `agent/loop_helpers.py` devuelve hasta 5 elementos:
- **Elemento [0]**: se muestra **inline** con el nombre de la tool → `◐ Tool: <first>`
- **Elementos [1:]**: se muestran **debajo** de la línea de tool (diff, "Running…", etc.)

| Tool | Inline [0] | Debajo [1:] |
|------|-----------|-------------|
| `bash` | `$ comando` (primera línea) | segunda línea cmd + `Running…` |
| `read_file` | `(path)` o `(path:offset+limit)` | — |
| `read_files` | `(path1)` | `(path2)`, `(path3)`, ... |
| `write_file` | `(path)` | primeras 4 líneas del contenido nuevo |
| `edit_file` / `smart_replace` / `regex_replace` | `(path)` | — (el diff coloreado se muestra tras la ejecución) |
| `edit_files` | `(path1)` | `(path2)`, `(path3)` |
| `bulk_replace` / `patch_apply` | `(path)` | — |
| `grep_code` / `grep_file` | `"patrón"  in dir` | — |
| `multi_grep` | `"patrón1"` | `"patrón2"`, `"patrón3"` |
| `code_search` | `"query"` | — |
| `find_file` / `find_files` | `nombre  in dir` | — |
| `python_exec` | primera línea del código | siguientes líneas (hasta 3) |
| `lsp_diagnostics` / `lint_file` | ruta del fichero | — |
| `git_commit` / `git_log` | mensaje o ruta | — |

### Tools completadas con contexto

Cuando una tool termina, `_update_live_tools()` captura `tool_label + preview[0]` en el historial de completed_tools. Así las líneas grises de tools pasadas muestran también el path o comando:

```
  │ ◐ Write: (agent/loop.py)      ← ya completada — con path
  │ ◐ Bash: $ pytest tests/ -q    ← ya completada — con comando
  │ ◐ Read: (config.py)           ← tool activa actual
  │   25 líneas de contenido…
```

### Visibilidad temporal

Las líneas de preview son **solo visibles mientras la tool está corriendo**. Al completarse:
1. `_update_live_tools_cb(count)` captura `label + preview[0]` en `completed_tools`, incrementa el contador y limpia `_live_block_preview = []`
2. La línea `◐ Tool:` activa pasa a la lista de completadas (greyed)
3. El `⎿ Used N tools` se actualiza

El preview detallado (líneas debajo) **nunca aparece en el historial estático** de la conversación.

---

## Auto-split bullet para write tools

### Problema

Cuando el modelo emite un planning text general ("Voy a refactorizar el módulo completo...") seguido inmediatamente de write tools (`edit_file`, `smart_replace`…), las ediciones quedaban "enterradas" bajo el mensaje de planificación sin contexto visual de qué fichero se estaba modificando:

```
  ● Voy a continuar con la refactorización completa. Primero necesito revisar...
  |  ◐ Replace:
  |     act_comm.c
  ⎿ Used 3 tools (ctrl+o to expand)
```

### Solución: auto-split

Si el planning text tiene **más de 60 caracteres** y **no menciona explícitamente** el fichero objetivo de las write tools, el sistema:

1. Imprime el planning text como `●` estático (no pulsante, sin live block)
2. Extrae los nombres de fichero de los args de las write tools
3. Genera automáticamente un nuevo `●` con el header del fichero:

```
  ● Voy a continuar con la refactorización completa. Primero necesito revisar...

  ● Updating act_comm.c:
  |  ◐ Replace:
  |     act_comm.c
  ⎿ Updated act_comm.c (ctrl+o to expand)
```

### Formato del header auto-generado

| Ficheros modificados | Header generado |
|---|---|
| 1 fichero | `Updating act_comm.c:` |
| 2 ficheros | `Updating act_comm.c, imc.c:` |
| 3+ ficheros | `Updating act_comm.c (+2 more):` |

### Condición de activación

El split **solo** ocurre cuando:
- `_start_live_block_cb` está activo (modo TUI — no REPL, no WebUI, no subagente)
- El texto del modelo es plain text (no lista Markdown, no heading)
- `len(first_line) > 60`
- Las write tools del batch tienen path en sus args
- El texto no menciona el nombre de ningún fichero objetivo

Si el modelo ya anuncia explícitamente el fichero ("Corrigiendo gethostname en act_comm.c:"), el comportamiento es el original: el texto del modelo se usa directamente como bullet del live block.

---

## Arquitectura interna

### Callbacks de AgentLoop → OOCodeApp

Todos los callbacks se inicializan a `None` en `AgentLoop.__init__` y solo se asignan cuando `OOCodeApp` (modo TUI interactivo) wirea el agente. En modo REPL, WebUI y subagentes permanecen `None`.

```python
# En AgentLoop.__init__:
self._start_live_block_cb:          Optional[Callable] = None
self._update_live_tool_start_cb:    Optional[Callable] = None  # atómico: label+preview
self._update_live_current_tool_cb:  Optional[Callable] = None  # compat
self._update_live_preview_cb:       Optional[Callable] = None  # compat
self._update_live_bullet_cb:        Optional[Callable] = None
self._update_live_tools_cb:         Optional[Callable] = None
self._flush_live_block_cb:          Optional[Callable] = None
```

```python
# En OOCodeApp.__init__ (ui/app.py):
agent_loop._start_live_block_cb         = self._start_live_block
agent_loop._update_live_tool_start_cb   = self._update_live_tool_start   # atomic
agent_loop._update_live_current_tool_cb = self._update_live_current_tool # compat
agent_loop._update_live_preview_cb      = self._update_live_preview      # compat
agent_loop._update_live_bullet_cb       = self._update_live_bullet
agent_loop._update_live_tools_cb        = self._update_live_tools
agent_loop._flush_live_block_cb         = self._flush_live_block
```

### Actualización atómica (`_update_live_tool_start`)

Para evitar un **double-flash** visible al inicio de cada tool (dos renders intermedios: uno al limpiar el estado anterior y otro al setear el nuevo), la actualización de label + preview se hace en **una sola operación atómica** bajo el lock:

```python
def _update_live_tool_start(self, tool_label: str, preview: list) -> None:
    with self._lock:
        self._live_block_current_tool = tool_label
        self._live_block_preview = [str(l) for l in preview[:4]]
        self._output_cache_key += 1
    self._app.invalidate()
```

Un solo `invalidate()` → un solo frame re-renderizado.

### Estado del live block en OOCodeApp

```python
self._live_block_active:       bool       # True mientras el bloque está abierto
self._live_block_bullet:       str        # texto original del agente en ●
self._live_block_action:       str        # sobreescribe ● mientras tool corre
self._live_block_body:         list[str]  # output acumulado (diffs de write tools)
self._live_block_tool_n:       int        # contador de tools completadas
self._live_block_current_tool: str        # "Tool:" mostrado en |  ◐
self._live_block_preview:      list[str]  # 1-4 líneas de preview (solo mientras corre)
self._live_pulse_idx:          int        # índice de color para animación
```

### Static ANSI cache

El área de conversación acumula ~80 KB de texto ANSI (historial). Parsear ese string con `ANSI()` de prompt_toolkit en cada tick del blink (350 ms) era costoso y causaba jank visible.

**Solución**: el historial estático se parsea una sola vez y se cachea. Solo se re-parsea cuando `_output_static_key` cambia (al añadir texto nuevo). El blink solo re-parsea el live block activo (~6 líneas de texto).

```python
# En _get_output_text():
if static_key != self._static_ansi_rendered_key:
    # Re-parsear solo cuando cambia el contenido estático
    self._static_ansi_cache = list(ANSI("".join(parts_snap)))
    self._static_ansi_rendered_key = static_key

# Combinar: cache estático + live block recién parseado
rendered = FormattedText(static_frags + live_frags)
```

Separación de claves de invalidación:
- `_output_static_key` — sube cuando `_output_parts` cambia (nueva parte estática)
- `_output_cache_key` — sube en cualquier cambio, incluyendo el blink

---

## Flujo completo de un tool call en TUI

```
modelo → text + tool_calls[]
    │
    ├── _flush_turn_block()               # cierra cualquier ⎿ pendiente
    ├── (auto-split si aplica)            # ● estático si planning text largo + write tools
    ├── _start_live_block_cb(bullet)      # abre live block con texto del modelo
    │
    └── para cada tool_call:
          ├── _show_tool_header_before_call(name, args)
          │     ├── _update_live_tool_start_cb(f"{display}:", preview_lines)
          │     │     → actualización atómica: label + preview bajo un solo lock
          │     └── _update_live_bullet_cb(f"Reading /path…  (ctrl+o to expand)")
          │
          ├── [tool ejecuta en el hilo del agente]
          │
          ├── _show_tool_block(name, args, result)
          │     ├── si write tool: _print(diff)  → va a _live_block_body
          │     └── si read/search: va a _turn_block (para ⎿ compacto)
          │
          └── _update_live_tools_cb(count)
                ├── _live_block_current_tool = ""
                ├── _live_block_preview = []    ← preview desaparece
                └── _live_block_action = ""     ← ● recupera texto original
    │
    └── _flush_live_block_cb(summary)
          ├── ● se fija con color de acento del agente
          ├── ⎿ muestra summary compacto (nombres de ficheros, patrones, etc.)
          └── bloque pasa a _output_parts (estático)
```

---

## Modo REPL vs TUI

| Modo | Live block | Preview | Auto-split | Callback |
|------|-----------|---------|------------|---------|
| **TUI** (OOCodeApp) | ✓ pulsante | ✓ | ✓ | wired |
| **REPL** (sin App) | ✗ | ✗ | ✗ | None |
| **WebUI** (Flask SSE) | ✗ (usa SSE) | ✗ | ✗ | None |
| **Subagente** | ✗ | ✗ | ✗ | None |

En modo REPL se usa `_run_animated_header()` en `ui/loop_tui.py`: anima el `◐` con colores ANSI sobre la misma línea (`\r`), sin live block.

---

## SYSTEM_RULES — regla de anuncio pre-escritura

Para que el split sea innecesario la mayoría de las veces, `SYSTEM_RULES` incluye:

> **OBLIGATORIO antes de llamar a `edit_file`/`smart_replace`/`write_file`:** emite una frase corta que mencione el fichero concreto: `"Corrigiendo X en Y.c:"` o `"Actualizando Y.c — razón:"`. Esto aparece como cabecera `●` en el terminal.

Cuando el modelo sigue esta regla, el texto corto ("Corrigiendo act_comm.c:") se usa directamente como bullet del live block y el auto-split no se activa. El auto-split es el **fallback** para cuando el modelo emite un planning general sin mencionar el fichero.

---

## Añadir soporte de preview a una nueva tool

1. En `agent/loop_helpers.py`, añadir caso en `_make_tool_preview()`:

```python
def _make_tool_preview(name: str, args: dict) -> list[str]:
    ...
    if name == "mi_nueva_tool":
        target = args.get("target", "")
        return [target] if target else []
    ...
```

2. No se necesita ningún otro cambio: `_show_tool_header_before_call()` en `agent/loop.py` llama automáticamente a `_make_tool_preview()` para cualquier tool.

3. Si la tool genera output visible (diffs, logs) que deben aparecer en el historial, usar `self._print()` durante la ejecución — el output va a `_live_block_body` y permanece en el bloque final.
