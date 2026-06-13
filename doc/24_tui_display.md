# 24 — TUI Live Block y Display de Herramientas

## Visión general

El TUI de OOCode muestra un **live block** al final del área de conversación mientras el agente ejecuta herramientas. El bloque es dinámico: se actualiza en tiempo real con el nombre de la tool activa, el fichero o comando inline, y hasta 4 líneas de contexto (diff, "Running…"), y desaparece limpiamente al completarse la tarea, dejando solo el resumen compacto `⎿`.

```
  ● Voy a revisar el código y corregir los errores de compilación.

  ● Updating handlers.c:
  │ ◐ Replace: (handlers.c)
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

## Barra de estado — spinner y plan multitarea

Mientras el agente piensa o ejecuta, la **barra de estado** (encima del prompt) muestra un
spinner animado (`_SPINNER_FRAMES`, nunca un icono fijo). Tiene tres formas según el momento,
todas con el **mismo patrón de alineación** — icono/spinner en col 2 + 1 espacio; conector
`↳` en col 2; iconos de tarea, summary `…` y footer `⎿ Tip` en col 4:

**Turno simple (sin plan):**

```
  ◉ Cavilando…  (830.9s)
  ↳ 2.5M↑ 14K↓  ·  ctx: ▰▱▱▱▱▱▱▱▱▱ 17%
    ⎿ Tip: /doctor  diagnostica la conexión con Ollama
```

La palabra de "pensamiento" (`_THINKING_WORDS`) y la frase near-finish (`_NEAR_FINISH_PHRASES`,
a partir de 25 s) se colorean con `status-word` (cyan) y `status-phrase` (ámbar).

**Multitarea (con `plan_create` activo):**

```
  ◉ Recableando word/excel/pptx (Cavilando… · 3m 19s · 2.5M↑ 14K↓ tokens)
  ↳ ✔ Generar word/excel/pptx_assistant.py desde office
    ◼ Re-cablear config/comandos/webui/tests/docs para word/excel/pptx
    … +0 pending, 1 completed
```

- **Frase principal en rojo** (`status-main`) = el `summary` del plan (`plan_create(summary=…)`,
  guardado en `_plan_summary`); si no hay summary, cae al texto de la tarea activa.
- Entre paréntesis, la misma palabra/colores que el turno simple.
- **Tareas** (`_get_status_text` en `ui/app.py`): completadas `✔` en **verde tachado**
  (`task-done` con `strike`); la activa `◼` con el cuadrado en **verde** (`task-active-mark`)
  y el texto en **blanco negrita** (`task-active-text`); pendientes `◻` atenuadas. El conector
  `↳` solo va en la primera fila visible.

**Compactación (`_compacting_ctx`):**

```
  ↻ Compactando  40 msgs · ~50,000 tok · 81%
  ◉ ▰▰▰▱▱▱▱▱▱▱   45%  resumiendo 12 msgs…
    ⎿ Tip: …
```

El `↻` es el arco de compactación; la animación va en la barra de progreso de la línea 2
(`_frame_cmp`, también `_SPINNER_FRAMES`).

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
  |     handlers.c
  ⎿ Used 3 tools (ctrl+o to expand)
```

### Solución: auto-split

Si el planning text tiene **más de 60 caracteres** y **no menciona explícitamente** el fichero objetivo de las write tools, el sistema:

1. Imprime el planning text como `●` estático (no pulsante, sin live block)
2. Extrae los nombres de fichero de los args de las write tools
3. Genera automáticamente un nuevo `●` con el header del fichero:

```
  ● Voy a continuar con la refactorización completa. Primero necesito revisar...

  ● Updating handlers.c:
  |  ◐ Replace:
  |     handlers.c
  ⎿ Updated handlers.c (ctrl+o to expand)
```

### Formato del header auto-generado

| Ficheros modificados | Header generado |
|---|---|
| 1 fichero | `Updating handlers.c:` |
| 2 ficheros | `Updating handlers.c, utils.c:` |
| 3+ ficheros | `Updating handlers.c (+2 more):` |

### Condición de activación

El split **solo** ocurre cuando:
- `_start_live_block_cb` está activo (modo TUI — no REPL, no WebUI, no subagente)
- El texto del modelo es plain text (no lista Markdown, no heading)
- `len(first_line) > 60`
- Las write tools del batch tienen path en sus args
- El texto no menciona el nombre de ningún fichero objetivo

Si el modelo ya anuncia explícitamente el fichero ("Corrigiendo gethostname en handlers.c:"), el comportamiento es el original: el texto del modelo se usa directamente como bullet del live block.

---

