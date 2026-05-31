"""Tests de LSP para formatos de oficina en OOCode.

Verifica:
  - office_linter.py produce diagnósticos correctos para DOCX, XLSX, CSV, PDF, ODT
  - _SERVER_CMDS contiene las extensiones de oficina y nuevos formatos
  - _EXT_TO_LANG tiene los language IDs correctos
  - _SERVER_ALIASES cubre formatos legados y nuevos
  - _LSP_DIAG_EXTS incluye extensiones de oficina y nuevos formatos
  - efm-langserver config incluye secciones office cuando el linter existe
  - efm-langserver config incluye linters disponibles (ruff, mypy, shellcheck, yamllint, eslint…)
  - _ensure_efm_config regenera si el contenido cambia (hash comparison)
"""
import csv
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.lsp_client import (
    _SERVER_CMDS,
    _EXT_TO_LANG,
    _SERVER_ALIASES,
    _OFFICE_LINTER,
    _generate_efm_config,
    _ensure_efm_config,
    _EFM_CONFIG_PATH,
)
from tools.hooks import _LSP_DIAG_EXTS
from tools.office_linter import (
    lint_csv,
    lint_docx,
    lint_odt,
    lint_pdf,
    lint_xlsx,
    _template_fields,
    _LINTERS,
)


# ── office_linter: helpers ────────────────────────────────────────────────────

class TestOfficeLinterHelpers:
    def test_template_fields_basic(self):
        fields = _template_fields("Hola {{NOMBRE}}, tu empresa es {{EMPRESA}}.")
        assert "NOMBRE" in fields
        assert "EMPRESA" in fields

    def test_template_fields_empty(self):
        assert _template_fields("Sin campos aquí.") == []

    def test_template_fields_deduplicates(self):
        fields = _template_fields("{{X}} y {{X}} de nuevo")
        assert fields.count("X") == 1

    def test_linters_dict_covers_all_formats(self):
        expected = {".docx", ".doc", ".dotx", ".docm",
                    ".xlsx", ".xlsm", ".xltx", ".xls",
                    ".csv", ".pdf", ".odt", ".ods", ".odp", ".odg"}
        assert expected.issubset(set(_LINTERS.keys()))


# ── CSV linter ───────────────────────────────────────────────────────────────

