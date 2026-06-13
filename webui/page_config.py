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

function field(key, label, type, opts) {
  type = type || 'text';
  opts = opts || {};
  const desc = opts.desc || '';
  const choices = opts.choices || null;
  const min = opts.min != null ? opts.min : null;
  const max = opts.max != null ? opts.max : null;
  const step = opts.step || null;
  const placeholder = opts.placeholder || '';
  const val = _cfg[key];
  let inp;
  if (type === 'bool') {
    inp = `<input type="checkbox" id="f_${key}" ${val ? 'checked' : ''} style="width:auto;margin-right:6px">
           <label for="f_${key}" style="display:inline;font-weight:normal">${label}</label>`;
    return `<div class="form-group" style="display:flex;align-items:center;gap:4px">${inp}${desc ? `<small style="color:var(--text-secondary);margin-left:8px">(${desc})</small>` : ''}</div>`;
  }
  if (choices) {
    const optHtml = choices.map(c => `<option value="${c}" ${val==c?'selected':''}>${c}</option>`).join('');
    inp = `<select id="f_${key}">${optHtml}</select>`;
  } else {
    const extra = [
      min !== null ? `min="${min}"` : '',
      max !== null ? `max="${max}"` : '',
      step ? `step="${step}"` : '',
      placeholder ? `placeholder="${placeholder}"` : '',
    ].filter(Boolean).join(' ');
    inp = `<input type="${type}" id="f_${key}" value="${val ?? ''}" ${extra}>`;
  }
  return `<div class="form-group">
    <label for="f_${key}">${label}${desc ? ` <small style="color:var(--text-secondary)">(${desc})</small>` : ''}</label>
    ${inp}
  </div>`;
}

