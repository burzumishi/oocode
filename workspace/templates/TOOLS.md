# TOOLS.md — Entorno Local de OOCode

## Servidor Ollama

- **Host:** `http://localhost:11434`
- **Config:** `~/.oocode/oocode.json`

## Servidor SearXNG

- **Host:** `http://localhost:8888`
- **Categorías:** general, news, science, it, images, videos, files, social media

## Permisos a recordar

| Tool | Permiso |
|------|---------|
| `email_send` | ⚠️ Pedir confirmación |
| `git_push` | ⚠️ Pedir confirmación |
| `compose_down -v` | ❌ Prohibido sin confirmación explícita |

## Flujo LSP (obligatorio tras editar código)

| Lenguaje | Flujo |
|----------|-------|
| C/C++ | `lsp_symbols` → `lsp_hover` → editar → `lsp_diagnostics` |
| Python | editar → `lint_file` → `lsp_diagnostics` |
| JS/TS/Go/Rust | editar → `lsp_diagnostics` |

## Patrones no obvios

**Escribir dentro de un contenedor Docker:**
```python
# Método recomendado: heredoc vía docker_exec
docker_exec(container="nombre", command='cat > /ruta/fichero << "EOF"\ncontenido\nEOF')
```

**Vault de credenciales:**
1. `/vault unlock` para desbloquear
2. `vault_list()` → ver credenciales disponibles
3. `vault_get(name)` → obtener credencial completa

---
*Actualiza este fichero con las URLs reales y permisos específicos del entorno.*