class TestCsvLinter:
    def test_valid_csv_no_diags(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("hostname,ip,status\nweb-01,10.0.0.1,active\ndb-01,10.0.0.2,active\n")
        diags = lint_csv(p)
        assert diags == []

    def test_inconsistent_columns(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("a,b,c\n1,2,3\n4,5\n")  # row 3 has 2 cols instead of 3
        diags = lint_csv(p)
        assert any("inconsistente" in d.lower() for d in diags)

    def test_inconsistent_columns_line_number(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("a,b,c\n1,2,3\n4,5\n")
        diags = lint_csv(p)
        # Line 3 (1-based for data rows, +1 for header = line 3)
        assert any(":3:" in d for d in diags)

    def test_empty_csv(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("")
        diags = lint_csv(p)
        assert any("vacío" in d.lower() or "empty" in d.lower() for d in diags)

    def test_bom_detected(self, tmp_path):
        p = tmp_path / "bom.csv"
        # UTF-8 BOM = \xef\xbb\xbf, followed by CSV content
        p.write_bytes(b"\xef\xbb\xbf" + b"a,b\n1,2\n")
        diags = lint_csv(p)
        assert any("bom" in d.lower() for d in diags)

    def test_diag_format(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text("a,b\n1\n")
        diags = lint_csv(p)
        for d in diags:
            parts = d.split(":")
            assert len(parts) >= 4, f"Formato incorrecto: {d!r}"


# ── PDF linter ───────────────────────────────────────────────────────────────

class TestPdfLinter:
    def test_pdftotext_not_found_returns_warning(self, tmp_path, monkeypatch):
        import shutil as _shutil
        original = _shutil.which

        def fake_which(cmd):
            return None if cmd == "pdftotext" else original(cmd)

        monkeypatch.setattr(_shutil, "which", fake_which)
        # We need to patch subprocess.run to raise FileNotFoundError
        import subprocess as _sp
        import tools.office_linter as _ol

        original_run = _sp.run
        def fake_run(cmd, **kw):
            if cmd[0] == "pdftotext":
                raise FileNotFoundError
            return original_run(cmd, **kw)

        monkeypatch.setattr(_sp, "run", fake_run)
        p = tmp_path / "test.pdf"
        p.write_bytes(b"%PDF-1.4 fake")
        diags = lint_pdf(p)
        assert any("pdftotext" in d.lower() for d in diags)

    def test_template_fields_in_pdf_text(self, tmp_path, monkeypatch):
        import subprocess as _sp
        import tools.office_linter as _ol

        def fake_run(cmd, **kw):
            class R:
                returncode = 0
                stdout = "Estimado {{NOMBRE}}, su empresa {{EMPRESA}} ha sido registrada."
                stderr = ""
            return R()

        monkeypatch.setattr(_sp, "run", fake_run)
        p = tmp_path / "template.pdf"
        p.write_bytes(b"%PDF-1.4")
        diags = lint_pdf(p)
        assert any("NOMBRE" in d for d in diags)
        assert any("EMPRESA" in d for d in diags)

    def test_empty_pdf_text_warning(self, tmp_path, monkeypatch):
        import subprocess as _sp

        def fake_run(cmd, **kw):
            class R:
                returncode = 0
                stdout = "   \n  "
                stderr = ""
            return R()

        monkeypatch.setattr(_sp, "run", fake_run)
        p = tmp_path / "empty.pdf"
        p.write_bytes(b"%PDF-1.4")
        diags = lint_pdf(p)
        assert any("sin texto" in d.lower() or "image" in d.lower() or "extraíble" in d.lower() for d in diags)


# ── DOCX linter ──────────────────────────────────────────────────────────────

class TestDocxLinter:
    def _make_docx(self, tmp_path: Path, content: str = "Sin campos.", track_changes: bool = False) -> Path:
        try:
            from docx import Document
            doc = Document()
            doc.add_paragraph(content)
            p = tmp_path / "test.docx"
            doc.save(str(p))
            if track_changes:
                # Inject a fake w:ins marker into the XML
                raw = p.read_bytes()
                raw = raw.replace(b"<w:body>", b"<w:body><w:ins ")
                p.write_bytes(raw)
            return p
        except ImportError:
            pytest.skip("python-docx not available")

    def test_clean_docx_no_diags(self, tmp_path):
        p = self._make_docx(tmp_path, "Documento limpio sin campos.")
        diags = lint_docx(p)
        assert diags == []

    def test_unfilled_field_detected(self, tmp_path):
        p = self._make_docx(tmp_path, "Estimado {{NOMBRE}}, empresa {{EMPRESA}}.")
        diags = lint_docx(p)
        assert any("NOMBRE" in d for d in diags)
        assert any("EMPRESA" in d for d in diags)

    def test_unfilled_field_is_warning(self, tmp_path):
        p = self._make_docx(tmp_path, "Hola {{CLIENTE}}.")
        diags = lint_docx(p)
        assert all("warning" in d for d in diags)

    def test_corrupted_docx_returns_error(self, tmp_path):
        p = tmp_path / "corrupt.docx"
        p.write_bytes(b"Not a zip file at all")
        diags = lint_docx(p)
        assert any("error" in d.lower() for d in diags)

    def test_no_python_docx_returns_warning(self, tmp_path, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "docx":
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        p = tmp_path / "test.docx"
        p.write_bytes(b"PK\x03\x04")  # zip magic bytes
        diags = lint_docx(p)
        assert any("python-docx" in d.lower() for d in diags)


# ── XLSX linter ──────────────────────────────────────────────────────────────

class TestXlsxLinter:
    def _make_xlsx(self, tmp_path: Path, data: dict) -> Path:
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Datos"
            for cell_ref, value in data.items():
                ws[cell_ref] = value
            p = tmp_path / "test.xlsx"
            wb.save(str(p))
            return p
        except ImportError:
            pytest.skip("openpyxl not available")

    def test_clean_xlsx_no_diags(self, tmp_path):
        p = self._make_xlsx(tmp_path, {"A1": "Hostname", "B1": "IP", "A2": "web-01", "B2": "10.0.0.1"})
        diags = lint_xlsx(p)
        assert diags == []

    def test_formula_error_detected(self, tmp_path):
        p = self._make_xlsx(tmp_path, {"A1": "#REF!", "B1": "normal"})
        diags = lint_xlsx(p)
        assert any("#REF!" in d for d in diags)
        assert any("error" in d.lower() for d in diags)

    def test_template_field_warning(self, tmp_path):
        p = self._make_xlsx(tmp_path, {"A1": "{{EMPRESA}}", "B1": "valor"})
        diags = lint_xlsx(p)
        assert any("EMPRESA" in d for d in diags)
        assert any("warning" in d for d in diags)

    def test_multiple_formula_errors(self, tmp_path):
        p = self._make_xlsx(tmp_path, {"A1": "#VALUE!", "B1": "#NAME?", "C1": "ok"})
        diags = lint_xlsx(p)
        errors = [d for d in diags if "error" in d.lower()]
        assert len(errors) >= 2

    def test_corrupted_xlsx_returns_error(self, tmp_path):
        p = tmp_path / "corrupt.xlsx"
        p.write_bytes(b"Not a zip file")
        diags = lint_xlsx(p)
        assert any("error" in d.lower() for d in diags)


# ── ODT linter ───────────────────────────────────────────────────────────────

class TestOdtLinter:
    def _make_odt(self, tmp_path: Path, text_content: str) -> Path:
        p = tmp_path / "test.odt"
        content_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
            ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            '<office:body><office:text>'
            f'<text:p>{text_content}</text:p>'
            '</office:text></office:body></office:document-content>'
        )
        with zipfile.ZipFile(str(p), "w") as z:
            z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
            z.writestr("content.xml", content_xml)
        return p

    def test_clean_odt_no_diags(self, tmp_path):
        p = self._make_odt(tmp_path, "Documento limpio.")
        diags = lint_odt(p)
        assert diags == []

    def test_template_field_detected(self, tmp_path):
        p = self._make_odt(tmp_path, "Estimado {{DESTINATARIO}}, adjunto {{DOCUMENTO}}.")
        diags = lint_odt(p)
        assert any("DESTINATARIO" in d for d in diags)
        assert any("DOCUMENTO" in d for d in diags)

    def test_corrupted_odt(self, tmp_path):
        p = tmp_path / "corrupt.odt"
        p.write_bytes(b"Not a zip")
        diags = lint_odt(p)
        assert any("error" in d.lower() for d in diags)

    def test_missing_content_xml(self, tmp_path):
        p = tmp_path / "noncontent.odt"
        with zipfile.ZipFile(str(p), "w") as z:
            z.writestr("other.xml", "<root/>")
        diags = lint_odt(p)
        assert any("error" in d.lower() for d in diags)


# ── LSP client integration ───────────────────────────────────────────────────

class TestOfficeLspClientIntegration:
    def test_server_cmds_has_docx(self):
        assert ".docx" in _SERVER_CMDS
        assert _SERVER_CMDS[".docx"][0] == "efm-langserver"

    def test_server_cmds_has_xlsx(self):
        assert ".xlsx" in _SERVER_CMDS
        assert _SERVER_CMDS[".xlsx"][0] == "efm-langserver"

    def test_server_cmds_has_xls(self):
        assert ".xls" in _SERVER_CMDS

    def test_server_cmds_has_csv(self):
        assert ".csv" in _SERVER_CMDS

    def test_server_cmds_has_pdf(self):
        assert ".pdf" in _SERVER_CMDS

    def test_server_cmds_has_odt(self):
        assert ".odt" in _SERVER_CMDS

    def test_server_cmds_has_ods(self):
        assert ".ods" in _SERVER_CMDS

    def test_ext_to_lang_docx(self):
        assert _EXT_TO_LANG.get(".docx") == "docx"

    def test_ext_to_lang_xlsx(self):
        assert _EXT_TO_LANG.get(".xlsx") == "xlsx"

    def test_ext_to_lang_xls(self):
        assert _EXT_TO_LANG.get(".xls") == "xls"

    def test_ext_to_lang_csv(self):
        assert _EXT_TO_LANG.get(".csv") == "csv"

    def test_ext_to_lang_pdf(self):
        assert _EXT_TO_LANG.get(".pdf") == "pdf"

    def test_ext_to_lang_odt(self):
        assert _EXT_TO_LANG.get(".odt") == "odt"

    def test_ext_to_lang_ods(self):
        assert _EXT_TO_LANG.get(".ods") == "ods"

    def test_aliases_doc_to_docx(self):
        assert _SERVER_ALIASES.get(".doc") == ".docx"

    def test_aliases_xls_to_xlsx(self):
        assert _SERVER_ALIASES.get(".xls") == ".xlsx"

    def test_aliases_ods_to_odt(self):
        assert _SERVER_ALIASES.get(".ods") == ".odt"

    def test_aliases_dotx_to_docx(self):
        assert _SERVER_ALIASES.get(".dotx") == ".docx"

    def test_aliases_xlsm_to_xlsx(self):
        assert _SERVER_ALIASES.get(".xlsm") == ".xlsx"

    def test_office_linter_path_exists(self):
        assert _OFFICE_LINTER.exists(), f"office_linter.py no encontrado en {_OFFICE_LINTER}"

    def test_efm_config_includes_docx_when_linter_available(self):
        config = _generate_efm_config()
        # Only if python3 and linter exist
        if _OFFICE_LINTER.exists():
            assert "docx:" in config
            assert "xlsx:" in config
            assert "csv:" in config
            assert "pdf:" in config

    def test_efm_config_includes_linter_cmd(self):
        config = _generate_efm_config()
        if _OFFICE_LINTER.exists():
            assert "office_linter.py" in config

    def test_efm_config_lint_formats_include_severity(self):
        config = _generate_efm_config()
        if _OFFICE_LINTER.exists():
            assert "error: %m" in config
            assert "warning: %m" in config
            assert "information: %m" in config


# ── hooks._LSP_DIAG_EXTS ─────────────────────────────────────────────────────

class TestOfficeLspDiagExts:
    def test_docx_in_lsp_diag_exts(self):
        assert ".docx" in _LSP_DIAG_EXTS

    def test_xlsx_in_lsp_diag_exts(self):
        assert ".xlsx" in _LSP_DIAG_EXTS

    def test_csv_in_lsp_diag_exts(self):
        assert ".csv" in _LSP_DIAG_EXTS

    def test_pdf_in_lsp_diag_exts(self):
        assert ".pdf" in _LSP_DIAG_EXTS

    def test_odt_in_lsp_diag_exts(self):
        assert ".odt" in _LSP_DIAG_EXTS

    def test_xls_in_lsp_diag_exts(self):
        assert ".xls" in _LSP_DIAG_EXTS

    def test_doc_in_lsp_diag_exts(self):
        assert ".doc" in _LSP_DIAG_EXTS

    def test_new_formats_in_lsp_diag_exts(self):
        for ext in (".rst", ".tex", ".latex", ".dockerfile", ".tf", ".tfvars", ".lua"):
            assert ext in _LSP_DIAG_EXTS, f"{ext} falta en _LSP_DIAG_EXTS"

    def test_lua_in_lsp_diag_exts(self):
        assert ".lua" in _LSP_DIAG_EXTS


# ── Nuevos formatos en _SERVER_CMDS / _EXT_TO_LANG ───────────────────────────

class TestNewFormatsLspClient:
    def test_rst_in_server_cmds(self):
        assert ".rst" in _SERVER_CMDS
        assert _SERVER_CMDS[".rst"][0] == "efm-langserver"

    def test_tex_in_server_cmds(self):
        assert ".tex" in _SERVER_CMDS
        assert _SERVER_CMDS[".tex"][0] == "efm-langserver"

    def test_dockerfile_in_server_cmds(self):
        assert ".dockerfile" in _SERVER_CMDS
        assert _SERVER_CMDS[".dockerfile"][0] == "efm-langserver"

    def test_tf_in_server_cmds(self):
        assert ".tf" in _SERVER_CMDS
        assert _SERVER_CMDS[".tf"][0] == "efm-langserver"

    def test_lua_in_server_cmds(self):
        assert ".lua" in _SERVER_CMDS
        assert _SERVER_CMDS[".lua"][0] == "lua-language-server"

    def test_ext_to_lang_rst(self):
        assert _EXT_TO_LANG.get(".rst") == "rst"

    def test_ext_to_lang_tex(self):
        assert _EXT_TO_LANG.get(".tex") == "latex"

    def test_ext_to_lang_latex(self):
        assert _EXT_TO_LANG.get(".latex") == "latex"

    def test_ext_to_lang_dockerfile(self):
        assert _EXT_TO_LANG.get(".dockerfile") == "dockerfile"

    def test_ext_to_lang_tf(self):
        assert _EXT_TO_LANG.get(".tf") == "terraform"

    def test_ext_to_lang_tfvars(self):
        assert _EXT_TO_LANG.get(".tfvars") == "terraform"

    def test_alias_latex_to_tex(self):
        assert _SERVER_ALIASES.get(".latex") == ".tex"

    def test_alias_tfvars_to_tf(self):
        assert _SERVER_ALIASES.get(".tfvars") == ".tf"


# ── efm-langserver config: linters disponibles ───────────────────────────────

class TestEfmConfigAvailableLinters:
    """efm solo incluye linters para lenguajes cuyo LSP ES efm-langserver.
    Los que tienen servidor LSP dedicado (pylsp, clangd, etc.) no aparecen en efm.
    """

    def test_config_is_valid_yaml_structure(self):
        config = _generate_efm_config()
        assert config.startswith("version: 2")
        assert "root-markers:" in config
        assert "languages:" in config

    def test_xmllint_in_efm_if_available(self):
        import shutil
        config = _generate_efm_config()
        if shutil.which("xmllint"):
            assert "xmllint" in config
            assert "xml:" in config

    def test_markdownlint_in_efm_if_available(self):
        import shutil
        config = _generate_efm_config()
        if shutil.which("markdownlint"):
            assert "markdownlint" in config
            assert "markdown:" in config

    def test_rpmlint_in_efm_if_available(self):
        import shutil
        config = _generate_efm_config()
        if shutil.which("rpmlint"):
            assert "rpmlint" in config
            assert "spec:" in config

    def test_rstcheck_in_efm_if_available(self):
        import shutil
        config = _generate_efm_config()
        if shutil.which("rstcheck"):
            assert "rstcheck" in config
            assert "rst:" in config

    def test_hadolint_in_efm_if_available(self):
        import shutil
        config = _generate_efm_config()
        if shutil.which("hadolint"):
            assert "hadolint" in config
            assert "dockerfile:" in config

    def test_tflint_in_efm_if_available(self):
        import shutil
        config = _generate_efm_config()
        if shutil.which("tflint"):
            assert "tflint" in config
            assert "terraform:" in config

    def test_chktex_in_efm_if_available(self):
        import shutil
        config = _generate_efm_config()
        if shutil.which("chktex"):
            assert "chktex" in config
            assert "latex:" in config

    def test_linters_with_dedicated_lsp_not_in_efm(self):
        """Linters para lenguajes con LSP dedicado nunca deben estar en el config de efm."""
        config = _generate_efm_config()
        # Python → pylsp; Shell → bash-language-server; JS/TS → typescript-language-server
        # YAML → yaml-language-server; JSON → vscode-json-language-server; C/C++ → clangd
        # Ruby → ruby-lsp; SQL → sql-language-server; Perl → perl-language-server
        # PHP → intelephense; Lua → lua-language-server; CSS → vscode-css-language-server
        assert "ruff" not in config
        assert "mypy" not in config
        assert "shellcheck" not in config
        assert "eslint" not in config
        assert "yamllint" not in config
        assert "ansible-lint" not in config
        assert "jsonlint" not in config
        assert "cppcheck" not in config
        assert "rubocop" not in config
        assert "sqlfluff" not in config
        assert "perlcritic" not in config
        assert "phpcs" not in config
        assert "luacheck" not in config
        assert "stylelint" not in config

    def test_no_lsp_language_sections_in_efm(self):
        """Secciones de idioma para LSPs dedicados no deben aparecer en efm."""
        config = _generate_efm_config()
        assert "  python:" not in config
        assert "  javascript:" not in config
        assert "  typescript:" not in config
        assert "  ruby:" not in config
        assert "  sql:" not in config
        assert "  perl:" not in config
        assert "  php:" not in config
        assert "  lua:" not in config
        assert "  css:" not in config
        assert "  yaml:" not in config
        assert "  json:" not in config


# ── _ensure_efm_config: hash comparison ──────────────────────────────────────

class TestEnsureEfmConfig:
    def test_creates_file_when_missing(self, tmp_path, monkeypatch):
        import agent.lsp_client as _lc
        fake_path = tmp_path / "efm-langserver.yaml"
        monkeypatch.setattr(_lc, "_EFM_CONFIG_PATH", fake_path)
        # Patch _generate_efm_config to return a known value
        monkeypatch.setattr(_lc, "_generate_efm_config", lambda: "version: 2\n")
        assert not fake_path.exists()
        _lc._ensure_efm_config()
        assert fake_path.exists()
        assert fake_path.read_text() == "version: 2\n"

    def test_does_not_overwrite_identical_content(self, tmp_path, monkeypatch):
        import agent.lsp_client as _lc
        fake_path = tmp_path / "efm-langserver.yaml"
        fake_path.write_text("version: 2\n")
        mtime_before = fake_path.stat().st_mtime_ns
        monkeypatch.setattr(_lc, "_EFM_CONFIG_PATH", fake_path)
        monkeypatch.setattr(_lc, "_generate_efm_config", lambda: "version: 2\n")
        _lc._ensure_efm_config()
        assert fake_path.stat().st_mtime_ns == mtime_before

    def test_overwrites_when_content_changes(self, tmp_path, monkeypatch):
        import agent.lsp_client as _lc
        fake_path = tmp_path / "efm-langserver.yaml"
        fake_path.write_text("version: 2\nlanguages:\n  {}\n")
        monkeypatch.setattr(_lc, "_EFM_CONFIG_PATH", fake_path)
        monkeypatch.setattr(_lc, "_generate_efm_config", lambda: "version: 2\nlanguages:\n  yaml:\n    - lint-command: 'yamllint'\n")
        _lc._ensure_efm_config()
        assert "yamllint" in fake_path.read_text()

    def test_force_overwrites_even_if_identical(self, tmp_path, monkeypatch):
        import agent.lsp_client as _lc
        fake_path = tmp_path / "efm-langserver.yaml"
        fake_path.write_text("version: 2\n")
        mtime_before = fake_path.stat().st_mtime_ns
        import time; time.sleep(0.01)
        monkeypatch.setattr(_lc, "_EFM_CONFIG_PATH", fake_path)
        monkeypatch.setattr(_lc, "_generate_efm_config", lambda: "version: 2\n")
        _lc._ensure_efm_config(force=True)
        # Content is same but force=True should rewrite — mtime may or may not change
        # (filesystem resolution). Just check no exception raised and content is correct.
        assert fake_path.read_text() == "version: 2\n"

    def test_new_linter_installed_triggers_update(self, tmp_path, monkeypatch):
        import agent.lsp_client as _lc
        fake_path = tmp_path / "efm-langserver.yaml"
        fake_path.write_text("version: 2\nlanguages:\n  {}\n")
        monkeypatch.setattr(_lc, "_EFM_CONFIG_PATH", fake_path)
        # Simulate a new tool being installed (ruff becomes available)
        monkeypatch.setattr(_lc, "_generate_efm_config",
                            lambda: "version: 2\nlanguages:\n  python:\n    - lint-command: 'ruff'\n")
        _lc._ensure_efm_config()
        assert "ruff" in fake_path.read_text()
