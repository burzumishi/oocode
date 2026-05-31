# 23 — Hooks

Los hooks son interceptores que se ejecutan antes (pre) o después (post) de cada tool call. OOCode incluye 18 hooks built-in y permite definir hooks personalizados en `OOCODE.md`.

## Gestión desde el REPL

```
/hooks                              # ver hooks activos
/hooks list                         # lista completa de hooks disponibles
/hooks builtin <nombre>             # activar/desactivar hook (toggle)
```

## Los 18 hooks built-in

### lint_after_write
**Cuando:** post `write_file`, `edit_file`, `edit_files`  
**Efecto:** Ejecuta el linter apropiado para el lenguaje del fichero modificado:
- Python: `ruff check` (y `mypy` si disponible)
- JavaScript/TypeScript: `eslint`
- Shell: `shellcheck`
- Rust: `cargo check`
- Go: `go vet`

El output del linter se muestra directamente en el TUI.

**Activar:**
```
/hooks builtin lint_after_write
```

---

### lsp_after_write
**Cuando:** post `write_file`, `edit_file` (para extensiones con LSP configurado)  
**Efecto:** Solicita diagnósticos LSP del fichero modificado y los muestra en el TUI. Itera sobre todos los ficheros de una operación `edit_files` (máximo 3).

**Activar:**
```
/hooks builtin lsp_after_write
```

---

### quick_syntax
**Cuando:** post `write_file`, `edit_file` en ficheros `.py`  
**Efecto:** Ejecuta `ast.parse()` instantáneamente (sin dependencias externas) para detectar errores de sintaxis Python antes del linter completo.

Activo por defecto.

---

### config_syntax_after_write
**Cuando:** post `write_file`, `edit_file` en ficheros `.json`, `.toml`, `.ini`, `.cfg`  
**Efecto:** Valida la sintaxis del fichero de configuración usando la stdlib de Python (`json.loads`, `tomllib`, `configparser`).

Activo por defecto.

---

### backup_before_write
**Cuando:** pre `write_file` (ficheros ya existentes)  
**Efecto:** Crea una copia de seguridad del fichero original con extensión `.bak` antes de sobreescribirlo.

```
/hooks builtin backup_before_write
```

---

### test_after_write
**Cuando:** post `write_file`, `edit_file` en ficheros `.py`  
**Efecto:** Detecta el fichero de test asociado (mismo nombre con prefijo `test_` o en directorio `tests/`) y ejecuta pytest con timeout de 30 segundos.

```
/hooks builtin test_after_write
```

---

### verify_after_edit
**Cuando:** post `edit_file`  
**Efecto:** Re-lee la sección del fichero alrededor de la edición (usando los marcadores del edit) y la muestra con marcadores `▶` para verificar visualmente que el cambio se aplicó correctamente.

Soporta `edit_files` (itera todos los ficheros editados).

```
/hooks builtin verify_after_edit
```

---

### interface_change_detector
**Cuando:** pre + post `write_file`, `edit_file` en ficheros `.py`  
**Efecto:** Captura snapshot de las interfaces públicas (firmas de funciones/métodos, constantes exportadas) antes y después de la edición. Si detecta cambios de firma o símbolos eliminados, busca los callers con ripgrep y muestra un aviso con los ficheros afectados.

```
/hooks builtin interface_change_detector
```

---

### test_suite_delta
**Cuando:** pre + post cualquier edición  
**Efecto:** Ejecuta la suite de tests antes de la edición (captura baseline) y después. Al terminar, reporta solo las regresiones nuevas y los tests reparados, no el output completo.

```
/hooks builtin test_suite_delta
```

---

### todo_scan
**Cuando:** post `write_file`, `edit_file`  
**Efecto:** Escanea el fichero modificado en busca de `TODO`, `FIXME`, `HACK`, `NOTE` y muestra los encontrados (máximo 5) en el TUI.

```
/hooks builtin todo_scan
```

---

### size_check
**Cuando:** post `write_file`, `edit_file`  
**Efecto:** Avisa si el fichero modificado supera 300 líneas o 15 KB, sugiriendo dividirlo en módulos más pequeños.

```
/hooks builtin size_check
```

---

### log_tool_calls
**Cuando:** post todas las tools  
**Efecto:** Registra cada tool call en `~/.oocode/logs/tool_calls.jsonl` con timestamp, nombre de tool, argumentos y resultado truncado.

```
/hooks builtin log_tool_calls
```

---

### git_push_guard
**Cuando:** pre `git_commit`, `git_push`  
**Efecto:**
- Antes de `git_commit`: avisa si el mensaje de commit es vacío, genérico (`"fix"`, `"update"`) o muy corto
- Antes de `git_push`: avisa si la rama destino es `main`, `master` o `production`

```
/hooks builtin git_push_guard
```

---

### security_audit_log
**Cuando:** post todas las tools del servidor `security-assistant`  
**Efecto:** Registra en `~/.oocode/logs/security_audit.log` cada herramienta de seguridad usada, con timestamp, herramienta, argumentos y usuario.

```
/hooks builtin security_audit_log
```

---

## Hooks personalizados en OOCODE.md

Puedes definir hooks de shell en la sección `## Hooks` de `OOCODE.md`:

```markdown
## Hooks
post write_file: ruff check {path} --fix
post edit_file:  mypy {path} --ignore-missing-imports
post bash:       echo "[hook] Ejecutado: {command}"
pre  git_push:   npm test
```

**Variables disponibles:**

| Variable | Disponible en | Descripción |
|----------|---------------|-------------|
| `{path}` | write_file, edit_file | Ruta del fichero modificado |
| `{command}` | bash | Comando ejecutado |
| `{message}` | git_commit | Mensaje de commit |
| `{branch}` | git_push | Rama destino |

Los hooks de shell se ejecutan con `bash -c` y su salida se muestra en el TUI. Si devuelven código de error no cero, se muestra un aviso pero no se interrumpe la operación.

---

## Configuración avanzada

Los hooks activos se persisten en `~/.oocode/oocode.json`:

```json
{
  "hooks": {
    "builtins": [
      "lint_after_write",
      "quick_syntax",
      "config_syntax_after_write",
      "log_tool_calls",
      "backup_before_write",
      "git_push_guard"
    ]
  }
}
```

---

## Crear un hook built-in personalizado

Para añadir un hook built-in al proyecto:

1. Implementar en `tools/hooks.py`:
```python
def _hook_mi_hook_post(name: str, args: dict, result: str, loop) -> None:
    """Se ejecuta después de write_file y edit_file."""
    if name not in ("write_file", "edit_file"):
        return
    path = args.get("path", "")
    # lógica del hook...
    loop._hprint(f"  [mi_hook] procesado: {path}")
```

2. Registrar en `_BUILTIN_HOOKS`:
```python
_BUILTIN_HOOKS = {
    ...
    "mi_hook": HookDef(
        name="mi_hook",
        description="Descripción de mi hook",
        post_fn=_hook_mi_hook_post
    )
}
```

3. Activar con:
```
/hooks builtin mi_hook
```

---

## Hooks con par pre+post

Los hooks `interface_change_detector` y `test_suite_delta` usan el par pre+post para comparar el estado antes y después de la edición. El snapshot previo se guarda en el estado interno del `HookManager` y se recupera en el post para calcular el delta.

El sistema garantiza que cada par pre+post esté sincronizado aunque haya múltiples tool calls entre ellos.
