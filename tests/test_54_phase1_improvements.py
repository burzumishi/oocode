"""Tests para _make_compact_summary."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCompactSummaryMetadata:
    """Tests para la función _make_compact_summary."""

    def test_compact_summary_includes_metadata(self, tmp_path):
        from agent.loop import _make_compact_summary

        blocks = [
            ("grep_code", {"path": "test.py"}, "result", True),
        ]
        summary = _make_compact_summary(blocks)
        assert "Searched" in summary or "grep_code" in summary

    def test_compact_summary_handles_empty_blocks(self, tmp_path):
        from agent.loop import _make_compact_summary

        summary = _make_compact_summary([])
        assert "(ctrl+o to expand)" in summary
