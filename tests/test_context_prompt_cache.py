"""Tests de la caché SQLite de embeddings (EmbeddingClient + _DiskCache)."""
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.embeddings import EmbeddingClient, _DiskCache


def _make_client(tmp_dir: str, enabled: bool = True, max_e: int = 5) -> EmbeddingClient:
    return EmbeddingClient(
        host="http://localhost:11434",
        model="test-model:latest",
        max_input_chars=512,
        disk_cache_enabled=enabled,
        disk_cache_dir=tmp_dir,
        disk_cache_max=max_e,
    )


class TestDiskCacheUnit:
    """Tests unitarios de _DiskCache (independientes de EmbeddingClient)."""

    def _cache(self, tmp: str, max_e: int = 10) -> _DiskCache:
        return _DiskCache(Path(tmp) / "test.db", max_e)

    def test_put_and_get_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            dc = self._cache(tmp)
            vec = [0.1, 0.2, 0.3, 0.4]
            dc.put("k1", vec)
            result = dc.get("k1")
            assert result == pytest.approx(vec)

    def test_get_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            dc = self._cache(tmp)
            assert dc.get("nonexistent") is None

    def test_count_reflects_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            dc = self._cache(tmp)
            dc.put("a", [1.0])
            dc.put("b", [2.0])
            assert dc.count() == 2

    def test_eviction_respects_max(self):
        with tempfile.TemporaryDirectory() as tmp:
            dc = self._cache(tmp, max_e=3)
            for i in range(6):
                dc.put(f"key{i}", [float(i)])
            assert dc.count() <= 3

    def test_upsert_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            dc = self._cache(tmp)
            dc.put("k", [1.0, 2.0])
            dc.put("k", [3.0, 4.0])
            assert dc.count() == 1
            assert dc.get("k") == pytest.approx([3.0, 4.0])

    def test_get_updates_lru_timestamp(self):
        """El vector accedido más recientemente sobrevive a la eviction."""
        with tempfile.TemporaryDirectory() as tmp:
            dc = self._cache(tmp, max_e=2)
            dc.put("old", [0.0])
            dc.put("mid", [1.0])
            # Tocar "old" para que sea más reciente que "mid"
            dc.get("old")
            # Insertar tercero → evicta "mid" (seen más antigua)
            dc.put("new", [2.0])
            assert dc.get("old") is not None
            assert dc.get("new") is not None
            assert dc.get("mid") is None

    def test_db_file_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            _DiskCache(db, 10)
            assert db.exists()

    def test_concurrent_writes_are_safe(self):
        """Múltiples hilos escribiendo simultáneamente no corrompen la BD."""
        with tempfile.TemporaryDirectory() as tmp:
            dc = self._cache(tmp, max_e=200)
            errors: list[Exception] = []

            def _write(n: int) -> None:
                try:
                    dc.put(f"key{n}", [float(n)] * 8)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=_write, args=(i,)) for i in range(50)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors
            assert dc.count() == 50

    def test_binary_storage_smaller_than_json(self):
        """El BLOB float64 ocupa menos que JSON para vectores con decimales reales."""
        import json, struct, math
        # Valores con muchos decimales significativos, como embeddings reales
        vec = [math.sin(i * 0.1) / (i + 1) for i in range(768)]
        blob = struct.pack(f"{len(vec)}d", *vec)
        json_bytes = json.dumps(vec).encode()
        assert len(blob) < len(json_bytes)


class TestEmbeddingClientDiskCache:
    """Tests de integración entre EmbeddingClient y _DiskCache."""

    def test_db_file_created_in_cache_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_client(tmp)
            db = Path(tmp) / "test-model_latest.db"
            assert db.exists()

    def test_disabled_cache_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            ec = _make_client(tmp, enabled=False)
            assert ec._disk_cache is None

    def test_disk_put_and_get_via_wrappers(self):
        with tempfile.TemporaryDirectory() as tmp:
            ec = _make_client(tmp)
            vec = [0.5, 0.6, 0.7]
            ec._disk_put("mykey", vec)
            result = ec._disk_get("mykey")
            assert result == pytest.approx(vec)

    def test_disk_get_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            ec = _make_client(tmp)
            assert ec._disk_get("nothere") is None

    def test_eviction_via_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            ec = _make_client(tmp, max_e=3)
            for i in range(6):
                ec._disk_put(f"k{i}", [float(i)])
            assert ec.disk_cache_stats()["entries"] <= 3

    def test_embed_misses_ram_hits_disk(self):
        """Tras primer embed, un segundo cliente (RAM fría) lo lee del disco."""
        with tempfile.TemporaryDirectory() as tmp:
            ec1 = _make_client(tmp)
            vec = [1.0, 2.0, 3.0]
            ec1._call_api = MagicMock(return_value=vec)
            ec1._available = True
            ec1.embed("hello")

            # Nuevo cliente: RAM vacía, disco caliente
            ec2 = _make_client(tmp)
            ec2._call_api = MagicMock()
            ec2._available = True
            result = ec2.embed("hello")

            ec2._call_api.assert_not_called()
            assert result == pytest.approx(vec)

    def test_embed_warms_ram_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            ec = _make_client(tmp)
            text = "warm me"
            key = ec._cache_key(text[:512])
            vec = [0.9, 0.8]
            ec._disk_put(key, vec)
            ec._call_api = MagicMock()
            ec._available = True
            result = ec.embed(text)
            ec._call_api.assert_not_called()
            assert result == pytest.approx(vec)
            # RAM caliente tras disk hit
            assert ec._cache_get(key) is not None

    def test_embed_persists_to_disk_after_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            ec = _make_client(tmp)
            vec = [1.0, 2.0, 3.0]
            ec._call_api = MagicMock(return_value=vec)
            ec._available = True
            ec.embed("persist me")
            key = ec._cache_key("persist me")
            assert ec._disk_get(key) == pytest.approx(vec)

    def test_disk_cache_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            ec = _make_client(tmp)
            ec._disk_put("x", [1.0])
            ec._disk_put("y", [2.0])
            stats = ec.disk_cache_stats()
            assert stats["enabled"] is True
            assert stats["entries"] == 2
            assert stats["max"] == 5
            assert "path" in stats

    def test_cache_stats_includes_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            ec = _make_client(tmp)
            s = ec.cache_stats()
            assert "disk" in s
            assert s["disk"]["enabled"] is True
            assert "ram_size" in s
            assert "ram_max" in s

    def test_close_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            ec = _make_client(tmp)
            ec.close()  # no debe lanzar excepción


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
