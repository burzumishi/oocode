# 13 — Herramientas Git (MCP)

Las herramientas Git están disponibles directamente como tools del agente a través del servidor MCP bundled `mcp_servers/oocode_assistant.py`. No requieren activar ningún plugin.

## Herramientas disponibles

| Herramienta | Descripción | Permisos |
|-------------|-------------|----------|
| `git_status` | Estado del repositorio (staged, modified, untracked, ahead/behind) | lectura |
| `git_diff` | Diff de cambios unstaged, staged o respecto a un ref | lectura |
| `git_log` | Historial de commits con gráfico de ramas (`file_path`, `show_diff`) | lectura |
| `git_add` | Añade ficheros al staging area | escritura |
| `git_commit` | Crea un commit con el mensaje indicado | escritura |
| `git_push` | Empuja commits al remote (`force` = `--force-with-lease`) | escritura |
| `git_pull` | Actualiza la rama desde el remote | escritura |
| `git_branch` | Lista, crea, cambia, elimina o renombra ramas | escritura |
| `git_stash` | push/pop/list/drop del stash (`diff_index` para ver diff) | escritura |
| `git_patch` | Genera o aplica parches (create/format/apply) | escritura |
| `git_clone` | Clona un repositorio (shallow, rama específica) | escritura |
| `git_worktree` | Gestiona git worktrees: list/add/remove/prune/lock/unlock | escritura |

## Configuración de permisos

En `~/.oocode/oocode.json` puedes ajustar el nivel de permiso por herramienta:

```json
{
  "permissions": {
    "git_commit": "ask",
    "git_push":   "ask",
    "git_add":    "auto",
    "git_status": "auto",
    "git_diff":   "auto",
    "git_log":    "auto"
  }
}
```

Modos: `auto` (sin confirmación), `ask` (pide confirmación), `deny` (bloquea).
