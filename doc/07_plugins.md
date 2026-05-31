# 07 — Plugins

Los plugins son módulos Python que amplían OOCode con nuevas herramientas, comandos `/slash` y hooks de ciclo de vida.

## Directorio

```
~/.oocode/plugins/
├── enabled.json      # lista de plugins activos (sincronizado con oocode.json)
├── searxng.py        # plugin incluido: búsqueda SearXNG
└── mi-plugin.py      # plugins del usuario
```

## Gestión desde el CLI

```bash
# Ver plugins disponibles y estado
/plugins list

# Crear plantilla
/plugins create mi-plugin

# Activar (carga herramientas, guarda en oocode.json)
/plugins enable mi-plugin

# Desactivar (guarda en oocode.json)
/plugins disable mi-plugin

# Recargar todos los activos
/plugins reload
```

Al hacer enable/disable, `oocode.json` se actualiza automáticamente en `plugins.enabled`. Al siguiente arranque, los plugins se cargan según esa lista.

## Estructura de un plugin

Los plugins **no incluyen herramientas directas** (las tools van en el servidor MCP `mcp_servers/oocode_assistant.py`). Los plugins solo pueden aportar: comandos `/slash`, inyección en el system prompt, y hooks de ciclo de vida.

```python
"""Plugin: Mi Plugin

Descripción corta que aparece en /plugins list.
"""

NAME        = "mi-plugin"
DESCRIPTION = "Hace algo muy útil"
VERSION     = "1.0.0"

# ── Comandos /slash ───────────────────────────────────────────────────────────
# Mapa {"/cmd": handler_fn}  — handler recibe (args: str, agent_loop, config)

def _cmd_mi_comando(args: str, agent_loop, config) -> None:
    from ui.console import console   # SIEMPRE usar el console compartido
    console.print(f"[bold]Resultado:[/bold] {args}")

COMMANDS = {
    "/mi-comando": _cmd_mi_comando,
}

# ── Hooks de ciclo de vida ────────────────────────────────────────────────────

def on_start(config) -> None:
    """Llamado al arrancar OOCode. Recibe el OOConfig completo."""
    pass

def on_message(role: str, content: str) -> None:
    """Llamado en cada mensaje (user/assistant)."""
    pass

def on_tool_result(name: str, args: dict, result: str) -> None:
    """Llamado tras ejecutar una herramienta."""
    pass

def system_prompt_injection() -> str:
    """Texto adicional inyectado en el system prompt. Retorna '' para nada."""
    return "Contexto adicional para el agente desde mi-plugin."

def on_end() -> None:
    """Llamado al salir de OOCode."""
    pass
```

> **IMPORTANTE:** usa siempre `from ui.console import console` en lugar de crear una instancia `Console()` local. Crear consolas locales puede causar que el output se mezcle con el TUI de prompt_toolkit.

## Hook `on_start` y `TOOLS` dinámico

El hook `on_start(config)` se llama antes de que se lean las `TOOLS` del plugin. Esto permite que la lista de herramientas sea dinámica según la configuración:

```python
_cfg = {"url": "", "enabled": False}

def on_start(config) -> None:
    _cfg["url"]     = getattr(config, "searxng_url", "")
    _cfg["enabled"] = getattr(config, "searxng_enabled", False)
    global TOOLS
    TOOLS = _build_tools()   # reconstruye según config

def _build_tools() -> list:
    tools = [("mi_tool_base", fn_base, schema_base)]
    if _cfg["enabled"]:
        tools.append(("web_search", fn_override, schema_override))
    return tools
```

Los plugins pueden **sobreescribir herramientas built-in** (como `web_search`) porque se cargan después de las herramientas base.

## Plugins incluidos

### LSP (`lsp`)
14 herramientas LSP: `lsp_definition`, `lsp_references`, `lsp_hover`, `lsp_symbols`, `lsp_diagnostics`, `lsp_completion`, `lsp_rename`, `lsp_format`, `lsp_code_actions`, `lsp_type_definition`, `lsp_implementation`, `lsp_workspace_symbols`, `lsp_call_hierarchy`, `lsp_restart`.

`lsp_diagnostics` acepta un parámetro `wait` (float). Si no se especifica, se auto-selecciona: 3.0s para extensiones lentas (C/C++/Java/Kotlin/Swift), 2.0s para el resto.

Gestiona servidores LSP con `/lsp` en el REPL.

### SearXNG (`searxng`)
Ver `doc/09_searxng.md` para configuración completa.  
Expone `searxng_search`. Si `searxng.enabled = true`, sobreescribe `web_search`.

## Funcionalidades migradas a MCP y hooks nativos

A partir de la v5, las funcionalidades que antes requerían plugins ahora son parte del núcleo:

| Funcionalidad | Antes | Ahora |
|---------------|-------|-------|
| Diff visual con colores | `plugins enable diff` | Builtin hook `diff_after_write` (activo por defecto) |
| Linting automático | `plugins enable linter` | Builtin hook `lint_after_write` (activo por defecto) |
| Índice de símbolos ctags | `plugins enable ctags` | Builtin hook `ctags_after_write` + `/symbols` |
| Herramientas git | `plugins enable git` | MCP tools: `git_status`, `git_diff`, `git_log`… |
| Herramientas docker | `plugins enable docker` | MCP tools: `docker_ps`, `docker_logs`, `compose_up`… |

