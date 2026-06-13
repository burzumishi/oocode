"""Blueprint /sessions, /help, /doctor, /theme — páginas misceláneas."""
from pathlib import Path

from flask import Blueprint

from webui.helpers import CONFIG_FILE, _get_theme, _load_ooconfig
from webui.sessions import _WEBUI_SESSIONS
from webui.templates import _render

bp = Blueprint("page_misc", __name__)


# ── Sesiones ──────────────────────────────────────────────────────────────────

@bp.route('/sessions')
def sessions_page():
    content = """
<div class="card">
  <h2>📚 Historial de sesiones</h2>
  <div id="sessions-container"><p>Cargando…</p></div>
</div>
<script>
async function loadSessions() {
  const resp = await fetch('/api/sessions');
  const data = await resp.json();
  const sessions = data.sessions || [];
  if (!sessions.length) {
    document.getElementById('sessions-container').innerHTML = '<p style="color:var(--text-secondary)">Sin sesiones registradas.</p>';
    return;
  }
  let html = '<table class="tbl"><thead><tr><th>ID</th><th>Inicio</th><th>Modelo</th><th>Msgs</th><th>Tokens (E/S)</th><th>Compact.</th><th>Acción</th></tr></thead><tbody>';
  for (const s of sessions) {
    const ts = (s.started_at||'').replace('T',' ').slice(0,19);
    const inp = s.input_tokens ? s.input_tokens.toLocaleString() : '—';
    const out = s.output_tokens ? s.output_tokens.toLocaleString() : '—';
    const sid8 = (s.session_id||'').slice(0,8);
    html += `<tr>
      <td><code title="${s.session_id}">${sid8}…</code></td>
      <td>${ts}</td>
      <td style="font-size:.82rem;max-width:200px;word-break:break-all">${s.model||'—'}</td>
      <td>${s.message_count||0}</td>
      <td style="font-size:.82rem">${inp} / ${out}</td>
      <td>${s.compactions||0}</td>
      <td><a href="/chat" class="btn btn-secondary btn-sm" title="/session ${sid8}">Chat →</a></td>
    </tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('sessions-container').innerHTML = html;
}
loadSessions();
</script>
"""
    return _render('sessions', 'Sesiones', content)


# ── Ayuda ─────────────────────────────────────────────────────────────────────