## Razonamiento del modelo (💭) — v0.4.8

Cuando el pensamiento del modelo está activado (`/think low|medium…`, o `thinking.think_level` en `models.configs`), su razonamiento (canal `<think>`) se **muestra como narración atenuada** prefijada con 💭 — antes se descartaba (solo se contaba para tokens) y las herramientas se ejecutaban sin explicar el "porqué".

- **Apertura de paso** (sin bloque de tools abierto): el razonamiento va al nivel de la conversación, renderizado como **Markdown** (negritas, listas, `code`) y **alineado** (columna 2, como el `●`):

```
  💭 Veo varios errores. Voy a corregirlos: primero el `else` sin `if` en db.c,
     luego los tipos en parser.c.
```

- **Dentro de un bloque** (ya hay herramientas trabajando sobre un fichero y esta iteración CONTINÚA ese trabajo — tool-only o preámbulo repetido): el razonamiento intermedio aparece **dentro del bloque**, con el prefijo `│`, para no romperlo:

```
  ● Reading db.c
  │ ◐ Reading: (db.c:650+20)
  │ 💭 Veo un else sin if previo. Voy a reescribir esa sección.
  │ ◐ Update: (db.c)
  ⎿ Read 1 file (db.c) …
```

- **Paso nuevo con bloque abierto** (la iteración trae **texto nuevo** no-duplicado → tendrá su propio `●`): el flush del bloque anterior — que iba a producirse igualmente por el texto — se **adelanta** a antes del 💭, de modo que el razonamiento del paso queda **entre bloques**, visible al nivel de la conversación, y no enterrado como última línea `│ 💭` del bloque que se estaba cerrando:

```
  ⎿ Read 1 file (configure.ac) …

  💭 Ahora voy a regenerar el proyecto con autogen.sh para confirmar que funciona.

  ● Regenerando el proyecto con autogen.sh:
  │ ◐ Bash: $ ./autogen.sh
```

- **Paso nuevo por razonamiento distinto** (v0.5.0, `_reasoning_step`): con `reasoning` activo el modelo razona ANTES de cada acción aunque reemita el mismo preámbulo (o ninguno). Sin esto, todos esos pasos se fundían bajo un único `●` "Used N tools" (medido en logs reales: 11 mensajes de agente para 132 tools). Ahora, cuando una iteración de continuación trae un 💭 **distinto** del último **y** herramientas nuevas **y** el bloque abierto ya tiene trabajo, se cierra el bloque, el 💭 sale entre bloques y se abre un `●` etiquetado por la acción — la estructura `💭 → ● → tools → ⎿` por cada paso, igual que en Claude Code:

```
  ⎿ Read 2 files …

  💭 Los símbolos que faltan son funciones de Windows, no del sistema de moneda.

  ● Editing (winport.c):
  │ ◐ Update: (winport.c)
```

> **Regla canónica (guards en test_42/test_22/test_76):** la frontera del bloque la decide el **texto nuevo** (misma condición que el `●`), el **auto-split por fichero** de las write tools, el **cambio de asunto** de la tanda de tools entrante (ver abajo) o un **razonamiento (💭) DISTINTO acompañado de tools nuevas** (v0.5.0). **Razonar a solas sigue SIN cerrar el bloque**: razonar sin tools, o repitiendo el MISMO pensamiento, mantiene el bloque abierto (💭 dentro, `│ 💭`). Lo que abre paso es un 💭 nuevo + tools nuevas con el bloque ya con trabajo. Los modelos sin `reasoning` conservan la agrupación previa. Los tres intentos de "flush-al-razonar INCONDICIONAL" del 2026-06-11 (incondicional → por fichero → `_continue_same_file`) troceaban bloques y suprimían `●`; el corte v0.5.0 es distinto porque exige 💭 distinto + tools + bloque con trabajo (no reintroduce aquella regresión).

Coste cero cuando el pensamiento está desactivado (default): no se emite nada. En la WebUI/Vim se emite el evento SSE `reasoning` con `new_step` (misma decisión de colocación que el TUI: `true` → el cliente cierra su bloque y pinta el 💭 standalone).

## Bloques de herramientas por edición (unidades visuales) — v0.4.8

La unidad visual es **una edición**: exploración + razonamiento + UNA edición + su diff = un bloque, que se **cierra inmediatamente al completarse la edición con éxito** (`_show_tool_block` → `_flush_turn_block` tras renderizar el diff). El bloque pasa YA al buffer estático — el usuario ve cada decisión y cada diff **al momento**, como en Claude Code, en lugar de un live block que apila 16 tools del mismo fichero y suelta todos los diffs de golpe al final:

