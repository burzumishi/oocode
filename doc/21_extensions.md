# 21 — Extensiones para editores

OOCode incluye extensiones para VIM/Neovim y VSCode que conectan con el WebUI via API REST y SSE para streaming en tiempo real.

---

## Extensión VIM / Neovim

**Versión:** 3.0.0  
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

### Características del panel lateral

- **Streaming en tiempo real** via SSE: el texto aparece mientras el LLM lo genera
- **Markdown renderizado**: cabeceras, código, listas, tablas con resaltado de sintaxis
- **Indicador "Pensando"** durante la ejecución de herramientas
- **Inyección de contexto automática**: cuando `g:oocode_inject_file_hint = 1`, cada mensaje incluye automáticamente `[fichero: ruta, línea: N, tipo: python]`
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

```
Editor (VIM / VSCode)
  │
  ├── REST POST /api/chat/send_sync    — mensaje usuario
  │         ↓ respuesta completa
  │
  └── SSE  GET  /api/chat/stream       — streaming en tiempo real
         │ chunk text
         │ tool_start event
         │ tool_done event
         └── done event
```

El WebUI mantiene un `AgentLoop` persistente: la conversación sobrevive entre reconexiones del editor.