@bp.route('/help')
def help_page():
    try:
        from ui.commands import SLASH_HELP
        cmds_html = "".join(
            f'<tr><td><code>{cmd}</code></td><td style="color:var(--text-secondary);font-size:.88rem">{desc}</td></tr>'
            for cat in SLASH_HELP.values()
            for cmd, desc in (cat.items() if isinstance(cat, dict) else {}.items())
        )
        table = f'<table class="tbl"><thead><tr><th>Comando</th><th>Descripción</th></tr></thead><tbody>{cmds_html}</tbody></table>'
    except Exception:
        table = '<p style="color:var(--text-secondary)">No se pudieron cargar los comandos slash.</p>'

    content = f"""
<div class="card">
  <h2>💬 Chat integrado con AgentLoop</h2>
  <p style="color:var(--text-secondary)">El chat del WebUI usa el mismo AgentLoop que el TUI con todas sus herramientas, memoria, RAG y hooks.</p>
  <ul class="tag-list" style="margin-top:12px">
    <li>✓ Todas las tools MCP disponibles</li>
    <li>✓ Memoria semántica (RAG)</li>
    <li>✓ Hooks activos</li>
    <li>✓ Subagentes desde el chat</li>
    <li>✓ Multi-tarea con plan panel</li>
    <li>✓ Conversación persistente entre pestañas</li>
    <li>✓ Streaming en tiempo real (SSE)</li>
  </ul>
</div>
<div class="card">
  <h2>📖 Comandos slash del TUI</h2>
  {table}
</div>
<div class="card">
  <h2>🌐 API REST del WebUI</h2>
  <table class="tbl">
    <thead><tr><th>Ruta</th><th>Método</th><th>Descripción</th></tr></thead>
    <tbody>
      <tr><td><code>GET /api/config</code></td><td>GET</td><td>Obtener configuración actual</td></tr>
      <tr><td><code>POST /api/config/save</code></td><td>POST</td><td>Guardar campos de configuración</td></tr>
      <tr><td><code>GET /api/config/raw</code></td><td>GET</td><td>oocode.json completo</td></tr>
      <tr><td><code>GET /api/sessions</code></td><td>GET</td><td>Historial de sesiones</td></tr>
      <tr><td><code>GET /api/status</code></td><td>GET</td><td>Estado del sistema</td></tr>
      <tr><td><code>GET /api/agents</code></td><td>GET</td><td>Subagentes activos y recientes</td></tr>
      <tr><td><code>POST /api/agents/spawn</code></td><td>POST</td><td>Lanzar subagente</td></tr>
      <tr><td><code>GET /api/agents/stream</code></td><td>SSE</td><td>Stream de subagentes en tiempo real</td></tr>
      <tr><td><code>POST /api/chat/send</code></td><td>POST</td><td>Enviar mensaje al AgentLoop</td></tr>
      <tr><td><code>GET /api/chat/stream</code></td><td>SSE</td><td>Stream de output del agente</td></tr>
      <tr><td><code>GET /api/chat/history</code></td><td>GET</td><td>Historial del chat actual</td></tr>
      <tr><td><code>GET /api/chat/status</code></td><td>GET</td><td>Estado del agente (ctx, tokens, tareas)</td></tr>
      <tr><td><code>POST /api/chat/clear</code></td><td>POST</td><td>Reiniciar sesión de chat</td></tr>
      <tr><td><code>POST /theme/set</code></td><td>POST</td><td>Cambiar tema (dark/light)</td></tr>
      <tr><td><code>GET /api/files/download?path=…</code></td><td>GET</td><td>Descargar fichero generado por el agente</td></tr>
      <tr><td><code>GET /api/files/info?path=…</code></td><td>GET</td><td>Metadatos de fichero (nombre, tamaño, tipo)</td></tr>
      <tr><td><code>POST /api/files/upload</code></td><td>POST</td><td>Subir imagen o fichero de texto para visión/contexto</td></tr>
    </tbody>
  </table>
</div>
<div class="card">
  <h2>🚀 Arranque rápido</h2>
  <pre class="code">oocode --webui start        # Arrancar WebUI standalone (sin TUI)
oocode --webui stop         # Detener WebUI
oocode --webui status       # Estado actual

# Desde el TUI:
/webserver start            # Arrancar WebUI en background
/webserver stop             # Detener WebUI
/webserver status           # Estado</pre>
</div>
"""
    return _render('help', 'Ayuda', content)


# ── Doctor ────────────────────────────────────────────────────────────────────

