"""Sistema de hooks PreToolUse / PostToolUse.

Permite registrar callbacks que se ejecutan antes y después de cada tool call.

Pre-hooks:  fn(tool_name, args) → args modificados | None (cancela la ejecución)
Post-hooks: fn(tool_name, args, result) → result modificado | None (usa el original)

Los hooks se registran con un patrón de nombre (str exacto o "*" para todos).
Se ejecutan en orden de registro. Si un pre-hook devuelve None, la tool no se ejecuta
y se devuelve "Cancelado por hook pre-tool."

Built-in hooks disponibles (activar via config hooks.builtins):
  diff_after_write          — renderiza diff visual con colores tras edit_file/write_file
  lsp_after_write           — diagnósticos LSP automáticos tras escribir .py/.c/.cpp/etc.
  ctags_after_write         — reindexea símbolos (ctags) tras edit_file/write_file
  lint_after_write          — linting automático tras write_file/edit_file/edit_files
  quick_syntax_after_write  — verifica sintaxis Python (ast) instantáneamente tras escribir .py
  autoformat_after_write    — formatea via LSP tras escribir código
  backup_before_write       — copia .bak antes de modificar; elimina .bak si la escritura tiene éxito
  check_secrets             — bloquea write_file si detecta credenciales en el contenido
  log_tool_calls            — registra tool calls de escritura en ~/.oocode/logs/tool_calls.jsonl (rot. 2MB×3)
  todo_scan_after_write     — muestra TODO/FIXME/HACK/XXX encontrados en ficheros modificados
  test_after_write          — ejecuta pytest del test file asociado al .py modificado (30s timeout)
  size_check_after_write    — avisa si un fichero supera 300 líneas o 15 KB tras escribirlo
  verify_after_edit         — re-lee la sección modificada tras edit_file (±2 líneas contexto con ▶)
"""
import fnmatch
import re as _re
import shutil as _shutil
from typing import Callable, Any, Optional


PreHookFn  = Callable[[str, dict], Optional[dict]]   # (name, args) → args | None
PostHookFn = Callable[[str, dict, str], Optional[str]]  # (name, args, result) → result | None

# ── Redirección TUI: el loop inyecta self._print para que hooks usen el canal ─
# Set by agent/loop.py at the start of each run(); reset to None at end.
_hook_print_fn = None


def set_hook_print_fn(fn) -> None:
    """Configura la función de impresión para hooks (TUI-aware). None = REPL mode."""
    global _hook_print_fn
    _hook_print_fn = fn


def _hprint(markup) -> None:
    """Imprime via el canal de hooks: self._print en TUI, console.print en REPL."""
    fn = _hook_print_fn
    if fn is not None:
        fn(markup)
    else:
        from ui.console import console as _c
        _c.print(markup)


def _is_tui_mode() -> bool:
    """True si el agente está en modo TUI (loop gestiona el diff inline)."""
    return _hook_print_fn is not None


# ── Built-in hooks ────────────────────────────────────────────────────────────

_WRITE_TOOLS = frozenset({"write_file", "edit_file", "edit_files"})
_WRITE_SUFFIXES = frozenset(f"_{n}" for n in _WRITE_TOOLS)

# Conjunto ampliado: incluye también replace/patch tools que modifican ficheros.
# Se usa en hooks de lint/ctags/LSP para activarlos también tras regex_replace etc.
_ALL_MODIFY_TOOLS = _WRITE_TOOLS | frozenset({
    "regex_replace", "smart_replace", "bulk_replace", "patch_apply",
})
_ALL_MODIFY_SUFFIXES = frozenset(f"_{n}" for n in _ALL_MODIFY_TOOLS)


def _is_modify_tool(name: str) -> bool:
    """True si la tool modifica ficheros: write/edit/replace/patch (incluyendo MCP)."""
    return name in _ALL_MODIFY_TOOLS or (
        name.startswith("mcp_") and any(name.endswith(s) for s in _ALL_MODIFY_SUFFIXES)
    )


def _is_write_tool(name: str) -> bool:
    """True si el nombre corresponde a una write-tool (incluyendo prefijos MCP)."""
    return name in _WRITE_TOOLS or (
        name.startswith("mcp_") and any(name.endswith(s) for s in _WRITE_SUFFIXES)
    )

# Último resultado completo de lint — accesible desde ui/app.py (Ctrl+O)
_last_lint_output: str = ""

# Linters disponibles por extensión de fichero
_LINTERS: dict[str, list[list[str]]] = {
    ".py":  [
        ["ruff", "check", "--output-format=concise", "{file}"],
        ["mypy", "--no-error-summary", "--ignore-missing-imports", "{file}"],
    ],
    ".js":  [["eslint", "{file}"]],
    ".ts":  [["eslint", "{file}"]],
    ".jsx": [["eslint", "{file}"]],
    ".tsx": [["eslint", "{file}"]],
    ".sh":  [["shellcheck", "-S", "warning", "{file}"]],
    ".bash":[["shellcheck", "-S", "warning", "{file}"]],
    ".rs":  [["cargo", "check", "--message-format=short"]],
    ".go":  [["go", "vet", "{file}"]],
    # C/C++ — cppcheck análisis estático + splint análisis de seguridad
    ".c":   [["cppcheck", "--enable=warning,style,performance",
               "--error-exitcode=1", "--quiet", "{file}"],
             ["splint", "+posixlib", "+quiet", "{file}"]],
    ".h":   [["cppcheck", "--enable=warning,style",
               "--error-exitcode=1", "--quiet", "{file}"],
             ["splint", "+posixlib", "+quiet", "{file}"]],
    ".cpp": [["cppcheck", "--enable=warning,style,performance",
               "--language=c++", "--error-exitcode=1", "--quiet", "{file}"]],
    ".cc":  [["cppcheck", "--enable=warning,style,performance",
               "--language=c++", "--error-exitcode=1", "--quiet", "{file}"]],
    ".hpp": [["cppcheck", "--enable=warning,style",
               "--language=c++", "--error-exitcode=1", "--quiet", "{file}"]],
    # Ruby — rubocop
    ".rb":  [["rubocop", "--no-color", "--format", "simple", "{file}"]],
    # SQL — sqlfluff
    ".sql": [["sqlfluff", "lint", "--dialect", "ansi", "--format", "default", "{file}"]],
    # Perl — syntax check + perlcritic + B::Lint análisis estático
    ".pl":  [["perl", "-c", "{file}"],
             ["perlcritic", "--severity", "3", "{file}"],
             ["perl", "-MO=Lint", "{file}"]],
    ".pm":  [["perl", "-c", "{file}"],
             ["perlcritic", "--severity", "3", "{file}"],
             ["perl", "-MO=Lint", "{file}"]],
    # YAML — yamllint; ansible-lint para playbooks Ansible
    ".yaml": [["yamllint", "-d", "relaxed", "{file}"],
              ["ansible-lint", "--parseable", "--nocolor", "{file}"]],
    ".yml":  [["yamllint", "-d", "relaxed", "{file}"],
              ["ansible-lint", "--parseable", "--nocolor", "{file}"]],
    # PHP — syntax check nativo + PHP CodeSniffer (PSR-12)
    ".php":  [["php", "-l", "{file}"],
              ["phpcs", "--standard=PSR12", "--report=emacs", "{file}"]],
    # JSON — jsonlint validación de sintaxis
    ".json": [["jsonlint", "--compact", "{file}"]],
    # gitlint — se invoca sobre el mensaje del commit, no un fichero; ver gitlint_check tool
    # NOTA: .md/.xml/.spec usan efm-langserver como servidor LSP (no tienen entrada aquí);
    # sus linters (markdownlint, xmllint, rpmlint) se configuran en efm-langserver.yaml.
}


def _lint_run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    import subprocess
    import os
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True,
            cwd=cwd or os.getcwd(), start_new_session=True,
        )
        try:
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            proc.communicate()
            return -1, "Timeout (30s)"
        return proc.returncode, (out or "").strip()
    except FileNotFoundError:
        return -2, ""
    except Exception as e:
        return -3, str(e)


def _lint_file(path: str) -> str:
    """Linting de un fichero; devuelve diagnósticos formateados."""
    import shutil as _sh
    from pathlib import Path as _P
    p = _P(path).resolve()
    if not p.exists():
        return ""
    ext     = p.suffix.lower()
    linters = _LINTERS.get(ext, [])
    if not linters:
        return ""

    results = []
    for template in linters:
        cmd = [c.replace("{file}", str(p)) for c in template]
        if not _sh.which(cmd[0]):
            continue
        rc, out = _lint_run(cmd, cwd=str(p.parent))
        if rc == -2:
            continue
        tool = cmd[0]
        if rc == 0:
            results.append(f"  ✓  {tool}: sin errores")
        else:
            out_trim = out[:4000]
            if len(out) > 4000:
                out_trim += "\n     … (recortado)"
            indented = "\n".join(f"     {ln}" for ln in out_trim.splitlines())
            results.append(f"  ✗  {tool} (rc={rc}):\n{indented}")
    return "\n".join(results)


def _lint_project(path: str = "") -> str:
    """Linting de todo un directorio (ruff, mypy, shellcheck a nivel proyecto)."""
    import shutil as _sh
    from pathlib import Path as _P
    root = _P(path or ".").resolve()
    if not root.is_dir():
        return f"Error: directorio no encontrado: {root}"

    results = []
    if _sh.which("ruff"):
        rc, out = _lint_run(["ruff", "check", "--output-format=concise", str(root)])
        if rc == 0:
            results.append("  ✓  ruff: sin errores")
        elif out:
            lines = out.splitlines()[:40]
            results.append("  ✗  ruff:\n" + "\n".join(f"    {ln}" for ln in lines))

    if _sh.which("mypy") and any(root.rglob("*.py")):
        rc, out = _lint_run(
            ["mypy", "--no-error-summary", "--ignore-missing-imports", str(root)],
            cwd=str(root),
        )
        if rc == 0:
            results.append("  ✓  mypy: sin errores de tipos")
        elif out:
            lines = out.splitlines()[:30]
            results.append("  ✗  mypy:\n" + "\n".join(f"    {ln}" for ln in lines))

    if _sh.which("shellcheck"):
        scripts = list(root.rglob("*.sh"))[:20]
        if scripts:
            rc, out = _lint_run(["shellcheck", "-S", "warning"] + [str(s) for s in scripts])
            if rc == 0:
                results.append(f"  ✓  shellcheck: {len(scripts)} scripts OK")
            elif out:
                lines = out.splitlines()[:20]
                results.append("  ✗  shellcheck:\n" + "\n".join(f"    {ln}" for ln in lines))

    if not results:
        return "Ningún linter disponible. Instala ruff, mypy o shellcheck."
    return f"Lint: {root.name}/\n" + "\n".join(results)


_REPLACE_TOOL_NAMES = frozenset({"regex_replace", "smart_replace"})
_REPLACE_TOOL_SUFFIXES = frozenset(f"_{n}" for n in _REPLACE_TOOL_NAMES)


