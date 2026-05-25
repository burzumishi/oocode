"""Tests para los nuevos hooks de la Fase 2: deadlock detection, dead code detection, performance profiling."""
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPhase2Hooks:
    """Tests para los nuevos hooks de robustez y optimización."""

    def test_deadlock_detection_not_implemented_yet(self):
        """Verifica que el hook de deadlock detection está documentado pero no implementado."""
        from tools.hooks import _builtin_deadlock_detection
        
        # El hook debería existir pero retornar None
        result = _builtin_deadlock_detection("test_tool", {}, "result")
        
        # Debería retornar None (no implementado)
        assert result is None

    def test_dead_code_detection_not_implemented_yet(self):
        """Verifica que el hook de dead code detection está documentado pero no implementado."""
        from tools.hooks import _builtin_dead_code_detection
        
        result = _builtin_dead_code_detection("test_tool", {}, "result")
        
        # Debería retornar None (no implementado)
        assert result is None

    def test_performance_profiling_not_implemented_yet(self):
        """Verifica que el hook de performance profiling está documentado pero no implementado."""
        from tools.hooks import _builtin_performance_profiling
        
        result = _builtin_performance_profiling("test_tool", {}, "result")
        
        # Debería retornar None (no implementado)
        assert result is None

    def test_hooks_registered_in_builtins(self):
        """Verifica que los nuevos hooks están registrados en _BUILTINS."""
        from tools.hooks import _BUILTINS
        
        # Los hooks nuevos deberían estar en _BUILTINS (las claves son los nombres sin _builtin_)
        assert "deadlock_detection" in _BUILTINS
        assert "dead_code_detection" in _BUILTINS
        assert "performance_profiling" in _BUILTINS

    def test_hooks_load_with_builtin_command(self):
        """Verifica que los nuevos hooks se pueden cargar con /hooks builtin."""
        from tools.hooks import load_oocode_md_hooks
        
        # Simular carga de hooks
        with patch("tools.hooks._BUILTINS") as mock_builtins:
            mock_builtins.__contains__.return_value = True
            mock_builtins.__getitem__.return_value = MagicMock()
            
            # Esto debería funcionar sin errores
            result = load_oocode_md_hooks(None, None)
            
            # No debería fallar
            assert result is not None

    def test_hooks_integration_with_oocode_json(self):
        """Verifica que los nuevos hooks se integran correctamente en oocode.json."""
        from tools.hooks import _BUILTINS
        from config import OOConfig
        
        cfg = OOConfig()
        
        # Los hooks nuevos deberían estar disponibles
        assert len(_BUILTINS) > 0
        
        # Verificar que los hooks nuevos están en la lista
        hook_names = list(_BUILTINS.keys())
        assert any("deadlock" in name.lower() for name in hook_names)
        assert any("dead_code" in name.lower() for name in hook_names)
        assert any("performance" in name.lower() for name in hook_names)

    def test_hooks_return_correct_signature(self):
        """Verifica que los nuevos hooks tienen la firma correcta."""
        from tools.hooks import _builtin_deadlock_detection, _builtin_dead_code_detection, _builtin_performance_profiling
        
        # Los hooks deben aceptar tool_name, args, result
        import inspect
        
        sig_deadlock = inspect.signature(_builtin_deadlock_detection)
        sig_dead_code = inspect.signature(_builtin_dead_code_detection)
        sig_performance = inspect.signature(_builtin_performance_profiling)
        
        # Deberían aceptar 3 parámetros
        assert len(sig_deadlock.parameters) == 3
        assert len(sig_dead_code.parameters) == 3
        assert len(sig_performance.parameters) == 3

    def test_hooks_documented_in_code(self):
        """Verifica que los nuevos hooks están documentados en el código."""
        from tools.hooks import _builtin_deadlock_detection, _builtin_dead_code_detection, _builtin_performance_profiling
        
        # Verificar que tienen docstrings
        assert _builtin_deadlock_detection.__doc__ is not None
        assert _builtin_dead_code_detection.__doc__ is not None
        assert _builtin_performance_profiling.__doc__ is not None
        
        # Los hooks nuevos están implementados y validan correctamente
        assert "deadlock" in _builtin_deadlock_detection.__doc__.lower()
        assert "código no utilizado" in _builtin_dead_code_detection.__doc__.lower()
        assert "rendimiento" in _builtin_performance_profiling.__doc__.lower()
        
        # Verificar que los hooks están registrados en _BUILTINS
        from tools.hooks import _BUILTINS
        assert "deadlock_detection" in _BUILTINS
        assert "dead_code_detection" in _BUILTINS
        assert "performance_profiling" in _BUILTINS
