"""LSP client: JSON-RPC 2.0 sobre stdio con framing Content-Length.

I/O no bloqueante: un hilo daemon lee stdout del servidor y deposita
mensajes en una queue. _request() usa queue.get(timeout=) en lugar de
readline() directo — evita bloqueos si el servidor no responde.

Race-condition del pool corregida: el lock se mantiene durante todo
el ciclo create+start+store.
"""
import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

import agent.logger as log

_DEFAULT_TIMEOUT = 10.0   # segundos máximos esperando respuesta del servidor

# Config de efm-langserver gestionada por OOCode (propósito general / fallback)
_EFM_CONFIG_PATH = Path.home() / ".oocode" / "efm-langserver.yaml"

# Linter Python para formatos de oficina — usado como backend de efm-langserver
_OFFICE_LINTER = Path(__file__).parent.parent / "tools" / "office_linter.py"


def _generate_efm_config() -> str:
    """Genera la config de efm-langserver con los linters instalados en el sistema.

    Solo incluye secciones para lenguajes cuyo servidor LSP ES efm-langserver
    (xml, md, rst, tex, dockerfile, tf, spec, office). Las extensiones con servidor
    LSP dedicado (pylsp, typescript-language-server, clangd, etc.) se omiten porque
    efm nunca sería invocado para ellas.
    """
    lines = [
        "version: 2",
        "root-markers:",
        "  - .git",
        "  - .hg",
        "languages:",
    ]
    has_lang = False

    # ── XML / SVG / XSL — efm es el servidor LSP para .xml/.xsl/.xslt/.svg ──
    if shutil.which("xmllint"):
        has_lang = True
        for lang in ("xml", "xsl", "xslt", "svg"):
            lines += [
                f"  {lang}:",
                "    - lint-command: 'xmllint --noout 2>&1 {input}'",
                "      lint-stdin: false",
                "      lint-formats:",
                "        - '%f:%l: %m'",
                "        - '%f:%l:%c: %m'",
            ]

    # ── Markdown / prose — efm es el servidor LSP para .md/.markdown ───────
    if shutil.which("markdownlint"):
        has_lang = True
        lines += [
            "  markdown:",
            "    - lint-command: 'markdownlint {input}'",
            "      lint-stdin: false",
            "      lint-formats:",
            "        - '%f:%l:%c %m'",
            "        - '%f:%l %m'",
        ]
    if shutil.which("vale"):
        has_lang = True
        _has_md = shutil.which("markdownlint")
        if not _has_md:
            lines.append("  markdown:")
        lines += [
            "    - lint-command: 'vale --output=line {input}'",
            "      lint-stdin: false",
            "      lint-formats:",
            "        - '%f:%l:%c: %m'",
        ]
    if shutil.which("proselint"):
        has_lang = True
        if not shutil.which("markdownlint") and not shutil.which("vale"):
            lines.append("  markdown:")
        lines += [
            "    - lint-command: 'proselint {input}'",
            "      lint-stdin: false",
            "      lint-formats:",
            "        - '%f:%l:%c: %m'",
        ]

    # ── reStructuredText ─────────────────────────────────────────────────────
    if shutil.which("rstcheck"):
        has_lang = True
        lines += [
            "  rst:",
            "    - lint-command: 'rstcheck {input}'",
            "      lint-stdin: false",
            "      lint-formats:",
            "        - '%f:%l: %m'",
            "        - '%f:%l:%c: %m'",
        ]

    # ── LaTeX ─────────────────────────────────────────────────────────────────
    if shutil.which("chktex"):
        has_lang = True
        for lang in ("latex", "tex"):
            lines += [
                f"  {lang}:",
                "    - lint-command: 'chktex -q -v0 {input}'",
                "      lint-stdin: false",
                "      lint-formats:",
                "        - '%f:%l:%c: %m'",
            ]

    # ── Dockerfile ───────────────────────────────────────────────────────────
    if shutil.which("hadolint"):
        has_lang = True
        lines += [
            "  dockerfile:",
            "    - lint-command: 'hadolint --format tty {input}'",
            "      lint-stdin: false",
            "      lint-formats:",
            "        - '%f:%l %t%n: %m'",
        ]

    # ── Terraform / HCL ──────────────────────────────────────────────────────
    if shutil.which("tflint"):
        has_lang = True
        lines += [
            "  terraform:",
            "    - lint-command: 'tflint --format=compact {input}'",
            "      lint-stdin: false",
            "      lint-formats:",
            "        - '%f:%l:%c: %m'",
        ]

    # ── RPM spec — efm es el servidor LSP para .spec ─────────────────────────
    if shutil.which("rpmlint"):
        has_lang = True
        lines += [
            "  spec:",
            "    - lint-command: 'rpmlint {input}'",
            "      lint-stdin: false",
            "      lint-formats:",
            "        - '%f: W: %m'",
            "        - '%f: E: %m'",
        ]

    # ── Git commit messages ───────────────────────────────────────────────────
    if shutil.which("gitlint"):
        has_lang = True
        lines += [
            "  git-commit:",
            "    - lint-command: 'gitlint'",
            "      lint-stdin: true",
            "      lint-formats:",
            "        - '%l: %m'",
        ]

    # ── Office formats via office_linter.py ──────────────────────────────────
    # Siempre disponible si Python 3 está en PATH (libs opcionales: python-docx, openpyxl)
    if shutil.which("python3") and _OFFICE_LINTER.exists():
        has_lang = True
        _linter_cmd = f"python3 {_OFFICE_LINTER} {{input}}"
        _office_fmt = [
            "      lint-stdin: false",
            "      lint-formats:",
            "        - '%f:%l:%c: error: %m'",
            "        - '%f:%l:%c: warning: %m'",
            "        - '%f:%l:%c: information: %m'",
        ]
        for _lang in ("docx", "xls", "xlsx", "csv", "pdf", "odt"):
            lines += [f"  {_lang}:", f"    - lint-command: '{_linter_cmd}'"] + _office_fmt

    if not has_lang:
        lines.append("  {}")

    return "\n".join(lines) + "\n"


