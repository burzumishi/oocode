"""CSS, HTML base template, nav bar y helper _render para OOCode WebUI."""
from flask import render_template_string

# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
:root {
    --bg-primary: #1e1e2e; --bg-secondary: #181825; --bg-tertiary: #11111b;
    --text-primary: #cdd6f4; --text-secondary: #a6adc8;
    --accent-primary: #89b4fa; --accent-secondary: #f38ba8;
    --border-color: #313244;
    --success: #a6e3a1; --warning: #f9e2af; --error: #f38ba8; --info: #89dceb;
    --shadow: 0 4px 6px rgba(0,0,0,.3); --radius: 8px; --transition: all .3s ease;
    --term-bg: #0d0d1a; --term-text: #c0c0d0; --term-accent: #00e5ff;
    --term-green: #00cc66; --term-yellow: #f9e2af; --term-red: #f38ba8;
    --term-dim: #556677;
}
[data-theme="light"] {
    --bg-primary:#fff; --bg-secondary:#f8f9fa; --bg-tertiary:#e9ecef;
    --text-primary:#333; --text-secondary:#666;
    --accent-primary:#2563eb; --accent-secondary:#dc2626;
    --border-color:#d1d5db;
    --success:#059669; --warning:#d97706; --error:#dc2626; --info:#0891b2;
    --shadow:0 4px 6px rgba(0,0,0,.1);
    --term-bg:#1a1a2e; --term-text:#c0ccd0;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg-primary); color:var(--text-primary); line-height:1.6; min-height:100vh; transition:var(--transition); }
.container { max-width:1200px; margin:0 auto; padding:20px; }
header { background:var(--bg-secondary); padding:12px 0; box-shadow:var(--shadow); position:sticky; top:0; z-index:200; }
.header-content { display:flex; justify-content:space-between; align-items:center; padding:0 20px; }
.logo { font-size:1.4rem; font-weight:bold; color:var(--accent-primary); display:flex; align-items:center; gap:8px; }
.logo-icon { font-size:1.8rem; animation:pulse 2s infinite; }
@keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.05)} }
.nav-links { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
.nav-links a { color:var(--text-secondary); text-decoration:none; padding:6px 13px; border-radius:var(--radius); transition:var(--transition); font-size:.9rem; white-space:nowrap; }
.nav-links a:hover,.nav-links a.active { background:var(--bg-tertiary); color:var(--accent-primary); }
.theme-toggle-btn { background:none; border:1px solid var(--border-color); border-radius:6px; padding:5px 10px; font-size:1.1rem; cursor:pointer; transition:var(--transition); color:var(--text-secondary); margin-right:6px; }
.theme-toggle-btn:hover { border-color:var(--accent-primary); background:var(--bg-tertiary); }
.hamburger { display:none; flex-direction:column; gap:5px; cursor:pointer; padding:6px; border:none; background:none; }
.hamburger span { display:block; width:24px; height:2px; background:var(--text-secondary); border-radius:2px; transition:var(--transition); }
.hamburger.open span:nth-child(1) { transform:rotate(45deg) translate(5px,5px); }
.hamburger.open span:nth-child(2) { opacity:0; }
.hamburger.open span:nth-child(3) { transform:rotate(-45deg) translate(5px,-5px); }
.mobile-nav { display:none; position:fixed; top:0; left:0; right:0; bottom:0; z-index:300; flex-direction:column; background:var(--bg-secondary); padding:20px; }
.mobile-nav.open { display:flex; }
.mobile-nav-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
.mobile-nav-title { font-size:1.4rem; font-weight:bold; color:var(--accent-primary); }
.mobile-nav-close { font-size:1.8rem; cursor:pointer; background:none; border:none; color:var(--text-secondary); line-height:1; }
.mobile-nav-links { display:flex; flex-direction:column; gap:4px; }
.mobile-nav-links a { color:var(--text-secondary); text-decoration:none; padding:14px 16px; border-radius:var(--radius); font-size:1.1rem; transition:var(--transition); border:1px solid transparent; }
.mobile-nav-links a:hover,.mobile-nav-links a.active { background:var(--bg-tertiary); color:var(--accent-primary); border-color:var(--border-color); }
.main-content { padding:20px 0; }
.card { background:var(--bg-secondary); border-radius:var(--radius); padding:20px; margin-bottom:20px; box-shadow:var(--shadow); border:1px solid var(--border-color); transition:var(--transition); }
.card:hover { border-color:var(--accent-primary); }
.card h2 { color:var(--accent-primary); margin-bottom:15px; font-size:1.3rem; display:flex; align-items:center; gap:10px; }
.card h2::before { content:''; display:inline-block; width:4px; height:20px; background:var(--accent-primary); border-radius:2px; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:20px; }
.grid3 { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:15px; }
.stat-card { background:var(--bg-tertiary); padding:15px; border-radius:var(--radius); border:1px solid var(--border-color); }
.stat-card .label { font-size:.8rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.05em; }
.stat-card .value { font-size:1.4rem; font-weight:bold; color:var(--accent-primary); margin-top:4px; }
.stat-card .sub { font-size:.85rem; color:var(--text-secondary); margin-top:2px; word-break:break-all; }
.model-selector { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:15px; margin-top:15px; }
.model-card { background:var(--bg-tertiary); padding:15px; border-radius:var(--radius); border:1px solid var(--border-color); transition:var(--transition); cursor:pointer; }
.model-card:hover { border-color:var(--accent-primary); transform:translateY(-2px); }
.model-card.active { border-color:var(--accent-primary); background:rgba(137,180,250,.1); }
.model-card h3 { color:var(--accent-primary); margin-bottom:6px; font-size:1rem; word-break:break-all; }
.model-card p { color:var(--text-secondary); font-size:.85rem; }
.badge { display:inline-flex; align-items:center; gap:5px; padding:3px 10px; border-radius:20px; font-size:.82rem; font-weight:500; }
.badge-ok { background:rgba(166,227,161,.2); color:var(--success); }
.badge-warn { background:rgba(249,226,175,.2); color:var(--warning); }
.badge-err { background:rgba(243,138,168,.2); color:var(--error); }
.badge-info { background:rgba(137,220,235,.2); color:var(--info); }
.btn { display:inline-flex; align-items:center; gap:8px; padding:10px 20px; border:none; border-radius:var(--radius); background:var(--accent-primary); color:var(--bg-primary); font-size:1rem; cursor:pointer; transition:var(--transition); text-decoration:none; }
.btn:hover { opacity:.85; transform:translateY(-1px); }
.btn:disabled { opacity:.5; cursor:not-allowed; transform:none; }
.btn-sm { padding:6px 14px; font-size:.88rem; }
.btn-danger { background:var(--error); }
.btn-secondary { background:var(--bg-tertiary); color:var(--text-primary); }
.btn-success { background:var(--success); color:var(--bg-primary); }
.form-group { margin-bottom:14px; }
.form-group label { display:block; margin-bottom:5px; color:var(--text-secondary); font-size:.9rem; }
.form-group input,.form-group select,.form-group textarea { width:100%; padding:9px; border:1px solid var(--border-color); border-radius:var(--radius); background:var(--bg-primary); color:var(--text-primary); font-size:.95rem; transition:var(--transition); }
.form-group input:focus,.form-group select:focus,.form-group textarea:focus { outline:none; border-color:var(--accent-primary); box-shadow:0 0 0 3px rgba(137,180,250,.2); }
.form-group input[type=checkbox] { width:auto; margin-right:8px; }
.section-title { font-size:1rem; font-weight:600; color:var(--accent-primary); border-bottom:1px solid var(--border-color); padding-bottom:8px; margin:20px 0 14px; }
.toast { position:fixed; bottom:24px; right:24px; padding:12px 22px; border-radius:var(--radius); background:var(--success); color:var(--bg-primary); font-weight:600; z-index:999; animation:fadeIn .3s ease; display:none; }
.toast.error { background:var(--error); }
@keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
@keyframes slideIn { from{opacity:0;transform:translateX(-15px)} to{opacity:1;transform:translateX(0)} }
table.tbl { width:100%; border-collapse:collapse; font-size:.9rem; }
table.tbl th { text-align:left; padding:10px 12px; border-bottom:2px solid var(--border-color); color:var(--text-secondary); font-size:.8rem; text-transform:uppercase; letter-spacing:.05em; }
table.tbl td { padding:10px 12px; border-bottom:1px solid var(--border-color); vertical-align:middle; }
table.tbl tr:hover td { background:rgba(137,180,250,.05); }
.pulse { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--success); animation:blink 1.2s ease-in-out infinite; margin-right:6px; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }
pre.code { background:var(--bg-tertiary); padding:15px; border-radius:var(--radius); overflow-x:auto; font-size:.85rem; border:1px solid var(--border-color); white-space:pre-wrap; word-break:break-word; }
.footer { text-align:center; padding:20px; color:var(--text-secondary); font-size:.85rem; border-top:1px solid var(--border-color); margin-top:40px; }
ul.tag-list { display:flex; flex-wrap:wrap; gap:8px; list-style:none; padding:0; margin-top:10px; }
ul.tag-list li { background:var(--bg-tertiary); padding:4px 12px; border-radius:20px; font-size:.82rem; color:var(--text-secondary); border:1px solid var(--border-color); }

