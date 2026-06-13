" OOCode VIM Plugin — Wrapper completo del TUI OOCode local
" Repositorio: https://github.com/burzumishi/oocode
" Versión:     3.2.0
"
" INSTALACIÓN (vim-plug):
"   Plug 'burzumishi/oocode', { 'rtp': 'extensions/vim' }
"
" INSTALACIÓN MANUAL:
"   cp -r extensions/vim/* ~/.vim/
"
" CONFIGURACIÓN:
"   let g:oocode_host             = 'http://localhost:4000'  " URL WebUI (auto-detectado)
"   let g:oocode_agent            = 'main'                   " Agente activo
"   let g:oocode_split            = 'vertical'               " 'vertical'|'horizontal'|'tab'
"   let g:oocode_width            = 50                       " Ancho del split vertical
"   let g:oocode_height           = 15                       " Alto del split horizontal
"   let g:oocode_auto_open        = 0                        " Abrir panel al arrancar
"   let g:oocode_verbose          = 0                        " Mensajes de depuración
"   let g:oocode_inject_file_hint = 1                        " Inyectar fichero+línea en mensajes (0=off)
"
" USO RÁPIDO:
"   :OOCode <mensaje>        — Envía mensaje al agente (streaming en tiempo real)
"   :OOCodeAsk               — Prompt interactivo
"   :OOCodeContext           — Envía fichero actual como contexto
"   :OOCodeSelection         — Envía selección visual como contexto
"   :OOCodeExplain           — Explica el código bajo el cursor / selección
"   :OOCodeReview            — Pide revisión de la selección
"   :OOCodeTUI               — Abre el TUI completo embebido en terminal
"   :OOCodeOpen/Close/Toggle — Gestiona el panel de respuestas
"   :OOCodeKill              — Interrumpe el turno activo del agente
"   :OOCodeElevated [modo]   — Cicla/establece elevated (ask|off|on|full)
"   :OOCodeStatus            — Estado del agente (modelo, ctx%, hooks)
"   :OOCodeConnect           — Fuerza re-detección del servidor
"   :OOCodeWebUI             — Abre el WebUI en el navegador
"   :OOCodeWebServer start|stop|restart|status
"   :OOCodeNew               — Nueva sesión (resetea contexto)
"   :OOCodeSwitch <agent_id> — Cambia el agente activo
"   :OOCodeAgents            — Lista subagentes activos y recientes
"   :OOCodeSessions          — Historial de sesiones
"   :OOCodeDoctor            — Diagnóstico del sistema
"   :OOCodeCmd <slash_cmd>   — Envía cualquier slash command al agente

if exists('g:loaded_oocode') | finish | endif
let g:loaded_oocode = 1

" ── Configuración por defecto ──────────────────────────────────────────────
let g:oocode_host             = get(g:, 'oocode_host',             'http://localhost:4000')
let g:oocode_agent            = get(g:, 'oocode_agent',            'main')
let g:oocode_split            = get(g:, 'oocode_split',            'vertical')
let g:oocode_width            = get(g:, 'oocode_width',            52)
let g:oocode_height           = get(g:, 'oocode_height',           15)
let g:oocode_auto_open        = get(g:, 'oocode_auto_open',        0)
let g:oocode_verbose          = get(g:, 'oocode_verbose',          0)
" Inyectar fichero activo en cada mensaje (ruta + línea del cursor). Desactiva con 0.
let g:oocode_inject_file_hint = get(g:, 'oocode_inject_file_hint', 1)
" Modo streaming SSE (1) — paridad TUI/WebUI: text/tools/plan/subagentes en vivo.
" Con 0 usa send_sync bloqueante (respuesta completa de una vez, sin streaming).
let g:oocode_stream           = get(g:, 'oocode_stream',           1)
" Timeout del turno en streaming (s): si el stream enmudece, se cierra el turno.
let g:oocode_turn_timeout     = get(g:, 'oocode_turn_timeout',     360)

" ── Comandos públicos ──────────────────────────────────────────────────────

" Chat con el agente (streaming en tiempo real)
command! -nargs=+ OOCode           call oocode#send(<q-args>)
command! -nargs=0 OOCodeAsk        call oocode#ask()
command! -nargs=0 OOCodeContext    call oocode#send_context()
command! -range   OOCodeSelection  call oocode#send_selection()
command! -range   OOCodeExplain    call oocode#explain()
command! -range   OOCodeReview     call oocode#review_selection()

" Panel de respuestas
command! -nargs=0 OOCodeOpen       call oocode#open_panel()
command! -nargs=0 OOCodeClose      call oocode#close_panel()
command! -nargs=0 OOCodeToggle     call oocode#toggle_panel()

