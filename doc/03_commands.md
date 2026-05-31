# 03 — Referencia de comandos `/slash`

Todos los comandos empiezan con `/`. Son case-insensitive. Los argumentos van separados por espacio.

## Sesión y contexto

### `/new`
Finaliza la sesión actual (la guarda en disco), limpia el historial y abre una sesión nueva.

### `/session [id]`
Sin argumento: muestra la sesión activa con su ID y estadísticas.  
Con ID (puede ser prefijo): restaura esa sesión y carga sus mensajes en el contexto.

### `/sessions`
Lista las últimas sesiones del agente activo con fecha, modelo y número de mensajes.

### `/context`
Muestra el estado detallado del contexto:
- Tokens estimados vs máximo
- Porcentaje de uso
- Resumen acumulado (si hay compactación previa)
- Modo de contexto del workspace

### `/ctx [mini|full]`
Cambia el modo de contexto del workspace inyectado en el system prompt:
- `mini` (~150 tokens): OOCODE.md + índice de memoria + log diario reciente
- `full` (~800 tokens): todo el workspace completo

### `/compact [fast]`
Compacta el historial cuando supera el umbral de contexto:
- Sin `fast`: usa el LLM para generar un resumen de los mensajes eliminados
- Con `fast`: elimina mensajes sin generar resumen (más rápido)

### `/checkpoint`
Guarda un checkpoint manual del contexto actual en el log diario del workspace.

### `/clear`
Borra el historial de conversación manteniendo el resumen acumulado.

### `/copy [n]`
Copia la última respuesta del asistente al portapapeles. Con `n`, copia la enésima respuesta anterior.

### `/btw <pregunta>`
Realiza una pregunta rápida sin interrumpir el contexto principal.

---

## Agentes y modelos

### `/switch <agent_id>`
Cambia el agente activo en caliente (sin reiniciar). Carga el workspace, la memoria y la identidad del agente seleccionado.

```
/switch coding        # cambiar al agente de programación
/switch home_office   # cambiar al agente de ofimática
/switch reasoning     # cambiar al agente de razonamiento
/switch webcrawler    # cambiar al agente de búsqueda web
/switch main          # volver al agente principal
```

### `/agents`
Lista todos los agentes configurados con su ID, nombre, emoji, modelo y workspace.

### `/model [nombre]`
Sin argumento: muestra el modelo activo.  
Con nombre: cambia el modelo y lo guarda en `oocode.json`.

### `/models`
Lista todos los modelos disponibles en el servidor Ollama. Permite seleccionar uno interactivamente.

### `/spawn <id> <tarea>`
Lanza un subagente con el ID especificado para ejecutar una tarea en contexto aislado.

```
/spawn coding "analiza src/main.py y sugiere refactorizaciones"
/spawn home_office "crea un informe de estado del proyecto en DOCX"
```

### `/subagents`
Lista subagentes activos y recientes (últimos 30 minutos):

```
/subagents                          # listar todos
/subagents status [id]              # estado detallado
/subagents steer <id> <instrucción> # inyectar nueva instrucción
/subagents kill <id>                # detener subagente
/subagents kill all                 # detener todos
/subagents output <id>              # mostrar resultado completo
```

---

## MCP, LSP y RAG

### `/mcp`
Estado de todos los servidores MCP conectados: nombre, herramientas activas, prompts y recursos.

```
/mcp                    # estado de todos los servidores
/mcp reload <nombre>    # recargar servidor
/mcp restart <nombre>   # reiniciar servidor
```

### `/lsp [subcmd]`
Gestión de servidores LSP por extensión de fichero:

```
/lsp                    # estado de todos los servidores LSP activos
/lsp start <ext>        # arrancar servidor LSP para extensión (ej: .py, .ts)
/lsp stop <ext>         # parar servidor LSP
/lsp restart <ext>      # reiniciar servidor LSP
/lsp status             # diagnóstico completo de servidores LSP
```

### `/rag [subcmd]`
Control del índice RAG (búsqueda semántica en el workspace):

```
/rag                    # estado del índice y configuración
/rag enable             # activar RAG
/rag disable            # desactivar RAG
/rag reindex            # re-indexar workspace con progreso
```

---

## Hooks

### `/hooks`
Muestra los hooks activos en el sistema (built-in y de OOCODE.md).

### `/hooks list`
Lista completa de todos los hooks built-in disponibles con descripción.

### `/hooks builtin <nombre>`
Activa o desactiva un hook built-in (toggle):

```
/hooks builtin lint_after_write
/hooks builtin backup_before_write
/hooks builtin test_after_write
/hooks builtin interface_change_detector
/hooks builtin git_push_guard
/hooks builtin security_audit_log
```

---

## Herramientas de código

### `/diff [fichero]`
Historial de diffs visuales de la sesión actual:

```
/diff              # lista ficheros editados con +añadidas/-eliminadas
/diff parser.py    # diff completo de ficheros con ese nombre
```

### `/symbols [arg]`
Navegación de símbolos del proyecto:

```
/symbols                # genera/actualiza índice del workspace
/symbols main.py        # lista funciones/clases del fichero
/symbols NombreClase    # busca símbolo por nombre
```

### `/lint [ruta]`
Linting manual (el linting automático ocurre tras cada edición con el hook `lint_after_write`):

