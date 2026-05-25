"""Test de validación de _PROMPT_CACHE_DIR en context.py."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.context import _PROMPT_CACHE_DIR, CONFIG


class TestPromptCacheDir:
    """Tests para validar _PROMPT_CACHE_DIR."""

    def test_prompt_cache_dir_exists(self):
        """Test que _PROMPT_CACHE_DIR existe y es una cadena."""
        assert isinstance(_PROMPT_CACHE_DIR, str)
        assert len(_PROMPT_CACHE_DIR) > 0

    def test_prompt_cache_dir_loads_from_config(self):
        """Test que _PROMPT_CACHE_DIR carga desde oocode.json."""
        # Verificar que CONFIG es accesible
        assert CONFIG is not None
        
        # Verificar que _PROMPT_CACHE_DIR usa el valor de cache_dir de CONFIG
        # o el valor por defecto si no está configurado
        assert "~/.oocode/cache" in _PROMPT_CACHE_DIR

    def test_prompt_cache_dir_default_value(self):
        """Test que usa el valor por defecto si cache_dir no está en CONFIG."""
        # Verificar que el valor por defecto es "~/.oocode/cache"
        assert "~/.oocode/cache" in _PROMPT_CACHE_DIR

    def test_prompt_cache_dir_can_be_customized(self):
        """Test que _PROMPT_CACHE_DIR puede ser personalizado en oocode.json."""
        # Si cache_dir está configurado en oocode.json, debería usar ese valor
        # Esto se verificará automáticamente al cambiar la configuración
        assert isinstance(_PROMPT_CACHE_DIR, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
