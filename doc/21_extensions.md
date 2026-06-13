# 21 — Extensiones para editores

OOCode incluye extensiones para VIM/Neovim y VSCode que conectan con el WebUI via API REST y SSE para streaming en tiempo real.

---

## Extensión VIM / Neovim

**Versión:** 3.2.0  
**Ubicación:** `extensions/vim/`  
**Requisito:** el WebUI debe estar corriendo (`/webserver start` o `python oocode.py --webserver start`)

### Instalación

Con **vim-plug**:
```vim
" ~/.config/nvim/init.vim o ~/.vimrc
call plug#begin()
Plug 'burzumishi/oocode', { 'rtp': 'extensions/vim' }
call plug#end()
```

Luego en VIM:
```
:PlugInstall
```

**Instalación manual:**
```bash
cp -r /path/to/oocode/extensions/vim/* ~/.vim/
# o para Neovim:
cp -r /path/to/oocode/extensions/vim/* ~/.config/nvim/
```

### Configuración

Añade en tu `init.vim` o `.vimrc`:
```vim
" URL del WebUI (auto-detectado si no se especifica)
let g:oocode_host = 'http://localhost:4000'

" Agente activo por defecto
let g:oocode_agent = 'main'

" Tipo de split: 'vertical', 'horizontal', 'tab'
let g:oocode_split = 'vertical'

" Ancho del panel lateral (para split vertical)
let g:oocode_width = 52

" Alto del panel (para split horizontal)
let g:oocode_height = 15

" Abrir panel automáticamente al arrancar VIM
let g:oocode_auto_open = 0

" Mensajes de depuración
let g:oocode_verbose = 0

" Inyectar ruta del fichero + línea + filetype en cada mensaje
let g:oocode_inject_file_hint = 1

" Modo streaming SSE (1) — paridad TUI/WebUI: texto, tools, plan y subagentes
" en vivo. Con 0 usa send_sync bloqueante (respuesta completa de una vez).
let g:oocode_stream = 1

" Timeout del turno en streaming (s): cierra el turno si el stream enmudece
let g:oocode_turn_timeout = 360

" Desactivar mappings de teclado por defecto
" let g:oocode_no_mappings = 1
```

### Comandos

| Comando | Descripción |
|---------|-------------|
| `:OOCode <mensaje>` | Envía mensaje al agente (streaming en tiempo real) |
| `:OOCodeAsk` | Prompt interactivo para escribir el mensaje |
| `:OOCodeContext` | Envía el fichero actual completo como contexto |
| `:OOCodeSelection` | Envía la selección visual como contexto |
| `:OOCodeExplain` | Explica el código bajo el cursor o la selección |
| `:OOCodeReview` | Pide revisión de la selección |
| `:OOCodeTUI` | Abre el TUI completo de OOCode en un terminal embebido |
| `:OOCodeOpen` | Abre el panel lateral de respuestas |
| `:OOCodeClose` | Cierra el panel lateral |
| `:OOCodeToggle` | Alterna visibilidad del panel lateral |
| `:OOCodeKill` | Interrumpe el turno activo (= botón Kill del WebUI, `/kill` en TUI) |
| `:OOCodeElevated [modo]` | Cicla/establece elevated: `ask`\|`off`\|`on`\|`full` |
| `:OOCodeStatus` | Muestra estado del agente (modelo, contexto %, hooks) |
| `:OOCodeConnect` | Fuerza re-detección del servidor WebUI |
| `:OOCodeWebUI` | Abre el WebUI en el navegador por defecto |
| `:OOCodeWebServer start\|stop\|restart\|status` | Control del WebUI daemon |
| `:OOCodeNew` | Nueva sesión (resetea contexto) |
| `:OOCodeSwitch <agent_id>` | Cambia el agente activo |
| `:OOCodeAgents` | Lista subagentes activos y recientes |
| `:OOCodeSessions` | Historial de sesiones |
| `:OOCodeDoctor` | Diagnóstico del sistema |
| `:OOCodeCmd <slash_cmd>` | Envía cualquier slash command al agente |

