#!/usr/bin/env bash
# OOCode Installer — instala dependencias y el comando 'oocode' accesible globalmente.
#
# Métodos de instalación (en orden de preferencia):
#   1. pip install -e . --user   → comando gestionado por pip, actualizable con git pull
#   2. Symlink en ~/.local/bin   → apunta al wrapper del repo, siempre actualizado
#   3. Symlink en /usr/local/bin → igual, si hay permisos de escritura
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="${HOME}/.oocode"
PLUGINS_SRC="${REPO_DIR}/plugins"
PLUGINS_DST="${CONFIG_DIR}/plugins"
SKILLS_SRC="${REPO_DIR}/skills"
SKILLS_DST="${CONFIG_DIR}/skills"

# ── Colores ───────────────────────────────────────────────────────────────────
_ok()   { printf '  \033[32m✓\033[0m  %s\n' "$*"; }
_info() { printf '  \033[34m→\033[0m  %s\n' "$*"; }
_warn() { printf '  \033[33m⚠\033[0m  %s\n' "$*"; }
_err()  { printf '  \033[31m✗\033[0m  %s\n' "$*"; }

echo ""
echo "  ╔═══════════════════════════════════╗"
echo "  ║   OOCode — Ollama Open Code       ║"
echo "  ║   Instalador v1.1                 ║"
echo "  ╚═══════════════════════════════════╝"
echo ""
_info "Directorio del repo: ${REPO_DIR}"
_info "Configuración:       ${CONFIG_DIR}"
echo ""

# ── Python ────────────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    _err "Python 3 no encontrado. Instala Python 3.10 o superior."
    exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
_ok "Python ${PY_VER} encontrado"

# ── Instalación de dependencias y comando ─────────────────────────────────────
_info "Instalando OOCode y dependencias con pip…"
PIP_INSTALLED=false
PIP_BIN="$(python3 -m site --user-base)/bin"

_pip_install() {
    # 1) intento normal
    if python3 -m pip install -q --user -e "${REPO_DIR}" 2>/dev/null; then
        return 0
    fi
    # 2) Debian/Ubuntu gestionan Python externamente (PEP 668) — reintentar con flag
    if python3 -m pip install -q --user --break-system-packages -e "${REPO_DIR}" 2>/dev/null; then
        return 0
    fi
    return 1
}

if _pip_install; then
    _ok "pip install -e . completado — comando 'oocode' registrado"
    PIP_INSTALLED=true
    if ! command -v oocode &>/dev/null && [[ ":${PATH}:" != *":${PIP_BIN}:"* ]]; then
        _warn "Añade '${PIP_BIN}' a tu PATH:"
        printf "       echo 'export PATH=\"%s:\$PATH\"' >> ~/.bashrc\n" "${PIP_BIN}"
        printf "       source ~/.bashrc\n"
    fi
else
    _warn "pip install falló — instalando solo dependencias…"
    pip_req_ok=false
    python3 -m pip install -q --user -r "${REPO_DIR}/requirements.txt" 2>/dev/null \
        || python3 -m pip install -q --user --break-system-packages \
               -r "${REPO_DIR}/requirements.txt" 2>/dev/null \
        && pip_req_ok=true
    if $pip_req_ok; then
        _ok "Dependencias instaladas (requirements.txt)"
    else
        _warn "Algunos paquetes fallaron — revisa requirements.txt manualmente"
    fi
fi

# ── Directorios de configuración ──────────────────────────────────────────────
_info "Creando estructura de directorios en ${CONFIG_DIR}…"
mkdir -p "${CONFIG_DIR}/plugins" "${CONFIG_DIR}/skills" "${CONFIG_DIR}/memory"
mkdir -p "${CONFIG_DIR}/workspace/main" "${CONFIG_DIR}/workspace/coding" "${CONFIG_DIR}/workspace/reasoning"
_ok "Directorios creados"

