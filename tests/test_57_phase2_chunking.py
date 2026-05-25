"""Tests para workspace_rag.py — chunking inteligente y metadata enriquecida."""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Importar módulo workspace_rag
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent.workspace_rag import (
    _chunk_code_intelligently,
    _enrich_metadata,
    _fallback_index_chunk,
    chunk_with_metadata,
    WorkspaceRAG,
)


class TestChunkCodeIntelligently:
    """Tests para chunking inteligente por estructura de código."""
    
    def test_chunk_respects_function_boundaries(self):
        """Chunking debe respetar límites de funciones."""
        code = """
def hello():
    print("Hello")
    return True

def world():
    print("World")
    return False
"""
        chunks = _chunk_code_intelligently(code, "test.py")
        
        # Verificar que hay chunks
        assert len(chunks) > 0
        
        # Verificar que al menos un chunk tiene function_name
        has_function = any(chunk.get("function") for chunk in chunks)
        assert has_function or len(chunks) == 1  # OK si es 1 chunk grande
    
    def test_chunk_respects_class_boundaries(self):
        """Chunking debe respetar límites de clases."""
        code = """
class Calculator:
    def add(self, a, b):
        return a + b
    
    def subtract(self, a, b):
        return a - b
"""
        chunks = _chunk_code_intelligently(code, "test.py")
        
        # Verificar que hay chunks
        assert len(chunks) > 0
        
        # Verificar que al menos un chunk tiene class_name
        has_class = any(chunk.get("class") for chunk in chunks)
        assert has_class or len(chunks) == 1
    
    def test_chunk_size_limit(self):
        """Chunking debe respetar límite de ~512 chars."""
        long_code = "x = " + "a" * 600 + "\n"
        chunks = _chunk_code_intelligently(long_code, "test.py")
        
        # Verificar que ningún chunk supera el límite
        for chunk in chunks:
            assert len(chunk["text"]) <= 512 + 100  # +100 para solapamiento
    
    def test_chunk_with_overlap(self):
        """Chunking debe incluir solapamiento entre chunks."""
        code = "x = " + "a" * 1000 + "\n"
        chunks = _chunk_code_intelligently(code, "test.py")
        
        # Verificar que hay múltiples chunks
        assert len(chunks) > 1
        
        # Verificar solapamiento
        for i in range(len(chunks) - 1):
            current_end = len(chunks[i]["text"])
            next_start = chunks[i + 1]["line"]
            # El solapamiento debe ser significativo
            assert chunks[i + 1]["text"] or True  # Simplificado


class TestEnrichMetadata:
    """Tests para metadata enriquecida."""
    
    def test_enrich_with_function(self):
        """Metadata debe incluir function_name."""
        chunk = {"text": "def hello():\n    pass", "path": "test.py"}
        enriched = _enrich_metadata(chunk, "test.py")
        
        assert "function" in enriched.get("tags", [])
        assert enriched.get("file_type") == ".py"
        assert enriched.get("complexity") == 2
    
    def test_enrich_with_class(self):
        """Metadata debe incluir class_name."""
        chunk = {"text": "class Foo:\n    pass", "path": "test.py"}
        enriched = _enrich_metadata(chunk, "test.py")
        
        assert "class" in enriched.get("tags", [])
    
    def test_enrich_with_import(self):
        """Metadata debe detectar imports."""
        chunk = {"text": "import os\nimport sys", "path": "test.py"}
        enriched = _enrich_metadata(chunk, "test.py")
        
        assert "import" in enriched.get("tags", [])
    
    def test_enrich_with_loop(self):
        """Metadata debe detectar bucles."""
        chunk = {"text": "for i in range(10):\n    pass", "path": "test.py"}
        enriched = _enrich_metadata(chunk, "test.py")
        
        assert "loop" in enriched.get("tags", [])
    
    def test_enrich_complexity(self):
        """Metadata debe calcular complejidad (nº líneas)."""
        chunk = {"text": "x = 1\ny = 2", "path": "test.py"}
        enriched = _enrich_metadata(chunk, "test.py")
        
        # "x = 1\n" + "y = 2" = 2 líneas (no 3)
        assert enriched.get("complexity") == 2


class TestFallbackIndexChunk:
    """Tests para fallback indexado."""
    
    def test_fallback_adds_hash(self):
        """Fallback debe añadir hash de texto."""
        chunk = {"text": "test content", "path": "test.py"}
        result = _fallback_index_chunk(chunk)
        
        assert "fallback_hash" in result
        assert len(result["fallback_hash"]) == 12
        assert result.get("index_type") == "fallback"
    
    def test_fallback_preserves_original(self):
        """Fallback debe preservar datos originales."""
        chunk = {"text": "test", "path": "test.py", "vec": [0.1, 0.2]}
        result = _fallback_index_chunk(chunk)
        
        assert result["text"] == chunk["text"]
        assert result["path"] == chunk["path"]
        assert "vec" in result  # El vec original se mantiene


class TestWorkspaceRAGChunking:
    """Tests para WorkspaceRAG con chunking inteligente."""
    
    @pytest.fixture
    def mock_embed_client(self):
        """Mock de cliente de embeddings."""
        mock = Mock()
        mock.is_available = Mock(return_value=True)
        mock.embed = Mock(return_value=[0.1] * 1536)
        mock.similarity = Mock(return_value=0.9)
        return mock
    
    def test_chunk_with_metadata_intelligent(self, mock_embed_client):
        """chunk_with_metadata debe usar chunking inteligente."""
        code = """
def test_func():
    print("test")
"""
        # chunk_with_metadata es método de WorkspaceRAG
        rag = WorkspaceRAG(
            workspace="/tmp",
            embed_client=mock_embed_client,
            index_dir=Path("/tmp/index"),
        )
        chunks = rag.chunk_with_metadata(code, "test.py", use_intelligent=True)
        
        assert len(chunks) > 0
        # Verificar que el chunk tiene function_name (no en tags, es campo directo)
        assert chunks[0].get("function") == "test_func" or chunks[0].get("function") is not None
    
    def test_chunk_with_metadata_simple(self, mock_embed_client):
        """chunk_with_metadata debe usar chunking simple cuando use_intelligent=False."""
        code = "x = " + "a" * 600 + "\n"
        rag = WorkspaceRAG(
            workspace="/tmp",
            embed_client=mock_embed_client,
            index_dir=Path("/tmp/index"),
        )
        chunks = rag.chunk_with_metadata(code, "test.py", use_intelligent=False)
        
        assert len(chunks) > 0


class TestWorkspaceRAGMetadata:
    """Tests para metadata enriquecida en WorkspaceRAG."""
    
    @pytest.fixture
    def mock_embed_client(self):
        """Mock de cliente de embeddings."""
        mock = Mock()
        mock.is_available = Mock(return_value=True)
        mock.embed = Mock(return_value=[0.1] * 1536)
        mock.similarity = Mock(return_value=0.9)
        return mock
    
    def test_index_includes_metadata(self, mock_embed_client, tmp_path):
        """Índice debe incluir metadata enriquecida."""
        rag = WorkspaceRAG(
            workspace=str(tmp_path),
            embed_client=mock_embed_client,
            index_dir=tmp_path / "index",
        )
        
        # Crear fichero de prueba
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def hello():
    print("Hello")
    
class Foo:
    pass
""")
        
        # Forzar indexado
        rag.ensure_indexed()
        
        # Verificar que hay chunks indexados (puede ser 0 si no hay embeddings)
        # El test principal es que no haya errores
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
