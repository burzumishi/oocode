# Changelog — OOCode

## v0.4.3 (2026-06-04) — Robustez de subagentes, contexto y personalización de agentes

Bloque de robustez y visibilidad: confusión PDF/web corregida, compactación a mitad de
turno, delegación consciente de agentes, capa de personalización por-agente, timeout de
subagentes por inactividad, alineación del TUI, `/kill` instantáneo y VIM 3.1.

Tres correcciones derivadas de una sesión real (búsqueda + descarga de un PDF): el
agente confundía el contenido descargado con un mensaje nuevo del usuario, la
compactación a mitad de turno reimprimía un mensaje obsoleto, y el LLM no sabía qué
agentes especializados tenía disponibles para delegar.

### Búsqueda/descarga — el contenido externo ya no se confunde con el usuario

- **Resultados de tools tipo documento etiquetados.** `web_fetch`, `pdf_extract_text`,
  `doc_read` y `doc_extract_metadata` inyectaban su texto sin marca; un modelo débil,
  tras descargar p.ej. un PDF, respondía «¡Hola! Veo que has compartido un PDF…
  ¿en qué puedo ayudarte?» como si la conversación empezara de cero, y el turno
  terminaba. Ahora `_postprocess_tool_result` (`agent/loop.py`) antepone una cabecera
  («es SALIDA DE HERRAMIENTA, NO un mensaje nuevo del usuario — continúa la tarea»)
  con el origen (URL/fichero). Va al principio para sobrevivir a la truncación.
- **Hint reactivo de «arranque en frío».** Si el agente ya usó tools en el turno y su
  último texto es un saludo/petición de instrucciones de cero (`_COLD_START_RE` en
  `agent/loop_helpers.py`), `_turn_guidance` lo reorienta a la tarea en curso.

### TUI — Compactación a mitad de turno muestra el mensaje REAL más reciente

- **Corregido el «último mensaje del agente» obsoleto al compactar.** `_last_response`
  solo se fijaba en `_turn_finish` (fin de `run()`); con auto-continue, la compactación
  a mitad de turno mostraba el mensaje del `run()` *anterior* — y en la 2ª/3ª
  compactación de un mismo turno repetía el de la 1ª. Nuevo `_last_agent_msg`,
  actualizado por iteración con el último bloque de texto; `_show_compact_reset`
  (`ui/loop_tui.py`) lo usa (fallback a `_last_response`). Cumple «mostrar solo el
  último bloque». test_13 `TestShowCompactReset`, test_81.

### TUI — alineación del ● de texto de los subagentes

- **Corregida la desalineación del `●` de los subagentes.** Los subagentes no tienen
  live block (sus callbacks son `None`), así que su `●` de texto caía en la rama
  `console.print` directa de `_turn_display_bullet` → columna 0, desalineado respecto a
  sus propias líneas de tool (`  │  …`). Nuevo `_render_subagent_bullet` (`agent/loop.py`)
  renderiza el `●` y su continuación vía `self._print`, que añade el prefijo `│` y
  respeta el presupuesto `_MAX_SUB_LINES`. Ahora todo el bloque del subagente comparte
  la columna `│`.
- **Avisos de retry XML** (thinking agotado / XML malformado / parcial recuperado) pasan
  por el nuevo helper `_notice`, que indenta para el agente principal y añade `│` para
  subagentes — antes se imprimían en columna 0 dentro de un subagente. test_22
  `TestSubagentBulletAlignment`.

### Subagentes — bash ya no intenta ejecutar el workspace de identidad como cwd

- **Corregido el `workdir` de las tools del subagente.** El subagente construía su
  registry con `build_registry_fn(sub_config.workspace, …)`, es decir, fijaba como
  directorio de trabajo de `bash`/`python_exec`/`workspace_remember` su **workspace de
  identidad** (`~/.oocode/workspace/<id>`), que además llegaba con `~` literal sin
  expandir. Resultado: cada `bash` fallaba con
  `[Errno 2] No such file or directory: '~/.oocode/workspace/coding'`. Ahora usa el
  **`project_dir` del padre** (expandido), igual que el agente principal — el subagente
  trabaja en el mismo proyecto, no en su carpeta de identidad (`agent/subagent.py`).
- **Defensa en `bash_execute`** (`tools/bash.py`): el `workdir` se normaliza con
  `expanduser`/`expandvars` y, si la ruta no existe, cae a `None` (cwd del proceso) en
  vez de hacer crashear a `Popen`. Un `~` o ruta mal formada nunca vuelve a romper bash.
- `workspace.manager.agent_role` también expande `~` al leer `IDENTITY.md`.
  test_19 `TestBashWorkdirRobustness`/`TestSubagentToolWorkdir`.

### Workspaces — capa de personalización por-agente (TOOLS.md / AGENTS.md)

- **El usuario puede personalizar usos de herramientas y delegación sin tocar
  código.** Modelo en capas: el código mantiene la base invariable de disciplina y
  seguridad (`SYSTEM_RULES` + enforcement en `tools/bash.py`); encima, cada agente
  carga la sección **`## Notas`** de su `TOOLS.md` (preferencias de tools) y `AGENTS.md`
  (preferencias de delegación). `WorkspaceManager.load_mini_context()` las incluye en el
  system prompt vía el helper `_extract_section` (filtra los placeholders de plantilla y
  acota a 1500 chars), así que **no cuesta tokens hasta que el usuario personaliza**.
  Antes, editar esos ficheros no surtía efecto en el modo `mini` por defecto.
- Plantillas `workspace/templates/TOOLS.md` y `AGENTS.md` ganan una sección `## Notas`
  con guía de qué escribir. El roster de agentes sigue generándose dinámicamente en
  `_system_prompt` (lee el `Rol` de cada `IDENTITY.md`). test_81
  `TestWorkspaceCustomizationLayer`.