def _ensure_efm_config(force: bool = False) -> None:
    """Crea o actualiza la config de efm-langserver en ~/.oocode/efm-langserver.yaml.

    Regenera el fichero si el contenido generado difiere del almacenado, de forma
    que herramientas instaladas después del primer arranque se incorporen automáticamente.
    """
    try:
        _EFM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        generated = _generate_efm_config()
        existing = _EFM_CONFIG_PATH.read_text() if _EFM_CONFIG_PATH.exists() else ""
        if force or existing != generated:
            _EFM_CONFIG_PATH.write_text(generated)
    except Exception:
        pass  # Si falla, efm-langserver usará su config por defecto


# Servidores soportados: extensión → comando
_SERVER_CMDS: dict[str, list[str]] = {
    ".py":    ["pylsp"],
    ".js":    ["typescript-language-server", "--stdio"],
    ".ts":    ["typescript-language-server", "--stdio"],
    ".jsx":   ["typescript-language-server", "--stdio"],
    ".tsx":   ["typescript-language-server", "--stdio"],
    ".go":    ["gopls"],
    ".rs":    ["rust-analyzer"],
    ".c":     ["clangd", "--background-index", "--clang-tidy=false", "--log=error"],
    ".cpp":   ["clangd", "--background-index", "--clang-tidy=false", "--log=error"],
    ".cc":    ["clangd", "--background-index", "--clang-tidy=false", "--log=error"],
    ".h":     ["clangd", "--background-index", "--clang-tidy=false", "--log=error"],
    ".hpp":   ["clangd", "--background-index", "--clang-tidy=false", "--log=error"],
    ".java":  ["jdtls"],
    ".rb":    ["ruby-lsp"],
    # C# — csharp-ls (dotnet tool install -g csharp-ls)
    # OmniSharp ya no se mantiene activamente; csharp-ls es el sucesor ligero
    ".cs":    ["csharp-ls"],
    ".kt":    ["kotlin-language-server"],
    ".swift": ["sourcekit-lsp"],
    ".lua":   ["lua-language-server"],
    ".sh":    ["bash-language-server", "start"],
    # .mk son Makefile fragments (reglas/variables Make), NO CMake.
    # Se usa bash-language-server como aproximación; no existe servidor LSP
    # dedicado para Makefile. Nota: "Makefile" (sin extensión) no puede
    # mapearse por extensión — requeriría detección por nombre de fichero.
    ".mk":    ["bash-language-server", "start"],
    ".json":  ["vscode-json-language-server", "--stdio"],
    ".yaml":  ["yaml-language-server", "--stdio"],
    ".yml":   ["yaml-language-server", "--stdio"],
    ".pl":    ["perl-language-server"],
    ".pm":    ["perl-language-server"],
    ".sql":   ["sql-language-server", "up", "--method", "stdio"],
    # cmake-language-server@0.1.11 roto con pygls v2 (API incompatible) — sin LSP cmake disponible
    # ".cmake": ["cmake-language-server"],
    ".css":   ["vscode-css-language-server", "--stdio"],
    ".scss":  ["vscode-css-language-server", "--stdio"],
    ".less":  ["vscode-css-language-server", "--stdio"],
    ".html":  ["vscode-html-language-server", "--stdio"],
    ".toml":  ["taplo", "lsp", "stdio"],
    ".php":   ["intelephense", "--stdio"],
    # Markdown — efm-langserver con markdownlint como backend
    # vscode-markdown-language-server@4.10.0 roto en Node 22 (ESM vscode-uri incompatible)
    ".md":       ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".markdown": ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    # XML, SVG, XSL — efm-langserver como LSP de propósito general con xmllint como backend
    # efm-langserver config generada automáticamente en ~/.oocode/efm-langserver.yaml
    # apt install efm-langserver  (o go install github.com/mattn/efm-langserver@latest)
    ".xml":   ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".xsl":   ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".xslt":  ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".svg":   ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    # RPM spec — efm-langserver con rpmlint
    ".spec":  ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    # ── Formatos de oficina — efm-langserver con office_linter.py ────────────
    # Proporciona: diagnósticos (campos sin rellenar, errores de fórmula,
    # PDFs corruptos, CSV malformados). Requiere efm-langserver + Python 3.
    # Deps opcionales: python-docx (.docx), openpyxl (.xlsx), pdftotext (.pdf)
    ".docx":  ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".xlsx":  ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".xls":   ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".csv":   ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".pdf":   ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".odt":   ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".ods":   ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    # ── Nuevos formatos vía efm-langserver ────────────────────────────────────
    # reStructuredText (rstcheck), LaTeX (chktex), Dockerfile (hadolint), Terraform (tflint)
    ".rst":        ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".tex":        ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".latex":      ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".dockerfile": ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".tf":         ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
    ".tfvars":     ["efm-langserver", "-c", str(_EFM_CONFIG_PATH)],
}

