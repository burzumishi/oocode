" OOCode autoload — wrapper completo del TUI (streaming SSE, tools, plan)
" Versión: 3.2.0

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
let s:tokens_in      = 0
let s:tokens_out     = 0
let s:mem_hits       = 0
let s:rag_hits       = 0
let s:rag_available  = 0
let s:think_level    = 'off'
let s:reasoning      = 0

" Detección del servidor
let s:server_alive    = -1   " -1=desconocido  0=inactivo  1=activo
let s:server_check_ts = 0
let s:server_ports    = [4000, 7788, 3000, 5000]

" Sesión Flask establecida en el cookie jar.
" CRÍTICO: un curl SSE persistente NUNCA escribe el cookie jar (curl lo vuelca
" al terminar la transferencia, y el stream no termina). Si el primer contacto
" con el servidor es el SSE, el POST /api/chat/send va sin cookie → Flask crea
" una sesión distinta → los eventos del turno caen en OTRA cola y el panel se
" queda mudo. Por eso establecemos la cookie con una petición que COMPLETA
" (GET /api/chat/status) ANTES de abrir el stream.
let s:session_ready   = 0

" Estado de subagente activo (para prefijar líneas con │, paridad TUI/WebUI)
let s:sub_depth       = 0

" Prompts interactivos pendientes (ask_user / permisos), servidos vía timer
" porque input()/inputlist() no se pueden llamar desde el callback del SSE.
let s:pending_questions = []
let s:pending_perm      = {}

" Watchdog del turno: timer id que cierra el turno si el SSE enmudece
let s:turn_watchdog   = -1
let s:last_event_ts   = 0

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

" Establece la cookie de sesión Flask con una petición que COMPLETA, de modo
" que el SSE y el POST de envío compartan el mismo sid (misma cola de eventos).
" Idempotente: solo realiza la petición una vez por sesión.
function! s:ensure_session() abort
    if s:session_ready | return | endif
    " GET /api/chat/status invoca _get_or_create_sid() → Set-Cookie en el jar.
    call system(printf(
        \ 'curl -sf -c %s -b %s --connect-timeout 3 --max-time 8 %s >/dev/null 2>&1',
        \ shellescape(s:cookie_jar), shellescape(s:cookie_jar),
        \ shellescape(s:api_url('/api/chat/status?agent_id=' . g:oocode_agent))
    \ ))
    let s:session_ready = 1
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
    " tokens · mem · rag — paridad con la línea 2 del status del TUI
    let l:tok_str = (s:tokens_in > 0 || s:tokens_out > 0)
                 \ ? '  ·  ' . s:tokens_in . '↑ ' . s:tokens_out . '↓'
                 \ : ''
    let l:mem_str = s:mem_hits > 0 ? '  ·  ⬡ ' . s:mem_hits . ' mem' : ''
    let l:rag_str = s:rag_hits > 0
                 \ ? '  ·  ◈ ' . (s:rag_available > s:rag_hits ? s:rag_hits . '/' . s:rag_available : s:rag_hits) . ' rag'
                 \ : ''
    " think:med.+r — paridad con el bloque think del toolbar TUI
    let l:think_str = s:think_level !=# 'off'
                   \ ? '  ·  think:' . strpart(s:think_level, 0, 3) . (s:reasoning ? '.+r' : '')
                   \ : ''
    let l:hdr = printf('# %s %s  │  %s  │  %s%s%s%s%s%s',
        \ s:agent_emoji, s:agent_name, s:agent_model, l:ctx_str,
        \ l:think_str, l:tok_str, l:mem_str, l:rag_str, l:task_str)
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
    let s:sub_depth   = 0
    call s:cancel_watchdog()
    " Flush texto acumulado si lo hay
    if !empty(s:agent_text_buf)
        call s:panel_append(s:agent_text_buf)
        let s:agent_text_buf = []
    endif
    call s:panel_append(['', '─────────────────────────────────────────'])
    call s:panel_update_header()
endfunction

" ── Watchdog del turno (modo streaming) ───────────────────────────────────────
" Si el stream SSE no entrega NINGÚN evento en g:oocode_turn_timeout segundos,
" cerramos el turno para reactivar el prompt (evita "Pensando…" colgado).