- **CLAUDE.md** documenta el flujo de arranque completo: agente por defecto `main`,
  los 7 ficheros del workspace, modos de contexto `mini` (default) vs `full`, los dos
  sistemas de memoria (workspace vs semántica) y el trust-check de `OOCODE.md`.

### Orquestación — el LLM sabe qué agentes hay y delega mejor

- **Especialidades de agentes expuestas al LLM.** Los schemas de `spawn_subagent`,
  `create_team` y `spawn_fanout` listaban solo IDs (`"main", "webcrawler"`) sin decir
  para qué sirve cada uno, así que el modelo no sabía, p.ej., que `webcrawler` es
  idóneo para búsquedas web. Ahora incluyen el **Rol** de cada agente, leído de su
  `IDENTITY.md` (helper público `workspace.manager.agent_role`, reutiliza
  `_extract_md_field`; `SubAgentRunner._agents_descr` cacheado). Además, el system
  prompt gana una sección **«Agentes disponibles para delegar»** (solo con >1 agente y
  no-subagente) para que el modelo evalúe la delegación de forma genérica, sin prompts
  específicos del backend. test_81.

### Subagentes — Timeout por paso/petición al LLM, no por tiempo total

- **El watchdog de timeout de subagentes ahora mide INACTIVIDAD, no tiempo total.**
  Antes, `subagents.defaultTimeout` (y `timeout_seconds`) disparaba un `kill_event`
  con `ev.wait(secs)` one-shot: mataba el subagente al alcanzar ese tiempo TOTAL,
  aunque estuviera progresando — una tarea larga y legítima se detenía «por acumular
  tiempo». Ahora el watchdog mata el subagente **solo si un paso pasa `secs` sin
  progreso**. El `AgentLoop` emite `sub.heartbeat()` (vía `_subagent_heartbeat`) al
  iniciar cada iteración, al recibir la respuesta del LLM y tras cada tool, así que
  el timeout es efectivamente **por petición al LLM / paso**: un subagente que avanza
  de forma sostenida no se detiene aunque la tarea completa dure mucho más; solo se
  mata si una sola petición o tool se cuelga más de `secs`.
- Mensaje de timeout actualizado: «subagente sin progreso» + texto que aclara que es
  por paso, no por tiempo total. `ActiveSubAgent.last_activity` + `heartbeat()` nuevos.
- Descripciones de config (`defaultTimeout`) y de los schemas `timeout_seconds`
  (`spawn_subagent`/`spawn_fanout`) reescritas. Sin cambios de formato del JSON.
  Tests: test_subagent_integration `TestInactivityWatchdog`.

### TUI — Recuperar el último mensaje tras compactar

- **El último mensaje del agente se re-muestra tras la compactación.** La
  compactación limpia el área visible del TUI; si saltaba justo después de que el
  agente terminara (p.ej. mostrando un resumen final que preguntaba si continuar),
  ese mensaje se perdía de vista y el usuario respondía a ciegas. Ahora
  `_show_compact_reset` (`ui/loop_tui.py`) re-imprime `_last_response` —que sigue
  vivo en contexto, la compactación no lo borra— renderizado igual que en el turno
  (Markdown, sangría 2), bajo el aviso «último mensaje del agente (antes de
  compactar)». Robusto si `_last_response` está vacío o sin inicializar. Solo TUI
  (el WebUI conserva la conversación en el DOM). test_13 `TestShowCompactReset`.

### Extensión VIM v3.1.0 — Streaming real y paridad con TUI/WebUI

La extensión de VIM/Neovim se conectaba mediante un flujo roto: mantenía un
stream SSE *y* enviaba los mensajes por `send_sync`, pero ambos acababan en
sesiones Flask distintas, así que el panel apenas mostraba el resultado final y
nunca el streaming en vivo. Esta versión lo arregla y lo alinea con el WebUI.

#### Arreglo central — sesión compartida SSE ↔ envío

- **Cookie de sesión establecida antes del stream** — un curl SSE persistente
  nunca vuelca el cookie jar (libcurl lo escribe al terminar la transferencia,
  y el stream no termina). Ahora el plugin hace primero una petición que
  COMPLETA (`GET /api/chat/status`) para fijar la cookie; luego el SSE y el
  `POST /api/chat/send` comparten `sid` y los eventos llegan a la cola correcta.
- **Envío vía `/api/chat/send` (fire-and-forget) en modo streaming** — en lugar
  de `send_sync`. Todos los eventos (text, tools, plan, subagentes, done) fluyen
  por el stream ya abierto, como en el navegador. `send_sync` queda solo como
  fallback (`g:oocode_stream=0` o VIM sin `+job`), sin un SSE compitiendo por la
  misma cola.

#### Paridad de eventos con el WebUI

- Nuevos handlers SSE: `status`, `preflight`, `plan_progress`, `subagent_start`,
  `subagent_done`, `embed_flash`, `inference_done`, además de los previos.
- **Subagentes** — cabecera del subagente y sus líneas (texto + tools) prefijadas
  con `│`, igual que el bloque dedicado del TUI/WebUI.
- **Texto intercalado en orden** — la prosa del agente se vuelca antes de cada
  evento estructurado (tool/plan/subagente), no acumulada al final del turno.

#### Control del turno (paridad con botones del WebUI)

- **`:OOCodeKill`** (`<Leader>oK`) — interrumpe el turno activo (`POST /api/chat/kill`).
- **`:OOCodeElevated [modo]`** (`<Leader>oe`) — cicla/establece `ask|off|on|full`.
- **Guard de turno** — no se solapan envíos; si el agente está ocupado avisa.
- **Watchdog** (`g:oocode_turn_timeout`, 360 s) — cierra el turno si el stream
  enmudece, para que el prompt no quede colgado en "Pensando…".

#### Config nueva

- `g:oocode_stream` (1) — streaming SSE vs `send_sync` bloqueante.
- `g:oocode_turn_timeout` (360) — timeout del watchdog del turno.