```
  ● Voy a corregir los warnings de compilación…
  │ ◐ Read: (handlers.c:700+30)
  │ ◐ Update: (handlers.c)  + diff
  ⎿ Read 1 file (handlers.c)

  ● Continuing with handlers.c
  │ ◐ Update: (handlers.c)  + diff
  ⎿ Used 1 tool
```

Reglas de la unidad:
- **Cierre**: edición completada con éxito (diff renderizado). Una edición **fallida** (PRE-EDIT, duplicado…) NO cierra: el reintento se queda en el mismo bloque.
- **Reapertura**: la siguiente write tool abre su propia unidad en `_show_tool_running_header` (sin bloque abierto → `_start_live_block_cb`): frase de **continuación** si es el MISMO fichero (`_last_write_target`, sobrevive al flush) o de **cambio** si es otro (`_pick_file_continue_phrase` / `_pick_file_switch_phrase`).
- **Auto-split por cambio de fichero** (`_current_write_target`): sigue existiendo como frontera adicional (cubre el caso edición fallida → edición de otro fichero, donde no hubo cierre post-diff).
- **Cambio de ASUNTO (concern) en iteración tool-only**: un intento de compilación/ejecución (`bash`/`python_exec`/`make_run`/`run_script`/`pip_tool`/`npm_tool` → concern `cmd`) y la edición de un fichero (concern `file:<ruta>`) son unidades visuales **distintas**. En `run()`, cuando una iteración de continuación (dup/tool-only) trae una tanda cuyo concern (`_tools_concern`) difiere del establecido en el bloque abierto (`_block_has_cmd` / `_current_write_target`), el dedup se anula: el bloque se cierra, el 💭 de la iteración queda **entre bloques** y la tanda abre su `●` (etiquetado por su primera tool). Sin esto, "autogen + make + razonar los errores + editar config.h" se encadenaban bajo un solo "Used N tools". La decisión la toman las **tools entrantes**, no el razonamiento; el concern del bloque muere con el flush.
- Las **lecturas/búsquedas** no cierran unidades ni fijan concern (son NEUTRALES): se agrupan con el trabajo al que acompañan (diagnóstico tras un make fallido, exploración previa a una edición…).
- **`task_done` cierra la unidad de su tarea**: el header hace flush ANTES de ejecutarse, la narración del desenlace (`●` de `_render_task_narration`) sale estática **entre bloques** (antes caía en `_live_block_body` y quedaba enterrada), y su resultado interno ("✔ Tarea N/M…") no se bufferiza ni cuenta en el `⎿` del bloque siguiente.
- **Paridad WebUI**: el evento `tool_done` lleva `is_modify`; el cliente hace `_finishToolBlock()` tras una edición OK y la siguiente tool abre bloque nuevo.
- **Tools de memoria** (`mem_save`/`workspace_remember`): son acciones de continuidad del agente, NO trabajo sobre ficheros — cierran el bloque en curso y su `◐ ⬡` + resultado salen estáticos al nivel de la conversación (nunca enterrados en un "Used N tools"); no cuentan en el `⎿` del bloque siguiente.

`_extract_write_target` debe cubrir **todos** los nombres de parámetro de ruta de las modify tools: `path` (edit_file, lsp_rename…), `file_path` (write_file) **y `file` (smart_replace, regex_replace)**. Si falta uno, el cierre/auto-split deja de disparar para esa tool en silencio y vuelven los bloques multi-edición (bug real: el steering anti-fallos de edición empuja hacia `smart_replace`, cuyo parámetro `file` no estaba cubierto).

El **mensaje de `task_done(message=…)`** (resumen de cada tarea del plan) se **muestra al usuario** como narración: los modelos locales suelen poner ahí su explicación ("Tarea 3: eliminé X porque no se usa"), que antes se descartaba.

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

## Streaming `│` del sub-agente (presupuesto por turno)

Un sub-agente **no** usa el live block del padre: renderiza su propio bloque en la conversación mediante `console.print` con prefijo `│` coloreado (color rotativo por turno). `AgentLoop._print()`, cuando `is_subagent=True`, envuelve cada línea en `│` y la cuenta contra `_MAX_SUB_LINES` (12). Al alcanzar el límite imprime una vez `… buffer lleno (ctrl+o para ver completo)` y suprime el resto de líneas de ese turno.

El cap es **por turno**, no por ejecución completa. El contador `_sub_lines_shown` se resetea al inicio de cada iteración del bucle `run()` (en `agent/loop.py`, junto al incremento de color `_subagent_color_idx`, gateado por `is_subagent`):