def _builtin_diff_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: renderiza diff visual con colores tras edit_file/write_file/edit_files
    y también tras regex_replace, smart_replace, bulk_replace y patch_apply.

    En modo TUI (_is_tui_mode()), el diff lo muestra el loop directamente via _print;
    este hook solo actúa en modo REPL (no TUI) para evitar doble renderizado.
    """
    if _is_tui_mode():
        return None  # loop's _show_tool_result handles diff via _render_tool_diff_print

    if _is_write_tool(tool_name):
        if "Error" in result or "fallida" in result or "rollback" in result:
            return None
        try:
            from tools.diff_renderer import render_edit_diff, render_write_diff
            is_edit  = tool_name == "edit_file"  or tool_name.endswith("_edit_file")
            is_multi = tool_name == "edit_files" or tool_name.endswith("_edit_files")
            if is_edit or is_multi:
                render_edit_diff(args, result)
            else:
                render_write_diff(args, result)
        except Exception:
            pass
        return None

    if tool_name in _REPLACE_TOOL_NAMES or any(tool_name.endswith(s) for s in _REPLACE_TOOL_SUFFIXES):
        try:
            from tools.diff_renderer import render_replace_diff
            render_replace_diff(args, result)
        except Exception:
            pass
        return None

    if tool_name == "bulk_replace" or tool_name.endswith("_bulk_replace"):
        try:
            from tools.diff_renderer import render_bulk_diff
            render_bulk_diff(args, result)
        except Exception:
            pass
        return None

    if tool_name == "patch_apply" or tool_name.endswith("_patch_apply"):
        try:
            from tools.diff_renderer import render_patch_diff
            render_patch_diff(args, result)
        except Exception:
            pass
        return None

    return None


def _builtin_ctags_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: reindexea el directorio del fichero editado con ctags."""
    if not _is_modify_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    _p = args.get("file_path") or args.get("path", "")
    if _p:
        paths = [_p]
    else:
        paths = [
            e.get("path", "") for e in args.get("edits", [])
            if isinstance(e, dict) and e.get("path") and e.get("action") != "delete"
        ]
    paths = [p for p in paths if p]
    if not paths:
        return None
    try:
        from tools.ctags_index import build_index_for_file
        for p in paths:
            build_index_for_file(p)
    except Exception:
        pass
    return None


def _builtin_lint_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: linting automático tras cualquier tool que modifique ficheros."""
    if not _is_modify_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    # Colectar todas las rutas afectadas (edit_files puede tener varias)
    _paths: list[str] = []
    _p = args.get("file_path") or args.get("path", "")
    if _p:
        _paths.append(_p)
    else:
        _paths = [
            e.get("path", "") for e in args.get("edits", [])
            if isinstance(e, dict) and e.get("path") and e.get("action") != "delete"
        ]
    _paths = [p for p in _paths if p]
    if not _paths:
        return None
    # Para display usamos la primera ruta; lint de todas las afectadas
    path = _paths[0]

    lint_out = "\n".join(filter(None, (_lint_file(p) for p in _paths)))
    if not lint_out:
        return None

    global _last_lint_output
    _last_lint_output = lint_out

    has_err = "✗" in lint_out
    if has_err:
        try:
            from rich.markup import escape as _resc
            from pathlib import Path as _P
            fname = _P(path).name
            lines = lint_out.splitlines()
            _MAX_LINT_LINES = 3  # max líneas visibles en TUI (resto resumidas)
            shown  = lines[:_MAX_LINT_LINES]
            hidden = len(lines) - _MAX_LINT_LINES
            _hprint(f"\n  [yellow]⚠[/yellow]  lint  [bold]{_resc(fname)}[/bold]")
            for ln in shown:
                s = ln.strip()
                if s.startswith("✓"):
                    _hprint(f"     [green]{_resc(s)}[/green]")
                elif s.startswith("✗"):
                    _hprint(f"     [yellow]{_resc(s)}[/yellow]")
                else:
                    _hprint(f"        {_resc(s)}")
            if hidden > 0:
                _hprint(f"     [dim]+{hidden} más — [bold]/lint[/bold] para ver completo[/dim]")
            else:
                _hprint("     [dim]↳ /lint para ver completo[/dim]")
            _hprint("")
        except Exception:
            pass
        return result + f"\n\n[Lint] {path}:\n{lint_out}"
    else:
        try:
            from pathlib import Path as _P
            _hprint(f"\n  [green]✓[/green]  lint  [dim]{_P(path).name}[/dim]\n")
        except Exception:
            pass
    return None


_LSP_DIAG_EXTS = frozenset({
    ".py", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh",
    ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".rb", ".pl", ".pm", ".sql", ".sh", ".yaml", ".yml",
    ".css", ".html", ".toml", ".php",
    # Office formats — diagnosticados por efm-langserver + office_linter.py
    ".docx", ".doc", ".dotx", ".docm",
    ".xlsx", ".xlsm", ".xltx", ".xls",
    ".csv", ".pdf", ".odt", ".ods",
    # Nuevos formatos vía efm-langserver
    ".rst", ".tex", ".latex", ".dockerfile", ".tf", ".tfvars", ".lua",
})

_AUTOFORMAT_EXTS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go",
    ".rs", ".c", ".cpp", ".h", ".hpp", ".java",
    ".rb", ".sql", ".sh", ".css", ".html", ".toml", ".php",
})

# Extensiones C/C++ que necesitan más tiempo de análisis en clangd
_C_EXTS = frozenset({".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh"})


def _lsp_diagnose_one(path: str) -> tuple[bool, str | None]:
    """Ejecuta lsp_diagnostics en un fichero. Devuelve (has_errors, diag_text|None)."""
    from pathlib import Path as _Path
    try:
        from plugins.lsp import lsp_diagnostics  # type: ignore
        if _Path(path).suffix.lower() in _C_EXTS:
            try:
                from plugins import lsp as _lsp_mod  # type: ignore
                _client = _lsp_mod._get_client(path)
                if _client is not None:
                    diag = _lsp_mod._fmt_diagnostics(_client.diagnostics(path, wait=5.0))
                else:
                    diag = lsp_diagnostics(path)
            except Exception:
                diag = lsp_diagnostics(path)
        else:
            diag = lsp_diagnostics(path)
        if not diag or "no hay servidor" in diag.lower() or "no encontrado" in diag.lower():
            return False, None
        has_err = "ERROR" in diag or "✗" in diag
        return has_err, diag
    except Exception:
        return False, None


def _builtin_lsp_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: ejecuta lsp_diagnostics en todos los ficheros modificados."""
    if not _is_modify_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None

    # Colectar todas las rutas afectadas
    from pathlib import Path as _Path
    raw_paths: list[str] = []
    _p = args.get("file_path") or args.get("path", "")
    if _p:
        raw_paths.append(_p)
    else:
        for e in args.get("edits", []):
            if isinstance(e, dict) and e.get("path"):
                raw_paths.append(e["path"])

    # Filtrar a extensiones LSP; máx 3 para no saturar con diagnósticos lentos
    paths = [p for p in raw_paths if _Path(p).suffix.lower() in _LSP_DIAG_EXTS][:3]
    if not paths:
        return None

    all_appends: list[str] = []
    for path in paths:
        has_err, diag = _lsp_diagnose_one(path)
        if diag is None:
            continue
        fname = _Path(path).name
        try:
            from rich.markup import escape as _resc
            if has_err:
                _hprint(f"\n  [red]✗[/red]  lsp  [bold]{_resc(fname)}[/bold]")
                for ln in diag.splitlines()[:10]:
                    _hprint(f"     [dim]{_resc(ln.strip())}[/dim]")
                _hprint("")
            else:
                _hprint(f"\n  [green]✓[/green]  lsp  [dim]{fname}[/dim]\n")
        except Exception:
            pass
        if has_err:
            n_err = len([l for l in diag.splitlines() if "✗" in l])
            all_appends.append(f"[LSP] ⚠ {n_err} error(es) — {path}:\n{diag}")
        else:
            all_appends.append(f"[LSP] ✓ Sin errores — {path}")

    if all_appends:
        return result + "\n\n" + "\n\n".join(all_appends)
    return None


def _builtin_autoformat_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: formatea via LSP solo tras write_file (ficheros nuevos).

    Solo actúa en write_file/mcp_*_write_file para evitar revertir ediciones
    intencionales hechas con edit_file/regex_replace/smart_replace.
    """
    # Solo write_file (creación/sobreescritura total) — no ediciones parciales
    _is_new_write = (tool_name == "write_file") or (
        tool_name.startswith("mcp_") and tool_name.endswith("_write_file")
    )
    if not _is_new_write:
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    path = args.get("file_path") or args.get("path", "")
    if not path:
        return None
    from pathlib import Path as _Path
    if _Path(path).suffix.lower() not in _AUTOFORMAT_EXTS:
        return None
    try:
        from plugins.lsp import lsp_format  # type: ignore
        fmt_result = lsp_format(path)
        if fmt_result and "no encontrado" not in fmt_result.lower():
            return result + f"\n[Autoformat] {fmt_result}"
    except Exception:
        pass
    return None


# Patrones de secretos/credenciales para detectar en contenido de ficheros
_SECRET_PATTERNS: list[tuple[str, _re.Pattern]] = [
    ("AWS key",          _re.compile(r'AKIA[0-9A-Z]{16}', _re.ASCII)),
    ("private key",      _re.compile(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----')),
    ("password field",   _re.compile(r'(?i)password\s*[:=]\s*["\']?\S{6,}')),
    ("API key/token",    _re.compile(r'(?i)(?:api_?key|api_?token|secret_?key)\s*[:=]\s*["\']?\S{8,}')),
    ("Bearer token",     _re.compile(r'(?i)Bearer\s+[A-Za-z0-9\-._~+/]{20,}')),
    ("GitHub token",     _re.compile(r'gh[ps]_[A-Za-z0-9]{36,}')),
    ("generic secret",   _re.compile(r'(?i)(?:secret|passwd)\s*[:=]\s*["\']?\S{8,}')),
]

# Valores de marcador/placeholder que NO son credenciales reales
_PLACEHOLDER_RE = _re.compile(
    r'(?i)(?:example|your[_\-]|changeme|change_?me|placeholder|x{4,}|'
    r'secret_key_here|password123|testpass|test_?pass|demopass|samplepass|'
    r'mockpass|fakepass|dummypass|replace_?me|my_?password|enter_?here|'
    r'insert_?here|<[^>]+>|\$\{[^}]+\}|\$\([^)]+\)|{{[^}]+}}|'
    r'\[?todo\]?|\[?tbd\]?|n/?a|none|null|empty|default|to_?be_?set|'
    r'your_(?:api|secret|token|key|password)|supersecret|'
    r'some_?(?:password|secret|key|token)|env\.|os\.environ)',
)

_BACKUP_EXTS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".c", ".cpp",
    ".h", ".hpp", ".java", ".rb", ".php", ".cs", ".sh", ".bash",
    ".pl", ".pm", ".sql", ".md", ".txt", ".json", ".yaml", ".yml",
    ".toml", ".html", ".css",
})

# {resolved_path_str: bak_path_str} — populated by pre, consumed by post
_backup_pending: dict[str, str] = {}


def _builtin_backup_pre(tool_name: str, args: dict) -> Optional[dict]:
    """Pre-hook: crea copia .bak antes de modificar ficheros existentes."""
    if not _is_modify_tool(tool_name):
        return args
    paths: list[str] = []
    p = args.get("file_path") or args.get("path", "")
    if p:
        paths.append(p)
    else:
        for edit in args.get("edits", []):
            if isinstance(edit, dict) and edit.get("path"):
                paths.append(edit["path"])
    for path in paths:
        try:
            from pathlib import Path as _Path
            src = _Path(path).expanduser().resolve()
            if src.exists() and src.suffix.lower() in _BACKUP_EXTS:
                bak = src.with_suffix(src.suffix + ".bak")
                _shutil.copy2(src, bak)
                _backup_pending[str(src)] = str(bak)
        except Exception:
            pass
    return args


def _builtin_backup_post(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: elimina .bak creado por el pre si la escritura tuvo éxito."""
    if not _backup_pending:
        return None
    failed = "Error" in result or "fallida" in result or "rollback" in result
    if failed:
        _backup_pending.clear()
        return None
    from pathlib import Path as _Path
    for src_str, bak_str in list(_backup_pending.items()):
        try:
            _Path(bak_str).unlink(missing_ok=True)
        except Exception:
            pass
    _backup_pending.clear()
    return None


