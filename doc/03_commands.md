# 03 — Referencia de comandos `/slash`

Todos los comandos empiezan con `/`. Son case-insensitive. Los argumentos van separados por espacio.

## Sesión y contexto

### `/new` `/reset`
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

### `/resume`
Resume el contexto actual con el LLM y limpia el historial, manteniendo solo el resumen como memoria de la sesión.

### `/checkpoint`
Guarda un checkpoint manual del contexto actual en el log diario del workspace.

### `/branch [subcmd]`
Gestión de ramas de conversación (snapshots):
```
/branch save <nombre>   # guarda el estado actual de la conversación
/branch load <nombre>   # restaura un snapshot guardado
/branch list            # lista todas las ramas disponibles
/branch rm <nombre>     # elimina una rama
```

### `/clear`
Borra el historial de conversación manteniendo el resumen acumulado.

### `/usage [modo]`
Controla la visualización del uso de tokens:
- `off` — no muestra uso
- `tokens` — muestra tokens de entrada/salida por turno (defecto)
- `full` — muestra también totales de sesión y porcentaje de contexto

### `/copy [n]`
Copia la última respuesta del asistente al portapapeles. Con `n`, copia la enésima respuesta anterior. Usa `wl-copy` (Wayland), `xclip`, `xsel`, `pbcopy` (macOS) o `pyperclip` como fallback.

### `/btw <pregunta>`
Realiza una pregunta rápida sin interrumpir el contexto principal. El contexto actual se guarda, se abre un contexto nuevo para la pregunta, y al terminar se restaura el original.

---

## Memoria

### `/mem list`
Lista todas las memorias guardadas con nombre, fecha y tamaño.

### `/mem search <query>`
Búsqueda semántica en las memorias usando embeddings. Devuelve los fragmentos más relevantes.

### `/mem show <nombre>`
Muestra el contenido completo de una memoria específica.

### `/mem save <nombre>`
Guarda el siguiente mensaje del usuario como una memoria con ese nombre.

### `/mem rm <nombre>`
Elimina una memoria permanentemente (pide confirmación).

### `/mem rebuild`
Recalcula los embeddings de todas las memorias (útil tras cambiar el modelo de embeddings).

### `/mem clear`
Elimina TODAS las memorias (pide confirmación explícita).

---

## Tareas y planificación

### `/tasks [subcmd]`
```
/tasks                         # lista todas las tareas
/tasks list [todo|wip|done]    # filtra por estado
/tasks add <título>            # nueva tarea en estado "todo"
/tasks wip <id>                # marca como "en progreso"
/tasks done <id>               # marca como completada
/tasks rm <id>                 # elimina la tarea
/tasks clear                   # elimina todas las "done"
```

Estados: `○ todo` → `◐ wip` → `● done`

Los IDs son los primeros 8 caracteres del UUID. Se puede usar un prefijo único.

### `/schedule [subcmd]`
```
/schedule                         # lista jobs
/schedule add <min> <comando>     # nuevo job cada N minutos
/schedule run <id>                # ejecuta un job manualmente
/schedule toggle <id>             # activa/desactiva
/schedule rm <id>                 # elimina
```

Los jobs se ejecutan con `bash` cuando el usuario interactúa y ha pasado el intervalo.

---

## Extensiones

### `/skills [subcmd]`
```
/skills                      # lista skills (nombre, estado, herramientas)
/skills list
/skills create <nombre>      # crea plantilla en ~/.oocode/skills/
/skills enable <nombre>      # activa y guarda en oocode.json
/skills disable <nombre>     # desactiva y guarda en oocode.json
```

Ver `doc/08_skills.md` para detalles de desarrollo.

### `/plugins [subcmd]`
```
/plugins                     # lista plugins
/plugins list
/plugins create <nombre>     # crea plantilla en ~/.oocode/plugins/
/plugins enable <nombre>     # activa, carga herramientas, guarda en oocode.json
/plugins disable <nombre>    # desactiva y guarda en oocode.json
/plugins reload              # recarga todos los plugins activos
```

Ver `doc/07_plugins.md` para detalles de desarrollo.

### `/add-dir [ruta]`
```
/add-dir                     # lista directorios adicionales activos
/add-dir /ruta/al/proyecto   # añade directorio al contexto de trabajo
/add-dir rm /ruta            # elimina directorio
```

Los directorios adicionales se inyectan en el system prompt para que el agente los tenga en cuenta.

---

## Modos de respuesta

### `/think <nivel>`
Ajusta la profundidad de razonamiento:
- `off` — respuesta directa (defecto)
- `minimal` — conciso y directo
- `low` — paso a paso
- `medium` — considera múltiples enfoques
- `high` — razonamiento exhaustivo con casos extremos

### `/reasoning <on|off>`
Activa/desactiva la cadena de razonamiento explícita (chain-of-thought).

### `/fast <on|off>`
Modo rápido: cambia temporalmente a un modelo más ligero definido en la configuración.

### `/verbose <on|off>`
Muestra los argumentos completos y resultados de cada llamada a herramienta.

