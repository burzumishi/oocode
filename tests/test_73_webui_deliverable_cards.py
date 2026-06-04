"""Tests WebUI: tarjetas de descarga solo para entregables + hooks en workers.

Dos correcciones:

1. `_show_tool_block` (rama WebUI) solo adjunta `file_path` (→ tarjeta de descarga)
   para entregables que el usuario pide producir: documentos ofimáticos/PDF, o
   write_file/create_file genéricos con extensión de entregable. NUNCA para
   ediciones de código (edit_file, *_replace, patch_apply) ni ficheros temporales.

2. El dispatch paralelo (ThreadPoolExecutor) reinyecta el canal de impresión de
   hooks (`tools.hooks.set_hook_print_fn`) en cada hilo worker. Sin esto, como
   `hook_print_fn` vive en `threading.local`, lint/lsp/interface_change_detector
   caerían al fallback `console` y su salida no llegaría al WebUI / bloque del
   subagente.
"""
import os
import sys
import queue as _queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_webui_loop():
    """Loop mínimo para ejercitar la rama WebUI de _show_tool_block."""
    from agent.loop import AgentLoop
    loop = AgentLoop.__new__(AgentLoop)
    loop.capture_output = False
    loop.is_subagent = False
    loop._webui_queue = _queue.SimpleQueue()
    loop._TOOL_DISPLAY_NAMES = {}
    loop._strip_rich = lambda s: s
    loop._call_context = lambda n, a: ""
    loop._webui_status = lambda: {"type": "status"}
    return loop


def _emit_and_get_tool_done(loop, name, args, result="✅ Guardado"):
    loop._show_tool_block(name, args, result, allowed=True)
    events = []
    while True:
        try:
            events.append(loop._webui_queue.get_nowait())
        except _queue.Empty:
            break
    return next((e for e in events if e.get("type") == "tool_done"), None)


# ── Tarjetas de descarga: solo entregables ────────────────────────────────────

def test_code_edit_no_file_card(tmp_path):
    """edit_file sobre código NO debe generar tarjeta de descarga."""
    f = tmp_path / "main.py"
    f.write_text("print('x')\n")
    loop = _make_webui_loop()
    ev = _emit_and_get_tool_done(loop, "edit_file", {"file_path": str(f)})
    assert ev is not None
    assert "file_path" not in ev


def test_generic_write_code_no_file_card(tmp_path):
    """write_file de un .py NO es entregable."""
    f = tmp_path / "module.py"
    f.write_text("x = 1\n")
    loop = _make_webui_loop()
    ev = _emit_and_get_tool_done(loop, "write_file", {"path": str(f)})
    assert ev is not None and "file_path" not in ev


def test_replace_tools_no_file_card(tmp_path):
    """smart_replace/bulk_replace/patch_apply son ediciones de código, sin tarjeta."""
    f = tmp_path / "code.c"
    f.write_text("int main(){}\n")
    for tool in ("smart_replace", "bulk_replace", "regex_replace", "patch_apply"):
        loop = _make_webui_loop()
        ev = _emit_and_get_tool_done(loop, tool, {"file_path": str(f)})
        assert ev is not None and "file_path" not in ev, f"{tool} no debe dar tarjeta"


def test_generic_write_deliverable_ext_gets_card(tmp_path, monkeypatch):
    """write_file de un .docx fuera de temp SÍ es entregable."""
    # Asegurar que tmp_path no se considera temporal
    monkeypatch.setattr("tempfile.gettempdir", lambda: "/nonexistent-temp-xyz")
    f = tmp_path / "informe.docx"
    f.write_bytes(b"PK\x03\x04docx")
    loop = _make_webui_loop()
    ev = _emit_and_get_tool_done(loop, "write_file", {"path": str(f)})
    assert ev is not None
    assert ev.get("file_path") == os.path.abspath(str(f))
    assert ev.get("file_action") == "created"
    assert ev.get("file_name") == "informe.docx"


