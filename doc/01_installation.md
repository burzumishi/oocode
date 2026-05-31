# 01 — Instalación y requisitos

## Requisitos del sistema

| Componente | Versión mínima | Notas |
|------------|---------------|-------|
| Python | 3.10+ | Necesario para `match`, `|` en tipos |
| Ollama | 0.4+ | Servidor local de inferencia |
| RAM | 8 GB | 16 GB recomendados para modelos 9B+ |
| Disco | 5–30 GB | Para los modelos GGUF |

## Instalación de Ollama

```bash
# Linux / macOS
curl -fsSL https://ollama.com/install.sh | sh

# Arrancar el servidor
ollama serve

# Servidor disponible en toda la red local
OLLAMA_HOST=0.0.0.0 ollama serve
```

## Descarga de modelos recomendados

```bash
# Recomendado: mejor equilibrio calidad/velocidad/contexto (16 GB VRAM)
ollama pull qwen3.5:9b

# Alternativa para 8 GB VRAM
ollama pull qwen2.5-coder:7b
ollama pull qwen3.5:4b

# Razonamiento extendido
ollama pull deepseek-r1:8b

# Modelo de embeddings (memoria semántica y RAG — necesario para /mem y /rag)
ollama pull nomic-embed-text-v2-moe
```

Los modelos deben soportar **tool calling** nativo. Verifica con:
```bash
ollama show qwen3.5:9b | grep -i tool
```

## Instalación de OOCode

### Opción 1 — Instalador (recomendada)

```bash
git clone https://github.com/burzumishi/oocode
cd oocode
./install.sh
```

El instalador hace todo lo necesario:
1. `pip install -e .` — registra el comando `oocode` en `~/.local/bin/`
2. Crea `~/.oocode/oocode.json` con la configuración por defecto
3. Sincroniza plugins y skills a `~/.oocode/plugins/` y `~/.oocode/skills/`
4. Comprueba herramientas opcionales (git, docker, ctags, ruff, etc.)

Como es una **instalación editable**, `git pull` actualiza OOCode inmediatamente:

```bash
cd /ruta/a/oocode && git pull   # actualiza el código sin reinstalar
```

### Opción 2 — pip manual

```bash
pip install -r requirements.txt
pip install --user -e /ruta/a/oocode
```

Asegúrate de que `~/.local/bin` está en tu `PATH`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Opción 3 — Sin instalar (desde el repo)

```bash
# Añadir el repo al PATH
export PATH="/ruta/a/oocode:$PATH"
oocode

# O ejecutar directamente
python /ruta/a/oocode/oocode.py
```

## Dependencias Python

Gestionadas automáticamente por `pip install -r requirements.txt`:

```
ollama>=0.4.0          # SDK oficial de Ollama
rich>=13.0.0           # Terminal UI: markdown, tablas, spinners
prompt_toolkit>=3.0.0  # REPL interactivo con historial
requests>=2.31.0       # HTTP para web_fetch y SearXNG
beautifulsoup4>=4.12.0 # Parseo HTML para web_fetch
ddgs>=9.0.0            # DuckDuckGo sin API key
pydantic>=2.0.0        # Validación de configuración
pydantic-settings>=2.0.0
pyperclip>=1.8.0       # Portapapeles (/copy)
flask                  # WebUI (puerto 4000)
```

### Dependencias opcionales — Office (home-office-assistant MCP)

```bash
pip install python-docx>=1.0 python-pptx>=1.0 openpyxl>=3.1 matplotlib pillow docxtpl

# Verificar:
python -c "import docx, openpyxl, pptx, matplotlib, docxtpl; print('OK')"
```

### Dependencias opcionales — Vault cifrado

```bash
pip install cryptography   # vault de credenciales SSH/Git/API (AES-Fernet + PBKDF2)
```

### Dependencias opcionales — LSP servers

Instala los servidores LSP según los lenguajes que uses:

