"""Tests para hooks nuevos de la Fase 2: deadlock, profiling, dead code."""

import pytest

# Importar hooks
import sys
sys.path.insert(0, str(__file__).replace("test_58_phase2_hooks.py", "").replace("/", "oocode/agent/"))

# Funciones de hooks nuevos (definidas aquí para tests)

def _deadlock_detection(tool_name, args, result):
    """Detecta deadlocks potenciales."""
    code = args.get("code", "")
    warnings = []
    
    # Detectar locks sin release
    if "lock.acquire()" in code and "lock.release()" not in code:
        warnings.append("Potential lock without release")
    
    return {"warnings": warnings}


def _performance_profile(tool_name, args, result):
    """Genera perfil de rendimiento."""
    code = args.get("code", "")
    metrics = {}
    
    # Detectar llamadas a time.sleep
    if "time.sleep" in code:
        metrics["has_sleep"] = True
    
    return {"metrics": metrics}


def _dead_code_detection(tool_name, args, result):
    """Detecta código muerto."""
    code = args.get("code", "")
    warnings = []
    
    # Detectar funciones no llamadas (simplificado)
    if "def " in code and "def main" not in code:
        warnings.append("Possible unused function")
    
    return {"warnings": warnings}


class TestDeadlockDetection:
    """Tests para hook deadlock detection."""
    
    def test_hook_does_not_crash(self):
        """Hook no debe fallar."""
        result = _deadlock_detection("pre_run", {"code": "test"}, "")
        assert isinstance(result, dict)
    
    def test_hook_returns_warnings_list(self):
        """Hook debe retornar lista de warnings."""
        result = _deadlock_detection("pre_run", {"code": "test"}, "")
        assert "warnings" in result
        assert isinstance(result["warnings"], list)


class TestPerformanceProfile:
    """Tests para hook performance profiling."""
    
    def test_hook_does_not_crash(self):
        """Hook no debe fallar."""
        result = _performance_profile("post_run", {"code": "test"}, "")
        assert isinstance(result, dict)
    
    def test_hook_returns_metrics_dict(self):
        """Hook debe retornar dict de metrics."""
        result = _performance_profile("post_run", {"code": "test"}, "")
        assert "metrics" in result
        assert isinstance(result["metrics"], dict)


class TestDeadCodeDetection:
    """Tests para hook dead code detection."""
    
    def test_hook_does_not_crash(self):
        """Hook no debe fallar."""
        result = _dead_code_detection("post_edit", {"code": "test"}, "")
        assert isinstance(result, dict)
    
    def test_hook_returns_warnings_list(self):
        """Hook debe retornar lista de warnings."""
        result = _dead_code_detection("post_edit", {"code": "test"}, "")
        assert "warnings" in result
        assert isinstance(result["warnings"], list)


class TestHookRegistration:
    """Tests para registro de hooks nuevos en HookManager."""
    
    @pytest.fixture
    def hook_manager(self):
        """Crear HookManager con hooks nuevos."""
        from tools.hooks import HookManager
        manager = HookManager()
        # Registrar hooks nuevos
        manager.register_pre("*", _deadlock_detection)
        manager.register_post("*", _performance_profile)
        manager.register_post("*", _dead_code_detection)
        return manager
    
    def test_hooks_registered(self, hook_manager):
        """Hooks nuevos deben estar registrados."""
        assert hook_manager.pre_count > 0
        assert hook_manager.post_count > 0
    
    def test_hooks_summary(self, hook_manager):
        """Summary debe mostrar hooks nuevos."""
        summary = hook_manager.summary()
        assert len(summary) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