### TUI — Render de orquestación y contexto del subagente

- **El `task` de `spawn_subagent` y `explore` se renderiza como Markdown.** Cuando
  el agente principal delegaba con un `task` multilínea en markdown (contexto,
  listas numeradas, **negritas**…), el header lo volcaba en crudo vía `_esc()` —que
  escapa el markup Rich pero **no** interpreta markdown—, así que aparecía
  `**Contexto actual:**`, `- bullets`, etc. literales, escapando al formato de la
  conversación. Ahora la 1.ª línea del task va inline en el header (`● spawn_subagent
  💬 emoji nombre: …`) y el resto se renderiza como `Markdown` indentado. En
  `explore` además se **escapa** la 1.ª línea (antes iba sin escapar → el markup
  Rich del task se interpretaba). `agent/loop.py` (header spawn) + `agent/subagent.py`
  (header explore).
- **El `% ctx` del panel de subagentes refleja el contexto del SUBAGENTE activo,
  no el del agente principal.** El header del panel («⏵⏵ Subagentes Activos … N%
  ctx») derivaba el `%` de `self._agent_loop.context.stats()`, es decir el contexto
  del agente principal —que ya está en el toolbar de abajo—, no el del subagente en
  ejecución. Ahora toma `ctx_pct` del subagente `running` (o del último que reporte
  contexto); si ninguno ha completado aún su 1.ª petición al LLM, no muestra `%`.
  `ui/app.py:_get_subagent_panel_text`. Cada línea de subagente ya mostraba su
  `ctx_pct` propio; el bug era solo el valor del header.

### Backends — `/kill` aborta el LLM de inmediato (cierre forzado del socket)

- **`/kill` ahora interrumpe la generación del LLM al instante, también durante el
  prompt-eval o las pausas de generación.** El watchdog de kill cerraba el cliente
  HTTP (`httpx.Client.close()`), pero `close()` **no** desbloquea un `read()` colgado
  sobre una conexión en uso si el servidor está en silencio (p.ej. Ollama evaluando
  un prompt grande o pausando entre tokens). El hilo lector quedaba bloqueado en
  `recv()` y Ollama mantenía el request vivo (GPU ocupada) hasta que escribía o
  terminaba; el siguiente mensaje quedaba en cola tras esa generación «zombi». Ahora
  `kill_stream()` hace primero `shutdown(SHUT_RDWR)` del socket subyacente del stream
  activo (`api.base.force_close_httpx_sockets`): el `recv()` retorna de inmediato y
  el servidor detecta la desconexión y aborta la generación. Aplicado a los tres
  backends httpx: Ollama (`self._client._client`), OpenAI (`self._client`) y Anthropic
  (`self._client._client` del SDK). El helper es tolerante a la versión de httpx (si
  la estructura interna del pool cambia, no lanza). Tests: `TestForceCloseHttpxSockets`
  en `test_71_api_backends.py` (incl. integración con httpx real + servidor en silencio).

### `/kill` y `/kill all` — matar turno + subagentes + equipos al momento

- **`/kill` ahora mata también los subagentes y equipos activos, no solo el turno
  principal.** Antes solo ponía `_kill_requested` en el loop principal; si había un
  subagente corriendo (el padre bloqueado en `spawn_subagent`→`join`) o un equipo en
  marcha, `/kill` no surtía efecto hasta que terminaban. Nuevo `AgentLoop.request_kill()`
  centraliza el corte: marca `_kill_requested`, aborta el LLM en vuelo (socket, ver
  arriba) y dispara `subagent_runner.kill_all()`. Como los subagentes comparten el pool
  del cliente del padre, el cierre del socket también aborta sus `chat_sync` en vuelo;
  su bucle ve `_ext_kill` (nuevo check tras la llamada al LLM, además del de inicio de
  turno) y para al momento. Cableado en TUI (`/kill`, `Ctrl+C`), slash (`ui/commands.py`)
  y WebUI (`POST /api/chat/kill`, botón Kill) — paridad total.
- **Los miembros de un equipo (`run_team`) ya son matables.** `Team.execute` llamaba
  `runner.run()` **sin** `kill_event` ni registro, así que los miembros de equipo eran
  **inmatables** (no estaban en `_registry` y su `_ext_kill` era `None`). Ahora cada
  miembro se registra como `ActiveSubAgent` con su propia `kill_event`, por lo que
  `kill_all()` los alcanza y además aparecen en `/subagents` y en el panel de subagentes.
- **`/kill all`** = `/kill` + deshabilitar todos los jobs del scheduler + resetear las
  tareas `wip → todo`. El mensaje resume qué se detuvo (subagentes, jobs, tareas).
- **Mensaje correcto de kill manual vs timeout.** Cuando `kill_all` mataba un subagente
  de `spawn_subagent`, el closure lo reportaba como «Timeout». Ahora distingue: el
  watchdog marca `sub.error="Timeout: …"`; el kill manual no, así que muestra
  «Detenido por el usuario». Tests: `test_80_kill_all.py`.

### Tests

- 4482 tests (antes 4457): `TestInactivityWatchdog` (subagentes), `TestShowCompactReset`
  (recuperación de mensaje), `test_79_subagent_task_markdown` (render markdown del
  task de orquestación + ctx del panel), `TestForceCloseHttpxSockets` en
  `test_71_api_backends` (abort del LLM por cierre de socket, con integración httpx real)
  y `test_80_kill_all` (request_kill + miembros de equipo killables). La extensión VIM
  se validó end-to-end contra la WebUI.

## v0.4.2 (2026-06-03) — Flujo de conversación multidominio + paridad TUI/WebUI

OOCode es multi-agente: el usuario empieza con un agente `main` (asistente de código) pero puede crear agentes de cualquier dominio (oficina, seguridad, investigación web, IoT, datos…) con `/agent new` y los ficheros `.md` de su workspace. Esta versión hace que el flujo de conversación —preflight, planificación, anuncios de acción, narración de equipos— sea coherente para **cualquier dominio**, no solo programación, y alinea TUI y WebUI.