```
/lint              # linting del workspace completo
/lint src/main.py  # linting de un fichero concreto
```

### `/todo [subcmd]`
Gestión de TODOs y FIXMEs del código:

```
/todo              # muestra todos los TODOs del proyecto
/todo add <texto>  # añade nuevo TODO
/todo done <id>    # marca TODO como resuelto
/todo sync         # sincroniza con el código fuente
```

### `/clip <texto>`
Copia texto al portapapeles del sistema.

---

## WebUI y servidor

### `/webserver start|stop|restart|status`
Control del daemon WebUI (Flask + SSE en puerto 4000):

```
/webserver start    # arrancar WebUI en background
/webserver stop     # parar WebUI
/webserver restart  # reiniciar WebUI
/webserver status   # estado del daemon
```

---

## Sistema y diagnóstico

### `/doctor`
Diagnóstico completo del sistema:
- Conectividad con Ollama y versión
- Disponibilidad del modelo configurado y el de embeddings
- SearXNG (si configurado)
- Ficheros de configuración y workspaces
- Plugins y skills cargados
- Dependencias Python instaladas
- LSP servers y agentes disponibles
- Hooks activos

### `/init [ruta]`
Genera un fichero `OOCODE.md` en el workspace o en la ruta especificada, analizando el proyecto con el LLM.

### `/steer`
Inyecta instrucciones al agente en el turno actual, redirigiendo su comportamiento sin perder el contexto.

### `/config`
Muestra la configuración completa en tablas por sección.

### `/config edit`
Panel interactivo para editar la configuración sección por sección. Los cambios se guardan en `oocode.json`.

### `/logs [n]`
Muestra las últimas `n` líneas del fichero de log (defecto: 40).

---

## Memoria

### `/mem list`
Lista todas las memorias guardadas.

### `/mem search <query>`
Búsqueda semántica en las memorias usando embeddings.

### `/mem show <nombre>`
Muestra el contenido completo de una memoria específica.

### `/mem save <nombre>`
Guarda el siguiente mensaje del usuario como una memoria.

### `/mem rm <nombre>`
Elimina una memoria permanentemente.

### `/mem rebuild`
Recalcula los embeddings de todas las memorias.

---

## Extensiones (plugins y skills)

### `/plugins [subcmd]`

```
/plugins                     # lista plugins
/plugins enable <nombre>     # activa y carga herramientas
/plugins disable <nombre>    # desactiva
/plugins reload              # recarga todos los plugins activos
/plugins create <nombre>     # crea plantilla de plugin nuevo
```

### `/skills [subcmd]`

```
/skills                      # lista skills
/skills enable <nombre>      # activa
/skills disable <nombre>     # desactiva
/skills create <nombre>      # crea plantilla de skill nuevo
```

---

## Color y apariencia

### `/color [nombre|list|save|rm]`

```
/color              # aplica un color aleatorio
/color list         # lista temas disponibles
/color cyan         # aplica color base directamente
/color neon         # tema predefinido (neon=cyan, forest=green, ocean=blue…)
/color save <nombre># guarda el esquema actual
/color rm <nombre>  # elimina un tema guardado
```

---

## Resumen de todos los comandos

| Comando | Descripción |
|---------|-------------|
| `/new` | Nueva sesión |
| `/switch <id>` | Cambiar agente |
| `/agents` | Listar agentes |
| `/session [id]` | Sesión activa / restaurar |
| `/sessions` | Historial de sesiones |
| `/context` | Estado del contexto |
| `/ctx [mini|full]` | Modo de contexto |
| `/compact` | Compactar contexto |
| `/checkpoint` | Guardar checkpoint |
| `/clear` | Limpiar historial |
| `/copy [n]` | Copiar respuesta |
| `/model [nombre]` | Ver / cambiar modelo |
| `/models` | Seleccionar modelo |
| `/spawn <id> <tarea>` | Lanzar subagente |
| `/subagents` | Control de subagentes |
| `/mcp` | Estado de servidores MCP |
| `/lsp [subcmd]` | Gestión LSP |
| `/rag [subcmd]` | Control RAG |
| `/hooks` | Hooks activos |
| `/hooks list` | Lista de hooks |
| `/hooks builtin <nombre>` | Activar/desactivar hook |
| `/diff [fichero]` | Historial de diffs |
| `/symbols [arg]` | Símbolos del proyecto |
| `/lint [ruta]` | Linting manual |
| `/todo [subcmd]` | Gestión de TODOs |
| `/clip <texto>` | Copiar al portapapeles |
| `/webserver start|stop|status` | Control WebUI |
| `/doctor` | Diagnóstico del sistema |
| `/init [ruta]` | Generar OOCODE.md |
| `/steer` | Inyectar instrucciones |
| `/config [edit]` | Ver / editar config |
| `/logs [n]` | Últimas líneas del log |
| `/mem [subcmd]` | Gestión de memorias |
| `/plugins [subcmd]` | Gestión de plugins |
| `/skills [subcmd]` | Gestión de skills |
| `/color [subcmd]` | Tema de color |
| `/btw <pregunta>` | Pregunta rápida |
| `/help` | Ayuda completa |
| `/exit` | Salir de OOCode |
