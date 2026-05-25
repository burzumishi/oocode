# TOOLS.md — 🤖 Entorno Local de OOCode

Las skills definen _cómo_ funcionan las herramientas. Este fichero es para _tu_ entorno específico.

## Servidor Ollama

- **Modelos disponibles:**
  - `batiai/qwen3.5-9b:latest` — Principal (general purpose)
  - `qwen2.5-coder-14b` — Código y refactoring
  - `deepseek-r1-8b` — Razonamiento y análisis
  - `llama3.1-8b` — Alternativa adicional

## Servidor SearXNG

- **Categorías:** general, news, science, it, images, videos, music, files, social media

## Infraestructura Local

- **Configuración:** `~/.oocode/oocode.json`

## Herramientas OOCode

| Tool | Permiso por defecto | Descripción |
|--|--|--|
| `read_file` | ✅ Libre | Lee archivos (por defecto 400 líneas) |
| `write_file` | ✅ Libre | Escribe o sobreescribe archivos |
| `edit_file` | ✅ Libre | Reemplaza cadena única exacta |
| `edit_files` | ✅ Libre | Edición atómica múltiple con rollback |
| `grep_code` | ✅ Libre | Búsqueda regex con contexto (ripgrep) |
| `find_file` | ✅ Libre | Búsqueda de archivos por patrón glob |
| `run_tests` | ✅ Libre | Ejecuta tests del proyecto (pytest, jest, etc.) |
| `lint_file` | ✅ Libre | Linter de archivo (ruff/mypy/eslint/cppcheck) |
| `git_status` | ✅ Libre | Estado del repositorio |
| `docker_ps` | ✅ Libre | Listar contenedores |
| `affected_files` | ✅ Libre | Análisis de impacto de cambios |
| `lsp_definition` | ✅ Libre | Go-to-definition |
| `lsp_diagnostics` | ✅ Libre | Errores y advertencias del archivo |
| `web_search` | ✅ Libre | Búsqueda en SearXNG local |
| `email_send` | ⚠️ Confirmación | Enviar email (acción externa) |
| `git_push` | ⚠️ Confirmación | Empujar a remoto (irreversible) |
| `compose_down -v` | ❌ Prohibido | DESTRUYE volúmenes sin confirmación |

## Herramientas LSP (Language Server Protocol)

### Navegación en Código

| Tool | Descripción |
|--|--|
| `lsp_definition(path, line, col)` | Go-to-definition |
| `lsp_references(path, line, col)` | Todas las referencias al símbolo |
| `lsp_type_definition(path, line, col)` | Definición del tipo de variable |
| `lsp_hover(path, line, col)` | Tipo/documentación del símbolo |
| `lsp_symbols(path)` | Símbolos del archivo (clases, funciones, variables) |
| `lsp_workspace_symbols(path, query)` | Buscar símbolo en todo el workspace |
| `lsp_implementation(path, line, col)` | Implementaciones de interfaz |
| `lsp_call_hierarchy(path, line, direction)` | Callers/callees de función |

### Refactoring

| Tool | Descripción |
|--|--|
| `lsp_rename(path, line, col, new_name, apply=false)` | Renombrar símbolo en todos los ficheros |
| `lsp_format(path, tab_size=4, insert_spaces=true)` | Formatear archivo |
| `lsp_code_actions(path, line, col)` | Acciones de código (quickfixes) |

### Diagnóstico

| Tool | Descripción |
|--|--|
| `lsp_diagnostics(path, wait=0)` | Errores y advertencias del archivo (OBLIGATORIO tras editar C/C++) |
| `lsp_restart(path)` | Reiniciar servidor LSP si da errores |

### Flujo Obligatorio con LSP

**C/C++ (clangd):**
1. `lsp_symbols(path)` → estructura del fichero
2. `lsp_hover(path, line, col)` → tipo exacto del símbolo
3. `edit_file` / `write_file` → hacer cambios
4. `lsp_diagnostics(path)` → verificar errores

**Python:**
1. `edit_file` / `write_file` → hacer cambios
2. `lsp_diagnostics(path)` → verificar errores tras editar

**JS/TS/Shell/Perl/YAML:**
1. `edit_file` / `write_file` → hacer cambios
2. `lsp_diagnostics(path)` → verificar errores

## Debug

- **Limpiar historial REPL:** `rm ~/.oocode/history`
- **Config:** `~/.oocode/oocode.json`
- **Memoria:** `~/.oocode/workspace/main/memory/`

## Notas

### Paquetes Python

Usa `pip_tool` para instalar paquetes:

```python
pip_tool(action="install", packages=["rich", "python-docx"])
```

### Docker en Contenedores

Para escribir ficheros dentro de un contenedor:

```python
# Método 1: Escribir en host y copiar
write_file(path="~/.oocode/tmp/file.txt", content="...")
docker_cp(src="~/.oocode/tmp/file.txt", dst="CONTAINER:/ruta/file.txt")

# Método 2: printf directo desde docker_exec
docker_exec(container="mi_contenedor", command='printf "texto" > /ruta/fichero')
```

### Vault de Credenciales

El vault está bloqueado por seguridad. Para acceder a sistemas remotos:

1. Ejecuta `/vault unlock` para desbloquear
2. Usa `vault_list()` para ver credenciales disponibles
3. Usa `vault_get(name)` para obtener credencial completa

### Plantillas de Documentos

- Listar plantillas: `doc_list_templates(directory)`
- Leer campos de plantilla: `doc_read_template_fields(path)`
- Rellenar plantilla: `doc_fill_template(template_path, fields, output_path)`

---

*Última actualización: 2026-05-24*
