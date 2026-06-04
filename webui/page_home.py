"""Blueprint / — página de inicio."""
from flask import Blueprint

from webui.helpers import _load_ooconfig, _model_cards
from webui.templates import _render

bp = Blueprint("page_home", __name__)


@bp.route('/')
def home():
    cfg    = _load_ooconfig()
    cards  = _model_cards(cfg)
    models_html = "".join(
        f'<div class="model-card{"  active" if c["active"] else ""}" onclick="selectModel(\'{c["name"]}\')">'
        f'<h3>{c["name"]}</h3>'
        f'<p>Context: {c["context_window"]} &nbsp;|&nbsp; Max tokens: {c["max_tokens"]}</p>'
        f'</div>'
        for c in cards
    ) or (f'<div class="model-card active"><h3>{cfg.model if cfg else "—"}</h3><p>Modelo activo</p></div>'
          if cfg and cfg.model else '<p>Sin modelos configurados</p>')

    hooks   = cfg.hooks_builtins if cfg else []
    plugins = cfg.plugins_enabled if cfg else []
    agents  = cfg.agents if cfg else []

    hooks_html   = "".join(f'<li>{h}</li>' for h in hooks)   or "<li>Sin hooks</li>"
    plugins_html = "".join(f'<li>{p}</li>' for p in plugins) or "<li>Sin plugins</li>"
    agents_html  = "".join(
        f'<li><strong>{a.emoji} {a.name}</strong> <span style="color:var(--text-secondary);font-size:.85rem">({a.id})</span></li>'
        for a in agents
    ) or "<li>Sin agentes definidos</li>"

    content = f"""
<div class="grid3" style="margin-bottom:20px">
  <div class="stat-card">
    <div class="label">Agente activo</div>
    <div class="value">{cfg.agent_emoji if cfg else '🤖'} {cfg.agent_name if cfg else '—'}</div>
    <div class="sub">ID: {cfg.agent_id if cfg else '—'}</div>
  </div>
  <div class="stat-card">
    <div class="label">Modelo</div>
    <div class="value" style="font-size:1rem;word-break:break-all">{cfg.model if (cfg and cfg.model) else '—'}</div>
    <div class="sub">{cfg.ollama_host if cfg else '—'}</div>
  </div>
  <div class="stat-card">
    <div class="label">Workspace</div>
    <div class="value" style="font-size:.9rem;word-break:break-all">{cfg.workspace if cfg else '—'}</div>
    <div class="sub">
      RAG: <span class="badge {'badge-ok' if cfg and cfg.rag_enabled else 'badge-warn'}">{("✓ ON" if cfg and cfg.rag_enabled else "✗ OFF")}</span>
      &nbsp; Hooks: <span class="badge {'badge-ok' if cfg and cfg.hooks_enabled else 'badge-warn'}">{("✓ ON" if cfg and cfg.hooks_enabled else "✗ OFF")}</span>
    </div>
  </div>
  <div class="stat-card">
    <div class="label">Hooks activos</div>
    <div class="value">{len(hooks)}</div>
    <div class="sub">builtins configurados</div>
  </div>
  <div class="stat-card">
    <div class="label">Plugins</div>
    <div class="value">{len(plugins)}</div>
    <div class="sub">plugins habilitados</div>
  </div>
  <div class="stat-card">
    <div class="label">Agentes</div>
    <div class="value">{len(agents)}</div>
    <div class="sub">definidos en oocode.json</div>
  </div>
</div>

<div class="card">
  <h2>🧠 Modelos configurados</h2>
  <div class="model-selector">{models_html}</div>
</div>

<div class="grid2">
  <div class="card">
    <h2>🔧 Hooks activos ({len(hooks)})</h2>
    <ul class="tag-list">{hooks_html}</ul>
  </div>
  <div class="card">
    <h2>🧩 Plugins ({len(plugins)})</h2>
    <ul class="tag-list">{plugins_html}</ul>
  </div>
</div>

<div class="card">
  <h2>🤖 Agentes disponibles</h2>
  <ul class="tag-list">{agents_html}</ul>
</div>

<script>
async function selectModel(name) {{
  const resp = await fetch('/api/config/save', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{model: name}})
  }});
  const d = await resp.json();
  if (d.ok) {{ showToast('Modelo cambiado a ' + name); setTimeout(()=>location.reload(),1000); }}
  else showToast('Error: ' + (d.error||'?'), false);
}}
</script>
"""
    return _render('home', 'Inicio', content)
