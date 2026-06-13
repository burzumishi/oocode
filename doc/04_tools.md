# 04 — Herramientas del agente (Tool Use)

OOCode usa el **tool calling nativo de Ollama**. El modelo decide qué herramienta llamar; OOCode verifica permisos, la ejecuta y devuelve el resultado al modelo para que continúe.

## Flujo de ejecución

```
Usuario → AgentLoop.run(mensaje)
    → Ollama chat(messages, tools=schemas)
    → modelo devuelve tool_calls[]
    → para cada tool_call:
        → PermissionManager.check(nombre, descripción)
            → "auto": ejecuta
            → "ask":  pide confirmación al usuario
            → "deny": devuelve "Operación denegada"
        → ToolRegistry.call(nombre, args)
        → resultado → contexto → Ollama (nuevo turno)
    → hasta que no haya más tool_calls
    → render respuesta final en Markdown
```

## Herramientas disponibles

### `read_file`

Lee un fichero con números de línea. Soporta lectura parcial.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `path` | string | Ruta del fichero (absoluta o relativa al workspace) |
| `offset` | integer | Línea desde la que empezar (defecto: 1) |
| `limit` | integer | Número de líneas a leer (defecto: 150, configurable) |
| `skip_comment_banner` | boolean | (v0.4.8) Si `true`, colapsa una cabecera de comentario/licencia larga al inicio (logos, listas de autores) en un marcador, **conservando los números de línea** — útil para no gastar contexto en banners. Opt-in (defecto `false`). |

**Ejemplo de uso del modelo:**
```json
{"name": "read_file", "arguments": {"path": "src/main.py", "offset": 50, "limit": 100}}
```

**Configuración:** `tools.readFileLinesDefault` (defecto: 150), `tools.readFileLinesWarnLarge` (defecto: 500).