```
while True:                       # bucle de turnos del sub-agente
    ...
    self._subagent_color_idx += 1
    if self.is_subagent:
        self._sub_lines_shown = 0  # presupuesto │ fresco para este turno
```

Sin este reset por turno (comportamiento previo), un sub-agente multi-turno consumía su presupuesto en el primer turno y **congelaba** el resto de su ejecución mostrando solo las líneas más antiguas. Como las líneas `│` se imprimen al buffer estático scrollable del padre (cap 80 KB, ver §2), las antiguas hacen scroll hacia arriba a medida que llegan las nuevas, así el usuario sigue viendo la actividad reciente del sub-agente. La traza completa de todos los turnos queda disponible expandiendo con `Ctrl+O`.

Cubierto por `tests/test_22_tui_display.py::TestSubagentLinePrintCap`.

### Alineación del `●` de texto del sub-agente

Como el sub-agente no tiene live block (sus callbacks son `None`), su `●` de texto caía en la rama `console.print` directa de `_turn_display_bullet` → **columna 0**, desalineado respecto a sus líneas de tool (`  │  …`). `_turn_display_bullet` ahora hace early-return a `_render_subagent_bullet` cuando `is_subagent`: imprime el `●` y su continuación vía `self._print` (prefijo `│`, respeta `_MAX_SUB_LINES`). Los avisos de retry XML usan el helper `_notice` (indenta para el principal, `│` para sub-agentes). Todo el bloque del sub-agente queda alineado bajo su columna `│`:

```
  │ ● Tarea 6 activa: Documentar cambios en doc/interaccion_social.md.
  │   Voy a crear la documentación con todos los cambios del Sprint 9.
  │   ◐  Write(interaccion_social.md)
  │   │  Fichero escrito: /ruta/doc.md (8292 caracteres)
```

Cubierto por `tests/test_22_tui_display.py::TestSubagentBulletAlignment`.

---

## Render del `task` de orquestación (Markdown)

Los headers de `spawn_subagent` (`● spawn_subagent 💬 emoji nombre: …`) y de `explore` (`🔍 Explorando: …`) muestran el `task` que el agente principal delega. Cuando ese `task` es un bloque markdown multilínea (contexto, listas numeradas, **negritas**…), el header **no** debe volcarlo en crudo.

- **1.ª línea → inline en el header**, escapada con `rich.markup.escape` (para que el markup Rich del texto no se interprete como tags).
- **Resto → `Padding(Markdown(...), (0,0,0,4))`** justo debajo, de modo que negritas, viñetas y listas numeradas se renderizan correctamente.

Antes, todo el `task` iba por `_esc()` en un único f-string. `_esc()` escapa el markup Rich pero **no** interpreta markdown, así que `**Contexto actual:**`, `- bullets`, etc. aparecían literales en pantalla —escapando al formato de la conversación—. En `explore` la 1.ª línea iba además **sin escapar**, de modo que un `[texto]` en el task se interpretaba como tag Rich. Implementado en `agent/loop.py` (header de spawn) y `agent/subagent.py` (`explore`). Cubierto por `tests/test_79_subagent_task_markdown.py`.

> El mismo patrón (1.ª línea inline + resto como `Markdown`) lo usa `_turn_display_bullet` para el texto del agente; aquí se aplica al `task` delegado.

## `% ctx` del panel de subagentes

El header del panel de subagentes (`⏵⏵ Subagentes Activos … N% ctx`) muestra un porcentaje de contexto que corresponde al **subagente activo**, no al agente principal. `OOCodeApp._get_subagent_panel_text` toma `ctx_pct` del subagente en estado `running` (o del último que reporte contexto); si ninguno ha completado aún su 1.ª petición al LLM (`ctx_pct == 0`), el header no muestra `%`. Cada línea de subagente ya mostraba su propio `ctx_pct` (actualizado por el subagente vía `_sub_stats_ref` en `agent/loop.py`); el `%` del agente principal vive en el toolbar inferior, no en este panel.

---

## SYSTEM_RULES — regla de anuncio pre-escritura

Para que el split sea innecesario la mayoría de las veces, `SYSTEM_RULES` incluye:

> **OBLIGATORIO antes de llamar a `edit_file`/`smart_replace`/`write_file`:** emite una frase corta que mencione el fichero concreto: `"Corrigiendo X en Y.c:"` o `"Actualizando Y.c — razón:"`. Esto aparece como cabecera `●` en el terminal.

Cuando el modelo sigue esta regla, el texto corto ("Corrigiendo handlers.c:") se usa directamente como bullet del live block y el auto-split no se activa. El auto-split es el **fallback** para cuando el modelo emite un planning general sin mencionar el fichero.

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