**Ejemplos de uso:**
```vim
:OOCode explica qué hace esta función
:OOCode añade type hints a todas las funciones del fichero
:OOCodeSwitch coding
:OOCodeCmd /compact
:OOCodeCmd /hooks
:OOCodeWebServer start
```

### Mappings de teclado

Los mappings se asignan automáticamente si `g:oocode_no_mappings` no está definido:

| Mapping | Modo | Acción |
|---------|------|--------|
| `<Leader>oa` | Normal | `:OOCodeAsk` — prompt interactivo |
| `<Leader>oc` | Normal | `:OOCodeContext` — enviar fichero actual |
| `<Leader>os` | Visual | `:OOCodeSelection` — enviar selección |
| `<Leader>ox` | Normal/Visual | `:OOCodeExplain` — explicar código |
| `<Leader>or` | Visual | `:OOCodeReview` — revisar selección |
| `<Leader>ot` | Normal | `:OOCodeToggle` — mostrar/ocultar panel |
| `<Leader>ow` | Normal | `:OOCodeWebUI` — abrir WebUI en navegador |
| `<Leader>ou` | Normal | `:OOCodeTUI` — abrir TUI completo |
| `<Leader>on` | Normal | `:OOCodeNew` — nueva sesión |
| `<Leader>ok` | Normal | `:OOCodeConnect` — reconectar servidor |
| `<Leader>oK` | Normal | `:OOCodeKill` — interrumpir el turno activo |
| `<Leader>oe` | Normal | `:OOCodeElevated` — ciclar modo elevated |

### Características del panel lateral

- **Streaming en tiempo real** via SSE: texto, tools, plan, progreso del plan y subagentes aparecen mientras el agente trabaja (mismo flujo que el WebUI)
- **Sesión compartida con el envío**: el plugin establece la cookie de sesión antes de abrir el stream, de modo que el SSE y el POST `/api/chat/send` comparten `sid` y los eventos llegan a la cola correcta (ver más abajo)
- **Subagentes**: la cabecera del subagente y sus líneas (texto + tools) se muestran prefijadas con `│`, igual que el bloque dedicado del TUI/WebUI
- **Indicador "Pensando"** y frase *preflight* mientras el modelo piensa
- **Interacción `ask_user` (v3.2)**: cuando el agente plantea preguntas, el panel las muestra y te pide la respuesta con `inputlist()` (soporta multiselección `1,3` y texto libre); la respuesta se envía a `/api/chat/answer` y el turno continúa. Igual para la **confirmación de permisos** (si `webui.permissionPrompt` está activo). Antes, un `ask_user` dejaba el turno colgado hasta el timeout. *(El prompt se difiere con un timer porque `input()` no puede invocarse desde el callback del stream SSE.)*
- **Cola y slash (v3.2)**: muestra los mensajes encolados mientras el agente trabaja y el resultado de los slash commands ejecutados en el servidor.
- **Inyección de contexto automática (v3.2)**: cuando `g:oocode_inject_file_hint = 1`, cada `:OOCode`/`:OOCodeAsk` antepone una referencia con la **ruta absoluta** del fichero abierto (+ línea/columna del cursor) y el directorio de trabajo — `[Contexto Vim — el usuario está viendo el fichero: /ruta/abs.c (línea L12:5, ft=c). Directorio de trabajo: /ruta]` — para que el agente sepa a qué te refieres y lo lea con `read_file`. En un explorador (netrw) referencia el directorio. Las rutas son siempre absolutas (el `read_file` del agente no las acota a su `project_dir`). Para enviar el **contenido** en vez de la referencia, usa `:OOCodeContext`/`:OOCodeSelection`/`:OOCodeExplain`/`:OOCodeReview`.
- **Watchdog del turno**: si el stream enmudece más de `g:oocode_turn_timeout` segundos, el turno se cierra para que el prompt no quede colgado
- **Auto-detección del servidor**: al arrancar VIM, el plugin verifica si el WebUI está disponible en el puerto configurado; si no, muestra un aviso