function renderForm() {
  const sections = [
    { title: '🔌 Backend LLM (api)', fields: [
      ['api_type',                'Backend', 'text', {choices:['ollama','openai','anthropic'],desc:'ollama estable; openai/anthropic experimentales'}],
      ['api_key',                 'API key', 'password', {desc:'OpenAI / Anthropic; vacío para Ollama'}],
      ['ollama_host',             'Host / baseUrl', 'text', {desc:'Ollama→host; OpenAI→baseUrl; Anthropic→ignorado'}],
      ['ollama_extra_hosts',      'Hosts extra (Ollama)', 'text', {desc:'coma-separados, round-robin para subagentes'}],
      ['ollama_embed_host',       'Host embeddings (Ollama)', 'text', {desc:'vacío = host principal / localhost:11434'}],
      ['ollama_subagent_routing', 'Routing subagentes (Ollama)', 'text', {choices:['round-robin','primary-only']}],
      ['ollama_retry_count',      'Reintentos timeout (Ollama)', 'number', {min:0,max:10}],
      ['ollama_retry_delay',      'Delay reintento (s, Ollama)', 'number', {min:0,max:30,step:'0.5'}],
    ]},
    { title: '🧠 Modelo activo', fields: [
      ['model',                'Modelo activo', 'text', {desc:'nombre del modelo en Ollama'}],
      ['model_system_overhead','System overhead (tokens)', 'number', {min:100,max:20000,desc:'reservados para system prompt + schemas'}],
      ['model_repeat_penalty', 'Repeat penalty global', 'number', {min:0,max:2,step:'0.01',desc:'vacío = sin override'}],
      ['model_seed',           'Seed global', 'number', {desc:'-1 = aleatorio, vacío = sin override'}],
    ]},
    { title: '🌐 WebUI', fields: [
      ['webui_enabled',      'Habilitar WebUI al arrancar', 'bool'],
      ['webui_host',         'IP de escucha', 'text'],
      ['webui_port',         'Puerto', 'number', {min:1024,max:65535}],
      ['webui_log_file',     'Log file WebUI', 'text', {desc:'vacío = ~/.oocode/logs/webserver.log'}],
      ['webui_log_max_size', 'Tamaño máx. log WebUI (MB)', 'number', {min:1,max:500}],
    ]},
    { title: '🔄 Contexto / Compactación', fields: [
      ['auto_continue_max',      'Auto-continue máx.', 'number', {min:0,max:20,desc:'0 = desactivado'}],
      ['compact_threshold',      'Compact threshold', 'number', {min:0.5,max:0.99,step:'0.01',desc:'fracción del límite que dispara compactación'}],
      ['compact_min_keep',       'Mensajes mínimos a conservar', 'number', {min:1,max:50}],
      ['max_summary_chars',      'Max chars resumen compactación', 'number', {min:500,max:10000}],
      ['max_tool_result_tokens', 'Max tokens resultado tool', 'number', {min:100,max:5000}],
    ]},
    { title: '🔧 Límites de herramientas', fields: [
      ['read_file_lines_default',   'Líneas lectura por defecto', 'number', {min:10,max:2000}],
      ['read_file_lines_warn_large','Líneas aviso fichero grande', 'number', {min:100,max:10000}],
      ['web_fetch_max_chars',       'Web fetch máx. chars', 'number', {min:1000,max:100000}],
      ['web_fetch_timeout',         'Web fetch timeout (s)', 'number', {min:5,max:120}],
      ['web_search_max_results',    'Web search máx. resultados', 'number', {min:1,max:20}],
      ['bash_max_output_chars',     'Bash máx. chars output', 'number', {min:1000,max:200000}],
      ['code_search_max_results',   'Code search máx. resultados', 'number', {min:5,max:500}],
      ['code_search_context_lines', 'Code search líneas contexto', 'number', {min:0,max:20}],
      ['code_search_max_filesize',  'Code search tamaño máx. fichero', 'text', {desc:'ej: 500K, 1M'}],
      ['tool_cache_enabled',        'Caché de herramientas', 'bool'],
      ['tool_cache_max_size',       'Caché: entradas máx.', 'number', {min:10,max:2000}],
    ]},
    { title: '🔍 RAG (Retrieval)', fields: [
      ['rag_enabled',              'RAG habilitado', 'bool'],
      ['rag_top_k',                'Top-K base', 'number', {min:1,max:50}],
      ['rag_top_k_complex',        'Top-K complejo', 'number', {min:1,max:100,desc:'queries largas/autoedición'}],
      ['rag_similarity_threshold', 'Similaridad mínima base', 'number', {min:0,max:1,step:'0.01'}],
      ['rag_threshold_complex',    'Similaridad mínima complejo', 'number', {min:0,max:1,step:'0.01'}],
      ['rag_max_snippet_chars',    'Máx. chars por snippet', 'number', {min:100,max:20000}],
      ['rag_index_interval',       'Intervalo re-índice (s)', 'number', {min:10,max:3600}],
    ]},
    { title: '🧮 Embeddings', fields: [
      ['embed_model',               'Modelo embedding', 'text'],
      ['embed_top_k',               'Top-K embeddings', 'number', {min:1,max:50}],
      ['embed_similarity_threshold','Similaridad mínima', 'number', {min:0,max:1,step:'0.01'}],
      ['embed_max_input_chars',     'Máx. chars entrada', 'number', {min:500,max:50000}],
      ['embed_snippet_chars',       'Chars por snippet', 'number', {min:50,max:2000}],
      ['embed_disk_cache_enabled',  'Caché disco habilitada', 'bool'],
      ['embed_disk_cache_dir',      'Directorio caché disco', 'text', {desc:'vacío = ~/.oocode/cache'}],
      ['embed_disk_cache_max',      'Entradas máx. caché disco', 'number', {min:100,max:50000}],
    ]},
    { title: '🔎 SearXNG', fields: [
      ['searxng_enabled',     'SearXNG habilitado', 'bool'],
      ['searxng_url',         'URL instancia', 'text'],
      ['searxng_max_results', 'Resultados máx.', 'number', {min:1,max:20}],
      ['searxng_categories',  'Categorías', 'text', {desc:'ej: general,news'}],
      ['searxng_language',    'Idioma', 'text', {desc:'auto, es, en, …'}],
      ['searxng_safe_search', 'Safe search', 'number', {min:0,max:2,desc:'0=off 1=moderado 2=estricto'}],
      ['searxng_timeout',     'Timeout (s)', 'number', {min:5,max:60}],
    ]},
    { title: '🔌 MCP Servers', fields: [
      ['mcp_request_timeout',               'Timeout requests MCP (s)', 'number', {min:5,max:120}],
      ['mcp_oocode_assistant_enabled',      'OOCode Assistant', 'bool'],
      ['mcp_system_assistant_enabled',      'System Assistant', 'bool'],
      ['mcp_devops_assistant_enabled',      'DevOps Assistant', 'bool'],
      ['mcp_database_assistant_enabled',    'Database Assistant', 'bool'],
      ['mcp_word_assistant_enabled',        'Word Assistant (docs Word/PDF + núcleo O365)', 'bool'],
      ['mcp_excel_assistant_enabled',       'Excel Assistant (hojas .xlsx/CSV)', 'bool'],
      ['mcp_pptx_assistant_enabled',        'PowerPoint Assistant (.pptx)', 'bool'],
      ['mcp_mail_assistant_enabled',        'Mail Assistant (email/cal/notas)', 'bool'],
      ['mcp_cmdb_assistant_enabled',        'CMDB Assistant (inventario IT)', 'bool'],
      ['mcp_security_assistant_enabled',    'Security Assistant', 'bool'],
      ['mcp_iot_assistant_enabled',         'IoT Assistant', 'bool'],
      ['mcp_http_client_assistant_enabled', 'HTTP Client Assistant', 'bool'],
    ]},
    { title: '🪝 Hooks', fields: [
      ['hooks_enabled', 'Hooks habilitados', 'bool'],
    ]},
    { title: '🤖 Subagentes', fields: [
      ['subagents_max_concurrent',   'Máx. concurrentes', 'number', {min:1,max:16}],
      ['subagents_max_teams',        'Máx. equipos', 'number', {min:1,max:10}],
      ['subagents_max_team_size',    'Máx. por equipo', 'number', {min:1,max:20}],
      ['subagents_recent_ttl',       'TTL finalizados (s)', 'number', {min:60,max:86400}],
      ['subagents_default_priority', 'Prioridad por defecto', 'number', {min:-10,max:10}],
      ['subagents_auto_cont_max',    'Auto-continue máx.', 'number', {min:0,max:32,desc:'0 = hereda del agente principal'}],
      ['subagents_inference_timeout','Timeout inferencia (s)', 'number', {min:0,max:3600,desc:'0 = hereda fallback'}],
      ['subagents_default_timeout',  'Timeout tarea (s)', 'number', {min:0,max:7200,desc:'0 = sin límite'}],
    ]},
    { title: '💾 Backups', fields: [
      ['backup_enabled',   'Backups habilitados', 'bool'],
      ['backup_dir',       'Directorio', 'text', {desc:'vacío = ~/.oocode/backup/'}],
      ['backup_max_files', 'Ficheros máx.', 'number', {min:1,max:500}],
    ]},
    { title: '📷 Snapshots', fields: [
      ['snapshots_enabled',        'Snapshots habilitados', 'bool'],
      ['snapshots_max',            'Máx. snapshots', 'number', {min:1,max:100}],
      ['snapshots_save_on_compact','Snapshot al compactar', 'bool'],
    ]},
    { title: '📝 Logging', fields: [
      ['log_enabled',   'Log habilitado', 'bool'],
      ['log_level',     'Nivel', 'text', {choices:['debug','info','warn','error']}],
      ['log_file',      'Fichero log', 'text', {desc:'vacío = ~/.oocode/logs/oocode.log'}],
      ['log_max_size',  'Tamaño máx. (MB)', 'number', {min:1,max:500}],
      ['log_max_files', 'Ficheros de rotación máx.', 'number', {min:1,max:20}],
    ]},
    { title: '👁️ Visión', fields: [
      ['vision_enabled',        'Visión (imágenes) habilitada', 'bool'],
      ['vision_show_indicator', 'Mostrar indicador de visión', 'bool'],
    ]},
    { title: '📋 Chat log', fields: [
      ['chatlog_enabled',    'Chat log habilitado', 'bool'],
      ['chatlog_path',       'Ruta fichero', 'text', {desc:'vacío = ~/.oocode/logs/chatlog.jsonl'}],
      ['chatlog_max_size_mb','Tamaño máx. (MB)', 'number', {min:1,max:500}],
    ]},
    { title: '🔁 Fallback', fields: [
      ['fallback_enabled', 'Fallback habilitado', 'bool'],
      ['fallback_model',   'Modelo fallback', 'text'],
    ]},
    { title: '🎨 Apariencia', fields: [
      ['accent_color', 'Color de acento', 'text', {choices:['cyan','blue','green','purple','orange','red']}],
    ]},
  ];

  let html = '';
  for (const sec of sections) {
    html += `<div class="section-title">${sec.title}</div><div class="grid2">`;
    for (const f of sec.fields) {
      html += field(f[0], f[1], f[2], f[3]);
    }
    html += '</div>';
  }
  document.getElementById('cfg-form').innerHTML = html;
}