_EXT_TO_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascriptreact", ".tsx": "typescriptreact",
    ".go": "go", ".rs": "rust", ".c": "c", ".cpp": "cpp",
    ".cc": "cpp", ".h": "c", ".hpp": "cpp", ".hh": "cpp", ".cxx": "cpp",
    ".java": "java",
    ".rb": "ruby", ".cs": "csharp", ".kt": "kotlin",
    ".swift": "swift", ".lua": "lua", ".sh": "shellscript",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".pl": "perl", ".pm": "perl",
    ".sql": "sql",
    ".cmake": "cmake", ".mk": "make",
    ".css": "css", ".scss": "scss", ".less": "less",
    ".html": "html", ".toml": "toml", ".php": "php",
    ".md": "markdown", ".markdown": "markdown",
    ".xml": "xml", ".xsl": "xml", ".xslt": "xml", ".svg": "xml",
    ".spec": "spec",
    # Office formats
    ".docx": "docx", ".doc": "docx", ".dotx": "docx", ".docm": "docx",
    ".xlsx": "xlsx", ".xlsm": "xlsx", ".xltx": "xlsx",
    ".xls":  "xls",
    ".csv":  "csv",
    ".pdf":  "pdf",
    ".odt":  "odt",  ".ods": "ods",
    # Nuevos formatos vía efm-langserver
    ".rst":        "rst",
    ".tex":        "latex",  ".latex": "latex",
    ".dockerfile": "dockerfile",
    ".tf":         "terraform",  ".tfvars": "terraform",
}

# Extensiones que comparten el servidor LSP de otra extensión canónica.
# Evita lanzar N procesos clangd para .c/.h/.cpp/.hpp — todos usan el mismo.
_SERVER_ALIASES: dict[str, str] = {
    # C/C++ headers y variantes comparten el clangd de su primario
    ".h":   ".c",
    ".hpp": ".cpp",
    ".hh":  ".cpp",
    ".cc":  ".cpp",
    ".cxx": ".cpp",
    # TypeScript server sirve también a JSX/TSX
    ".jsx": ".js",
    ".tsx": ".ts",
    # CSS server sirve SCSS y LESS
    ".scss": ".css",
    ".less": ".css",
    # YAML server sirve .yml
    ".yml": ".yaml",
    # Perl modules comparten servidor con .pl
    ".pm":  ".pl",
    # Markdown — .markdown comparte servidor con .md
    ".markdown": ".md",
    # Office — variantes y formatos legacy comparten el mismo servidor
    ".doc":   ".docx",   # Word 97-2003 — misma lógica de diagnóstico
    ".dotx":  ".docx",   # Plantilla Word
    ".docm":  ".docx",   # Word con macros
    ".xls":   ".xlsx",   # Excel legado — mismo servidor efm
    ".xlsm":  ".xlsx",   # Excel con macros
    ".xltx":  ".xlsx",   # Plantilla Excel
    ".ods":   ".odt",    # Hoja de cálculo ODF — efm + office_linter
    # XML — variantes comparten efm-langserver con .xml
    ".xsl":  ".xml",
    ".xslt": ".xml",
    ".svg":  ".xml",
    # Terraform — .tfvars comparte servidor con .tf
    ".tfvars": ".tf",
    # LaTeX — .latex comparte servidor con .tex
    ".latex": ".tex",
}