### Orquestación

- **Tools de orquestación fuerzan modo secuencial** — `spawn_subagent`, `spawn_fanout`, `create_team`, `run_team` y `explore` (`_ORCHESTRATION_TOOLS`) ya no se paralelizan en el `ThreadPoolExecutor`. Antes, al batchear `spawn_subagent` con `grep_code`/`read_file` en un mismo turno, la cabecera y el streaming `│` del subagente quedaban "encerrados" en el bloque anterior. Para paralelismo real se usa `spawn_fanout`/`create_team`.

### Flujo de conversación agnóstico de dominio

- **`SYSTEM_RULES` con núcleo neutral** — el ciclo de trabajo (Clasifica → Reúne contexto → Actúa → Verifica → Finaliza) ahora es aplicable a cualquier dominio; la disciplina de código (explorar con grep/lsp, `run_tests`, ficheros grandes, edición segura) vive en un bloque condicional **"Cuando trabajes con código"**.
- **Hints dinámicos sin asumir edición de código** — el aviso de "escrituras sin tests" solo se dispara si se tocó código real (detección por extensión, no por tipo de agente); los avisos de exploración sin acción usan lenguaje neutral. Un agente de ofimática que genera un `.docx` ya no recibe avisos de tests.
- **Frases de preflight neutras + nuevos dominios** — las frases genéricas ya no asumen "código"/"módulo"; añadidos dominios `web` (investigación/crawl) y `data` (análisis/SQL).
- **Verbos del live block para tools MCP** — el indicador "●" muestra verbos de dominio para tools de oficina/email/IoT/datos/web/seguridad ("Generating…", "Sending email to…", "Querying…", "Controlling…") en vez de un genérico.

### Agentes y equipos

- **`/agent new` personaliza la persona por dominio** — clasificación automática del dominio (código/oficina/seguridad/IoT/web/datos/DevOps); el prompt de personalización por LLM es consciente del dominio (no asume programación) y hay un fallback determinista (`SOUL.md` adaptado al dominio) cuando no hay LLM disponible.
- **Narración de equipos** — regla explícita para anunciar la composición del equipo antes de `create_team`/`run_team`/`spawn_fanout` y para sintetizar qué aportó cada agente antes de cerrar la tarea.

### WebUI

- **Página de configuración consciente del backend** — `/config` refleja el bloque `api` unificado (`type`/`key`/`host`/`extraHosts`/`embedHost`/`subagentRouting`/retry) y los campos de subagentes (`autoContMax`/`inferenceTimeout`/`defaultTimeout`).
- **Hooks de subagente visibles en su bloque** — en el dispatch paralelo, el canal de impresión de hooks (`threading.local`) se reinyecta en cada hilo worker, así los hallazgos de `interface_change_detector`/lint/verify de un subagente llegan a su bloque (antes caían al fallback de consola y se perdían).
- **Tarjetas de descarga solo para entregables** — aparecen para documentos ofimáticos/PDF (lo que el usuario pide producir), no para ediciones de código ni ficheros temporales.
- **Status bar única (paridad con el TUI)** — eliminada la barra de estado duplicada (arriba y abajo mostraban agente/modelo/ctx); ahora hay una sola barra, como el toolbar del TUI.

#### Refinamientos del flujo de conversación WebUI (2026-06-04)

Principio rector: **lo que es estado va en la barra de estado; lo que es contenido va en la conversación.**

- **Status bar reubicada bajo el prompt** — orden de arriba abajo: indicador "Pensando" → prompt → team-bar → status bar (agente/modelo/ctx/indicadores) → filas de detalle MCP/LSP. Antes la status bar quedaba al fondo, por debajo de MCP/LSP; ahora la línea principal va arriba y el detalle MCP/LSP debajo, igual que el toolbar del TUI.
- **Team-bar de una sola línea** — la cabecera de equipo muestra una línea compacta `📋 Agente principal 💬 💻 Subagente · N subagente(s)`. Se revirtió el detalle multilínea por subagente (tarea/elapsed/ctx%) que **desbordaba** la barra de estado (la tarea podía ocupar párrafos enteros). Ese detalle largo ahora vive en el **bloque del subagente dentro de la conversación**.
- **Tarea del subagente en su bloque** — al arrancar un subagente, su tarea encomendada se siembra al principio de su bloque en la conversación (no en el status), donde se acumulan también su plan, su texto y sus herramientas.
- **Eliminado el bloque de herramienta huérfano "◐ Subagent"** — `spawn_subagent` ya no emite un `tool_start` del agente principal en WebUI: se representa con `subagent_start` + su propio bloque. Antes se creaba un bloque de herramienta que nunca se cerraba (el `tool_done` se convierte en `subagent_done`), quedaba colgado y provocaba que textos del subagente se salieran de su bloque.
- **La barra "Pensando" ya no muestra títulos de herramientas** — es estado puro (palabras ciclantes + frases de preflight); el detalle de cada herramienta aparece en su bloque dentro de la conversación, no en el prompt.
- **Limpieza** — eliminada la rama muerta del evento `preflight` (referencias a IDs inexistentes) y corregido el chequeo de visibilidad del indicador "Pensando" al pausarse el streaming.

#### Historial de prompt y sesiones compartidos TUI ↔ WebUI (2026-06-04)