Los comandos `/diff`, `/symbols` y `/lint` están disponibles directamente sin activar ningún plugin.

## Acceder a la config de OOCode desde un plugin

En `on_start(config)` tienes acceso al objeto `OOConfig` completo:

```python
def on_start(config) -> None:
    url = config.searxng_url       # campo específico
    model = config.model           # modelo activo
    workspace = config.workspace   # workspace del agente
```

Para configuración propia del plugin, usa `getattr(config, "mi_campo", defecto)` si has añadido el campo a `oocode.json`, o guarda un fichero JSON propio en `~/.oocode/plugins/mi-plugin.json`.

## Carga de plugins al arranque

```
OOCode.main()
  → PluginManager(enabled_override=config.plugins_enabled)
  → load_all(config)
      → para cada plugin en _enabled:
          → importlib.util carga el módulo Python
          → llama on_start(config)
          → registra el módulo en _loaded
  → get_tools()
      → lee TOOLS de cada módulo cargado
      → registry.register(name, fn, schema)  ← sobreescribe si ya existe
  → get_commands()
      → registra COMMANDS en el dispatcher de handle_slash
```

## Errores de carga

Si un plugin falla al cargarse, el error se muestra al arrancar y se escribe en el log, pero OOCode continúa sin ese plugin:

```
⚠  Plugin error: mi-plugin: ImportError: No module named 'requests'
```

Ver errores con `/logs 20`.

---

## 🏠 Home Office — Herramientas de Oficina

OOCode incluye herramientas para manipular documentos de oficina (.docx, .xlsx, .pdf) con soporte para estilos y formatos compatibles con O365 y LibreOffice.

### 📄 Documentos .docx (python-docx)

**Descripción:** Creación y manipulación de documentos Word con estilos profesionales.

**Métodos principales:**
- `add_paragraph()` — Añadir párrafo con formato
- `add_table()` — Crear tablas con estilos
- `add_picture()` — Insertar imágenes (requiere Pillow)
- `add_heading()` — Añadir encabezados
- `run_formatting` — Aplicar formato a texto

**Estilos disponibles:**
- **Fuente:** Calibri, Arial, Times New Roman
- **Tamaño:** 8-72 pt
- **Negrita/Cursiva:** Soporte completo
- **Subrayado:** Sencillo, doble, contable
- **Colores:** RGB completo
- **Alineación:** Centro, izquierda, derecha, justificado
- **Interlineado:** 1.0-3.0
- **Espaciado:** 0-50 pt

**Ver documentación:** `doc/STYLES_O365.md`

---

### 📊 Hojas de Cálculo .xlsx (openpyxl)

**Descripción:** Manipulación de hojas Excel con estilos avanzados.

**Métodos principales:**
- `cell()` — Acceder a celda
- `style` — Aplicar estilo de celda
- `number_format` — Formato numérico
- `hyperlink` — Añadir hipervínculos
- `merge_cells()` — Fusionar celdas

**Estilos de celda:**
- **Font:** `bold`, `italic`, `underline`, `size`, `color`
- **PatternFill:** Relleno sólido y gradientes
- **Border:** Bordes con estilos múltiples
- **Alignment:** Alineación horizontal/vertical
- **NumberFormat:** Moneda, %, fecha, texto
- **Protection:** Bloqueo y ocultación de celdas

**Ver documentación:** `doc/STYLES_O365.md`

---

### 📈 Gráficos con matplotlib

**Descripción:** Generación de gráficos dinámicos para informes.

**Formatos de exportación:**
- `.png` — Alta calidad (DPI 300 recomendado)
- `.pdf` — Vectorial con fuentes embebidas
- `.svg` — Escalable vectorial
- `.eps` — PostScript

**Configuración recomendada:**
```python
import matplotlib
matplotlib.use('Agg')  # Modo no-GUI
matplotlib.rcParams['figure.dpi'] = 300
matplotlib.rcParams['savefig.dpi'] = 300
```

**Ver documentación:** `doc/STYLES_O365.md`

---

### 🎨 Paleta de Colores O365

```python
from docx.shared import RGBColor
from openpyxl.styles import PatternFill

colores_o365 = {
    'blue': RGBColor(0, 112, 192),      # #0070C0
    'dark_blue': RGBColor(0, 51, 102),   # #003366
    'red': RGBColor(204, 0, 0),          # #CC0000
    'green': RGBColor(0, 128, 0),        # #008000
    'yellow': RGBColor(255, 204, 0),     # #FFCC00
}
```

---

### 📦 Instalación

```bash
# Instalar todas las dependencias
pip install python-docx openpyxl matplotlib pillow

# Verificar instalación
python -c "import docx; import openpyxl; import matplotlib; print('✅ Todas las librerías instaladas')"
```

---

### 📚 Referencias

- [python-docx documentación](https://python-docx.readthedocs.io/)
- [openpyxl documentación](https://openpyxl.readthedocs.io/)
- [Matplotlib documentación](https://matplotlib.org/)
- [Pillow documentación](https://pillow.readthedocs.io/)

**Ver guía completa:** `doc/STYLES_O365.md`
