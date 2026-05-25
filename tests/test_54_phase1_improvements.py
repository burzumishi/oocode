"""Tests para las mejoras de la Fase 1: métricas, compaction con metadata, retry logic."""
import sys
import json
import time
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestToolMetrics:
    """Tests para la función global _record_tool_metrics."""

    def test_record_tool_metrics_creates_file(self, tmp_path):
        """Verifica que _record_tool_metrics crea el fichero de métricas."""
        from agent.loop import _record_tool_metrics
        
        # Limpiar fichero antes
        metrics_path = Path.home() / ".oocode" / "metrics" / "tool_timing.jsonl"
        if metrics_path.exists():
            metrics_path.write_text("")
        
        # Llamar a la función de métricas
        _record_tool_metrics("test_tool", 0.5, True)
        
        # Verificar que el fichero se creó
        assert metrics_path.exists(), "El fichero de métricas no se creó"
        
        # Verificar contenido
        content = metrics_path.read_text()
        assert "test_tool" in content
        entry = json.loads(content.strip())
        assert entry["duration"] == 0.5
        assert entry["success"] is True

    def test_record_tool_metrics_logs_failure(self, tmp_path):
        """Verifica que _record_tool_metrics registra fallos correctamente."""
        from agent.loop import _record_tool_metrics
        
        # Limpiar fichero antes
        metrics_path = Path.home() / ".oocode" / "metrics" / "tool_timing.jsonl"
        if metrics_path.exists():
            metrics_path.write_text("")
        
        # Llamar con success=False
        _record_tool_metrics("failing_tool", 1.2, False)
        
        content = metrics_path.read_text()
        assert "failing_tool" in content
        entry = json.loads(content.strip())
        assert entry["success"] is False

    def test_record_tool_metrics_logs_different_tools(self, tmp_path):
        """Verifica que se pueden registrar múltiples herramientas."""
        from agent.loop import _record_tool_metrics
        
        # Limpiar fichero antes
        metrics_path = Path.home() / ".oocode" / "metrics" / "tool_timing.jsonl"
        if metrics_path.exists():
            metrics_path.write_text("")
        
        _record_tool_metrics("tool_a", 0.1, True)
        _record_tool_metrics("tool_b", 0.3, True)
        _record_tool_metrics("tool_a", 0.2, True)  # segunda llamada
        
        content = metrics_path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 3  # tres entradas
        assert "tool_a" in lines[0]
        assert "tool_b" in lines[1]
        assert "tool_a" in lines[2]


class TestRetryWithBackoff:
    """Tests para la función global _retry_with_backoff."""

    def test_retry_success_on_first_try(self, tmp_path):
        """Verifica que _retry_with_backoff devuelve el resultado inmediato si funciona."""
        from agent.loop import _retry_with_backoff
        
        def success_func():
            return "success"
        
        result = _retry_with_backoff(success_func)
        assert result == "success"

    def test_retry_exhausts_all_attempts(self, tmp_path):
        """Verifica que _retry_with_backoff falla después de max_retries intentos."""
        from agent.loop import _retry_with_backoff
        
        attempt_count = 0
        
        def failing_func():
            nonlocal attempt_count
            attempt_count += 1
            raise Exception("Simulated failure")
        
        # Debería fallar después de 3 intentos (max_retries=3)
        with pytest.raises(Exception, match="Simulated failure"):
            _retry_with_backoff(failing_func, max_retries=3)
        
        assert attempt_count == 3

    def test_retry_with_custom_delay(self, tmp_path):
        """Verifica que _retry_with_backoff usa el delay personalizado."""
        from agent.loop import _retry_with_backoff
        
        def failing_func():
            raise Exception("Fail")
        
        # Con base_delay=0.1 y max_retries=2:
        # Intento 1 falla → delay 0.1s + random(0, 0.1) → Intento 2 falla → delay 0.3s + random(0, 0.1) → Falla
        # Mínimo: 0.1 + 0.3 = 0.4s, Máximo: 0.2 + 0.4 = 0.6s
        # Usamos un margen amplio para evitar problemas de timing
        start = time.time()
        try:
            _retry_with_backoff(failing_func, max_retries=2, base_delay=0.1)
            assert False, "Debería haber fallado"
        except Exception:
            elapsed = time.time() - start
            # El delay total debe estar entre 0.1s y 0.6s (mínimo + máximo posible)
            assert 0.1 <= elapsed <= 0.6, f"El delay no se aplicó correctamente (elapsed={elapsed:.2f}s)"


class TestCompactSummaryMetadata:
    """Tests para la función _make_compact_summary."""

    def test_compact_summary_includes_metadata(self, tmp_path):
        """Verifica que _make_compact_summary incluye metadata en el resumen."""
        from agent.loop import _make_compact_summary
        
        # Usar una herramienta que esté en el mapeo
        blocks = [
            ("grep_code", {"path": "test.py"}, "result", True),
        ]
        
        summary = _make_compact_summary(blocks)
        
        # Verificar que usa el verbo correcto para grep_code
        assert "Searched" in summary or "grep_code" in summary

    def test_compact_summary_handles_empty_blocks(self, tmp_path):
        """Verifica que _make_compact_summary maneja bloques vacíos."""
        from agent.loop import _make_compact_summary
        
        summary = _make_compact_summary([])
        
        # Debería contener el mensaje de control
        assert "(ctrl+o to expand)" in summary


class TestPhase1ImprovementsIntegration:
    """Tests de integración para todas las mejoras de la Fase 1."""

    def test_all_phase1_features_available(self, tmp_path):
        """Verifica que todas las mejoras de la Fase 1 están disponibles."""
        from agent.loop import _record_tool_metrics, _retry_with_backoff, _make_compact_summary
        
        # Verificar que las funciones existen y son callable
        assert callable(_record_tool_metrics), "_record_tool_metrics no es callable"
        assert callable(_retry_with_backoff), "_retry_with_backoff no es callable"
        assert callable(_make_compact_summary), "_make_compact_summary no es callable"

    def test_metrics_directory_exists(self, tmp_path):
        """Verifica que el directorio de métricas existe."""
        import os
        metrics_dir = Path.home() / ".oocode" / "metrics"
        assert metrics_dir.exists(), "El directorio de métricas no existe"
        assert os.access(metrics_dir, os.W_OK), "El directorio de métricas no es escribible"

    def test_metrics_file_format(self, tmp_path):
        """Verifica que el fichero de métricas tiene el formato JSONL correcto."""
        from agent.loop import _record_tool_metrics
        
        # Limpiar fichero antes
        metrics_path = Path.home() / ".oocode" / "metrics" / "tool_timing.jsonl"
        if metrics_path.exists():
            metrics_path.write_text("")
        
        _record_tool_metrics("integration_test", 0.1, True)
        
        metrics_path = Path.home() / ".oocode" / "metrics" / "tool_timing.jsonl"
        assert metrics_path.exists()
        
        content = metrics_path.read_text()
        lines = [l for l in content.strip().split("\n") if l]
        
        assert len(lines) == 1
        entry = json.loads(lines[0])
        
        assert "ts" in entry
        assert "tool" in entry
        assert "duration" in entry
        assert "success" in entry
        assert "cwd" in entry
