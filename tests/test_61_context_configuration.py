"""Test de validación de configuración de contexto en context.py y config.py."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.context import _CHARS_PER_TOKEN, _PROMPT_CACHE_DIR, _CACHE_TTL
from config import DEFAULT_CONFIG


class TestContextConfiguration:
    """Tests para validar la configuración de contexto."""

    def test_chars_per_token_configured(self):
        """Test que _CHARS_PER_TOKEN está configurado correctamente."""
        assert isinstance(_CHARS_PER_TOKEN, (int, float))
        assert _CHARS_PER_TOKEN > 0
        assert _CHARS_PER_TOKEN == 3.0

    def test_prompt_cache_dir_configured(self):
        """Test que _PROMPT_CACHE_DIR está configurado correctamente."""
        assert isinstance(_PROMPT_CACHE_DIR, str)
        assert len(_PROMPT_CACHE_DIR) > 0
        assert "~/.oocode/cache" in _PROMPT_CACHE_DIR

    def test_cache_ttl_configured(self):
        """Test que _CACHE_TTL está configurado correctamente."""
        assert isinstance(_CACHE_TTL, (int, float))
        assert _CACHE_TTL > 0
        assert _CACHE_TTL == 300

    def test_context_cache_section_exists(self):
        """Test que la sección context_cache existe en DEFAULT_CONFIG."""
        assert "context_cache" in DEFAULT_CONFIG

    def test_context_cache_chars_per_token(self):
        """Test que context_cache.chars_per_token existe."""
        assert "chars_per_token" in DEFAULT_CONFIG["context_cache"]

    def test_context_cache_cache_dir(self):
        """Test que context_cache.cache_dir existe."""
        assert "cache_dir" in DEFAULT_CONFIG["context_cache"]

    def test_context_cache_cache_ttl(self):
        """Test que context_cache.cache_ttl existe."""
        assert "cache_ttl" in DEFAULT_CONFIG["context_cache"]

    def test_context_cache_default_values(self):
        """Test que los valores por defecto son correctos."""
        assert DEFAULT_CONFIG["context_cache"]["chars_per_token"] == 3.0
        assert DEFAULT_CONFIG["context_cache"]["cache_dir"] == "~/.oocode/cache"
        assert DEFAULT_CONFIG["context_cache"]["cache_ttl"] == 300


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
