" OOCode autoload — wrapper completo del TUI (streaming SSE, tools, plan)
" Versión: 3.0.0

" ── Estado interno ────────────────────────────────────────────────────────────
let s:panel_bufname  = '__OOCode__'
let s:panel_bufnr    = -1
let s:cookie_jar     = expand('~/.oocode/vim_session.txt')
let s:state_file     = expand('~/.oocode/webui_state.json')

" SSE job (para actualizaciones de estado pasivas)
" s:stream_job es un job object en Vim8 o un channel-id (int) en Neovim.
" NO comparar s:stream_job con números directamente — usar s:stream_active.
let s:stream_job     = v:null  " job handle o v:null
let s:stream_active  = 0       " 1 = curl SSE corriendo
let s:sse_buf        = ''      " línea parcial acumulada del stream

" Job de send_sync (envío/recepción asíncrono sin SSE)
let s:sync_buf       = ''      " JSON acumulado de la respuesta send_sync
let s:sync_job       = v:null  " job del curl send_sync en curso

" Estado del turno
let s:turn_active    = 0
let s:think_lnum     = -1     " número de línea del indicador "Pensando…"
let s:agent_text_buf = []     " buffer de texto del agente (flush al done)
let s:tool_lnums     = {}     " tool → lnum para actualizar in-place
let s:turn_sep_done  = 0      " 1 si ya se imprimió el sep al inicio del turno
let s:sse_turn_shown  = 0      " 1 si SSE ya mostró la respuesta del turno actual

" Estado del agente (actualizado desde eventos SSE)
let s:agent_emoji    = '🤖'
let s:agent_name     = 'OOCode'
let s:agent_model    = '—'
let s:ctx_pct        = 0
let s:task_done      = 0
let s:task_total     = 0

" Detección del servidor
let s:server_alive    = -1   " -1=desconocido  0=inactivo  1=activo
let s:server_check_ts = 0
let s:server_ports    = [4000, 7788, 3000, 5000]

" ── Utilidades HTTP ───────────────────────────────────────────────────────────

function! s:api_url(path) abort
    return g:oocode_host . a:path
endfunction

function! s:ping_host(host) abort
    let l:url = a:host . '/api/status'
    let l:out = system(printf(
        \ 'curl -sf --connect-timeout 2 --max-time 3 %s 2>/dev/null',
        \ shellescape(l:url)
    \ ))
    return !empty(trim(l:out))
endfunction

function! s:is_server_alive() abort
    return s:ping_host(g:oocode_host)
endfunction

function! s:port_from_state() abort
    " Lee el puerto del state file; devuelve 0 si no hay info.
    if !filereadable(s:state_file)
        return 0
    endif
    try
        let l:state = json_decode(join(readfile(s:state_file), ''))
        return get(l:state, 'port', 0)
    catch
        return 0
    endtry
endfunction

function! s:post(path, data) abort
    let l:url  = s:api_url(a:path)
    let l:body = json_encode(a:data)
    let l:tmpf = tempname()
    call system(printf(
        \ 'curl -sf -c %s -b %s -X POST -H "Content-Type: application/json"'
        \ . ' --connect-timeout 3 --max-time 180 -d %s %s > %s 2>/dev/null',
        \ shellescape(s:cookie_jar), shellescape(s:cookie_jar),
        \ shellescape(l:body), shellescape(l:url), shellescape(l:tmpf)
    \ ))
    if filereadable(l:tmpf)
        let l:resp = join(readfile(l:tmpf), "\n")
        call delete(l:tmpf)
        return l:resp
    endif
    return ''
endfunction

function! s:get(path) abort
    return system(printf(
        \ 'curl -sf -c %s -b %s --connect-timeout 3 --max-time 10 %s 2>/dev/null',
        \ shellescape(s:cookie_jar), shellescape(s:cookie_jar),
        \ shellescape(s:api_url(a:path))
    \ ))
endfunction

" ── Detección automática del servidor ────────────────────────────────────────
" Escanea el port del state file y fallbacks; actualiza g:oocode_host.

function! oocode#check_server_on_start() abort
    " Construir lista de puertos a probar: state file primero, luego defaults
    let l:sp    = s:port_from_state()
    let l:ports = l:sp > 0 ? [l:sp] : []
    for l:p in s:server_ports
        if index(l:ports, l:p) < 0
            call add(l:ports, l:p)
        endif
    endfor

    " También probar el host configurado actualmente si no es localhost
    let l:hosts = []
    for l:p in l:ports
        call add(l:hosts, 'http://localhost:' . l:p)
    endfor

    " Probar cada host en orden
    for l:h in l:hosts
        if s:ping_host(l:h)
            if g:oocode_host !=# l:h
                let g:oocode_host = l:h
                if get(g:, 'oocode_verbose', 0)
                    echom 'OOCode: servidor detectado en ' . l:h
                endif
            endif
            let s:server_alive    = 1
            let s:server_check_ts = localtime()
            return
        endif
    endfor

    let s:server_alive    = 0
    let s:server_check_ts = localtime()