def _builtin_check_secrets(tool_name: str, args: dict) -> Optional[dict]:
    """Pre-hook: bloquea write_file si el contenido contiene credenciales/secretos."""
    if tool_name != "write_file" and not tool_name.endswith("_write_file"):
        return args
    content = args.get("content", "")
    if not content:
        return args
    hits: list[str] = []
    for label, pat in _SECRET_PATTERNS:
        m = pat.search(content)
        if m and not _PLACEHOLDER_RE.search(m.group(0)):
            hits.append(label)
    if hits:
        # Devuelve None → cancela la escritura
        import sys
        msg = "[check_secrets] Escritura BLOQUEADA — posibles credenciales detectadas: " + ", ".join(hits)
        sys.stdout.write(f"\n  ⛔  {msg}\n")
        sys.stdout.flush()
        return None
    return args


_LOG_READONLY_TOOLS = frozenset({
    "read_file", "read_sections", "ls_dir", "find_file", "find_files",
    "find_dir", "grep_code", "code_search", "multi_grep", "file_stat",
    "code_outline", "analyze_codebase", "semantic_search",
})
_LOG_MAX_BYTES   = 2 * 1024 * 1024   # 2 MB per log file
_LOG_MAX_FILES   = 3


def _rotate_log(log_path) -> None:  # type: ignore[no-untyped-def]
    """Rota log_path → log_path.1, .1 → .2, … hasta _LOG_MAX_FILES."""
    from pathlib import Path as _Path
    p = _Path(log_path)
    for i in range(_LOG_MAX_FILES - 1, 0, -1):
        old = p.parent / f"{p.stem}.{i}{p.suffix}"
        new = p.parent / f"{p.stem}.{i + 1}{p.suffix}"
        if old.exists():
            try:
                old.rename(new)
            except Exception:
                pass
    try:
        p.rename(p.parent / f"{p.stem}.1{p.suffix}")
    except Exception:
        pass


