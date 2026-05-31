"""Blueprint /config — página de configuración."""
from flask import Blueprint

from webui.templates import _render

bp = Blueprint("page_config", __name__)


@bp.route('/config')
def config_page():
    content = """
<div class="card">
  <h2>⚙️ Configuración de OOCode</h2>
  <p style="color:var(--text-secondary);margin-bottom:16px">
    Los cambios se persisten inmediatamente en <code>~/.oocode/oocode.json</code>.
  </p>
  <div id="cfg-form"></div>
  <div style="margin-top:20px;display:flex;gap:10px;flex-wrap:wrap">
    <button class="btn btn-success" onclick="saveConfig()">💾 Guardar cambios</button>
    <button class="btn btn-secondary" onclick="loadConfig()">🔄 Recargar</button>
    <button class="btn btn-secondary" onclick="showRawJson()">📄 Ver JSON completo</button>
  </div>
</div>
<div class="card" id="raw-json-card" style="display:none">
  <h2>📄 oocode.json completo</h2>
  <pre class="code" id="raw-json-pre"></pre>
</div>

<script>
let _cfg = {};

function field(key, label, type='text', opts={}) {
  const {desc='', choices=null, min=null, max=null} = opts;
  let inp;
  const val = _cfg[key];
  if (type === 'bool') {
    inp = `<input type="checkbox" id="f_${key}" ${val ? 'checked' : ''} style="width:auto;margin-right:6px">
           <label for="f_${key}" style="display:inline;font-weight:normal">${label}</label>`;
    return `<div class="form-group" style="display:flex;align-items:center;gap:4px">${inp}</div>`;
  }
  if (choices) {
    const opts2 = choices.map(c => `<option value="${c}" ${val==c?'selected':''}>${c}</option>`).join('');
    inp = `<select id="f_${key}">${opts2}</select>`;
  } else {
    inp = `<input type="${type}" id="f_${key}" value="${val ?? ''}" ${min!==null?`min="${min}"`:''}
           ${max!==null?`max="${max}"`:''}>`;
  }
  return `<div class="form-group">
    <label for="f_${key}">${label}${desc ? ` <small style="color:var(--text-secondary)">(${desc})</small>` : ''}</label>
    ${inp}
  </div>`;
}

function renderForm() {
  const sections = [
    { title: '🦙 Ollama', fields: [
      ['ollama_host', 'Host Ollama', 'text'],
      ['model', 'Modelo activo', 'text', {desc:'nombre del modelo en Ollama'}],
    ]},
    { title: '🌐 WebUI', fields: [
      ['webui_enabled', 'Habilitar WebUI al arrancar', 'bool'],
      ['webui_host', 'IP de escucha', 'text'],
      ['webui_port', 'Puerto', 'number', {min:1024,max:65535}],
      ['webui_log_file', 'Log file', 'text', {desc:'vacío = ~/.oocode/logs/webserver.log'}],
    ]},
    { title: '🔄 Contexto', fields: [
      ['auto_continue_max', 'Auto-continue máx.', 'number', {min:0,max:20,desc:'0 = desactivado'}],
      ['compact_threshold', 'Compact threshold', 'number', {desc:'0.0–1.0'}],
      ['max_summary_chars', 'Max summary chars', 'number'],
    ]},
    { title: '🔍 RAG', fields: [
      ['rag_enabled', 'RAG habilitado', 'bool'],
      ['rag_top_k', 'Top-K base', 'number', {min:1,max:50}],
      ['rag_similarity_threshold', 'Similaridad mínima', 'number', {desc:'0.0–1.0'}],
      ['rag_index_interval', 'Intervalo re-índice (s)', 'number'],
    ]},
    { title: '🔎 SearXNG', fields: [
      ['searxng_enabled', 'SearXNG habilitado', 'bool'],
      ['searxng_url', 'URL instancia', 'text'],
      ['searxng_max_results', 'Resultados máx.', 'number', {min:1,max:20}],
    ]},
    { title: '🤖 Subagentes', fields: [
      ['subagents_max_concurrent', 'Máx. concurrentes', 'number', {min:1,max:16}],
      ['subagents_max_teams', 'Máx. equipos', 'number', {min:1,max:10}],
      ['subagents_max_team_size', 'Máx. por equipo', 'number', {min:1,max:20}],
      ['subagents_recent_ttl', 'TTL finalizados (s)', 'number'],
    ]},
    { title: '💾 Backups', fields: [
      ['backup_enabled', 'Backups habilitados', 'bool'],
      ['backup_dir', 'Directorio', 'text', {desc:'vacío = ~/.oocode/backup/'}],
      ['backup_max_files', 'Ficheros máx.', 'number', {min:1,max:500}],
    ]},
    { title: '📷 Snapshots', fields: [
      ['snapshots_enabled', 'Snapshots habilitados', 'bool'],
      ['snapshots_max', 'Máx. snapshots', 'number', {min:1,max:100}],
    ]},
    { title: '📝 Logging', fields: [
      ['log_enabled', 'Log habilitado', 'bool'],
      ['log_level', 'Nivel', 'text', {choices:['debug','info','warn','error']}],
    ]},
    { title: '🎨 Apariencia', fields: [
      ['accent_color', 'Color de acento', 'text', {choices:['cyan','blue','green','purple','orange','red']}],
    ]},
    { title: '🧠 Embeddings', fields: [
      ['embed_model', 'Modelo embedding', 'text'],
    ]},
    { title: '📋 Chat / Vision', fields: [
      ['chatlog_enabled', 'Chat log habilitado', 'bool'],
      ['vision_enabled', 'Visión (imágenes) habilitada', 'bool'],
    ]},
    { title: '🔁 Fallback', fields: [
      ['fallback_enabled', 'Fallback habilitado', 'bool'],
      ['fallback_model', 'Modelo fallback', 'text'],
    ]},
  ];

  let html = '';
  for (const sec of sections) {
    html += `<div class="section-title">${sec.title}</div><div class="grid2">`;
    for (const f of sec.fields) {
      html += field(f[0], f[1], f[2]||'text', f[3]||{});
    }
    html += '</div>';
  }
  document.getElementById('cfg-form').innerHTML = html;
}

async function loadConfig() {
  const resp = await fetch('/api/config');
  _cfg = await resp.json();
  renderForm();
}

async function saveConfig() {
  const payload = {};
  const bools = ['webui_enabled','rag_enabled','searxng_enabled','hooks_enabled',
                 'backup_enabled','snapshots_enabled','log_enabled','chatlog_enabled',
                 'vision_enabled','fallback_enabled'];
  for (const k of Object.keys(_cfg)) {
    const el = document.getElementById('f_' + k);
    if (!el) continue;
    if (bools.includes(k)) payload[k] = el.checked;
    else if (el.type === 'number') payload[k] = parseFloat(el.value)||0;
    else payload[k] = el.value;
  }
  const resp = await fetch('/api/config/save', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });
  const d = await resp.json();
  if (d.ok) showToast('✓ Guardado en oocode.json');
  else showToast('Error: ' + (d.error||'?'), false);
}

async function showRawJson() {
  const card = document.getElementById('raw-json-card');
  if (card.style.display === 'none') {
    const resp = await fetch('/api/config/raw');
    const text = await resp.text();
    document.getElementById('raw-json-pre').textContent = text;
    card.style.display = 'block';
  } else {
    card.style.display = 'none';
  }
}

loadConfig();
</script>
"""
    return _render('config', 'Configuración', content)