endfunction

function! oocode#connect() abort
    " Fuerza re-detección inmediata (útil tras /webserver start en el TUI)
    call oocode#check_server_on_start()
    if s:server_alive
        echo 'OOCode: conectado → ' . g:oocode_host
        call s:sse_ensure_running()
    else
        echohl WarningMsg
        echo 'OOCode: servidor no encontrado. Inicia con: oocode --webserver start'
        echohl None
    endif
endfunction

" ── Panel de respuestas ───────────────────────────────────────────────────────

function! s:panel_winnr() abort
    return bufwinnr(s:panel_bufname)
endfunction

function! oocode#open_panel() abort
    let l:existing = s:panel_winnr()
    if l:existing > 0
        execute l:existing . 'wincmd w'
        return
    endif

    if g:oocode_split ==# 'tab'
        tabnew
    elseif g:oocode_split ==# 'horizontal'
        execute 'botright ' . g:oocode_height . 'split'
    else
        execute 'botright ' . g:oocode_width . 'vsplit'
    endif

    enew
    execute 'file ' . s:panel_bufname
    setlocal buftype=nofile bufhidden=wipe noswapfile nobuflisted
    setlocal filetype=markdown wrap linebreak nolist
    setlocal nonumber norelativenumber winfixwidth winfixheight
    setlocal modifiable nomodifiable

    call s:panel_header()
    let s:panel_bufnr = bufnr('%')

    wincmd p
endfunction

function! oocode#close_panel() abort
    let l:w = s:panel_winnr()
    if l:w > 0 | execute l:w . 'wincmd w' | close | endif
endfunction

function! oocode#toggle_panel() abort
    if s:panel_winnr() > 0
        call oocode#close_panel()
    else
        call oocode#open_panel()
    endif
endfunction

function! s:panel_header() abort
    let l:hdr = [
        \ '# 🤖 OOCode — Panel de respuestas',
        \ '─────────────────────────────────────────',
        \ '',
    \ ]
    call s:panel_writelines(l:hdr)
endfunction

" Escribe líneas en el panel (reemplaza todo)
function! s:panel_writelines(lines) abort
    let l:w = s:panel_winnr()
    if l:w < 0 | return | endif
    let l:cur = winnr()
    execute l:w . 'wincmd w'
    setlocal modifiable
    silent! %delete _
    call setline(1, a:lines)
    execute l:cur . 'wincmd w'
endfunction

" Añade líneas al final del panel; devuelve el número de la última línea añadida.
function! s:panel_append(lines) abort
    let l:w = s:panel_winnr()
    if l:w < 0 | return -1 | endif
    let l:cur = winnr()
    execute l:w . 'wincmd w'
    setlocal modifiable
    let l:list = type(a:lines) == v:t_list ? a:lines : [a:lines]
    call append(line('$'), l:list)
    let l:lnum = line('$')
    normal! G
    setlocal nomodifiable
    execute l:cur . 'wincmd w'
    redraw
    return l:lnum
endfunction

" Actualiza una línea específica del panel in-place.
function! s:panel_setline(lnum, text) abort
    let l:w = s:panel_winnr()
    if l:w < 0 || a:lnum < 1 | return | endif
    let l:cur = winnr()
    execute l:w . 'wincmd w'
    setlocal modifiable
    call setline(a:lnum, a:text)
    execute l:cur . 'wincmd w'
    redraw
endfunction

" Elimina la línea indicada del panel.
function! s:panel_delete_line(lnum) abort
    let l:w = s:panel_winnr()
    if l:w < 0 || a:lnum < 1 | return | endif
    let l:cur = winnr()
    execute l:w . 'wincmd w'
    setlocal modifiable
    execute a:lnum . 'delete _'
    setlocal nomodifiable
    " Ajustar referencias a líneas que quedaron por debajo
    if s:think_lnum > a:lnum | let s:think_lnum -= 1 | endif
    for l:k in keys(s:tool_lnums)
        if s:tool_lnums[l:k] > a:lnum
            let s:tool_lnums[l:k] -= 1
        endif
    endfor
    execute l:cur . 'wincmd w'
endfunction

function! s:panel_clear() abort
    let s:think_lnum     = -1
    let s:tool_lnums     = {}
    let s:agent_text_buf = []
    let s:turn_sep_done  = 0
    call oocode#open_panel()
    call s:panel_writelines([
        \ '# 🤖 OOCode — Panel de respuestas',
        \ '─────────────────────────────────────────',
        \ '',
    \ ])
endfunction

" ── Actualización de status bar del panel ────────────────────────────────────

function! s:panel_update_header() abort
    let l:w = s:panel_winnr()
    if l:w < 0 | return | endif
    let l:ctx_str = s:ctx_pct > 80 ? '⚠ ctx:' . s:ctx_pct . '%'
                 \ : s:ctx_pct > 60 ? '~ ctx:' . s:ctx_pct . '%'
                 \ : 'ctx:' . s:ctx_pct . '%'
    let l:task_str = s:task_total > 0
                  \ ? '  ✔ ' . s:task_done . '/' . s:task_total
                  \ : ''
    let l:hdr = printf('# %s %s  │  %s  │  %s%s',
        \ s:agent_emoji, s:agent_name, s:agent_model, l:ctx_str, l:task_str)
    call s:panel_setline(1, l:hdr)
