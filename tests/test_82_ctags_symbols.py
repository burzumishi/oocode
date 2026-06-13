"""Tests del indexado de símbolos vía ctags y del fix de timeout de list_symbols.

Causa raíz del bug: `list_symbols` disparaba un `ctags -R` sobre todo el árbol
cuando no había índice cacheado; en árboles grandes excedía el timeout del
cliente MCP (15 s) y, al ser el servidor single-thread por stdio, bloqueaba
también las llamadas siguientes (dos "Sin respuesta del servidor MCP (timeout)"
seguidos).

Fix verificado aquí:
  1. `_ctags_bin()` detecta **Universal Ctags** (necesario para --extras /
     --output-format=u-ctags), no Exuberant.
  2. `_ctags_build_index()` excluye directorios pesados (.git/node_modules/...).
  3. `list_symbols` indexa SOLO el fichero pedido (rápido) cuando no hay índice
     de proyecto cacheado, en vez de construir el árbol entero.

Parametrizado sobre los binarios ctags reales instalados. No requiere LLM.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mcp_servers.oocode_assistant as oa
from mcp_servers.oocode_assistant import (
    _CTAGS_EXCLUDE_DIRS,
    _ctags_build_index,
    _ctags_parse_lines,
    _ctags_read_tags,
    _ctags_symbols_for_file,
    _tool_list_symbols,
)


def _is_universal(path: str) -> bool:
    try:
        out = subprocess.run([path, "--version"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, timeout=5).stdout
        return "Universal Ctags" in out
    except Exception:
        return False


# Descubre los binarios reales instalados, etiquetados por variante.
_BINARIES: list[tuple[str, str, bool]] = []  # (id, path, is_universal)
for _name in ("ctags-universal", "universal-ctags", "ctags-exuberant", "ctags"):
    _p = shutil.which(_name)
    if _p:
        _BINARIES.append((_name, _p, _is_universal(_p)))

_UNIVERSAL_PATH = next((p for _, p, u in _BINARIES if u), None)
_EXUBERANT_PATH = next((p for _, p, u in _BINARIES if not u), None)

SAMPLE_PY = (
    "def my_function():\n"
    "    return 1\n"
    "\n"
    "class MyClass:\n"
    "    def method(self):\n"
    "        pass\n"
)


@pytest.fixture(autouse=True)
def _reset_ctags_cache():
    """El binario detectado se cachea en módulo; resetear entre tests para que
    el monkeypatch de which()/_ctags_bin sea honrado."""
    oa._CTAGS_BIN_CACHE = None
    yield
    oa._CTAGS_BIN_CACHE = None


# ── _ctags_parse_lines (puro, sin binario) ────────────────────────────────────

class TestParseLines:
    def test_parses_u_ctags_lines(self):
        lines = [
            "!_TAG_FILE_FORMAT\t2\t/extended format/",
            'McpClient\tmcp_client.py\t/^class McpClient:$/;"\tc\tline:50',
            'call_tool\tmcp_client.py\t/^    def call_tool/;"\tm\tline:319\tclass:McpClient',
        ]
        syms = _ctags_parse_lines(lines)
        assert len(syms) == 2
        assert syms[0] == {"name": "McpClient", "path": "mcp_client.py",
                           "line": "50", "kind": "c"}
        assert syms[1]["name"] == "call_tool"
        assert syms[1]["line"] == "319"
        assert syms[1]["kind"] == "m"

    def test_skips_comments_and_short_lines(self):
        assert _ctags_parse_lines(["!_TAG_FOO\tx", "incompleta\tsolo"]) == []

    def test_empty(self):
        assert _ctags_parse_lines([]) == []


# ── _ctags_bin (detección de variante) ────────────────────────────────────────

class TestCtagsBinDetection:
    def test_prefers_ctags_universal_name(self, monkeypatch):
        def fake_which(name):
            return {"ctags-universal": "/usr/bin/ctags-universal"}.get(name)
        monkeypatch.setattr(shutil, "which", fake_which)
        assert oa._ctags_bin() == "/usr/bin/ctags-universal"

    def test_prefers_universal_ctags_name(self, monkeypatch):
        def fake_which(name):
            return {"universal-ctags": "/opt/universal-ctags"}.get(name)
        monkeypatch.setattr(shutil, "which", fake_which)
        assert oa._ctags_bin() == "/opt/universal-ctags"

    def test_plain_ctags_rejected_if_exuberant(self, monkeypatch):
        # Solo existe 'ctags' y es Exuberant → no apto → ""
        def fake_which(name):
            return "/usr/bin/ctags" if name == "ctags" else None
        monkeypatch.setattr(shutil, "which", fake_which)

        class _R:
            stdout = "Exuberant Ctags 5.9\n"
        monkeypatch.setattr(oa.subprocess, "run", lambda *a, **k: _R())
        assert oa._ctags_bin() == ""

    def test_plain_ctags_accepted_if_universal(self, monkeypatch):
        def fake_which(name):
            return "/usr/bin/ctags" if name == "ctags" else None
        monkeypatch.setattr(shutil, "which", fake_which)

        class _R:
            stdout = "Universal Ctags 6.2.1\n"
        monkeypatch.setattr(oa.subprocess, "run", lambda *a, **k: _R())
        assert oa._ctags_bin() == "/usr/bin/ctags"

    def test_none_installed(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: None)
        assert oa._ctags_bin() == ""

    def test_result_is_cached(self, monkeypatch):
        calls = {"n": 0}

        def fake_which(name):
            calls["n"] += 1
            return "/usr/bin/ctags-universal" if name == "ctags-universal" else None
        monkeypatch.setattr(shutil, "which", fake_which)
        oa._ctags_bin()
        first = calls["n"]
        oa._ctags_bin()
        assert calls["n"] == first  # 2ª llamada no re-sondea


# ── Parametrizado sobre los binarios REALES instalados ────────────────────────

@pytest.mark.skipif(not _BINARIES, reason="ningún ctags instalado")
@pytest.mark.parametrize("name,path,is_universal", _BINARIES,
                         ids=[b[0] for b in _BINARIES])
class TestRealBinaries:
    def test_symbols_for_file(self, monkeypatch, tmp_path, name, path, is_universal):
        monkeypatch.setattr(oa, "_ctags_bin", lambda: path)
        f = tmp_path / "sample.py"
        f.write_text(SAMPLE_PY)
        syms = _ctags_symbols_for_file(str(f))
        if is_universal:
            names = {s["name"] for s in syms}
            assert "my_function" in names
            assert "MyClass" in names
        else:
            # Exuberant no soporta --extras/--output-format=u-ctags → degrada a []
            assert syms == []

    def test_list_symbols_single_file_path(self, monkeypatch, tmp_path,
                                           name, path, is_universal):
        monkeypatch.setattr(oa, "_ctags_bin", lambda: path)
        f = tmp_path / "alpha.py"
        f.write_text(SAMPLE_PY)
        out = _tool_list_symbols({"path": str(f)})
        assert isinstance(out, str)
        if is_universal:
            assert "my_function" in out
            assert "MyClass" in out
            # NO debe haber construido el índice de árbol completo
            assert not (tmp_path / oa._CTAGS_FILE).exists()
        else:
            assert "Sin símbolos" in out


# ── Tests que requieren Universal Ctags real ──────────────────────────────────

@pytest.mark.skipif(_UNIVERSAL_PATH is None, reason="Universal Ctags no instalado")
class TestUniversalReal:
    def test_build_index_excludes_heavy_dirs(self, monkeypatch, tmp_path):
        monkeypatch.setattr(oa, "_ctags_bin", lambda: _UNIVERSAL_PATH)
        # Fichero normal + fichero dentro de un dir excluido
        (tmp_path / "main.py").write_text("def main_sym(): pass\n")
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "vendored.py").write_text("def excluded_sym(): pass\n")

        err = _ctags_build_index(str(tmp_path))
        assert err == ""
        tags = _ctags_read_tags(str(tmp_path))
        names = {t["name"] for t in tags}
        assert "main_sym" in names
        assert "excluded_sym" not in names  # node_modules excluido

    def test_list_symbols_reuses_existing_index(self, monkeypatch, tmp_path):
        monkeypatch.setattr(oa, "_ctags_bin", lambda: _UNIVERSAL_PATH)
        (tmp_path / "a.py").write_text("def func_a(): pass\n")
        (tmp_path / "b.py").write_text("def func_b(): pass\n")
        _ctags_build_index(str(tmp_path))
        assert (tmp_path / oa._CTAGS_FILE).exists()
        # list_symbols sobre a.py debe filtrar solo símbolos de a.py
        out = _tool_list_symbols({"path": str(tmp_path / "a.py")})
        assert "func_a" in out
        assert "func_b" not in out

    def test_kinds_filter(self, monkeypatch, tmp_path):
        monkeypatch.setattr(oa, "_ctags_bin", lambda: _UNIVERSAL_PATH)
        f = tmp_path / "mix.py"
        f.write_text(SAMPLE_PY)
        # kind 'c' = clase → solo MyClass, no my_function
        out = _tool_list_symbols({"path": str(f), "kinds": "c"})
        assert "MyClass" in out
        assert "my_function" not in out


class TestExcludeConstant:
    def test_common_heavy_dirs_present(self):
        for d in (".git", "node_modules", "__pycache__", ".venv"):
            assert d in _CTAGS_EXCLUDE_DIRS


# ── Degradación sin Universal Ctags ───────────────────────────────────────────

class TestNoUniversalDegradation:
    def test_symbols_for_file_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(oa, "_ctags_bin", lambda: "")
        f = tmp_path / "x.py"
        f.write_text(SAMPLE_PY)
        assert _ctags_symbols_for_file(str(f)) == []

    def test_build_index_reports_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(oa, "_ctags_bin", lambda: "")
        err = _ctags_build_index(str(tmp_path))
        assert "no instalado" in err

    def test_list_symbols_missing_path(self):
        assert "requerido" in _tool_list_symbols({})

    def test_list_symbols_nonexistent_file(self, tmp_path):
        out = _tool_list_symbols({"path": str(tmp_path / "nope.py")})
        assert "no encontrado" in out
