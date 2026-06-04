"""Blueprint /agents — página de subagentes en tiempo real."""
from flask import Blueprint

from webui.helpers import _load_ooconfig
from webui.templates import _render

bp = Blueprint("page_agents", __name__)


@bp.route('/agents')
def agents_page():
    cfg    = _load_ooconfig()
    agents = cfg.agents if cfg else []
    agent_opts = "".join(
        f'<option value="{a.id}">{a.emoji} {a.name} ({a.id})</option>'
        for a in agents
    ) or '<option value="main">main</option>'

    content = f"""
<div class="card">
  <h2>🤖 Subagentes en tiempo real</h2>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
    <span style="font-size:.85rem;color:var(--text-secondary)">Actualización automática cada 2s</span>
    <span id="agents-ts" style="font-size:.8rem;color:var(--text-secondary)"></span>
  </div>
  <div id="agents-container"><p>Cargando…</p></div>
</div>
<div class="card">
  <h2>➕ Lanzar subagente</h2>
  <div class="grid2">
    <div class="form-group">
      <label>ID del agente</label>
      <select id="spawn-agent">{agent_opts}</select>
    </div>
    <div class="form-group">
      <label>Tarea</label>
      <input id="spawn-task" type="text" placeholder="Describe la tarea…">
    </div>
  </div>
  <button class="btn" onclick="spawnAgent()">🚀 Lanzar</button>
  <span id="spawn-result" style="margin-left:14px;font-size:.88rem;color:var(--text-secondary)"></span>
</div>

<!-- Modal overlay para resultado completo -->
<div id="agent-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9999;overflow-y:auto;padding:24px">
  <div style="max-width:900px;margin:0 auto;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:0">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid var(--border)">
      <span id="modal-title" style="font-weight:600;font-size:.95rem"></span>
      <button class="btn btn-secondary btn-sm" onclick="closeModal()">✕ Cerrar</button>
    </div>
    <div id="modal-task" style="padding:12px 18px;background:#05050f;border-bottom:1px solid var(--border);font-size:.82rem;color:var(--text-secondary);white-space:pre-wrap;max-height:120px;overflow-y:auto"></div>
    <div id="modal-body" style="padding:14px 18px;font-size:.84rem;white-space:pre-wrap;font-family:monospace;max-height:70vh;overflow-y:auto;line-height:1.6"></div>
  </div>
</div>

<script>
const POLL_INTERVAL = 2000;

function statusBadge(s) {{
  if (s==='running') return '<span class="badge badge-ok"><span class="pulse"></span>running</span>';
  if (s==='done')    return '<span class="badge" style="color:var(--text-secondary)">done</span>';
  if (s==='killed')  return '<span class="badge badge-warn">killed</span>';
  if (s==='error')   return '<span class="badge badge-err">error</span>';
  return `<span class="badge">${{s}}</span>`;
}}

function esc(s) {{ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

async function fetchAgents() {{
  try {{
    const resp = await fetch('/api/agents');
    const data = await resp.json();
    const all  = [...(data.running||[]), ...(data.recent||[])];
    document.getElementById('agents-ts').textContent = new Date().toLocaleTimeString();
    if (!all.length) {{
      document.getElementById('agents-container').innerHTML =
        '<p style="color:var(--text-secondary)">Sin subagentes activos o recientes.</p>';
      return;
    }}
    let html = '<div style="overflow-x:auto"><table class="tbl"><thead><tr>'
      + '<th>ID</th><th>Agente</th><th>Tarea</th><th>Estado</th><th>Tiempo</th><th>Acciones</th>'
      + '</tr></thead><tbody>';
    for (const a of all) {{
      const hasResult = a.status !== 'running' && (a.result_preview || a.error);
      const taskShort = a.task.length > 80 ? a.task.slice(0,80) + '…' : a.task;
      html += `<tr>
        <td><code title="${{esc(a.run_id)}}">${{esc(a.short_id)}}</code></td>
        <td>${{esc(a.agent_emoji)}} ${{esc(a.agent_name)}}</td>
        <td style="max-width:220px;font-size:.84rem" title="${{esc(a.task)}}">${{esc(taskShort)}}</td>
        <td>${{statusBadge(a.status)}}</td>
        <td>${{a.elapsed}}s</td>
        <td style="white-space:nowrap;display:flex;gap:4px;flex-wrap:wrap">
          ${{a.status==='running' ? `
            <button class="btn btn-danger btn-sm" onclick="killAgent('${{a.run_id}}')">Kill</button>
            <button class="btn btn-secondary btn-sm" onclick="steerAgent('${{a.run_id}}')">Steer</button>
          ` : ''}}
          <button class="btn btn-secondary btn-sm" onclick="showTask('${{esc(a.run_id)}}','${{esc(a.agent_emoji + ' ' + a.agent_name)}}','${{esc(a.task.replace(/'/g,"\\'"))}}')">Tarea</button>
          ${{hasResult ? `<button class="btn btn-secondary btn-sm" onclick="showResult('${{a.run_id}}','${{esc(a.agent_emoji + ' ' + a.agent_name)}}')">Resultado</button>` : ''}}
        </td>
      </tr>`;
    }}
    html += '</tbody></table></div>';
    document.getElementById('agents-container').innerHTML = html;
  }} catch(e) {{
    document.getElementById('agents-container').innerHTML = '<p style="color:var(--error)">Error cargando agentes.</p>';
  }}
}}

async function killAgent(id) {{
  const resp = await fetch('/api/agents/kill/'+id, {{method:'POST'}});
  const d = await resp.json();
  showToast(d.ok ? 'Subagente terminado' : 'Error: '+(d.error||'?'), d.ok);
  fetchAgents();
}}

async function steerAgent(id) {{
  const instr = prompt('Instrucción para el agente:');
  if (!instr) return;
  const resp = await fetch('/api/agents/steer/'+id, {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{instruction: instr}})
  }});
  const d = await resp.json();
  showToast(d.ok ? 'Instrucción enviada' : 'Error: '+(d.error||'?'), d.ok);
}}

function showTask(runId, agentLabel, task) {{
  document.getElementById('modal-title').textContent = agentLabel + ' — Tarea completa';
  document.getElementById('modal-task').textContent  = '';
  document.getElementById('modal-body').textContent  = task;
  document.getElementById('agent-modal').style.display = '';
}}

async function showResult(runId, agentLabel) {{
  document.getElementById('modal-title').textContent = agentLabel + ' — Resultado';
  document.getElementById('modal-task').textContent  = '⏳ Cargando…';
  document.getElementById('modal-body').textContent  = '';
  document.getElementById('agent-modal').style.display = '';
  try {{
    const resp = await fetch('/api/agents/' + runId + '/output');
    const d    = await resp.json();
    if (d.error) {{
      document.getElementById('modal-task').textContent = '';
      document.getElementById('modal-body').innerHTML =
        '<span style="color:var(--error)">✗ ' + esc(d.error) + '</span>';
      return;
    }}
    document.getElementById('modal-task').textContent = '📋 Tarea: ' + (d.task || '');
    const resText  = d.error ? ('✗ Error: ' + d.error) : (d.result || '(sin resultado)');
    const resColor = d.error ? '#f38ba8' : 'var(--text-primary)';
    document.getElementById('modal-body').style.color = resColor;
    document.getElementById('modal-body').textContent = resText;
  }} catch(e) {{
    document.getElementById('modal-body').innerHTML =
      '<span style="color:var(--error)">✗ Error de red</span>';
  }}
}}

function closeModal() {{
  document.getElementById('agent-modal').style.display = 'none';
}}

// Cerrar modal al hacer click en el overlay (fuera del panel)
document.addEventListener('DOMContentLoaded', () => {{
  const modal = document.getElementById('agent-modal');
  modal.addEventListener('click', e => {{ if (e.target === modal) closeModal(); }});
}});

async function spawnAgent() {{
  const agent = document.getElementById('spawn-agent').value.trim();
  const task  = document.getElementById('spawn-task').value.trim();
  if (!agent || !task) {{ showToast('Rellena agente y tarea', false); return; }}
  const result = document.getElementById('spawn-result');
  result.textContent = '⏳ Lanzando…';
  try {{
    const resp = await fetch('/api/agents/spawn', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{agent_id: agent, task: task}})
    }});
    const d = await resp.json();
    if (d.ok) {{
      showToast('✓ Subagente lanzado: ' + d.run_id.slice(0,6));
      result.textContent = '✓ Run ID: ' + d.run_id.slice(0,8);
      document.getElementById('spawn-task').value = '';
      fetchAgents();
    }} else {{
      showToast('Error: ' + (d.error||'?'), false);
      result.textContent = '✗ ' + (d.error||'error');
    }}
  }} catch(e) {{
    showToast('Error de red', false);
    result.textContent = '✗ Error de red';
  }}
}}

setInterval(fetchAgents, POLL_INTERVAL);
fetchAgents();
</script>
"""
    return _render('agents', 'Agentes', content)