# ── Plugins ───────────────────────────────────────────────────────────────────
_info "Sincronizando plugins…"
copied=0; skipped=0
for src in "${PLUGINS_SRC}"/*.py; do
    name="$(basename "${src}")"
    [[ "${name}" == __* ]] && continue
    dst="${PLUGINS_DST}/${name}"
    if [ ! -f "${dst}" ]; then cp "${src}" "${dst}"; copied=$((copied + 1))
    else skipped=$((skipped + 1)); fi
done
_ok "${copied} plugin(s) copiados, ${skipped} ya existían"

# ── Skills ────────────────────────────────────────────────────────────────────
_info "Sincronizando skills…"
copied_s=0; skipped_s=0
for src in "${SKILLS_SRC}"/*.py; do
    name="$(basename "${src}")"
    [[ "${name}" == __* ]] && continue
    [[ "${name}" == "manager.py" ]] && continue
    dst="${SKILLS_DST}/${name}"
    if [ ! -f "${dst}" ]; then cp "${src}" "${dst}"; copied_s=$((copied_s + 1))
    else skipped_s=$((skipped_s + 1)); fi
done
_ok "${copied_s} skill(s) copiadas, ${skipped_s} ya existían"

# ── Configuración por defecto ─────────────────────────────────────────────────
if [ ! -f "${CONFIG_DIR}/oocode.json" ]; then
    _info "Creando configuración por defecto…"
    cat > "${CONFIG_DIR}/oocode.json" << 'EOF'
{
  "ollama": {
    "host": "http://localhost:11434"
  },

  "agents": {
    "defaults": {
      "model": "",
      "workspace": "~/.oocode/workspace/main"
    },
    "list": [
      {
        "id":        "main",
        "name":      "OOCode",
        "emoji":     "🤖",
        "model":     "",
        "workspace": "~/.oocode/workspace/main"
      },
      {
        "id":        "coding",
        "name":      "OOCode Coder",
        "emoji":     "💻",
        "model":     "",
        "workspace": "~/.oocode/workspace/coding"
      },
      {
        "id":        "reasoning",
        "name":      "OOCode Brain",
        "emoji":     "🧠",
        "model":     "",
        "workspace": "~/.oocode/workspace/reasoning"
      }
    ]
  },

  "permissions": {
    "bash":           "ask",
    "write_file":     "ask",
    "edit_file":      "ask",
    "read_file":      "auto",
    "list_dir":       "auto",
    "web_search":     "auto",
    "web_fetch":      "auto",
    "searxng_search": "auto",
    "spawn_subagent": "ask",
    "lint_file":      "auto",
    "lint_project":   "auto",
    "git_status":     "auto",
    "git_diff":       "auto",
    "git_log":        "auto",
    "git_commit":     "ask",
    "git_push":       "ask",
    "git_pull":       "ask",
    "git_add":        "ask",
    "git_branch":     "auto",
    "git_stash":      "ask",
    "git_patch":      "ask",
    "git_clone":      "ask",
    "run_tests":      "ask",
    "test_file":      "ask",
    "todo_list":      "auto",
    "todo_add":       "ask",
    "todo_done":      "auto",
    "todo_sync":      "auto",
    "changelog_today":   "auto",
    "changelog_session": "auto",
    "changelog_week":    "auto"
  },

  "context": {
    "minKeep":             6,
    "compactThreshold":    0.85,
    "maxSummaryChars":     2100,
    "maxToolResultTokens": 2048,
    "autoContinueMax":     8
  },

  "embeddings": {
    "model":               "nomic-embed-text-v2-moe:latest",
    "maxInputChars":       12000,
    "similarityThreshold": 0.30,
    "snippetChars":        800,
    "topK":                3
  },

  "tools": {
    "readFileLinesDefault":   300,
    "readFileLinesWarnLarge": 2000,
    "webFetchMaxChars":       16000,
    "webFetchTimeout":        15,
    "webSearchMaxResults":    5,
    "bashMaxOutputChars":     75000
  },

  "workspace": {
    "maxMemoryLines": 12,
    "maxDailyChars":  400
  },

  "models": {
    "systemOverhead": 4000,
    "configs": {}
  },

  "fallback": {
    "enabled":        false,
    "model":          "",
    "timeoutSeconds": 120
  },

  "searxng": {
    "url":        "",
    "enabled":    false,
    "maxResults": 5,
    "categories": "general",
    "language":   "auto",
    "safeSearch": 0,
    "timeout":    10
  },

  "logging": {
    "enabled":   true,
    "file":      "",
    "level":     "info",
    "maxSizeMb": 5,
    "maxFiles":  3
  },

  "appearance": {
    "accentColor": "cyan"
  },

  "plugins": {
    "enabled": ["diff", "git"]
  },

  "skills": {
    "enabled": []
  },

  "pluginOptions": {
    "linter": { "auto": true, "maxOutput": 4000, "timeout": 30 },
    "git":    { "autostage": false, "showDiff": true }
  }
}
EOF
    _ok "Configuración creada en ${CONFIG_DIR}/oocode.json"
else
    _info "Configuración existente — sin cambios (${CONFIG_DIR}/oocode.json)"
fi

# ── Symlink si pip no lo instaló ──────────────────────────────────────────────
if [ "${PIP_INSTALLED}" != "true" ]; then
    _info "Instalando comando 'oocode' via symlink…"
    chmod +x "${REPO_DIR}/oocode"

    LOCAL_BIN="${HOME}/.local/bin"
    mkdir -p "${LOCAL_BIN}" 2>/dev/null || true

    if [ -d "${LOCAL_BIN}" ]; then
        ln -sf "${REPO_DIR}/oocode" "${LOCAL_BIN}/oocode"
        _ok "Symlink creado: ${LOCAL_BIN}/oocode → ${REPO_DIR}/oocode"
        if [[ ":${PATH}:" != *":${LOCAL_BIN}:"* ]]; then
            _warn "${LOCAL_BIN} no está en tu PATH. Añádelo:"
            printf "       echo 'export PATH=\"%s:\$PATH\"' >> ~/.bashrc && source ~/.bashrc\n" "${LOCAL_BIN}"
        fi
    elif [ -w "/usr/local/bin" ]; then
        ln -sf "${REPO_DIR}/oocode" "/usr/local/bin/oocode"
        _ok "Symlink creado: /usr/local/bin/oocode → ${REPO_DIR}/oocode"
    else
        _warn "No se pudo instalar el symlink. Ejecuta manualmente:"
        printf "       sudo ln -sf %s/oocode /usr/local/bin/oocode\n" "${REPO_DIR}"
    fi
fi

# ── Ollama ────────────────────────────────────────────────────────────────────
echo ""
if command -v ollama &>/dev/null; then
    _ok "Ollama encontrado: $(ollama --version 2>/dev/null | head -1)"
else
    _warn "Ollama no encontrado — instálalo desde https://ollama.com"
    printf "       curl -fsSL https://ollama.com/install.sh | sh\n"
    printf "       ollama pull qwen3.5:9b\n"
    printf "       ollama pull nomic-embed-text-v2-moe\n"
fi

# ── Herramientas opcionales ───────────────────────────────────────────────────
echo ""
_info "Comprobando herramientas opcionales…"

command -v git    &>/dev/null && _ok  "git encontrado (plugin 'git')"       || _warn "git no encontrado — plugin 'git' no funcionará"
command -v docker &>/dev/null && _ok  "docker encontrado (plugin 'docker')" || _warn "docker no encontrado — plugin 'docker' no funcionará"

if command -v ctags &>/dev/null; then
    _ok "ctags encontrado (plugin 'ctags')"
else
    _warn "ctags no encontrado — sudo apt install universal-ctags"
fi

if command -v wl-copy &>/dev/null; then
    _ok "wl-copy encontrado (plugin 'clipboard' — Wayland)"
elif command -v xclip &>/dev/null || command -v xsel &>/dev/null; then
    _ok "xclip/xsel encontrado (plugin 'clipboard' — X11)"
else
    _warn "Sin portapapeles (Wayland: apt install wl-clipboard / X11: apt install xclip)"
fi

if command -v ruff &>/dev/null; then
    _ok "ruff encontrado (plugin 'linter' — Python)"
elif command -v pylint &>/dev/null; then
    _ok "pylint encontrado (plugin 'linter' — Python)"
else
    _warn "Sin linter Python — pip install ruff (plugin 'linter')"
fi

python3 -c "import cryptography" &>/dev/null \
    && _ok  "cryptography encontrado (plugin 'vault')" \
    || _warn "cryptography no encontrado — pip install cryptography"

python3 -c "import tree_sitter" &>/dev/null \
    && _ok  "tree-sitter encontrado (plugin 'tree_sitter')" \
    || _warn "tree-sitter no encontrado — pip install tree-sitter"

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo "  ──────────────────────────────────────────"
_ok "Instalación completada"
echo ""
echo "  Uso desde cualquier directorio:"
echo "    oocode                            Inicia OOCode"
echo "    oocode --host http://IP:11434     Ollama en red local"
echo "    oocode --model qwen3.5:9b         Modelo específico"
echo "    oocode /ruta/al/proyecto          Workspace del proyecto"
echo "    oocode --agent coding             Agente 'coding'"
echo ""
echo "  Actualizar (los cambios se aplican al instante):"
echo "    cd ${REPO_DIR} && git pull"
echo ""
echo "  Plugins disponibles (/plugins enable <nombre>):"
echo "    diff, git, docker, changelog, linter, test_runner,"
echo "    ctags, tree_sitter, embeddings_search, todo, clipboard, searxng, vault"
echo ""
echo "  /doctor — diagnóstico completo de la instalación"
echo ""