def _builtin_log_tool_calls(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: registra tool calls de escritura en ~/.oocode/logs/tool_calls.jsonl.

    Omite herramientas de solo lectura para reducir volumen.
    Rota el log al superar 2 MB (máx 3 ficheros).
    """
    if tool_name in _LOG_READONLY_TOOLS:
        return None
    if tool_name.startswith("mcp_") and any(
        tool_name.endswith(f"_{ro}") for ro in _LOG_READONLY_TOOLS
    ):
        return None

    import json as _json
    import time as _time
    from pathlib import Path as _Path
    log_path = _Path.home() / ".oocode" / "logs" / "tool_calls.jsonl"
    entry = {
        "ts":   _time.time(),
        "tool": tool_name,
        "ok":   "Error" not in result and "fallida" not in result,
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if log_path.exists() and log_path.stat().st_size >= _LOG_MAX_BYTES:
            _rotate_log(log_path)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return None


def _builtin_quick_syntax_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: verifica sintaxis Python con ast.parse (instantáneo, sin dependencias).

    Se ejecuta ANTES del lint completo para dar feedback inmediato de errores de sintaxis.
    Solo actúa sobre ficheros .py con escritura exitosa.
    """
    if not _is_modify_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    import ast
    import os

    _p = args.get("file_path") or args.get("path", "")
    if _p:
        paths = [_p]
    else:
        paths = [
            e.get("path", "") for e in args.get("edits", [])
            if isinstance(e, dict) and e.get("path") and e.get("action") != "delete"
        ]
    paths = [p for p in paths if p and p.endswith(".py")]
    if not paths:
        return None

    errors: list[str] = []
    for p in paths:
        try:
            src = open(p, "r", encoding="utf-8", errors="replace").read()
            ast.parse(src, filename=p)
        except SyntaxError as exc:
            rel = os.path.relpath(p) if len(p) > 40 else p
            errors.append(f"  ⚠ SyntaxError en {rel}:{exc.lineno}: {exc.msg}")
        except Exception:
            pass

    if errors:
        return result + "\n\n⚠ Syntax check:\n" + "\n".join(errors)
    return None


_EDIT_TOOL_NAMES = frozenset({"edit_file"})
_EDIT_TOOL_SUFFIXES = frozenset({"_edit_file"})

_CTX_LINES = 2     # líneas de contexto antes/después del cambio
_MAX_SHOW  = 14    # máximo de líneas en la sección [Verify]
_MAX_NEW_STR_LINES = 40  # si new_string tiene más líneas, mostramos solo el inicio


def _verify_single(path: str, new_string: str) -> str | None:
    """Verifica que new_string está en el fichero y devuelve el texto a añadir al resultado.

    Devuelve None si no hay nada que mostrar (ok sin contexto util).
    Devuelve el texto de advertencia/verificación sin el `result +` prefix.
    """
    from pathlib import Path as _P
    try:
        content = _P(path).read_text(errors="replace")
    except Exception:
        return None

    search_str = new_string
    idx = content.find(search_str)
    if idx == -1:
        search_str = new_string.strip()
        idx = content.find(search_str) if search_str else -1

    fname = _P(path).name

    if idx == -1:
        try:
            from rich.markup import escape as _resc
            _hprint(
                f"\n  [yellow]⚠[/yellow]  verify  [bold]{_resc(fname)}[/bold]"
                " — new_string no encontrado en el fichero\n"
            )
        except Exception:
            pass
        return (
            f"\n[Verify] ⚠ '{fname}': new_string no encontrado — "
            "posible error de edición, verifica manualmente."
        )

    lines = content.splitlines()
    start_line = content[:idx].count("\n")
    change_line_count = search_str.count("\n") + 1
    end_line = start_line + change_line_count - 1

    show_end  = min(end_line, start_line + _MAX_NEW_STR_LINES - 1)
    ctx_start = max(0, start_line - _CTX_LINES)
    ctx_end   = min(len(lines) - 1, show_end + _CTX_LINES)

    if ctx_end - ctx_start + 1 > _MAX_SHOW:
        ctx_end = ctx_start + _MAX_SHOW - 1

    ctx_lines = lines[ctx_start : ctx_end + 1]
    change_range = (
        f"{start_line + 1}-{end_line + 1}" if start_line != end_line else str(start_line + 1)
    )

    formatted: list[str] = []
    for i, ln in enumerate(ctx_lines):
        lno       = ctx_start + i + 1
        is_change = start_line <= (ctx_start + i) <= end_line
        marker    = "▶" if is_change else " "
        formatted.append(f"  {marker} {lno:4d}│ {ln[:120]}")
    if show_end < end_line:
        formatted.append(f"       … ({end_line - show_end} líneas más omitidas)")

    context_text = "\n".join(formatted)

    try:
        from rich.markup import escape as _resc
        _hprint(
            f"\n  [green]✓[/green]  verify  [dim]{_resc(fname)}:{change_range}[/dim]\n"
        )
    except Exception:
        pass

    return f"\n[Verify] {fname}:{change_range}:\n{context_text}"


def _builtin_verify_after_edit(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: re-lee la sección modificada tras edit_file/edit_files para confirmar.

    Muestra ±2 líneas de contexto con ▶ en las líneas cambiadas.
    Si new_string no se encuentra emite un aviso de verificación fallida.
    Para edit_files verifica cada edit del batch individualmente.
    Desactivado por defecto — activar con /hooks builtin verify_after_edit.
    """
    is_edit = (
        tool_name in _EDIT_TOOL_NAMES
        or (tool_name.startswith("mcp_") and any(tool_name.endswith(s) for s in _EDIT_TOOL_SUFFIXES))
        or "edit_files" in tool_name
    )
    if not is_edit:
        return None
    if "Error" in result or "fallida" in result or "rollback" in result or "no encontrada" in result:
        return None

    # edit_files: verificar cada edit del batch
    if "edit_files" in tool_name:
        edits = args.get("edits", [])
        if not edits:
            return None
        additions: list[str] = []
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            path = edit.get("path", "")
            new_string = edit.get("new_string", "")
            if not path or not new_string:
                continue
            addition = _verify_single(path, new_string)
            if addition:
                additions.append(addition)
        return result + "".join(additions) if additions else None

    # edit_file: fichero único
    path       = args.get("file_path") or args.get("path", "")
    new_string = args.get("new_string", "")
    if not path or not new_string:
        return None
    addition = _verify_single(path, new_string)
    return result + addition if addition else None


_TODO_EXTS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".c", ".cpp",
    ".h", ".hpp", ".java", ".rb", ".php", ".sh", ".pl", ".sql",
})
_TODO_RE = _re.compile(
    r'(?i)\b(TODO|FIXME|HACK|XXX|BUG|OPTIMIZE|NOQA)\b\s*[:\-]?\s*(.*)',
)


def _builtin_todo_scan_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: escanea TODO/FIXME/HACK/XXX en ficheros modificados y muestra resumen.

    Avisa al agente de deuda técnica pendiente sin interrumpir el flujo.
    Solo actúa sobre extensiones de código; silencioso si no hay marcadores.
    """
    if not _is_modify_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    from pathlib import Path as _P

    _paths: list[str] = []
    _p = args.get("file_path") or args.get("path", "")
    if _p:
        _paths.append(_p)
    else:
        _paths = [
            e.get("path", "") for e in args.get("edits", [])
            if isinstance(e, dict) and e.get("path") and e.get("action") != "delete"
        ]
    _paths = [p for p in _paths if p and _P(p).suffix.lower() in _TODO_EXTS]
    if not _paths:
        return None

    all_hits: list[str] = []
    for path in _paths:
        try:
            text = _P(path).read_text(errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                m = _TODO_RE.search(line)
                if m:
                    tag    = m.group(1).upper()
                    detail = m.group(2).strip()[:60]
                    rel    = _P(path).name
                    all_hits.append(f"  {rel}:{i}  [{tag}] {detail}")
        except Exception:
            pass

    if not all_hits:
        return None

    try:
        from rich.markup import escape as _resc
        _hprint(f"\n  [dim]📝  {len(all_hits)} TODO/FIXME en fichero(s) modificado(s):[/dim]")
        for hit in all_hits[:5]:
            _hprint(f"  [dim]{_resc(hit)}[/dim]")
        if len(all_hits) > 5:
            _hprint(f"  [dim]   … y {len(all_hits) - 5} más[/dim]")
        _hprint("")
    except Exception:
        pass
    return None


def _find_test_file(source_path: str) -> str | None:
    """Busca el fichero de test asociado a un fichero fuente .py."""
    from pathlib import Path as _P
    src = _P(source_path).resolve()
    if not src.suffix == ".py":
        return None
    stem = src.stem
    # Candidatos: misma carpeta, carpeta tests/ hermana, tests/ en raíz del proyecto
    candidates = [
        src.parent / f"test_{stem}.py",
        src.parent / f"{stem}_test.py",
        src.parent / "tests" / f"test_{stem}.py",
        src.parent.parent / "tests" / f"test_{stem}.py",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _builtin_test_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: ejecuta pytest del fichero de test asociado al fichero .py modificado.

    Busca test_<módulo>.py o <módulo>_test.py en el mismo directorio o en tests/.
    Timeout de 30s. Solo actúa si se encuentra un fichero de test; silencioso si no hay.
    Desactivado por defecto — activar con /hooks builtin test_after_write.
    Se omite automáticamente si test_suite_delta está activo (_suite_snapshot is not None).
    """
    if _suite_snapshot is not None:
        return None  # test_suite_delta está activo — evitar doble ejecución
    if not _is_modify_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None

    _p = args.get("file_path") or args.get("path", "")
    if not _p:
        _edits = args.get("edits", [])
        _p = next((e.get("path", "") for e in _edits if isinstance(e, dict) and e.get("path")), "")
    if not _p or not _p.endswith(".py"):
        return None

    # No ejecutar si el propio fichero modificado ya es un test
    from pathlib import Path as _P
    stem = _P(_p).stem
    if stem.startswith("test_") or stem.endswith("_test"):
        return None

    test_file = _find_test_file(_p)
    if test_file is None:
        return None

    import subprocess, os
    try:
        proc = subprocess.Popen(
            ["python", "-m", "pytest", test_file, "-q", "--tb=short", "--no-header"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True,
            cwd=str(_P(_p).parent), start_new_session=True,
        )
        try:
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            proc.communicate()
            return None
        rc = proc.returncode
        out = (out or "").strip()
        if rc == 0:
            # Resumen de la última línea (ej: "5 passed in 0.12s")
            summary = out.splitlines()[-1] if out else "OK"
            try:
                from rich.markup import escape as _resc
                _hprint(f"\n  [green]✓[/green]  tests  [dim]{_resc(summary)}[/dim]\n")
            except Exception:
                pass
        else:
            try:
                from rich.markup import escape as _resc
                fname = _P(test_file).name
                lines = out.splitlines()[-12:]
                _hprint(f"\n  [red]✗[/red]  tests  [bold]{_resc(fname)}[/bold]")
                for ln in lines:
                    _hprint(f"     [dim]{_resc(ln)}[/dim]")
                _hprint("")
            except Exception:
                pass
            return result + f"\n\n[Tests] ✗ {_P(test_file).name}:\n{out[-2000:]}"
    except FileNotFoundError:
        pass  # pytest no disponible
    except Exception:
        pass
    return None


_SIZE_WARN_LINES = 300
_SIZE_WARN_BYTES = 15_000


def _builtin_size_check_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: avisa cuando un fichero supera 300 líneas o 15 KB tras escribirlo.

    Recuerda al agente que los ficheros grandes son difíciles de mantener y conviene
    dividirlos en módulos más pequeños. Silencioso si el fichero está dentro del umbral.
    """
    if not _is_write_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    from pathlib import Path as _P

    _paths: list[str] = []
    _p = args.get("file_path") or args.get("path", "")
    if _p:
        _paths.append(_p)
    else:
        _paths = [
            e.get("path", "") for e in args.get("edits", [])
            if isinstance(e, dict) and e.get("path") and e.get("action") != "delete"
        ]
    _paths = [p for p in _paths if p]
    if not _paths:
        return None

    warnings: list[str] = []
    for path in _paths:
        try:
            p = _P(path)
            if not p.exists():
                continue
            size = p.stat().st_size
            lines = len(p.read_text(errors="replace").splitlines())
            if lines > _SIZE_WARN_LINES or size > _SIZE_WARN_BYTES:
                warnings.append(
                    f"  {p.name}  {lines} líneas / {size // 1024 + 1} KB"
                )
        except Exception:
            pass

    if not warnings:
        return None

    try:
        from rich.markup import escape as _resc
        _hprint(f"\n  [yellow]📏[/yellow]  Fichero(s) grandes (>{_SIZE_WARN_LINES} líneas o >{_SIZE_WARN_BYTES//1000} KB):")
        for w in warnings:
            _hprint(f"  [dim]{_resc(w)}[/dim]")
        _hprint("  [dim]Considera dividir en módulos más pequeños.[/dim]\n")
    except Exception:
        pass
    return None


# ── test_suite_delta — baseline + delta detection ────────────────────────────

_suite_snapshot: dict[str, str] | None = None   # {test_id: "PASSED"|"FAILED"|"ERROR"}
_suite_workdir: str = ""


def reset_suite_snapshot() -> None:
    """Resetea el baseline de la suite (llámalo en /new o cuando cambies de proyecto)."""
    global _suite_snapshot, _suite_workdir
    _suite_snapshot = None
    _suite_workdir = ""


def _find_suite_workdir(path: str) -> str:
    """Sube en el árbol desde `path` hasta encontrar la raíz del proyecto pytest."""
    from pathlib import Path as _P
    p = _P(path).resolve()
    for candidate in (p.parent, *p.parents):
        if any((candidate / m).exists()
               for m in ("pytest.ini", "pyproject.toml", "setup.py",
                         "setup.cfg", "tox.ini")):
            return str(candidate)
    return str(p.parent)


def _run_suite_capture(workdir: str) -> dict[str, str] | None:
    """Ejecuta pytest -v --tb=no y devuelve {test_id: status}. None en timeout/error."""
    import subprocess as _sp, os as _os
    try:
        proc = _sp.Popen(
            ["python", "-m", "pytest", "-v", "--tb=no", "--no-header", "-q"],
            stdout=_sp.PIPE, stderr=_sp.STDOUT,
            stdin=_sp.DEVNULL, text=True,
            cwd=workdir, start_new_session=True,
        )
        try:
            out, _ = proc.communicate(timeout=120)
        except _sp.TimeoutExpired:
            try:
                import signal as _sig
                _os.killpg(_os.getpgid(proc.pid), _sig.SIGKILL)
            except Exception:
                proc.kill()
            proc.communicate()
            return None
        results: dict[str, str] = {}
        for line in (out or "").splitlines():
            line = line.strip()
            for status in ("PASSED", "FAILED", "ERROR"):
                if f" {status}" in line:
                    test_id = line.split(f" {status}")[0].strip()
                    if "::" in test_id:
                        results[test_id] = status
                    break
        return results if results else None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _builtin_test_suite_delta_pre(tool_name: str, args: dict) -> dict:
    """Pre-hook: captura el baseline de la suite ANTES de la primera escritura del turno.

    Solo actúa una vez por sesión (cuando _suite_snapshot is None). Silencioso si
    pytest no está disponible o no se puede determinar el workdir.
    """
    global _suite_snapshot, _suite_workdir
    if not _is_write_tool(tool_name):
        return args
    if _suite_snapshot is not None:
        return args  # baseline ya capturado

    path = args.get("file_path") or args.get("path", "")
    if not path:
        edits = args.get("edits", [])
        path = next(
            (e.get("path", "") for e in edits if isinstance(e, dict) and e.get("path")),
            "",
        )
    if not path:
        return args

    workdir = _find_suite_workdir(path)
    captured = _run_suite_capture(workdir)
    if captured is not None:
        _suite_snapshot = captured
        _suite_workdir = workdir
        try:
            _hprint(
                f"\n  [dim]◎  test_suite_delta: baseline "
                f"— {len(captured)} test(s)[/dim]\n"
            )
        except Exception:
            pass
    return args


def _builtin_test_suite_delta_post(
    tool_name: str, args: dict, result: str
) -> Optional[str]:
    """Post-hook: ejecuta la suite y muestra solo los tests nuevos que fallan (delta).

    Compara contra el baseline capturado por _builtin_test_suite_delta_pre.
    Informa de regresiones (antes pasaban, ahora fallan) y fixes (antes fallaban,
    ahora pasan). Silencioso si no hay delta.
    """
    if not _is_write_tool(tool_name):
        return None
    if result.startswith("Error") or "rollback" in result:
        return None
    if _suite_snapshot is None:
        return None

    current = _run_suite_capture(_suite_workdir)
    if current is None:
        return None

    baseline = _suite_snapshot

    regressions = sorted(
        t for t in current
        if current[t] in ("FAILED", "ERROR") and baseline.get(t) == "PASSED"
    )
    fixes = sorted(
        t for t in current
        if current[t] == "PASSED" and baseline.get(t) in ("FAILED", "ERROR")
    )
    new_failures = sorted(
        t for t in current
        if current[t] in ("FAILED", "ERROR") and t not in baseline
    )

    if not regressions and not new_failures and not fixes:
        return None

    lines: list[str] = ["\n[test_suite_delta]"]
    if regressions:
        lines.append(f"  ✘ {len(regressions)} regresión(es) — antes pasaban:")
        for t in regressions[:10]:
            lines.append(f"    ✘ {t}")
        if len(regressions) > 10:
            lines.append(f"    … y {len(regressions) - 10} más")
    if new_failures:
        lines.append(f"  ✘ {len(new_failures)} test(s) nuevo(s) fallando:")
        for t in new_failures[:5]:
            lines.append(f"    ✘ {t}")
    if fixes:
        lines.append(f"  ✔ {len(fixes)} fix(es) — ahora pasan:")
        for t in fixes[:5]:
            lines.append(f"    ✔ {t}")

    report = "\n".join(lines)
    try:
        from rich.markup import escape as _resc
        _hprint(_resc(report))
    except Exception:
        pass
    return result + report


# ── interface_change_detector — AST signature diff + caller search ────────────

_icd_snapshots: dict[str, str] = {}   # {abs_path: content_before_write}


def reset_icd_snapshots() -> None:
    """Resetea las capturas de ficheros (llámalo en /new o cuando cambies de proyecto)."""
    _icd_snapshots.clear()


def _icd_sig_str(args_node) -> str:
    """Devuelve la representación compacta de ast.arguments como '(a, b=1, *args, **kw)'."""
    import ast as _ast
    parts: list[str] = []
    a = args_node
    n_defaults = len(a.defaults)
    n_args = len(a.args)
    for i, arg in enumerate(a.args):
        p = arg.arg
        if arg.annotation:
            p += f": {_ast.unparse(arg.annotation)}"
        di = i - (n_args - n_defaults)
        if di >= 0:
            p += f"={_ast.unparse(a.defaults[di])}"
        parts.append(p)
    if a.vararg:
        v = f"*{a.vararg.arg}"
        if a.vararg.annotation:
            v += f": {_ast.unparse(a.vararg.annotation)}"
        parts.append(v)
    elif a.kwonlyargs:
        parts.append("*")
    for i, arg in enumerate(a.kwonlyargs):
        p = arg.arg
        if arg.annotation:
            p += f": {_ast.unparse(arg.annotation)}"
        d = a.kw_defaults[i]
        if d is not None:
            p += f"={_ast.unparse(d)}"
        parts.append(p)
    if a.kwarg:
        kw = f"**{a.kwarg.arg}"
        if a.kwarg.annotation:
            kw += f": {_ast.unparse(a.kwarg.annotation)}"
        parts.append(kw)
    return "(" + ", ".join(parts) + ")"


def _icd_extract_sigs(text: str) -> dict[str, str]:
    """Devuelve {qualified_name: 'name(sig)'} para top-level functions y métodos de clase."""
    import ast as _ast
    try:
        tree = _ast.parse(text)
    except SyntaxError:
        return {}
    result: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            result[node.name] = f"{node.name}{_icd_sig_str(node.args)}"
        elif isinstance(node, _ast.ClassDef):
            for child in node.body:
                if isinstance(child, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    qname = f"{node.name}.{child.name}"
                    result[qname] = f"{child.name}{_icd_sig_str(child.args)}"
    return result


def _icd_extract_docs(text: str) -> dict[str, str]:
    """Devuelve {qualified_name: primera_línea_docstring} para top-level y métodos."""
    import ast as _ast
    try:
        tree = _ast.parse(text)
    except SyntaxError:
        return {}
    result: dict[str, str] = {}

    def _first_line(node) -> str:
        doc = _ast.get_docstring(node, clean=True)
        if not doc:
            return ""
        for line in doc.splitlines():
            line = line.strip()
            if line:
                return line[:120]
        return ""

    for node in tree.body:
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            result[node.name] = _first_line(node)
        elif isinstance(node, _ast.ClassDef):
            result[node.name] = _first_line(node)
            for child in node.body:
                if isinstance(child, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    result[f"{node.name}.{child.name}"] = _first_line(child)
    return result


def _icd_find_workspace(path: str) -> str:
    """Sube desde el directorio del fichero hasta encontrar la raíz del proyecto."""
    from pathlib import Path as _P
    markers = (".git", "pyproject.toml", "setup.py", "setup.cfg",
               "CMakeLists.txt", "Cargo.toml", "go.mod", "package.json")
    p = _P(path).resolve().parent
    for cand in (p, *p.parents):
        if any((cand / m).exists() for m in markers):
            return str(cand)
    return str(p)


def _icd_find_callers(func_name: str, workspace: str,
                      exclude_path: str, max_hits: int = 12) -> list[str]:
    """Busca call-sites del símbolo con ripgrep. Excluye el fichero modificado."""
    import subprocess as _sp, shutil as _sh
    from pathlib import Path as _P

    # Pattern: word-boundary match of the function name
    if not _sh.which("rg") and not _sh.which("grep"):
        return []

    short = func_name.split(".")[-1]   # "Agent.run" → "run"
    exc = _P(exclude_path).resolve()
    root = _P(workspace).resolve()

    try:
        if _sh.which("rg"):
            cmd = ["rg", "--no-heading", "--line-number", "--color=never",
                   "--max-count=3", "--word-regexp",
                   "--glob", "*.py",
                   "--glob", f"!{exc.name}",
                   "--", short, str(root)]
        else:
            cmd = ["grep", "-rn", "--color=never", "--word-regexp",
                   "--include=*.py", short, str(root)]
        proc = _sp.run(cmd, capture_output=True, text=True, timeout=15)
        lines = (proc.stdout or "").splitlines()
    except Exception:
        return []

    results: list[str] = []
    seen_files: set[str] = set()
    for raw in lines:
        parts = raw.split(":", 2)
        if len(parts) < 3:
            continue
        fpath, lineno_s, snippet = parts[0], parts[1], parts[2].strip()
        try:
            fpath_abs = str(_P(fpath).resolve())
        except Exception:
            fpath_abs = fpath
        if fpath_abs == str(exc):
            continue
        # relative path for display
        try:
            rel = str(_P(fpath_abs).relative_to(root))
        except ValueError:
            rel = fpath
        entry = f"  {rel}:{lineno_s:<6} {snippet[:80]}"
        results.append(entry)
        seen_files.add(fpath_abs)
        if len(results) >= max_hits:
            break
    return results


def _icd_get_path(tool_name: str, args: dict) -> list[str]:
    """Extrae la lista de rutas absolutas desde los args del tool call."""
    from pathlib import Path as _P
    if "edit_files" in tool_name:
        edits = args.get("edits") or []
        return [str(_P(e["path"]).resolve())
                for e in edits if isinstance(e, dict) and e.get("path")]
    raw = args.get("path") or args.get("file_path") or ""
    return [str(_P(raw).resolve())] if raw else []


def _builtin_icd_pre(tool_name: str, args: dict) -> dict:
    """Pre-hook: captura el contenido del fichero .py antes de modificarlo."""
    if not _is_write_tool(tool_name):
        return args
    for path in _icd_get_path(tool_name, args):
        from pathlib import Path as _P
        p = _P(path)
        if p.suffix.lower() != ".py" or not p.exists():
            continue
        if path not in _icd_snapshots:
            try:
                _icd_snapshots[path] = p.read_text(errors="replace")
            except Exception:
                pass
    return args


def _builtin_icd_post(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: compara firmas antes/después y muestra callers de las cambiadas."""
    if not _is_write_tool(tool_name):
        return None
    if result.startswith("Error"):
        return None

    from pathlib import Path as _P
    warnings: list[str] = []

    for path in _icd_get_path(tool_name, args):
        before_text = _icd_snapshots.get(path)
        if before_text is None:
            continue
        p = _P(path)
        if p.suffix.lower() != ".py" or not p.exists():
            continue
        try:
            after_text = p.read_text(errors="replace")
        except Exception:
            continue

        sigs_before = _icd_extract_sigs(before_text)
        sigs_after  = _icd_extract_sigs(after_text)
        docs_before = _icd_extract_docs(before_text)
        docs_after  = _icd_extract_docs(after_text)

        changed: list[tuple[str, str, str]] = []   # (qname, sig_before, sig_after)
        for qname, sig_before in sigs_before.items():
            sig_after = sigs_after.get(qname)
            if sig_after is not None and sig_after != sig_before:
                changed.append((qname, sig_before, sig_after))

        # Public symbols deleted (present before, absent after) — breaking change
        deleted: list[tuple[str, str]] = []  # (qname, sig_before)
        for qname, sig_before in sigs_before.items():
            if not qname.split(".")[-1].startswith("_") and qname not in sigs_after:
                deleted.append((qname, sig_before))

        # Symbols whose docstring changed but signature did NOT
        doc_only: list[tuple[str, str, str]] = []  # (qname, doc_before, doc_after)
        for qname in docs_before:
            if qname in sigs_before and sigs_after.get(qname) == sigs_before[qname]:
                db = docs_before[qname]
                da = docs_after.get(qname, "")
                if db != da:
                    doc_only.append((qname, db, da))

        if not changed and not doc_only and not deleted:
            continue

        workspace = _icd_find_workspace(path)
        block: list[str] = ["\n[interface_change_detector]"]

        for qname, sig_b, sig_a in changed:
            func_short = sig_b.split("(")[0]
            before_display = f"{p.name}::{qname.split('.')[-1]}{sig_b[len(func_short):]}"
            after_display  = f"{p.name}::{qname.split('.')[-1]}{sig_a[len(func_short):]}"
            block.append(f"⚠ Cambio de interfaz: [bold]{qname}[/bold]")
            block.append(f"  Antes: {before_display}")
            block.append(f"  Ahora: {after_display}")

            # Docstring check: warn if sig changed but doc is unchanged (stale)
            doc_b = docs_before.get(qname, "")
            doc_a = docs_after.get(qname, "")
            if doc_b and doc_b == doc_a:
                block.append(f"  📝 Docstring posiblemente desactualizado: \"{doc_b}\"")
            elif doc_b and doc_b != doc_a:
                new_label = f' → "{doc_a}"' if doc_a else " (eliminado)"
                block.append(f"  📝 Docstring actualizado: \"{doc_b}\"{new_label}")

            callers = _icd_find_callers(qname, workspace, path)
            if callers:
                block.append(f"  Callers que necesitan revisión ({len(callers)}):")
                block.extend(callers)
            else:
                block.append("  Sin callers externos encontrados.")

        for qname, doc_b, doc_a in doc_only:
            new_label = f' → "{doc_a}"' if doc_a else " (eliminado)"
            block.append(f"📝 Docstring modificado: [bold]{qname}[/bold]")
            block.append(f"  Antes: \"{doc_b}\"{new_label}")

        for qname, sig_b in deleted:
            func_short = sig_b.split("(")[0]
            sig_display = f"{p.name}::{qname.split('.')[-1]}{sig_b[len(func_short):]}"
            block.append(f"🗑 Símbolo eliminado: [bold]{qname}[/bold]")
            block.append(f"  Era: {sig_display}")
            callers = _icd_find_callers(qname, workspace, path)
            if callers:
                block.append(f"  Callers que se romperán ({len(callers)}):")
                block.extend(callers)
            else:
                block.append("  Sin callers externos encontrados.")

        report = "\n".join(block)
        try:
            from rich.markup import escape as _resc
            _hprint(_resc(report).replace(
                r"\[bold]", "[bold]").replace(r"\[/bold]", "[/bold]"))
        except Exception:
            pass
        warnings.append(report)

    return ("\n".join(warnings) if warnings else None)


# ── config_syntax_after_write — JSON / TOML / INI validation ─────────────────

_CONFIG_SYNTAX_EXTS = frozenset({".json", ".toml", ".ini", ".cfg"})


def _builtin_config_syntax_after_write(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: valida la sintaxis de ficheros .json/.toml/.ini/.cfg tras escribirlos.

    Usa sólo stdlib (json, tomllib/tomli, configparser) — cero dependencias externas.
    Activo por defecto. Silencioso en ficheros fuera de las extensiones soportadas.
    """
    if not _is_write_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    path = args.get("file_path") or args.get("path", "")
    if not path:
        # edit_files: tomar el primer path afectado
        edits = args.get("edits", [])
        for e in edits:
            if isinstance(e, dict) and e.get("path") and e.get("action") != "delete":
                path = e["path"]
                break
    if not path:
        return None

    from pathlib import Path as _P
    p = _P(path).expanduser().resolve()
    if not p.exists() or p.suffix.lower() not in _CONFIG_SYNTAX_EXTS:
        return None

    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        return None

    ext = p.suffix.lower()
    error_msg: str | None = None

    if ext == ".json":
        import json as _json
        try:
            _json.loads(content)
            _hprint(f"\n  [green]✓[/green]  JSON válido  [dim]{p.name}[/dim]\n")
        except _json.JSONDecodeError as _e:
            error_msg = str(_e)
            _hprint(f"\n  [red]✗[/red]  JSON inválido  [bold]{p.name}[/bold]: {_e}\n")

    elif ext == ".toml":
        try:
            import tomllib as _toml  # Python 3.11+
        except ImportError:
            try:
                import tomli as _toml  # type: ignore[no-redef]
            except ImportError:
                return None  # sin parser disponible → silencioso
        try:
            _toml.loads(content)  # type: ignore[attr-defined]
            _hprint(f"\n  [green]✓[/green]  TOML válido  [dim]{p.name}[/dim]\n")
        except Exception as _e:
            error_msg = str(_e)
            _hprint(f"\n  [red]✗[/red]  TOML inválido  [bold]{p.name}[/bold]: {_e}\n")

    elif ext in (".ini", ".cfg"):
        import configparser as _cp
        parser = _cp.ConfigParser()
        try:
            parser.read_string(content)
            _hprint(f"\n  [green]✓[/green]  INI válido  [dim]{p.name}[/dim]\n")
        except _cp.Error as _e:
            error_msg = str(_e)
            _hprint(f"\n  [red]✗[/red]  INI inválido  [bold]{p.name}[/bold]: {_e}\n")

    if error_msg:
        return result + f"\n\n[config_syntax] {p.name}: {error_msg}"
    return None


# ── git_push_guard — seguridad en commits y push ─────────────────────────────

_GIT_GUARD_TOOLS     = frozenset({"git_commit", "git_push"})
_PROTECTED_BRANCHES  = frozenset({"main", "master", "production", "prod", "release", "stable"})
_WEAK_COMMIT_MSGS    = frozenset({
    "wip", "temp", "fix", "test", "update", "changes", "misc",
    "change", "edit", "refactor", "stuff", "tweak", "patch",
})


def _builtin_git_push_guard(tool_name: str, args: dict) -> Optional[dict]:
    """Pre-hook: advierte en push a ramas protegidas y commits con mensaje genérico.

    No bloquea: sólo muestra una advertencia visual y devuelve los args sin modificar.
    Útil para que el LLM vea el contexto antes de ejecutar git_push o git_commit.
    """
    if tool_name not in _GIT_GUARD_TOOLS:
        return args

    import subprocess as _sp

    if tool_name == "git_commit":
        msg = (args.get("message") or "").strip()
        if not msg:
            _hprint("\n  [red]✗[/red]  git_commit: mensaje de commit vacío\n")
        elif len(msg) < 10:
            _hprint(f"\n  [yellow]⚠[/yellow]  git_commit: mensaje muy corto ({len(msg)} chars)\n")
        elif msg.lower().split()[0].rstrip(".,!") in _WEAK_COMMIT_MSGS:
            _hprint(f"\n  [yellow]⚠[/yellow]  git_commit: mensaje genérico «{msg}»\n")

    elif tool_name == "git_push":
        try:
            branch = _sp.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=_sp.DEVNULL, text=True, timeout=5,
            ).strip()
            remote = (args.get("remote") or "origin").strip()

            # Contar commits a enviar
            try:
                ahead = _sp.check_output(
                    ["git", "rev-list", "--count", f"{remote}/{branch}..HEAD"],
                    stderr=_sp.DEVNULL, text=True, timeout=5,
                ).strip()
                n = int(ahead) if ahead.isdigit() else "?"
            except Exception:
                n = "?"

            label_color = "red bold" if branch in _PROTECTED_BRANCHES else "cyan"
            _hprint(
                f"\n  [{label_color}]↑[/{label_color}]"
                f"  git push {remote}/{branch}"
                f"  [dim]({n} commit{'s' if n != 1 else ''})[/dim]\n"
            )
            if branch in _PROTECTED_BRANCHES:
                _hprint(
                    f"  [bold red]⚠  Push directo a rama protegida: {branch}[/bold red]\n"
                )
        except Exception:
            pass

    return args


# ── security_audit_log — audit trail para Security MCP ───────────────────────

_SECURITY_TOOL_NAMES: frozenset[str] = frozenset({
    "nmap_scan", "port_scan", "ssl_check", "whois_lookup", "dns_enum",
    "http_headers", "nikto_scan", "gobuster_run", "curl_request",
    "hash_crack", "encode_decode", "jwt_decode", "cert_inspect",
    "log_analyze", "secret_scan", "cve_lookup", "xor_decode",
    "steganography_check", "base_convert", "hex_dump",
    "fw_audit", "ssh_key_audit", "sudoers_review", "file_integrity_check",
})


def _builtin_security_audit_log(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: guarda un registro de auditoría de cada tool del Security MCP.

    Escribe en ~/.oocode/logs/security_audit.log con timestamp, tool, target y resumen.
    Desactivado por defecto — actívalo con /hooks builtin security_audit_log cuando
    trabajes en CTF o pentesting para mantener un trail documentado.
    """
    if tool_name not in _SECURITY_TOOL_NAMES:
        return None

    import datetime as _dt
    import os as _os
    from pathlib import Path as _P

    log_path = _P.home() / ".oocode" / "logs" / "security_audit.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().isoformat(timespec="seconds")
        # Extraer target del resultado o de los args
        target = (
            args.get("target") or args.get("host") or args.get("url")
            or args.get("domain") or args.get("ip") or args.get("path")
            or args.get("text", "")[:60] or "—"
        )
        # Resumen del resultado: primera línea no vacía, máx 120 chars
        summary = next(
            (ln.strip()[:120] for ln in result.splitlines() if ln.strip()),
            result[:120],
        )
        entry = f"[{ts}] {tool_name:<28} target={target!r:<40} → {summary}\n"
        with open(log_path, "a", encoding="utf-8") as _f:
            _f.write(entry)
        _hprint(
            f"  [dim]📋 logs/security_audit.log[/dim]"
        )
    except Exception:
        pass
    return None


def _builtin_doc_validate_template_filled(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook para doc_fill_template: avisa si el fichero de salida tiene campos sin rellenar."""
    if tool_name not in {"doc_fill_template", "mcp_home_office_assistant_doc_fill_template"}:
        return None
    import re as _re
    from pathlib import Path as _P

    output_path = None
    for line in result.splitlines():
        if "→" in line or "->" in line or "Guardado" in line or "Output" in line:
            parts = line.split("→") if "→" in line else line.split("->")
            candidate = parts[-1].strip().strip("`").strip("'").strip('"')
            p = _P(candidate)
            if p.suffix in {".md", ".txt", ".html", ".docx"} and p.exists():
                output_path = p
                break
    if output_path is None:
        for word in result.split():
            w = word.strip(".,;:`'\"")
            if w.endswith((".md", ".txt", ".html")) and _P(w).exists():
                output_path = _P(w)
                break
    if output_path is None or not output_path.exists():
        return None
    try:
        if output_path.suffix == ".docx":
            import zipfile
            with zipfile.ZipFile(output_path) as z:
                content = z.read("word/document.xml").decode("utf-8", errors="replace")
        else:
            content = output_path.read_text(errors="replace")
        fields = _re.findall(r"\{\{([A-Z_a-z][A-Z_a-z0-9]*)\}\}", content)
        if fields:
            unique = sorted(set(fields))
            _hprint(
                f"  [yellow]⚠ Campos sin rellenar en {output_path.name}: "
                + ", ".join(f"{{{{" + f + "}}}}" for f in unique[:10])
                + ("[…]" if len(unique) > 10 else "")
                + "[/yellow]"
            )
    except Exception:
        pass
    return None


# ── Hooks de la Fase 2 (documentados como no implementados aún) ──

def _builtin_deadlock_detection(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: detección de deadlocks potenciales.
    
    Analiza AST para detectar:
    - Patrones de locks concurrentes (RLock, Semaphore, Lock)
    - Llamadas recursivas profundas
    - Condiciones de carrera potenciales
    
    Solo actúa sobre ficheros .py con escritura exitosa.
    """
    if not _is_write_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    
    import ast
    import re
    from pathlib import Path as _P
    
    _p = args.get("file_path") or args.get("path", "")
    if not _p:
        _edits = args.get("edits", [])
        _p = next((e.get("path", "") for e in _edits if isinstance(e, dict) and e.get("path")), "")
    if not _p or not _p.endswith(".py"):
        return None
    
    try:
        content = _P(_p).read_text(encoding="utf-8")
        tree = ast.parse(content)
    except SyntaxError:
        return None
    
    warnings: list[str] = []
    
    # 1. Detectar uso de locks (threading.Lock, RLock, Semaphore, Condition)
    lock_patterns = [
        r'threading\.(?:Lock|RLock|Semaphore|Condition|Barrier|Event)',
        r'__import\("threading"\)\.(?:Lock|RLock|Semaphore|Condition)',
    ]
    
    for pattern in lock_patterns:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if re.search(pattern, ast.unparse(node.func), re.IGNORECASE):
                        warnings.append(
                            f"  ⚠ Lock detectado: {ast.unparse(node.func)}"
                            f" — revisa si hay adquisición múltiple no protegida."
                        )
    
    # 2. Detectar llamadas recursivas profundas (más de 10 niveles)
    MAX_RECURSION_DEPTH = 10  # Variable para documentación
    
    def count_recursion_depth(node: ast.AST, depth: int = 0, max_depth: int = MAX_RECURSION_DEPTH) -> int:
        """Devuelve la profundidad máxima de recursión."""
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            # Buscar llamadas a esta función dentro de sí misma
            func_name = node.name
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name) and child.func.id == func_name:
                        return max(depth + 1, count_recursion_depth(child, depth + 1, max_depth))
        return max_depth
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            depth = count_recursion_depth(node)
            if depth > max_depth:
                warnings.append(
                    f"  ⚠ Función recursiva profunda: {node.name} (profundidad: {depth})"
                    f" — considera iteración o memoización."
                )
    
    # 3. Detectar acceso a variables compartidas sin lock
    shared_vars: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    shared_vars.add(target.id)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            if isinstance(node.target, ast.Name) and node.target.id in shared_vars:
                if isinstance(node.iter, ast.Call):
                    warnings.append(
                        f"  ⚠ Iteración sobre variable compartida: {node.target.id}"
                        f" — usa lock para proteger el bucle."
                    )
    
    if warnings:
        report = "\n[deadlock_detection] Potenciales deadlocks o condiciones de carrera:\n"
        for w in warnings[:10]:
            report += w + "\n"
        if len(warnings) > 10:
            report += f"  … y {len(warnings) - 10} más"
        return result + report
    return None


def _builtin_dead_code_detection(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: detección de código no utilizado.
    
    Analiza AST para detectar:
    - Funciones/variables definidas pero nunca usadas
    - Importaciones sin uso
    - Códigos muertos en bloques condicionales nunca alcanzados
    
    Solo actúa sobre ficheros .py con escritura exitosa.
    """
    if not _is_write_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    
    import ast
    from pathlib import Path as _P
    
    _p = args.get("file_path") or args.get("path", "")
    if not _p:
        _edits = args.get("edits", [])
        _p = next((e.get("path", "") for e in _edits if isinstance(e, dict) and e.get("path")), "")
    if not _p or not _p.endswith(".py"):
        return None
    
    try:
        content = _P(_p).read_text(encoding="utf-8")
        tree = ast.parse(content)
    except SyntaxError:
        return None
    
    warnings: list[str] = []
    
    # 1. Detectar funciones/variables definidas pero nunca usadas
    defined_names: set[str] = set()
    used_names: set[str] = set()
    
    for node in ast.walk(tree):
        # Registrar definiciones
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                defined_names.add(node.target.id)
        elif isinstance(node, ast.NamedExpr):
            defined_names.add(node.target.id)
        
        # Registrar usos (excluyendo definiciones)
        if isinstance(node, ast.Name):
            if node.id in defined_names:
                # Verificar si es uso o definición
                parent = node
                depth = 0
                while hasattr(parent, 'parent') if hasattr(parent, 'parent') else False:
                    depth += 1
                    if depth > 100:  # Evitar bucles infinitos
                        break
                if node.id in used_names:
                    used_names.add(node.id)
    
    # 2. Detectar importaciones sin uso
    import_nodes: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                import_nodes.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                import_nodes.append(f"{module}.{alias.name}" if module else alias.name)
    
    # Verificar usos de imports
    for name in import_nodes:
        if name not in used_names and name not in defined_names:
            warnings.append(
                f"  ⚠ Importación sin uso: {name}"
                f" — considera eliminar o usar el módulo."
            )
    
    # 3. Detectar bloques dead (if/else con código nunca alcanzado)
    # Análisis mejorado de condiciones falsas
    constant_false_patterns = [
        r'if\s+False:',
        r'if\s+0:',
        r'if\s+\(\s*0\s*\):',
        r'if\s+not\s+True:',
        r'if\s+\(\s*not\s+True\s*\):',
        r'if\s+""',
        r"if\s+''",
        r'if\s+None:',
        r'if\s+\(\s*not\s+\w+\s*\):',
    ]
    
    for pattern in constant_false_patterns:
        import re
        matches = re.findall(pattern, content)
        for match in matches:
            line_num = content[:content.find(match)].count('\n') + 1
            warnings.append(
                f"  ⚠ Bloque muerto en {line_num}: {match.strip()}"
                f" — código nunca se ejecutará."
            )
    
    # 4. Detectar funciones/variables globales sin uso (análisis más completo)
    global_defs: set[str] = set()
    global_uses: set[str] = set()
    
    # Extraer todas las definiciones globales
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    global_defs.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                global_defs.add(node.target.id)
        elif isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Call):
                # Funciones globales llamadas
                if isinstance(node.value.func, ast.Name):
                    global_uses.add(node.value.func.id)
        elif isinstance(node, ast.Attribute):
            # Métodos globales llamados
            if isinstance(node.value, ast.Name):
                global_uses.add(node.value.id)
    
    # Verificar definiciones globales sin uso
    for name in global_defs:
        if name not in global_uses:
            warnings.append(
                f"  ⚠ Variable global definida pero nunca usada: {name}"
                f" — considera eliminar o usar la variable."
            )
    
    # 5. Detectar listas/sets/dicts vacíos o sin uso
    empty_collections: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Set, ast.Dict)):
            if len(node.elts) == 0:
                # Buscar el nombre de la variable
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            empty_collections.add(target.id)
                elif isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Name):
                        empty_collections.add(node.target.id)
    
    for name in empty_collections:
        warnings.append(
            f"  ⚠ Colección vacía definida: {name}"
            f" — considera si realmente es necesaria."
        )
    
    # 6. Detectar try/except vacío (catch-all sin manejo de excepciones)
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            if node.handlers and not any(h.type is None for h in node.handlers):
                # Hay handlers pero no hay except: (catch-all)
                for handler in node.handlers:
                    if handler.type is None:
                        warnings.append(
                            f"  ⚠ try/except vacío en línea {node.lineno}:"
                            f" — catch-all sin manejo de excepciones específicas."
                        )
    
    # 7. Detectar if/else con else vacío
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if node.orelse and not node.orelse:
                # else vacío
                warnings.append(
                    f"  ⚠ if sin else en línea {node.lineno}:"
                    f" — bloque else vacío, considera eliminar."
                )
    
    # 4. Detectar código muerto en otros lenguajes
    
    # C/C++
    if _p.endswith(('.c', '.h', '.cpp', '.hpp')):
        content = _P(_p).read_text(encoding='utf-8')
        c_warnings: list[str] = []
        
        # Detectar funciones no usadas (basado en includes)
        if 'stdbool.h' in content or 'stdbool.h' in content:
            # Verificar funciones bool usadas
            if 'if (false)' in content.lower():
                c_warnings.append(
                    f"  ⚠ Código muerto en C: 'if (false)' encontrado"
                    f" — bloque nunca se ejecutará."
                )
        
        # Detectar macros sin usar
        if '#define' in content:
            # Verificar macros obsoletas
            if '#define const' in content:
                c_warnings.append(
                    f"  ⚠ Macro obsoleta en C: '#define const' encontrado"
                    f" — usa 'const' nativo en lugar de macro."
                )
        
        if c_warnings:
            warnings.extend(c_warnings)
    
    # Shell/Bash
    elif _p.endswith('.sh'):
        content = _P(_p).read_text(encoding='utf-8')
        sh_warnings: list[str] = []
        
        # Detectar if con condiciones siempre falsas
        if 'if [ 0 = 1 ]' in content or 'if [ false ]' in content:
            sh_warnings.append(
                f"  ⚠ Código muerto en Shell: 'if [ 0 = 1 ]' o similar encontrado"
                f" — bloque nunca se ejecutará."
            )
        
        # Detectar comentarios obsoletos
        if '# TODO' in content or '# FIXME' in content:
            sh_warnings.append(
                f"  ⚠ Comentarios obsoletos en Shell: TODO/FIXME encontrados"
                f" — considera completar o eliminar."
            )
        
        if sh_warnings:
            warnings.extend(sh_warnings)
    
    # JavaScript
    elif _p.endswith(('.js', '.ts', '.jsx', '.tsx')):
        content = _P(_p).read_text(encoding='utf-8')
        js_warnings: list[str] = []
        
        # Detectar if con condiciones siempre falsas
        if 'if (false)' in content.lower():
            js_warnings.append(
                f"  ⚠ Código muerto en JS: 'if (false)' encontrado"
                f" — bloque nunca se ejecutará."
            )
        
        # Detectar console.log sin uso en producción
        if 'console.log' in content and 'console.error' not in content:
            # Verificar si hay exportaciones
            if 'export' in content or 'module.exports' in content:
                js_warnings.append(
                    f"  ⚠ console.log en código exportado: considera usar logger en lugar."
                )
        
        if js_warnings:
            warnings.extend(js_warnings)
    
    # C# / Rust / Go / Java
    elif _p.endswith(('.cs', '.rs', '.go', '.java')):
        content = _P(_p).read_text(encoding='utf-8')
        other_warnings: list[str] = []
        
        # Detectar if con condiciones siempre falsas
        if 'if (false)' in content.lower() or 'if (0)' in content:
            other_warnings.append(
                f"  ⚠ Código muerto: 'if (false)' o 'if (0)' encontrado"
                f" — bloque nunca se ejecutará."
            )
        
        # Detectar código en bloques nunca alcanzados
        if 'if (\'\')' in content or 'if ("" )' in content:
            other_warnings.append(
                f"  ⚠ Código muerto: cadena vacía en condición"
                f" — bloque nunca se ejecutará."
            )
        
        if other_warnings:
            warnings.extend(other_warnings)
    
    if warnings:
        report = "\n[dead_code_detection] Código potencialmente no utilizado:\n"
        for w in warnings[:10]:
            report += w + "\n"
        if len(warnings) > 10:
            report += f"  … y {len(warnings) - 10} más"
        return result + report
    return None


def _builtin_performance_profiling(tool_name: str, args: dict, result: str) -> Optional[str]:
    """Post-hook: profiling de rendimiento.
    
    Analiza AST para detectar:
    - Operaciones costosas (list comprehensions grandes, operaciones I/O)
    - Bucles anidados ineficientes
    - Funciones sin cacheo (memoización)
    - Operaciones de cadena no optimizadas
    
    Solo actúa sobre ficheros .py con escritura exitosa.
    """
    if not _is_write_tool(tool_name):
        return None
    if "Error" in result or "fallida" in result or "rollback" in result:
        return None
    
    import ast
    from pathlib import Path as _P
    
    _p = args.get("file_path") or args.get("path", "")
    if not _p:
        _edits = args.get("edits", [])
        _p = next((e.get("path", "") for e in _edits if isinstance(e, dict) and e.get("path")), "")
    if not _p or not _p.endswith(".py"):
        return None
    
    try:
        content = _P(_p).read_text(encoding="utf-8")
        tree = ast.parse(content)
    except SyntaxError:
        return None
    
    warnings: list[str] = []
    
    # 1. Detectar list comprehensions grandes (>100 elementos)
    for node in ast.walk(tree):
        if isinstance(node, ast.ListComp):
            # Contar iterables
            iterables = sum(1 for expr in node.generators if isinstance(expr.iter, (ast.Call, ast.Name)))
            if iterables > 2:
                warnings.append(
                    f"  ⚠ List comprehension con {iterables} iterables — considera usar list(zip(...))"
                )
    
    # 2. Detectar operaciones I/O dentro de bucles
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Attribute):
                        if child.func.attr in ("read", "write", "open", "seek"):
                            warnings.append(
                                f"  ⚠ Operación I/O dentro de bucle — considera precargar datos."
                            )
    
    # 3. Detectar funciones sin decorador @cache o @lru_cache
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Verificar si tiene decoradores de cache
            has_cache = False
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Attribute):
                        if decorator.func.attr in ("cache", "lru_cache"):
                            has_cache = True
                            break
                elif isinstance(decorator, ast.Name):
                    if decorator.id in ("cache", "lru_cache"):
                        has_cache = True
                        break
            
            # Si no tiene cache y tiene parámetros, advertir
            if not has_cache and node.args.args:
                # Verificar si es una función que probablemente debería cachearse
                func_name = node.name
                if any(kw in func_name.lower() for kw in ["compute", "calculate", "get", "fetch", "lookup"]):
                    warnings.append(
                        f"  ⚠ Función {func_name} sin cacheo — considera @cache o @lru_cache."
                    )
    
    # 4. Detectar concatenación de cadenas en bucles
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            for child in ast.walk(node):
                if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Add):
                    # Verificar si es concatenación de cadenas (Python 3.8+ usa ast.Constant)
                    if isinstance(child.left, ast.Constant) and isinstance(child.right, ast.Constant):
                        if isinstance(child.left.value, str) or isinstance(child.right.value, str):
                            warnings.append(
                                f"  ⚠ Concatenación de cadenas en bucle — usa f-strings o list.join()."
                            )
    
    # 5. Detectar diccionarios grandes sin pre-asignación
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            if len(node.keys) > 100:
                warnings.append(
                    f"  ⚠ Diccionario con {len(node.keys)} elementos — considera pre-asignar."
                )
    
    if warnings:
        report = "\n[performance_profiling] Oportunidades de optimización:\n"
        for w in warnings[:10]:
            report += w + "\n"
        if len(warnings) > 10:
            report += f"  … y {len(warnings) - 10} más"
        return result + report
    return None


_BUILTINS: dict[str, tuple[str, str, Any]] = {
    "diff_after_write": (
        "post",
        # Usa "*" porque cubre edit_file, write_file, edit_files, regex_replace,
        # smart_replace, bulk_replace, patch_apply y sus variantes MCP.
        # fnmatch no soporta alternativas, así que la función filtra internamente.
        "*",
        _builtin_diff_after_write,
    ),
    "lsp_after_write": (
        "post",
        # Cubre _WRITE_TOOLS y sus variantes MCP — no hay glob único para todos.
        "*",
        _builtin_lsp_after_write,
    ),
    "ctags_after_write": (
        "post",
        "*",   # cubre _WRITE_TOOLS + variantes MCP; filtra internamente
        _builtin_ctags_after_write,
    ),
    "lint_after_write": (
        "post",
        "*",   # cubre _WRITE_TOOLS + variantes MCP; filtra internamente
        _builtin_lint_after_write,
    ),
    "quick_syntax_after_write": (
        "post",
        "*",   # solo actúa sobre .py; filtra internamente
        _builtin_quick_syntax_after_write,
    ),
    "autoformat_after_write": (
        "post",
        "*",   # cubre _WRITE_TOOLS + _AUTOFORMAT_EXTS; filtra internamente
        _builtin_autoformat_after_write,
    ),
    "backup_before_write": (
        # Par pre+post: pre crea .bak antes de modificar; post lo elimina si la
        # escritura tuvo éxito (queda solo si hay error, útil para recuperación).
        "pre+post",
        "*",   # cubre _WRITE_TOOLS + _BACKUP_EXTS; filtra internamente
        (_builtin_backup_pre, _builtin_backup_post),
    ),
    "check_secrets": (
        "pre",
        # Patrón específico: solo write_file y mcp_*_write_file.
        # edit/edit_files no tienen el contenido completo en args, no aplica.
        # Es el único hook que puede usar glob exacto porque solo necesita un sufijo.
        "*write_file",
        _builtin_check_secrets,
    ),
    "log_tool_calls": (
        "post",
        "*",   # intencionalmente registra TODOS los tool calls
        _builtin_log_tool_calls,
    ),
    "todo_scan_after_write": (
        "post",
        "*",   # filtra por _TODO_EXTS internamente
        _builtin_todo_scan_after_write,
    ),
    "test_after_write": (
        "post",
        "*",   # solo actúa sobre .py cuyo test file existe; filtra internamente
        _builtin_test_after_write,
    ),
    "size_check_after_write": (
        "post",
        "*",   # filtra por _is_write_tool internamente
        _builtin_size_check_after_write,
    ),
    "verify_after_edit": (
        "post",
        "*",   # filtra por edit_file (excluye write_file y edit_files) internamente
        _builtin_verify_after_edit,
    ),
    "test_suite_delta": (
        # Par pre+post: pre captura el baseline antes de la primera escritura;
        # post compara la suite actual contra ese baseline y reporta solo el delta.
        "pre+post",
        "*",
        (_builtin_test_suite_delta_pre, _builtin_test_suite_delta_post),
    ),
    "interface_change_detector": (
        # Par pre+post: pre captura el contenido .py antes de la escritura;
        # post compara las firmas AST antes/después y busca callers con ripgrep.
        # Desactivado por defecto — activa con /hooks builtin interface_change_detector
        "pre+post",
        "*",
        (_builtin_icd_pre, _builtin_icd_post),
    ),
    "config_syntax_after_write": (
        # Valida .json/.toml/.ini/.cfg tras escritura. Stdlib puro, cero deps.
        # Activo por defecto — avisa de sintaxis inválida inmediatamente.
        "post",
        "*",
        _builtin_config_syntax_after_write,
    ),
    "git_push_guard": (
        # Pre-hook: muestra rama+commits en git_push, advierte en ramas protegidas
        # y en mensajes de commit genéricos. No bloquea — sólo informa.
        # Desactivado por defecto.
        "pre",
        "git_*",
        _builtin_git_push_guard,
    ),
    "security_audit_log": (
        # Append en ~/.oocode/logs/security_audit.log tras cada tool del Security MCP.
        # Desactivado por defecto — activa cuando trabajes en CTF/pentest.
        "post",
        "*",
        _builtin_security_audit_log,
    ),
    "doc_validate_template_filled": (
        # Post-hook para doc_fill_template: avisa si quedan campos {{CAMPO}} sin rellenar.
        # Desactivado por defecto — activa con /hooks builtin doc_validate_template_filled.
        "post",
        "*",
        _builtin_doc_validate_template_filled,
    ),
    # Hooks de la Fase 2 (documentados como no implementados aún)
    "deadlock_detection": (
        # Hook pendiente: requiere AST parsing para detectar deadlocks potenciales.
        # No implementado aún — requiere análisis de llamadas recursivas y locks.
        "post",
        "*",
        _builtin_deadlock_detection,
    ),
    "dead_code_detection": (
        "post",
        "*",
        _builtin_dead_code_detection,
    ),
    "performance_profiling": (
        "post",
        "*",
        _builtin_performance_profiling,
    ),
}


class HookManager:
    def __init__(self):
        self._pre:  list[tuple[str, PreHookFn]]  = []
        self._post: list[tuple[str, PostHookFn]] = []

    # ── Built-ins ─────────────────────────────────────────────────────────────

    def register_builtins(self, names: list[str]) -> list[str]:
        """Registra los built-in hooks indicados. Devuelve los que se registraron."""
        registered = []
        already_named = {fn.__name__ for _, fn in self._pre} | {fn.__name__ for _, fn in self._post}
        for name in names:
            if name not in _BUILTINS:
                continue
            hook_type, pattern, fn = _BUILTINS[name]
            if hook_type == "pre+post":
                pre_fn, post_fn = fn
                added = False
                if pre_fn.__name__ not in already_named:
                    self._pre.append((pattern, pre_fn))
                    already_named.add(pre_fn.__name__)
                    added = True
                if post_fn.__name__ not in already_named:
                    self._post.append((pattern, post_fn))
                    already_named.add(post_fn.__name__)
                    added = True
                if added:
                    registered.append(name)
            else:
                if fn.__name__ in already_named:
                    continue
                if hook_type == "pre":
                    self._pre.append((pattern, fn))
                else:
                    self._post.append((pattern, fn))
                already_named.add(fn.__name__)
                registered.append(name)
        return registered

    def unregister_builtin(self, name: str) -> bool:
        """Elimina un built-in hook por nombre. Devuelve True si se eliminó."""
        if name not in _BUILTINS:
            return False
        hook_type, _, fn = _BUILTINS[name]
        before = len(self._pre) + len(self._post)
        if hook_type == "pre+post":
            pre_fn, post_fn = fn
            self._pre  = [(p, f) for p, f in self._pre  if f is not pre_fn]
            self._post = [(p, f) for p, f in self._post if f is not post_fn]
        else:
            self._pre  = [(p, f) for p, f in self._pre  if f is not fn]
            self._post = [(p, f) for p, f in self._post if f is not fn]
        return (len(self._pre) + len(self._post)) < before

    @staticmethod
    def available_builtins() -> list[str]:
        return list(_BUILTINS.keys())

    # ── Registro ──────────────────────────────────────────────────────────────

    def register_pre(self, pattern: str, fn: PreHookFn) -> None:
        """Registra un pre-hook para tools cuyo nombre coincide con `pattern` (glob)."""
        self._pre.append((pattern, fn))

    def register_post(self, pattern: str, fn: PostHookFn) -> None:
        """Registra un post-hook para tools cuyo nombre coincide con `pattern` (glob)."""
        self._post.append((pattern, fn))

    def unregister(self, fn: Callable) -> int:
        """Elimina todas las ocurrencias de `fn` de pre y post hooks. Devuelve nº eliminados."""
        before = len(self._pre) + len(self._post)
        self._pre  = [(p, f) for p, f in self._pre  if f is not fn]
        self._post = [(p, f) for p, f in self._post if f is not fn]
        return before - (len(self._pre) + len(self._post))

    def clear(self) -> None:
        self._pre.clear()
        self._post.clear()

    # ── Ejecución ─────────────────────────────────────────────────────────────

    def run_pre(self, tool_name: str, args: dict) -> tuple[bool, dict]:
        """Ejecuta los pre-hooks. Devuelve (continuar, args_modificados).

        Si algún hook devuelve None, continuar=False y la tool no debe ejecutarse.
        """
        current_args = dict(args)
        for pattern, fn in self._pre:
            if fnmatch.fnmatch(tool_name, pattern):
                try:
                    result = fn(tool_name, current_args)
                except Exception:
                    continue  # hooks defectuosos no bloquean la ejecución
                if result is None:
                    return False, current_args
                current_args = result
        return True, current_args

    def run_post(self, tool_name: str, args: dict, result: str) -> str:
        """Ejecuta los post-hooks. Devuelve el resultado (posiblemente modificado)."""
        current = result
        for pattern, fn in self._post:
            if fnmatch.fnmatch(tool_name, pattern):
                try:
                    out = fn(tool_name, args, current)
                except Exception:
                    continue
                if out is not None:
                    current = out
        return current

    @property
    def pre_count(self) -> int:
        return len(self._pre)

    @property
    def post_count(self) -> int:
        return len(self._post)

    def summary(self) -> str:
        lines = []
        for pattern, fn in self._pre:
            lines.append(f"  pre  [{pattern}]  {fn.__name__}")
        for pattern, post_fn in self._post:
            lines.append(f"  post [{pattern}]  {post_fn.__name__}")
        return "\n".join(lines) if lines else "  Sin hooks registrados."

    def active_builtin_names(self) -> set[str]:
        """Devuelve los nombres de built-ins actualmente activos."""
        active_fns = {fn.__name__ for _, fn in self._pre} | {fn.__name__ for _, fn in self._post}
        result: set[str] = set()
        for name, (hook_type, _, fn) in _BUILTINS.items():
            if hook_type == "pre+post":
                pre_fn, post_fn = fn
                if pre_fn.__name__ in active_fns or post_fn.__name__ in active_fns:
                    result.add(name)
            else:
                if fn.__name__ in active_fns:
                    result.add(name)
        return result

    def list_rows(self) -> list[tuple[str, str, str, bool]]:
        """Devuelve lista de (tipo, patrón, nombre_fn, es_builtin) para tablas."""
        builtin_fns: set[str] = set()
        for hook_type, _, fn in _BUILTINS.values():
            if hook_type == "pre+post":
                pre_fn, post_fn = fn
                builtin_fns.add(pre_fn.__name__)
                builtin_fns.add(post_fn.__name__)
            else:
                builtin_fns.add(fn.__name__)
        rows = []
        for pattern, fn in self._pre:
            rows.append(("pre", pattern, fn.__name__, fn.__name__ in builtin_fns))
        for pattern, post_fn in self._post:
            rows.append(("post", pattern, post_fn.__name__, post_fn.__name__ in builtin_fns))
        return rows


def load_oocode_md_hooks(hooks_manager: "HookManager", config) -> int:
    """Carga hooks definidos en la sección '## Hooks' del OOCODE.md del workspace.

    Formato de cada línea:
      post write_file: ruff check {path}
      pre  bash: echo "args: {command}"
      post edit_file: mypy {path} --ignore-missing-imports

    Devuelve el número de hooks cargados.
    """
    import re
    md_text = config.load_oocode_md() if hasattr(config, "load_oocode_md") else ""
    if not md_text:
        return 0

    m = re.search(r'##\s+Hooks\s*\n(.*?)(?=\n##|\Z)', md_text, re.DOTALL | re.IGNORECASE)
    if not m:
        return 0

    section = m.group(1)
    count   = 0
    for line in section.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        lm = re.match(r'^(pre|post)\s+([\w*\-]+)\s*:\s*(.+)$', line, re.IGNORECASE)
        if not lm:
            continue
        hook_type, pattern, cmd_tmpl = lm.group(1).lower(), lm.group(2), lm.group(3).strip()

        def _make_post_hook(tmpl: str):
            def _hook(tool_name: str, args: dict, result: str) -> None:
                import subprocess as _sp
                try:
                    cmd = tmpl.format_map({**args, "tool": tool_name, "result": result[:200]})
                    _sp.run(cmd, shell=True, timeout=30, capture_output=True)
                except Exception:
                    pass
                return None
            _hook.__name__ = f"oocode_md_post_{pattern}"
            return _hook

        def _make_pre_hook(tmpl: str):
            def _hook(tool_name: str, args: dict) -> dict:
                import subprocess as _sp
                try:
                    cmd = tmpl.format_map({**args, "tool": tool_name})
                    _sp.run(cmd, shell=True, timeout=10, capture_output=True)
                except Exception:
                    pass
                return args
            _hook.__name__ = f"oocode_md_pre_{pattern}"
            return _hook

        if hook_type == "post":
            hooks_manager.register_post(pattern, _make_post_hook(cmd_tmpl))
        else:
            hooks_manager.register_pre(pattern, _make_pre_hook(cmd_tmpl))
        count += 1

    return count