endfunction

" ── Indicadores de turno ──────────────────────────────────────────────────────

function! s:panel_start_turn(user_msg, is_slash) abort
    let s:turn_active    = 1
    let s:tool_lnums     = {}
    let s:agent_text_buf = []
    let s:think_lnum     = -1
    let s:sse_turn_shown = 0

    let l:sym = a:is_slash ? '⌘' : '❯'
    let l:hdr = l:sym . ' ' . a:user_msg
    call s:panel_append(['', l:hdr, ''])
    " Pensando…
    let s:think_lnum = s:panel_append('  ● Pensando…')
endfunction

function! s:panel_hide_thinking() abort
    if s:think_lnum > 0
        call s:panel_delete_line(s:think_lnum)
        let s:think_lnum = -1
    endif
endfunction

function! s:panel_end_turn() abort
    let s:turn_active = 0
    " Flush texto acumulado si lo hay
    if !empty(s:agent_text_buf)
        call s:panel_append(s:agent_text_buf)
        let s:agent_text_buf = []
    endif
    call s:panel_append(['', '─────────────────────────────────────────'])
    call s:panel_update_header()
endfunction

" ── Eventos SSE → Panel ───────────────────────────────────────────────────────

function! s:panel_on_thinking() abort
    " Asegurar que el indicador está visible
    if s:think_lnum < 0
        let s:think_lnum = s:panel_append('  ● Pensando…')
    endif
endfunction

function! s:panel_on_text(text) abort
    call s:panel_hide_thinking()
    if !empty(a:text)
        " Dividir por \n para que cada línea sea un elemento independiente del buffer
        let l:parts = split(a:text, "\n", 1)
        let s:agent_text_buf += l:parts
    endif
endfunction

function! s:panel_on_stream_chunk(text) abort
    " Acumular chunks respetando los saltos de línea del modelo
    call s:panel_hide_thinking()
    if !empty(a:text)
        let l:parts = split(a:text, "\n", 1)
        if empty(s:agent_text_buf)
            let s:agent_text_buf = l:parts
        else
            " El primer parte continúa la última línea; el resto son líneas nuevas
            let s:agent_text_buf[-1] .= l:parts[0]
            if len(l:parts) > 1
                let s:agent_text_buf += l:parts[1:]
            endif
        endif
    endif
endfunction

function! s:panel_on_tool_start(tool, ctx) abort
    call s:panel_hide_thinking()
    let l:ctx_str = empty(a:ctx) ? '' : '  ' . a:ctx[:50]
    let l:line = '  ◐ ' . a:tool . l:ctx_str . ' …'
    let l:lnum = s:panel_append(l:line)
    let s:tool_lnums[a:tool] = l:lnum
endfunction

function! s:panel_on_tool_done(tool, ok, nlines, preview) abort
    let l:sym   = a:ok ? '⎿' : '✗'
    let l:col   = a:ok ? '' : ''
    let l:detail = ''
    if a:nlines > 1
        let l:detail = '  ▸ ' . a:nlines . ' líneas'
    elseif !empty(a:preview)
        let l:detail = '  ' . a:preview[:50]
    endif
    let l:line = '  ' . l:sym . ' ' . a:tool . l:detail

    if has_key(s:tool_lnums, a:tool) && s:tool_lnums[a:tool] > 0
        call s:panel_setline(s:tool_lnums[a:tool], l:line)
        unlet s:tool_lnums[a:tool]
    else
        call s:panel_append(l:line)
    endif
endfunction

function! s:panel_on_plan(tasks, n, summary) abort
    call s:panel_hide_thinking()
    call s:panel_append(['', '  ◈  Plan de ejecución  [1/' . a:n . ']'])
    if !empty(a:summary)
        call s:panel_append('    ' . a:summary[:100])
    endif
    for l:t in a:tasks[:9]
        call s:panel_append('    ◻ ' . l:t[:70])
    endfor
    if len(a:tasks) > 10
        call s:panel_append('    … +' . (len(a:tasks)-10) . ' más')
    endif
    call s:panel_append('')
endfunction

function! s:panel_on_error(msg) abort
    call s:panel_hide_thinking()
    call s:panel_append(['', '  ✗ Error: ' . a:msg, ''])
    call s:panel_end_turn()
endfunction

