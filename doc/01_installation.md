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

# Servidor en otra máquina de la red (sin autenticación)
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

# Modelo de embeddings (para memoria semántica — necesario para /mem)
ollama pull nomic-embed-text-v2-moe
```

Los modelos deben soportar **tool calling** nativo. Verifica con:
```bash
ollama show qwen3.5:9b | grep -i tool
```

## Instalación de OOCode

### Opción 1 — Instalador (recomendada)

```bash
git clone https://github.com/tu-usuario/oocode
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
cd /ruta/a/oocode && git pull   # actualiza el código
# oocode ya usa la nueva versión — sin reinstalar
```

### Opción 2 — pip manual

```bash
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

Gestionadas automáticamente por `pip install -e .`:

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
```

Dependencias opcionales (para plugins específicos):

```bash
pip install cryptography   # plugin 'vault' (credenciales cifradas)
pip install tree-sitter    # plugin 'tree_sitter' (análisis AST)
pip install ruff           # plugin 'linter' (Python)
```

## Primer arranque

```bash
# Desde cualquier directorio — OOCode muestra selector si no hay modelo configurado
oocode

# Apuntar a Ollama en red local
oocode --host http://192.168.1.33:11434

# Con modelo predefinido, sin selector
oocode --model qwen3.5:9b

# En el directorio de un proyecto específico
oocode --model qwen3.5:9b /home/user/mi-proyecto

# Agente específico
oocode --agent coding
```

Al primer arranque se crea automáticamente `~/.oocode/oocode.json` con la configuración por defecto.

## Verificar instalación

Desde el REPL de OOCode:
```
/doctor
```

El comando `/doctor` comprueba:
- Conectividad con Ollama y versión
- Disponibilidad del modelo configurado
- Modelo de embeddings
- SearXNG (si está configurado)
- Dependencias Python
- Herramientas externas (git, docker, ctags, ruff, etc.)
- Ficheros de configuración

## Actualización

```bash
cd /ruta/a/oocode
git pull
# Con pip install -e . no hay que reinstalar — los cambios son inmediatos.
# Si se añadieron nuevas dependencias en requirements.txt:
pip install --user -r requirements.txt --upgrade
```

Los ficheros en `~/.oocode/` (configuración, memoria, sesiones) se conservan entre versiones.

## Configuración de modelos al primer arranque

OOCode muestra un selector interactivo si no hay modelo configurado. Para saltar el selector, configura el modelo en `~/.oocode/oocode.json` bajo `agents.list[].model` o `agents.defaults.model`.

Ver `doc/02_configuration.md` para ejemplos completos por hardware (16 GB, 8 GB VRAM).

## Estructura de directorios tras la instalación

```
~/.oocode/
├── oocode.json           # configuración principal
├── oocode.json.bak       # backup automático
├── history               # historial del REPL
├── plugins/              # plugins activos (sincronizados desde el repo)
├── skills/               # skills activos (sincronizados desde el repo)
├── memory/<agent_id>/    # memoria semántica persistente por agente
│   ├── MEMORY.md         # índice de memorias
│   ├── *.md              # ficheros de memoria individual
│   └── *.emb.json        # vectores de embedding
├── workspace/<agent_id>/ # contexto de workspace por agente
├── sessions/<agent_id>/  # historial de sesiones (JSONL)
└── logs/oocode.log       # log rotativo de actividad
```