function! s:arm_watchdog() abort
    call s:cancel_watchdog()
    let s:last_event_ts = localtime()
    let l:secs = get(g:, 'oocode_turn_timeout', 360)
    if exists('*timer_start')
        let s:turn_watchdog = timer_start(l:secs * 1000, function('s:watchdog_fire'))
    endif
endfunction

function! s:cancel_watchdog() abort
    if s:turn_watchdog >= 0 && exists('*timer_stop')
        call timer_stop(s:turn_watchdog)
    endif
    let s:turn_watchdog = -1
endfunction

function! s:watchdog_fire(timer) abort
    let s:turn_watchdog = -1
    if !s:turn_active | return | endif
    let l:idle = localtime() - s:last_event_ts
    let l:secs = get(g:, 'oocode_turn_timeout', 360)
    if l:idle >= l:secs - 1
        " Stream mudo demasiado tiempo: cerrar el turno.
        call s:panel_hide_thinking()
        call s:panel_append('  ⏳ Sin respuesta del stream — turno cerrado (revisa el servidor)')
        call s:panel_end_turn()
    else
        " Hubo actividad reciente: re-armar para el tiempo restante.
        if exists('*timer_start')
            let s:turn_watchdog = timer_start((l:secs - l:idle) * 1000,
                \ function('s:watchdog_fire'))
        endif
    endif
endfunction

" ── Eventos SSE → Panel ───────────────────────────────────────────────────────

function! s:panel_on_thinking() abort
    " Asegurar que el indicador está visible
    if s:think_lnum < 0
        let s:think_lnum = s:panel_append('  ● Pensando…')
    endif
endfunction

" Vuelca el texto acumulado del agente principal al panel, en orden.
" Se llama antes de cada evento estructurado (tool/plan/subagente) para que la
" prosa del agente aparezca intercalada en su sitio (paridad con TUI/WebUI),
" no toda junta al final del turno.
function! s:flush_text_buf() abort
    if !empty(s:agent_text_buf)
        call s:panel_append(s:agent_text_buf)
        let s:agent_text_buf = []
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

function! s:panel_on_tool_done(tool, ok, nlines, preview, ...) abort
    let l:ctx   = a:0 >= 1 ? a:1 : ''
    let l:sym   = a:ok ? '⎿' : '✗'
    let l:ctxs  = empty(l:ctx) ? '' : '  ' . l:ctx[:40]
    let l:detail = ''
    if a:nlines > 1
        let l:detail = '  ▸ ' . a:nlines . ' líneas'
    elseif !empty(a:preview)
        let l:detail = '  ' . a:preview[:50]
    endif
    let l:line = '  ' . l:sym . ' ' . a:tool . l:ctxs . l:detail

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

function! s:panel_on_plan_progress(done, total, active_text) abort
    if a:total <= 0 | return | endif
    let l:line = '  ◈  Plan  [' . a:done . '/' . a:total . ']'
    if !empty(a:active_text)
        let l:line .= '  ▸ ' . a:active_text[:60]
    endif
    call s:panel_append(l:line)
endfunction

" Subagentes — paridad con el bloque dedicado del TUI/WebUI (líneas con │)
function! s:panel_on_subagent_start(emoji, name, task) abort
    call s:panel_hide_thinking()
    " Flush del texto del agente principal antes de abrir el bloque del subagente
    if !empty(s:agent_text_buf)
        call s:panel_append(s:agent_text_buf)
        let s:agent_text_buf = []
    endif
    let s:sub_depth += 1
    call s:panel_append('  ' . a:emoji . ' ' . a:name . ' ◂ ' . a:task[:64])
endfunction

function! s:panel_on_subagent_done(name) abort
    if s:sub_depth > 0 | let s:sub_depth -= 1 | endif
    let l:label = empty(a:name) ? 'subagente' : a:name
    call s:panel_append('  │ ⎿ ' . l:label . ' ✓')
endfunction

" Texto/chunk de subagente: se vuelca directo con prefijo │ (no al buffer del padre)
function! s:panel_on_subagent_text(text) abort
    call s:panel_hide_thinking()
    if empty(a:text) | return | endif
    for l:ln in split(a:text, "\n", 1)
        call s:panel_append('  │ ' . l:ln)
    endfor
