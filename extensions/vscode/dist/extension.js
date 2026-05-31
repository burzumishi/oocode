'use strict';

const vscode = require('vscode');
const http   = require('http');
const https  = require('https');
const { exec } = require('child_process');
const path   = require('path');
const fs     = require('fs');
const os     = require('os');

// ── Configuración ──────────────────────────────────────────────────────────

function cfg() {
    return vscode.workspace.getConfiguration('oocode');
}

function apiBase() {
    return cfg().get('host', 'http://localhost:4000');
}

function stateFile() {
    return path.join(os.homedir(), '.oocode', 'webui_state.json');
}

// ── Utilidades HTTP ────────────────────────────────────────────────────────

function apiGet(apiPath) {
    return new Promise((resolve, reject) => {
        const base = apiBase();
        const url  = new URL(apiPath, base);
        const lib  = url.protocol === 'https:' ? https : http;
        lib.get(url.toString(), { timeout: 5000 }, (res) => {
            let data = '';
            res.on('data', d => data += d);
            res.on('end', () => {
                try { resolve(JSON.parse(data)); }
                catch { resolve({ raw: data }); }
            });
        }).on('error', reject);
    });
}

function apiPost(apiPath, body) {
    return new Promise((resolve, reject) => {
        const base    = apiBase();
        const url     = new URL(apiPath, base);
        const payload = JSON.stringify(body);
        const lib     = url.protocol === 'https:' ? https : http;
        const opts    = {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
            timeout: 30000,
        };
        const req = lib.request(url.toString(), opts, (res) => {
            let data = '';
            res.on('data', d => data += d);
            res.on('end', () => {
                try { resolve(JSON.parse(data)); }
                catch { resolve({ raw: data }); }
            });
        });
        req.on('error', reject);
        req.write(payload);
        req.end();
    });
}

// ── Panel WebView ──────────────────────────────────────────────────────────

let _panel = null;

function getOrCreatePanel(ctx) {
    if (_panel) { _panel.reveal(vscode.ViewColumn.Beside); return _panel; }
    _panel = vscode.window.createWebviewPanel(
        'oocode', 'OOCode', vscode.ViewColumn.Beside,
        { enableScripts: true, retainContextWhenHidden: true }
    );
    _panel.webview.html = panelHtml();
    _panel.onDidDispose(() => { _panel = null; }, null, ctx.subscriptions);
    _panel.webview.onDidReceiveMessage(async (msg) => {
        if (msg.command === 'send') {
            await cmdChat(msg.text, msg.context);
        }
    }, null, ctx.subscriptions);
    return _panel;
}

function panelHtml() {
    return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body { font-family: var(--vscode-font-family); font-size: var(--vscode-font-size);
         background: var(--vscode-editor-background); color: var(--vscode-editor-foreground);
         margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; }
  #messages { flex: 1; overflow-y: auto; padding: 12px 16px; }
  .msg-user { background: var(--vscode-inputOption-activeBackground);
              border-radius: 6px; padding: 8px 12px; margin: 8px 0; white-space: pre-wrap; }
  .msg-agent { padding: 8px 12px; margin: 8px 0; white-space: pre-wrap;
               border-left: 3px solid var(--vscode-activityBarBadge-background); }
  .msg-thinking { color: var(--vscode-descriptionForeground); font-style: italic; }
  #input-row { display: flex; gap: 8px; padding: 8px 16px 12px;
               border-top: 1px solid var(--vscode-panel-border); }
  #input { flex: 1; background: var(--vscode-input-background);
           color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border);
           border-radius: 4px; padding: 6px 10px; resize: vertical; min-height: 38px; }
  button { background: var(--vscode-button-background); color: var(--vscode-button-foreground);
           border: none; border-radius: 4px; padding: 6px 14px; cursor: pointer; }
  button:hover { background: var(--vscode-button-hoverBackground); }
  #header { padding: 8px 16px; font-weight: bold;
            border-bottom: 1px solid var(--vscode-panel-border);
            display: flex; align-items: center; gap: 8px; }
</style>
</head>
<body>
<div id="header">🤖 OOCode</div>
<div id="messages"><div class="msg-agent">
  Hola. Escribe tu pregunta o envía código desde el editor.<br>
  Asegúrate de que el WebUI esté activo: <code>oocode --webserver start</code>
</div></div>
<div id="input-row">
  <textarea id="input" placeholder="Escribe tu mensaje…" rows="2"></textarea>
  <button onclick="send()">Enviar</button>
</div>
<script>
const vscode = acquireVsCodeApi();
const input  = document.getElementById('input');
const msgs   = document.getElementById('messages');

input.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') send();
});

function send() {
    const text = input.value.trim();
    if (!text) return;
    appendMsg('user', text);
    input.value = '';
    const thinking = appendMsg('thinking', 'Pensando…');
    vscode.postMessage({ command: 'send', text });
    window.pendingThinking = thinking;
}

