"""Guarda de regresión: ningún .py del repo debe emitir SyntaxWarning.

Un SyntaxWarning (p.ej. secuencia de escape inválida '\\/' en un regex JS dentro
de un string Python) se imprime a stderr cuando el módulo se compila/importa, y en
la app TUI full-screen ese texto crudo corrompe el statusbar/prompt. Este test
atrapa esas secuencias antes de que lleguen al usuario. También verifica que no
queden SyntaxError reales.
"""
import pathlib
import warnings

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _iter_py():
    for p in _ROOT.rglob("*.py"):
        # Ignorar entornos virtuales / cachés ocultos
        if any(part.startswith(".") or part in ("__pycache__", "node_modules")
               for part in p.parts):
            continue
        yield p


def test_no_syntax_warnings_repo_wide():
    offenders = []
    for p in _iter_py():
        src = p.read_text(encoding="utf-8", errors="replace")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                compile(src, str(p), "exec")
            except SyntaxError:
                continue  # los SyntaxError se cubren en el otro test
            for w in caught:
                if issubclass(w.category, SyntaxWarning):
                    rel = p.relative_to(_ROOT)
                    offenders.append(f"{rel}:{w.lineno} {w.message}")
    assert not offenders, "SyntaxWarnings detectados:\n" + "\n".join(offenders)


def test_no_syntax_errors_repo_wide():
    offenders = []
    for p in _iter_py():
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            compile(src, str(p), "exec")
        except SyntaxError as e:
            offenders.append(f"{p.relative_to(_ROOT)}:{e.lineno} {e.msg}")
    assert not offenders, "SyntaxErrors detectados:\n" + "\n".join(offenders)


def test_page_chat_session_regex_emitted_correctly():
    """El fix de webui/page_chat.py mantiene el regex JS exacto (\\/session\\s+\\S)."""
    src = (_ROOT / "webui" / "page_chat.py").read_text(encoding="utf-8")
    # En el FUENTE están los backslashes duplicados (Python los colapsa a uno solo)
    assert r"/^\\/session\\s+\\S/" in src
    # Y el literal Python resultante es el regex JS correcto
    assert r"/^\/session\s+\S/" == "/^\\/session\\s+\\S/"