endfunction

function! s:panel_on_error(msg) abort
    call s:panel_hide_thinking()
    call s:panel_append(['', '  ✗ Error: ' . a:msg, ''])
    call s:panel_end_turn()
endfunction

" ── ask_user — paridad TUI/WebUI ──────────────────────────────────────────────
" El servidor emite 'question' y BLOQUEA el turno hasta POST /api/chat/answer.
" Sin esto, cualquier ask_user del agente cuelga el turno hasta el timeout (900s).
" El prompt interactivo se difiere con timer_start(0): input()/inputlist() no se
" pueden invocar desde el callback del job SSE (textlock).
function! s:panel_on_question(questions) abort
    call s:panel_hide_thinking()
    let s:pending_questions = a:questions
    call s:panel_append(['', '  ❓ OOCode necesita tu decisión:'])
    call timer_start(0, {-> s:prompt_questions()})
endfunction

function! s:prompt_questions() abort
    let l:qs = get(s:, 'pending_questions', [])
    let s:pending_questions = []
    if empty(l:qs) | return | endif
    let l:answers = []
    for l:q in l:qs
        let l:header  = get(l:q, 'header', '')
        let l:qtext   = get(l:q, 'question', '')
        let l:multi   = get(l:q, 'multiSelect', 0)
        let l:options = get(l:q, 'options', [])
        call s:panel_append('  ┌ ' . (empty(l:header) ? '' : '['.l:header.'] ') . l:qtext)
        " Construir lista de opciones para inputlist (1-based) + opción de texto libre.
        let l:menu = [(empty(l:qtext) ? 'Elige:' : l:qtext) . (l:multi ? '  (varias: 1,3)' : '')]
        let l:i = 1
        for l:opt in l:options
            let l:lbl = type(l:opt) == v:t_dict ? get(l:opt, 'label', string(l:opt)) : string(l:opt)
            let l:dsc = type(l:opt) == v:t_dict ? get(l:opt, 'description', '') : ''
            call s:panel_append('  │ ' . l:i . '. ' . l:lbl . (empty(l:dsc) ? '' : '  — ' . l:dsc))
            call add(l:menu, printf('%d. %s', l:i, l:lbl))
            let l:i += 1
        endfor
        call add(l:menu, printf('%d. (otro: escribir respuesta)', l:i))
        " Prompt al usuario.
        let l:sel = []
        let l:free = ''
        if l:multi
            call inputsave()
            let l:raw = input('  → opciones (ej. 1,3) o texto libre: ')
            call inputrestore()
            if l:raw =~# '^\s*\d\+\(\s*,\s*\d\+\)*\s*$'
                for l:n in split(l:raw, ',')
                    call add(l:sel, str2nr(trim(l:n)) - 1)
                endfor
            else
                let l:free = l:raw
            endif
        else
            call inputsave()
            let l:choice = inputlist(l:menu)
            call inputrestore()
            if l:choice >= 1 && l:choice <= len(l:options)
                call add(l:sel, l:choice - 1)
            elseif l:choice == l:i
                call inputsave()
                let l:free = input('  → tu respuesta: ')
                call inputrestore()
            endif
        endif
        call add(l:answers, {'selection': l:sel, 'free_text': l:free})
    endfor
    call s:panel_append(['  └ enviando respuesta…', ''])
    call s:post('/api/chat/answer', {'answers': l:answers})
endfunction

" Bloque resumen de respuestas (paridad con _render_ask_answers TUI/WebUI).
function! s:panel_on_ask_answers(pairs) abort
    if empty(a:pairs) | return | endif
    call s:panel_append('  ● Respondiste a OOCode:')
    for l:p in a:pairs
        call s:panel_append('  ⎿ · ' . get(l:p, 'q', '') . ' → ' . get(l:p, 'a', ''))
    endfor
    call s:panel_append('')
endfunction

" ── Confirmación de permisos — paridad GAP 4 ──────────────────────────────────
" Solo se emite si webui.permissionPrompt=ON y hay cliente SSE (Vim cuenta). El
" turno bloquea hasta POST /api/chat/permission (180s → denegado por seguridad).
function! s:panel_on_permission(tool, description) abort
    let s:pending_perm = {'tool': a:tool, 'description': a:description}
    call timer_start(0, {-> s:prompt_permission()})