/* ── TUI Chat ─────────────────────────────────────────────────────────────── */
.tui-chat-wrap { display:flex; flex-direction:column; height:calc(100vh - 130px); min-height:480px; background:var(--term-bg); border-radius:var(--radius); border:1px solid var(--border-color); overflow:hidden; font-family:'JetBrains Mono','Fira Code','Cascadia Code',monospace; }
.tui-statusbar { display:flex; align-items:center; gap:0; background:#0a0a18; border-bottom:1px solid #1a2035; padding:4px 10px; font-size:.78rem; color:#8899bb; white-space:nowrap; overflow:hidden; flex-shrink:0; }
.tui-sb-sep { color:#1e2d45; margin:0 8px; }
.tui-sb-agent { color:#00e5ff; font-weight:bold; }
.tui-sb-model { color:#89b4fa; }
.tui-sb-ctx { color:#a6e3a1; }
.tui-sb-ctx.warn { color:#f9e2af; }
.tui-sb-ctx.crit { color:#f38ba8; animation:ctxCritBlink .8s ease-in-out infinite; }
@keyframes ctxCritBlink { 0%,100%{opacity:1} 50%{opacity:.5} }
.tui-sb-tasks { color:#bb66ff; }
.tui-sb-right { margin-left:auto; display:flex; align-items:center; gap:6px; color:#334455; }
.tui-ctx-bar { display:inline-block; width:160px; height:6px; background:#0d1a2a; border:1px solid #1a2e48; border-radius:3px; overflow:hidden; vertical-align:middle; margin:0 5px; flex-shrink:0; }
.tui-ctx-bar-fill { height:100%; width:0%; background:#00cc66; border-radius:2px; transition:width .6s ease, background .4s ease; }
.tui-sb-badge { font-size:.72rem; padding:1px 5px; border-radius:3px; border:1px solid; color:#334455; border-color:#1a2a3a; background:rgba(10,20,35,.5); letter-spacing:.02em; }
.tui-sb-badge.active { color:#667788; border-color:#223344; }
.tui-sb-badge.mcp-active  { color:#00aacc; border-color:#005580; }
.tui-sb-badge.lsp-active  { color:#89b4fa; border-color:#3060a0; }
.tui-sb-badge.mem-active  { color:#a6e3a1; border-color:#306030; }
.tui-sb-badge.rag-active  { color:#bb66ff; border-color:#603090; }
.tui-sb-badge.vision-active { color:#f9e2af; border-color:#806020; }
.tui-sb-badge.elev-on     { color:#f9e2af; border-color:#80600a; background:rgba(80,60,10,.3); }
.tui-sb-badge.elev-full   { color:#f38ba8; border-color:#803050; background:rgba(80,20,30,.3); animation:elevPulse 1.5s ease-in-out infinite; }
.tui-sb-badge.elev-off    { color:#445566; border-color:#1a2a3a; opacity:.6; }
@keyframes elevPulse { 0%,100%{opacity:1} 50%{opacity:.6} }
.tui-messages { flex:1; overflow-y:auto; padding:14px 16px; display:flex; flex-direction:column; gap:0; scroll-behavior:smooth; }
.tui-messages::-webkit-scrollbar { width:6px; }
.tui-messages::-webkit-scrollbar-thumb { background:#1e2d45; border-radius:3px; }
/* ── Mensajes ── */
.tui-msg { margin-bottom:10px; animation:slideIn .18s ease; }
.tui-msg-user .tui-msg-hdr { color:#89b4fa; font-size:.78rem; margin-bottom:4px; }
.tui-msg-user .tui-msg-body { background:#0f1929; border-left:2px solid #89b4fa; padding:8px 12px; border-radius:0 6px 6px 0; white-space:pre-wrap; font-size:.88rem; }
/* Agente: ● text inline — estilo TUI */
.tui-msg-agent { display:flex; align-items:flex-start; gap:.6ch; padding:3px 0; }
.tui-dot { color:#00e5ff; flex-shrink:0; line-height:1.65; font-size:.9rem; user-select:none; }
.tui-dot.streaming { animation:agentDotPulse .9s ease-in-out infinite; }
@keyframes agentDotPulse { 0%,100%{opacity:.4;color:#007799} 50%{opacity:1;color:#00e5ff} }
.tui-msg-agent .tui-msg-body { color:#c0c8d8; font-size:.88rem; line-height:1.65; flex:1; min-width:0; }
/* ── Filas de tools: estilo pipa TUI ── */
.tui-tool { display:flex; align-items:flex-start; padding:1px 0; font-size:.82rem; font-family:'JetBrains Mono','Fira Code',monospace; }
.tui-tool-pipe { color:#1a2d3a; flex-shrink:0; white-space:pre; user-select:none; }
.tui-tool-icon { flex-shrink:0; }
.tui-tool-icon.running { color:#00aacc; }
.tui-tool-icon.ok  { color:#3a7a4a; }
.tui-tool-icon.err { color:#f38ba8; }
.tui-tool-name { color:#3a8faa; white-space:nowrap; margin-left:.2ch; }
.tui-tool-ctx  { color:#2a5a48; margin-left:.4ch; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tui-running-dots { color:#223344; margin-left:.3ch; }
/* ── Tool block: pipa TUI, sin caja ── */
.tui-tool-block-wrapper { margin:1px 0 4px 0; }
.tui-tool-block-header { display:flex; align-items:center; gap:.4ch; padding:2px 0; cursor:pointer; font-size:.82rem; font-family:'JetBrains Mono','Fira Code',monospace; user-select:none; }
.tui-tool-block-header:hover .tui-tool-block-summary { color:#556677; }
.tui-tool-block-icon { color:#2a5040; flex-shrink:0; }
.tui-tool-block-icon.running { color:#00aacc; }
.tui-tool-block-summary { flex:1; color:#2a5040; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tui-tool-block-toggle { color:#1a2d3a; font-size:.7rem; flex-shrink:0; margin-left:.4ch; }
.tui-tool-block-wrapper.expanded .tui-tool-block-toggle { color:#334455; }
/* Inner: colapsado por defecto; visible solo con .expanded */
.tui-tool-block-inner { overflow:hidden; max-height:0; transition:max-height .25s ease-out; }
.tui-tool-block-wrapper.expanded .tui-tool-block-inner { max-height:600px; padding-bottom:2px; }
/* Tarjetas de archivo siempre visibles (no dependientes del estado del tool block) */
.tui-tool-block-wrapper .tui-file-card { display:flex !important; }
/* ── Plan block: estilo TUI plano ── */
.tui-plan-block { margin:5px 0 10px 0; font-family:'JetBrains Mono','Fira Code',monospace; font-size:.84rem; }
.tui-plan-header { color:#bb66ff; font-weight:600; white-space:nowrap; padding:1px 0; }
.tui-plan-header.done { color:#3a8a5a; }
.tui-plan-icon { color:#bb66ff; }
.tui-plan-icon.done { color:#3a8a5a; }
.tui-plan-stats { color:#445566; font-weight:normal; font-size:.8rem; }
.tui-plan-summary { color:#4a5566; font-size:.79rem; padding-left:2ch; }
.tui-plan-tasks { margin-top:2px; display:flex; flex-direction:column; gap:1px; }
.tui-plan-task { display:flex; align-items:flex-start; gap:.5ch; font-size:.82rem; }
.tui-plan-task.pending { color:#334455; padding-left:2ch; }
.tui-plan-task.active  { color:#cc99ff; padding-left:0; }
.tui-plan-task.done    { color:#2a7a4a; padding-left:2ch; }
.tui-task-sym { flex-shrink:0; }
.tui-plan-task.active .tui-task-sym  { color:#bb66ff; }
.tui-plan-task.done .tui-task-sym    { color:#3a8a5a; }
.tui-plan-task.pending .tui-task-sym { color:#334455; }
.tui-plan-extra { color:#263040; font-size:.78rem; padding-left:2ch; }
/* ── Pensando: línea encima del prompt con barras verticales ondulantes ── */
.tui-thinking-area { display:flex; align-items:center; gap:.6ch; padding:4px 12px; background:#080814; border-top:1px solid #0d1225; font-family:'JetBrains Mono','Fira Code',monospace; font-size:.84rem; flex-shrink:0; }
.tui-thinking-dot  { color:#00e5ff; animation:agentDotPulse .9s ease-in-out infinite; flex-shrink:0; }
.tui-thinking-word { color:#00b8cc; white-space:nowrap; }
.tui-wave-bars { display:flex; align-items:flex-end; gap:2px; height:13px; margin-left:.3ch; flex-shrink:0; }
.tui-wave-bar  { width:3px; background:#006680; border-radius:1px; animation:waveBarAnim 1.1s ease-in-out infinite; }
.tui-wave-bar:nth-child(1) { animation-delay:0.00s; }
.tui-wave-bar:nth-child(2) { animation-delay:0.18s; }
.tui-wave-bar:nth-child(3) { animation-delay:0.36s; }
.tui-wave-bar:nth-child(4) { animation-delay:0.54s; }
.tui-wave-bar:nth-child(5) { animation-delay:0.72s; }
.tui-wave-bar:nth-child(6) { animation-delay:0.54s; }
.tui-wave-bar:nth-child(7) { animation-delay:0.36s; }
@keyframes waveBarAnim { 0%,100%{ height:2px; opacity:.35; } 50%{ height:12px; opacity:1; background:#00aacc; } }
.tui-error { color:#f38ba8; background:rgba(243,138,168,.08); border:1px solid rgba(243,138,168,.2); padding:8px 12px; border-radius:var(--radius); font-size:.85rem; margin:6px 0; }
.tui-input-area { padding:10px 12px; border-top:1px solid #1a2035; background:#0a0a18; flex-shrink:0; }
.tui-input-row { display:flex; gap:8px; align-items:flex-end; }
.tui-input { flex:1; background:#0d1520; color:#c0c8d8; border:1px solid #1e2d45; border-radius:6px; padding:9px 12px; font-size:.9rem; font-family:inherit; resize:none; min-height:40px; max-height:160px; transition:border-color .2s; }
.tui-input:focus { outline:none; border-color:#00e5ff; }
.tui-attach-btn { padding:9px 10px; background:none; color:#556677; border:1px solid #1e2d45; border-radius:6px; font-size:1.1rem; cursor:pointer; transition:color .2s,border-color .2s; flex-shrink:0; }
.tui-attach-btn:hover { color:#00aacc; border-color:#00aacc; }
.tui-send-btn { padding:9px 18px; background:#00e5ff; color:#0a0a18; border:none; border-radius:6px; font-size:.95rem; font-weight:bold; cursor:pointer; transition:opacity .2s,background .3s; white-space:nowrap; flex-shrink:0; min-width:90px; text-align:center; }
.tui-send-btn:hover { opacity:.85; }
.tui-send-btn:disabled { opacity:.5; cursor:not-allowed; background:#0a2030; color:#224; }
/* .tui-bottom-bar: base reutilizada por las filas de detalle MCP/LSP (.tui-sb2). */
.tui-bottom-bar { display:flex; align-items:center; gap:8px; background:#060612; border-top:1px solid #0d1225; padding:3px 10px; font-size:.74rem; color:#334455; flex-shrink:0; white-space:nowrap; overflow:hidden; }
.tui-sb2 { font-size:.72rem; padding:2px 10px; gap:6px; flex-wrap:wrap; overflow:hidden; background:#060612; border-top:1px solid #0a0f1c; }
.tui-agent-row { display:flex; align-items:center; gap:8px; padding:6px 10px; background:#0a0a18; border-bottom:1px solid #1a2035; flex-shrink:0; flex-wrap:wrap; }
.tui-agent-row label { color:#556677; font-size:.78rem; flex-shrink:0; }
.tui-agent-sel { background:#0d1520; color:#89b4fa; border:1px solid #1e2d45; border-radius:4px; padding:3px 8px; font-size:.82rem; cursor:pointer; }
.tui-clear-btn { background:none; border:1px solid #1e2d45; color:#556677; border-radius:4px; padding:3px 10px; font-size:.78rem; cursor:pointer; }
.tui-clear-btn:hover { color:#f38ba8; border-color:#f38ba8; }
.tui-sessions-btn { background:none; border:1px solid #1e2d45; color:#445566; border-radius:4px; padding:3px 10px; font-size:.78rem; cursor:pointer; margin-left:auto; }
.tui-sessions-btn:hover { color:#89b4fa; border-color:#89b4fa; }
.tui-sessions-panel { display:none; position:absolute; top:0; left:0; right:0; bottom:0; z-index:50; background:rgba(5,5,20,.96); border-radius:var(--radius); flex-direction:column; }
.tui-sessions-panel.open { display:flex; }
.tui-sessions-panel-header { display:flex; align-items:center; justify-content:space-between; padding:10px 14px; border-bottom:1px solid #1a2035; flex-shrink:0; }
.tui-sessions-panel-title { color:#89b4fa; font-size:.9rem; font-weight:bold; }
.tui-sessions-panel-close { background:none; border:none; color:#556677; font-size:1.2rem; cursor:pointer; }
.tui-sessions-panel-close:hover { color:#f38ba8; }
.tui-sessions-list { flex:1; overflow-y:auto; padding:8px; }
.tui-session-item { display:flex; align-items:center; gap:10px; padding:8px 10px; border:1px solid #1a2035; border-radius:6px; margin-bottom:6px; cursor:pointer; transition:border-color .2s; }
.tui-session-item:hover { border-color:#89b4fa; background:#0a1020; }
.tui-session-date { color:#445566; font-size:.76rem; flex-shrink:0; }
.tui-session-model { color:#334455; font-size:.74rem; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tui-session-count { color:#556677; font-size:.76rem; flex-shrink:0; }
.tui-session-load-btn { background:#1a2035; border:1px solid #1e2d45; color:#89b4fa; border-radius:4px; padding:2px 8px; font-size:.74rem; cursor:pointer; flex-shrink:0; }
.tui-session-load-btn:hover { background:#00e5ff; color:#0a0a18; border-color:#00e5ff; }
/* ── File attachments ────────────────────────────────────────────────────── */
.tui-attachments { margin:10px 0 4px 0; display:flex; flex-direction:column; gap:6px; }
.tui-attachments-hdr { color:#00aacc; font-size:.73rem; font-weight:600; letter-spacing:.06em; text-transform:uppercase; margin-bottom:2px; display:flex; align-items:center; gap:6px; }
.tui-attachment { display:flex; align-items:center; gap:12px; background:rgba(10,22,40,.9); border:1px solid rgba(0,180,220,.18); border-radius:10px; padding:10px 14px; max-width:480px; transition:border-color .2s; }
.tui-attachment:hover { border-color:rgba(0,220,240,.5); }
.tui-att-icon { font-size:2rem; flex-shrink:0; }
.tui-att-body { flex:1; min-width:0; }
.tui-att-name { color:#c8e0f8; font-size:.88rem; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-bottom:3px; }
.tui-att-meta { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.tui-att-size { color:#445577; font-size:.74rem; }
.tui-att-badge { font-size:.68rem; padding:1px 6px; border-radius:3px; font-weight:600; background:rgba(0,180,200,.12); color:#00aacc; border:1px solid rgba(0,180,200,.25); }
.tui-att-badge.edited { background:rgba(137,180,250,.1); color:#89b4fa; border-color:rgba(137,180,250,.25); }
.tui-att-dl { display:inline-flex; align-items:center; gap:5px; padding:7px 16px; background:#00e5ff; color:#060a12; border-radius:6px; font-size:.8rem; font-weight:800; text-decoration:none; transition:opacity .15s; white-space:nowrap; border:none; cursor:pointer; font-family:inherit; }
.tui-att-dl:hover { opacity:.88; }
.tui-att-dl.edited { background:#89b4fa; }
/* ── Pending attachments (before send) ───────────────────────────────────── */
.tui-pending-files { display:flex; flex-wrap:wrap; gap:6px; padding:4px 0; }
.tui-pending-file { display:flex; align-items:center; gap:6px; background:#0d1520; border:1px solid #1e2d45; border-radius:6px; padding:4px 10px; font-size:.78rem; color:#89b4fa; }
.tui-pending-file-remove { background:none; border:none; color:#556677; cursor:pointer; font-size:.9rem; padding:0 2px; }
.tui-pending-file-remove:hover { color:#f38ba8; }
.tui-pending-file img { width:32px; height:32px; object-fit:cover; border-radius:3px; }
/* ── Markdown rendered output ─────────────────────────────────────────────── */
.md-body { font-size:.88rem; color:#c0c8d8; line-height:1.7; }
.md-body h1 { color:#00e5ff; font-size:1.15rem; margin:.8em 0 .4em; padding-bottom:4px; border-bottom:1px solid #1e2d45; }
.md-body h2 { color:#89b4fa; font-size:1.05rem; margin:.7em 0 .35em; }
.md-body h3 { color:#a6adc8; font-size:.95rem; margin:.6em 0 .3em; }
.md-body p  { margin:.4em 0; }
.md-body strong { color:#cdd6f4; font-weight:700; }
.md-body em     { color:#b0b8d0; font-style:italic; }
.md-body code   { background:#0d1520; color:#00e5ff; padding:1px 5px; border-radius:3px; font-family:'JetBrains Mono','Fira Code',monospace; font-size:.83em; border:1px solid #1a2a40; }
.md-body pre    { background:#0a1018; border:1px solid #1a2a40; border-radius:6px; padding:10px 14px; overflow-x:auto; margin:.5em 0; }
.md-body pre code { background:none; border:none; padding:0; color:#a8c0d0; font-size:.85rem; }
.md-body ul,.md-body ol { padding-left:1.6em; margin:.4em 0; }
.md-body li { margin:.15em 0; }
.md-body blockquote { border-left:3px solid #334455; padding:.3em .8em; color:#778899; margin:.4em 0; font-style:italic; }
.md-body hr { border:none; border-top:1px solid #1e2d45; margin:.6em 0; }
.md-body a  { color:#89b4fa; text-decoration:none; }
.md-body a:hover { text-decoration:underline; }
.md-body table { border-collapse:collapse; font-size:.84rem; margin:.5em 0; width:100%; }
.md-body th { background:#0d1525; color:#89b4fa; padding:5px 10px; border:1px solid #1e2d45; text-align:left; }
.md-body td { padding:4px 10px; border:1px solid #1a2030; }
.md-body tr:nth-child(even) td { background:rgba(10,20,35,.5); }
/* ── Responsive ───────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .nav-links { display:none !important; }
  .hamburger { display:flex !important; }
  .container { padding:12px; }
  .grid2,.grid3 { grid-template-columns:1fr; }
  .tui-chat-wrap { height:calc(100vh - 90px); border-radius:0; border-left:none; border-right:none; }
  .tui-statusbar { font-size:.7rem; padding:3px 8px; }
  .toast { right:12px; left:12px; text-align:center; }
}
"""

_NAV_LINKS = [
    ("/",        "home",     "Inicio"),
    ("/agents",  "agents",   "Agentes"),
    ("/config",  "config",   "Config"),
    ("/chat",    "chat",     "Chat"),
    ("/help",    "help",     "Ayuda"),
    ("/doctor",  "doctor",   "Doctor"),
]

_NAV = """
<header>
  <div class="header-content">
    <div class="logo"><span class="logo-icon">🤖</span><span>OOCode WebUI</span></div>
    <nav class="nav-links">
      {% for href, key, label in nav_links %}
      <a href="{{ href }}" class="{% if tab==key %}active{% endif %}">{{ label }}</a>
      {% endfor %}
    </nav>
    <button class="theme-toggle-btn" id="theme-toggle-btn" onclick="toggleThemeInline()" title="Cambiar tema">🌙</button>
    <button class="hamburger" id="hamburger" onclick="toggleMenu()" aria-label="Menú">
      <span></span><span></span><span></span>
    </button>
  </div>
</header>
<div class="mobile-nav" id="mobile-nav">
  <div class="mobile-nav-header">
    <div class="mobile-nav-title">🤖 OOCode</div>
    <button class="mobile-nav-close" onclick="toggleMenu()">✕</button>
  </div>
  <nav class="mobile-nav-links">
    {% for href, key, label in nav_links %}
    <a href="{{ href }}" class="{% if tab==key %}active{% endif %}" onclick="toggleMenu()">{{ label }}</a>
    {% endfor %}
  </nav>
</div>
<script>
function toggleMenu() {
  document.getElementById('hamburger').classList.toggle('open');
  document.getElementById('mobile-nav').classList.toggle('open');
  document.body.style.overflow = document.getElementById('mobile-nav').classList.contains('open') ? 'hidden' : '';
}
async function toggleThemeInline() {
  const html = document.documentElement;
  const cur = html.getAttribute('data-theme') || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  document.getElementById('theme-toggle-btn').textContent = next === 'dark' ? '🌙' : '☀️';
  await fetch('/theme/set', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({theme: next})});
}
(function() {
  const t = document.documentElement.getAttribute('data-theme') || 'dark';
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) btn.textContent = t === 'dark' ? '🌙' : '☀️';
})();
</script>
"""

_BASE = (
    "<!DOCTYPE html>"
    '<html lang="es" data-theme="{{ theme }}">'
    "<head>"
    '<meta charset="UTF-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    "<title>OOCode WebUI — {{ title }}</title>"
    "<style>" + _CSS + "</style>"
    "</head>"
    "<body>"
    + _NAV +
    '<main class="main-content {{ \'container-fluid\' if fullwidth else \'\' }}">'
    "{% if not fullwidth %}<div class=\"container\">{% endif %}"
    "{{ content | safe }}"
    "{% if not fullwidth %}</div>{% endif %}"
    "</main>"
    '<footer class="footer">'
    "OOCode WebUI v2.1 — 100% local — Ollama | TUI: <code>/webserver</code>"
    "</footer>"
    '<div class="toast" id="toast"></div>'
    "<script>"
    "function showToast(msg, ok=true) {"
    "  const t = document.getElementById('toast');"
    "  t.textContent = msg; t.className = 'toast' + (ok ? '' : ' error');"
    "  t.style.display = 'block';"
    "  setTimeout(() => { t.style.display = 'none'; }, 3500);"
    "}"
    "</script>"
    "</body></html>"
)


def _render(tab: str, title: str, content: str, fullwidth: bool = False) -> str:
    from webui.helpers import _get_theme
    return render_template_string(
        _BASE, tab=tab, title=title, content=content,
        theme=_get_theme(), nav_links=_NAV_LINKS, fullwidth=fullwidth,
    )