### Archivo de autoload

El comportamiento interno está en `extensions/vim/autoload/oocode.vim`. Las funciones clave:
- `oocode#send(msg)` — envía mensaje y muestra streaming en el panel
- `oocode#ask()` — abre prompt de VIM, llama a `oocode#send()`
- `oocode#tui()` — lanza `python oocode.py` en terminal embebido (`:terminal`)
- `oocode#open_webui()` — abre `http://localhost:4000` en el navegador

---

## Extensión VSCode

**Ubicación:** `extensions/vscode/`

### Instalación

Instalación manual desde el repositorio:
```bash
cd /path/to/oocode/extensions/vscode
npm install
npm run compile
code --install-extension *.vsix
```

O busca "OOCode" en el Marketplace de VSCode (publisher: `burzumishi`).

### Comandos disponibles en VSCode

| Comando | Descripción |
|---------|-------------|
| `OOCode: Estado` | Ver estado del agente |
| `OOCode: Listar modelos` | Modelos disponibles en Ollama |
| `OOCode: Seleccionar modelo` | Cambiar modelo activo |
| `OOCode: Listar hooks` | Hooks disponibles |
| `OOCode: Activar hook` | Activar hook específico |
| `OOCode: Listar plugins` | Plugins instalados |
| `OOCode: Activar plugin` | Activar plugin |
| `OOCode: Listar subagentes` | Subagentes activos |
| `OOCode: Lanzar subagente` | Spawn subagente |
| `OOCode: Detener subagente` | Kill subagente |
| `OOCode WebUI: Estado` | Estado del WebUI |
| `OOCode WebUI: Iniciar` | Arrancar WebUI daemon |
| `OOCode WebUI: Parar` | Parar WebUI daemon |
| `OOCode: Listar comandos` | Slash commands disponibles |
| `OOCode: Ayuda` | Documentación |

### Configuración en VSCode

En `settings.json`:
```json
{
  "oocode.host": "http://localhost:4000",
  "oocode.agent": "main",
  "oocode.injectFileHint": true
}
```

---

## Flujo de comunicación

El VIM (modo streaming, por defecto) replica el flujo del navegador WebUI:

```
Editor (VIM, g:oocode_stream=1)
  │
  ├── 1. GET  /api/chat/status   — establece la cookie de sesión (jar)   ┐
  │                                 (petición que COMPLETA → curl la vuelca)│ mismo
  ├── 2. GET  /api/chat/stream   — SSE persistente (curl -sN -b jar)      ├ sid /
  │         ↑ text · tool_start/done · plan · subagent · question ·        │ cola
  │           permission · queued · slash_result · done                    │
  └── 3. POST /api/chat/send     — dispara el turno (fire-and-forget)     ┘
            (los eventos del turno llegan por el stream del paso 2)
```

Los eventos interactivos del paso 2 que **bloquean** el turno (`question` de
`ask_user`, `permission`) se responden con un POST de vuelta: `/api/chat/answer`
y `/api/chat/permission` respectivamente. El plugin (v3.2) los maneja en paridad
con el WebUI.

**Por qué el paso 1 es imprescindible:** un curl SSE persistente nunca escribe
el cookie jar (libcurl lo vuelca al terminar la transferencia, y el stream no
termina). Sin establecer antes la cookie con una petición que completa, el POST
del paso 3 iría sin cookie, Flask crearía una sesión distinta, y los eventos
caerían en otra cola — el panel se quedaría mudo. Este era el bug del flujo
anterior, que mezclaba `send_sync` y un SSE en sesiones distintas.

Modo fallback (`g:oocode_stream=0` o VIM sin `+job`):

```
Editor (VIM)
  └── POST /api/chat/send_sync   — bloquea/espera; devuelve respuesta + tool_events
                                    (sin SSE en paralelo; sin streaming)
```

El WebUI mantiene un `AgentLoop` persistente: la conversación sobrevive entre reconexiones del editor.