def _ext(path: str) -> str:
    return Path(path).suffix.lower()


def _which(cmd: str) -> bool:
    return bool(shutil.which(cmd))


class LspError(Exception):
    pass


class LspClient:
    """Cliente JSON-RPC para un servidor LSP concreto.

    El hilo _reader_thread lee mensajes del proceso LSP en segundo plano
    y los encola en _msg_queue. _request() consume la cola con timeout.
    """

    def __init__(self, cmd: list[str], workspace: str,
                 request_timeout: float = _DEFAULT_TIMEOUT):
        self._cmd             = cmd
        self._workspace       = Path(workspace).expanduser().resolve()
        self._timeout         = request_timeout
        self._proc:           Optional[subprocess.Popen] = None
        self._req_id          = 0
        self._id_lock         = threading.Lock()
        self._send_lock       = threading.Lock()   # serializa escrituras a stdin
        self._msg_queue:      queue.Queue = queue.Queue()
        self._reader_thread:  Optional[threading.Thread] = None
        self._started         = False
        self._dead            = False              # True si el proceso terminó
        self._open_files:     dict[str, int] = {}  # URI → version (1-based, incrementa en didChange)
        self._diag_cache:     dict[str, list] = {}  # URI → última lista de diagnósticos
        self._req_sent:       int   = 0             # peticiones enviadas
        self._req_errors:     int   = 0             # respuestas con error o timeout
        self._last_used:      float = 0.0           # monotonic timestamp del último request

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._started:
            return
        self._proc = subprocess.Popen(
            self._cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=str(self._workspace),
            start_new_session=True,
        )
        self._started = True
        self._dead    = False
        # Hilo daemon que lee stdout del servidor LSP
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name=f"lsp-reader-{self._cmd[0]}",
        )
        self._reader_thread.start()
        self._initialize()
        log.debug("lsp_started", cmd=self._cmd[0], workspace=str(self._workspace))

    def stop(self) -> None:
        if not self._started or self._proc is None:
            return
        self._started = False
        self._dead    = True
        try:
            self._send_notification("exit", {})
        except Exception:
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=3)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        # Desbloquear cualquier _request que esté esperando
        self._msg_queue.put(None)
        self._open_files.clear()
        self._diag_cache.clear()
        log.debug("lsp_stopped", cmd=self._cmd[0])

    @property
    def is_alive(self) -> bool:
        return (self._started and not self._dead
                and self._proc is not None
                and self._proc.poll() is None)

    # ── Lector de stdout (hilo daemon) ────────────────────────────────────────

    def _reader_loop(self) -> None:
        """Lee mensajes Content-Length del proceso LSP y los encola."""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while True:
                # Leer cabeceras hasta línea en blanco
                headers: dict[str, str] = {}
                while True:
                    raw = proc.stdout.readline()
                    if not raw:          # EOF → proceso terminó
                        self._dead = True
                        self._msg_queue.put(None)
                        return
                    line = raw.decode(errors="replace").strip()
                    if not line:
                        break
                    if ":" in line:
                        k, _, v = line.partition(":")
                        headers[k.strip().lower()] = v.strip()

                length = int(headers.get("content-length", 0))
                if length <= 0:
                    continue
                body = proc.stdout.read(length)
                if not body:
                    self._dead = True
                    self._msg_queue.put(None)
                    return
                try:
                    msg = json.loads(body.decode(errors="replace"))
                    self._msg_queue.put(msg)
                except json.JSONDecodeError:
                    pass
        except Exception:
            self._dead = True
            self._msg_queue.put(None)

    # ── JSON-RPC ──────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        with self._id_lock:
            self._req_id += 1
            return self._req_id

    def _send(self, payload: dict) -> None:
        if not self._started or self._proc is None or self._proc.stdin is None:
            raise LspError("LSP process not running")
        body   = json.dumps(payload, ensure_ascii=False).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        with self._send_lock:
            self._proc.stdin.write(header + body)
            self._proc.stdin.flush()

    def _request(self, method: str, params: dict) -> Optional[dict]:
        if self._dead:
            raise LspError("LSP server died")
        req_id = self._next_id()
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method,
                    "params": params})
        # Consumir mensajes de la queue hasta recibir la respuesta o timeout.
        # Notificaciones (sin "id") se devuelven a la queue para diagnósticos.
        deadline = self._timeout
        pending: list = []
        import time as _time
        self._req_sent  += 1
        self._last_used  = _time.monotonic()
        try:
            t0 = _time.monotonic()
            while True:
                remaining = deadline - (_time.monotonic() - t0)
                if remaining <= 0:
                    self._req_errors += 1
                    break
                try:
                    msg = self._msg_queue.get(timeout=min(remaining, 1.0))
                except queue.Empty:
                    if self._dead:
                        self._req_errors += 1
                        break
                    continue
                if msg is None:              # señal de muerte del proceso
                    self._req_errors += 1
                    break
                if msg.get("id") == req_id:
                    # Devolver notificaciones pendientes a la queue
                    for p in pending:
                        self._msg_queue.put(p)
                    if "error" in msg:
                        self._req_errors += 1
                        raise LspError(f"LSP error: {msg['error']}")
                    return msg.get("result")
                else:
                    pending.append(msg)      # notificación o respuesta ajena
        finally:
            for p in pending:
                self._msg_queue.put(p)
        return None

    def _send_notification(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _initialize(self) -> None:
        params = {
            "processId": os.getpid(),
            "rootUri":   self._workspace.as_uri(),
            "capabilities": {
                "textDocument": {
                    "definition":        {"linkSupport": False},
                    "references":        {},
                    "hover":             {"contentFormat": ["plaintext", "markdown"]},
                    "documentSymbol":    {"hierarchicalDocumentSymbolSupport": False},
                    "publishDiagnostics": {"relatedInformation": False},
                    "completion":        {"completionItem": {"snippetSupport": False}},
                    "rename":            {"prepareSupport": False},
                    "formatting":        {},
                    "typeDefinition":    {},
                    "implementation":    {},
                    "codeAction":        {
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "", "quickfix", "refactor", "refactor.extract",
                                    "refactor.inline", "refactor.rewrite",
                                    "source", "source.organizeImports",
                                ]
                            }
                        }
                    },
                    "callHierarchy":     {},
                },
                "workspace": {
                    "symbol": {},
                    "workspaceFolders": True,
                },
            },
            "workspaceFolders": [
                {"uri": self._workspace.as_uri(), "name": self._workspace.name}
            ],
        }
        result = self._request("initialize", params)
        if result is None:
            raise LspError(f"LSP server '{self._cmd[0]}' no respondió al initialize")
        self._send_notification("initialized", {})

    # ── Gestión de ficheros abiertos ─────────────────────────────────────────

    def _open_file(self, path: str) -> str:
        """Notifica el fichero al servidor. didOpen la primera vez, didChange en
        llamadas sucesivas (el contenido puede haber cambiado entre tool calls)."""
        p   = Path(path).expanduser().resolve()
        uri = p.as_uri()
        try:
            text = p.read_text(errors="replace")
        except Exception:
            text = ""
        lang = _EXT_TO_LANG.get(p.suffix.lower(), "plaintext")
        if uri not in self._open_files:
            self._send_notification("textDocument/didOpen", {
                "textDocument": {"uri": uri, "languageId": lang,
                                 "version": 1, "text": text}
            })
            self._open_files[uri] = 1
        else:
            version = self._open_files[uri] + 1
            self._open_files[uri] = version
            self._send_notification("textDocument/didChange", {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": text}],
            })
        return uri

    def _pos(self, line: int, col: int) -> dict:
        return {"line": max(0, line - 1), "character": max(0, col - 1)}

    # ── API pública ───────────────────────────────────────────────────────────

    def definition(self, path: str, line: int, col: int) -> list[dict]:
        uri = self._open_file(path)
        result = self._request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": self._pos(line, col),
        })
        if not result:
            return []
        if isinstance(result, dict):
            result = [result]
        return [_loc_to_dict(r) for r in result if r]

    def references(self, path: str, line: int, col: int,
                   include_decl: bool = False) -> list[dict]:
        uri = self._open_file(path)
        result = self._request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": self._pos(line, col),
            "context": {"includeDeclaration": include_decl},
        })
        if not result:
            return []
        return [_loc_to_dict(r) for r in result if r]

    def hover(self, path: str, line: int, col: int) -> str:
        uri = self._open_file(path)
        result = self._request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": self._pos(line, col),
        })
        if not result:
            return ""
        contents = result.get("contents", "")
        if isinstance(contents, dict):
            return contents.get("value", "")
        if isinstance(contents, list):
            return "\n".join(
                c.get("value", c) if isinstance(c, dict) else str(c)
                for c in contents
            )
        return str(contents)

    def document_symbols(self, path: str) -> list[dict]:
        uri = self._open_file(path)
        result = self._request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        })
        if not result:
            return []
        return [_sym_to_dict(s) for s in result if s]

    def workspace_symbols(self, query: str) -> list[dict]:
        result = self._request("workspace/symbol", {"query": query})
        if not result:
            return []
        return [_sym_to_dict(s) for s in result if s]

    def diagnostics(self, path: str, wait: float = 2.0) -> list[dict]:
        """Abre el fichero y espera publishDiagnostics del servidor.

        `wait` es el tiempo máximo de espera (por defecto 2s, mucho menor que el
        timeout global de 10s). Si no llega un diagnóstico fresco en ese tiempo
        devuelve los diagnósticos cacheados del turno anterior, o lista vacía.
        """
        import time as _time
        uri = self._open_file(path)
        # diagnostics usa flujo push (notificación → publishDiagnostics), no _request(),
        # así que actualizamos los stats manualmente para que /lsp los refleje.
        self._req_sent  += 1
        self._last_used  = _time.monotonic()
        # Esperar diagnóstico fresco con timeout reducido
        t0      = _time.monotonic()
        limit   = min(wait, self._timeout)
        pending: list = []
        try:
            while _time.monotonic() - t0 < limit:
                remaining = limit - (_time.monotonic() - t0)
                try:
                    msg = self._msg_queue.get(timeout=min(remaining, 0.3))
                except queue.Empty:
                    if self._dead:
                        break
                    continue
                if msg is None:
                    break
                if (msg.get("method") == "textDocument/publishDiagnostics"
                        and msg.get("params", {}).get("uri") == uri):
                    for p in pending:
                        self._msg_queue.put(p)
                    result = [_diag_to_dict(d, path)
                              for d in msg["params"].get("diagnostics", [])]
                    self._diag_cache[uri] = result
                    return result
                else:
                    pending.append(msg)
        finally:
            for p in pending:
                self._msg_queue.put(p)
        # Devolver caché si no llegó diagnóstico fresco
        return self._diag_cache.get(uri, [])

    def completion(self, path: str, line: int, col: int) -> list[dict]:
        """Solicita completions en la posición indicada."""
        uri = self._open_file(path)
        result = self._request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": self._pos(line, col),
            "context":  {"triggerKind": 1},   # Invoked
        })
        if not result:
            return []
        items = result if isinstance(result, list) else result.get("items", [])
        return [
            {
                "label":  item.get("label", ""),
                "kind":   _COMPLETION_KINDS.get(item.get("kind", 0), "Text"),
                "detail": item.get("detail", ""),
                "doc":    (item.get("documentation") or {}).get("value", "")
                          if isinstance(item.get("documentation"), dict)
                          else str(item.get("documentation", "")),
            }
            for item in items[:30]    # limitar a 30 items
        ]

    def rename(self, path: str, line: int, col: int, new_name: str) -> dict:
        """Solicita rename del símbolo. Devuelve {changes: {path: [(old, new)]}}."""
        uri = self._open_file(path)
        result = self._request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": self._pos(line, col),
            "newName":  new_name,
        })
        if not result:
            return {}
        changes: dict[str, list] = {}
        # WorkspaceEdit puede tener .changes (dict uri→edits) o .documentChanges
        doc_changes = result.get("documentChanges", [])
        if doc_changes:
            for dc in doc_changes:
                p = _uri_to_path(dc.get("textDocument", {}).get("uri", ""))
                edits = [
                    {"range": e.get("range"), "newText": e.get("newText", "")}
                    for e in dc.get("edits", [])
                ]
                if edits:
                    changes[p] = edits
        else:
            for u, edits in result.get("changes", {}).items():
                p = _uri_to_path(u)
                changes[p] = [
                    {"range": e.get("range"), "newText": e.get("newText", "")}
                    for e in edits
                ]
        return changes

    def format_document(self, path: str, tab_size: int = 4,
                        insert_spaces: bool = True) -> list[dict]:
        """textDocument/formatting → lista de TextEdit a aplicar."""
        uri = self._open_file(path)
        result = self._request("textDocument/formatting", {
            "textDocument": {"uri": uri},
            "options": {"tabSize": tab_size, "insertSpaces": insert_spaces},
        })
        if not result:
            return []
        return [
            {"range": e.get("range", {}), "newText": e.get("newText", "")}
            for e in result
        ]

    def code_actions(self, path: str, line: int, col: int,
                     end_line: Optional[int] = None,
                     end_col: Optional[int] = None) -> list[dict]:
        """textDocument/codeAction → lista de acciones disponibles en el rango."""
        uri   = self._open_file(path)
        pos   = self._pos(line, col)
        e_pos = self._pos(end_line or line, end_col or col)
        result = self._request("textDocument/codeAction", {
            "textDocument": {"uri": uri},
            "range":   {"start": pos, "end": e_pos},
            "context": {"diagnostics": [], "only": []},
        })
        if not result:
            return []
        actions = []
        for item in result:
            cmd = item.get("command", {})
            actions.append({
                "title":   item.get("title", ""),
                "kind":    item.get("kind", ""),
                "command": cmd.get("command", "") if isinstance(cmd, dict) else "",
            })
        return actions

    def type_definition(self, path: str, line: int, col: int) -> list[dict]:
        """textDocument/typeDefinition → ubicación del tipo del símbolo."""
        uri = self._open_file(path)
        result = self._request("textDocument/typeDefinition", {
            "textDocument": {"uri": uri},
            "position": self._pos(line, col),
        })
        if not result:
            return []
        if isinstance(result, dict):
            result = [result]
        return [_loc_to_dict(r) for r in result if r]

    def implementation(self, path: str, line: int, col: int) -> list[dict]:
        """textDocument/implementation → ubicaciones de implementaciones de la interfaz."""
        uri = self._open_file(path)
        result = self._request("textDocument/implementation", {
            "textDocument": {"uri": uri},
            "position": self._pos(line, col),
        })
        if not result:
            return []
        if isinstance(result, dict):
            result = [result]
        return [_loc_to_dict(r) for r in result if r]

    def prepare_call_hierarchy(self, path: str, line: int, col: int) -> list[dict]:
        """textDocument/prepareCallHierarchy → items de jerarquía de llamadas."""
        uri = self._open_file(path)
        result = self._request("textDocument/prepareCallHierarchy", {
            "textDocument": {"uri": uri},
            "position": self._pos(line, col),
        })
        if not result:
            return []
        return result if isinstance(result, list) else [result]

    def incoming_calls(self, item: dict) -> list[dict]:
        """callHierarchy/incomingCalls → quién llama a este símbolo."""
        result = self._request("callHierarchy/incomingCalls", {"item": item})
        if not result:
            return []
        return result if isinstance(result, list) else [result]

    def outgoing_calls(self, item: dict) -> list[dict]:
        """callHierarchy/outgoingCalls → qué llama este símbolo."""
        result = self._request("callHierarchy/outgoingCalls", {"item": item})
        if not result:
            return []
        return result if isinstance(result, list) else [result]