- **Mismo historial de input del prompt** — el WebUI escribe y **lee** el mismo `~/.oocode/history` que el TUI (formato `prompt_toolkit FileHistory`). El recall con flecha arriba ahora coincide entre ambos y sobrevive a recargas de página (antes el WebUI usaba un historial en memoria que se perdía al recargar). Helpers compartidos `append_input_history`/`load_input_history` en `agent/session.py`.
- **Formato compatible y sin contaminar** — los mensajes **multilínea** se guardan con prefijo `+` por línea (antes solo la primera línea lo llevaba, corrompiendo la entrada para el TUI) y **ya no se escribe la respuesta del agente** en el historial de input (solo lo que teclea el usuario). `send_sync` (vim/CLI) también alimenta el historial compartido.
- **Recuperación de sesiones en el WebUI** — el botón *Cargar* del panel 📚 Sesiones ahora **restaura de verdad** la sesión (nuevo `POST /api/chat/load_session`): reusa `AgentLoop.restore_session` (igual que el TUI) sobre el mismo JSONL y re-renderiza la conversación. El slash `/session <id>` también funciona en el WebUI (antes se enviaba al LLM como mensaje y el botón solo mostraba una instrucción que no hacía nada).

### Robustez de edición

- **Anti-bucle unificado en ediciones** — los fallos de modificación del mismo fichero en un turno (PRE-EDIT fallido de `edit_file`, regex sin coincidencias, llamada duplicada) ahora cuentan juntos y escalan: 1.º indica leer y copiar literal; 2.º **inyecta el contenido real del fichero** (ground truth) y avisa de que el cambio puede estar ya aplicado; 3.º para en seco. Corta el bucle típico `edit → regex → write` que no avanzaba tras una compactación (antes solo escalaban los `regex_replace` sin coincidencias; los `edit_file` y los duplicados no contaban).

#### Streaming del subagente en el TUI (2026-06-04)

- **Presupuesto de líneas `│` del subagente ahora es por turno (no por ejecución completa)** — el streaming `│` del subagente tiene un cap de líneas (`_MAX_SUB_LINES`, 12) pensado **por turno**, pero solo se reseteaba una vez al arrancar el subagente. Un subagente multi-turno (auto-continue) consumía su presupuesto en el primer turno, imprimía `… buffer lleno` y **congelaba** — el usuario veía las líneas más antiguas y dejaba de ver toda la actividad posterior. Ahora el contador se refresca al inicio de cada turno: cada turno muestra líneas nuevas y las antiguas hacen scroll hacia arriba en el buffer de salida, como era la intención original.

### Tests

4457 tests (sin LLM ni servidor externo).

---

## v0.4.1 (2026-06-03) — Consistencia multi-backend + correcciones

Versión de pulido que hace que los backends OpenAI-compatible y Anthropic (experimentales, introducidos en v0.4.0) funcionen de forma coherente en **todos** los comandos y diagnósticos, no solo en el bucle del agente.

### Correcciones

- **Bug: `doc_create` fallaba con `'str' object has no attribute 'get'`** (`mcp_servers/home_office_assistant.py`) — cuando el LLM pasaba `content_blocks` como string JSON, bloques individuales como strings sueltos, `metadata`/`sheets`/`slides` como JSON, o un dict único en vez de lista. Nuevos helpers `_coerce_json` y `_norm_blocks` normalizan la entrada antes de procesarla (envuelven strings sueltos como párrafos, parsean JSON, descartan tipos inválidos).
- **Bug: mensaje "Subagente detenido por el usuario" espurio** — el watchdog de timeout (`subagents.defaultTimeout` o `timeout_seconds` del LLM) disparaba `kill_event` y `_turn_loop_guard` imprimía siempre "detenido por el usuario" sin distinguir un timeout automático de un kill manual. Ahora el guard inspecciona el `ActiveSubAgent` y muestra el motivo real (timeout vs. usuario). El mensaje de retorno al LLM usa el timeout efectivo (`_eff_timeout`), no el argumento original.
- **Fuga de hilos watchdog** — en una finalización normal el `kill_event` nunca se seteaba, así que el hilo watchdog quedaba dormido el `secs` completo (acumulación con `defaultTimeout` alto). El worker ahora hace `kill_ev.set()` en el `finally` para liberarlo de inmediato.
- **Embeddings apuntaban al servidor equivocado con backend no-Ollama** — `effective_embed_host` devolvía la URL del servidor OpenAI/Anthropic (porque el campo unificado `api.host` alimenta `ollama_host`), pero las embeddings SIEMPRE usan el protocolo Ollama. Ahora cae al host local de Ollama (`localhost:11434`) cuando `api.type != "ollama"` y no hay `embedHost` dedicado.
- **`/switch` usaba `ollama_host` para embeddings** — único `EmbeddingClient` del repo que no usaba `effective_embed_host`; corregido. Con backend no-Ollama o `embedHost` dedicado, las embeddings del agente conmutado apuntaban al servidor equivocado.
- **`_personalize_workspace_with_llm` rompía con backend no-Ollama** — usaba `ollama.Client().chat()` directo; migrado a `build_client(config)` + `chat_sync()` (funciona con cualquier `api_type`).

### Mejoras

- **`/doctor`, `--doctor` y doctor WebUI conscientes del backend** — nuevo helper compartido `_doctor_llm_backend_checks` (elimina ~60 líneas duplicadas). Con backend Ollama: lista modelos, verifica modelo/fallback/hosts extra. Con OpenAI: reporta tipo/baseUrl/key + conectividad ligera a `/models`. Con Anthropic: reporta tipo/key (falla si falta) + paquete instalado. Las embeddings se verifican siempre contra `effective_embed_host` (protocolo Ollama). Antes daban un FALLO falso de Ollama con cualquier backend no nativo.
- **`/config`, `/settings` y `/model` conscientes del backend** — `/config show` añade sección "Backend (api)" (type/host/key enmascarada/baseUrl/embedHost según backend) y sección "Subagentes" (que no se mostraba); `/settings` muestra fila "Backend"; `/model` indica el backend; `/model <nombre>`, `/config edit` y `/models` ya no sondean Ollama inútilmente con backend no nativo.
- **`subagents.inferenceTimeout` ahora aplica siempre** — nuevo campo de runtime `inference_timeout_override` con máxima prioridad en `model_timeout` (override > per-model > fallback > 0). Antes solo surtía efecto si había un modelo de fallback configurado.