function! s:handle_sse_event(ev) abort
    let l:type = get(a:ev, 'type', '')

    if l:type ==# 'connected'
        call s:panel_append('  [conectado → ' . g:oocode_host . ']')

    elseif l:type ==# 'heartbeat'
        " silencioso

    elseif l:type ==# 'thinking'
        call s:panel_on_thinking()

    elseif l:type ==# 'text'
        call s:panel_on_text(get(a:ev, 'text', ''))

    elseif l:type ==# 'stream_chunk'
        call s:panel_on_stream_chunk(get(a:ev, 'text', ''))

    elseif l:type ==# 'tool_start'
        call s:panel_on_tool_start(get(a:ev, 'tool', '?'), get(a:ev, 'context', ''))

    elseif l:type ==# 'tool_done'
        call s:panel_on_tool_done(
            \ get(a:ev, 'tool',    '?'),
            \ get(a:ev, 'ok',      1),
            \ get(a:ev, 'n_lines', 0),
            \ get(a:ev, 'preview', '')
        \ )

    elseif l:type ==# 'plan'
        call s:panel_on_plan(
            \ get(a:ev, 'tasks',   []),
            \ get(a:ev, 'n',        0),
            \ get(a:ev, 'summary', '')
        \ )

    elseif l:type ==# 'status'
        call s:update_agent_status(a:ev)

    elseif l:type ==# 'done'
        call s:update_agent_status(a:ev)
        " Flush texto
        if !empty(s:agent_text_buf)
            call s:panel_append(s:agent_text_buf)
            let s:agent_text_buf = []
        elseif !empty(get(a:ev, 'response', ''))
            call s:panel_append(split(get(a:ev, 'response', ''), "\n", 1))
        endif
        call s:panel_hide_thinking()
        let s:sse_turn_shown = 1
        call s:panel_end_turn()

    elseif l:type ==# 'error'
        call s:panel_on_error(get(a:ev, 'error', 'desconocido'))
    endif
endfunction

function! s:update_agent_status(ev) abort
    if has_key(a:ev, 'agent_emoji') | let s:agent_emoji = get(a:ev, 'agent_emoji', '🤖') | endif
    if has_key(a:ev, 'agent_name')  | let s:agent_name  = get(a:ev, 'agent_name',  'OOCode') | endif
    if has_key(a:ev, 'model')       | let s:agent_model = substitute(get(a:ev, 'model', '—'), ':latest$', '', '') | endif
    if has_key(a:ev, 'context_pct') | let s:ctx_pct     = get(a:ev, 'context_pct', 0) | endif
    if has_key(a:ev, 'task_done')   | let s:task_done   = get(a:ev, 'task_done',  0) | endif
    if has_key(a:ev, 'task_total')  | let s:task_total  = get(a:ev, 'task_total', 0) | endif
endfunction

" ── SSE Streaming job ─────────────────────────────────────────────────────────
" Conecta un curl -sN persistente al /api/chat/stream y parsea eventos en tiempo real.

function! s:process_sse_line(line) abort
    " Acumular líneas parciales (Neovim puede partir líneas)
    let l:line = s:sse_buf . a:line
    let s:sse_buf = ''

    if l:line =~# '^data: '
        let l:json = strpart(l:line, 6)
        if !empty(l:json)
            try
                let l:ev = json_decode(l:json)
                call s:handle_sse_event(l:ev)
            catch
            endtry
        endif
    endif
endfunction

" Callback Neovim: data es lista de strings (split por \n)
function! s:nvim_sse_data(jid, data, event) abort
    for l:line in a:data
        " Neovim puede enviar líneas vacías entre eventos SSE
        if !empty(l:line)
            call s:process_sse_line(l:line)
        endif
    endfor
endfunction

function! s:nvim_sse_exit(jid, code, event) abort
    let s:stream_job    = v:null
    let s:stream_active = 0
    if s:server_alive && s:turn_active
        call timer_start(2000, {-> s:sse_ensure_running()})
    endif
endfunction

" Callback Vim 8: recibe una línea por llamada
function! s:vim_sse_data(ch, line) abort
    call s:process_sse_line(a:line)
endfunction

function! s:vim_sse_exit(job, code) abort
    let s:stream_job    = v:null
    let s:stream_active = 0
    if s:server_alive
        call timer_start(2000, {-> s:sse_ensure_running()})
    endif
endfunction

function! s:sse_is_running() abort
    if !s:stream_active | return 0 | endif
    try
        if has('nvim')
            " jobwait([id], 0) devuelve -1 si el job sigue corriendo
            return type(s:stream_job) == v:t_number
                \ && s:stream_job > 0
                \ && jobwait([s:stream_job], 0)[0] ==# -1
        elseif has('job')
            return job_status(s:stream_job) ==# 'run'
        endif
    catch
        let s:stream_active = 0
    endtry
    return 0
endfunction

