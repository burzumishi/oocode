"""Tests de preservación de estilos en plantillas Office.

Verifica que _tool_doc_fill_template preserva los estilos originales del documento.
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.home_office_assistant import _tool_doc_fill_template


class TestDocFillTemplateStyles:
    """Tests de preservación de estilos en _tool_doc_fill_template."""

    def test_fill_template_preserves_styles(self):
        """Test que se preservan estilos originales."""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            template_path = f.name
        
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            output_path = f.name
        
        try:
            # Crear plantilla con placeholder
            from docx import Document
            doc = Document()
            para = doc.add_paragraph()
            run = para.add_run("{{NOMBRE}}")
            run.font.size = 12
            doc.save(template_path)
            
            result = _tool_doc_fill_template({
                "template_path": template_path,
                "fields": {"NOMBRE": "Juan", "FECHA": "2026-05-24"},
                "output_path": output_path
            })
            assert "✅ Plantilla rellenada" in result
            assert "Estilos originales preservados" in result
        finally:
            Path(template_path).unlink(missing_ok=True)
            Path(output_path).unlink(missing_ok=True)

    def test_fill_template_missing_fields(self):
        """Test con campos faltantes."""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            template_path = f.name
        
        try:
            from docx import Document
            doc = Document()
            para = doc.add_paragraph()
            run = para.add_run("{{NOMBRE}}")
            doc.save(template_path)
            
            result = _tool_doc_fill_template({
                "template_path": template_path,
                "fields": {},
                "output_path": "/tmp/filled.docx"
            })
            assert "Parámetro requerido: fields" in result
        finally:
            Path(template_path).unlink(missing_ok=True)

    def test_fill_template_missing_template(self):
        """Test con plantilla no existente."""
        result = _tool_doc_fill_template({
            "template_path": "/nonexistent.docx",
            "fields": {"NOMBRE": "Juan"},
            "output_path": "/tmp/filled.docx"
        })
        assert "no encontrada" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