def test_doc_create_gets_card(tmp_path, monkeypatch):
    """doc_create (tool ofimática) siempre genera tarjeta."""
    monkeypatch.setattr("tempfile.gettempdir", lambda: "/nonexistent-temp-xyz")
    f = tmp_path / "contrato.docx"
    f.write_bytes(b"PK\x03\x04docx")
    loop = _make_webui_loop()
    ev = _emit_and_get_tool_done(loop, "doc_create", {"output_path": str(f)})
    assert ev is not None and ev.get("file_path") == os.path.abspath(str(f))


def test_doc_update_section_marks_edited(tmp_path, monkeypatch):
    """doc_update_section es un entregable editado."""
    monkeypatch.setattr("tempfile.gettempdir", lambda: "/nonexistent-temp-xyz")
    f = tmp_path / "memo.docx"
    f.write_bytes(b"PK\x03\x04docx")
    loop = _make_webui_loop()
    ev = _emit_and_get_tool_done(loop, "doc_update_section", {"file_path": str(f)})
    assert ev is not None
    assert ev.get("file_path") == os.path.abspath(str(f))
    assert ev.get("file_action") == "edited"


def test_temp_deliverable_excluded(tmp_path, monkeypatch):
    """Un .docx dentro del directorio temporal NO genera tarjeta (es temporal)."""
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    f = tmp_path / "scratch.docx"
    f.write_bytes(b"PK\x03\x04docx")
    loop = _make_webui_loop()
    ev = _emit_and_get_tool_done(loop, "doc_create", {"output_path": str(f)})
    assert ev is not None and "file_path" not in ev


def test_bak_suffix_excluded(tmp_path, monkeypatch):
    """Ficheros .bak/.tmp no son entregables."""
    monkeypatch.setattr("tempfile.gettempdir", lambda: "/nonexistent-temp-xyz")
    f = tmp_path / "data.bak"
    f.write_text("x")
    loop = _make_webui_loop()
    ev = _emit_and_get_tool_done(loop, "write_file", {"path": str(f)})
    assert ev is not None and "file_path" not in ev


# ── Propagación de hook_print_fn a hilos worker del pool ──────────────────────

def _make_dispatch_loop():
    from agent.loop import AgentLoop
    from tools.registry import ToolRegistry
    from config import OOConfig
    loop = AgentLoop.__new__(AgentLoop)
    loop.config = OOConfig()
    loop.registry = ToolRegistry()
    loop.permissions = MagicMock()
    loop.permissions.check = MagicMock(return_value=True)
    loop.memory = MagicMock()
    loop.is_subagent = False
    loop.capture_output = False
    loop._status_cb = None
    loop._plan_tasks = []
    loop._kill_requested = False
    loop._sep_label = ""
    loop._tool_current_file = ""
    loop.context = MagicMock()
    loop.context.stats.return_value = {"tokens_estimate": 10, "max_tokens": 1000}
    loop.context.compact_threshold = 0.8
    loop._run_animated_header = MagicMock(return_value="ok")
    loop._show_tool_running_header = MagicMock()
    loop._webui_emit = MagicMock()
    loop._strip_rich = lambda s: s
    loop._call_context = lambda n, a: ""
    loop._TOOL_DISPLAY_NAMES = {}
    return loop


def _tc(name, args=None):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=args or {}))


def test_parallel_workers_get_hook_print_fn():
    """Cada worker del pool debe tener hook_print_fn = loop._print seteado."""
    import tools.hooks as hooks_mod
    loop = _make_dispatch_loop()

    sentinel = lambda *a, **k: None
    loop._print = sentinel

    captured: dict[str, object] = {}

    def _cap(name, args):
        # Leído dentro del hilo worker durante la ejecución de la tool
        captured[name] = getattr(hooks_mod._tl, "hook_print_fn", None)
        return "ok"

    loop._execute_tool = _cap
    # Lote de solo-lectura → rama paralela (ThreadPoolExecutor)
    calls = [_tc("read_file"), _tc("find_file")]
    *_, safe_parallel = loop._turn_dispatch_tools(calls, total_inp=0, total_out=0)

    assert safe_parallel is True
    assert captured, "las tools deberían haberse ejecutado"
    assert all(fn is sentinel for fn in captured.values()), \
        "hook_print_fn debe propagarse al hilo worker (era None → fallback console)"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
