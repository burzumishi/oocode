"""Tests de configuración de contexto en context.py y config.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.context import _CPT_TOOL, _CPT_CALLS, _CPT_THINK, _CPT_TEXT, _CPT_SYS, _CPT_DEFLT
from config import DEFAULT_CONFIG


class TestContextConfiguration:
    def test_chars_per_token_values(self):
        # Tool results / JSON payloads: más densos → ratio más bajo
        assert _CPT_TOOL < _CPT_TEXT
        assert _CPT_CALLS < _CPT_TEXT
        # Thinking: lenguaje natural → ratio más alto
        assert _CPT_THINK > _CPT_TEXT
        # Todos son floats positivos
        for cpt in (_CPT_TOOL, _CPT_CALLS, _CPT_THINK, _CPT_TEXT, _CPT_SYS, _CPT_DEFLT):
            assert isinstance(cpt, float) and cpt > 0

    def test_context_section_exists(self):
        assert "context" in DEFAULT_CONFIG

    def test_context_required_keys(self):
        ctx = DEFAULT_CONFIG["context"]
        for key in ("minKeep", "compactThreshold", "maxSummaryChars",
                    "maxToolResultTokens", "autoContinueMax"):
            assert key in ctx, f"Falta clave context.{key}"

    def test_embeddings_disk_cache_keys(self):
        emb = DEFAULT_CONFIG["embeddings"]
        assert "diskCacheEnabled" in emb
        assert "diskCacheDir" in emb
        assert "diskCacheMaxEntries" in emb

    def test_embeddings_disk_cache_defaults(self):
        emb = DEFAULT_CONFIG["embeddings"]
        assert emb["diskCacheEnabled"] is True
        assert "~/.oocode/cache" in emb["diskCacheDir"]
        assert isinstance(emb["diskCacheMaxEntries"], int)
        assert emb["diskCacheMaxEntries"] > 0

    def test_no_context_cache_section(self):
        """context_cache fue eliminado — no debe existir en DEFAULT_CONFIG."""
        assert "context_cache" not in DEFAULT_CONFIG


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