function! s:sse_ensure_running() abort
    if s:sse_is_running() | return | endif

    let l:url = s:api_url('/api/chat/stream?agent_id=' . g:oocode_agent)
    let l:cmd = ['curl', '-sN', '--no-buffer',
               \ '-c', s:cookie_jar, '-b', s:cookie_jar,
               \ '--connect-timeout', '5', '--max-time', '3600',
               \ l:url]

    if has('nvim')
        let s:stream_job    = jobstart(l:cmd, {
            \ 'on_stdout': function('s:nvim_sse_data'),
            \ 'on_exit':   function('s:nvim_sse_exit'),
            \ 'stdout_buffered': v:false,
        \ })
        let s:stream_active = type(s:stream_job) == v:t_number && s:stream_job > 0
    elseif has('job')
        let s:stream_job    = job_start(l:cmd, {
            \ 'out_cb':  function('s:vim_sse_data'),
            \ 'exit_cb': function('s:vim_sse_exit'),
        \ })
        " job_start devuelve un job object; marcar como activo si no es una string de error
        let s:stream_active = type(s:stream_job) != v:t_string
    else
        " Sin soporte de jobs — el envío usará send_sync bloqueante
        let s:stream_active = 0
    endif
endfunction

function! s:sse_stop() abort
    if !s:stream_active | return | endif
    try
        if has('nvim') && type(s:stream_job) == v:t_number && s:stream_job > 0
            call jobstop(s:stream_job)
        elseif has('job')
            call job_stop(s:stream_job)
        endif
    catch
    endtry
    let s:stream_job    = v:null
    let s:stream_active = 0
endfunction

function! s:has_async() abort
    return has('nvim') || (has('job') && has('lambda'))
endfunction

" ── Contexto del fichero activo ───────────────────────────────────────────────
" Devuelve una línea de contexto con el fichero abierto y la línea del cursor.
" Si no hay fichero real (buffer sin nombre, panel OOCode, etc.) devuelve ''.
function! s:file_hint() abort
    let l:file = expand('%:p')
    " Ignorar buffers sin fichero real y el propio panel OOCode
    if empty(l:file) || bufname('%') ==# s:panel_bufname
        return ''
    endif
    " Ignorar buffers especiales (terminal, quickfix, help…)
    if &buftype !=# '' && &buftype !=# 'nofile'
        return ''
    endif
    let l:lnum = line('.')
    let l:col  = col('.')
    let l:ft   = empty(&filetype) ? '' : &filetype
    let l:hint = printf('[Vim: fichero=%s  L%d:%d', l:file, l:lnum, l:col)
    if !empty(l:ft)
        let l:hint .= '  ft=' . l:ft
    endif
    let l:hint .= ']'
    return l:hint
endfunction

" ── Envío de mensajes ─────────────────────────────────────────────────────────

" s:no_hint_once: cuando es 1 la próxima llamada a send() salta la inyección de fichero
let s:no_hint_once = 0

function! oocode#send(message) abort
    if empty(trim(a:message)) | return | endif

    " Detectar servidor si es desconocido
    if s:server_alive ==# -1
        call oocode#check_server_on_start()
    endif

    " Re-comprobar si estaba marcado como caído
    if !s:server_alive
        if !s:is_server_alive()
            echohl WarningMsg
            echo 'OOCode: WebUI no responde en ' . g:oocode_host
            echo '  Inicia con: oocode --webserver start'
            echo '  O ejecuta: :OOCodeConnect'
            echohl None
            return
        endif
        let s:server_alive = 1
    endif

    call oocode#open_panel()
    let l:is_slash = a:message =~# '^\s*/'

    " Inyectar contexto del fichero activo en mensajes normales (no slash commands)
    let l:msg = a:message
    if !l:is_slash && get(g:, 'oocode_inject_file_hint', 1) && !s:no_hint_once
        let l:hint = s:file_hint()
        if !empty(l:hint)
            let l:msg = l:hint . "\n\n" . a:message
        endif
    endif
    let s:no_hint_once = 0

    if s:has_async()
        " ── Modo asíncrono: send_sync en un job de fondo (no bloquea VIM) ──
        " Usamos send_sync en lugar de SSE para evitar el problema de sesión:
        " con SSE+POST separados, Flask crea dos sesiones distintas y los
        " eventos nunca llegan al stream correcto.
        call s:panel_start_turn(a:message, l:is_slash)

        let l:timeout = l:is_slash ? 60 : 300
        let l:url  = s:api_url('/api/chat/send_sync')
        let l:body = json_encode({
            \ 'message':  l:msg,
            \ 'agent_id': g:oocode_agent,
            \ 'timeout':  l:timeout,
        \ })
        let l:cmd = ['curl', '-sf',
            \ '-c', s:cookie_jar, '-b', s:cookie_jar,
            \ '-X', 'POST', '-H', 'Content-Type: application/json',
            \ '--connect-timeout', '3', '--max-time', string(l:timeout + 15),
            \ '-d', l:body, l:url]

        let s:sync_buf = ''

        if has('nvim')
            let s:sync_job = jobstart(l:cmd, {
                \ 'on_stdout': function('s:nvim_sync_stdout'),
                \ 'on_exit':   function('s:nvim_sync_exit'),
                \ 'stdout_buffered': v:false,
            \ })
        elseif has('job')
            let s:sync_job = job_start(l:cmd, {
                \ 'out_cb':  function('s:vim_sync_stdout'),
                \ 'exit_cb': function('s:vim_sync_exit'),
            \ })
        endif

    else
        " ── Modo fallback: send_sync bloqueante ────────────────────────────
        call s:panel_start_turn(a:message, l:is_slash)
        let l:timeout = l:is_slash ? 30 : 180
        let l:resp = s:post('/api/chat/send_sync', {
            \ 'message':  l:msg,
            \ 'agent_id': g:oocode_agent,
            \ 'timeout':  l:timeout,
        \ })
        call s:panel_hide_thinking()
        if empty(l:resp)
            call s:panel_append('  ⚠ Sin respuesta del servidor')
        else
            try
                let l:data  = json_decode(l:resp)
                let l:tools = get(l:data, 'tool_events', [])
                for l:t in l:tools
                    let l:sym = get(l:t, 'ok', 1) ? '⎿' : '✗'
                    call s:panel_append('  ' . l:sym . ' ' . get(l:t, 'tool', '?'))
                endfor
                let l:text = get(l:data, 'response', '')
                if !empty(l:text) && !s:sse_turn_shown
                    call s:panel_append(split(l:text, "\n", 1))
                endif
            catch
                call s:panel_append('  ⚠ Respuesta inválida')
            endtry
        endif
        call s:panel_end_turn()
    endif