const _BOOL_KEYS = [
  'webui_enabled','tool_cache_enabled','rag_enabled','embed_disk_cache_enabled',
  'searxng_enabled','mcp_oocode_assistant_enabled','mcp_system_assistant_enabled',
  'mcp_devops_assistant_enabled','mcp_database_assistant_enabled',
  'mcp_word_assistant_enabled','mcp_excel_assistant_enabled','mcp_pptx_assistant_enabled',
  'mcp_mail_assistant_enabled','mcp_cmdb_assistant_enabled',
  'mcp_security_assistant_enabled',
  'mcp_iot_assistant_enabled','mcp_http_client_assistant_enabled',
  'hooks_enabled','backup_enabled','snapshots_enabled',
  'snapshots_save_on_compact','log_enabled','vision_enabled','vision_show_indicator',
  'chatlog_enabled','fallback_enabled',
];

async function loadConfig() {
  const resp = await fetch('/api/config');
  _cfg = await resp.json();
  renderForm();
}

async function saveConfig() {
  const payload = {};
  for (const k of Object.keys(_cfg)) {
    const el = document.getElementById('f_' + k);
    if (!el) continue;
    if (_BOOL_KEYS.includes(k)) {
      payload[k] = el.checked;
    } else if (el.type === 'number') {
      const v = el.value.trim();
      payload[k] = v === '' ? null : (parseFloat(v) || 0);
    } else {
      const v = el.value.trim();
      payload[k] = v === '' ? null : v;
    }
  }
  const resp = await fetch('/api/config/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const d = await resp.json();
  if (d.ok) showToast('✓ Guardado en oocode.json');
  else showToast('Error: ' + (d.error || '?'), false);
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