" TUI completo embebido (acceso a todos los slash commands, streaming nativo)
command! -nargs=0 OOCodeTUI        call oocode#tui()

" Control del turno activo
command! -nargs=0 OOCodeKill       call oocode#kill()
command! -nargs=? OOCodeElevated   call oocode#elevated(<q-args>)

" Estado y conexión
command! -nargs=0 OOCodeStatus     call oocode#status()
command! -nargs=0 OOCodeConnect    call oocode#connect()
command! -nargs=0 OOCodeWebUI      call oocode#open_webui()
command! -nargs=1 OOCodeWebServer  call oocode#webserver(<q-args>)

" Sesiones y agentes
command! -nargs=0 OOCodeNew        call oocode#new_session()
command! -nargs=1 OOCodeSwitch     call oocode#switch_agent(<q-args>)
command! -nargs=0 OOCodeAgents     call oocode#agents()
command! -nargs=0 OOCodeSessions   call oocode#sessions()
command! -nargs=0 OOCodeDoctor     call oocode#doctor()

" Slash commands del TUI — completado con los más usados
command! -nargs=+ -complete=customlist,s:SlashComplete OOCodeCmd call oocode#tui_cmd(<q-args>)

function! s:SlashComplete(A, L, P) abort
    let l:cmds = [
        \ '/new', '/switch', '/doctor', '/compact', '/compact fast',
        \ '/elevated', '/elevated on', '/elevated off', '/elevated full',
        \ '/hooks', '/hooks list', '/agents', '/subagents',
        \ '/model', '/models', '/rag', '/rag reindex',
        \ '/mcp', '/lsp', '/context', '/ctx', '/checkpoint',
        \ '/steer', '/diff', '/symbols', '/lint', '/todo', '/clip',
        \ '/webserver start', '/webserver stop', '/webserver status',
        \ '/session', '/sessions', '/clear', '/copy',
    \ ]
    return filter(l:cmds, 'v:val =~# "^" . escape(a:A, "\\") ')
endfunction

" ── Mapeos por defecto ────────────────────────────────────────────────────
if !get(g:, 'oocode_no_mappings', 0)
    " <Leader>oa  — Preguntar al agente (prompt)
    nnoremap <Leader>oa :OOCodeAsk<CR>
    " <Leader>oc  — Enviar fichero actual como contexto
    nnoremap <Leader>oc :OOCodeContext<CR>
    " <Leader>os  — Enviar selección visual como contexto
    vnoremap <Leader>os :OOCodeSelection<CR>
    " <Leader>ox  — Explicar selección / código bajo cursor
    nnoremap <Leader>ox :OOCodeExplain<CR>
    vnoremap <Leader>ox :OOCodeExplain<CR>
    " <Leader>or  — Pedir revisión de la selección
    vnoremap <Leader>or :OOCodeReview<CR>
    " <Leader>ot  — Toggle panel de respuestas
    nnoremap <Leader>ot :OOCodeToggle<CR>
    " <Leader>ow  — Abrir WebUI en navegador
    nnoremap <Leader>ow :OOCodeWebUI<CR>
    " <Leader>ou  — TUI completo embebido
    nnoremap <Leader>ou :OOCodeTUI<CR>
    " <Leader>on  — Nueva sesión
    nnoremap <Leader>on :OOCodeNew<CR>
    " <Leader>ok  — Conectar / re-detectar servidor
    nnoremap <Leader>ok :OOCodeConnect<CR>
    " <Leader>oK  — Interrumpir el turno activo (Kill)
    nnoremap <Leader>oK :OOCodeKill<CR>
    " <Leader>oe  — Ciclar modo elevated (ask→off→on→full)
    nnoremap <Leader>oe :OOCodeElevated<CR>
endif

" ── Statusline ────────────────────────────────────────────────────────────
" Añade %{OOCodeStatusLine()} a tu statusline para ver el agente activo.
" Ejemplo: set statusline+=%{OOCodeStatusLine()}

" ── Auto-apertura e inicialización ────────────────────────────────────────
augroup oocode_init
    autocmd!
    if g:oocode_auto_open
        autocmd VimEnter * call oocode#open_panel()
    endif
    " Detectar servidor al arrancar VIM (silencioso)
    autocmd VimEnter * call oocode#check_server_on_start()
    " Si el servidor está activo, arrancar el stream SSE
    autocmd VimEnter * call timer_start(500, {-> s:maybe_start_sse()})
    " Limpiar job SSE al salir
    autocmd VimLeave * call s:cleanup()
augroup END

function! s:maybe_start_sse() abort
    if get(g:, 'oocode_auto_sse', 1) && oocode#server_alive() > 0
        call oocode#sse_start()
    endif
endfunction

function! s:cleanup() abort
    call oocode#sse_stop()
endfunction
