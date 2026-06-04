# TOOLS.md — Entorno Local de OOCode

## Servidor LLM (backend)

- **Backend:** `api.type` en `~/.oocode/oocode.json` (ollama | openai | anthropic)
- **Host:** `api.host` (p.ej. `http://localhost:11434` para Ollama)

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

## Notas

_(Personaliza aquí tus usos de herramientas: qué tool prefieres para cada tarea, alias, nombres de dispositivos, convenciones propias. Lo que escribas en esta sección se carga en el contexto del agente — los placeholders no.)_

---
*Actualiza este fichero con las URLs reales y permisos específicos del entorno.*
