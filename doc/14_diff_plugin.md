# 14 — Diffs visuales y herramientas de código

Los diffs visuales, el índice de símbolos ctags y el linting automático son hooks nativos activos por defecto. No requieren activar ningún plugin.

## Diff visual — hook `diff_after_write`

Activo por defecto. Después de cada `edit_file`, `write_file` o `edit_files` — incluyendo las variantes MCP (`mcp_oocode_assistant_write_file`, etc.) — el hook `diff_after_write` renderiza el diff con colores al estilo Claude Code directamente en el terminal.

**Implementación:** `tools/diff_renderer.py` + `tools/hooks.py:_builtin_diff_after_write`

### Comportamiento

- **`edit_file`** / **`edit_files`**: reconstruye el contenido anterior desde `old_string`/`new_string`, calcula y renderiza el diff.
- **`write_file`** (built-in y MCP): el resultado incluye el diff unificado en un bloque ` ```diff ``` `; el hook lo parsea y lo renderiza.
- **Soporte MCP**: el hook usa `_is_write_tool(tool_name)` que detecta tanto nombres bare (`write_file`) como prefijados (`mcp_oocode_assistant_write_file`).

### Comando `/diff`

```
/diff            # lista ficheros editados en la sesión con +añadidas / ─eliminadas
/diff parser.py  # muestra el diff completo de ficheros cuyo nombre contenga "parser.py"
```

El historial se limpia automáticamente al abrir una nueva sesión con `/new`.

---

## Índice de símbolos — hook `ctags_after_write`

Activo por defecto. Requiere `universal-ctags` instalado (`apt install universal-ctags`).

Después de cada edición, el hook reindexea el directorio del fichero modificado. Al arrancar OOCode, se genera un índice inicial si no existe.

**Implementación:** `tools/ctags_index.py` + `tools/hooks.py:_builtin_ctags_after_write`

### Comando `/symbols`

```
/symbols                  # genera/actualiza índice del workspace
/symbols archivo.py       # lista funciones, clases y métodos del fichero
/symbols NombreClase      # busca símbolo por nombre en el proyecto
```

Las mismas funciones están disponibles como tools del agente vía MCP: `build_symbol_index`, `find_symbol`, `list_symbols`.

---

## Linting automático — hook `lint_after_write`

Activo por defecto. Ejecuta el linter apropiado según la extensión del fichero editado.

**Implementación:** `tools/hooks.py:_builtin_lint_after_write` + `_lint_file()`

| Extensión | Linter(s) |
|-----------|-----------|
| `.py` | `ruff check` + `mypy` |
| `.js` `.ts` `.jsx` `.tsx` | `eslint` |
| `.sh` `.bash` | `shellcheck` |
| `.rs` | `cargo check` |
| `.go` | `go vet` |

Si hay errores, se muestran en consola con colores y se incluyen en la respuesta al LLM. Si no hay errores, solo muestra `✓` en consola.

### Comando `/lint`

```
/lint              # linting del workspace completo (ruff, mypy, shellcheck)
/lint src/main.py  # linting de un fichero concreto
```

Las mismas funciones están disponibles como tools del agente vía MCP: `lint_file`, `lint_project`.

---

## Activar/desactivar hooks

```json
{
  "hooks": {
    "enabled": true,
    "builtins": ["diff_after_write", "ctags_after_write", "lint_after_write"]
  }
}
```

O desde el REPL:
```
/hooks builtin diff_after_write    # toggle
/hooks builtin ctags_after_write   # toggle
/hooks builtin lint_after_write    # toggle
```

## Caché intra-turno y tools de escritura

Las tools con side-effects (write, edit, git commit, mv, rm…) están excluidas de la caché intra-turno en `tools/registry.py:_NO_CACHE_BASE`. El helper `_is_no_cache(name)` también excluye las variantes MCP (e.g., `mcp_oocode_assistant_write_file`) para garantizar que cada escritura se ejecuta realmente.
