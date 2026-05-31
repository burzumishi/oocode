# 19 — WebUI *(beta / experimental)*

> **Estado:** El WebUI está en desarrollo activo. Es funcional pero aún le falta trabajo para igualar el TUI en stabilidad y fidelidad de salida. El **TUI es la interfaz de referencia**; el WebUI puede mostrar diferencias en el formato de la conversación, herramientas y planes. Se aceptan issues y PRs.

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
- Markdown-to-HTML con resaltado de código
- Archivos adjuntos
- Panel MCP/LSP status con estado de servidores activos
- Barra de contexto (tokens usados/disponibles)
- Modo "Pensando" durante ejecución de herramientas
- Panel de task progress con estado de tareas activas
- Temas claro/oscuro
- Diseño responsive para móvil
- Historial de sesiones
- Gestión de agentes (ver, lanzar, controlar)
- Diagnóstico del sistema
- Configuración visual de `oocode.json`

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
| `/api/chat/history` | GET | Historial de mensajes de la sesión |
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
| `tool_start` | Inicio de ejecución de herramienta (incluye nombre y args) |
| `tool_done` | Fin de ejecución de herramienta (incluye resultado resumido y `file_path` si aplica) |
| `plan` | Actualización del plan multi-tarea (`◈`) |
| `subagent_start` | Inicio de un subagente (incluye `agent_id`, `task`) |
| `subagent_text` | Chunk de texto producido por un subagente |
| `subagent_tool` | Tool call de un subagente (en bloque expandible) |
| `subagent_done` | Subagente terminado (incluye resultado) |
| `done` | Fin del turno |
| `error` | Error durante la ejecución |

El output de los subagentes fluye al WebUI via SSE en tiempo real, de la misma forma que en el TUI. Las herramientas de los subagentes aparecen en un bloque expandible con encabezado `↳ Subagente 💻 coding` que el usuario puede plegar/desplegar. Al finalizar, el resultado del subagente se muestra como una tarjeta con el texto completo.

### Sesiones

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/sessions` | GET | Lista de sesiones del agente activo |
| `/api/status` | GET | Estado completo del sistema |

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

El puerto y host son configurables en `oocode.json`:

```json
{
  "webui_host": "0.0.0.0",
  "webui_port": 4000
}
```

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
