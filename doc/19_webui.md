# 19 — WebUI *(beta)*

> **Estado:** El WebUI ha alcanzado el estado **beta** (v0.4.0). La interfaz es estable, está cubierta por la suite de tests y la paridad de características con el TUI es completa. El **TUI sigue siendo la interfaz de referencia** en rendimiento; el WebUI es la opción recomendada para uso desde navegador o extensiones de editor. Se aceptan issues y PRs.

## Descripción

OOCode WebUI es una interfaz web integrada con `AgentLoop` (el mismo motor que el TUI). Proporciona acceso web a las funcionalidades de OOCode: chat, configuración, gestión de agentes, diagnóstico y más.

**Backend:** Flask + Server-Sent Events (SSE) para streaming en tiempo real  
**Fichero:** `webui/app.py`  
**Puerto por defecto:** 4000

## Arranque

```bash
# Desde la CLI
python oocode.py --webserver start

# Desde el REPL TUI
/webserver start

# Verificar estado
python oocode.py --webserver status
/webserver status
```

Acceso: `http://localhost:4000`

Para parar el WebUI:
```bash
python oocode.py --webserver stop
/webserver stop
```

## Características

- Chat en tiempo real con streaming via SSE
- **Salida idéntica al TUI**: mismos símbolos `●/│/◐/⎿/◈/✔/◼/◻`, fuente monoespaciada, bloques de tools colapsables al estilo pipa
- **Indicador "Pensando"** encima del prompt: palabras inventadas ciclantes (`Cavilando…`, `Tokenizando…`…) y frases de preflight. Es **estado puro**: NO muestra títulos de herramientas — el detalle de cada tool aparece en su bloque dentro de la conversación (corrección 2026-06-04)
- **Status bar reubicada bajo el prompt (paridad TUI)** — orden de arriba abajo: indicador "Pensando" → prompt → team-bar → **status bar** (agente · modelo · barra de contexto `▱▱▱▱▱▱▱▱▱▱` · tareas · badges MCP/LSP/MEM/RAG/EMBED/VIS/ELEV · tokens) → filas de detalle MCP/LSP. Igual que el toolbar del TUI (línea principal arriba, detalle MCP/LSP debajo). Es una barra única (antes había una superior duplicada; se eliminó en v0.4.2)
- **Team-bar de una sola línea (cabecera de equipo)** — cuando hay subagentes activos, muestra una cabecera compacta: `📋 Agente principal 💬 💻 Subagente · N subagente(s)` (con `✓` delante de los terminados). El **detalle largo** de cada subagente (su tarea, plan, texto y herramientas) vive en su **bloque dentro de la conversación**, no en la barra de status. Auto-descubre también los subagentes de `team`/`fanout`. La tarea encomendada se siembra al principio del bloque del subagente al arrancar (`subagent_start`)
- **Preguntas del agente (`ask_user`)** — cuando el agente necesita una decisión, muestra una **tarjeta de preguntas** (una o varias, con opciones, multiselección y texto libre) y espera tu respuesta; al enviar, un bloque `● User answered OOCode's questions` recoge lo elegido antes de continuar
- **Aprobación de planes (plan-mode)** — con `/plan on`, el plan se presenta como una pregunta (Aprobar/Editar/Cancelar) antes de ejecutarse
- **Confirmación de permisos** (opt-in, `webui.permissionPrompt`) — las herramientas que requieren permiso muestran una tarjeta Sí/No/Siempre; solo si hay navegador conectado (si no, auto-aprueba para no colgar el uso headless)
- **Cola de entrada** — puedes escribir mientras el agente trabaja: los slash de display pasan al momento; los mensajes y slash mutadores se encolan y se procesan al terminar el turno
- Planes multi-tarea con estado `✔/◼/◻` actualizables en tiempo real
- Markdown-to-HTML con resaltado de código
- Archivos adjuntos (imágenes y ficheros de texto)
- Panel MCP/LSP status con estado de servidores activos
- Barra de contexto (tokens usados/disponibles) con alerta visual al acercarse al límite
- Panel de task progress con estado de tareas activas
- Temas claro/oscuro
- Diseño responsive para móvil
- Historial de sesiones
- Gestión de agentes (ver, lanzar, controlar)
- Diagnóstico del sistema (consciente del backend: ollama/openai/anthropic)
- **Configuración visual completa** de `oocode.json`: Backend LLM (api: type/key/host/extraHosts/embedHost/routing/retry), Modelo, WebUI, Contexto, Herramientas, RAG, Embeddings, SearXNG, MCP Servers, Hooks, Subagentes (incl. autoContMax/inferenceTimeout/defaultTimeout), Backups, Snapshots, Logging, Visión, Chat log, Fallback, Apariencia