**`skip_comment_banner` — detección multi-lenguaje (v0.4.8):** reconoce la sintaxis de comentario según la extensión: C-family (`//`, `/* */`; las directivas `#include`/`#define` NO se colapsan), `#` (Python/shell/Ruby/YAML/TOML… + docstrings `"""`/`'''` en Python), `--` (SQL/Lua/Haskell), `;` (Lisp/ASM), `!` (Fortran), `%` (LaTeX/Erlang/MATLAB), `<!-- -->` (HTML/XML/SVG/Markdown), `(* *)` (OCaml/F#/Pascal), `"` (Vim). Como los números de línea se conservan, las ediciones posteriores no se desalinean.

---

### `write_file`

Escribe o sobreescribe un fichero completo.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `path` | string | Ruta del fichero |
| `content` | string | Contenido completo a escribir |

**Permiso defecto:** `ask`

**Con plugin diff activo:** la herramienta se sobreescribe para capturar el contenido anterior y mostrar un diff con colores antes de confirmar.

---

### `edit_file`

Reemplaza una cadena exacta dentro de un fichero. Más seguro que `write_file` para ediciones parciales.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `path` | string | Ruta del fichero |
| `old_string` | string | Texto a buscar (único). Copia el texto del fichero; pequeñas diferencias de espacios/indentación se toleran |
| `new_string` | string | Texto de reemplazo |

**Permiso defecto:** `ask`

Falla si `old_string` no se encuentra o la coincidencia es **ambigua** (aparece varias veces).

#### Match tolerante a whitespace, multi-lenguaje (v0.4.8)

La causa nº1 de "PRE-EDIT FALLIDO" era el modelo equivocándose en espacios/tabs/indentación de un `old_string` multilínea. `edit_file`/`edit_files` ya **no exigen match exacto**: el matcher escala la tolerancia y **solo aplica si la coincidencia es ÚNICA** (si es ambigua, no adivina y devuelve error):

1. **Exacto.**
2. **Por línea ignorando espacios finales** (`rstrip`) — cubre espacios al final de línea y diferencias CRLF/LF.
3. **Por línea ignorando indentación** (`strip`) — cubre tabs vs espacios o un bloque desplazado; al aplicar, se **reaplica la indentación real del fichero** al `new_string`.

Funciona en **cualquier lenguaje** (opera sobre líneas y whitespace, sin asumir sintaxis). El resultado avisa cuando hubo que tolerar whitespace (`(match tolerante a indentación — revisa el diff)`); el diff mostrado es la verdad. `replace_all=true` sigue usando match literal exacto.

#### Verificación previa y anti-bucle de ediciones (v0.4.2)

Para evitar que el modelo malgaste turnos editando con texto alucinado, OOCode aplica varias salvaguardas en torno a `edit_file`/`regex_replace`/`smart_replace`/`write_file`:

- **Read-before-edit** — `edit_file` exige que el fichero se haya leído en el turno (garantiza que existe y que el `old_string` es real).
- **PRE-EDIT** — antes de aplicar el cambio, OOCode comprueba que `old_string` existe literalmente; si no, devuelve el error sin tocar el fichero y muestra líneas similares.
- **Escalada unificada por fichero** — todos los fallos de modificación del **mismo** fichero en un turno (PRE-EDIT fallido, regex sin coincidencias, llamada duplicada) cuentan juntos y escalan:
  1. **1.º:** indica leer el fichero y copiar el texto literal.
  2. **2.º:** **inyecta el contenido real del fichero** (con números de línea) para que el agente copie el texto exacto en lugar de adivinarlo — y avisa de que el cambio puede estar **ya aplicado**.
  3. **3.º:** parada en seco — deja de reintentar sobre ese fichero; lo más probable es que el cambio ya esté hecho (debe verificarlo e informar al usuario) o que falte el texto exacto (debe pedir ayuda).

  El contador se reinicia cuando una modificación a ese fichero tiene éxito. Así se corta el bucle típico `edit → regex → write` que no avanza tras una compactación.

#### Fiabilidad de edición — invalidación de la caché de lecturas (v0.4.7)

Las salvaguardas anteriores mitigaban el **síntoma**; en v0.4.7 se corrigió la **causa raíz** de que las ediciones "nunca acertaran y tuvieran que revertir".

OOCode cachea los resultados de las herramientas de **solo lectura** (`read_file`, `grep_code`, `read_sections`, `ls_dir`…) durante el turno para no repetir trabajo. Esa caché solo se vaciaba **una vez por turno**, pero el auto-continue ejecuta muchas herramientas dentro del mismo turno. El efecto era:

1. `read_file(fichero)` → se cachea el contenido.
2. `edit_file(fichero)` → **éxito**, el fichero cambia en disco.
3. `read_file(fichero)` (mismos argumentos) → devolvía el contenido **cacheado pre-edición**.
4. El agente creía que el cambio no se aplicó, reintentaba el mismo `old_string` y obtenía `PRE-EDIT FALLIDO` (ya estaba aplicado) → bucle de reintento/revert.

Era un fallo de la herramienta, no del modelo. Ahora, **tras cada operación de mutación las lecturas afectadas se invalidan automáticamente**:

- **Dirigida por ruta** para las herramientas con ruta concreta (`edit_file`, `write_file`, `regex_replace`, `smart_replace`, `bulk_replace`, `edit_files`, `patch_apply`, `mv_file`, `cp_file`, `rm_file`…): se purgan las lecturas cacheadas de ese fichero y de su directorio.
- **Vaciado completo** para las que ejecutan comandos y pueden tocar ficheros arbitrarios (`bash`, `python_exec`, `make_run`, `git_*`, `docker_*`…).

Además, `smart_replace` y varias operaciones git mutadoras (`checkout`/`reset`/`merge`/`rebase`/`apply`) dejaron de cachearse: antes, una segunda llamada idéntica devolvía el resultado cacheado **sin editar de verdad**.

Consecuencia práctica: un `read_file` posterior a un edit siempre refleja el cambio, así que el agente ya no entra en el bucle de reintentos por leer contenido obsoleto.

---

### `list_dir`

Lista el contenido de un directorio.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `path` | string | Ruta del directorio |
| `recursive` | boolean | Lista recursivamente (defecto: false) |

**Permiso defecto:** `auto`

---

### `bash`

Ejecuta un comando de shell con timeout configurable.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `command` | string | Comando a ejecutar |
| `timeout` | integer | Timeout en segundos (defecto: 120) |
| `workdir` | string | Directorio de trabajo (defecto: workspace del agente) |

**Permiso defecto:** `ask`

**Configuración:** `tools.bashMaxOutputChars` (defecto: 20000) — la salida se trunca si supera este límite.

**Gestión de procesos:** usa `subprocess.Popen` con `start_new_session=True` y `stdin=DEVNULL`. Al timeout, mata el grupo de procesos completo con `os.killpg(pgid, SIGKILL)`, evitando procesos zombie a 100% CPU.

---

## Herramientas directas (disponibles en agentes y subagentes)

Las siguientes herramientas se registran directamente en `ToolRegistry` (además de via MCP). Están disponibles tanto en el agente principal como en los subagentes.

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `grep_code` | Búsqueda de patrones con ripgrep en el workspace | `auto` |
| `multi_grep` | Varias búsquedas en paralelo (patrones, flags distintos) | `auto` |
| `python_exec` | Ejecuta código Python en un subintérprete aislado | `ask` |
| `ls_dir` | Lista directorios en formato compacto | `auto` |
| `workspace_remember` | Añade notas persistentes al OOCODE.md del workspace | `auto` |
| `plan_create` / `task_done` | Plan de tareas del agente (ver doc 24) | `auto` |
| `ask_user` | Pregunta(s) estructurada(s) al usuario y espera respuesta | `auto` |

---

## `ask_user` — preguntar al usuario (v0.4.6)

El agente usa `ask_user` cuando la decisión es **del usuario** (en vez de adivinar o listar opciones en texto pasivo): ambigüedad real, elegir enfoque/orden, o proponer próximos pasos que dependen de una decisión.

```python
ask_user(questions=[
  {
    "header": "Enfoque",                      # chip corto
    "question": "¿Qué enfoque prefieres?",
    "multiSelect": false,                      # true = varias opciones (conserva el orden)
    "options": [
      {"label": "Rápido", "description": "menos robusto"},
      {"label": "Completo", "description": "más lento"}
    ]
  }
  # … hasta 4 preguntas
])
```

- Hasta **4 preguntas** por llamada; **2-4 opciones** cada una. El sistema añade siempre una opción de **texto libre**.
- **TUI**: formulario en la barra de estado con chips y navegación libre `←/→`; respondes por teclado. **WebUI**: tarjeta con secciones y botón Submit.
- Al cerrar, un bloque `● User answered OOCode's questions: …` recoge las respuestas antes de continuar.
- **Tolerante**: un modelo pequeño puede llamar con la forma simple `ask_user(question="…", options=["A","B"])` → se normaliza a 1 pregunta.
- **Subagentes** NO pueden preguntar: reciben un fallback y deciden solos.
- Es la base de `/plan` (plan-mode) y del prompt de permisos del WebUI.
- **Siempre se muestra (v0.4.8):** `ask_user` es una pregunta genuina del agente, así que `/elevated` **no la silencia** — elevated solo afecta a los permisos de herramientas. Lo mismo para la aprobación de plan (`/plan on`): si la activas, siempre te pregunta. La aprobación de plan muestra el plan **formateado** en la conversación y un formulario con una **pregunta corta**.

---

## Herramientas de filesystem (MCP)

Las siguientes herramientas están disponibles a través del servidor MCP bundled `mcp_servers/oocode_assistant.py`. Se registran automáticamente con el prefijo `mcp_oocode_assistant_`.

### Lectura/consulta — permiso `auto`

| Tool | Descripción |
|------|-------------|
| `ls_file` | Stat detallado de un fichero: permisos, propietario, tamaño, fechas, inodo |
| `ls_dir` | Listado estilo `ls -la`: permisos, propietario, tamaño, fecha de modificación |
| `find_file` | Busca ficheros por patrón glob con profundidad y límite configurables |
| `find_dir` | Busca directorios por patrón glob |
| `grep_file` | Busca regex en un fichero con números de línea y contexto opcional |

### Escritura/modificación — permiso `ask`

| Tool | Descripción |
|------|-------------|
| `chmod_file` | `chmod` en un fichero (modo octal: `'644'`, `'755'`, etc.) |
| `chmod_dir` | `chmod` en un directorio, con opción `recursive` |
| `chown_file` | `chown` en un fichero (`owner`: `'user'` o `'user:group'`) |
| `chown_dir` | `chown` en un directorio, con opción `recursive` |
| `mv_file` | Mueve o renombra un fichero o directorio |
| `cp_file` | Copia un fichero (o directorio completo con `copytree`) |
| `rm_file` | Elimina un fichero |
| `rm_dir` | Elimina un directorio (vacío, o recursivo con `recursive=true`) |
| `mkdir_dir` | Crea directorios con `mkdir -p` y modo opcional |
| `touch_file` | Crea un fichero vacío o actualiza su timestamp |

**Seguridad:** todas las herramientas verifican que la ruta esté dentro del home o cwd. Rutas del sistema (`/etc`, `/usr`, `/bin`…) están bloqueadas.

---

### `code_search`

Busca en el código fuente del workspace usando **ripgrep** con soporte completo de regex, patrones glob, líneas de contexto y múltiples archivos.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `pattern` | string | Patrón de búsqueda (regex o cadena fija) |
| `path` | string | Directorio o fichero donde buscar (defecto: workspace) |
| `glob` | string | Filtro glob de ficheros (ej: `"*.py"`, `"src/**/*.ts"`) |
| `context_lines` | integer | Líneas de contexto alrededor de cada resultado (defecto: 2) |
| `fixed_string` | boolean | Busca cadena literal, no regex (defecto: false) |
| `max_results` | integer | Límite de resultados (configurable con `tools.codeSearchMaxResults`) |

**Permiso defecto:** `auto`

**Progress en tiempo real:** usa `subprocess.Popen` + `select.select` para streaming del output de `rg`. Cada fichero nuevo encontrado llama `tools.progress.report_progress(path)`, que actualiza el status bar del TUI en tiempo real mostrando `⎿ filename` mientras la búsqueda avanza.

**Fallback:** si `rg` no está disponible, cae a `grep -r`.

**Configuración:** `tools.codeSearchMaxResults` (defecto: 50), `tools.codeSearchContextLines` (defecto: 2).

---

### `edit_files`

Edición atómica multi-fichero con rollback automático si alguno falla.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `edits` | array | Lista de operaciones: `{path, old_string, new_string, replace_all?, action?}` |

Cada operación puede tener `action: "create"` (crear fichero nuevo), `action: "delete"` (eliminar fichero), o sin action (edición por reemplazo exacto).

Si `replace_all: true`, reemplaza **todas** las ocurrencias de `old_string` en el fichero.

**Permiso defecto:** `ask`

Si alguna operación falla, las ya ejecutadas se revierten automáticamente.

---

### `web_search`

Busca en internet usando DuckDuckGo (sin API key). Si el plugin SearXNG está activo y `searxng.enabled = true`, este tool usa SearXNG en su lugar.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `query` | string | Términos de búsqueda |
| `max_results` | integer | Resultados máximos (defecto: 5) |

**Permiso defecto:** `auto`

---

### `web_fetch`

Descarga una URL y extrae el texto visible (elimina scripts, estilos, nav, footer).

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `url` | string | URL a descargar |
| `max_chars` | integer | Límite de caracteres (defecto: 8000, configurable) |

**Permiso defecto:** `auto`

**Configuración:** `tools.webFetchMaxChars`

> El resultado de `web_fetch` (y de `pdf_extract_text`/`doc_read`/`doc_extract_metadata`) se etiqueta internamente como salida de herramienta antes de inyectarlo en el contexto, para que el modelo no confunda el documento descargado con un mensaje nuevo del usuario y siga la tarea en curso (v0.4.3).

---

### `searxng_search`

Busca usando una instancia SearXNG local (requiere el plugin searxng activo).

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `query` | string | Términos de búsqueda |
| `max_results` | integer | Resultados (0 = usa config) |
| `categories` | string | `general`, `news`, `science`, `it`, `images`, `videos` |

**Permiso defecto:** `auto`

Ver `doc/09_searxng.md` para configuración del plugin.

---

## Permisos

Cada herramienta tiene un modo de permiso configurable en `~/.oocode/oocode.json`:

```json
"permissions": {
  "bash":                    "ask",
  "write_file":              "ask",
  "edit_file":               "ask",
  "edit_files":              "ask",
  "read_file":               "auto",
  "list_dir":                "auto",
  "web_search":              "auto",
  "web_fetch":               "auto",
  "code_search":             "auto",
  "grep_code":               "auto",
  "multi_grep":              "auto",
  "python_exec":             "ask",
  "ls_dir":                  "auto",
  "workspace_remember":      "auto",
  "lsp_definition":          "auto",
  "lsp_references":          "auto",
  "lsp_hover":               "auto",
  "lsp_symbols":             "auto",
  "lsp_diagnostics":         "auto",
  "lsp_completion":          "auto",
  "lsp_rename":              "ask",
  "lsp_format":              "ask",
  "lsp_code_actions":        "auto",
  "lsp_type_definition":     "auto",
  "lsp_implementation":      "auto",
  "lsp_workspace_symbols":   "auto",
  "lsp_call_hierarchy":      "auto",
  "lsp_restart":             "auto"
}
```

| Modo | Comportamiento |
|------|---------------|
| `auto` | Se ejecuta siempre sin preguntar |
| `ask` | Muestra la herramienta y los argumentos, pide confirmación. La opción `siempre` activa `auto` solo para esta sesión |
| `deny` | Siempre denegado, devuelve "Operación denegada" al modelo |

El nivel `/elevated` sobreescribe los permisos en runtime:
- `off` — bash/write/edit → deny
- `full` — todo → auto
- `ask` — todo → ask

## Registro y extensión

Las herramientas se registran en `ToolRegistry` (`tools/registry.py`). Cada herramienta es una tupla `(nombre, función, schema_openai)`.

Para añadir una herramienta nueva:

```python
# tools/mi_herramienta.py
def mi_funcion(param: str) -> str:
    return f"resultado: {param}"

MI_SCHEMA = {
    "name": "mi_herramienta",
    "description": "Hace algo útil",
    "parameters": {
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "El parámetro"}
        },
        "required": ["param"]
    }
}
```

```python
# En oocode.py:build_registry()
registry.register("mi_herramienta", mi_funcion, MI_SCHEMA)
```

O mejor, crear un skill o plugin (ver `doc/07_plugins.md`, `doc/08_skills.md`).

---

## Herramientas de Documentos (python-docx, openpyxl, python-pptx)

OOCode incluye soporte nativo para manipulación de documentos O365 (.docx, .xlsx, .pptx) usando las librerías **python-docx**, **openpyxl** y **python-pptx**. Las gráficas se generan como **objetos OOXML nativos** (DrawingML), editables en Office — sin imágenes PNG ni matplotlib.

### 📄 python-docx — Documentos .docx

**Descripción:** Biblioteca para crear y manipular documentos Word (.docx).

**Métodos principales:**
- `add_paragraph()` — Añadir párrafo con formato
- `add_table()` — Crear tablas con estilos
- `add_picture()` — Insertar imágenes (requiere Pillow)
- `add_heading()` — Añadir encabezados
- `run_formatting` — Aplicar formato a texto (bold, italic, color)

**Estilos disponibles:**
| Propiedad | Descripción | Valores |
|------|-----|-----|
| `font.name` | Fuente del texto | Calibri, Arial, Times New Roman |
| `font.size` | Tamaño de fuente | 8-72 pt (Pt) |
| `font.bold` | Negrita | True/False |
| `font.italic` | Cursiva | True/False |
| `font.underline` | Subrayado | WD_UNDERLINE.SINGLE, DOUBLE, etc. |
| `font.color.rgb` | Color | RGBColor(r, g, b) |
| `alignment` | Alineación | CENTER, LEFT, RIGHT, JUSTIFY |
| `paragraph_format.space_after` | Espacio después | 0-50 pt |
| `paragraph_format.line_spacing` | Interlineado | 1.0-3.0 |

**Ejemplo básico:**
```python
from docx import Document
from docx.shared import Pt, RGBColor

doc = Document()
p = doc.add_paragraph("Texto con estilo")
run = p.runs[0]
run.bold = True
run.font.size = Pt(12)
run.font.name = "Calibri"
doc.save("documento.docx")
```

**Ver documentación completa:** `doc/STYLES_O365.md`

---

### 📊 openpyxl — Hojas de Cálculo .xlsx

**Descripción:** Biblioteca para manipular hojas de cálculo Excel.

**Métodos principales:**
- `cell()` — Acceder a celda
- `style` — Aplicar estilo de celda
- `number_format` — Formato numérico
- `hyperlink` — Añadir hipervínculos
- `merge_cells()` — Fusionar celdas

**Estilos de celda:**
| Clase | Propiedades | Descripción |
|-------|------|-----|
| `Font` | `bold`, `italic`, `underline`, `size`, `color` | Formato de texto |
| `PatternFill` | `start_color`, `end_color`, `pattern_type` | Relleno de celda |
| `Border` | `left`, `right`, `top`, `bottom` | Bordes de celda |
| `Side` | `style`, `color`, `border_style` | Borde individual |
| `Alignment` | `horizontal`, `vertical`, `wrap_text` | Alineación |

**Ejemplo básico:**
```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border

wb = Workbook()
ws = wb.active
cell = ws['A1']
cell.font = Font(name='Calibri', size=11, bold=True)
cell.fill = PatternFill(start_color='FF4472C4', pattern_type='solid')
cell.border = Border(left=Side(style='thin'), right=Side(style='thin'))
wb.save("hoja.xlsx")
```

**Ver documentación completa:** `doc/STYLES_O365.md`

---

### 📈 Gráficas OOXML nativas (DrawingML)

**Descripción:** Las gráficas se insertan como objetos `chartSpace` OOXML nativos — editables en Word/Excel/PowerPoint, vectoriales y sin pérdida de calidad. **No** se usan imágenes PNG ni matplotlib.

**Tools por formato:**
- `insert_chart` — gráfica nativa en Word (.docx): bar, column, line, line_markers, area, pie, doughnut, scatter, stacked_bar, stacked_column, radar
- `xlsx_insert_chart` — gráfica nativa de openpyxl anclada a un rango en Excel (.xlsx)
- `pptx_insert_chart` — gráfica nativa en una diapositiva (.pptx)
- En `doc_create`, el bloque `{"type": "chart", ...}` incrusta la gráfica nativa directamente

**Formato de datos:**
```json
{"categories": ["Ene", "Feb", "Mar"],
 "series": [{"label": "Ventas", "values": [100, 200, 150]}]}
```

---

### 📦 Instalación de Dependencias

```bash
# Instalar todas las dependencias necesarias
pip install python-docx python-pptx openpyxl pillow docxtpl

# Verificar instalación
python -c "import docx, openpyxl, pptx, docxtpl; print('✅ Todas las librerías instaladas')"
```

**Paleta de colores O365:**
```python
from docx.shared import RGBColor

colores_o365 = {
    'blue': RGBColor(0, 112, 192),      # #0070C0
    'dark_blue': RGBColor(0, 51, 102),   # #003366
    'red': RGBColor(204, 0, 0),          # #CC0000
    'green': RGBColor(0, 128, 0),        # #008000
    'yellow': RGBColor(255, 204, 0),     # #FFCC00
}
```

**Ver documentación completa:** `doc/STYLES_O365.md`