# ── Pool de clientes LSP ──────────────────────────────────────────────────────

class LspPool:
    """Pool de clientes LSP: uno por extensión de fichero y workspace.

    El lock cubre todo el ciclo create+start+store para evitar la race
    condition donde dos hilos crean el mismo cliente.
    """

    def __init__(self, workspace: str,
                 request_timeout: float = _DEFAULT_TIMEOUT,
                 server_overrides: Optional[dict] = None):
        self._workspace      = workspace
        self._timeout        = request_timeout
        self._cmds           = dict(_SERVER_CMDS)
        if server_overrides:
            self._cmds.update(server_overrides)
        self._clients: dict[str, LspClient] = {}
        self._lock    = threading.Lock()

    def get(self, ext: str) -> Optional[LspClient]:
        # Resolver alias: .h → .c, .hpp → .cpp, .jsx → .js, etc.
        canonical = _SERVER_ALIASES.get(ext, ext)
        with self._lock:
            if canonical in self._clients:
                c = self._clients[canonical]
                if c.is_alive:
                    return c
                # Servidor muerto → limpiar y reintentar
                try:
                    c.stop()
                except Exception:
                    pass
                del self._clients[canonical]

            # Preferir el comando del canónico; si no existe, usar el del alias
            cmd = self._cmds.get(canonical) or self._cmds.get(ext)
            if not cmd or not _which(cmd[0]):
                return None
            # efm-langserver necesita la config generada antes de arrancar
            if cmd[0] == "efm-langserver":
                _ensure_efm_config()
            client = LspClient(cmd, self._workspace, request_timeout=self._timeout)
            try:
                client.start()
                self._clients[canonical] = client
                log.debug("lsp_pool_client_added", ext=canonical, cmd=cmd[0])
                return client
            except Exception as exc:
                log.debug("lsp_start_error", ext=canonical, error=str(exc))
                return None

    def stop_all(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for c in clients:
            try:
                c.stop()
            except Exception:
                pass

    def status(self) -> list[dict]:
        """Devuelve estado de cada cliente activo."""
        import time as _t
        now = _t.monotonic()
        with self._lock:
            return [
                {
                    "ext":      ext,
                    "cmd":      c._cmd[0] if c._cmd else "?",
                    "alive":    c.is_alive,
                    "requests": c._req_sent,
                    "errors":   c._req_errors,
                    "files":    len(c._open_files),
                    "idle_s":   int(now - c._last_used) if c._last_used else None,
                }
                for ext, c in self._clients.items()
            ]

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(1 for c in self._clients.values() if c.is_alive)

    @property
    def active_extensions(self) -> list[str]:
        with self._lock:
            return [ext for ext, c in self._clients.items() if c.is_alive]

    def available_servers(self) -> list[dict]:
        """Devuelve qué servidores están instalados en el sistema."""
        result = []
        seen: set[str] = set()
        for _ext, cmd in self._cmds.items():
            name = cmd[0]
            if name in seen:
                continue
            seen.add(name)
            result.append({
                "name":      name,              # nombre del ejecutable
                "installed": _which(name),
                "exts":      [e for e, c in self._cmds.items() if c[0] == name],
            })
        return result

    def restart(self, ext: str) -> bool:
        """Para y reinicia el cliente de la extensión dada. Devuelve True si OK."""
        canonical = _SERVER_ALIASES.get(ext, ext)
        with self._lock:
            client = self._clients.pop(canonical, None)
        if client:
            try:
                client.stop()
            except Exception:
                pass
        # get() iniciará uno nuevo bajo lock
        return self.get(ext) is not None


# ── Helpers de formato ─────────────────────────────────────────────────────────

def _uri_to_path(uri: str) -> str:
    if uri.startswith("file://"):
        from urllib.parse import unquote
        return unquote(uri[7:])
    return uri


def _loc_to_dict(loc: dict) -> dict:
    r     = loc.get("range", loc.get("targetRange", {}))
    start = r.get("start", {})
    return {
        "path": _uri_to_path(loc.get("uri", loc.get("targetUri", ""))),
        "line": start.get("line", 0) + 1,
        "col":  start.get("character", 0) + 1,
    }


_KIND_NAMES = {
    1: "File", 2: "Module", 3: "Namespace", 4: "Package",
    5: "Class", 6: "Method", 7: "Property", 8: "Field",
    9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
    13: "Variable", 14: "Constant", 15: "String", 16: "Number",
    17: "Boolean", 18: "Array", 19: "Object", 20: "Key",
    21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
    25: "Operator", 26: "TypeParameter",
}

_COMPLETION_KINDS = {
    1: "Text", 2: "Method", 3: "Function", 4: "Constructor", 5: "Field",
    6: "Variable", 7: "Class", 8: "Interface", 9: "Module", 10: "Property",
    11: "Unit", 12: "Value", 13: "Enum", 14: "Keyword", 15: "Snippet",
    16: "Color", 17: "File", 18: "Reference", 19: "Folder", 20: "EnumMember",
    21: "Constant", 22: "Struct", 23: "Event", 24: "Operator", 25: "TypeParameter",
}


def _sym_to_dict(sym: dict) -> dict:
    kind  = _KIND_NAMES.get(sym.get("kind", 0), "Symbol")
    loc   = sym.get("location", {})
    r     = loc.get("range", {})
    start = r.get("start", {})
    return {
        "name":      sym.get("name", ""),
        "kind":      kind,
        "path":      _uri_to_path(loc.get("uri", "")),
        "line":      start.get("line", 0) + 1,
        "container": sym.get("containerName", ""),
    }


_SEV_NAMES = {1: "error", 2: "warning", 3: "information", 4: "hint"}


def _diag_to_dict(diag: dict, path: str) -> dict:
    r     = diag.get("range", {})
    start = r.get("start", {})
    return {
        "path":     path,
        "line":     start.get("line", 0) + 1,
        "col":      start.get("character", 0) + 1,
        "severity": _SEV_NAMES.get(diag.get("severity", 1), "error"),
        "message":  diag.get("message", ""),
        "source":   diag.get("source", ""),
    }