### Infraestructura

- **Instalador** — el `oocode.json` por defecto que escribe `install.sh` usa el bloque `api` unificado (no el legacy `ollama`) e incluye el bloque `subagents`.
- **`completion.phrase` despromocionado** — el bloque `completion` es un ajuste **interno** (señal de fin de turno + control de auto-continue), no una personalización de las respuestas del agente. Ya **no se materializa** en `oocode.json` (`save()` no lo escribe) ni se muestra en `/config`. `load()` lo sigue respetando si un agente multi-idioma lo añade a mano, como *escape hatch* para que la detección de fin de turno funcione en idiomas distintos de ES/EN.
- **Limpieza de código muerto y duplicaciones** — barrido tras los refactors de `api/`/`config/`:
  - Eliminados 3 ficheros `.tmp` huérfanos (escrituras atómicas interrumpidas) y la property muerta `OllamaBackend.raw_client`.
  - Eliminadas funciones muertas: `MemorySystem._auto_suggest_memories`, `RuntimeSettings.summary_line`, `AgentLoop._chat_kwargs` (resto del path `client.chat()` previo a la abstracción de backends), más 5 bloques de código comentado.
  - **Nuevo `api/ollama.py::ollama_model_names`/`list_ollama_models`** — fuente única para listar/parsear modelos Ollama; consolida 6 copias (`/doctor`, `/models`, `/fast`, `/config`, selector de modelo, gateway-status).
  - **Nuevo `agent/services.py`** (`build_workspace_manager`/`build_embedding_client`/`build_memory_system`) — factories del stack de agente que unifican el bootstrap del TUI, WebUI y `/switch`. Elimina la divergencia que había causado el bug de embeddings en `/switch`.
- **Tests** — 4374 tests (100% pasando, +16 en `tests/test_72_services_and_model_helpers.py`).

---

## v0.4.0 (2026-06-02) — Multi-backend API + HTTP Client MCP

### Nuevas características

- **Multi-backend LLM** (`api/`) — OOCode ya no está atado a Ollama. Nuevo módulo `api/` con tres backends intercambiables seleccionables en `oocode.json`:
  - `api/ollama.py` (`"type": "ollama"`) — comportamiento anterior, sin cambios
  - `api/openai.py` (`"type": "openai"`) — compatible con cualquier servidor OpenAI-API (llama.cpp, LM Studio, vLLM, koboldcpp, OpenAI cloud); usa `httpx` directo sin dependencia del paquete `openai`
  - `api/anthropic.py` (`"type": "anthropic"`) — API de Anthropic con conversión automática de mensajes y tool schemas; soporta streaming y thinking blocks
  - `api/base.py` — tipos normalizados `Chunk`, `ToolCall`, `Response`, `BackendClient` ABC; misma interfaz de atributos (`.function.name`, `.function.arguments`, `.model_dump()`) para compatibilidad con el código existente
  - `build_client(config)` factory en `api/__init__.py` — el tipo se lee de `oocode.json`: `{"api": {"type": "openai", "key": "...", "baseUrl": "http://localhost:8080/v1"}}`
  - Subagentes heredan automáticamente `api_type`, `api_key`, `api_base_url` del config padre
  - `ollama_client=` en `AgentLoop.__init__` sigue funcionando como alias deprecado

- **HTTP Client Assistant MCP** (`mcp_servers/http_client_assistant.py`) — nuevo servidor MCP con 17 herramientas para desarrollo y debugging de APIs REST:
  - `http_request` — GET/POST/PUT/PATCH/DELETE con headers, auth, body, timeouts
  - `http_get` — migrado desde oocode-assistant (oocode-assistant: 54→53 tools)
  - `http_headers`, `http_auth` (bearer/basic/oauth2), `http_upload` (multipart)
  - `response_diff` — compara dos respuestas HTTP campo a campo
  - `openapi_validate` — valida request/response contra schema OpenAPI (JSON Schema)
  - `curl_import` — convierte un comando curl a una llamada http_request
  - `websocket_send` — envía mensajes WebSocket (requiere `websocket-client`)
  - `sse_listen` — escucha un endpoint SSE y recoge N eventos
  - `mock_server_start` / `mock_server_stop` — servidor HTTP mock local en un thread daemon
  - `http_health_check` — verifica disponibilidad de endpoints con métricas de latencia
  - `graphql_query` — ejecuta queries GraphQL con soporte de variables
  - `jwt_decode` — decodifica JWT (sin verificación de firma, para debugging)
  - `http_batch` — ejecuta múltiples requests en paralelo
  - `http_history` — historial de requests de la sesión con estadísticas
  - Activar: `{"mcp": {"httpClientAssistant": {"enabled": true}}}`

- **`/mcp` muestra todos los bundled** — el comando `/mcp` ahora lista los 8 servidores MCP bundled aunque estén desactivados, con estado `●/○`, counts de tools/resources/prompts y flag `enabled/disabled`. Antes solo mostraba los servidores corriendo.

### Correcciones

- **Bug: devops-assistant mostraba 0 prompts y 0 resources** — `mcp_client.py` usaba `not self._capabilities.get("resources")` que evaluaba el dict vacío `{}` como falsy; corregido a `"resources" not in self._capabilities`; afectaba a todos los servidores con capabilities vacías

### Optimizaciones

- **SYSTEM_RULES −51% tokens** — reescritura de las reglas del sistema desde ~3795 a ~1840 tokens; secciones de planificación convertidas a tablas compactas; reglas de comunicación deduplicadas; todos los comportamientos críticos preservados

### Infraestructura

- `tools/registry.py`: nuevo método `tool_schemas()` (renombrado de `ollama_schemas()`); `ollama_schemas()` mantenido como alias de compatibilidad
- `agent/subagent.py`: usa `backend_client=` en lugar de `ollama_client=` al instanciar AgentLoop
- **Tests** — 4375 tests (100% pasando, +49 en `tests/test_71_api_backends.py`)