endfunction

" ── Callbacks del job send_sync ───────────────────────────────────────────────

function! s:nvim_sync_stdout(jid, data, event) abort
    let s:sync_buf .= join(a:data, '')
endfunction

function! s:nvim_sync_exit(jid, code, event) abort
    let s:sync_job = v:null
    call s:display_sync_response(s:sync_buf)
endfunction

function! s:vim_sync_stdout(ch, line) abort
    let s:sync_buf .= a:line
endfunction

function! s:vim_sync_exit(job, code) abort
    let s:sync_job = v:null
    call s:display_sync_response(s:sync_buf)
endfunction

function! s:display_sync_response(resp) abort
    call s:panel_hide_thinking()
    if empty(trim(a:resp))
        call s:panel_append('  ⚠ Sin respuesta del servidor')
    else
        try
            let l:data  = json_decode(a:resp)
            " Mostrar tool events
            let l:tools = get(l:data, 'tool_events', [])
            for l:t in l:tools
                let l:sym = get(l:t, 'ok', 1) ? '⎿' : '✗'
                call s:panel_append('  ' . l:sym . ' ' . get(l:t, 'tool', '?'))
            endfor
            " Mostrar respuesta del agente
            let l:text = get(l:data, 'response', '')
            if get(l:data, 'timeout', v:false)
                call s:panel_append('  ⏳ Respuesta parcial (timeout):')
            endif
            if !empty(l:text) && !s:sse_turn_shown
                call s:panel_append(split(l:text, "\n", 1))
            elseif empty(l:tools) && !s:sse_turn_shown
                call s:panel_append('  ⚠ Respuesta vacía')
            endif
        catch
            call s:panel_append(['  ⚠ Respuesta inválida:', '  ' . a:resp[:120]])
        endtry
    endif
    call s:panel_end_turn()
endfunction

function! oocode#ask() abort
    " Mostrar el fichero activo en el prompt para que el usuario sepa qué contexto se enviará
    let l:file_short = expand('%:t')
    let l:prompt = empty(l:file_short) || bufname('%') ==# s:panel_bufname
        \ ? 'OOCode ❯ '
        \ : 'OOCode [' . l:file_short . ':L' . line('.') . '] ❯ '
    let l:msg = input(l:prompt)
    if !empty(trim(l:msg))
        call oocode#send(l:msg)
    endif
endfunction

function! oocode#send_context() abort
    let l:file  = expand('%:p')
    let l:lines = getbufline('%', 1, '$')
    let l:code  = join(l:lines, "\n")
    let l:lang  = &filetype
    let l:lnum  = line('.')

    let l:question = input('Pregunta sobre el fichero [L' . l:lnum . '] ❯ ')
    if empty(trim(l:question)) | return | endif

    let l:msg = printf("Fichero: %s (cursor L%d)\n\n```%s\n%s\n```\n\n%s",
        \ l:file, l:lnum, l:lang, l:code, l:question)
    let s:no_hint_once = 1   " ya incluye contexto completo
    call oocode#send(l:msg)
endfunction

function! oocode#send_selection() abort range
    let l:lines = getline(a:firstline, a:lastline)
    let l:code  = join(l:lines, "\n")
    let l:lang  = &filetype
    let l:question = input('Pregunta sobre la selección ❯ ')
    if empty(trim(l:question)) | return | endif

    let l:msg = printf("Selección (%s:%d-%d):\n\n```%s\n%s\n```\n\n%s",
        \ expand('%:t'), a:firstline, a:lastline, l:lang, l:code, l:question)
    let s:no_hint_once = 1
    call oocode#send(l:msg)
endfunction

