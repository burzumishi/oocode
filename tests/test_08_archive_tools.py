"""Tests de tools de archivos comprimidos: archive_create, archive_list, archive_extract.

Nota: las tools de archivo usan 'sources' (string separado por espacios) y no _safe_path.
"""
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_archive_create,
    _tool_archive_list,
    _tool_archive_extract,
)


class TestArchiveCreate:
    def test_creates_tar_gz(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "file1.txt").write_text("hello")
        archive = tmp_path / "out.tar.gz"
        # 'sources' is space-separated string, not a list
        result = _tool_archive_create({
            "archive": str(archive),
            "sources": str(src),
            "compress": "gz",
        })
        assert archive.exists(), f"Archive not created. Result: {result}"

    def test_creates_zip(self, tmp_path):
        src = tmp_path / "zipsrc"
        src.mkdir()
        (src / "data.py").write_text("x = 1\n")
        archive = tmp_path / "out.zip"
        result = _tool_archive_create({
            "archive":  str(archive),
            "sources":  str(src),
            "compress": "zip",
        })
        assert archive.exists(), f"Zip not created. Result: {result}"

    def test_missing_sources(self, tmp_path):
        result = _tool_archive_create({
            "archive":  str(tmp_path / "out.tar.gz"),
            "sources":  "",
        })
        assert "Error" in result or "proporciona" in result


class TestArchiveList:
    def test_lists_tar_gz(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "listed.txt").write_text("content")
        archive = tmp_path / "list_test.tar.gz"
        _tool_archive_create({"archive": str(archive), "sources": str(src), "compress": "gz"})
        assert archive.exists()
        result = _tool_archive_list({"archive": str(archive)})
        assert "listed.txt" in result

    def test_nonexistent_archive(self, tmp_path):
        result = _tool_archive_list({"archive": str(tmp_path / "nonexistent.tar.gz")})
        assert "Error" in result or "no existe" in result or "not found" in result.lower()


class TestArchiveExtract:
    def test_extracts_tar_gz(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "extracted.txt").write_text("hello extract")
        archive = tmp_path / "extract_test.tar.gz"
        _tool_archive_create({"archive": str(archive), "sources": str(src), "compress": "gz"})
        assert archive.exists()
        dest = tmp_path / "dest"
        dest.mkdir()
        result = _tool_archive_extract({
            "archive":     str(archive),
            "destination": str(dest),
        })
        extracted_files = list(dest.rglob("*"))
        assert len(extracted_files) > 0, f"No files extracted. Result: {result}"