---

## v0.3.10 (2026-06-02) — Subagentes: auto-continues y timeout configurables

- **Bug: subagente para antes de terminar la tarea** — `auto_continue_max=8` del agente principal se aplicaba también a los subagentes; tareas complejas de 3-4 pasos agotaban los 8 turnos y devolvían resultado parcial; el agente principal interpretaba "herramienta ejecutada" como "tarea completada". Nuevo campo `subagents.autoContMax` (default: 16) en `oocode.json` — sobreescribe `auto_continue_max` solo para subagentes, sin tocar el límite del agente principal
- **Bug: timeout de inferencia de 120s no configurable desde el bloque de subagentes** — `fallback.timeoutSeconds=120` (segundos sin tokens antes de usar fallback) se aplicaba igual a subagentes; inferencias largas (razonamiento complejo) provocaban abort prematuro; no era configurable desde el bloque `subagents` de `oocode.json`. Nuevo campo `subagents.inferenceTimeout` (default: 0 = hereda de `fallback.timeoutSeconds`) — permite fijar un límite de inferencia más alto para subagentes
- **Nuevo campo `subagents.defaultTimeout`** — timeout de tarea máximo por subagente en segundos (0 = sin límite); cuando el LLM llama `spawn_subagent` sin especificar `timeout_seconds`, se aplica este default; aplica también a `spawn_fanout`; `timeout_seconds` explícito del LLM siempre tiene precedencia
- **Robustez: guards `isinstance(int)` en overrides de config** — los tres nuevos overrides usan `getattr + isinstance` para que tests con `MagicMock` sigan pasando sin modificar fixtures existentes
- **Tests** — 3999 tests (100% pasando, +15 tests nuevos en `TestSubagentsConfigNewFields`, `TestSubagentRunAppliesConfig`, `TestSpawnSubagentDefaultTimeout`)

## v0.3.9 (2026-06-02) — WebUI beta

- **WebUI promovido a beta** — 122 tests al 100%; paridad de características completa con el TUI; listo para uso en producción desde navegador y extensiones de editor
- **WebUI: evento SSE `inference_done`** — `loop_webui.py` emite `inference_done` al finalizar cada turno; el chat muestra "⚡ Inferencia completada." y limpia el indicador de pensando; replica el comportamiento del TUI
- **WebUI: tarjetas de archivo siempre visibles** — eliminada la dependencia de la clase `.expanded`; el botón de descarga es ahora visible independientemente del estado del bloque de tools (`display:flex !important`)
- **WebUI: escape correcto de guiones bajos en rutas** — rutas de fichero con `_` (p. ej. `report_2026_final.docx`) protegidas antes del escape HTML para evitar que sean interpretadas como cursiva en Markdown
- **WebUI: icono `◐` correcto durante ejecución** — `_updateToolBlockHeader` solo sobreescribe el header con el resumen cuando no hay tools en ejecución; mantiene `◐` visible mientras corren herramientas
- **WebUI: previsualización de imágenes adjuntas** — `appendUserMsg` acepta `images[]` con `previewUrl`; las imágenes adjuntas se muestran inline en el mensaje del usuario
- **WebUI: `api_chat_history` corregida** — eliminado import local incorrecto (`from webui.sessions import _get_or_create_sid`); revertida lógica errónea que leía `~/.oocode/history` (historial readline del TUI) como historial de conversación
- **Compactación de contexto mejorada** — estimación de tokens por tipo de mensaje (tool results 2.5 chars/tok, thinking 4.0, texto 3.5); `compact_threshold` bajado a 0.80; punto de corte busca hacia atrás hasta 5 mensajes para alinear en frontera `user`; tarea original anclada en el resumen (`**Tarea original:**`) para no perderla entre compactaciones; re-condensación LLM del resumen acumulado cuando supera `maxSummaryChars`
- **SYSTEM_RULES: árbol de decisión de planificación 4 niveles** — Nivel 1 (directo ≤2 pasos), Nivel 2 (texto breve sin plan), Nivel 3 (`plan_create` con checklist), Nivel 4 (paralelismo/subagentes/equipos); reemplaza la regla "≥3 pasos → siempre plan"; tabla de paralelismo universalizada para tareas complejas
- **Hint #13 mejorado** — tras ≥5 tool calls exploratorias sin escritura, distingue exploración de módulo único (empuja a ejecución directa Nivel 1/2) vs. multi-módulo ≥3 directorios (empuja a subagentes/spawn_fanout/create_team)
- **WebUI: salida idéntica al TUI** — conversación, bloques de tools y planes con los mismos símbolos (●/│/◐/⎿/◈/✔/◼/◻); fuente monoespaciada; palabras inventadas de pensamiento (`Cavilando…`, `Tokenizando…`, etc.) en la barra de estado superior (no en la conversación); bloque colapsable para tools; `appendPlan`/`updatePlanProgress` con CSS plano estilo TUI
- **WebUI: indicador "Pensando" en barra de estado** — las palabras inventadas del TUI ciclan en `sb-think` (barra superior) junto a la barra de contexto `▱▱▱▱▱▱▱▱▱▱`; eliminado el div en la conversación; durante tools muestra `◐ nombre_tool` en la barra
- **WebUI: página de configuración completa** — expuesta toda la `OOConfig` en 17 secciones: Ollama, Modelo global, WebUI, Contexto/Compactación, Límites de herramientas, RAG, Embeddings, SearXNG, MCP Servers (5 toggles), Hooks, Subagentes, Backups, Snapshots, Logging, Visión, Chat log, Fallback, Apariencia; API GET/POST actualizadas (~50 parámetros)
- **Tests** — 3984 tests (100% pasando, sin LLM ni servidor externo)

## v0.3.8 (2026-05-31)