function appendMsg(type, text) {
    const div = document.createElement('div');
    div.className = type === 'user' ? 'msg-user' : type === 'thinking' ? 'msg-agent msg-thinking' : 'msg-agent';
    div.textContent = text;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
}

window.addEventListener('message', e => {
    const msg = e.data;
    if (msg.command === 'response') {
        if (window.pendingThinking) { window.pendingThinking.remove(); window.pendingThinking = null; }
        appendMsg('agent', msg.text);
    }
    if (msg.command === 'append') {
        const text = msg.text || '';
        if (window.pendingThinking) { window.pendingThinking.textContent = text; }
        else appendMsg('agent', text);
    }
});
</script>
</body>
</html>`;
}

function panelPost(command, data) {
    if (_panel) _panel.webview.postMessage({ command, ...data });
}

// ── Comandos ───────────────────────────────────────────────────────────────

async function cmdChat(message, context) {
    const agent = cfg().get('agent', 'main');
    const body  = context ? { message: message + '\n\n' + context, agent } : { message, agent };
    try {
        const data = await apiPost('/chat/send', body);
        const text = data.response || data.message || data.raw || JSON.stringify(data);
        panelPost('response', { text });
    } catch (e) {
        panelPost('response', { text: `⚠ Error: ${e.message}\n¿Está activo el WebUI?\nInicia con: oocode --webserver start` });
    }
}

async function cmdStatus() {
    try {
        const data = await apiGet('/api/status');
        const agent = data.agent_id || '?';
        const model = data.model     || '?';
        vscode.window.showInformationMessage(`OOCode: agente=${agent}  modelo=${model}`);
    } catch {
        vscode.window.showWarningMessage('OOCode WebUI no responde. Inicia con: oocode --webserver start');
    }
}

async function cmdModelsList() {
    try {
        const data = await apiGet('/api/config');
        const models = (data.models || {}).configs || {};
        const names  = Object.keys(models);
        if (!names.length) { vscode.window.showInformationMessage('No hay modelos configurados.'); return; }
        vscode.window.showQuickPick(names, { placeHolder: 'Modelos disponibles' });
    } catch {
        vscode.window.showErrorMessage('No se pudo obtener la lista de modelos.');
    }
}

async function cmdModelsSelect() {
    try {
        const data   = await apiGet('/api/config');
        const models = (data.models || {}).configs || {};
        const names  = Object.keys(models);
        if (!names.length) { vscode.window.showInformationMessage('No hay modelos configurados.'); return; }
        const chosen = await vscode.window.showQuickPick(names, { placeHolder: 'Selecciona modelo' });
        if (chosen) {
            await apiPost('/api/config/save', { model: chosen });
            vscode.window.showInformationMessage(`Modelo cambiado a: ${chosen}`);
        }
    } catch {
        vscode.window.showErrorMessage('No se pudo cambiar el modelo.');
    }
}

async function cmdHooksList() {
    try {
        const data  = await apiGet('/api/config');
        const hooks = (data.hooks || {});
        const items = Object.entries(hooks).map(([k, v]) => ({
            label: k,
            description: v.enabled ? '✓ activo' : '○ inactivo',
        }));
        vscode.window.showQuickPick(items, { placeHolder: 'Hooks configurados' });
    } catch {
        vscode.window.showErrorMessage('No se pudo obtener la lista de hooks.');
    }
}

async function cmdSubagentsList() {
    try {
        const data  = await apiGet('/api/agents');
        const agents = data.running || data.agents || [];
        if (!agents.length) { vscode.window.showInformationMessage('No hay subagentes activos.'); return; }
        const items = agents.map(a => ({
            label: a.id || a.agent_id || '?',
            description: a.status || '',
        }));
        vscode.window.showQuickPick(items, { placeHolder: 'Subagentes activos' });
    } catch {
        vscode.window.showErrorMessage('No se pudo obtener la lista de subagentes.');
    }
}

async function cmdSubagentsSpawn() {
    const agentId = await vscode.window.showInputBox({ prompt: 'ID del agente a lanzar (ej: coding)' });
    if (!agentId) return;
    const task = await vscode.window.showInputBox({ prompt: 'Tarea para el subagente' });
    if (!task) return;
    try {
        await apiPost('/api/agents/spawn', { agent_id: agentId, task });
        vscode.window.showInformationMessage(`Subagente ${agentId} lanzado.`);
    } catch {
        vscode.window.showErrorMessage('No se pudo lanzar el subagente.');
    }
}

async function cmdWebServerStatus() {
    const sf = stateFile();
    if (!fs.existsSync(sf)) {
        vscode.window.showInformationMessage('OOCode WebUI no está activo. Usa: oocode --webserver start');
        return;
    }
    try {
        const state   = JSON.parse(fs.readFileSync(sf, 'utf8'));
        const elapsed = Math.round((Date.now() / 1000) - (state.started_ts || 0));
        vscode.window.showInformationMessage(
            `WebUI activo  PID: ${state.pid}  http://${state.host}:${state.port}  uptime: ${elapsed}s`
        );
    } catch {
        vscode.window.showInformationMessage('OOCode WebUI en ejecución (estado no disponible).');
    }
}