" Envía la selección visual como diff/patch para revisión
function! oocode#review_selection() abort range
    let l:lines    = getline(a:firstline, a:lastline)
    let l:code     = join(l:lines, "\n")
    let l:lang     = &filetype
    let l:file     = expand('%:t')
    let l:msg = printf(
        \ "Revisa este código de %s (L%d-L%d):\n\n```%s\n%s\n```\n\nBusca bugs, mejoras y problemas de seguridad.",
        \ l:file, a:firstline, a:lastline, l:lang, l:code)
    let s:no_hint_once = 1
    call oocode#send(l:msg)
endfunction

" Explica el código bajo el cursor o selección
function! oocode#explain() abort range
    let l:lines = getline(a:firstline, a:lastline)
    let l:code  = join(l:lines, "\n")
    let l:lang  = &filetype
    let l:msg = printf("Explica este código de forma concisa:\n\n```%s\n%s\n```", l:lang, l:code)
    let s:no_hint_once = 1
    call oocode#send(l:msg)
endfunction

" ── TUI completo embebido ─────────────────────────────────────────────────────

function! oocode#tui() abort
    let l:cmd = 'oocode'
    if g:oocode_agent !=# 'main'
        let l:cmd .= ' --agent ' . shellescape(g:oocode_agent)
    endif

    if has('nvim')
        if g:oocode_split ==# 'tab'
            tabnew
        elseif g:oocode_split ==# 'horizontal'
            execute 'botright ' . g:oocode_height . 'split'
        else
            execute 'botright ' . g:oocode_width . 'vsplit'
        endif
        execute 'terminal ' . l:cmd
        startinsert
    elseif has('terminal')
        if g:oocode_split ==# 'tab'
            tabnew
            execute 'terminal ++curwin ' . l:cmd
        elseif g:oocode_split ==# 'horizontal'
            execute 'botright terminal ++rows=' . g:oocode_height . ' ' . l:cmd
        else
            execute 'vertical botright terminal ++cols=' . g:oocode_width . ' ' . l:cmd
        endif
    else
        echohl WarningMsg
        echom 'OOCode: terminal no disponible — ejecuta "oocode" en la terminal'
        echohl None
    endif
endfunction

" ── Sesiones ─────────────────────────────────────────────────────────────────

function! oocode#new_session() abort
    call s:sse_stop()
    call s:post('/api/chat/clear', {})
    if filereadable(s:cookie_jar) | call delete(s:cookie_jar) | endif
    let s:turn_active    = 0
    let s:agent_text_buf = []
    let s:tool_lnums     = {}
    call s:panel_clear()
    call s:panel_append('  🆕 Nueva sesión iniciada')
    call s:sse_ensure_running()
    echo 'OOCode: nueva sesión'
endfunction

function! oocode#switch_agent(agent_id) abort
    if empty(trim(a:agent_id))
        echo 'OOCode: uso: :OOCodeSwitch <agent_id>'
        return
    endif
    call s:sse_stop()
    let g:oocode_agent = trim(a:agent_id)
    call s:post('/api/chat/clear', {})
    if filereadable(s:cookie_jar) | call delete(s:cookie_jar) | endif
    call s:panel_clear()
    call s:panel_append('  🔄 Agente → ' . g:oocode_agent)
    call s:sse_ensure_running()
    echo 'OOCode: agente → ' . g:oocode_agent
endfunction

function! oocode#sessions() abort
    if !s:server_alive | call oocode#connect() | endif
    let l:resp = s:get('/api/sessions')
    call oocode#open_panel()
    call s:panel_append(['', '  📚 Sesiones recientes', ''])
    if empty(l:resp)
        call s:panel_append('  Sin sesiones o servidor no responde')
    else
        try
            let l:data = json_decode(l:resp)
            for l:s in get(l:data, 'sessions', [])[:9]
                let l:ts  = substitute(get(l:s, 'started_at', ''), 'T', ' ', '')[0:15]
                let l:cnt = get(l:s, 'message_count', 0)
                let l:sid = get(l:s, 'session_id', '')[0:7]
                call s:panel_append(printf('  %s  %s  %d msgs', l:sid, l:ts, l:cnt))
            endfor
        catch
            call s:panel_append('  Error leyendo sesiones')
        endtry
    endif
    call s:panel_append(['', '─────────────────────────────────────────'])
endfunction

" ── Agentes / Subagentes ──────────────────────────────────────────────────────

function! oocode#agents() abort
    if !s:server_alive | call oocode#connect() | endif
    let l:resp = s:get('/api/agents')
    if empty(l:resp) | echo 'OOCode: servidor no responde' | return | endif
    call oocode#open_panel()
    call s:panel_append(['', '  📋 Subagentes', ''])
    try
        let l:data = json_decode(l:resp)
        let l:all  = get(l:data, 'running', []) + get(l:data, 'recent', [])
        if empty(l:all)
            call s:panel_append('  Sin subagentes activos')
        else
            for l:a in l:all
                let l:sym = l:a.status ==# 'running' ? '●' : '○'
                call s:panel_append(printf('  %s %s %s  %s  (%ds)',
                    \ l:sym, get(l:a,'agent_emoji','🤖'), get(l:a,'agent_id','?'),
                    \ get(l:a,'task','—')[:50], get(l:a,'elapsed',0)
                \ ))
                if l:a.status !=# 'running' && !empty(get(l:a, 'result_preview', ''))
                    call s:panel_append('    → ' . l:a.result_preview[:80])
                endif
            endfor
        endif
    catch
        call s:panel_append('  Error: ' . v:exception)
    endtry
    call s:panel_append(['', '─────────────────────────────────────────'])