endfunction

function! s:prompt_permission() abort
    let l:p = get(s:, 'pending_perm', {})
    let s:pending_perm = {}
    if empty(l:p) | return | endif
    call s:panel_append('  🔐 Permiso: ' . get(l:p, 'tool', '?')
        \ . (empty(get(l:p, 'description', '')) ? '' : ' — ' . l:p['description']))
    call inputsave()
    let l:c = inputlist(['Autorizar ' . get(l:p, 'tool', '?') . '?',
        \ '1. Sí (una vez)', '2. No', '3. Siempre'])
    call inputrestore()
    let l:choice = l:c == 1 ? 's' : (l:c == 3 ? 'siempre' : 'n')
    call s:panel_append('  ⎿ ' . (l:choice ==# 'n' ? 'denegado' : 'autorizado (' . l:choice . ')'))
    call s:post('/api/chat/permission', {'choice': l:choice})
endfunction

function! s:handle_sse_event(ev) abort
    let l:type = get(a:ev, 'type', '')
    let s:last_event_ts = localtime()
    let l:is_sub = get(a:ev, 'subagent', 0)

    if l:type ==# 'connected'
        " Confirmación silenciosa (evita ruido en cada reconexión del stream).

    elseif l:type ==# 'heartbeat'
        " silencioso

    elseif l:type ==# 'thinking'
        if !l:is_sub | call s:panel_on_thinking() | endif

    elseif l:type ==# 'text'
        if l:is_sub
            call s:panel_on_subagent_text(get(a:ev, 'text', ''))
        else
            call s:panel_on_text(get(a:ev, 'text', ''))
        endif

    elseif l:type ==# 'stream_chunk'
        if l:is_sub
            call s:panel_on_subagent_text(get(a:ev, 'text', ''))
        else
            call s:panel_on_stream_chunk(get(a:ev, 'text', ''))
        endif

    elseif l:type ==# 'tool_start'
        call s:flush_text_buf()
        let l:pre = l:is_sub ? '│ ' : ''
        call s:panel_on_tool_start(l:pre . get(a:ev, 'tool', '?'), get(a:ev, 'context', ''))

    elseif l:type ==# 'tool_done'
        let l:pre = l:is_sub ? '│ ' : ''
        call s:panel_on_tool_done(
            \ l:pre . get(a:ev, 'tool', '?'),
            \ get(a:ev, 'ok',      1),
            \ get(a:ev, 'n_lines', 0),
            \ get(a:ev, 'preview', ''),
            \ get(a:ev, 'context', '')
        \ )

    elseif l:type ==# 'plan'
        call s:flush_text_buf()
        call s:panel_on_plan(
            \ get(a:ev, 'tasks',   []),
            \ get(a:ev, 'n',        0),
            \ get(a:ev, 'summary', '')
        \ )

    elseif l:type ==# 'plan_progress'
        call s:flush_text_buf()
        call s:panel_on_plan_progress(
            \ get(a:ev, 'done',  0),
            \ get(a:ev, 'total', 0),
            \ get(a:ev, 'active_text', '')
        \ )

    elseif l:type ==# 'subagent_start'
        call s:panel_on_subagent_start(
            \ get(a:ev, 'agent_emoji', '🤖'),
            \ get(a:ev, 'agent_name',  get(a:ev, 'agent_id', 'subagente')),
            \ get(a:ev, 'task', '')
        \ )

    elseif l:type ==# 'subagent_done'
        call s:panel_on_subagent_done(get(a:ev, 'subagent_name', get(a:ev, 'agent_id', '')))

    elseif l:type ==# 'preflight'
        " Reemplazar "Pensando…" por la frase preflight enlatada del servidor.
        let l:label = get(a:ev, 'label', '')
        if !empty(l:label) && s:think_lnum > 0
            call s:panel_setline(s:think_lnum, '  ● ' . l:label)
        endif

    elseif l:type ==# 'question'
        " ask_user: el turno bloquea hasta /api/chat/answer → prompt obligatorio.
        call s:panel_on_question(get(a:ev, 'questions', []))

    elseif l:type ==# 'ask_answers'
        call s:panel_on_ask_answers(get(a:ev, 'pairs', []))

    elseif l:type ==# 'permission'
        " Confirmación de permiso (webui.permissionPrompt ON) → bloquea el turno.
        call s:panel_on_permission(get(a:ev, 'tool', '?'), get(a:ev, 'description', ''))

    elseif l:type ==# 'queued'
        " Mensaje encolado mientras el agente trabaja (cola FIFO de entrada).
        call s:panel_append('  ⏳ en cola: ' . get(a:ev, 'text', ''))

    elseif l:type ==# 'slash_result'
        " Resultado de un slash command ejecutado server-side.
        let l:r = get(a:ev, 'result', get(a:ev, 'text', ''))
        if !empty(l:r) | call s:panel_append(split(l:r, "\n", 1)) | endif

    elseif l:type ==# 'reasoning'
        " Razonamiento del modelo (think_level != off): bloque tenue con el porqué.
        call s:panel_hide_thinking()
        for l:rl in split(get(a:ev, 'text', ''), "\n", 1)
            call s:panel_append('  💭 ' . l:rl)
        endfor

    elseif l:type ==# 'embed_flash'
        " Operación de memoria/RAG en curso — indicador discreto, sin romper el flujo.

    elseif l:type ==# 'inference_done'
        " Señal de fin de inferencia; el evento 'done' cierra el turno.

    elseif l:type ==# 'status'
        call s:update_agent_status(a:ev)
        call s:panel_update_header()

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
    if has_key(a:ev, 'tokens_in')   | let s:tokens_in   = get(a:ev, 'tokens_in',  0) | endif
    if has_key(a:ev, 'tokens_out')  | let s:tokens_out  = get(a:ev, 'tokens_out', 0) | endif
    if has_key(a:ev, 'mem_hits')    | let s:mem_hits    = get(a:ev, 'mem_hits',   0) | endif
    if has_key(a:ev, 'rag_hits')    | let s:rag_hits    = get(a:ev, 'rag_hits',   0) | endif
    if has_key(a:ev, 'rag_available') | let s:rag_available = get(a:ev, 'rag_available', 0) | endif
    if has_key(a:ev, 'think_level')  | let s:think_level  = get(a:ev, 'think_level', 'off') | endif
    if has_key(a:ev, 'reasoning')    | let s:reasoning    = get(a:ev, 'reasoning',   0) | endif
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

    " La cookie DEBE existir antes de abrir el stream (ver nota en s:session_ready).
    call s:ensure_session()

    let l:url = s:api_url('/api/chat/stream?agent_id=' . g:oocode_agent)
    " Solo -b (leer cookie): el SSE es persistente y -c truncaría el jar al cerrar.
    let l:cmd = ['curl', '-sN', '--no-buffer',
               \ '-b', s:cookie_jar,
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
" Devuelve una línea de contexto que REFERENCIA lo que el usuario está viendo en
" Vim (ruta absoluta del fichero + cursor, o el directorio si es un explorador),
" más el directorio de trabajo. El agente la usa para saber a qué se refiere el
" usuario ("revisa esta función") y leerlo con read_file. Siempre rutas ABSOLUTAS
" para que el agente las abra aunque su project_dir difiera del cwd de Vim.
function! s:file_hint() abort
    let l:cwd = getcwd()

    " Explorador de directorios (netrw) o buffer de directorio: referenciar el dir.
    if &filetype ==# 'netrw' || (isdirectory(expand('%:p')) && !empty(expand('%:p')))
        let l:dir = get(b:, 'netrw_curdir', expand('%:p'))
        if empty(l:dir) | let l:dir = l:cwd | endif
        return printf('[Contexto Vim — el usuario está navegando el directorio: %s]', l:dir)
    endif

    let l:file = expand('%:p')
    " Buffer sin fichero real o el propio panel OOCode → al menos referenciar el cwd.
    if empty(l:file) || bufname('%') ==# s:panel_bufname
        return printf('[Contexto Vim — directorio de trabajo: %s]', l:cwd)
    endif
    " Buffers especiales (terminal, quickfix, help…): solo el cwd.
    if &buftype !=# '' && &buftype !=# 'nofile'
        return printf('[Contexto Vim — directorio de trabajo: %s]', l:cwd)
    endif

    let l:lnum = line('.')
    let l:col  = col('.')
    let l:ft   = empty(&filetype) ? '' : &filetype
    " Rango de selección visual reciente (si lo hay) para acotar la referencia.
    let l:hint = printf('[Contexto Vim — el usuario está viendo el fichero: %s (línea L%d:%d',
        \ l:file, l:lnum, l:col)
    if !empty(l:ft)
        let l:hint .= ', ft=' . l:ft
    endif
    let l:hint .= printf('). Directorio de trabajo: %s]', l:cwd)
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

    " No solapar turnos: el servidor responde 409 si el agente está ocupado.
    if s:turn_active
        echohl WarningMsg
        echo 'OOCode: el agente está procesando — usa :OOCodeKill para interrumpir'
        echohl None
        return
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

    " Modo streaming (paridad TUI/WebUI): SSE persistente + POST /api/chat/send.
    " Requiere jobs y g:oocode_stream activo. Si no, fallback send_sync bloqueante.
    if get(g:, 'oocode_stream', 1) && s:has_async()
        call s:send_via_stream(a:message, l:msg, l:is_slash)
    else
        call s:send_via_sync(a:message, l:msg, l:is_slash)
    endif
endfunction

" ── Envío vía stream SSE (paridad con WebUI) ──────────────────────────────────
" El POST /api/chat/send es fire-and-forget: dispara el turno y TODOS los eventos
" (text, tool_start/done, plan, subagent, done) llegan por el stream SSE ya abierto.
function! s:send_via_stream(raw, msg, is_slash) abort
    call s:ensure_session()
    call s:sse_ensure_running()
    call s:panel_start_turn(a:raw, a:is_slash)

    let l:url  = s:api_url('/api/chat/send')
    let l:body = json_encode({'message': a:msg, 'agent_id': g:oocode_agent})
    let l:cmd  = ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
        \ '-b', s:cookie_jar,
        \ '-X', 'POST', '-H', 'Content-Type: application/json',
        \ '--connect-timeout', '5', '--max-time', '30',
        \ '-d', l:body, l:url]

    let s:sync_buf = ''
    if has('nvim')
        let s:sync_job = jobstart(l:cmd, {
            \ 'on_stdout': function('s:nvim_send_stdout'),
            \ 'on_exit':   function('s:nvim_send_exit'),
            \ 'stdout_buffered': v:true,
        \ })
    elseif has('job')
        let s:sync_job = job_start(l:cmd, {
            \ 'out_cb':  function('s:vim_send_stdout'),
            \ 'exit_cb': function('s:vim_send_exit'),
        \ })
    endif

    " Watchdog: si tras N s no llega NINGÚN evento del stream, cerrar el turno.
    call s:arm_watchdog()
endfunction

" Callbacks del POST /api/chat/send — solo comprueban el código HTTP del disparo.
function! s:nvim_send_stdout(jid, data, event) abort
    let s:sync_buf .= join(a:data, '')
endfunction
function! s:nvim_send_exit(jid, code, event) abort
    let s:sync_job = v:null
    call s:on_send_post_done(s:sync_buf)
endfunction
function! s:vim_send_stdout(ch, msg) abort
    let s:sync_buf .= a:msg
endfunction
function! s:vim_send_exit(job, code) abort
    let s:sync_job = v:null
    call s:on_send_post_done(s:sync_buf)
endfunction

function! s:on_send_post_done(body) abort
    let l:code = matchstr(a:body, '\d\+$')
    " 409 = el agente ya estaba ocupado; 5xx/000 = servidor caído.
    if l:code ==# '409'
        call s:panel_hide_thinking()
        call s:panel_append('  ⚠ El agente está ocupado — espera o usa :OOCodeKill')
        call s:cancel_watchdog()
        let s:turn_active = 0
    elseif l:code !=# '200' && !empty(l:code)
        call s:panel_hide_thinking()
        call s:panel_append('  ✗ Error de envío (HTTP ' . l:code . ')')
        call s:cancel_watchdog()
        call s:panel_end_turn()
    endif
    " 200 → el turno continúa por SSE; el evento 'done' lo cerrará.
endfunction

" ── Envío síncrono (fallback sin jobs / g:oocode_stream=0) ─────────────────────
function! s:send_via_sync(raw, msg, is_slash) abort
    " En modo sync NO debe haber un SSE compitiendo por la misma cola de eventos.
    call s:sse_stop()
    call s:panel_start_turn(a:raw, a:is_slash)

    let l:timeout = a:is_slash ? 60 : 300
    if s:has_async()
        let l:url  = s:api_url('/api/chat/send_sync')
        let l:body = json_encode({
            \ 'message': a:msg, 'agent_id': g:oocode_agent, 'timeout': l:timeout})
        let l:cmd = ['curl', '-sf', '-c', s:cookie_jar, '-b', s:cookie_jar,
            \ '-X', 'POST', '-H', 'Content-Type: application/json',
            \ '--connect-timeout', '3', '--max-time', string(l:timeout + 15),
            \ '-d', l:body, l:url]
        let s:sync_buf = ''
        if has('nvim')
            let s:sync_job = jobstart(l:cmd, {
                \ 'on_stdout': function('s:nvim_sync_stdout'),
                \ 'on_exit':   function('s:nvim_sync_exit'),
                \ 'stdout_buffered': v:true,
            \ })
        else
            let s:sync_job = job_start(l:cmd, {
                \ 'out_cb':  function('s:vim_sync_stdout'),
                \ 'exit_cb': function('s:vim_sync_exit'),
            \ })
        endif
    else
        " Sin jobs: bloqueante.
        let l:resp = s:post('/api/chat/send_sync', {
            \ 'message': a:msg, 'agent_id': g:oocode_agent, 'timeout': l:timeout})
        call s:display_sync_response(l:resp)
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
                let l:ctx = get(l:t, 'context', '')
                call s:panel_append('  ' . l:sym . ' ' . get(l:t, 'tool', '?')
                    \ . (empty(l:ctx) ? '' : '  ' . l:ctx[:50]))
            endfor
            " Mostrar respuesta del agente
            let l:text = get(l:data, 'response', '')
            if get(l:data, 'timeout', v:false)
                call s:panel_append('  ⏳ Respuesta parcial (timeout):')
            endif
            if !empty(l:text)
                call s:panel_append(split(l:text, "\n", 1))
            elseif empty(l:tools)
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
    call s:cancel_watchdog()
    call s:sse_stop()
    call s:post('/api/chat/clear', {})
    if filereadable(s:cookie_jar) | call delete(s:cookie_jar) | endif
    let s:session_ready  = 0
    let s:turn_active    = 0
    let s:sub_depth      = 0
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
    call s:cancel_watchdog()
    call s:sse_stop()
    let g:oocode_agent = trim(a:agent_id)
    call s:post('/api/chat/clear', {})
    if filereadable(s:cookie_jar) | call delete(s:cookie_jar) | endif
    let s:session_ready = 0
    let s:turn_active   = 0
    let s:sub_depth     = 0
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

" ── Interrupción del turno (paridad con el botón Kill del WebUI) ──────────────

function! oocode#kill() abort
    if !s:turn_active
        echo 'OOCode: no hay turno activo'
        return
    endif
    call s:post('/api/chat/kill', {})
    " El servidor emite un evento 'done' por el stream; el watchdog y el handler
    " 'done' cierran el turno. Forzamos el cierre local por si el stream no responde.
    call s:cancel_watchdog()
    call s:panel_hide_thinking()
    call s:panel_append('  ⛔ Turno interrumpido')
    call s:panel_end_turn()
    echo 'OOCode: turno interrumpido'
endfunction

" ── Modo elevated (paridad con el badge elevated del WebUI) ───────────────────

function! oocode#elevated(...) abort
    let l:mode = a:0 >= 1 ? trim(a:1) : ''
    let l:resp = s:post('/api/chat/elevated', empty(l:mode) ? {} : {'mode': l:mode})
    if empty(l:resp)
        echohl WarningMsg | echo 'OOCode: servidor no responde' | echohl None
        return
    endif
    try
        let l:data = json_decode(l:resp)
        echo 'OOCode: elevated → ' . get(l:data, 'elevated', '?')
            \ . '  (' . get(l:data, 'desc', '') . ')'
    catch
        echo 'OOCode: elevated actualizado'
    endtry
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
        let s:server_alive  = 0
        let s:session_ready = 0
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