function cmdWebServerCtl(action) {
    return () => new Promise((resolve) => {
        exec(`oocode --webserver ${action}`, { timeout: 10000 }, (err, stdout, stderr) => {
            const msg = (stdout + stderr).replace(/\x1b\[[0-9;]*m/g, '').trim();
            if (err) {
                vscode.window.showWarningMessage(`WebUI ${action}: ${msg || err.message}`);
            } else {
                vscode.window.showInformationMessage(`WebUI ${action}: ${msg || 'OK'}`);
            }
            resolve();
        });
    });
}

async function cmdAskInEditor(ctx) {
    const panel = getOrCreatePanel(ctx);
    const editor = vscode.window.activeTextEditor;
    let   context = '';
    if (editor) {
        const sel = editor.selection;
        if (!sel.isEmpty) {
            const lang = editor.document.languageId;
            const text = editor.document.getText(sel);
            const file = editor.document.fileName;
            context = `\n\nSelección de ${path.basename(file)}:\n\`\`\`${lang}\n${text}\n\`\`\``;
        }
    }
    const msg = await vscode.window.showInputBox({ prompt: 'Pregunta a OOCode', placeHolder: '¿Cómo puedo mejorar este código?' });
    if (!msg) return;
    panelPost('append', { text: '❯ ' + msg + (context ? ' [con selección]' : '') });
    await cmdChat(msg, context);
}

// ── Activación ─────────────────────────────────────────────────────────────

function activate(ctx) {
    vscode.commands.executeCommand('setContext', 'ooCodeInstalled', true);

    ctx.subscriptions.push(
        vscode.commands.registerCommand('ooCode.status',            cmdStatus),
        vscode.commands.registerCommand('ooCode.models.list',       cmdModelsList),
        vscode.commands.registerCommand('ooCode.models.select',     cmdModelsSelect),
        vscode.commands.registerCommand('ooCode.hooks.list',        cmdHooksList),
        vscode.commands.registerCommand('ooCode.hooks.enable',      () => vscode.window.showInformationMessage('Gestiona hooks en el WebUI')),
        vscode.commands.registerCommand('ooCode.hooks.disable',     () => vscode.window.showInformationMessage('Gestiona hooks en el WebUI')),
        vscode.commands.registerCommand('ooCode.plugins.list',      () => vscode.window.showInformationMessage('Gestiona plugins en el WebUI')),
        vscode.commands.registerCommand('ooCode.plugins.enable',    () => vscode.window.showInformationMessage('Gestiona plugins en el WebUI')),
        vscode.commands.registerCommand('ooCode.plugins.disable',   () => vscode.window.showInformationMessage('Gestiona plugins en el WebUI')),
        vscode.commands.registerCommand('ooCode.subagents.list',    cmdSubagentsList),
        vscode.commands.registerCommand('ooCode.subagents.spawn',   cmdSubagentsSpawn),
        vscode.commands.registerCommand('ooCode.subagents.kill',    () => vscode.window.showInformationMessage('Gestiona subagentes en el WebUI')),
        vscode.commands.registerCommand('ooCode.webserver.status',  cmdWebServerStatus),
        vscode.commands.registerCommand('ooCode.webserver.start',   cmdWebServerCtl('start')),
        vscode.commands.registerCommand('ooCode.webserver.stop',    cmdWebServerCtl('stop')),
        vscode.commands.registerCommand('ooCode.commands.list',     () => {
            vscode.window.showQuickPick([
                'ooCode.status', 'ooCode.models.list', 'ooCode.models.select',
                'ooCode.hooks.list', 'ooCode.subagents.list', 'ooCode.subagents.spawn',
                'ooCode.webserver.start', 'ooCode.webserver.stop', 'ooCode.webserver.status',
                'ooCode.ask', 'ooCode.help',
            ], { placeHolder: 'Comandos OOCode' });
        }),
        vscode.commands.registerCommand('ooCode.ask',  () => cmdAskInEditor(ctx)),
        vscode.commands.registerCommand('ooCode.help', () => {
            vscode.window.showInformationMessage(
                'OOCode: Usa Ctrl+Shift+P → "OOCode" para ver todos los comandos. ' +
                'WebUI: http://localhost:4000  Docs: github.com/burzumishi/oocode'
            );
        }),
    );
}

function deactivate() {}

module.exports = { activate, deactivate };