- **Auditoría de código muerto y duplicados** — revisión integral del código buscando funciones duplicadas, imports muertos y conjuntos de nombres de tools inconsistentes entre módulos
- **Bug: `smart_replace` fuera del guard de dedup** — `self._WRITE_TOOLS` en `agent/loop.py` no incluía `smart_replace`; llamadas repetidas con los mismos args en el mismo turno no se bloqueaban; corregido
- **Bug: `lsp_rename`/`lsp_code_actions` sin hooks** — no estaban en `_ALL_MODIFY_TOOLS` de `tools/hooks.py`; los hooks `lint_after_write`, `lsp_after_write`, `interface_change_detector`, etc. no se disparaban después de un rename o code action de LSP; corregido
- **Refactor: `_fmt_sub_elapsed` eliminada** — duplicado de `_fmt_elapsed` (con formato incompatible) eliminado de `agent/subagent.py`; unificado con `_fmt_elapsed` de `loop_helpers.py`
- **Limpieza: imports muertos** — `_is_write_tool` (sin usar) eliminado de `agent/loop.py`; `sys`, `os`, `_TOOL_LIVE_VERBS`, `_COMPACT_LOCK` (sin usar) eliminados de `ui/loop_tui.py`
- **Refactor: `_write_tool_names` inline** — definición inline de frozenset en `_turn_display_bullet` reemplazada por `self._WRITE_TOOLS`; una sola fuente de verdad para los nombres de write tools
- **TUI: display de replace tools** — `_call_context` para `regex_replace`/`smart_replace`/`bulk_replace` trunca el patrón a la primera línea (55 chars + `…`); elimina la inundación multi-línea antes del diff
- **TUI: preview del live block para edit/replace** — `_make_tool_preview` corrige la clave del arg (`"file"` en lugar de `"path"` para `smart_replace`/`regex_replace`); elimina las líneas `- old`/`+ new` del preview pre-ejecución; el diff coloreado real ya aparece después de la ejecución
- **Tests** — 3984 tests (100% pasando)

## v0.3.7 (2026-05-31)

- **AgentTeam como tool LLM** — `create_team` + `run_team` como herramientas nativas; el agente puede descomponer tareas en subtasks paralelas asignadas a agentes especializados y sintetizar los resultados
- **Flujo de resultados de equipos** — `run_team` inyecta los resultados de cada subagente al agente líder para síntesis; fix de `loop._last_response` para capture_output=False
- **`spawn_fanout`** — nueva herramienta `spawn_fanout(chunks, agent_id)` para análisis paralelo divide-and-conquer; hereda semáforo de concurrencia y timeout
- **Plan ↔ TaskManager sync** — `_plan_tasks` persisten al reiniciar vía `TaskManager` con marcador `__plan__`; visibles en `/task list`; restauración automática al arrancar
- **Timeout por subagente** — `timeout_seconds` en `spawn_subagent`/`spawn_fanout`; watchdog thread con `kill_event.wait()` mata subagentes colgados automáticamente
- **TUI live block mejorado** — `◐ Tool: (path)` y `◐ Bash: $ cmd` inline; diff preview/`Running…` debajo; tools completadas muestran path/cmd; máx 8 líneas `│` antes de `⎿`
- **Limpieza: referencias personales** — eliminadas todas las referencias personales del código; IDs de agentes de ejemplo hardcodeados reemplazados por placeholders genéricos
- **Limpieza: identificadores mixtos** — identificadores mezcla español/inglés en tests (`tarea_rapida`, `tarea_SLOW`…) renombrados a inglés consistente
- **Tests** — 3984 tests (100% pasando)

## v0.3.6 (2026-05-31)

- **TUI refinements** — `_update_live_bullet_cb` muestra la acción de la herramienta activa en el `●` pulsante; `●display(ctx)` como encabezado de tool; `⎿` sin `◐`; resumen compacto normalizado ("Searched for", "lines" en inglés)
- **WebUI print pollution fix** — `_print()` TUI-específicos (preflight/auto-continue/plan/resume/retry) filtrados con `if not _webui_queue`; JS de `thinking` preserva el label preflight
- **WebUI/TUI callbacks** — TUI sin `invalidate()` en callbacks intermedios del live block (blink timer suficiente); status SSE emitido al inicio de turno; file cards unificadas a `.tui-file-card`
- **Tests** — 3932 tests (100% pasando)

## v0.3.5 (2026-05-31)

- **Configuración completa desde oocode.json** — todos los parámetros internos (chunking RAG, caché embeddings, highWater de contexto) son ahora configurables en `~/.oocode/oocode.json`; eliminados todos los valores hardcodeados
- **Display compacto mejorado** — cada fichero en una línea separada con `│` (U+2502) y `⎿` en el último elemento; símbolo correcto `↻` para compactación en la barra de estado
- **Limpieza de código** — eliminados duplicados funcionales (`_fmt_tokens`, `_progress_bar`, `chunk_with_metadata` standalone); eliminadas 5 entradas no-op en `_TOOL_ALIASES`; unificadas 6 sets de write-tools en `_is_modify_tool()`; eliminado tracking dual `_task_modified_files`
- **Correcciones de robustez** — sincronizado `_RICH_TAG_RE` entre `loop.py` y `app.py`; corregido prefijo `[caché]` visible al LLM; eliminado bloque unreachable en el dispatch de tools; eliminado segundo `keep_alive` pop en `_chat_kwargs`

## v0.3.4 (2026-05-30)

- TUI Claude Code style: `●` sin sangría, `⎿` sin `◐`, resumen compacto
- WebUI + TUI fixes: collapse via `.expanded`, file cards unificadas, status al inicio de turno
- Home Office v5: `doc_create` + `template_path`, checklist/callout/highlight/toc en Word
- Home Office OOXML refactor: gráficas OOXML nativas (sin PNG), diagramas bar/pie/line
- External MCP support: `mcp_manager.py` + `catalog.json`, hot-add sin reiniciar
- WebUI refactorizada en 13 módulos Blueprint