### `/trace <on|off>`
Muestra información del system prompt y estadísticas de contexto en cada turno.

---

## Color y temas

### `/color`
Sin argumentos: aplica un color **aleatorio** del repertorio disponible.

### `/color list`
Lista todos los temas disponibles: predefinidos (builtin) y guardados por el usuario.

### `/color <nombre>`
Aplica un tema predefinido o guardado por nombre:
- `neon` (cyan), `forest` (green), `ocean` (blue), `sakura` (magenta)
- `sand` (yellow), `sunset` (red), `snow` (white)

También acepta colores base directamente: `cyan`, `green`, `blue`, `magenta`, `yellow`, `red`, `white`.

### `/color save <nombre>`
Guarda el esquema de color actual con un nombre en `~/.oocode/themes.json`.

### `/color rm <nombre>`
Elimina un tema guardado por el usuario (los predefinidos no se pueden eliminar).

---

## Permisos y activación

### `/elevated [modo]`
Nivel de permisos global:
- `off` — solo lectura (bash, write_file, edit_file denegados)
- `on` — permisos estándar con confirmación
- `ask` — todo requiere confirmación (defecto)
- `full` — todo automático sin confirmación

### `/activation <modo>`
- `always` — el agente responde a todo (defecto)
- `mention` — solo responde si el mensaje empieza con el nombre del agente

---

## Agentes y modelos

### `/model [nombre]`
Sin argumento: muestra el modelo activo.  
Con nombre: cambia el modelo y lo guarda en `oocode.json`.

### `/models`
Lista todos los modelos disponibles en el servidor Ollama con tamaño y detalles. Permite seleccionar uno interactivamente.

### `/workspace [ruta]`
Sin argumento: muestra el workspace activo.  
Con ruta: cambia el workspace del agente.

### `/spawn <id> <tarea>`
Lanza un subagente con el ID especificado para ejecutar una tarea en un contexto aislado (workspace propio, historial independiente).

**Restricción de VRAM:** el sub-agente siempre usa el mismo modelo de inferencia y el mismo modelo de embeddings que el agente principal. Esto garantiza que solo un LLM esté cargado en GPU a la vez (junto con el modelo de embeddings nomic). El sub-agente comparte el `EmbeddingClient` del padre; no abre conexiones adicionales.

La ejecución es **síncrona**: el agente principal espera el resultado del sub-agente antes de continuar. No hay paralelismo de modelos.

---

## Sistema

### `/status`
Estado general del agente: ID, modelo, contexto, flags activos, sesión.

### `/gateway-status`
Estado del servidor Ollama: conectividad, modelos disponibles, modelo de embeddings.

### `/config`
Muestra la configuración completa en tablas por sección.

### `/config edit`
Panel interactivo para editar la configuración sección por sección. Los cambios se guardan en `oocode.json`.

### `/doctor`
Diagnóstico completo del sistema:
- Conectividad con Ollama
- Disponibilidad del modelo configurado y el de embeddings
- Conectividad con SearXNG (si configurado)
- Ficheros de configuración
- Plugins y skills cargados
- Dependencias Python instaladas

### `/logs [n]`
Muestra las últimas `n` líneas del fichero de log (defecto: 40). Las líneas se colorean por nivel: rojo para errores, amarillo para warnings, gris para debug.

### `/init [ruta]`
Genera un fichero `OOCODE.md` en el workspace o en la ruta especificada, analizando el proyecto con el LLM.

### `/diff [fichero]`
Historial de diffs visuales de la sesión actual. Los diffs se generan automáticamente tras cada `edit_file`/`write_file` vía el builtin hook `diff_after_write`.
```
/diff            # lista ficheros editados con +añadidas/-eliminadas
/diff parser.py  # diff completo de ficheros cuyo nombre contenga "parser.py"
```

### `/symbols [arg]`
Navegación de símbolos usando universal-ctags (indexación automática vía `ctags_after_write`):
```
/symbols                # genera/actualiza índice del workspace
/symbols mi_fichero.py  # lista funciones/clases/métodos del fichero
/symbols NombreClase    # busca símbolo por nombre en el proyecto
```

### `/lint [ruta]`
Linting manual sobre un fichero o directorio (el linting automático ya ocurre tras cada edición):
```
/lint              # linting del workspace completo (ruff, mypy, shellcheck)
/lint src/main.py  # linting de un fichero concreto
```

Las herramientas git completas (`git_status`, `git_diff`, `git_log`, `git_add`, `git_commit`, `git_push`, `git_pull`, `git_branch`, `git_stash`, `git_patch`, `git_clone`, `git_worktree`) están disponibles directamente como tools del agente vía MCP. Ver `doc/13_git_plugin.md`.

### `/review`
Ejecuta `git diff` y pide al agente que revise los cambios actuales.

### `/help`
Muestra la ayuda completa con todos los comandos agrupados por categoría.

### `/commands`
Lista compacta de todos los comandos sin descripciones.

### `/exit` `/quit` `/q`
Sale de OOCode guardando la sesión actual.