## Páginas

| Ruta | Descripción |
|------|-------------|
| `/` | Dashboard: estado del sistema, modelo, hooks activos, plugins |
| `/chat` | Chat interactivo con streaming en tiempo real |
| `/config` | Editor visual de `oocode.json`: modelos, hooks, permisos, MCP |
| `/sessions` | Historial de sesiones del agente activo |
| `/agents` | Subagentes activos, spawn, steer, kill |
| `/doctor` | Diagnóstico: dependencias, herramientas, LSP, MCP |
| `/theme` | Cambio entre temas claro/oscuro |
| `/help` | Referencia de slash commands |

## API REST

Todos los endpoints devuelven JSON salvo los SSE:

### Chat

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/chat/send_sync` | POST | Enviar mensaje (síncrono, espera respuesta completa) |
| `/api/chat/send` | POST | Enviar mensaje (inicia streaming) |
| `/api/chat/stream` | GET | SSE: recibe chunks del streaming activo |
| `/api/chat/status` | GET | Estado del chat: modelo, agente, contexto % |
| `/api/chat/history` | GET | Historial de mensajes de la conversación de la sesión |
| `/api/chat/input_history` | GET | Historial de input del prompt (flecha arriba), **compartido con el TUI** (`~/.oocode/history`) |
| `/api/chat/load_session` | POST | Restaura una sesión pasada (contexto + conversación), reusando `AgentLoop.restore_session` |
| `/api/chat/answer` | POST | Respuestas del usuario a un `ask_user` (evento SSE `question`): `{"answers":[{"selection":[idx],"free_text":"…"}]}` — desbloquea el turno |
| `/api/chat/permission` | POST | Respuesta a un prompt de permiso (evento SSE `permission`): `{"choice":"s"\|"n"\|"siempre"}` (requiere `webui.permissionPrompt`) |
| `/api/chat/clear` | POST | Limpiar historial de la sesión |

#### Ejemplo: enviar mensaje síncrono

```bash
curl -X POST http://localhost:4000/api/chat/send_sync \
  -H "Content-Type: application/json" \
  -d '{"message": "¿qué ficheros hay en el directorio actual?"}'
```

Respuesta:
```json
{
  "response": "Los ficheros en el directorio actual son: ...",
  "session_id": "abc123",
  "tokens_used": 342
}
```

#### Ejemplo: streaming con SSE

```javascript
// Paso 1: enviar mensaje
fetch('/api/chat/send', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({message: 'analiza main.py'})
});

// Paso 2: conectar al stream SSE
const es = new EventSource('/api/chat/stream');
es.onmessage = (e) => {
  const data = JSON.parse(e.data);
  if (data.type === 'text') process(data.content);
  if (data.type === 'tool_start') showThinking(data.tool);
  if (data.type === 'tool_done') hideThinking();
  if (data.type === 'done') es.close();
};
```

**Tipos de eventos SSE:**

| Tipo | Descripción |
|------|-------------|
| `text` | Chunk de texto del LLM |
| `tool_start` | Inicio de ejecución de herramienta (incluye nombre y args). `spawn_subagent` **no** emite este evento del agente principal: se representa con `subagent_start` + su propio bloque |
| `tool_done` | Fin de ejecución de herramienta (incluye resultado resumido y `file_path` si aplica) |
| `plan` | Actualización del plan multi-tarea (`◈`) |
| `subagent_start` | Inicio de un subagente (incluye `agent_id`, `task`) |
| `subagent_text` | Chunk de texto producido por un subagente |
| `subagent_tool` | Tool call de un subagente (en bloque expandible) |
| `subagent_done` | Subagente terminado (incluye resultado) |
| `inference_done` | Fin de inferencia (muestra "⚡ Inferencia completada." en el chat) |
| `done` | Fin del turno |
| `error` | Error durante la ejecución |

El output de los subagentes fluye al WebUI via SSE en tiempo real, de la misma forma que en el TUI. Cada subagente vive en **un único bloque expandible** dentro de la conversación, con encabezado `💻 Subagente` que el usuario puede plegar/desplegar. Al arrancar (`subagent_start`) el bloque se siembra con la **tarea encomendada**; luego se llenan ahí su texto, su plan y sus herramientas mientras corre — todo se mantiene dentro del mismo bloque (sin que se "escapen" textos fuera). La cabecera de equipo de la status bar solo muestra el resumen de una línea (ver *Características*). `spawn_subagent` ya no genera un bloque de herramienta huérfano del agente principal.

### Sesiones

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/sessions` | GET | Lista de sesiones del agente activo |
| `/api/status` | GET | Estado completo del sistema |