endfunction

" ── Doctor / Status ───────────────────────────────────────────────────────────

function! oocode#doctor() abort
    if has('nvim') || has('terminal')
        call oocode#tui_cmd('/doctor')
    else
        call oocode#open_panel()
        call s:panel_append(['', '  🩺 Doctor', ''])
        call s:panel_append('  Abre el WebUI para el informe completo: ' . g:oocode_host . '/doctor')
        call s:panel_append(['', '─────────────────────────────────────────'])
    endif
endfunction

function! oocode#status() abort
    " Re-detectar si necesario
    call oocode#check_server_on_start()
    let l:resp = s:get('/api/status')
    if empty(l:resp)
        echohl WarningMsg
        echo 'OOCode: no responde en ' . g:oocode_host . '  (usa :OOCodeConnect)'
        echohl None
        return
    endif
    try
        let l:data = json_decode(l:resp)
        echo printf('OOCode %s %s | %s | ctx: %d%% | hooks: %d | plugins: %d',
            \ get(l:data, 'agent_emoji', '🤖'),
            \ get(l:data, 'agent_id',    'main'),
            \ substitute(get(l:data, 'model', '—'), ':latest$', '', ''),
            \ get(l:data, 'context_pct',  0),
            \ get(l:data, 'hooks_count',  0),
            \ get(l:data, 'plugins_count',0)
        \ )
    catch
        echo 'OOCode activo en ' . g:oocode_host
    endtry
endfunction

function! oocode#tui_cmd(cmd) abort
    call oocode#send(a:cmd)
endfunction

" ── WebUI / servidor ──────────────────────────────────────────────────────────

function! oocode#open_webui() abort
    let l:url = g:oocode_host
    if has('unix')
        let l:opener = executable('xdg-open') ? 'xdg-open'
                    \ : executable('open') ? 'open' : ''
        if !empty(l:opener)
            call system(l:opener . ' ' . shellescape(l:url) . ' &')
        endif
    endif
    echo 'OOCode WebUI: ' . l:url
endfunction

function! oocode#webserver(cmd) abort
    if index(['start','stop','restart','status'], a:cmd) < 0
        echohl ErrorMsg
        echo 'OOCode: usa start|stop|restart|status'
        echohl None
        return
    endif
    let l:out = system('oocode --webserver ' . shellescape(a:cmd) . ' 2>&1')
    echo substitute(l:out, '\e\[[0-9;]*m', '', 'g')
    if a:cmd ==# 'start'
        " Esperar arranque y re-detectar
        call timer_start(3000, {-> oocode#check_server_on_start()})
        call timer_start(4000, {-> s:sse_ensure_running()})
    elseif a:cmd ==# 'stop'
        call s:sse_stop()
        let s:server_alive = 0
    endif
endfunction

" ── Statusline ────────────────────────────────────────────────────────────────

let s:server_alive    = -1
let s:server_check_ts = 0

function! oocode#statusline() abort
    let l:now  = localtime()
    let l:diff = l:now - s:server_check_ts
    " Re-comprobar cada 30 segundos (async si está disponible, else sin bloquear si < 30s)
    if l:diff > 30
        let s:server_check_ts = l:now
        " Comprobación no bloqueante: usar cached state
        if filereadable(s:state_file)
            try
                let l:st = json_decode(join(readfile(s:state_file), ''))
                " Si el pid del state file sigue vivo, asumir activo
                let l:pid = get(l:st, 'pid', 0)
                if l:pid > 0
                    let l:alive = !empty(system('kill -0 ' . l:pid . ' 2>/dev/null; echo $?'))
                    let s:server_alive = trim(system('kill -0 ' . l:pid . ' 2>/dev/null; echo $?')) ==# '0' ? 1 : 0
                else
                    let s:server_alive = 0
                endif
            catch
                let s:server_alive = 0
            endtry
        else
            let s:server_alive = 0
        endif
    endif
    if s:server_alive > 0
        let l:busy = s:turn_active ? ' ◐' : ''
        return ' ' . s:agent_emoji . ' ' . g:oocode_agent
              \ . (s:ctx_pct > 0 ? ' ' . s:ctx_pct . '%' : '')
              \ . l:busy . ' '
    endif
    return ''
endfunction

function! OOCodeStatusLine() abort
    return oocode#statusline()
endfunction

" ── Funciones públicas de ciclo de vida (llamadas desde plugin/) ──────────────

function! oocode#sse_start() abort
    call s:sse_ensure_running()
endfunction

function! oocode#sse_stop() abort
    call s:sse_stop()
endfunction

function! oocode#server_alive() abort
    return s:server_alive
endfunction
