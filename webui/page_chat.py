"""Blueprint /chat — TUI completo CSS+HTML+JS."""
from flask import Blueprint

from webui.helpers import _load_ooconfig
from webui.templates import _render

bp = Blueprint("page_chat", __name__)


@bp.route('/chat')
def chat_page():
    cfg    = _load_ooconfig()
    agents = cfg.agents if cfg else []
    agent_opts = "".join(
        f'<option value="{a.id}" {"selected" if a.id==(cfg.agent_id if cfg else "main") else ""}>'
        f'{a.emoji} {a.name} ({a.id})</option>'
        for a in agents
    ) or '<option value="main">🤖 OOCode (main)</option>'

    content = f"""
<style>
body {{ overflow:hidden; }}
.main-content {{ padding:0 !important; }}
.tui-kill-btn {{
  background: #3a1010; border: 1px solid #f38ba8; color: #f38ba8;
  border-radius: 6px; padding: 6px 12px; font-size: .9rem;
  cursor: pointer; transition: background .15s;
  flex-shrink: 0;
}}
.tui-kill-btn:hover {{ background: #f38ba8; color: #1e1e2e; }}
.tui-sb-badge.elev-clickable {{
  cursor: pointer; user-select: none;
  transition: background .15s, color .15s;
}}
.tui-sb-badge.elev-clickable:hover {{ background: rgba(255,255,255,.12); border-radius: 4px; }}
.tui-sb-badge.elev-ask  {{ color: #556677; }}
.tui-sb-badge.elev-off  {{ color: #f38ba8; }}
.tui-sb-badge.elev-on   {{ color: #a6e3a1; font-weight: 600; }}
.tui-sb-badge.elev-full {{ color: #fab387; font-weight: 700; }}
/* EMBED flash badge */
.tui-sb-badge.embed-read {{ color: #cba6f7; animation: embedFlash 2s ease-in-out; }}
.tui-sb-badge.embed-save {{ color: #f9e2af; animation: embedFlash 2s ease-in-out; }}
@keyframes embedFlash {{
  0%   {{ opacity:0; transform:scale(.85); }}
  12%  {{ opacity:1; transform:scale(1.08); }}
  70%  {{ opacity:1; transform:scale(1); }}
  100% {{ opacity:0; transform:scale(.95); }}
}}
/* Team / subagent bar — SOLO cabecera de una línea (status, bajo el prompt).
   El detalle por subagente (tarea/tools/texto) vive en su bloque en la conversación. */
#tui-team-bar {{
  font-size: .73rem; color: #4fd6be;
  padding: 3px 12px; background: rgba(20,70,60,.10);
  border-top: 1px solid rgba(79,214,190,.10);
  border-bottom: 1px solid rgba(79,214,190,.10);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.team-hdr {{ color: #4fd6be; font-weight: 600; white-space: nowrap; }}
.team-sub {{ color: #cdd6f4; }}
.team-sub.done {{ color: #3a8a5a; }}
.team-chat {{
  display: inline-block;
  animation: teamChatBlink .65s ease-in-out infinite alternate;
}}
@keyframes teamChatBlink {{
  from {{ opacity: .25; transform: scale(.9); }}
  to   {{ opacity: 1;   transform: scale(1.05); }}
}}
.tui-subagent-block {{
  margin: 8px 0 8px 4px;
  border-left: 2px solid #1e6a5a;
  background: rgba(20,70,60,.05);
  border-radius: 0 6px 6px 0;
  border-top: 1px solid rgba(79,214,190,.08);
}}
.tui-subagent-hdr {{
  display: flex; align-items: center; gap: 6px;
  padding: 5px 10px 4px 10px;
  font-size: .76rem; color: #4fd6be; font-weight: 600;
  background: rgba(20,70,60,.15);
  border-bottom: 1px solid rgba(79,214,190,.12);
  border-radius: 0 6px 0 0;
  cursor: pointer; user-select: none;
}}
.tui-subagent-hdr:hover {{ background: rgba(20,70,60,.25); }}
.tui-subagent-dot {{
  display:inline-block; width:6px; height:6px;
  background:#4fd6be; border-radius:50%;
  animation: subDotPulse 1.4s ease-in-out infinite;
}}
.tui-subagent-done .tui-subagent-dot {{
  background:#1e6a5a; animation:none;
}}
@keyframes subDotPulse {{ 0%,100%{{opacity:.4}} 50%{{opacity:1}} }}
.tui-subagent-label {{ flex:1; }}
.tui-subagent-elapsed {{ color:#4a8a7a; font-weight:normal; }}
.tui-subagent-toggle {{ font-size:.65rem; color:#4fd6be; opacity:.7; flex-shrink:0; }}
.tui-subagent-body {{
  padding: 4px 10px 6px 10px;
  max-height: 640px; overflow-y: auto;
  overflow-x: hidden;
  transition: max-height .3s ease-out, padding .3s ease-out;
}}
.tui-subagent-block.collapsed .tui-subagent-body {{
  max-height: 0; overflow: hidden; padding-top: 0; padding-bottom: 0;
}}
.tui-subagent-text {{
  font-size: .84rem; color: #a0aab8; line-height:1.55;
}}
/* Override md-body inside subagent for smaller fonts */
.tui-subagent-text.md-body {{ font-size:.83rem; color:#9aa3b0; }}
.tui-subagent-text.md-body h1,.tui-subagent-text.md-body h2,.tui-subagent-text.md-body h3 {{ font-size:.88rem; }}
/* Tarea del subagente — sembrada en su bloque de conversación al arrancar (subagent_start) */
.tui-subagent-task {{
  font-size:.8rem; color:#8a96a4; line-height:1.5;
  padding:5px 10px 5px 10px;
  border-bottom:1px dashed rgba(79,214,190,.12);
}}
.tui-subagent-task-label {{
  display:inline-block; font-size:.64rem; font-weight:700;
  color:#4fd6be; text-transform:uppercase; letter-spacing:.05em;
  margin-right:6px;
}}
.tui-subagent-task.md-body p {{ margin:.2em 0; }}
/* Preview text inside tool rows */
.tui-tool-result {{
  display:block; color:#5a8fa8; font-size:.72rem; font-family:monospace;
  padding: 1px 0 2px 22px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  max-width:600px;
}}
.tui-tool-nlines {{ color:#5a8090; font-size:.7rem; flex-shrink:0; margin-left:4px; }}
.tui-file-link {{ color:#00aacc; text-decoration:none; font-weight:500; }}
.tui-file-link:hover {{ text-decoration:underline; }}
.tui-dl-btn {{ display:inline-flex; align-items:center; padding:0 5px;
  background:rgba(0,180,220,.15); color:#00aacc;
  border:1px solid rgba(0,180,220,.3); border-radius:3px;
  font-size:.72rem; text-decoration:none; vertical-align:middle; margin-left:2px; }}
.tui-dl-btn:hover {{ background:rgba(0,180,220,.3); }}
/* Tarjeta de fichero — visual styling (display controlado por templates.py via .expanded) */
.tui-file-card {{
  align-items:center; gap:6px;
  padding:6px 10px 7px 14px;
  font-size:.82rem; color:#4a8fa8;
  border-top:1px solid rgba(0,170,200,.18);
  background:rgba(0,160,200,.07);
}}
.tui-file-card.edited {{ border-top-color:rgba(137,180,250,.2); background:rgba(137,180,250,.06); }}
.tui-ifc-icon {{ font-size:1rem; flex-shrink:0; }}
.tui-ifc-name {{ color:#00ccee; font-weight:600; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; }}
.tui-ifc-badge {{ font-size:.68rem; padding:1px 7px; border-radius:4px; font-weight:700;
  background:rgba(0,180,200,.15); color:#00ccee; border:1px solid rgba(0,180,200,.3); flex-shrink:0; }}
.tui-ifc-badge.edited {{ background:rgba(137,180,250,.12); color:#89b4fa; border-color:rgba(137,180,250,.3); }}
.tui-ifc-size {{ color:#3a6070; font-size:.72rem; flex-shrink:0; }}
.tui-ifc-dl {{
  display:inline-flex; align-items:center; gap:4px;
  padding:3px 10px; background:#00e5ff; color:#060a12;
  border-radius:5px; font-size:.75rem; font-weight:800;
  text-decoration:none; transition:opacity .15s; white-space:nowrap; flex-shrink:0;
  border:none; cursor:pointer; font-family:inherit;
}}
.tui-ifc-dl:hover {{ opacity:.85; }}
.tui-ifc-dl.edited {{ background:#89b4fa; }}
</style>
<div class="tui-chat-wrap" id="tui-wrap">
  <!-- Agent selector row -->
  <div class="tui-agent-row">
    <label>Agente:</label>
    <select class="tui-agent-sel" id="agent-sel" onchange="changeAgent(this.value)">{agent_opts}</select>
    <button class="tui-clear-btn" onclick="clearChat()">🗑 Nueva</button>
    <button class="tui-sessions-btn" onclick="openSessionsPanel()">📚 Sesiones</button>
  </div>
  <!-- Messages (with sessions panel overlay) -->
  <div style="position:relative;flex:1;overflow:hidden;display:flex;flex-direction:column">
    <div class="tui-messages" id="tui-messages">
      <div style="color:#334455;font-size:.8rem;padding:10px 0;text-align:center">
        Conectando con el agente…
      </div>
    </div>
    <!-- Sessions overlay panel -->
    <div class="tui-sessions-panel" id="tui-sessions-panel">
      <div class="tui-sessions-panel-header">
        <span class="tui-sessions-panel-title">📚 Historial de sesiones</span>
        <button class="tui-sessions-panel-close" onclick="closeSessionsPanel()">✕</button>
      </div>
      <div class="tui-sessions-list" id="tui-sessions-list">
        <div style="color:#334455;font-size:.8rem;padding:20px;text-align:center">Cargando sesiones…</div>
      </div>
    </div>
  </div>
  <!-- Pensando — visible solo durante el turno activo, encima del prompt -->
  <div id="tui-thinking-bar" style="display:none" class="tui-thinking-area">
    <span class="tui-thinking-dot">●</span>
    <span class="tui-thinking-word" id="tui-think-word">Cavilando</span>
    <span class="tui-wave-bars">
      <span class="tui-wave-bar"></span>
      <span class="tui-wave-bar"></span>
      <span class="tui-wave-bar"></span>
      <span class="tui-wave-bar"></span>
      <span class="tui-wave-bar"></span>
      <span class="tui-wave-bar"></span>
      <span class="tui-wave-bar"></span>
    </span>
  </div>
  <!-- Input -->
  <div class="tui-input-area">
    <div id="tui-pending-files" class="tui-pending-files" style="display:none"></div>
    <div class="tui-input-row">
      <button class="tui-attach-btn" id="tui-attach" onclick="triggerFileInput()" title="Adjuntar imagen o fichero">📎</button>
      <input type="file" id="tui-file-input" style="display:none"
        accept="image/*,.txt,.py,.js,.ts,.jsx,.tsx,.md,.json,.yaml,.yml,.csv,.toml,.sh,.html,.css"
        multiple onchange="handleFileSelect(this)">
      <textarea class="tui-input" id="tui-input" rows="1"
        placeholder="Mensaje o /comando… Enter=enviar · Shift+Enter=nueva línea"
        oninput="autoResize(this);slashHint(this)"></textarea>
      <button class="tui-send-btn" id="tui-send" onclick="sendMsg()">▶ Enviar</button>
      <button class="tui-kill-btn" id="tui-kill" onclick="killAgent()" style="display:none" title="Interrumpir al agente">⏹</button>
    </div>
    <div id="tui-slash-hint" style="display:none;font-size:.74rem;color:#556677;padding:3px 4px 0">
      ⌘ Slash commands: /new &nbsp;/switch &lt;id&gt; &nbsp;/doctor &nbsp;/steer &nbsp;/compact &nbsp;/hooks &nbsp;/agents
    </div>
  </div>
  <!-- Subagent team bar (solo cabecera; el detalle va al bloque del subagente en la conversación) -->
  <div id="tui-team-bar" style="display:none"></div>
  <!-- Status bar (paridad con el toolbar del TUI: justo bajo el prompt y la team-bar, sobre MCP/LSP) -->
  <div class="tui-statusbar" id="tui-statusbar" style="border-top:1px solid #1a2035;border-bottom:none">
    <span class="tui-sb-agent" id="sb-agent">🤖 OOCode</span>
    <span class="tui-sb-sep">│</span>
    <span class="tui-sb-model" id="sb-model">—</span>
    <span class="tui-sb-sep">│</span>
    <span class="tui-sb-ctx" id="sb-ctx">▱▱▱▱▱▱▱▱▱▱  0%</span>
    <span id="sb-compact-hint" style="display:none;font-size:.68rem;margin-left:4px;font-weight:600"></span>
    <span class="tui-sb-sep" id="sb-tasks-sep" style="display:none">│</span>
    <span class="tui-sb-tasks" id="sb-tasks" style="display:none"></span>
    <div class="tui-sb-right">
      <span class="tui-sb-badge" id="sb-mcp"    title="Servidores MCP"    style="display:none">◎ MCP</span>
      <span class="tui-sb-badge" id="sb-lsp"    title="LSP activo"        style="display:none">⟨⟩ LSP</span>
      <span class="tui-sb-badge" id="sb-mem"    title="Memoria vectorial" style="display:none">⬡ MEM</span>
      <span class="tui-sb-badge" id="sb-rag"    title="RAG indexado"      style="display:none">⬢ RAG</span>
      <span class="tui-sb-badge" id="sb-embed"  title="Embeddings activos" style="display:none">◈ EMBED</span>
      <span class="tui-sb-badge" id="sb-vision" title="Modelo con visión" style="display:none">👁 VIS</span>
      <span class="tui-sb-badge elev-clickable" id="sb-elev" title="Click para cambiar permisos" onclick="cycleElevated()" style="display:none"></span>
      <span id="sb-tokens" style="color:#334455;font-size:.72rem"></span>
    </div>
  </div>
  <!-- MCP/LSP detail rows (una línea cada uno, bajo la status bar — como en el toolbar del TUI) -->
  <div class="tui-bottom-bar tui-sb2" id="tui-sb2-mcp" style="display:none">
    <span id="sb-mcp-names" style="color:#00aacc"></span>
  </div>
  <div class="tui-bottom-bar tui-sb2" id="tui-sb2-lsp" style="display:none">
    <span id="sb-lsp-langs" style="color:#89b4fa"></span>
  </div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let _evtSource      = null;
let _busy           = false;
let _scrollPinned   = true;   // true = auto-scroll al fondo; false = usuario ha subido a leer
let _agentId        = document.getElementById('agent-sel').value || 'main';
let _agentBuf       = '';    // buffer de texto del turno actual
let _agentDiv       = null;  // div del mensaje actual del agente
let _turnHadContent = false; // true si se mostró algún texto de agente en el turno actual
let _turnId         = 0;     // contador de turno — asegura bloques de tools distintos por turno
let _agentName      = 'OOCode';   // nombre real del agente (desde config)
let _agentEmoji     = '🤖';       // emoji del agente (desde config)
let _clockFrames    = ['🕐','🕑','🕒','🕓','🕔','🕕','🕖','🕗','🕘','🕙','🕚','🕛'];
let _clockIdx       = 0;
let _clockInterval  = null;
let _statusInterval = null;
let _streamEndTimer = null;   // timer: si el streaming para pero _busy, mostrar Pensando
let _agentMdTimer   = null;   // debounce: renderizar markdown tras pausa de 350ms en streaming
let _busyTimeout    = null;   // safety: re-enable if done event never arrives
let _killed         = false;  // kill en progreso: ignorar eventos del turno anterior
let _activePlanTask = '';     // texto de la tarea activa del plan (para el indicador Pensando)
// Palabras inventadas para el indicador de pensamiento (como en el TUI)
const _TW  = ["Cavilando","Cogitando","Ruminando","Elucubrando","Maquinando","Ponderando",
               "Discurriendo","Deliberando","Neuroneando","Sinaptizando","Tokenizando",
               "Vectorizando","Inferenciando","Transformeando","Embedizando","Prompteando",
               "Tensorando","Gradientando","Sampliando","Decodificando","Atteneando",
               "Softmaxeando","Backproneando","Halucineando"];
const _TWM = ["Planificando","Organizando","Orquestando","Coordinando",
              "Secuenciando","Estructurando","Implementando","Ejecutando"];
let _thinkWordIdx   = 0;
let _thinkWordTimer = null;
let _inputHistory  = [];     // mensajes enviados en esta sesión (historial de input)
let _historyIdx    = -1;     // -1 = posición actual (no en modo historia)
let _historyDraft  = '';     // borrador guardado al entrar en modo historia
let _pendingSessionReload = false;  // true tras enviar /session <id>: recarga la conversación al done

// ── Auto-resize textarea ───────────────────────────────────────────────────
function autoResize(el) {{
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}}

// ── Connect SSE ────────────────────────────────────────────────────────────
function connectSSE() {{
  if (_evtSource) {{ _evtSource.close(); }}
  _evtSource = new EventSource('/api/chat/stream?agent_id=' + _agentId);

  _evtSource.onopen = () => {{
    console.log('[SSE] connected');
    loadStatus(15);   // retry up to 15×2s = 30s while loop initializes
  }};

  _evtSource.onmessage = (e) => {{
    const ev = JSON.parse(e.data);
    handleEvent(ev);
  }};

  _evtSource.onerror = () => {{
    setTimeout(connectSSE, 3000);
  }};
}}

// ── Handle SSE events ──────────────────────────────────────────────────────

function handleEvent(ev) {{
  // Ignorar eventos del turno anterior tras un kill (excepto 'done' que confirma el fin)
  if (_killed && ev.type !== 'done' && ev.type !== 'status' && ev.type !== 'heartbeat') return;

  // Auto-descubrir subagentes para la team-bar: cualquier evento tagged 'subagent'
  // (tool_start/tool_done/text/status) alimenta su detalle, también los de team/fanout
  // que no emiten subagent_start. El ctx% se captura de sus eventos 'status'.
  if (ev.subagent && ev.subagent_name) {{
    const _se = _ensureSubagentEntry(ev.subagent_name, ev.subagent_emoji || '🤖', '', null);
    if (_se && ev.type === 'status' && 'context_pct' in ev) _se.ctx = ev.context_pct || 0;
    renderTeamBar();
  }}

  switch (ev.type) {{
    case 'connected':
      loadHistory();
      loadInputHistory();   // recall de flecha arriba compartido con el TUI
      loadStatus(15);  // retry: loop may still be initializing
      break;

    case 'heartbeat':
      // Resetear el safety timeout en cada latido — mientras la conexión SSE viva,
      // el agente sigue activo aunque tarde varios minutos (subagentes, tareas largas)
      if (_busy) _resetBusyTimeout();
      break;

    case 'thinking':
      _finishAgentMsg();
      // Preservar label actual si ya hay palabra visible
      (function() {{
        const wordEl = document.getElementById('tui-think-word');
        const bar = document.getElementById('tui-thinking-bar');
        const existingLabel = (wordEl && bar && bar.style.display !== 'none')
          ? wordEl.textContent : '';
        removeThinking();
        appendThinking(existingLabel || undefined);
      }})();
      break;

    case 'preflight':
      // Frase contextual de ESTADO → barra "Pensando" encima del prompt (status).
      // appendThinking crea el spinner (#tui-think-word) si aún no existe y fija el label.
      appendThinking(ev.label || undefined);
      break;

    case 'tool_start':
      if (ev.subagent) {{
        appendSubagentToolStart(ev.tool, ev.subagent_emoji || '🤖', ev.subagent_name || '');
      }} else {{
        // El detalle del tool va al BLOQUE de tools en la conversación. La barra
        // "Pensando" del prompt es status: NO se sobreescribe con el nombre del tool
        // (sigue ciclando palabras/preflight) — antes los títulos de tools "salían"
        // en el prompt en vez de en la conversación.
        appendToolStart(ev.tool, ev.context || '');
      }}
      break;

    case 'tool_done':
      if (ev.subagent) {{
        appendSubagentToolDone(ev.tool, ev.ok !== false,
                               ev.subagent_emoji || '🤖', ev.subagent_name || '',
                               ev.preview || '', ev.n_lines || 0);
        if (ev.file_path && ev.ok !== false) {{
          // Insertar en el bloque del subagente correspondiente
          const _subInner = _getOrCreateSubToolBlock(ev.subagent_emoji || '🤖', ev.subagent_name || '');
          appendFileCard(ev.file_path, ev.file_name || ev.file_path,
                         ev.file_size || 0, ev.file_action || 'created', _subInner);
        }}
      }} else {{
        appendToolDone(ev.tool, ev.context || '', ev.ok !== false,
                       ev.n_lines || 0, ev.preview || '');
        if (ev.file_path && ev.ok !== false) {{
          // Insertar en el tool block activo (posición actual en la conversación)
          appendFileCard(ev.file_path, ev.file_name || ev.file_path,
                         ev.file_size || 0, ev.file_action || 'created', null);
        }}
      }}
      break;

    case 'plan':
      if (ev.subagent) {{
        appendSubagentPlan(ev.tasks || [], ev.n || 0, ev.summary || '',
                           ev.subagent_emoji || '🤖', ev.subagent_name || '');
      }} else {{
        removeThinking();
        _finishToolBlock();
        appendPlan(ev.tasks || [], ev.n || 0, ev.summary || '', ev.extra || 0);
      }}
      break;

    case 'plan_progress':
      updatePlanProgress(ev.done || 0, ev.total || 0, ev.active || 0,
                         ev.active_text || '', ev.tasks || []);
      break;

    case 'text':
      removeThinking();
      if (ev.subagent) {{
        appendSubagentText(ev.text, ev.subagent_emoji || '🤖', ev.subagent_name || '');
      }} else {{
        appendAgentText(ev.text);
      }}
      break;

    case 'stream_chunk':
      removeThinking();
      if (ev.subagent) {{
        appendSubagentChunk(ev.text, ev.subagent_emoji || '🤖', ev.subagent_name || '');
      }} else {{
        appendStreamChunk(ev.text);
      }}
      break;

    case 'embed_flash':
      flashEmbed(ev.op || 'read');
      break;

    case 'subagent_start':
      _ensureSubagentEntry(ev.agent_name || ev.agent_id || '', ev.agent_emoji || '🤖',
                           ev.task || '', ev.agent_id || '');
      // El detalle largo (tarea) va al bloque del subagente en la CONVERSACIÓN, no a la
      // team-bar del status (que solo muestra la cabecera y no cabría en una línea).
      _seedSubagentTask(ev.agent_emoji || '🤖', ev.agent_name || '', ev.task || '');
      renderTeamBar();
      break;

    case 'subagent_done':
      {{
        const _aid = ev.agent_id || '';
        const e = _activeSubagents.find(a => a.id === _aid || a.name === _aid);
        if (e) e.status = 'done';
      }}
      renderTeamBar();
      break;

    case 'done': {{
      _killed = false;  // reset: próximo turno ya puede recibir eventos
      _activePlanTask = '';  // limpiar tarea activa al terminar el turno
      _planBlockTurn  = -1;
      _activeSubagents = [];  // limpiar equipo al terminar el turno
      if (_teamTimer) {{ clearInterval(_teamTimer); _teamTimer = null; }}
      renderTeamBar();
      // Guardar si hubo contenido ANTES de que _finishAgentMsg limpie _agentBuf
      const _hadContent = _turnHadContent;
      _turnHadContent = false;
      _finishAgentMsg();
      _finishToolBlock();
      removeThinking();
      updateStatus(ev);
      setBusy(false);
      // Si el turno fue un /session que restauró una sesión en el servidor,
      // re-renderizar la conversación restaurada (reemplaza la vista actual).
      if (_pendingSessionReload) {{
        _pendingSessionReload = false;
        loadHistory();
        break;
      }}
      // Fallback: solo mostrar ev.response si no hubo streaming/texto este turno
      if (ev.response && !_hadContent) {{
        appendAgentBlock(ev.response);
      }}
      break;
    }}

    case 'inference_done':
      // El turno terminó: mostrar mensaje de finalización de inferencia (como en TUI)
      if (_agentDiv) {{
        const body = _agentDiv.querySelector('.tui-msg-body');
        if (body) {{
          const currentText = body.innerHTML;
          if (!currentText.endsWith('\\n⚡ Inferencia completada.')) {{
            body.innerHTML = currentText + '\\n⚡ Inferencia completada.';
          }}
        }}
      }}
      // También limpiar la barra de pensando si aún está visible
      removeThinking();
      break;

    case 'status':
      // Los status tagged 'subagent' alimentan su ctx% en la team-bar (hook de arriba),
      // NO la barra principal — si no, el ctx del subagente pisaría el del agente.
      if (!ev.subagent) updateStatus(ev);
      break;

    case 'error':
      _killed = false;
      _finishAgentMsg();
      _finishToolBlock();
      removeThinking();
      setBusy(false);
      const errDiv = document.createElement('div');
      errDiv.className = 'tui-error';
      errDiv.textContent = '✗ Error: ' + (ev.error || 'desconocido');
      document.getElementById('tui-messages').appendChild(errDiv);
      scrollBottom();
      break;
  }}
}}

// ── Slash command hint ─────────────────────────────────────────────────────
function slashHint(el) {{
  const hint = document.getElementById('tui-slash-hint');
  if (hint) hint.style.display = el.value.trimStart().startsWith('/') ? '' : 'none';
}}

// ── Tool activity block (colapsable) ──────────────────────────────────────
let _toolBlockWrapper = null;   // div exterior (con header)
let _toolBlockInner   = null;   // div interior (donde van las filas)
let _toolBlockTurn    = -1;
let _toolDoneCount    = 0;
let _toolTotalCount   = 0;
let _toolNames        = [];     // nombres de tools completadas (para resumen ⎿)

function _getOrCreateToolBlock() {{
  // Reutilizar si existe y es del turno actual
  if (_toolBlockWrapper && _toolBlockTurn === _turnId && _toolBlockWrapper.isConnected) {{
    return _toolBlockInner;
  }}
  // Nuevo turno — crear bloque fresco
  _finishAgentMsg();
  const msgs = document.getElementById('tui-messages');

  const wrapper = document.createElement('div');
  wrapper.className = 'tui-tool-block-wrapper';
  wrapper.dataset.turn = _turnId;

  const header = document.createElement('div');
  header.className = 'tui-tool-block-header';
  // El header muestra ⎿/◐ + resumen compacto (igual que TUI)
  header.innerHTML =
    '<span class="tui-tool-block-icon running" id="tb-icon-' + _turnId + '">◐</span>'
    + '<span class="tui-tool-block-summary" id="tb-sum-' + _turnId + '">Ejecutando…</span>'
    + '<span class="tui-tool-block-toggle" id="tb-tog-' + _turnId + '">▼</span>';
  header.onclick = () => _toggleToolBlock(wrapper);
  // El bloque comienza EXPANDIDO para ver las filas mientras corren
  wrapper.classList.add('expanded');

  const inner = document.createElement('div');
  inner.className = 'tui-tool-block-inner';

  wrapper.appendChild(header);
  wrapper.appendChild(inner);
  msgs.appendChild(wrapper);
  _pinThinkingToBottom();

  _toolBlockWrapper = wrapper;
  _toolBlockInner   = inner;
  _toolBlockTurn    = _turnId;
  _toolDoneCount    = 0;
  _toolTotalCount   = 0;
  _toolNames        = [];
  return inner;
}}

function _toggleToolBlock(wrapper) {{
  const expanded = wrapper.classList.toggle('expanded');
  const tog = wrapper.querySelector('.tui-tool-block-toggle');
  if (tog) tog.textContent = expanded ? '▲' : '▼';
}}

function _updateToolBlockHeader(tool, running) {{
  const tid = _toolBlockTurn;
  const sumEl = document.getElementById('tb-sum-' + tid);
  const iconEl = document.getElementById('tb-icon-' + tid);
  if (!sumEl) return;
  if (running) {{
    const n = _toolTotalCount;
    // Mientras corre: ◐ nombre_tool (+ N más)
    sumEl.textContent = tool + (n > 1 ? '  +' + (n-1) + ' más' : '');
    if (iconEl) {{ iconEl.className = 'tui-tool-block-icon running'; iconEl.textContent = '◐'; }}
  }} else {{
    // Deduplicar: "Read · Read · Read" → "Read (+3)" — idéntico al TUI _make_compact_summary
    const counts = {{}};
    for (const t of _toolNames) counts[t] = (counts[t] || 0) + 1;
    const unique = Object.keys(counts);
    const shown  = unique.slice(0, 6);
    const extra  = unique.length - shown.length;
    const names  = shown.map(t => counts[t] > 1 ? t + ' (+' + counts[t] + ')' : t).join('  ·  ')
                   + (extra > 0 ? '  ·  +' + extra : '');
    const count  = _toolDoneCount;
    sumEl.textContent = names || (count + ' herramienta' + (count !== 1 ? 's' : ''));
    if (iconEl) {{ iconEl.className = 'tui-tool-block-icon'; iconEl.textContent = '⎿'; }}
  }}
}}

function _finishToolBlock() {{
  // Al terminar: mostrar ⎿ summary y colapsar las filas de detalle (como en TUI)
  if (_toolBlockWrapper && _toolBlockTurn >= 0) {{
    _updateToolBlockHeader('', false);
    const iconEl = document.getElementById('tb-icon-' + _toolBlockTurn);
    if (iconEl) {{ iconEl.className = 'tui-tool-block-icon'; iconEl.textContent = '⎿'; }}
    _toolBlockWrapper.classList.remove('expanded');  // colapsa inner y file cards
    _toolBlockWrapper.classList.add('done');
    const tog = document.getElementById('tb-tog-' + _toolBlockTurn);
    if (tog) tog.textContent = '▼';
  }}
  _toolBlockWrapper = null;
  _toolBlockInner   = null;
  _toolBlockTurn    = -1;
  _toolDoneCount    = 0;
  _toolTotalCount   = 0;
  _toolNames        = [];
}}

function appendToolStart(tool, ctx) {{
  const inner = _getOrCreateToolBlock();
  _toolTotalCount++;
  _updateToolBlockHeader(tool, true);

  const row = document.createElement('div');
  row.className = 'tui-tool';
  // Estilo TUI: │  ◐ tool: ctx …
  const ctxStr = ctx ? '<span class="tui-tool-ctx">' + _esc(ctx.substring(0,70)) + '</span>' : '';
  row.innerHTML = '<span class="tui-tool-pipe">│  </span>'
    + '<span class="tui-tool-icon running">◐</span>'
    + '<span class="tui-tool-name"> ' + _esc(tool) + ':</span>'
    + ctxStr
    + '<span class="tui-running-dots"> …</span>';
  row.dataset.tool = tool;
  row.dataset.pending = '1';
  inner.appendChild(row);
  scrollBottom();
}}

function appendToolDone(tool, ctx, ok, nLines, preview) {{
  const inner = (_toolBlockInner && _toolBlockInner.isConnected) ? _toolBlockInner : _getOrCreateToolBlock();
  _toolDoneCount++;
  _toolNames.push(tool);
  // Solo actualizar el header si no hay tools en ejecución (para no mostrar el resumen de tools completadas)
  if (_toolTotalCount <= 0) {{
    _updateToolBlockHeader(tool, false);
  }}

  // Buscar la fila pending de esta tool
  let row = null;
  const rows = inner.querySelectorAll('[data-pending="1"]');
  for (const r of rows) {{
    if (r.dataset.tool === tool) {{ row = r; break; }}
  }}
  if (!row) {{
    row = document.createElement('div');
    row.className = 'tui-tool';
    inner.appendChild(row);
  }}
  row.dataset.pending = '0';
  // Estilo TUI: │  ⎿ tool: ctx   o   │  ✗ tool
  const sym    = ok ? '⎿' : '✗';
  const symCls = ok ? 'ok' : 'err';
  const ctxStr = ctx ? '<span class="tui-tool-ctx"> ' + _esc(ctx.substring(0,55)) + '</span>' : '';
  const nlStr  = nLines > 1 ? ' <span class="tui-tool-nlines">' + nLines + 'l</span>' : '';
  row.innerHTML = '<span class="tui-tool-pipe">│  </span>'
    + '<span class="tui-tool-icon ' + symCls + '">' + sym + '</span>'
    + '<span class="tui-tool-name"> ' + _esc(tool) + '</span>'
    + ctxStr + nlStr;
  // Preview bajo la fila si hay resultado útil
  if (preview && preview.length > 1 && ok) {{
    const prev = document.createElement('span');
    prev.className = 'tui-tool-result';
    prev.textContent = preview;
    row.appendChild(prev);
  }}
  scrollBottom();
  // Reanudar cycling de palabras (como TUI entre tools)
  if (_busy) _resumeThinkingWords();
}}

function _fileIcon(name) {{
  const ext = (name.split('.').pop() || '').toLowerCase();
  const icons = {{
    'py':'🐍','js':'📜','ts':'📜','jsx':'📜','tsx':'📜',
    'html':'🌐','css':'🎨','json':'📋','yaml':'📋','yml':'📋',
    'md':'📝','txt':'📄','csv':'📊','sql':'🗄️','sh':'⚙️',
    'docx':'📘','doc':'📘','odt':'📘',
    'xlsx':'📗','xls':'📗','ods':'📗',
    'pptx':'📙','ppt':'📙','odp':'📙',
    'pdf':'📕','png':'🖼️','jpg':'🖼️','jpeg':'🖼️','gif':'🖼️',
    'svg':'🎨','zip':'🗜️','tar':'🗜️','gz':'🗜️',
    'mp3':'🎵','mp4':'🎬','wav':'🎵',
  }};
  return icons[ext] || '📄';
}}

function _fmtSize(bytes) {{
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1048576).toFixed(1) + ' MB';
}}

// Descarga robusta: verifica primero que el fichero existe, luego lanza <a> temporal.
// Si el servidor no está disponible o el fichero no existe → toast de error.
async function _safeDownload(filePath, fileName) {{
  const dlUrl = '/api/files/download?path=' + encodeURIComponent(filePath);
  try {{
    const info = await fetch('/api/files/info?path=' + encodeURIComponent(filePath));
    if (!info.ok) {{
      const d = await info.json().catch(() => ({{error: 'fichero no encontrado'}}));
      showToast('✗ No se puede descargar: ' + (d.error || 'fichero no encontrado'), false);
      return;
    }}
  }} catch(e) {{
    showToast('✗ Servidor no disponible (¿WebUI iniciado?): ' + e.message, false);
    return;
  }}
  const a = document.createElement('a');
  a.href = dlUrl; a.download = fileName;
  document.body.appendChild(a); a.click();
  setTimeout(() => document.body.removeChild(a), 200);
}}

function appendFileCard(filePath, fileName, fileSize, fileAction, targetInner) {{
  const isEdit  = fileAction === 'edited';
  const sizeStr = fileSize > 0 ? _fmtSize(fileSize) : '';
  const btnCls  = 'tui-ifc-dl' + (isEdit ? ' edited' : '');
  const safeFile = _esc(fileName);
  const safePath = _esc(filePath);

  const _buildCard = () => {{
    const card = document.createElement('div');
    card.className = 'tui-file-card' + (isEdit ? ' edited' : '');
    const btn = document.createElement('button');
    btn.className = btnCls;
    btn.textContent = '⬇ Descargar';
    btn.title = safePath;
    btn.onclick = () => _safeDownload(filePath, fileName);
    card.innerHTML =
      '<span class="tui-ifc-icon">' + _fileIcon(fileName) + '</span>'
      + '<span class="tui-ifc-name" title="' + safePath + '">' + safeFile + '</span>'
      + (sizeStr ? '<span class="tui-ifc-size">' + sizeStr + '</span>' : '')
      + '<span class="tui-ifc-badge' + (isEdit ? ' edited' : '') + '">' + (isEdit ? 'Modificado' : 'Generado') + '</span>';
    card.appendChild(btn);
    return card;
  }};

  // Subagente: insertar en el wrapper del bloque de tools del subagente
  if (targetInner != null && targetInner.isConnected) {{
    // Buscar el wrapper padre del inner para insertar fuera del inner colapsable
    const subWrapper = targetInner.parentElement;
    if (subWrapper) {{
      subWrapper.appendChild(_buildCard());
    }} else {{
      targetInner.appendChild(_buildCard());
    }}
    scrollBottom();
    return;
  }}

  // Agente principal: insertar en el wrapper del tool block
  const wrapper = _toolBlockWrapper && _toolBlockWrapper.isConnected ? _toolBlockWrapper : null;
  if (wrapper) {{
    wrapper.appendChild(_buildCard());
    scrollBottom();
    return;
  }}

  // Fallback: sin tool block activo — insertar al final del chat como tarjeta suelta
  const msgs = document.getElementById('tui-messages');
  msgs.appendChild(_buildCard());
  scrollBottom();
}}

let _planBlockTurn = -1;  // turno del bloque de plan actual

function appendPlan(tasks, n, summary, extra) {{
  _finishToolBlock();
  const msgs = document.getElementById('tui-messages');
  const d = document.createElement('div');
  d.className = 'tui-plan-block';
  d.dataset.planTurn = _turnId;
  _planBlockTurn = _turnId;
  // Estilo TUI plano: ◈ Plan de ejecución  [1/N · N-1 pendientes]
  let html = '<div data-plan-header class="tui-plan-header">'
    + '<span class="tui-plan-icon">◈</span>'
    + '  Plan de ejecución  '
    + '<span data-plan-stats class="tui-plan-stats">[1/' + n + ' · ' + (n-1) + ' pendientes]</span>'
    + '</div>';
  if (summary) {{
    html += '<div class="tui-plan-summary">' + _esc(summary) + '</div>';
  }}
  html += '<div data-plan-tasks class="tui-plan-tasks">';
  tasks.forEach((t, i) => {{
    const isFirst = i === 0;
    const cls  = isFirst ? 'active' : 'pending';
    const sym  = isFirst ? '◼' : '◻';
    html += '<div data-task-idx="' + i + '" class="tui-plan-task ' + cls + '">'
      + '<span class="tui-task-sym">' + sym + '</span>'
      + '  ' + _esc(t) + '</div>';
  }});
  if (extra > 0) {{
    html += '<div class="tui-plan-extra">  … +' + extra + ' más</div>';
  }}
  html += '</div>';
  d.innerHTML = html;
  msgs.appendChild(d);
  scrollBottom();
}}

function updatePlanProgress(done, total, activeIdx, activeText, tasks) {{
  // Guardar tarea activa para el indicador Pensando en la barra de estado
  _activePlanTask = (activeText && activeIdx < total) ? activeText : '';
  // Si hay thinking activo, el siguiente ciclo usará _TWM automáticamente
  // Encontrar el bloque de plan del turno actual
  const block = document.querySelector('.tui-plan-block[data-plan-turn="' + _planBlockTurn + '"]');
  if (!block) return;
  // Actualizar estadísticas del header
  const statsEl = block.querySelector('[data-plan-stats]');
  if (statsEl) {{
    const pending = Math.max(0, total - done - (activeIdx < total ? 1 : 0));
    const cur = Math.min(done + 1, total);
    statsEl.textContent = '[' + cur + '/' + total + ']'
      + '  · ' + done + ' completadas · ' + pending + ' pendientes';
  }}
  // Actualizar estado visual de cada tarea — mismos símbolos que TUI: ✔/◼/◻
  const taskEls = block.querySelectorAll('[data-task-idx]');
  taskEls.forEach(el => {{
    const idx = parseInt(el.dataset.taskIdx);
    if (tasks && tasks[idx]) {{
      const status = tasks[idx].status;
      const sym = el.querySelector('.tui-task-sym');
      if (status === 'done') {{
        el.className = 'tui-plan-task done';
        if (sym) sym.textContent = '✔';
      }} else if (status === 'active') {{
        el.className = 'tui-plan-task active';
        if (sym) sym.textContent = '◼';
      }} else {{
        el.className = 'tui-plan-task pending';
        if (sym) sym.textContent = '◻';
      }}
    }}
  }});
  // Si todas completadas → ✔ Plan completado (verde, como TUI)
  if (done >= total && total > 0) {{
    const hdrEl = block.querySelector('[data-plan-header]');
    if (hdrEl) {{
      hdrEl.className = 'tui-plan-header done';
      hdrEl.innerHTML = '<span class="tui-plan-icon done">✔</span>'
        + '  Plan completado  '
        + '<span data-plan-stats class="tui-plan-stats">[' + total + '/' + total + ' · todas completadas]</span>';
    }}
  }}
}}

function _esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

// ── Markdown → HTML renderer ───────────────────────────────────────────────
function _mdToHtml(md) {{
  if (!md) return '';
  // 1. Extraer bloques de código para protegerlos
  const codeBlocks = [];
  let s = md.replace(/```(\\w*)\\n?([\\s\\S]*?)```/g, (_, lang, code) => {{
    const idx = codeBlocks.length;
    codeBlocks.push({{ lang: lang || '', code }});
    return '\\x00CODE' + idx + '\\x00';
  }});
  // 2. Proteger rutas de fichero ANTES de escapar HTML (evita que _ en nombres como "report_2026_final.docx"
  //       sean interpretados como marcadores de cursiva)
  const _FILE_EXT = 'docx|xlsx|pptx|pdf|csv|txt|py|js|ts|jsx|tsx|json|yaml|yml|sh|md|zip|gz|png|jpg|jpeg|svg|odt|ods|odp';
  const _FILE_RE  = new RegExp("((?:/home|/tmp|/root)[^\\\\s<>\\"'`]{{1,200}}\\.(" + _FILE_EXT + "))(?=[\\\\s<>\\"'`.,;:)\\\\]!?]|$)", 'gi');
  const filePaths = [];
  s = s.replace(_FILE_RE, (_, path) => {{
    const idx = filePaths.length;
    filePaths.push(path);
    return '\\x00FILE' + idx + '\\x00';
  }});
  // 3. Escapar HTML en el texto normal
  s = s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  // 3. Restaurar bloques de código con highlighting
  s = s.replace(/\\x00CODE(\\d+)\\x00/g, (_, i) => {{
    const b = codeBlocks[parseInt(i)];
    const lang = b.lang ? ` class="language-${{_esc(b.lang)}}"` : '';
    const code = b.code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    return `<pre><code${{lang}}>${{code}}</code></pre>`;
  }});
  // 4. Inline code
  s = s.replace(/`([^`\\n]+)`/g, '<code>$1</code>');
  // 5. Bold / italic
  s = s.replace(/\\*\\*\\*(.+?)\\*\\*\\*/g, '<strong><em>$1</em></strong>');
  s = s.replace(/\\*\\*(.+?)\\*\\*/g,     '<strong>$1</strong>');
  s = s.replace(/__(.+?)__/g,          '<strong>$1</strong>');
  s = s.replace(/\\*(?!\\s)(.+?)(?<!\\s)\\*/g, '<em>$1</em>');
  s = s.replace(/_(?!\\s)(.+?)(?<!\\s)_/g,   '<em>$1</em>');
  // 6. Links
  s = s.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // 7. Headers (must come after inline)
  s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  s = s.replace(/^## (.+)$/gm,  '<h2>$1</h2>');
  s = s.replace(/^# (.+)$/gm,   '<h1>$1</h1>');
  // 8. Blockquotes
  s = s.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
  // 9. Horizontal rules
  s = s.replace(/^(?:---|\\.\\*{3}|___)$/gm, '<hr>');
  // 10. Lists — group consecutive items
  s = s.replace(/((?:^[-*+] .+\\n?)+)/gm, m => {{
    const items = m.trim().split('\\n').map(l => '<li>' + l.replace(/^[-*+] /, '') + '</li>').join('');
    return '<ul>' + items + '</ul>\\n';
  }});
  s = s.replace(/((?:^\\d+\\. .+\\n?)+)/gm, m => {{
    const items = m.trim().split('\\n').map(l => '<li>' + l.replace(/^\\d+\\. /, '') + '</li>').join('');
    return '<ol>' + items + '</ol>\\n';
  }});
  // 11. Tables (simple)
  s = s.replace(/((?:^\\|.+\\|\\n?)+)/gm, m => {{
    const rows = m.trim().split('\\n').filter(r => !/^\\|[-| :]+\\|$/.test(r.trim()));
    if (rows.length === 0) return m;
    let html = '<table>';
    rows.forEach((r, i) => {{
      const cells = r.split('|').slice(1,-1).map(c => c.trim());
      const tag = i === 0 ? 'th' : 'td';
      html += '<tr>' + cells.map(c => `<${{tag}}>${{c}}</${{tag}}>`).join('') + '</tr>';
    }});
    return html + '</table>\\n';
  }});
  // 12. Paragraphs — blank line separates paragraphs
  const paras = s.split(/\\n{{2,}}/);
  s = paras.map(p => {{
    p = p.trim();
    if (!p) return '';
    if (/^<(h[1-6]|ul|ol|pre|blockquote|hr|table)/.test(p)) return p;
    return '<p>' + p.replace(/\\n/g, '<br>') + '</p>';
  }}).filter(Boolean).join('\\n');
  // 13. Restaurar rutas de fichero como botones de descarga (onclick→_safeDownload)
  s = s.replace(/\\x00FILE(\\d+)\\x00/g, (_, i) => {{
    const path = filePaths[parseInt(i)];
    const name = path.split('/').pop();
    const eName = _esc(name); const ePath = _esc(path);
    // Atributos data-* para poder inyectar onclick después del HTML
    return '<span class="tui-file-link" title="' + ePath + '">' + eName + '</span>'
         + '<button class="tui-dl-btn" data-dl-path="' + ePath + '" data-dl-name="' + eName
         + '" title="Descargar ' + eName + '" style="border:none;cursor:pointer;background:rgba(0,180,220,.15);color:#00aacc">⬇</button>';
  }});
  return s;
}}

// ── Message rendering ──────────────────────────────────────────────────────
// Muestra la línea "Pensando" encima del prompt con barras verticales ondulantes
function appendThinking(overrideLabel) {{
  if (_streamEndTimer) {{ clearTimeout(_streamEndTimer); _streamEndTimer = null; }}
  const bar = document.getElementById('tui-thinking-bar');
  if (bar) bar.style.display = '';
  if (overrideLabel) {{
    _setThinkingLabel(overrideLabel);
    return;
  }}
  // Ciclar palabras inventadas
  if (_thinkWordTimer) clearInterval(_thinkWordTimer);
  const words = _activePlanTask ? _TWM : _TW;
  const wordEl = document.getElementById('tui-think-word');
  if (wordEl) wordEl.textContent = words[_thinkWordIdx % words.length];
  _thinkWordTimer = setInterval(() => {{
    _thinkWordIdx = (_thinkWordIdx + 1) % _TW.length;
    const w = _activePlanTask ? _TWM : _TW;
    const l = document.getElementById('tui-think-word');
    if (l) l.textContent = w[_thinkWordIdx % w.length];
  }}, 1500);
}}

function removeThinking() {{
  if (_streamEndTimer) {{ clearTimeout(_streamEndTimer); _streamEndTimer = null; }}
  if (_thinkWordTimer) {{ clearInterval(_thinkWordTimer); _thinkWordTimer = null; }}
  const bar = document.getElementById('tui-thinking-bar');
  if (bar) bar.style.display = 'none';
}}

// No-op: la barra de pensando siempre está encima del prompt
function _pinThinkingToBottom() {{}}

// Muestra label de tool específico (detiene el cycling de palabras)
function _setThinkingLabel(label) {{
  if (_thinkWordTimer) {{ clearInterval(_thinkWordTimer); _thinkWordTimer = null; }}
  const el = document.getElementById('tui-think-word');
  if (el) el.textContent = label;
}}

// Reanuda el cycling de palabras (tras tool_done, entre tools)
function _resumeThinkingWords() {{
  if (!_busy || _thinkWordTimer) return;
  const words = _activePlanTask ? _TWM : _TW;
  const el = document.getElementById('tui-think-word');
  if (el) el.textContent = words[_thinkWordIdx % words.length];
  _thinkWordTimer = setInterval(() => {{
    _thinkWordIdx = (_thinkWordIdx + 1) % words.length;
    const l = document.getElementById('tui-think-word');
    if (l) l.textContent = words[_thinkWordIdx % words.length];
  }}, 1500);
}}

function _agentHdr(streaming) {{
  // Estilo TUI: solo ● pulsante, sin header separado
  return '<span class="tui-dot' + (streaming ? ' streaming' : '') + '">●</span>';
}}

function appendAgentText(text) {{
  _turnHadContent = true;
  _agentBuf += ((_agentBuf && !_agentBuf.endsWith('\\n')) ? '\\n' : '') + text;
  if (!_agentDiv) {{
    if (_toolBlockWrapper) _finishToolBlock();
    _agentDiv = document.createElement('div');
    _agentDiv.className = 'tui-msg tui-msg-agent';
    // Estilo TUI: ● (dot) + body en flex-row
    _agentDiv.innerHTML = _agentHdr(false) + '<div class="tui-msg-body md-body"></div>';
    document.getElementById('tui-messages').appendChild(_agentDiv);
    _pinThinkingToBottom();
  }}
  const body = _agentDiv.querySelector('.tui-msg-body');
  body.className = 'tui-msg-body md-body';
  body.innerHTML = _mdToHtml(_agentBuf);
  scrollBottom();
  if (_busy) _resumeThinkingWords();
}}

function appendStreamChunk(text) {{
  _turnHadContent = true;
  _agentBuf += text;
  if (!_agentDiv) {{
    if (_toolBlockWrapper) _finishToolBlock();
    _agentDiv = document.createElement('div');
    _agentDiv.className = 'tui-msg tui-msg-agent';
    // Estilo TUI: ● streaming + body en flex-row
    _agentDiv.innerHTML = _agentHdr(true) + '<div class="tui-msg-body tui-streaming"></div>';
    document.getElementById('tui-messages').appendChild(_agentDiv);
    _pinThinkingToBottom();
  }} else {{
    // Mantener ● pulsante durante el streaming
    const dot = _agentDiv.querySelector('.tui-dot');
    if (dot) dot.classList.add('streaming');
  }}
  const body = _agentDiv.querySelector('.tui-msg-body');
  // Una vez en modo markdown (tras primera pausa de 350ms), seguir renderizando HTML.
  // Así no hay salto abrupto al final — la respuesta ya estará renderizada progresivamente.
  if (body.classList.contains('md-body')) {{
    body.innerHTML = _mdToHtml(_agentBuf);
  }} else {{
    body.textContent = _agentBuf;
    // Debounce: tras 350ms sin tokens, activar modo markdown
    if (_agentMdTimer) clearTimeout(_agentMdTimer);
    _agentMdTimer = setTimeout(() => {{
      _agentMdTimer = null;
      if (body && _agentBuf) {{
        body.className = 'tui-msg-body tui-streaming md-body';
        body.innerHTML = _mdToHtml(_agentBuf);
      }}
    }}, 350);
  }}
  scrollBottom();
  // Programar "Pensando" si el streaming se detiene pero el agente sigue activo
  if (_streamEndTimer) clearTimeout(_streamEndTimer);
  if (_busy) {{
    _streamEndTimer = setTimeout(() => {{
      _streamEndTimer = null;
      // Mostrar "Pensando" solo si la barra está oculta (no pisar un label visible).
      const _tb = document.getElementById('tui-thinking-bar');
      if (_busy && (!_tb || _tb.style.display === 'none')) appendThinking();
    }}, 200);
  }}
}}

// ── Subagente: texto, streaming y tools con bloque expandible ─────────────────
// _subBufs[key] = {{ wrap, div(body), textEl, buf, toolBlock, toolTurn, toolDone, toolTotal }}
let _subBufs = {{}};

function _subagentKey(emoji, name) {{ return emoji + '|' + name; }}

function _ensureSubBuf(emoji, name) {{
  const key = _subagentKey(emoji, name);
  if (!_subBufs[key]) {{
    const wrap = document.createElement('div');
    wrap.className = 'tui-subagent-block';
    const startTs = Date.now();
    wrap.innerHTML =
      '<div class="tui-subagent-hdr">'
      + '<span class="tui-subagent-dot"></span>'
      + '<span class="tui-subagent-label">' + _esc(emoji) + '  ' + _esc(name) + '</span>'
      + '<span class="tui-subagent-elapsed" id="sub-elapsed-' + key.replace(/[^a-z0-9]/gi,'') + '"></span>'
      + '<span class="tui-subagent-toggle">▼</span>'
      + '</div>'
      + '<div class="tui-subagent-body"></div>';
    document.getElementById('tui-messages').appendChild(wrap);
    _pinThinkingToBottom();
    // Toggle colapsar/expandir al pulsar el header
    const subHdr = wrap.querySelector('.tui-subagent-hdr');
    subHdr.onclick = () => {{
      const collapsed = wrap.classList.toggle('collapsed');
      const tog = wrap.querySelector('.tui-subagent-toggle');
      if (tog) tog.textContent = collapsed ? '▶' : '▼';
    }};
    // Timer de elapsed
    const elId = 'sub-elapsed-' + key.replace(/[^a-z0-9]/gi,'');
    const timer = setInterval(() => {{
      const el = document.getElementById(elId);
      if (el) el.textContent = Math.round((Date.now()-startTs)/1000) + 's';
    }}, 1000);
    _subBufs[key] = {{
      wrap, div: wrap.querySelector('.tui-subagent-body'),
      textEl: null, buf: '',
      toolBlock: null, toolTurn: -1, toolDone: 0, toolTotal: 0,
      toolNames: [], timer, startTs, mdTimer: null
    }};
  }}
  return _subBufs[key];
}}

// Siembra la tarea del subagente como primera línea de su bloque (conversación).
// Crea el bloque si no existe; idempotente por subagente.
function _seedSubagentTask(emoji, name, task) {{
  if (!name || !task) return;
  const entry = _ensureSubBuf(emoji, name);
  if (entry._taskSeeded) return;
  entry._taskSeeded = true;
  const d = document.createElement('div');
  d.className = 'tui-subagent-task md-body';
  d.innerHTML = '<span class="tui-subagent-task-label">Tarea</span>' + _mdToHtml(task);
  entry.div.insertBefore(d, entry.div.firstChild);
  scrollBottom();
}}

function appendSubagentText(text, emoji, name) {{
  const entry = _ensureSubBuf(emoji, name);
  if (!entry.textEl) {{
    const d = document.createElement('div');
    d.className = 'tui-subagent-text md-body';
    entry.div.appendChild(d);
    entry.textEl = d;
  }}
  entry.buf += (entry.buf && !entry.buf.endsWith('\\n') ? '\\n' : '') + text;
  // Renderizar como markdown inmediatamente (los text events son frases completas)
  entry.textEl.innerHTML = _mdToHtml(entry.buf);
  scrollBottom();
}}

function appendSubagentChunk(text, emoji, name) {{
  const entry = _ensureSubBuf(emoji, name);
  if (!entry.textEl) {{
    const d = document.createElement('div');
    d.className = 'tui-subagent-text';
    entry.div.appendChild(d);
    entry.textEl = d;
  }}
  entry.buf += text;
  // Durante el streaming, textContent para fluidez; renderizar markdown tras pausa breve
  entry.textEl.textContent = entry.buf;
  if (entry.mdTimer) clearTimeout(entry.mdTimer);
  entry.mdTimer = setTimeout(() => {{
    if (entry.textEl && entry.buf) {{
      entry.textEl.className = 'tui-subagent-text md-body';
      entry.textEl.innerHTML = _mdToHtml(entry.buf);
    }}
  }}, 350);
  scrollBottom();
}}

function _getOrCreateSubToolBlock(emoji, name) {{
  const entry = _ensureSubBuf(emoji, name);
  const tid = _turnId;
  if (entry.toolBlock && entry.toolBlock.isConnected && entry.toolTurn === tid) {{
    return entry.toolBlock.querySelector('.tui-tool-block-inner');
  }}
  // Nuevo bloque expandible dentro del cuerpo del subagente
  const safe = _subagentKey(emoji, name).replace(/[^a-z0-9]/gi, '');
  const icnId = 'stb-icn-' + safe + '-' + tid;
  const sumId = 'stb-sum-' + safe + '-' + tid;
  const togId = 'stb-tog-' + safe + '-' + tid;
  const wrapper = document.createElement('div');
  wrapper.className = 'tui-tool-block-wrapper';
  const hdr = document.createElement('div');
  hdr.className = 'tui-tool-block-header';
  hdr.innerHTML =
    '<span class="tui-tool-block-icon running" id="' + icnId + '">◐</span>'
    + '<span class="tui-tool-block-summary" id="' + sumId + '">Ejecutando…</span>'
    + '<span class="tui-tool-block-toggle" id="' + togId + '">▲ Ocultar</span>';
  hdr.onclick = () => {{
    const exp = wrapper.classList.toggle('expanded');
    const tog = document.getElementById(togId);
    if (tog) tog.textContent = exp ? '▲ Ocultar' : '▼ Ver';
  }};
  const inner = document.createElement('div');
  inner.className = 'tui-tool-block-inner';
  wrapper.appendChild(hdr);
  wrapper.appendChild(inner);
  wrapper.classList.add('expanded');  // comienza expandido
  entry.div.appendChild(wrapper);
  entry.toolBlock = wrapper;
  entry.toolTurn  = tid;
  entry.toolDone  = 0;
  entry.toolTotal = 0;
  // Resetear buf y textEl: el texto acumulado hasta aquí ya está en el div anterior;
  // el próximo appendSubagentText debe crear un nuevo div con solo el texto posterior al bloque.
  entry.buf    = '';
  entry.textEl = null;
  scrollBottom();
  return inner;
}}

function _updateSubToolHeader(emoji, name, tool, running) {{
  const entry = _subBufs[_subagentKey(emoji, name)];
  if (!entry || !entry.toolBlock) return;
  const safe  = _subagentKey(emoji, name).replace(/[^a-z0-9]/gi, '');
  const tid   = entry.toolTurn;
  const sumEl = document.getElementById('stb-sum-' + safe + '-' + tid);
  const icnEl = document.getElementById('stb-icn-' + safe + '-' + tid);
  if (!sumEl) return;
  if (running) {{
    const n = entry.toolTotal;
    sumEl.textContent = tool + (n > 1 ? '  +' + (n-1) + ' más' : '');
    if (icnEl) {{ icnEl.className = 'tui-tool-block-icon running'; icnEl.textContent = '◐'; }}
  }} else {{
    const names  = (entry.toolNames || []).slice(0, 5);
    const extra  = (entry.toolNames || []).length - names.length;
    const label  = names.join('  ·  ') + (extra > 0 ? '  +' + extra : '');
    sumEl.textContent = label || (entry.toolDone + ' herramienta' + (entry.toolDone !== 1 ? 's' : ''));
    if (icnEl && entry.toolDone >= entry.toolTotal) {{
      icnEl.className = 'tui-tool-block-icon'; icnEl.textContent = '⎿';
    }}
  }}
}}

function appendSubagentToolStart(tool, emoji, name) {{
  const inner = _getOrCreateSubToolBlock(emoji, name);
  const entry = _subBufs[_subagentKey(emoji, name)];
  if (entry) {{ entry.toolTotal++; _updateSubToolHeader(emoji, name, tool, true); }}
  const row = document.createElement('div');
  row.className = 'tui-tool';
  row.innerHTML = '<span class="tui-tool-icon" style="color:#334455">◐</span>'
    + '<span class="tui-tool-name" style="color:#336677">' + _esc(tool) + '</span>'
    + '<span style="color:#223344;margin-left:6px;font-size:.76rem">…</span>';
  row.dataset.tool    = tool;
  row.dataset.pending = '1';
  inner.appendChild(row);
  scrollBottom();
}}

function appendSubagentToolDone(tool, ok, emoji, name, preview, nLines) {{
  const entry = _subBufs[_subagentKey(emoji, name)];
  if (!entry || !entry.toolBlock) return;
  const inner = entry.toolBlock.querySelector('.tui-tool-block-inner');
  if (!inner) return;
  entry.toolDone++;
  if (!entry.toolNames) entry.toolNames = [];
  entry.toolNames.push(tool);
  _updateSubToolHeader(emoji, name, tool, false);
  let row = null;
  for (const r of inner.querySelectorAll('[data-pending="1"]')) {{
    if (r.dataset.tool === tool) {{ row = r; break; }}
  }}
  if (!row) {{ row = document.createElement('div'); row.className = 'tui-tool'; inner.appendChild(row); }}
  row.dataset.pending = '0';
  const sym    = ok ? '⎿' : '✗';
  const symCol = ok ? '#00cc66' : '#f38ba8';
  const nlStr  = nLines > 1 ? '<span class="tui-tool-nlines">' + nLines + 'l</span>' : '';
  row.innerHTML = '<span style="color:' + symCol + ';width:14px;flex-shrink:0">' + sym + '</span>'
    + '<span class="tui-tool-name" style="color:' + (ok ? '#00cc66' : '#f38ba8') + '">' + _esc(tool) + '</span>'
    + nlStr;
  if (preview && preview.length > 1 && ok) {{
    const prev = document.createElement('span');
    prev.className = 'tui-tool-result';
    prev.textContent = preview;
    row.appendChild(prev);
  }}
  scrollBottom();
}}

function _finishSubToolBlock(emoji, name) {{
  const entry = _subBufs[_subagentKey(emoji, name)];
  if (!entry || !entry.toolBlock) return;
  const safe  = _subagentKey(emoji, name).replace(/[^a-z0-9]/gi, '');
  const tid   = entry.toolTurn;
  const icnEl = document.getElementById('stb-icn-' + safe + '-' + tid);
  if (icnEl) {{ icnEl.className = 'tui-tool-block-icon'; icnEl.textContent = '⎿'; }}
  _updateSubToolHeader(emoji, name, '', false);
  entry.toolBlock.classList.remove('expanded');  // colapsa inner y file cards
  entry.toolBlock.classList.add('done');
  const tog = document.getElementById('stb-tog-' + safe + '-' + tid);
  if (tog) tog.textContent = '▼ Ver';
}}

function appendSubagentPlan(tasks, n, summary, emoji, name) {{
  // Renderizar plan como markdown con lista numerada
  let md = '**◈ Plan** (' + n + ' tareas)' + (summary ? ': *' + summary + '*' : '') + '\\n';
  tasks.forEach((t, i) => {{ md += (i+1) + '. ' + t + '\\n'; }});
  appendSubagentText(md.trim(), emoji, name);
}}

function _finishAgentMsg() {{
  if (_agentMdTimer) {{ clearTimeout(_agentMdTimer); _agentMdTimer = null; }}
  if (_agentDiv) {{
    // Detener pulsado del ● al finalizar el mensaje
    const dot = _agentDiv.querySelector('.tui-dot');
    if (dot) dot.classList.remove('streaming');
    // Render final: si el body aún está en plain text (respuesta muy corta), convertir ahora
    if (_agentBuf) {{
      const body = _agentDiv.querySelector('.tui-msg-body');
      if (body) {{
        body.className = 'tui-msg-body md-body';
        body.innerHTML = _mdToHtml(_agentBuf);
      }}
    }}
  }}
  _agentBuf = '';
  _agentDiv = null;
  // Finalizar todos los subagentes activos
  for (const [key, entry] of Object.entries(_subBufs)) {{
    if (!entry) continue;
    // Colapsar bloque de tools del subagente
    if (entry.toolBlock && !entry.toolBlock.classList.contains('done')) {{
      const parts = key.split('|');
      _finishSubToolBlock(parts[0] || '', parts[1] || '');
    }}
    // Re-renderizar texto del subagente como markdown
    if (entry.textEl && entry.buf) {{
      entry.textEl.className = 'tui-subagent-text md-body';
      entry.textEl.innerHTML = _mdToHtml(entry.buf);
    }}
    // Marcar header como done y colapsar automáticamente
    if (entry.wrap) {{
      entry.wrap.classList.add('tui-subagent-done');
      entry.wrap.classList.add('collapsed');
      const tog = entry.wrap.querySelector('.tui-subagent-toggle');
      if (tog) tog.textContent = '▶';
    }}
    // Parar timer elapsed
    if (entry.timer) clearInterval(entry.timer);
  }}
  _subBufs = {{}};
}}

function appendAgentBlock(text) {{
  const msgs = document.getElementById('tui-messages');
  const d = document.createElement('div');
  d.className = 'tui-msg tui-msg-agent';
  d.innerHTML = _agentHdr(false) + '<div class="tui-msg-body md-body"></div>';
  d.querySelector('.tui-msg-body').innerHTML = _mdToHtml(text);
  msgs.appendChild(d);
  scrollBottom();
}}

function appendUserMsg(text, isSlash, images) {{
  const msgs = document.getElementById('tui-messages');
  const d = document.createElement('div');
  d.className = 'tui-msg tui-msg-user';
  if (isSlash) {{
    d.innerHTML = '<div class="tui-msg-hdr" style="color:#bb66ff">⌘ Comando</div>'
      + '<div class="tui-msg-body" style="border-color:#bb66ff;color:#cba6f7"></div>';
  }} else {{
    d.innerHTML = '<div class="tui-msg-hdr">▶ Tú</div><div class="tui-msg-body"></div>';
  }}
  
  // Construir el contenido del mensaje
  const bodyEl = d.querySelector('.tui-msg-body');
  
  // Añadir texto del mensaje
  bodyEl.textContent = text;
  
  // Añadir imágenes adjuntas si las hay
  if (images && images.length > 0) {{
    images.forEach((img, idx) => {{
      const imgEl = document.createElement('img');
      imgEl.src = img;
      imgEl.alt = 'Imagen adjunta';
      imgEl.style.maxWidth = '100%';
      imgEl.style.maxHeight = '400px';
      imgEl.style.objectFit = 'contain';
      imgEl.style.margin = '12px 0';
      imgEl.style.borderRadius = '4px';
      imgEl.style.border = '1px solid rgba(0,180,240,.3)';
      bodyEl.appendChild(imgEl);
    }});
  }}
  
  msgs.appendChild(d);
  scrollBottom();
}}

function scrollBottom() {{
  // Solo auto-scroll si el usuario está pegado al fondo (o muy cerca).
  // Si subió a leer, no le forzamos a bajar en cada tool_start/tool_done.
  if (!_scrollPinned) return;
  const msgs = document.getElementById('tui-messages');
  // requestAnimationFrame garantiza que el layout del nuevo contenido ya esté calculado
  requestAnimationFrame(() => {{ msgs.scrollTop = msgs.scrollHeight; }});
}}

function _forceScrollBottom() {{
  // Forzar scroll al fondo y activar pin (al enviar mensaje, al conectar, etc.)
  _scrollPinned = true;
  const msgs = document.getElementById('tui-messages');
  requestAnimationFrame(() => {{ msgs.scrollTop = msgs.scrollHeight; }});
}}

// ── EMBED flash ────────────────────────────────────────────────────────────
let _embedTimer = null;
function flashEmbed(op) {{
  const el = document.getElementById('sb-embed');
  if (!el) return;
  const cls = (op === 'save') ? 'embed-save' : 'embed-read';
  el.textContent = (op === 'save') ? '⬟ EMBED' : '◈ EMBED';
  el.style.display = '';
  // Force reflow to restart CSS animation even if already running
  el.className = 'tui-sb-badge';
  void el.offsetWidth;
  el.className = 'tui-sb-badge ' + cls;
  clearTimeout(_embedTimer);
  _embedTimer = setTimeout(() => {{
    el.className = 'tui-sb-badge';
    el.style.display = 'none';
  }}, 2000);
}}

// ── Subagent team bar ──────────────────────────────────────────────────────
// Cada subagente: {{id, emoji, name, task, startTs, status:'running'|'done', ctx}}
let _activeSubagents = [];
let _teamTimer = null;

function _startTeamTimer() {{
  if (_teamTimer) return;
  _teamTimer = setInterval(() => {{
    if (!_activeSubagents.some(a => a.status === 'running')) {{
      clearInterval(_teamTimer); _teamTimer = null;
    }}
    renderTeamBar();
  }}, 1000);
}}

// Crea/actualiza la entrada de un subagente (auto-descubre los de team/fanout, que
// no emiten subagent_start). Empareja por nombre, estable en todos los paths.
function _ensureSubagentEntry(name, emoji, task, id) {{
  if (!name) return null;
  let e = _activeSubagents.find(a => a.name === name);
  if (!e) {{
    e = {{id: id || name, emoji: emoji || '🤖', name: name,
          task: task || '', startTs: Date.now(), status: 'running', ctx: 0}};
    _activeSubagents.push(e);
    _startTeamTimer();
  }} else {{
    if (task && !e.task) e.task = task;
    if (emoji && e.emoji === '🤖') e.emoji = emoji;
    if (id && (!e.id || e.id === e.name)) e.id = id;
  }}
  return e;
}}

function renderTeamBar() {{
  const el = document.getElementById('tui-team-bar');
  if (!el) return;
  if (!_activeSubagents.length) {{ el.style.display = 'none'; return; }}
  // SOLO cabecera de una línea (status). Formato: «📋 Main 💬 💻 Sub · N subagente(s)».
  // La tarea/tools/texto del subagente viven en su bloque en la conversación.
  const me   = (_agentEmoji || '🤖') + ' ' + (_agentName || 'OOCode');
  const subs = _activeSubagents.map(a =>
    '<span class="team-sub ' + a.status + '">'
    + (a.status === 'done' ? '✓ ' : '')
    + _esc(a.emoji) + ' ' + _esc(a.name) + '</span>'
  ).join('  ·  ');
  el.innerHTML = '<span class="team-hdr">' + _esc(me)
    + ' <span class="team-chat">💬</span> ' + subs
    + ' · ' + _activeSubagents.length + ' subagente(s)</span>';
  el.style.display = '';
}}

// ── Status bar update ──────────────────────────────────────────────────────
function _setBadge(id, active, cls) {{
  const el = document.getElementById(id);
  if (!el) return;
  if (active) {{
    el.style.display = '';
    el.className = 'tui-sb-badge ' + (cls || 'active');
  }} else {{
    el.style.display = 'none';
  }}
}}

function updateStatus(ev) {{
  if (!ev) return;
  // Persistir nombre y emoji — se usan como fallback cuando el evento es parcial
  // (p.ej. {{"type":"status","elevated":"on"}} no lleva agent_name ni context_pct)
  if (ev.agent_name)  _agentName  = ev.agent_name;
  if (ev.agent_emoji) _agentEmoji = ev.agent_emoji;

  // Agente + modelo — solo actualizar si el evento los trae
  if ('agent_name' in ev || 'agent_emoji' in ev) {{
    const emoji = ev.agent_emoji || _agentEmoji || '🤖';
    const name  = ev.agent_name  || _agentName  || 'OOCode';
    document.getElementById('sb-agent').textContent = emoji + ' ' + name;
  }}
  if ('model' in ev) {{
    const model = (ev.model || '—').replace(/:latest$/, '');
    document.getElementById('sb-model').textContent = model;
  }}

  // Context bar — solo si el evento trae context_pct
  // Formato: "ctx: ▰▰▱▱▱▱▱▱▱▱ 20%  ↻ cerca" (idéntico al TUI)
  if ('context_pct' in ev) {{
  const ctxEl   = document.getElementById('sb-ctx');
  const pct    = ev.context_pct || 0;
  const thrPct = ev.compact_threshold_pct || 80;
  const hint   = ev.compact_hint || '';
  const _BAR_LEN = 10;
  const _filled  = Math.round(Math.min(pct, 100) / 100 * _BAR_LEN);
  const _barStr  = '▰'.repeat(_filled) + '▱'.repeat(_BAR_LEN - _filled);
  const _barTxt  = 'ctx: ' + _barStr + ' ' + pct + '%';
  const ctxCls   = pct >= thrPct ? ' crit' : pct >= thrPct - 20 ? ' warn' : '';
  if (ctxEl)   {{ ctxEl.textContent   = _barTxt; ctxEl.className   = 'tui-sb-ctx' + ctxCls; }}
  }} // end context_pct guard

  // Tasks—solo si el evento trae task_total
  if ('task_total' in ev) {{
    const ttok = ev.task_total || 0;
    const dtok = ev.task_done  || 0;
    if (ttok > 0) {{
      document.getElementById('sb-tasks-sep').style.display = '';
      document.getElementById('sb-tasks').style.display     = '';
      document.getElementById('sb-tasks').textContent = '✔ ' + dtok + '/' + ttok;
    }} else {{
      document.getElementById('sb-tasks-sep').style.display = 'none';
      document.getElementById('sb-tasks').style.display     = 'none';
    }}
  }}

  // Tokens—solo si el evento los trae
  if ('tokens_in' in ev || 'tokens_out' in ev) {{
    const inp = ev.tokens_in  || 0;
    const out = ev.tokens_out || 0;
    if (inp > 0 || out > 0)
      document.getElementById('sb-tokens').textContent = inp + '↑ ' + out + '↓';
  }}

  // Feature badges (from /api/chat/status response)
  if ('mcp_count' in ev) {{
    _setBadge('sb-mcp', ev.mcp_count > 0, 'mcp-active');
    const mcpEl = document.getElementById('sb-mcp');
    if (mcpEl && ev.mcp_count > 0) mcpEl.textContent = '◎ MCP×' + ev.mcp_count;
  }}
  if ('lsp_on' in ev) {{
    const lspLangs = (ev.lsp_installed || []);
    _setBadge('sb-lsp', ev.lsp_on || lspLangs.length > 0, 'lsp-active');
    const lspEl = document.getElementById('sb-lsp');
    if (lspEl && lspLangs.length > 0) {{
      lspEl.textContent = '⟨⟩ LSP';
      lspEl.title = 'Lenguajes: ' + lspLangs.join(', ');
    }}
  }}
  if ('memory_on' in ev) _setBadge('sb-mem', ev.memory_on, 'mem-active');
  if ('rag_on' in ev)    _setBadge('sb-rag', ev.rag_on,    'rag-active');
  if ('vision_on' in ev) _setBadge('sb-vision', ev.vision_on, 'vision-active');

  // Compact hint junto a la barra de contexto
  const hintEl = document.getElementById('sb-compact-hint');
  if (hintEl && 'compact_hint' in ev) {{
    const h = ev.compact_hint || '';
    hintEl.textContent = h;
    hintEl.style.display = h ? '' : 'none';
    hintEl.style.color = (h === '↻ compactando') ? '#f38ba8' : '#f9e2af';
  }}

  // Segunda barra: MCP y LSP en líneas independientes.
  // Solo se actualiza cuando el evento trae estos campos (solo /api/chat/status,
  // no los SSE de turno). Así se evita que parpadeen al llegar eventos 'done'.
  if ('mcp_server_names' in ev || 'mcp_count' in ev || 'lsp_installed' in ev || 'lsp_on' in ev) {{
    const mcpNames     = ev.mcp_server_names || [];
    const lspInstalled = ev.lsp_installed    || [];
    const mcpEl2  = document.getElementById('sb-mcp-names');
    const lspEl2  = document.getElementById('sb-lsp-langs');
    const mcpRow  = document.getElementById('tui-sb2-mcp');
    const lspRow  = document.getElementById('tui-sb2-lsp');
    if (mcpEl2 && mcpRow) {{
      if (mcpNames.length > 0) {{
        mcpEl2.textContent  = '◎ MCP: ' + mcpNames.join('  ·  ');
        mcpRow.style.display = '';
      }} else {{
        mcpEl2.textContent  = '';
        mcpRow.style.display = 'none';
      }}
    }}
    if (lspEl2 && lspRow) {{
      if (lspInstalled.length > 0) {{
        lspEl2.textContent  = '⟨⟩ LSP: ' + lspInstalled.join('  ·  ');
        lspRow.style.display = '';
      }} else {{
        lspEl2.textContent  = '';
        lspRow.style.display = 'none';
      }}
    }}
  }}

  // Elevated mode badge (siempre visible para poder hacer click)
  if ('elevated' in ev) {{
    const elev = ev.elevated || 'ask';
    const elevEl = document.getElementById('sb-elev');
    if (elevEl) {{
      elevEl.style.display = '';
      const elevLabels = {{ask:'⊙ perms', off:'⊘ off', on:'⬆ on', full:'⚡ full'}};
      const elevTips   = {{
        ask:  'Permisos normales (ask) — click para cambiar',
        off:  'Solo lectura (off) — click para cambiar',
        on:   'Modo elevado (on) — click para cambiar',
        full: 'Sin restricciones (full) — click para cambiar',
      }};
      elevEl.textContent = elevLabels[elev] || elev;
      elevEl.className = 'tui-sb-badge elev-clickable elev-' + elev;
      elevEl.title = elevTips[elev] || 'Click para cambiar permisos';
    }}
  }}
}}

async function loadStatus(retries) {{
  // Retry until loop is ready (async init may take a few seconds)
  const _retries = (retries === undefined) ? 0 : retries;
  try {{
    const r = await fetch('/api/chat/status');
    const s = await r.json();
    if (!s.connected && _retries > 0) {{
      setTimeout(() => loadStatus(_retries - 1), 2000);
      return;
    }}
    updateStatus(s);
  }} catch(e) {{
    if (_retries > 0) setTimeout(() => loadStatus(_retries - 1), 2000);
  }}
}}

// ── Load history ───────────────────────────────────────────────────────────
async function loadHistory() {{
  const msgs = document.getElementById('tui-messages');
  try {{
    const r = await fetch('/api/chat/history?agent_id=' + _agentId);
    const d = await r.json();
    const hist = d.history || [];
    msgs.innerHTML = '';
    if (!hist.length) {{
      msgs.innerHTML = '<div style="color:#334455;font-size:.8rem;padding:10px 0;text-align:center">Nueva sesión — escribe tu primer mensaje</div>';
      return;
    }}
    for (const h of hist) {{
      const imgs = h.images || [];
      if (h.role === 'user')      appendUserMsg(h.text, (h.text||'').startsWith('/'), imgs);
      else if (h.role === 'assistant') appendAgentBlock(h.text);
    }}
    _forceScrollBottom();  // Tras cargar historial, bajar al fondo
  }} catch(e) {{
    msgs.innerHTML = '<div style="color:#334455;font-size:.8rem;padding:10px 0;text-align:center">Nueva sesión — escribe tu primer mensaje</div>';
  }}
}}

// Carga el historial de input del prompt (flecha arriba) COMPARTIDO con el TUI
// (~/.oocode/history). Así el recall sobrevive a recargas y coincide con el TUI.
async function loadInputHistory() {{
  try {{
    const r = await fetch('/api/chat/input_history?limit=200');
    const d = await r.json();
    if (Array.isArray(d.history)) {{
      _inputHistory = d.history;
      _historyIdx   = -1;
      _historyDraft = '';
    }}
  }} catch(e) {{ /* sin historial compartido: se usa el de la sesión en curso */ }}
}}

// ── File attach & vision ──────────────────────────────────────────────────
let _pendingFiles = [];  // [{{path, name, type, previewUrl}}]

function triggerFileInput() {{
  const inp = document.getElementById('tui-file-input');
  if (inp) inp.click();
}}

async function handleFileSelect(input) {{
  const files = Array.from(input.files || []);
  if (!files.length) return;
  for (const file of files) {{
    const fd = new FormData();
    fd.append('file', file);
    try {{
      const r = await fetch('/api/files/upload', {{method:'POST', body:fd}});
      const d = await r.json();
      if (d.ok) {{
        const previewUrl = d.type === 'image' ? URL.createObjectURL(file) : null;
        _pendingFiles.push({{path: d.path, name: d.name, type: d.type, size: d.size_h || '', previewUrl}});
        _renderPendingFiles();
      }} else {{
        showToast('Error subiendo: ' + (d.error || '?'), false);
      }}
    }} catch(e) {{
      showToast('Error de red: ' + e.message, false);
    }}
  }}
  input.value = '';
}}

function _renderPendingFiles() {{
  const container = document.getElementById('tui-pending-files');
  if (!container) return;
  if (!_pendingFiles.length) {{
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }}
  container.style.display = '';
  container.innerHTML = _pendingFiles.map((f, i) => {{
    const thumb = f.previewUrl
      ? `<img src="${{f.previewUrl}}" alt="${{_esc(f.name)}}" loading="lazy">`
      : '<span style="font-size:1rem">📄</span>';
    return `<div class="tui-pending-file" title="${{_esc(f.path)}}">`
      + thumb
      + `<span class="tui-pending-file-name">${{_esc(f.name)}}</span>`
      + (f.size ? `<span style="color:#334455;font-size:.7rem">${{_esc(f.size)}}</span>` : '')
      + `<button class="tui-pending-file-remove" onclick="removePendingFile(${{i}})" title="Quitar">✕</button>`
      + '</div>';
  }}).join('');
}}

function removePendingFile(idx) {{
  _pendingFiles.splice(idx, 1);
  _renderPendingFiles();
}}

// ── Send message ───────────────────────────────────────────────────────────
function _startClockAnim() {{
  _clockIdx = 0;
  if (_clockInterval) clearInterval(_clockInterval);
  _clockInterval = setInterval(() => {{
    const btn = document.getElementById('tui-send');
    if (btn) btn.textContent = _clockFrames[_clockIdx % _clockFrames.length];
    _clockIdx++;
  }}, 120);
}}
function _stopClockAnim() {{
  if (_clockInterval) {{ clearInterval(_clockInterval); _clockInterval = null; }}
  const btn = document.getElementById('tui-send');
  if (btn) btn.textContent = '▶ Enviar';
}}
function _startStatusPolling() {{
  if (_statusInterval) clearInterval(_statusInterval);
  _statusInterval = setInterval(loadStatus, 2500);
}}
function _stopStatusPolling() {{
  if (_statusInterval) {{ clearInterval(_statusInterval); _statusInterval = null; }}
}}

// Resetea el safety timeout sin tocar el estado busy.
// El heartbeat (cada 15s) llama aquí para que el timeout no dispare
// mientras el agente siga activo con subagentes o tareas largas.
function _resetBusyTimeout() {{
  if (_busyTimeout) clearTimeout(_busyTimeout);
  _busyTimeout = setTimeout(() => {{
    if (_busy) {{
      setBusy(false);
      showToast('⏱ Sin respuesta del agente — comprueba la conexión', false);
    }}
  }}, 300000);  // 5 min: se renueva en cada heartbeat (cada 15s)
}}

function setBusy(busy) {{
  _busy = busy;
  const btn  = document.getElementById('tui-send');
  const inp  = document.getElementById('tui-input');
  const att  = document.getElementById('tui-attach');
  const kill = document.getElementById('tui-kill');
  if (btn)  btn.disabled = busy;
  if (inp)  inp.disabled = busy;
  if (att)  att.disabled = busy;
  if (kill) kill.style.display = busy ? '' : 'none';
  if (busy) {{
    _startClockAnim();
    _startStatusPolling();
    _resetBusyTimeout();  // 5min inicial; se renueva en cada heartbeat
  }} else {{
    if (_busyTimeout) {{ clearTimeout(_busyTimeout); _busyTimeout = null; }}
    _stopClockAnim();
    _stopStatusPolling();
    loadStatus(5);
  }}
}}

async function killAgent() {{
  // Marcar killed inmediatamente: todos los eventos SSE siguientes se ignoran
  _killed = true;
  _finishAgentMsg();
  _finishToolBlock();
  removeThinking();
  setBusy(false);
  const msgs = document.getElementById('tui-messages');
  const el = document.createElement('div');
  el.style.cssText = 'color:#f38ba8;font-size:.8rem;padding:4px 12px;font-style:italic';
  el.textContent = '↯ Turno interrumpido.';
  msgs.appendChild(el);
  scrollBottom();
  // Notificar al backend (kill all: turno + subagentes/equipos + scheduler + wip).
  try {{
    const r = await fetch('/api/chat/kill', {{method:'POST'}});
    const j = await r.json();
    const parts = [];
    if (j.subagents) parts.push(j.subagents + ' subagente(s)/equipo(s)');
    if (j.jobs)      parts.push(j.jobs + ' jobs deshabilitados');
    if (j.wip)       parts.push(j.wip + ' tareas wip→todo');
    if (parts.length) el.textContent = '↯ Kill all — ' + parts.join('  ·  ') + '.';
  }} catch(e) {{}}
}}

async function sendMsg() {{
  if (_busy) return;
  const inp  = document.getElementById('tui-input');
  const text = inp.value.trim();
  if (!text) return;

  const hint = document.getElementById('tui-slash-hint');
  if (hint) hint.style.display = 'none';

  // Guardar en historial de input (max 200 entradas)
  _inputHistory.push(text);
  if (_inputHistory.length > 200) _inputHistory.shift();
  _historyIdx   = -1;
  _historyDraft = '';

  inp.value = '';
  inp.style.height = 'auto';

  // Preparar imágenes para enviar
  const imgPaths = _pendingFiles.filter(f => f.type === 'image').map(f => f.previewUrl || f.path);
  const isSlash = text.startsWith('/');
  // /session <id> restaura una sesión en el servidor → re-renderizar al terminar el turno
  _pendingSessionReload = /^\/session\s+\S/.test(text);
  appendUserMsg(text, isSlash, imgPaths);

  // Nuevo turno: incrementar ID, resetear kill flag, limpiar estado anterior
  _turnId++;
  _killed = false;
  _turnHadContent = false;
  _finishAgentMsg();
  _finishToolBlock();

  setBusy(true);
  _forceScrollBottom();  // Al enviar, bajar siempre al fondo
  appendThinking();  // Mostrar "Pensando..." inmediatamente en cada turno

  // Include pending images for vision models
  const payload = {{message: text, agent_id: _agentId}};
  if (imgPaths.length) payload.images = imgPaths;

  // Clear pending files before sending
  _pendingFiles = [];
  _renderPendingFiles();

  try {{
    const resp = await fetch('/api/chat/send', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(payload),
    }});
    const d = await resp.json();
    if (!d.ok) {{
      removeThinking();
      setBusy(false);
      showToast((d.error || 'Error enviando mensaje'), false);
    }}
  }} catch(err) {{
    removeThinking();
    setBusy(false);
    showToast('Error de red: ' + err.message, false);
  }}
}}

async function cycleElevated() {{
  const _elevNames = {{ask:'normal (ask)', off:'solo lectura (off)', on:'elevado (on)', full:'sin restricciones (full)'}};
  try {{
    const r = await fetch('/api/chat/elevated', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:'{{}}'}});
    const d = await r.json();
    if (d.ok) {{
      showToast('⬆ Permisos → ' + (_elevNames[d.elevated] || d.elevated), true);
      // El status SSE actualiza el badge automáticamente vía updateStatus
    }} else {{
      showToast('Error cambiando permisos: ' + (d.error || '?'), false);
    }}
  }} catch(e) {{
    showToast('Error de red al cambiar permisos', false);
  }}
}}

async function clearChat() {{
  if (!confirm('¿Iniciar nueva sesión? Se perderá el historial actual.')) return;
  await fetch('/api/chat/clear', {{method:'POST'}});
  document.getElementById('tui-messages').innerHTML =
    '<div style="color:#334455;font-size:.8rem;padding:10px 0;text-align:center">Nueva sesión — escribe tu primer mensaje</div>';
  updateStatus({{}});
  setBusy(false);
}}

async function changeAgent(newId) {{
  _agentId = newId;
  await clearChat();
  connectSSE();
}}

// ── Keyboard shortcuts ─────────────────────────────────────────────────────
document.getElementById('tui-input').addEventListener('keydown', e => {{
  const inp = e.target;
  if (e.key === 'Enter' && !e.shiftKey) {{
    e.preventDefault();
    sendMsg();
    return;
  }}
  // Historial de mensajes: ArrowUp/ArrowDown (solo si el input es de una línea o el cursor está al inicio/final)
  if (e.key === 'ArrowUp' && !e.shiftKey && !e.ctrlKey && !e.altKey) {{
    const noNewlines    = !inp.value.includes('\\n');
    const cursorAtStart = inp.selectionStart === 0 && inp.selectionEnd === 0;
    if ((noNewlines || cursorAtStart) && _inputHistory.length > 0) {{
      e.preventDefault();
      if (_historyIdx === -1) {{
        _historyDraft = inp.value;
        _historyIdx   = _inputHistory.length - 1;
      }} else if (_historyIdx > 0) {{
        _historyIdx--;
      }}
      inp.value = _inputHistory[_historyIdx];
      inp.selectionStart = inp.selectionEnd = inp.value.length;
      autoResize(inp);
    }}
    return;
  }}
  if (e.key === 'ArrowDown' && !e.shiftKey && !e.ctrlKey && !e.altKey) {{
    if (_historyIdx >= 0) {{
      e.preventDefault();
      _historyIdx++;
      if (_historyIdx >= _inputHistory.length) {{
        _historyIdx = -1;
        inp.value   = _historyDraft;
      }} else {{
        inp.value = _inputHistory[_historyIdx];
      }}
      inp.selectionStart = inp.selectionEnd = inp.value.length;
      autoResize(inp);
    }}
    return;
  }}
  // Cualquier otra tecla fuera de flechas resetea el modo historial
  if (e.key.length === 1 || e.key === 'Backspace' || e.key === 'Delete') {{
    _historyIdx   = -1;
    _historyDraft = '';
  }}
}});

// ── Sessions panel ────────────────────────────────────────────────────────
function openSessionsPanel() {{
  document.getElementById('tui-sessions-panel').classList.add('open');
  loadSessionsList();
}}
function closeSessionsPanel() {{
  document.getElementById('tui-sessions-panel').classList.remove('open');
}}
async function loadSessionsList() {{
  const list = document.getElementById('tui-sessions-list');
  list.innerHTML = '<div style="color:#334455;font-size:.8rem;padding:20px;text-align:center">Cargando…</div>';
  try {{
    const r = await fetch('/api/sessions?agent_id=' + _agentId);
    const d = await r.json();
    const sessions = d.sessions || [];
    if (!sessions.length) {{
      list.innerHTML = '<div style="color:#334455;font-size:.8rem;padding:20px;text-align:center">Sin sesiones registradas.</div>';
      return;
    }}
    list.innerHTML = sessions.map(s => {{
      const ts   = (s.started_at || '').replace('T',' ').slice(0,16);
      const msgs = s.message_count || 0;
      const model = (s.model || '—').replace(/:latest$/,'');
      const sid  = (s.session_id || '').slice(0,8);
      const inp  = s.input_tokens ? Math.round(s.input_tokens/1000)+'K' : '—';
      return `<div class="tui-session-item" title="ID: ${{s.session_id||''}}">
        <span class="tui-session-date">${{ts}}</span>
        <span class="tui-session-model" title="${{model}}">${{model}}</span>
        <span class="tui-session-count">${{msgs}} msgs · ${{inp}}</span>
        <button class="tui-session-load-btn" onclick="loadSession('${{s.session_id||''}}', event)">Cargar</button>
      </div>`;
    }}).join('');
  }} catch(e) {{
    list.innerHTML = '<div style="color:#f38ba8;font-size:.8rem;padding:20px;text-align:center">Error cargando sesiones.</div>';
  }}
}}
async function loadSession(sessionId, evt) {{
  if (evt) evt.stopPropagation();
  if (_busy) {{ showToast('El agente está procesando — espera a que termine', false); return; }}
  closeSessionsPanel();
  try {{
    const r = await fetch('/api/chat/load_session', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ session_id: sessionId, agent_id: _agentId }}),
    }});
    const d = await r.json();
    if (!r.ok || d.error) {{
      showToast('✗ No se pudo restaurar: ' + (d.error || 'error'), false);
      return;
    }}
    // Restaurada en el servidor (contexto + sess.history) → re-renderizar conversación
    _finishAgentMsg();
    _finishToolBlock();
    removeThinking();
    await loadHistory();
    showToast('📚 Sesión ' + sessionId.slice(0,8) + ' restaurada (' + (d.count || 0) + ' mensajes)', true);
  }} catch(e) {{
    showToast('✗ Error de red restaurando sesión: ' + e.message, false);
  }}
}}

// ── Scroll pin detector ────────────────────────────────────────────────────
(function() {{
  const msgs = document.getElementById('tui-messages');
  if (!msgs) return;
  msgs.addEventListener('scroll', () => {{
    // Si el usuario está a menos de 80px del fondo → re-activar pin
    _scrollPinned = (msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight) < 80;
  }}, {{ passive: true }});
  // Delegación de clicks en botones de descarga inline (dentro de markdown renderizado)
  msgs.addEventListener('click', e => {{
    const btn = e.target.closest('button[data-dl-path]');
    if (btn) {{
      e.preventDefault();
      _safeDownload(btn.dataset.dlPath, btn.dataset.dlName || btn.dataset.dlPath.split('/').pop());
    }}
  }});
}})();

// ── Init ───────────────────────────────────────────────────────────────────
connectSSE();
</script>
"""
    return _render('chat', 'Chat', content, fullwidth=True)