@bp.route('/doctor')
def doctor_page():
    checks = []

    def _ok(sec, msg):   checks.append(("ok",   sec, msg))
    def _warn(sec, msg): checks.append(("warn",  sec, msg))
    def _fail(sec, msg): checks.append(("fail",  sec, msg))

    # Config
    if CONFIG_FILE.exists():
        _ok("Config", f"oocode.json encontrado: {CONFIG_FILE}")
    else:
        _fail("Config", f"oocode.json no encontrado: {CONFIG_FILE}")

    cfg = _load_ooconfig()
    if cfg:
        ws = Path(cfg.workspace).expanduser()
        if ws.exists():
            _ok("Config", f"Workspace: {ws}")
        else:
            _warn("Config", f"Workspace no existe: {ws}")
    else:
        _fail("Config", "No se pudo cargar OOConfig")

    # Backend LLM (ollama | openai | anthropic)
    if cfg:
        import urllib.request
        _api_type = getattr(cfg, "api_type", "ollama")
        if _api_type == "ollama":
            try:
                urllib.request.urlopen(f"{cfg.ollama_host}/api/tags", timeout=3)
                _ok("Backend LLM", f"Ollama conectado en {cfg.ollama_host}")
            except Exception as e:
                _warn("Backend LLM", f"Ollama no disponible en {cfg.ollama_host}: {e}")
        else:
            _label = "OpenAI-compatible" if _api_type == "openai" else "Anthropic"
            _ok("Backend LLM", f"Tipo: {_api_type} ({_label} — experimental)")
            if _api_type == "anthropic" and not getattr(cfg, "api_key", ""):
                _fail("Backend LLM", "Falta API key (api.key) requerida por Anthropic")
            elif _api_type == "openai" and getattr(cfg, "api_base_url", ""):
                try:
                    _hdr = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
                    _req = urllib.request.Request(
                        f"{cfg.api_base_url.rstrip('/')}/models", headers=_hdr)
                    urllib.request.urlopen(_req, timeout=4)
                    _ok("Backend LLM", f"Conectado en {cfg.api_base_url}")
                except Exception as e:
                    _warn("Backend LLM", f"baseUrl no verificado ({cfg.api_base_url}): {e}")

        # Embeddings: siempre protocolo Ollama (memoria/RAG), sea cual sea el backend
        if getattr(cfg, "memory_embed_enabled", True):
            _eh = cfg.effective_embed_host
            try:
                urllib.request.urlopen(f"{_eh}/api/tags", timeout=3)
                _ok("Embeddings", f"Host Ollama conectado: {_eh}")
            except Exception as e:
                _warn("Embeddings", f"Host Ollama de embeddings no disponible ({_eh}): {e}")

    # Dependencias Python
    for pkg, label in [("flask", "Flask"), ("rich", "Rich"), ("ollama", "ollama SDK"),
                        ("pydantic", "pydantic"), ("prompt_toolkit", "prompt_toolkit"),
                        ("requests", "requests")]:
        try:
            import importlib
            importlib.import_module(pkg)
            _ok("Dependencias", f"{label} instalado")
        except ImportError:
            _warn("Dependencias", f"{label} no instalado (pip install {pkg})")

    # Flask
    try:
        import flask  # noqa: F401  (comprueba que está instalado)
        from importlib.metadata import version as _pkg_version, PackageNotFoundError
        try:
            _flask_ver = _pkg_version("flask")
        except PackageNotFoundError:
            _flask_ver = "?"
        _ok("Flask", f"Flask {_flask_ver}")
    except Exception:
        _fail("Flask", "Flask no instalado")

    # Sesiones
    try:
        from agent.session import SESSIONS_ROOT
        count = len(list(SESSIONS_ROOT.glob("*/*.jsonl")))
        _ok("Sesiones", f"SESSIONS_ROOT: {SESSIONS_ROOT} ({count} ficheros)")
    except Exception as e:
        _warn("Sesiones", f"Error: {e}")

    # WebUI sessions activas
    _ok("WebUI", f"Sesiones activas de chat: {len(_WEBUI_SESSIONS)}")

    rows = "".join(
        f'<tr><td><span class="badge {"badge-ok" if s=="ok" else ("badge-warn" if s=="warn" else "badge-err")}">'
        f'{"✓" if s=="ok" else "⚠"}</span></td>'
        f'<td style="color:var(--text-secondary);font-size:.85rem">{sec}</td>'
        f'<td>{msg}</td></tr>'
        for s, sec, msg in checks
    )

    content = f"""
<div class="card">
  <h2>🩺 Diagnóstico del sistema</h2>
  <table class="tbl">
    <thead><tr><th>Estado</th><th>Sección</th><th>Detalle</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div style="margin-top:14px">
    <button class="btn" onclick="location.reload()">🔄 Actualizar</button>
  </div>
</div>
"""
    return _render('doctor', 'Doctor', content)


# ── Tema ──────────────────────────────────────────────────────────────────────

@bp.route('/theme')
def theme_page():
    current = _get_theme()
    content = f"""
<div class="card">
  <h2>🎨 Tema de la interfaz</h2>
  <div class="grid2" style="max-width:500px">
    <button class="btn {"btn-success" if current=="dark" else "btn-secondary"}" onclick="setTheme('dark')">
      🌙 Oscuro
    </button>
    <button class="btn {"btn-success" if current=="light" else "btn-secondary"}" onclick="setTheme('light')">
      ☀️ Claro
    </button>
  </div>
  <p style="margin-top:14px;color:var(--text-secondary)">Tema actual: <strong>{current}</strong></p>
</div>
<script>
async function setTheme(t) {{
  await fetch('/theme/set', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{theme:t}})}});
  document.documentElement.setAttribute('data-theme', t);
  showToast('Tema cambiado a ' + t);
  setTimeout(()=>location.reload(), 800);
}}
</script>
"""
    return _render('theme', 'Tema', content)