**Persistencia y recuperación (paridad TUI):**

- **Sesiones (conversación):** TUI y WebUI persisten cada sesión en el mismo JSONL (`~/.oocode/sessions/<agent_id>/<id>.jsonl`) vía `SessionManager`. El panel 📚 *Sesiones* del WebUI restaura una sesión pasada con el botón *Cargar* (`POST /api/chat/load_session`) o con `/session <id>` en el chat; ambos reusan `AgentLoop.restore_session` igual que el `/session` del TUI, recargando el contexto del LLM y re-renderizando la conversación.
- **Historial de input del prompt (flecha arriba):** compartido con el TUI en `~/.oocode/history` (formato `prompt_toolkit FileHistory`). El WebUI lo lee al conectar (`/api/chat/input_history`) y escribe **solo** lo que teclea el usuario, con cada línea prefijada por `+` para que los mensajes multilínea sean compatibles. Las respuestas del agente nunca se mezclan ahí.

### Agentes

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/agents` | GET | Lista de subagentes activos y recientes |
| `/api/agents/spawn` | POST | Lanzar nuevo subagente |
| `/api/agents/kill/<run_id>` | POST | Detener subagente |
| `/api/agents/steer/<run_id>` | POST | Inyectar instrucción al subagente |
| `/api/agents/stream` | GET | SSE: eventos de subagentes en tiempo real |

### Configuración

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/config` | GET | Configuración actual (desde OOConfig) |
| `/api/config/raw` | GET | oocode.json crudo |
| `/api/config/save` | POST | Guardar cambios en oocode.json |

## Configuración del WebUI

El bloque `webui` de `oocode.json`:

```json
{
  "webui": {
    "host": "0.0.0.0",
    "port": 4000,
    "permissionPrompt": false
  }
}
```

- `permissionPrompt` (default `false`): si `true`, las herramientas que requieren permiso preguntan en el navegador (Sí/No/Siempre) **solo cuando hay un cliente SSE conectado**; sin navegador (VIM/`send_sync`/pestaña cerrada) auto-aprueba para no colgar el turno.

O con override de CLI:
```bash
python oocode.py --webserver start   # usa config de oocode.json
```

Estado de sesión runtime en `~/.oocode/webui_state.json`.  
Clave secreta de sesión Flask en `~/.oocode/webui_secret.key` (generada automáticamente).

## Uso desde extensiones

### Extensión VIM

La extensión VIM se comunica con el WebUI via REST + SSE. Ver `doc/21_extensions.md` para configuración completa.

### Extensión VSCode

La extensión VSCode también usa la API REST del WebUI. Ver `doc/21_extensions.md`.

## Troubleshooting

```bash
# Verificar que el WebUI está corriendo
/webserver status
curl http://localhost:4000/api/status

# Verificar puerto
ss -tlnp | grep 4000

# Reiniciar si hay problemas
/webserver restart

# Ver logs del WebUI
cat ~/.oocode/logs/webui.log
```

## Arquitectura interna

```
webui/app.py  (Blueprint modular — 13 módulos)
├── page_chat.py         — chat con SSE streaming
├── page_config.py       — editor visual de oocode.json
├── page_sessions.py     — historial de sesiones
├── page_agents.py       — subagentes: lista, spawn, steer, kill
├── page_doctor.py       — diagnóstico del sistema
├── page_misc.py         — dashboard, theme, help
├── api_chat.py          — /api/chat/* (send, send_sync, stream, status, history, clear)
├── api_agents.py        — /api/agents/* (spawn, kill, steer, stream)
├── api_config.py        — /api/config/* (get, raw, save)
├── api_status.py        — /api/status
├── api_sessions.py      — /api/sessions
├── sse.py               — generador SSE compartido + queue
└── state.py             — estado global del WebUI (AgentLoop, locks, queues)
```

El WebUI carga `AgentLoop` completo con todos los componentes:
- `OOConfig` desde `~/.oocode/oocode.json`
- `EmbeddingClient` + `MemorySystem`
- `MCPClient` con todos los servidores bundled activos
- `ToolRegistry` con todas las herramientas nativas
- `SessionManager`, `WorkspaceManager`, etc.

El output del `AgentLoop` se propaga al WebUI via `_webui_queue` (una `queue.SimpleQueue` inyectada en el loop). Los subagentes también inyectan su output en la misma queue con el marcador `subagent=True`, de modo que el WebUI puede distinguir el output del agente principal del de sus sub-agentes.

La conversación persiste en el servidor: cambiar de pestaña o reconectar al SSE no pierde el contexto.
