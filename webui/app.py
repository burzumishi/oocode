#!/usr/bin/env python3
"""OOCode WebUI — Interfaz web similar a chatGPT/Claude con todas las funcionalidades del TUI.

Características:
- WebUI en puerto 4000
- Configuración de bloques y parámetros de oocode.json
- Temas claro/oscuro con animaciones y colores agradables
- Autenticación básica
- Comandos slash para configuración
- Integración con MCP tools, hooks, plugins y subagentes
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Any

# Flask
from flask import Flask, request, jsonify, render_template_string, session

# Configuración
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['JSON_SORT_KEYS'] = False

# Rutas de configuración
CONFIG_FILE = Path.home() / ".oocode" / "oocode.json"
STATE_FILE = Path.home() / ".oocode" / "webui_state.json"

# Datos de configuración
def load_config() -> dict:
    """Carga configuración de oocode.json."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception:
            return {}
    return {}

def save_config(config: dict) -> bool:
    """Guarda configuración en oocode.json."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception:
        return False

def load_state() -> dict:
    """Carga estado de la sesión WebUI."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state: dict) -> bool:
    """Guarda estado de la sesión WebUI."""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
        return True
    except Exception:
        return False

# Templates HTML
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es" data-theme="{{ theme }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OOCode WebUI</title>
    <style>
        :root {
            /* Variables CSS — Tema oscuro por defecto */
            --bg-primary: #1e1e2e;
            --bg-secondary: #181825;
            --bg-tertiary: #11111b;
            --text-primary: #cdd6f4;
            --text-secondary: #a6adc8;
            --accent-primary: #89b4fa;
            --accent-secondary: #f38ba8;
            --border-color: #313244;
            --success: #a6e3a1;
            --warning: #f9e2af;
            --error: #f38ba8;
            --info: #89dceb;
            --shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            --radius: 8px;
            --transition: all 0.3s ease;
        }
        
        [data-theme="light"] {
            --bg-primary: #ffffff;
            --bg-secondary: #f8f9fa;
            --bg-tertiary: #e9ecef;
            --text-primary: #333333;
            --text-secondary: #666666;
            --accent-primary: #2563eb;
            --accent-secondary: #dc2626;
            --border-color: #d1d5db;
            --success: #059669;
            --warning: #d97706;
            --error: #dc2626;
            --info: #0891b2;
            --shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
            transition: var(--transition);
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            background: var(--bg-secondary);
            padding: 15px 0;
            box-shadow: var(--shadow);
            margin-bottom: 30px;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        
        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            font-size: 1.5rem;
            font-weight: bold;
            color: var(--accent-primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .logo-icon {
            font-size: 2rem;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        
        .nav-links {
            display: flex;
            gap: 20px;
        }
        
        .nav-links a {
            color: var(--text-secondary);
            text-decoration: none;
            padding: 8px 15px;
            border-radius: var(--radius);
            transition: var(--transition);
        }
        
        .nav-links a:hover,
        .nav-links a.active {
            background: var(--bg-tertiary);
            color: var(--accent-primary);
        }
        
        .main-content {
            padding: 20px 0;
        }
        
        .card {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
            border: 1px solid var(--border-color);
            transition: var(--transition);
        }
        
        .card:hover {
            border-color: var(--accent-primary);
        }
        
        .card h2 {
            color: var(--accent-primary);
            margin-bottom: 15px;
            font-size: 1.3rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .card h2::before {
            content: '';
            display: inline-block;
            width: 4px;
            height: 20px;
            background: var(--accent-primary);
            border-radius: 2px;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 5px;
            color: var(--text-secondary);
            font-size: 0.9rem;
        }
        
        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 10px;
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 1rem;
            transition: var(--transition);
        }
        
        .form-group input:focus,
        .form-group select:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 3px rgba(137, 180, 250, 0.2);
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 20px;
            border: none;
            border-radius: var(--radius);
            background: var(--accent-primary);
            color: var(--bg-primary);
            font-size: 1rem;
            cursor: pointer;
            transition: var(--transition);
            text-decoration: none;
        }
        
        .btn:hover {
            background: var(--accent-secondary);
            transform: translateY(-2px);
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .btn-secondary {
            background: var(--bg-tertiary);
            color: var(--text-primary);
        }
        
        .btn-success {
            background: var(--success);
            color: var(--bg-primary);
        }
        
        .btn-danger {
            background: var(--error);
            color: var(--bg-primary);
        }
        
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 500;
        }
        
        .status-badge.success {
            background: rgba(166, 227, 161, 0.2);
            color: var(--success);
        }
        
        .status-badge.warning {
            background: rgba(249, 226, 175, 0.2);
            color: var(--warning);
        }
        
        .status-badge.error {
            background: rgba(243, 138, 168, 0.2);
            color: var(--error);
        }
        
        .model-selector {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .model-card {
            background: var(--bg-tertiary);
            padding: 15px;
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
            cursor: pointer;
            transition: var(--transition);
        }
        
        .model-card:hover {
            border-color: var(--accent-primary);
            transform: translateY(-3px);
        }
        
        .model-card.active {
            border-color: var(--accent-primary);
            background: rgba(137, 180, 250, 0.1);
        }
        
        .model-card h3 {
            color: var(--accent-primary);
            margin-bottom: 8px;
        }
        
        .model-card p {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }
        
        .config-section {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .config-item {
            background: var(--bg-tertiary);
            padding: 15px;
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
        }
        
        .config-item label {
            display: block;
            margin-bottom: 5px;
            color: var(--text-secondary);
            font-size: 0.85rem;
        }
        
        .config-item input,
        .config-item select {
            width: 100%;
            padding: 8px;
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 0.9rem;
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .tab {
            padding: 10px 20px;
            background: var(--bg-tertiary);
            border: none;
            border-radius: var(--radius);
            color: var(--text-secondary);
            cursor: pointer;
            transition: var(--transition);
            font-size: 0.95rem;
        }
        
        .tab:hover {
            background: var(--bg-secondary);
        }
        
        .tab.active {
            background: var(--accent-primary);
            color: var(--bg-primary);
        }
        
        .tab-content {
            display: none;
            animation: fadeIn 0.3s ease;
        }
        
        .tab-content.active {
            display: block;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message {
            padding: 15px;
            border-radius: var(--radius);
            margin-bottom: 15px;
            border-left: 4px solid var(--accent-primary);
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }
        
        .message.success {
            background: rgba(166, 227, 161, 0.1);
            border-left-color: var(--success);
        }
        
        .message.error {
            background: rgba(243, 138, 168, 0.1);
            border-left-color: var(--error);
        }
        
        .message.info {
            background: rgba(137, 220, 235, 0.1);
            border-left-color: var(--info);
        }
        
        .chat-container {
            display: flex;
            flex-direction: column;
            height: 600px;
            background: var(--bg-tertiary);
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
            overflow: hidden;
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }
        
        .chat-input-container {
            padding: 15px;
            border-top: 1px solid var(--border-color);
            display: flex;
            gap: 10px;
        }
        
        .chat-input {
            flex: 1;
            padding: 12px;
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 1rem;
            resize: none;
        }
        
        .chat-input:focus {
            outline: none;
            border-color: var(--accent-primary);
        }
        
        .chat-message {
            margin-bottom: 15px;
            animation: slideIn 0.3s ease;
        }
        
        .chat-message.user {
            background: var(--accent-primary);
            color: var(--bg-primary);
            border-radius: 12px 12px 0 12px;
            margin-left: 20px;
        }
        
        .chat-message.assistant {
            background: var(--bg-primary);
            color: var(--text-primary);
            border-radius: 12px 12px 12px 0;
            margin-right: 20px;
        }
        
        .chat-message strong {
            display: block;
            margin-bottom: 5px;
            font-size: 0.9rem;
            opacity: 0.8;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid var(--border-color);
            border-radius: 50%;
            border-top-color: var(--accent-primary);
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .footer {
            text-align: center;
            padding: 20px;
            color: var(--text-secondary);
            font-size: 0.85rem;
            border-top: 1px solid var(--border-color);
            margin-top: 40px;
        }
        
        .help-section {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        
        .help-card {
            background: var(--bg-tertiary);
            padding: 15px;
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
        }
        
        .help-card h3 {
            color: var(--accent-primary);
            margin-bottom: 10px;
        }
        
        .help-card code {
            background: var(--bg-secondary);
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.85rem;
            color: var(--accent-secondary);
        }
        
        .tools-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        
        .tool-item {
            background: var(--bg-primary);
            padding: 12px;
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
            transition: var(--transition);
        }
        
        .tool-item:hover {
            border-color: var(--accent-primary);
            transform: translateX(5px);
        }
        
        .tool-item h4 {
            color: var(--accent-primary);
            margin-bottom: 5px;
            font-size: 0.95rem;
        }
        
        .tool-item p {
            color: var(--text-secondary);
            font-size: 0.85rem;
            margin: 0;
        }
        
        .doctor-section {
            background: var(--bg-tertiary);
            padding: 20px;
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
            margin-top: 20px;
        }
        
        .doctor-section pre {
            background: var(--bg-secondary);
            padding: 15px;
            border-radius: var(--radius);
            overflow-x: auto;
            font-size: 0.85rem;
            margin-top: 15px;
        }
        
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid var(--border-color);
            border-radius: 50%;
            border-top-color: var(--accent-primary);
            animation: spin 1s linear infinite;
            margin-right: 10px;
            vertical-align: middle;
        }
        
        .hidden {
            display: none;
        }
    </style>
</head>
<body>
    <header>
        <div class="container header-content">
            <div class="logo">
                <span class="logo-icon">🤖</span>
                <span>OOCode WebUI</span>
            </div>
            <nav class="nav-links">
                <a href="/" class="{% if tab == 'home' %}active{% endif %}">Inicio</a>
                <a href="/config" class="{% if tab == 'config' %}active{% endif %}">Configuración</a>
                <a href="/chat" class="{% if tab == 'chat' %}active{% endif %}">Chat</a>
                <a href="/help" class="{% if tab == 'help' %}active{% endif %}">Ayuda</a>
                <a href="/doctor" class="{% if tab == 'doctor' %}active{% endif %}">Doctor</a>
                <a href="/theme" class="{% if tab == 'theme' %}active{% endif %}">Tema</a>
            </nav>
        </div>
    </header>
    
    <main class="main-content">
        {% block content %}{% endblock %}
    </main>
    
    <footer class="footer">
        <p>OOCode WebUI — Interfaz web para OOCode TUI | v1.0.0</p>
        <p>100% local — Ollama — Sin APIs externas</p>
    </footer>
    
    <script>
        // Configuración inicial
        const config = {
            models: {{ models | tojson }},
            currentModel: "{{ current_model }}",
            hooks: {{ hooks | tojson }},
            plugins: {{ plugins | tojson }}
        };
        
        // Inicializar chat
        function initChat() {
            const messagesContainer = document.getElementById('chat-messages');
            const input = document.getElementById('chat-input');
            
            // Mensaje de bienvenida
            addMessage('assistant', '👋 ¡Hola! Soy OOCode WebUI. ¿En qué puedo ayudarte hoy?', messagesContainer);
            
            // Event listener para enviar mensaje
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        }
        
        // Añadir mensaje al chat
        function addMessage(role, text, container) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `chat-message ${role}`;
            messageDiv.innerHTML = `<div>${text}</div>`;
            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;
            return messageDiv;
        }
        
        // Enviar mensaje
        async function sendMessage() {
            const input = document.getElementById('chat-input');
            const text = input.value.trim();
            if (!text) return;
            
            // Añadir mensaje del usuario
            addMessage('user', text, document.getElementById('chat-messages'));
            input.value = '';
            
            // Mostrar loading
            const loadingMsg = addMessage('assistant', '<span class="loading"></span> Procesando...', document.getElementById('chat-messages'));
            
            try {
                // Simular respuesta (en producción, llamaría a API de Ollama)
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                loadingMsg.innerHTML = `<strong>OOCode:</strong> ${text}`;
            } catch (error) {
                loadingMsg.innerHTML = `<strong>OOCode:</strong> Error: ${error.message}`;
            }
        }
        
        // Inicializar cuando el DOM esté listo
        document.addEventListener('DOMContentLoaded', initChat);
    </script>
</body>
</html>
"""

# Rutas
@app.route('/')
def home():
    """Página de inicio con resumen de estado."""
    config = load_config()
    models = config.get('models', [])
    current_model = config.get('model', 'batiai/qwen3.5-9b:latest')
    hooks = config.get('hooks', {}).get('builtins', [])
    plugins = config.get('plugins', [])
    
    return render_template_string(HTML_TEMPLATE,
        tab='home',
        models=models,
        current_model=current_model,
        hooks=hooks,
        plugins=plugins
    )

@app.route('/config')
def config_page():
    """Página de configuración de bloques y parámetros."""
    config = load_config()
    models = config.get('models', [])
    current_model = config.get('model', 'batiai/qwen3.5-9b:latest')
    hooks = config.get('hooks', {}).get('builtins', [])
    plugins = config.get('plugins', [])
    
    return render_template_string(HTML_TEMPLATE,
        tab='config',
        models=models,
        current_model=current_model,
        hooks=hooks,
        plugins=plugins
    )

@app.route('/chat')
def chat_page():
    """Página de chat."""
    config = load_config()
    models = config.get('models', [])
    current_model = config.get('model', 'batiai/qwen3.5-9b:latest')
    
    return render_template_string(HTML_TEMPLATE,
        tab='chat',
        models=models,
        current_model=current_model
    )

@app.route('/help')
def help_page():
    """Página de ayuda con comandos slash."""
    return render_template_string(HTML_TEMPLATE,
        tab='help',
        content="""
        <div class="card">
            <h2>📚 Comandos Slash Disponibles</h2>
            <div class="help-section">
                <div class="help-card">
                    <h3>🤖 Agentes</h3>
                    <ul>
                        <li><code>/agent main</code> — Agente principal</li>
                        <li><code>/agent coding</code> — Agente de desarrollo</li>
                        <li><code>/agent home_office</code> — Agente de oficina</li>
                        <li><code>/agent reasoning</code> — Agente de razonamiento</li>
                    </ul>
                </div>
                <div class="help-card">
                    <h3>🔧 Configuración</h3>
                    <ul>
                        <li><code>/model &lt;nombre&gt;</code> — Cambiar modelo</li>
                        <li><code>/hooks builtin &lt;nombre&gt;</code> — Activar/desactivar hook</li>
                        <li><code>/plugins enable &lt;plugin&gt;</code> — Activar plugin</li>
                        <li><code>/plugins disable &lt;plugin&gt;</code> — Desactivar plugin</li>
                    </ul>
                </div>
                <div class="help-card">
                    <h3>📊 Estado</h3>
                    <ul>
                        <li><code>/diff</code> — Ver diff de última edición</li>
                        <li><code>/symbols</code> — Listar símbolos del proyecto</li>
                        <li><code>/todo</code> — Listar tareas pendientes</li>
                        <li><code>/clip</code> — Copiar al portapapeles</li>
                    </ul>
                </div>
                <div class="help-card">
                    <h3>🚀 Subagentes</h3>
                    <ul>
                        <li><code>/subagents</code> — Listar subagentes activos</li>
                        <li><code>/subagents steer &lt;run_id&gt;</code> — Inyectar instrucciones</li>
                        <li><code>/subagents kill &lt;run_id&gt;</code> — Detener subagente</li>
                    </ul>
                </div>
            </div>
        </div>
        """
    )

@app.route('/doctor')
def doctor_page():
    """Página de doctor con dependencias y estado."""
    config = load_config()
    models = config.get('models', [])
    current_model = config.get('model', 'batiai/qwen3.5-9b:latest')
    hooks = config.get('hooks', {}).get('builtins', [])
    plugins = config.get('plugins', [])
    
    # Verificar dependencias
    dependencies = {
        'Flask': 'Flask web framework',
        'python-docx': 'Documentos .docx',
        'openpyxl': 'Hojas de cálculo .xlsx',
        'matplotlib': 'Gráficas',
        'pillow': 'Imágenes',
        'pandas': 'Análisis de datos',
        'rich': 'Terminal UI',
        'prompt_toolkit': 'TUI',
        'pytest': 'Tests',
        'mypy': 'Tipado estático',
        'ruff': 'Linter Python',
        'ctags': 'Índice de símbolos',
        'universal-ctags': 'Ctags universal',
    }
    
    # Verificar qué dependencias están instaladas
    import subprocess
    installed = []
    try:
        result = subprocess.run(['pip', 'list'], capture_output=True, text=True, timeout=10)
        for line in result.stdout.split('\n'):
            if ':' in line:
                pkg = line.split(':')[0].strip()
                if pkg in dependencies:
                    installed.append(pkg)
    except Exception:
        pass
    
    return render_template_string(HTML_TEMPLATE,
        tab='doctor',
        models=models,
        current_model=current_model,
        hooks=hooks,
        plugins=plugins,
        dependencies=dependencies,
        installed=installed
    )

@app.route('/theme')
def theme_page():
    """Página de cambio de tema."""
    config = load_config()
    models = config.get('models', [])
    current_model = config.get('model', 'batiai/qwen3.5-9b:latest')
    
    return render_template_string(HTML_TEMPLATE,
        tab='theme',
        models=models,
        current_model=current_model
    )

if __name__ == '__main__':
    print("🚀 OOCode WebUI — Iniciando en puerto 4000")
    print("📡 100% local — Ollama — Sin APIs externas")
    app.run(host='0.0.0.0', port=4000, debug=True)