```bash
# Python
pip install python-lsp-server[all]       # pylsp

# JavaScript / TypeScript
npm install -g typescript-language-server typescript

# Rust
rustup component add rust-analyzer

# Go
go install golang.org/x/tools/gopls@latest

# C/C++
apt install clangd      # o brew install llvm

# Lua
# Descargar lua-language-server desde https://github.com/LuaLS/lua-language-server

# YAML / JSON / TOML
npm install -g yaml-language-server
npm install -g vscode-langservers-extracted   # JSON
```

## Primer arranque

```bash
# Desde cualquier directorio — OOCode muestra selector si no hay modelo configurado
oocode

# Apuntar a Ollama en red local
oocode --host http://192.168.1.100:11434

# Con modelo predefinido, sin selector
oocode --model qwen3.5:9b

# En el directorio de un proyecto específico
oocode --model qwen3.5:9b /home/user/mi-proyecto

# Agente específico
oocode --agent coding

# Diagnóstico del sistema
oocode --doctor
```

Al primer arranque se crea automáticamente `~/.oocode/oocode.json` con la configuración por defecto.

## Verificar instalación

Desde el REPL de OOCode:
```
/doctor
```

El comando `/doctor` comprueba:
- Conectividad con Ollama y versión
- Disponibilidad del modelo configurado y el de embeddings
- SearXNG (si está configurado)
- Dependencias Python instaladas
- Herramientas externas: git, docker, ruff, ctags, ripgrep, etc.
- LSP servers instalados
- Servidores MCP bundled activos
- Ficheros de configuración y workspaces

## Actualización

```bash
cd /ruta/a/oocode
git pull
# Con pip install -e . no hay que reinstalar — los cambios son inmediatos.
# Si se añadieron nuevas dependencias:
pip install -r requirements.txt --upgrade
```

Los ficheros en `~/.oocode/` (configuración, memoria, sesiones) se conservan entre versiones.

## Despliegue de SearXNG (búsqueda web privada, opcional)

SearXNG elimina la dependencia de DuckDuckGo y permite búsquedas sin rate-limits ni tracking.

```yaml
# docker-compose.searxng.yml
version: "3.8"
services:
  searxng:
    image: searxng/searxng:latest
    ports:
      - "8888:8080"
    volumes:
      - searxng-config:/etc/searxng
    environment:
      - SEARXNG_BASE_URL=http://localhost:8888/
      - SEARXNG_SECRET_KEY=cambiar-por-clave-aleatoria
    restart: unless-stopped
volumes:
  searxng-config:
```

```bash
docker compose -f docker-compose.searxng.yml up -d
```

Configura en `~/.oocode/oocode.json`:
```json
{
  "searxng": {
    "url": "http://localhost:8888",
    "enabled": true,
    "maxResults": 8
  }
}
```

## Estructura de directorios tras la instalación

```
~/.oocode/
├── oocode.json               # configuración principal
├── oocode.json.bak           # backup automático
├── history                   # historial del REPL
│
├── workspace/
│   └── <agent_id>/           # workspace por agente
│       ├── IDENTITY.md       # quién es el agente
│       ├── SOUL.md           # cómo actúa
│       ├── USER.md           # información sobre el usuario
│       ├── AGENTS.md         # guía del workspace y arranque
│       ├── HEARTBEAT.md      # tareas periódicas del agente
│       ├── TOOLS.md          # entorno local y herramientas
│       ├── MEMORY.md         # memoria a largo plazo editable
│       └── memory/           # logs diarios (YYYY-MM-DD.md)
│
├── sessions/
│   └── <agent_id>/           # historial de sesiones (JSONL)
│
├── memory/
│   └── <agent_id>/           # memoria semántica por agente
│       ├── MEMORY.md         # índice de memorias
│       ├── *.md              # ficheros de memoria individual
│       └── *.emb.json        # vectores de embedding
│
└── logs/
    ├── oocode.log            # log rotativo de actividad
    ├── tool_calls.jsonl      # registro de tool calls (si hook activo)
    └── security_audit.log    # auditoría de tools de seguridad
```
