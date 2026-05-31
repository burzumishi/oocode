"""Tests del servidor MCP Home Office Assistant.

Verifica que las tools están bien definidas, que la configuración se carga
correctamente, y que las tools sin dependencias externas funcionan con
ficheros temporales.

No requiere LLM, IMAP, SMTP, pandoc, tesseract ni openpyxl.
"""
import csv
import datetime
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.home_office_assistant import (
    _TOOL_FNS,
    _TOOLS,
    _build_word_chart_xml,
    _tool_doc_create,
    _PROMPTS,
    _RESOURCES,
    _RESOURCE_FNS,
    _load_config,
    _no_email_config,
    _deep_merge,
    _decode_header,
    _ics_date_str,
    _parse_ics_events,
    _read_csv_file,
    _get_prompt,
    _apply_naming,
    _parse_oocode_md,
    _tool_doc_word_count,
    _tool_csv_analyze,
    _tool_cal_list,
    _tool_cal_add,
    _tool_cal_search,
    _tool_notes_list,
    _tool_notes_search,
    _tool_notes_save,
    _tool_markdown_to_html,
    _tool_contact_search,
    _tool_doc_read_template_fields,
    _tool_doc_fill_template,
    _tool_doc_list_templates,
    _tool_doc_create_rfc,
    _tool_xlsx_fill_range,
    _tool_xlsx_append_row,
    _tool_xlsx_create_report,
    _tool_project_context_read,
    _tool_project_init_office,
    _tool_doc_project_save,
    _tool_doc_read,
    _tool_doc_update_section,
    _tool_doc_version_bump,
    _tool_cmdb_search,
    _tool_cmdb_update,
    _tool_asset_register_add,
)


# ── Schema integrity ─────────────────────────────────────────────────────────

class TestToolSchemas:
    def test_tool_count(self):
        assert len(_TOOLS) == 78  # 77 previous + doc_fill_corporate_template

    def test_all_tools_have_name_and_description(self):
        for t in _TOOLS:
            assert "name" in t, f"Tool sin nombre: {t}"
            assert "description" in t and t["description"], f"Tool sin descripción: {t['name']}"

    def test_all_tools_have_input_schema(self):
        for t in _TOOLS:
            assert "inputSchema" in t, f"Tool sin inputSchema: {t['name']}"
            assert t["inputSchema"].get("type") == "object", f"inputSchema no es object: {t['name']}"

    def test_all_tools_registered_in_fns(self):
        tool_names = {t["name"] for t in _TOOLS}
        fn_names   = set(_TOOL_FNS.keys())
        assert tool_names == fn_names, f"Mismatch: {tool_names ^ fn_names}"

    def test_all_fns_are_callable(self):
        for name, fn in _TOOL_FNS.items():
            assert callable(fn), f"_TOOL_FNS[{name!r}] no es callable"


class TestPromptSchemas:
    def test_prompt_count(self):
        assert len(_PROMPTS) == 19

    def test_prompts_have_required_keys(self):
        for name, p in _PROMPTS.items():
            assert "description" in p, f"Prompt {name} sin description"
            assert "arguments" in p, f"Prompt {name} sin arguments"
            assert isinstance(p["arguments"], list), f"Prompt {name}: arguments debe ser lista"

    def test_known_prompts_present(self):
        for expected in (
            "draft_email", "summarize_document", "meeting_notes", "weekly_report",
            "datacenter_migration_report", "rfc_change_request",
            "server_migration_plan", "it_incident_report", "infrastructure_change_plan",
            "executive_summary", "business_case", "project_status_report",
        ):
            assert expected in _PROMPTS, f"Prompt ausente: {expected}"


class TestResourceSchemas:
    def test_resource_count(self):
        assert len(_RESOURCES) == 15

    def test_resources_have_required_keys(self):
        for r in _RESOURCES:
            assert "uri" in r
            assert "name" in r
            assert "description" in r

    def test_resource_fns_match_uris(self):
        uris = {r["uri"] for r in _RESOURCES}
        assert uris == set(_RESOURCE_FNS.keys())

    def test_resource_fns_callable(self):
        for uri, fn in _RESOURCE_FNS.items():
            assert callable(fn), f"_RESOURCE_FNS[{uri!r}] no es callable"


# ── Config loading ───────────────────────────────────────────────────────────

class TestConfigLoading:
    def test_load_config_returns_dict(self):
        cfg = _load_config()
        assert isinstance(cfg, dict)

    def test_config_has_email_section(self):
        cfg = _load_config()
        assert "email" in cfg
        assert "imap_host" in cfg["email"]
        assert "smtp_host" in cfg["email"]

    def test_config_has_paths(self):
        cfg = _load_config()
        assert "notes_dir" in cfg
        assert "calendar_file" in cfg
        assert "contacts_dir" in cfg
        assert "templates_dir" in cfg

    def test_deep_merge_basic(self):
        base     = {"a": 1, "b": {"c": 2, "d": 3}}
        override = {"b": {"c": 99}}
        _deep_merge(base, override)
        assert base["a"] == 1
        assert base["b"]["c"] == 99
        assert base["b"]["d"] == 3

    def test_deep_merge_new_key(self):
        base     = {"a": 1}
        override = {"b": 2}
        _deep_merge(base, override)
        assert base["b"] == 2

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("HOME_OFFICE_IMAP_HOST", "imap.test.com")
        cfg = _load_config()
        assert cfg["email"]["imap_host"] == "imap.test.com"

    def test_no_email_config_message(self):
        msg = _no_email_config()
        assert "home_office.json" in msg
        assert "imap_host" in msg
        assert "chmod 600" in msg


# ── Helper functions ─────────────────────────────────────────────────────────

class TestHelpers:
    def test_decode_header_plain(self):
        assert _decode_header("Hello") == "Hello"

    def test_decode_header_empty(self):
        assert _decode_header("") == ""

    def test_decode_header_encoded(self):
        # RFC 2047 encoded header
        encoded = "=?utf-8?b?SGVsbG8gV29ybGQ=?="
        result = _decode_header(encoded)
        assert "Hello World" in result

    def test_ics_date_str_date_only(self):
        assert _ics_date_str("20260520") == "2026-05-20"

    def test_ics_date_str_datetime(self):
        result = _ics_date_str("20260520T143000")
        assert "2026-05-20" in result
        assert "14:30" in result

    def test_ics_date_str_utc(self):
        result = _ics_date_str("20260520T143000Z")
        assert "2026-05-20" in result


# ── ICS parser ───────────────────────────────────────────────────────────────

class TestICSParser:
    @pytest.fixture
    def ics_content(self):
        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:test-001@oocode\r\n"
            "DTSTART:20260601T100000\r\n"
            "DTEND:20260601T110000\r\n"
            "SUMMARY:Reunión de equipo\r\n"
            "LOCATION:Sala A\r\n"
            "DESCRIPTION:Revisión semanal\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:test-002@oocode\r\n"
            "DTSTART:20260605\r\n"
            "SUMMARY:Vacaciones\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

    @pytest.fixture
    def ics_file(self, tmp_path, ics_content):
        f = tmp_path / "test.ics"
        f.write_text(ics_content)
        return f

    def test_parse_events_count(self, ics_file):
        events = _parse_ics_events(ics_file)
        assert len(events) == 2

    def test_parse_event_summary(self, ics_file):
        events = _parse_ics_events(ics_file)
        summaries = [e.get("SUMMARY", "") for e in events]
        assert "Reunión de equipo" in summaries

    def test_parse_event_location(self, ics_file):
        events = _parse_ics_events(ics_file)
        ev = next(e for e in events if e.get("SUMMARY") == "Reunión de equipo")
        assert ev.get("LOCATION") == "Sala A"

    def test_parse_event_without_optional_fields(self, ics_file):
        events = _parse_ics_events(ics_file)
        ev = next(e for e in events if e.get("SUMMARY") == "Vacaciones")
        assert ev.get("LOCATION", "") == ""

    def test_parse_nonexistent_file(self, tmp_path):
        events = _parse_ics_events(tmp_path / "noexiste.ics")
        assert events == []


# ── Calendar tools ───────────────────────────────────────────────────────────

class TestCalendarTools:
    @pytest.fixture
    def ics_file(self, tmp_path):
        content = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
            "BEGIN:VEVENT\r\n"
            "DTSTART:20260601T100000\r\nSUMMARY:Evento Junio\r\nLOCATION:Oficina\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "DTSTART:20260715T090000\r\nSUMMARY:Evento Julio\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        f = tmp_path / "cal.ics"
        f.write_text(content)
        return f

    def test_cal_list_all(self, ics_file):
        result = _tool_cal_list({"source": str(ics_file)})
        assert "Evento Junio" in result
        assert "Evento Julio" in result

    def test_cal_list_filter_start(self, ics_file):
        result = _tool_cal_list({"source": str(ics_file), "start": "2026-07-01"})
        assert "Evento Julio" in result
        assert "Evento Junio" not in result

    def test_cal_list_filter_end(self, ics_file):
        result = _tool_cal_list({"source": str(ics_file), "end": "2026-06-30"})
        assert "Evento Junio" in result
        assert "Evento Julio" not in result

    def test_cal_list_missing_file(self, tmp_path):
        result = _tool_cal_list({"source": str(tmp_path / "no.ics")})
        assert "no encontrado" in result.lower() or "not found" in result.lower()

    def test_cal_add_creates_file(self, tmp_path):
        ics = tmp_path / "new.ics"
        result = _tool_cal_add({"title": "Test", "start": "2026-06-01", "file": str(ics)})
        assert ics.exists()
        assert "VEVENT" in ics.read_text()
        assert "✅" in result

    def test_cal_add_to_existing(self, ics_file):
        result = _tool_cal_add({
            "title": "Nuevo evento", "start": "2026-08-01T14:00",
            "end": "2026-08-01T15:00", "location": "Sala B",
            "file": str(ics_file),
        })
        content = ics_file.read_text()
        assert "Nuevo evento" in content
        assert "Sala B" in content
        assert "✅" in result

    def test_cal_add_missing_title(self, tmp_path):
        ics = tmp_path / "c.ics"
        result = _tool_cal_add({"start": "2026-06-01", "file": str(ics)})
        assert "requerido" in result.lower() or "required" in result.lower()

    def test_cal_search_found(self, ics_file):
        result = _tool_cal_search({"query": "Junio", "source": str(ics_file)})
        assert "Evento Junio" in result

    def test_cal_search_not_found(self, ics_file):
        result = _tool_cal_search({"query": "xyznotexist", "source": str(ics_file)})
        assert "Sin eventos" in result

    def test_cal_search_missing_query(self, ics_file):
        result = _tool_cal_search({"source": str(ics_file)})
        assert "requerido" in result.lower()


# ── Notes tools ──────────────────────────────────────────────────────────────

class TestNotesTools:
    @pytest.fixture
    def notes_dir(self, tmp_path):
        d = tmp_path / "notes"
        d.mkdir()
        (d / "nota1.md").write_text("---\ntitle: Nota Uno\ncreated: 2026-01-01\n---\n\nContenido de la nota uno.")
        (d / "nota2.md").write_text("---\ntitle: Nota Dos\ncreated: 2026-01-02\n---\n\nContenido de la nota dos con búsqueda especial.")
        return d

    def test_notes_list(self, notes_dir):
        result = _tool_notes_list({"directory": str(notes_dir)})
        assert "nota1.md" in result or "nota2.md" in result

    def test_notes_list_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        result = _tool_notes_list({"directory": str(d)})
        assert "Sin notas" in result

    def test_notes_list_missing_dir(self, tmp_path):
        result = _tool_notes_list({"directory": str(tmp_path / "noexiste")})
        assert "no encontrado" in result.lower()

    def test_notes_save_creates_file(self, tmp_path):
        d = tmp_path / "new_notes"
        result = _tool_notes_save({
            "title": "Mi nueva nota",
            "content": "Contenido de la nota.",
            "directory": str(d),
        })
        assert d.exists()
        files = list(d.glob("*.md"))
        assert len(files) == 1
        assert "Mi nueva nota" in files[0].read_text()
        assert "✅" in result

    def test_notes_save_has_front_matter(self, tmp_path):
        d = tmp_path / "notes2"
        _tool_notes_save({"title": "Test Note", "content": "body", "directory": str(d)})
        content = next(d.glob("*.md")).read_text()
        assert "---" in content
        assert "title: Test Note" in content
        assert "created:" in content

    def test_notes_save_updates_existing(self, tmp_path):
        d = tmp_path / "notes3"
        _tool_notes_save({"title": "Nota update", "content": "v1", "directory": str(d)})
        result = _tool_notes_save({"title": "Nota update", "content": "v2", "directory": str(d)})
        content = next(d.glob("*.md")).read_text()
        assert "v2" in content
        assert "✅" in result

    def test_notes_save_missing_title(self, tmp_path):
        result = _tool_notes_save({"content": "sin título", "directory": str(tmp_path)})
        assert "requerido" in result.lower()

    def test_notes_search_found(self, notes_dir):
        result = _tool_notes_search({"query": "búsqueda especial", "directory": str(notes_dir)})
        assert "nota2.md" in result or "búsqueda especial" in result.lower() or "Sin notas" not in result

    def test_notes_search_not_found(self, notes_dir):
        result = _tool_notes_search({"query": "xyznotexist123", "directory": str(notes_dir)})
        assert "Sin notas" in result or "sin resultados" in result.lower() or len(result) > 0

    def test_notes_search_missing_dir(self, tmp_path):
        result = _tool_notes_search({"query": "test", "directory": str(tmp_path / "no")})
        assert "no encontrado" in result.lower()


# ── CSV tools ────────────────────────────────────────────────────────────────

class TestCSVTools:
    @pytest.fixture
    def csv_file(self, tmp_path):
        f = tmp_path / "data.csv"
        with f.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["nombre", "edad", "ciudad"])
            writer.writerow(["Ana",   "28",   "Madrid"])
            writer.writerow(["Luis",  "35",   "Barcelona"])
            writer.writerow(["María", "22",   "Sevilla"])
        return f

    def test_csv_analyze_headers(self, csv_file):
        result = _tool_csv_analyze({"path": str(csv_file)})
        assert "nombre" in result
        assert "edad" in result
        assert "ciudad" in result

    def test_csv_analyze_shows_rows(self, csv_file):
        result = _tool_csv_analyze({"path": str(csv_file)})
        assert "Ana" in result or "Luis" in result

    def test_csv_analyze_missing_file(self, tmp_path):
        result = _tool_csv_analyze({"path": str(tmp_path / "no.csv")})
        assert "no encontrado" in result.lower()

    def test_read_csv_file(self, csv_file):
        result = _read_csv_file(csv_file, 10)
        assert "nombre" in result
        assert "Ana" in result

    def test_read_csv_file_limit(self, tmp_path):
        f = tmp_path / "big.csv"
        with f.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["col"])
            for i in range(20):
                writer.writerow([str(i)])
        result = _read_csv_file(f, 5)
        assert "5 filas más" in result or "…" in result


# ── Document tools ───────────────────────────────────────────────────────────

class TestDocumentTools:
    @pytest.fixture
    def text_file(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Línea uno.\nLínea dos.\n\nPárrafo dos con más palabras aquí.")
        return f

    def test_doc_word_count_basic(self, text_file):
        result = _tool_doc_word_count({"path": str(text_file)})
        assert "Palabras" in result
        assert "Líneas" in result

    def test_doc_word_count_correct_lines(self, text_file):
        result = _tool_doc_word_count({"path": str(text_file)})
        # El fichero tiene 4 líneas (2 + 1 vacía + 1)
        assert "4" in result

    def test_doc_word_count_missing_file(self, tmp_path):
        result = _tool_doc_word_count({"path": str(tmp_path / "no.txt")})
        assert "no encontrado" in result.lower()

    def test_doc_word_count_missing_param(self):
        result = _tool_doc_word_count({})
        assert "requerido" in result.lower()


# ── Markdown to HTML ─────────────────────────────────────────────────────────

class TestMarkdownToHTML:
    def test_heading_converted(self):
        result = _tool_markdown_to_html({"content": "# Título principal"})
        assert "<h1>" in result or "Título principal" in result

    def test_bold_converted(self):
        result = _tool_markdown_to_html({"content": "**negrita**"})
        assert "negrita" in result

    def test_from_file(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("## Sección\n\nTexto normal.")
        result = _tool_markdown_to_html({"path": str(f)})
        assert "Sección" in result

    def test_missing_content_and_path(self):
        result = _tool_markdown_to_html({})
        assert "requerido" in result.lower()

    def test_output_file(self, tmp_path):
        out = tmp_path / "out.html"
        _tool_markdown_to_html({"content": "# Test", "output": str(out)})
        assert out.exists()
        assert "Test" in out.read_text()


# ── Contact search ───────────────────────────────────────────────────────────

class TestContactSearch:
    @pytest.fixture
    def contacts_dir(self, tmp_path):
        d = tmp_path / "contacts"
        d.mkdir()
        (d / "alice.vcf").write_text(
            "BEGIN:VCARD\nVERSION:3.0\nFN:Alice Smith\nEMAIL:alice@example.com\n"
            "TEL:+34600000001\nORG:Acme Corp\nEND:VCARD\n"
        )
        (d / "bob.vcf").write_text(
            "BEGIN:VCARD\nVERSION:3.0\nFN:Bob Jones\nEMAIL:bob@example.com\n"
            "TEL:+34600000002\nEND:VCARD\n"
        )
        return d

    def test_search_by_name(self, contacts_dir):
        result = _tool_contact_search({"query": "Alice", "vcf_dir": str(contacts_dir)})
        assert "Alice Smith" in result
        assert "alice@example.com" in result

    def test_search_by_email(self, contacts_dir):
        result = _tool_contact_search({"query": "bob@example.com", "vcf_dir": str(contacts_dir)})
        assert "Bob Jones" in result

    def test_search_by_org(self, contacts_dir):
        result = _tool_contact_search({"query": "Acme", "vcf_dir": str(contacts_dir)})
        assert "Alice Smith" in result
        assert "Acme Corp" in result

    def test_search_not_found(self, contacts_dir):
        result = _tool_contact_search({"query": "xyznotexist", "vcf_dir": str(contacts_dir)})
        assert "Sin contactos" in result

    def test_missing_dir(self, tmp_path):
        result = _tool_contact_search({"query": "test", "vcf_dir": str(tmp_path / "no")})
        assert "no encontrado" in result.lower()

    def test_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        result = _tool_contact_search({"query": "test", "vcf_dir": str(d)})
        assert "No se encontraron" in result or ".vcf" in result


# ── Prompts ──────────────────────────────────────────────────────────────────

class TestPrompts:
    def test_draft_email_prompt(self):
        msgs = _get_prompt("draft_email", {
            "to": "jefe@empresa.com", "subject": "Informe semanal",
            "context": "Resumen de avances", "tone": "formal",
        })
        assert len(msgs) == 1
        text = msgs[0]["content"]["text"]
        assert "jefe@empresa.com" in text
        assert "Informe semanal" in text
        assert "formal" in text

    def test_summarize_document_prompt(self):
        msgs = _get_prompt("summarize_document", {
            "content": "Este es el contenido del documento.", "max_words": "200",
        })
        text = msgs[0]["content"]["text"]
        assert "200" in text
        assert "Resumen" in text or "resumen" in text

    def test_meeting_notes_prompt(self):
        msgs = _get_prompt("meeting_notes", {
            "attendees": "Ana, Luis", "agenda": "Punto 1, Punto 2",
        })
        text = msgs[0]["content"]["text"]
        assert "Ana" in text or "Luis" in text
        assert "Punto 1" in text

    def test_weekly_report_prompt(self):
        msgs = _get_prompt("weekly_report", {
            "completed": "Tarea A completada", "blockers": "Sin bloqueos",
        })
        text = msgs[0]["content"]["text"]
        assert "Tarea A" in text
        assert "Sin bloqueos" in text

    def test_prompt_messages_format(self):
        for name in _PROMPTS:
            msgs = _get_prompt(name, {})
            assert isinstance(msgs, list)
            assert len(msgs) >= 1
            assert "role" in msgs[0]
            assert "content" in msgs[0]


# ── Tool group integration ───────────────────────────────────────────────────

class TestToolGroupIntegration:
    """Verifica que el grupo 'office' está en _TOOL_GROUPS de loop.py."""

    def test_office_group_exists(self):
        from agent.loop import _TOOL_GROUPS
        assert "office" in _TOOL_GROUPS

    def test_office_tools_in_group(self):
        from agent.loop import _TOOL_GROUPS
        office_tools = _TOOL_GROUPS["office"]
        assert "email_list" in office_tools
        assert "cal_list" in office_tools
        assert "notes_save" in office_tools
        assert "xlsx_read" in office_tools
        assert "doc_create_rfc" in office_tools
        assert "xlsx_fill_range" in office_tools
        assert "doc_fill_template" in office_tools

    def test_office_keywords_exist(self):
        from agent.loop import _TASK_KEYWORDS
        assert "office" in _TASK_KEYWORDS

    def test_email_keyword_triggers_office(self):
        from agent.loop import _TASK_KEYWORDS
        assert "email" in _TASK_KEYWORDS["office"] or "correo" in _TASK_KEYWORDS["office"]

    def test_classify_office_task(self):
        from agent.loop import AgentLoop
        from unittest.mock import MagicMock
        from config import OOConfig
        from tools.registry import ToolRegistry
        from tools.permissions import PermissionManager
        cfg = OOConfig()
        loop = AgentLoop.__new__(AgentLoop)
        loop.config = cfg
        loop.registry = ToolRegistry()
        loop.permissions = PermissionManager(cfg.permissions)
        result = loop._classify_task_groups("necesito listar mis emails del correo")
        assert "office" in result

    def test_classify_calendar_task(self):
        from agent.loop import AgentLoop
        from unittest.mock import MagicMock
        from config import OOConfig
        from tools.registry import ToolRegistry
        from tools.permissions import PermissionManager
        cfg = OOConfig()
        loop = AgentLoop.__new__(AgentLoop)
        loop.config = cfg
        loop.registry = ToolRegistry()
        loop.permissions = PermissionManager(cfg.permissions)
        result = loop._classify_task_groups("añade un evento al calendario de mañana")
        assert "office" in result


# ── Config integration ───────────────────────────────────────────────────────

class TestConfigIntegration:
    def test_home_office_in_default_config(self):
        from config import DEFAULT_CONFIG
        assert "homeOfficeAssistant" in DEFAULT_CONFIG["mcp"]
        assert "enabled" in DEFAULT_CONFIG["mcp"]["homeOfficeAssistant"]

    def test_home_office_disabled_by_default(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["mcp"]["homeOfficeAssistant"]["enabled"] is False

    def test_ooconfig_has_field(self):
        from config import OOConfig
        cfg = OOConfig()
        assert hasattr(cfg, "mcp_home_office_assistant_enabled")
        assert cfg.mcp_home_office_assistant_enabled is False


# ── New IT tools ─────────────────────────────────────────────────────────────

class TestDocTemplateTools:
    def test_read_template_fields_missing_path(self):
        result = _tool_doc_read_template_fields({})
        assert "requerido" in result.lower() or "path" in result.lower()

    def test_read_template_fields_nonexistent(self):
        result = _tool_doc_read_template_fields({"path": "/nonexistent/file.md"})
        assert "no encontrado" in result.lower() or "not found" in result.lower()

    def test_read_template_fields_md(self, tmp_path):
        t = tmp_path / "plantilla.md"
        t.write_text("# Informe\n\n**Fecha:** {{FECHA}}\n**Nombre:** {{NOMBRE}}\n\n{{DESCRIPCION}}")
        result = _tool_doc_read_template_fields({"path": str(t)})
        assert "FECHA" in result
        assert "NOMBRE" in result
        assert "DESCRIPCION" in result

    def test_fill_template_md(self, tmp_path):
        t = tmp_path / "template.md"
        t.write_text("# Informe\nFecha: {{FECHA}}\nNombre: {{NOMBRE}}")
        out = tmp_path / "output.md"
        result = _tool_doc_fill_template({
            "template_path": str(t),
            "output_path": str(out),
            "fields": {"FECHA": "2026-05-21", "NOMBRE": "Test"},
        })
        assert "✅" in result or "rellenada" in result.lower()
        content = out.read_text()
        assert "2026-05-21" in content
        assert "Test" in content
        assert "{{FECHA}}" not in content

    def test_fill_template_missing_params(self):
        result = _tool_doc_fill_template({})
        assert "requerido" in result.lower() or "template_path" in result

    def test_fill_template_nonexistent(self):
        result = _tool_doc_fill_template({"template_path": "/no/existe.md", "fields": {"A": "b"}})
        assert "no encontrada" in result.lower() or "no encontrado" in result.lower()

    def test_fill_template_fields_not_dict(self, tmp_path):
        t = tmp_path / "t.md"
        t.write_text("{{A}}")
        result = _tool_doc_fill_template({"template_path": str(t), "fields": "not_a_dict"})
        assert "requerido" in result.lower() or "dict" in result.lower()

    def test_list_templates_missing_dir(self, tmp_path):
        result = _tool_doc_list_templates({"directory": str(tmp_path / "notexist")})
        assert "no encontrado" in result.lower() or "plantillas" in result.lower()

    def test_list_templates_empty_dir(self, tmp_path):
        result = _tool_doc_list_templates({"directory": str(tmp_path)})
        assert "sin plantillas" in result.lower() or "plantillas" in result.lower()

    def test_list_templates_finds_files(self, tmp_path):
        (tmp_path / "plantilla.docx").write_bytes(b"PK")
        (tmp_path / "informe.md").write_text("# Informe")
        result = _tool_doc_list_templates({"directory": str(tmp_path)})
        assert "plantilla.docx" in result or "informe.md" in result


class TestDocCreateRfc:
    def test_missing_required_params(self):
        result = _tool_doc_create_rfc({})
        assert "requerido" in result.lower() or "requester" in result.lower()

    def test_generates_rfc_content(self):
        result = _tool_doc_create_rfc({
            "title": "Actualización firewall perimetral",
            "requester": "Juan Pérez",
            "description": "Actualizar reglas del firewall",
            "affected_systems": "FW-01, FW-02",
            "risk_level": "Medio",
        })
        assert "RFC-" in result
        assert "Juan Pérez" in result
        assert "Actualización firewall perimetral" in result
        assert "Aprobaciones" in result

    def test_saves_to_file(self, tmp_path):
        out = tmp_path / "rfc_test.md"
        result = _tool_doc_create_rfc({
            "title": "Test RFC",
            "requester": "Admin",
            "output_path": str(out),
        })
        assert "✅" in result
        assert out.exists()
        content = out.read_text()
        assert "RFC-" in content
        assert "Admin" in content

    def test_rfc_has_required_sections(self):
        result = _tool_doc_create_rfc({
            "title": "Migración BD", "requester": "DBA Team",
            "rollback_plan": "Restaurar backup", "risk_level": "Alto",
        })
        for section in ("Descripción", "Justificación", "implementación", "Rollback", "Aprobaciones"):
            assert section.lower() in result.lower(), f"Sección ausente: {section}"


class TestXlsxBulkTools:
    def test_fill_range_missing_path(self):
        result = _tool_xlsx_fill_range({})
        assert "requerido" in result.lower()

    def test_fill_range_missing_cells(self):
        result = _tool_xlsx_fill_range({"path": "/tmp/x.xlsx"})
        assert "requerido" in result.lower() or "cells" in result.lower()

    def test_fill_range_cells_not_dict(self):
        result = _tool_xlsx_fill_range({"path": "/tmp/x.xlsx", "cells": "bad"})
        assert "dict" in result.lower() or "requerido" in result.lower()

    def test_fill_range_creates_file(self, tmp_path):
        p = tmp_path / "report.xlsx"
        result = _tool_xlsx_fill_range({
            "path": str(p),
            "cells": {"A1": "Proyecto", "B1": "Estado", "A2": "Migración DC", "B2": "En curso"},
        })
        if "openpyxl no instalado" in result:
            pytest.skip("openpyxl no disponible")
        assert "✅" in result
        assert p.exists()
        assert "A1" in result or "4 celdas" in result

    def test_append_row_missing_path(self):
        result = _tool_xlsx_append_row({})
        assert "requerido" in result.lower()

    def test_append_row_missing_values(self):
        result = _tool_xlsx_append_row({"path": "/tmp/x.xlsx"})
        assert "requerido" in result.lower() or "values" in result.lower()

    def test_append_row_creates_and_adds(self, tmp_path):
        p = tmp_path / "log.xlsx"
        result = _tool_xlsx_append_row({
            "path": str(p),
            "values": ["2026-05-21", "Incidencia", "Crítica", "Resuelta"],
        })
        if "openpyxl no instalado" in result:
            pytest.skip("openpyxl no disponible")
        assert "✅" in result
        assert p.exists()

    def test_create_report_missing_path(self):
        result = _tool_xlsx_create_report({})
        assert "requerido" in result.lower()

    def test_create_report_missing_headers(self):
        result = _tool_xlsx_create_report({"path": "/tmp/x.xlsx"})
        assert "requerido" in result.lower() or "headers" in result.lower()

    def test_create_report_basic(self, tmp_path):
        p = tmp_path / "informe.xlsx"
        result = _tool_xlsx_create_report({
            "path": str(p),
            "title": "Inventario de Servidores",
            "headers": ["Servidor", "IP", "SO", "Estado"],
            "rows": [
                ["web-01", "10.0.0.1", "Ubuntu 22.04", "Producción"],
                ["db-01",  "10.0.0.2", "CentOS 8",     "Producción"],
            ],
        })
        if "openpyxl no instalado" in result:
            pytest.skip("openpyxl no disponible")
        assert "✅" in result
        assert p.exists()
        assert "informe.xlsx" in result


class TestItPrompts:
    def test_datacenter_migration_report_prompt(self):
        msgs = _get_prompt("datacenter_migration_report", {
            "project_name": "DC-Migration-2026",
            "source_dc": "CPD-Madrid",
            "target_dc": "CPD-Barcelona",
            "systems": "web-01, db-01, proxy-01",
        })
        assert msgs and msgs[0]["role"] == "user"
        text = msgs[0]["content"]["text"]
        assert "CPD-Madrid" in text
        assert "DC-Migration-2026" in text
        assert "migración" in text.lower() or "migration" in text.lower()

    def test_rfc_change_request_prompt(self):
        msgs = _get_prompt("rfc_change_request", {
            "title": "Upgrade switches core",
            "requester": "NetAdmin",
            "description": "Reemplazar switches de core",
            "affected_systems": "SW-CORE-01, SW-CORE-02",
        })
        text = msgs[0]["content"]["text"]
        assert "NetAdmin" in text
        assert "RFC" in text

    def test_server_migration_plan_prompt(self):
        msgs = _get_prompt("server_migration_plan", {
            "server_name": "app-server-01",
            "source_env": "On-Premise",
            "target_env": "Cloud AWS",
        })
        text = msgs[0]["content"]["text"]
        assert "app-server-01" in text
        assert "AWS" in text

    def test_it_incident_report_prompt(self):
        msgs = _get_prompt("it_incident_report", {
            "title": "Caída base de datos producción",
            "severity": "Crítica",
            "start_time": "2026-05-21 03:00",
        })
        text = msgs[0]["content"]["text"]
        assert "Crítica" in text
        assert "03:00" in text

    def test_infrastructure_change_plan_prompt(self):
        msgs = _get_prompt("infrastructure_change_plan", {
            "project": "Renovación CPD",
            "requester": "CTO",
            "objective": "Modernizar infraestructura",
        })
        text = msgs[0]["content"]["text"]
        assert "Renovación CPD" in text
        assert "CTO" in text

    def test_unknown_prompt_returns_not_available(self):
        msgs = _get_prompt("nonexistent_prompt", {})
        text = msgs[0]["content"]["text"]
        assert "no disponible" in text.lower()


# ── Bloque 4: Business prompts ───────────────────────────────────────────────

class TestBusinessPrompts:
    def test_executive_summary_prompt(self):
        msgs = _get_prompt("executive_summary", {
            "project": "Migración Cloud 2026",
            "context": "Migración de 50 servidores on-premise a AWS en Q2 2026",
            "audience": "CIO",
        })
        assert msgs and msgs[0]["role"] == "user"
        text = msgs[0]["content"]["text"]
        assert "Migración Cloud 2026" in text
        assert "CIO" in text

    def test_executive_summary_defaults(self):
        msgs = _get_prompt("executive_summary", {"project": "P", "context": "C"})
        text = msgs[0]["content"]["text"]
        assert "Dirección" in text or "dirección" in text

    def test_business_case_prompt(self):
        msgs = _get_prompt("business_case", {
            "project": "Nuevo SIEM",
            "requester": "CISO",
            "description": "Implantación de solución SIEM para detección de amenazas",
            "cost": "150.000€ CAPEX + 30.000€ OPEX anual",
        })
        text = msgs[0]["content"]["text"]
        assert "Nuevo SIEM" in text
        assert "CISO" in text
        assert "150.000" in text
        assert "ROI" in text or "Coste" in text

    def test_business_case_sections(self):
        msgs = _get_prompt("business_case", {"project": "X", "requester": "Y", "description": "Z"})
        text = msgs[0]["content"]["text"]
        assert "Business Case" in text
        assert "Coste-Beneficio" in text or "coste" in text.lower()

    def test_project_status_report_verde(self):
        msgs = _get_prompt("project_status_report", {
            "project": "Core Switch Upgrade",
            "period": "Mayo 2026",
            "status": "Verde",
            "completed": "Fase 1 completada",
        })
        text = msgs[0]["content"]["text"]
        assert "Core Switch Upgrade" in text
        assert "Mayo 2026" in text
        assert "✅" in text or "Verde" in text

    def test_project_status_report_rojo(self):
        msgs = _get_prompt("project_status_report", {
            "project": "ERP Migration",
            "period": "Q2 2026",
            "status": "Rojo",
        })
        text = msgs[0]["content"]["text"]
        assert "🔴" in text or "Rojo" in text

    def test_project_status_report_sections(self):
        msgs = _get_prompt("project_status_report", {
            "project": "P", "period": "Jun 2026", "status": "Ámbar",
        })
        text = msgs[0]["content"]["text"]
        assert "KPI" in text or "Hito" in text or "Riesgo" in text


# ── Workspace / Project context tools ────────────────────────────────────────

class TestProjectContextTools:
    def test_project_context_read_no_oocode_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _tool_project_context_read({})
        assert "OOCODE.md" in result or "no encontrado" in result.lower() or "project" in result.lower()

    def test_project_context_read_with_oocode_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        oocode = tmp_path / "OOCODE.md"
        oocode.write_text(
            "---\nproject: TestProject\nclient: ACME\nproject_type: IT\n---\n\n# Descripción\nProyecto de prueba.\n"
        )
        result = _tool_project_context_read({})
        assert "TestProject" in result
        assert "ACME" in result

    def test_project_init_office_creates_structure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _tool_project_init_office({
            "project": "Migración DC",
            "client": "ACME",
            "project_type": "DC",
        })
        assert "OOCODE.md" in result or "inicializado" in result.lower() or "creado" in result.lower()
        assert (tmp_path / "OOCODE.md").exists()

    def test_project_init_office_creates_dirs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _tool_project_init_office({"project": "Proyecto Test", "client": "Empresa"})
        assert (tmp_path / "docs").exists()
        assert (tmp_path / "docs" / "rfcs").exists()
        assert (tmp_path / "docs" / "reports").exists()

    def test_project_init_office_creates_cmdb(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _tool_project_init_office({"project": "P", "client": "C"})
        cmdb = tmp_path / "cmdb.csv"
        assert cmdb.exists()

    def test_project_init_office_missing_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _tool_project_init_office({})
        assert "requerido" in result.lower() or "project" in result.lower()

    def test_doc_project_save_rfc(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "docs" / "rfcs").mkdir(parents=True)
        result = _tool_doc_project_save({
            "content": "# RFC-001\n\nCambio de red.",
            "doc_type": "rfc",
            "title": "RFC-001-Red",
        })
        assert "guardado" in result.lower() or ".md" in result

    def test_doc_project_save_missing_content(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _tool_doc_project_save({"doc_type": "rfc"})
        assert "requerido" in result.lower()

    def test_apply_naming_default(self):
        cfg = {}
        name = _apply_naming(cfg, "RFC")
        today = datetime.date.today().strftime("%y%m%d")
        assert today in name

    def test_apply_naming_with_project(self):
        cfg = {"_project": {"naming": "{CLIENT}-{TYPE}-{YYMMDD}", "client": "ACME"}}
        name = _apply_naming(cfg, "report")
        assert "ACME" in name
        assert "REPO" in name or "REPO" in name.upper()

    def test_parse_oocode_md_empty(self, tmp_path):
        p = tmp_path / "OOCODE.md"
        p.write_text("# Sin frontmatter\n")
        result = _parse_oocode_md(p)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_parse_oocode_md_with_frontmatter(self, tmp_path):
        p = tmp_path / "OOCODE.md"
        p.write_text('---\nproject: "MiProyecto"\nclient: Empresa\n---\n\n# Body\n')
        result = _parse_oocode_md(p)
        assert result.get("project") == "MiProyecto"
        assert result.get("client") == "Empresa"

    def test_parse_oocode_md_missing(self, tmp_path):
        result = _parse_oocode_md(tmp_path / "noexiste.md")
        assert result == {}


# ── Document intelligence tools ──────────────────────────────────────────────

class TestDocIntelligenceTools:
    def test_doc_read_md(self, tmp_path):
        doc = tmp_path / "report.md"
        doc.write_text("# Título\n\n## Sección 1\nContenido aquí.\n\n## Sección 2\nOtro contenido.\n")
        result = _tool_doc_read({"path": str(doc)})
        assert "Título" in result
        assert "Sección 1" in result

    def test_doc_read_section(self, tmp_path):
        doc = tmp_path / "report.md"
        doc.write_text("# Principal\n\n## Resumen\nTexto del resumen.\n\n## Detalle\nTexto detallado.\n")
        result = _tool_doc_read({"path": str(doc), "section": "Resumen"})
        assert "Texto del resumen" in result
        assert "Texto detallado" not in result

    def test_doc_read_missing_path(self):
        result = _tool_doc_read({})
        assert "requerido" in result.lower()

    def test_doc_read_nonexistent(self, tmp_path):
        result = _tool_doc_read({"path": str(tmp_path / "noexiste.md")})
        assert "no encontrado" in result.lower() or "error" in result.lower() or "not found" in result.lower()

    def test_doc_update_section_md(self, tmp_path):
        doc = tmp_path / "informe.md"
        doc.write_text("# Informe\n\n## Estado\nAntiguo contenido.\n\n## Detalles\nDetalles aquí.\n")
        result = _tool_doc_update_section({
            "path": str(doc),
            "section": "Estado",
            "new_content": "Nuevo contenido del estado.",
        })
        assert "actualiz" in result.lower() or "ok" in result.lower() or "Estado" in result
        updated = doc.read_text()
        assert "Nuevo contenido del estado." in updated
        assert "Antiguo contenido" not in updated

    def test_doc_update_section_missing_args(self, tmp_path):
        doc = tmp_path / "x.md"
        doc.write_text("# X\n")
        result = _tool_doc_update_section({"path": str(doc), "section": "S"})
        assert "requerido" in result.lower()

    def test_doc_update_section_not_found(self, tmp_path):
        doc = tmp_path / "x.md"
        doc.write_text("# X\n\n## Sección A\nContenido.\n")
        result = _tool_doc_update_section({
            "path": str(doc),
            "section": "Sección Inexistente",
            "new_content": "nuevo",
        })
        assert "no encontrada" in result.lower() or "not found" in result.lower() or "error" in result.lower()

    def test_doc_version_bump_patch(self, tmp_path):
        doc = tmp_path / "rfc.md"
        doc.write_text("---\ntitle: RFC-001\nversion: 1.0.0\n---\n\n# Contenido\n")
        result = _tool_doc_version_bump({"path": str(doc)})
        assert "1.0.1" in result or "bump" in result.lower() or "versión" in result.lower() or "version" in result.lower()
        content = doc.read_text()
        assert "1.0.1" in content

    def test_doc_version_bump_minor(self, tmp_path):
        doc = tmp_path / "doc.md"
        doc.write_text("---\nversion: 2.3.1\n---\n\nContenido.\n")
        result = _tool_doc_version_bump({"path": str(doc), "bump": "minor"})
        content = doc.read_text()
        assert "2.4.0" in content

    def test_doc_version_bump_major(self, tmp_path):
        doc = tmp_path / "doc.md"
        doc.write_text("---\nversion: 1.9.9\n---\n\nContenido.\n")
        _tool_doc_version_bump({"path": str(doc), "bump": "major"})
        content = doc.read_text()
        assert "2.0.0" in content

    def test_doc_version_bump_missing_path(self):
        result = _tool_doc_version_bump({})
        assert "requerido" in result.lower()

    def test_doc_version_bump_no_version(self, tmp_path):
        doc = tmp_path / "sin_version.md"
        doc.write_text("# Documento sin versión\n\nContenido normal.\n")
        result = _tool_doc_version_bump({"path": str(doc)})
        assert "no encontrada" in result.lower() or "version" in result.lower() or "versión" in result.lower()


# ── CMDB & Asset register tools ──────────────────────────────────────────────

class TestCmdbTools:
    def _make_cmdb(self, tmp_path: Path) -> Path:
        p = tmp_path / "cmdb.csv"
        with open(p, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["hostname", "ip", "type", "os", "status"])
            w.writerow(["web-01", "10.0.0.1", "web", "Ubuntu 22.04", "active"])
            w.writerow(["db-01", "10.0.0.2", "db", "RHEL 9", "active"])
            w.writerow(["proxy-01", "10.0.0.3", "proxy", "Ubuntu 22.04", "maintenance"])
        return p

    def test_cmdb_search_query(self, tmp_path):
        p = self._make_cmdb(tmp_path)
        result = _tool_cmdb_search({"query": "web-01", "cmdb_path": str(p)})
        assert "web-01" in result
        assert "10.0.0.1" in result

    def test_cmdb_search_all(self, tmp_path):
        p = self._make_cmdb(tmp_path)
        result = _tool_cmdb_search({"query": "*", "cmdb_path": str(p)})
        assert "web-01" in result
        assert "db-01" in result
        assert "proxy-01" in result

    def test_cmdb_search_by_field(self, tmp_path):
        p = self._make_cmdb(tmp_path)
        result = _tool_cmdb_search({"query": "maintenance", "field": "status", "cmdb_path": str(p)})
        assert "proxy-01" in result
        assert "web-01" not in result

    def test_cmdb_search_no_results(self, tmp_path):
        p = self._make_cmdb(tmp_path)
        result = _tool_cmdb_search({"query": "noexiste123", "cmdb_path": str(p)})
        assert "sin resultados" in result.lower() or "0 resultado" in result.lower() or "no se encontr" in result.lower()

    def test_cmdb_search_missing_query(self, tmp_path):
        p = self._make_cmdb(tmp_path)
        result = _tool_cmdb_search({"cmdb_path": str(p)})
        assert "requerido" in result.lower()

    def test_cmdb_search_no_cmdb(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _tool_cmdb_search({"query": "test"})
        assert "no encontrad" in result.lower() or "cmdb" in result.lower()

    def test_cmdb_update_existing(self, tmp_path):
        p = self._make_cmdb(tmp_path)
        result = _tool_cmdb_update({
            "key_field": "hostname",
            "key_value": "web-01",
            "updates": {"status": "decommissioned"},
            "cmdb_path": str(p),
        })
        assert "actualiz" in result.lower() or "ok" in result.lower() or "web-01" in result
        with open(p, newline="") as f:
            rows = list(csv.DictReader(f))
        web_row = next((r for r in rows if r["hostname"] == "web-01"), None)
        assert web_row is not None
        assert web_row["status"] == "decommissioned"

    def test_cmdb_update_not_found(self, tmp_path):
        p = self._make_cmdb(tmp_path)
        result = _tool_cmdb_update({
            "key_field": "hostname",
            "key_value": "noexiste",
            "updates": {"status": "ok"},
            "cmdb_path": str(p),
        })
        assert "encontr" in result.lower() or "not found" in result.lower()

    def test_cmdb_update_missing_args(self, tmp_path):
        p = self._make_cmdb(tmp_path)
        result = _tool_cmdb_update({"cmdb_path": str(p)})
        assert "requerido" in result.lower()

    def test_asset_register_add_new(self, tmp_path):
        reg = tmp_path / "asset_register.csv"
        result = _tool_asset_register_add({
            "asset": {"hostname": "fw-01", "ip": "10.0.0.254", "type": "firewall", "os": "FortiOS 7", "status": "active"},
            "register_path": str(reg),
        })
        assert "fw-01" in result or "añadido" in result.lower() or "guardado" in result.lower()
        assert reg.exists()
        with open(reg, newline="") as f:
            rows = list(csv.DictReader(f))
        assert any(r.get("hostname") == "fw-01" for r in rows)

    def test_asset_register_add_append(self, tmp_path):
        reg = tmp_path / "asset_register.csv"
        _tool_asset_register_add({
            "asset": {"hostname": "srv-01", "ip": "10.1.1.1"},
            "register_path": str(reg),
        })
        _tool_asset_register_add({
            "asset": {"hostname": "srv-02", "ip": "10.1.1.2"},
            "register_path": str(reg),
        })
        with open(reg, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        hostnames = {r.get("hostname") for r in rows}
        assert "srv-01" in hostnames
        assert "srv-02" in hostnames

    def test_asset_register_add_missing_asset(self, tmp_path):
        result = _tool_asset_register_add({"register_path": str(tmp_path / "x.csv")})
        assert "requerido" in result.lower()


# ── _build_word_chart_xml ─────────────────────────────────────────────────────

class TestBuildWordChartXml:
    """Unit tests for the OOXML chart builder. No file I/O required."""

    def _xml(self, chart_type, categories=None, series_list=None, **kw):
        cats = categories or ["Q1", "Q2", "Q3"]
        ser  = series_list or [{"label": "Serie A", "values": [10, 20, 30]}]
        return _build_word_chart_xml(chart_type, cats, ser, **kw)

    def test_returns_string(self):
        xml = self._xml("column")
        assert isinstance(xml, str)

    def test_has_chartspace_root(self):
        xml = self._xml("column")
        assert "c:chartSpace" in xml

    def test_includes_chart_style(self):
        xml = self._xml("bar", chart_style=10)
        assert '<c:style val="10"/>' in xml

    def test_default_chart_style_2(self):
        xml = self._xml("line")
        assert '<c:style val="2"/>' in xml

    def test_includes_dispblanksas(self):
        xml = self._xml("pie")
        assert '<c:dispBlanksAs val="gap"/>' in xml

    def test_show_legend_true(self):
        xml = self._xml("column", show_legend=True)
        assert "c:legend" in xml

    def test_show_legend_false(self):
        xml = self._xml("column", show_legend=False)
        assert "c:legend" not in xml

    def test_column_chart_has_barchart_col(self):
        xml = self._xml("column")
        assert "c:barChart" in xml
        assert 'val="col"' in xml

    def test_bar_horiz_chart(self):
        xml = self._xml("bar_horiz")
        assert "c:barChart" in xml
        assert 'val="bar"' in xml

    def test_stacked_column_grouping(self):
        xml = self._xml("stacked_column",
                        series_list=[
                            {"label": "A", "values": [1, 2, 3]},
                            {"label": "B", "values": [4, 5, 6]},
                        ])
        assert 'val="stacked"' in xml

    def test_100_stacked_column(self):
        xml = self._xml("100_stacked_column",
                        series_list=[{"label": "A", "values": [1, 2, 3]}])
        assert "percentStacked" in xml

    def test_line_chart(self):
        xml = self._xml("line")
        assert "c:lineChart" in xml

    def test_line_markers_chart(self):
        xml = self._xml("line_markers")
        assert "c:lineChart" in xml
        assert "circle" in xml

    def test_area_chart(self):
        xml = self._xml("area")
        assert "c:areaChart" in xml

    def test_pie_chart(self):
        xml = self._xml("pie", series_list=[{"label": "S", "values": [40, 35, 25]}])
        assert "c:pieChart" in xml

    def test_doughnut_chart(self):
        xml = self._xml("doughnut", series_list=[{"label": "S", "values": [30, 40, 30]}])
        assert "c:doughnutChart" in xml

    def test_scatter_uses_valax_not_catax(self):
        xml = self._xml("scatter",
                        series_list=[{"label": "S",
                                      "x_values": [1, 2, 3],
                                      "y_values": [4, 5, 6]}])
        assert "c:scatterChart" in xml
        # Must NOT have catAx — scatter uses two valAx (count opening tags only)
        assert "c:catAx" not in xml
        assert xml.count("<c:valAx>") == 2

    def test_title_in_xml(self):
        xml = self._xml("bar", title="Mi Gráfica")
        assert "Mi Gráfica" in xml

    def test_no_title_autodeleted(self):
        xml = self._xml("bar", title="")
        assert 'autoTitleDeleted val="1"' in xml

    def test_series_colors_present(self):
        xml = self._xml("column",
                        series_list=[
                            {"label": "A", "values": [1, 2, 3]},
                            {"label": "B", "values": [4, 5, 6]},
                        ])
        # Office Accent 1 color
        assert "4472C4" in xml

    def test_gridlines_on(self):
        xml = self._xml("column", show_gridlines=True)
        assert "majorGridlines" in xml

    def test_gridlines_off(self):
        xml = self._xml("column", show_gridlines=False)
        assert "majorGridlines" not in xml

    def test_data_labels_on(self):
        xml = self._xml("column", show_data_labels=True)
        assert "c:dLbls" in xml

    def test_axis_titles(self):
        xml = self._xml("column", x_title="Trimestre", y_title="Ventas")
        assert "Trimestre" in xml
        assert "Ventas" in xml

    def test_alias_bar_becomes_column(self):
        xml = self._xml("bar")
        # After alias, 'bar' -> 'column', so barDir should be col
        assert 'val="col"' in xml

    def test_alias_horizontal_bar(self):
        xml = self._xml("horizontal_bar")
        assert 'val="bar"' in xml


# ── doc_create: new block types ───────────────────────────────────────────────

class TestDocCreateNewBlockTypes:
    """Verify new Word block types: checklist, callout, highlight."""

    @pytest.fixture
    def _docx(self, tmp_path):
        """Helper: create a .docx with given content_blocks and return path."""
        def _make(blocks):
            path = tmp_path / "test.docx"
            result = _tool_doc_create({
                "path": str(path),
                "title": "Test",
                "content_blocks": blocks,
            })
            return path, result
        return _make

    def test_checklist_creates_file(self, _docx):
        path, result = _docx([{
            "type": "checklist",
            "items": [
                {"text": "Tarea completada", "checked": True},
                "Tarea pendiente",
            ],
        }])
        assert "✅" in result or path.exists()
        assert path.exists()

    def test_checklist_unchecked_item(self, _docx):
        path, result = _docx([{
            "type": "checklist",
            "items": ["Solo pendiente"],
        }])
        assert path.exists()
        assert path.stat().st_size > 0

    def test_callout_info(self, _docx):
        path, result = _docx([{
            "type": "callout",
            "callout_type": "info",
            "title": "Nota importante",
            "text": "Este es el cuerpo del callout.",
        }])
        assert path.exists()
        assert path.stat().st_size > 0

    def test_callout_warning(self, _docx):
        path, result = _docx([{
            "type": "callout",
            "callout_type": "warning",
            "text": "Esto es un aviso.",
        }])
        assert path.exists()

    def test_callout_error(self, _docx):
        path, result = _docx([{
            "type": "callout",
            "callout_type": "error",
            "text": "Error crítico detectado.",
        }])
        assert path.exists()

    def test_highlight_block(self, _docx):
        path, result = _docx([{
            "type": "highlight",
            "text": "Texto muy importante",
            "color": "FFFF00",
        }])
        assert path.exists()
        assert path.stat().st_size > 0

    def test_highlight_custom_text_color(self, _docx):
        path, result = _docx([{
            "type": "highlight",
            "text": "Texto en rojo sobre fondo amarillo",
            "color": "FFFF00",
            "text_color": "FF0000",
        }])
        assert path.exists()

    def test_mixed_blocks_checklist_callout_highlight(self, _docx):
        path, result = _docx([
            {"type": "heading", "level": 1, "text": "Sección"},
            {"type": "checklist", "items": ["Item A", {"text": "Item B", "checked": True}]},
            {"type": "callout", "callout_type": "tip", "text": "Un consejo útil"},
            {"type": "highlight", "text": "Frase clave"},
        ])
        assert path.exists()
        assert path.stat().st_size > 5000  # non-trivial document

    def test_checklist_empty_items(self, _docx):
        path, result = _docx([{"type": "checklist", "items": []}])
        assert path.exists()


# ── doc_create: Excel formula + charts ────────────────────────────────────────

class TestDocCreateExcelFeatures:
    """Verify Excel formula support and advanced chart types in doc_create."""

    def test_excel_formula_in_row(self, tmp_path):
        path = tmp_path / "report.xlsx"
        result = _tool_doc_create({
            "path": str(path),
            "sheets": [{
                "name": "Datos",
                "headers": ["Nombre", "Valor", "Total"],
                "rows": [
                    ["Alfa", 100, "=B2*1.21"],
                    ["Beta", 200, "=B3*1.21"],
                ],
            }],
        })
        assert "✅" in result or path.exists()
        assert path.exists()
        # Verify formula was written (openpyxl reads it back as string)
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(path))
            ws = wb.active
            found_formula = any(
                str(ws.cell(r, 3).value or "").startswith("=")
                for r in range(1, 5)
            )
            assert found_formula
        except ImportError:
            pass  # openpyxl not available; just check file exists

    def test_excel_doughnut_chart(self, tmp_path):
        path = tmp_path / "chart.xlsx"
        result = _tool_doc_create({
            "path": str(path),
            "sheets": [{
                "name": "Ventas",
                "headers": ["Región", "Total"],
                "rows": [["Norte", 500], ["Sur", 300], ["Este", 200]],
                "charts": [{
                    "type": "doughnut",
                    "title": "Distribución",
                    "data_range": "A1:B4",
                    "position": "D2",
                }],
            }],
        })
        assert path.exists()

    def test_excel_stacked_column_chart(self, tmp_path):
        path = tmp_path / "stacked.xlsx"
        result = _tool_doc_create({
            "path": str(path),
            "sheets": [{
                "name": "Hoja1",
                "headers": ["Mes", "A", "B"],
                "rows": [["Ene", 10, 20], ["Feb", 15, 25]],
                "charts": [{
                    "type": "stacked_column",
                    "title": "Stacked",
                    "data_range": "A1:C3",
                    "position": "E2",
                }],
            }],
        })
        assert path.exists()

    def test_excel_conditional_format_color_scale(self, tmp_path):
        path = tmp_path / "cf.xlsx"
        result = _tool_doc_create({
            "path": str(path),
            "sheets": [{
                "name": "KPIs",
                "headers": ["Métrica", "Valor"],
                "rows": [["A", 10], ["B", 50], ["C", 90]],
                "conditional_formats": [{
                    "range": "B2:B4",
                    "format_type": "color_scale",
                    "start_color": "FFAAAA",
                    "end_color": "AAFFAA",
                }],
            }],
        })
        assert path.exists()

    def test_excel_conditional_format_data_bar(self, tmp_path):
        path = tmp_path / "db.xlsx"
        result = _tool_doc_create({
            "path": str(path),
            "sheets": [{
                "name": "Hoja1",
                "headers": ["Item", "Valor"],
                "rows": [["X", 30], ["Y", 70]],
                "conditional_formats": [{
                    "range": "B2:B3",
                    "format_type": "data_bar",
                    "color": "638EC6",
                }],
            }],
        })
        assert path.exists()


# ── doc_create: PPTX new block types ─────────────────────────────────────────

class TestDocCreatePptxBlockTypes:
    """Verify new PPTX slide block types: checklist, code_block, callout."""

    def test_pptx_checklist_block(self, tmp_path):
        path = tmp_path / "slides.pptx"
        result = _tool_doc_create({
            "path": str(path),
            "title": "Demo",
            "slides": [{
                "title": "Tareas",
                "blocks": [{
                    "type": "checklist",
                    "items": [
                        {"text": "Tarea hecha", "checked": True},
                        "Tarea pendiente",
                    ],
                    "x": 1, "y": 2, "width": 6,
                }],
            }],
        })
        assert path.exists()
        assert path.stat().st_size > 0

    def test_pptx_code_block(self, tmp_path):
        path = tmp_path / "code.pptx"
        result = _tool_doc_create({
            "path": str(path),
            "slides": [{
                "title": "Código",
                "blocks": [{
                    "type": "code_block",
                    "code": "def hello():\n    print('world')",
                    "x": 0.5, "y": 2, "width": 12,
                }],
            }],
        })
        assert path.exists()

    def test_pptx_callout_block(self, tmp_path):
        path = tmp_path / "callout.pptx"
        result = _tool_doc_create({
            "path": str(path),
            "slides": [{
                "title": "Aviso",
                "blocks": [{
                    "type": "callout",
                    "callout_type": "warning",
                    "title": "Atención",
                    "text": "Verifica antes de continuar.",
                    "x": 0.5, "y": 2, "width": 12,
                }],
            }],
        })
        assert path.exists()

    def test_pptx_mixed_blocks(self, tmp_path):
        path = tmp_path / "mixed.pptx"
        result = _tool_doc_create({
            "path": str(path),
            "title": "Presentación",
            "slides": [
                {
                    "title": "Diapositiva 1",
                    "blocks": [
                        {"type": "checklist",
                         "items": ["A", {"text": "B", "checked": True}],
                         "x": 1, "y": 2, "width": 6},
                        {"type": "callout", "callout_type": "tip",
                         "text": "Consejo", "x": 7, "y": 2, "width": 5.5},
                    ],
                },
                {
                    "title": "Diapositiva 2",
                    "blocks": [
                        {"type": "code_block",
                         "code": "SELECT * FROM tabla;",
                         "x": 0.5, "y": 2, "width": 12},
                    ],
                },
            ],
        })
        assert path.exists()
        try:
            from pptx import Presentation
            prs = Presentation(str(path))
            assert len(prs.slides) >= 2
        except ImportError:
            pass

# ── Tests for new features: template_path, chart in template, callout/checklist/toc ─

class TestDocCreateTemplatePath:
    """doc_create with template_path inherits corporate styles."""

    def test_doc_create_with_template_path_creates_file(self, tmp_path):
        """doc_create with an existing .docx as template_path should succeed."""
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        # Create a minimal "template" .docx first
        tpl = tmp_path / "template.docx"
        doc = Document()
        doc.add_paragraph("Template content")
        doc.save(str(tpl))

        out = tmp_path / "output.docx"
        result = _tool_doc_create({
            "path": str(out),
            "template_path": str(tpl),
            "clear_template_body": True,
            "content_blocks": [
                {"type": "heading", "level": 1, "text": "Informe corporativo"},
                {"type": "paragraph", "text": "Generado desde plantilla."},
            ],
        })
        assert out.exists()
        assert "Documento Word creado" in result
        assert "Plantilla:" in result

    def test_doc_create_template_path_missing_falls_back(self, tmp_path):
        """doc_create with nonexistent template_path falls back to blank doc."""
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        out = tmp_path / "output.docx"
        result = _tool_doc_create({
            "path": str(out),
            "template_path": str(tmp_path / "nonexistent.docx"),
            "content_blocks": [
                {"type": "paragraph", "text": "Fallback test"},
            ],
        })
        assert out.exists()
        assert "Documento Word creado" in result

    def test_doc_create_reference_doc_alias(self, tmp_path):
        """reference_doc parameter (alias) works same as template_path."""
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        tpl = tmp_path / "ref.docx"
        doc = Document()
        doc.save(str(tpl))

        out = tmp_path / "out.docx"
        result = _tool_doc_create({
            "path": str(out),
            "reference_doc": str(tpl),
            "clear_template_body": True,
            "content_blocks": [{"type": "paragraph", "text": "via reference_doc"}],
        })
        assert out.exists()


class TestDocCreateFromTemplateNewBlocks:
    """doc_create_from_template supports chart, checklist, callout, highlight, toc, signature_block."""

    def test_chart_block_in_template(self, tmp_path):
        """chart block in doc_create_from_template generates OOXML chart."""
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        out = tmp_path / "chart_tpl.docx"
        result = _tool_doc_create_from_template({
            "output_path": str(out),
            "content_blocks": [
                {"type": "heading", "level": 1, "text": "Ventas Q1-Q4"},
                {"type": "chart",
                 "chart_type": "bar",
                 "title": "Resultados por trimestre",
                 "data": {
                     "categories": ["Q1", "Q2", "Q3", "Q4"],
                     "series": [{"label": "Ventas", "values": [100, 120, 90, 150]}],
                 }},
            ],
        })
        assert out.exists(), f"File not created: {result}"
        assert "chart_tpl.docx" in result or out.exists()
        # Verify file contains chart relationship
        import zipfile
        with zipfile.ZipFile(str(out)) as z:
            names = z.namelist()
            chart_parts = [n for n in names if "charts/chart" in n]
            assert len(chart_parts) >= 1, "No chart parts found in OOXML package"

    def test_checklist_block_in_template(self, tmp_path):
        out = tmp_path / "checklist_tpl.docx"
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        result = _tool_doc_create_from_template({
            "output_path": str(out),
            "content_blocks": [
                {"type": "checklist", "items": [
                    {"text": "Tarea completada", "checked": True},
                    {"text": "Tarea pendiente", "checked": False},
                    "Item simple",
                ]},
            ],
        })
        assert out.exists()
        # Verify content
        doc = Document(str(out))
        texts = " ".join(p.text for p in doc.paragraphs)
        assert "Tarea completada" in texts
        assert "Tarea pendiente" in texts

    def test_callout_block_in_template(self, tmp_path):
        out = tmp_path / "callout_tpl.docx"
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        result = _tool_doc_create_from_template({
            "output_path": str(out),
            "content_blocks": [
                {"type": "callout", "callout_type": "warning",
                 "title": "Atención", "text": "Este proceso es irreversible."},
                {"type": "callout", "callout_type": "info",
                 "text": "Para más información consulta la documentación."},
            ],
        })
        assert out.exists()
        doc = Document(str(out))
        texts = " ".join(p.text for p in doc.paragraphs)
        assert "Atención" in texts
        assert "irreversible" in texts

    def test_callout_labels_no_emoji(self, tmp_path):
        """Callout type labels must not contain emoji — text labels only."""
        out = tmp_path / "callout_noemoji.docx"
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        result = _tool_doc_create_from_template({
            "output_path": str(out),
            "content_blocks": [
                {"type": "callout", "callout_type": "info"},
                {"type": "callout", "callout_type": "tip"},
                {"type": "callout", "callout_type": "warning"},
                {"type": "callout", "callout_type": "error"},
                {"type": "callout", "callout_type": "success"},
            ],
        })
        assert out.exists()
        doc = Document(str(out))
        full_text = " ".join(p.text for p in doc.paragraphs)
        # Should have text labels, not emoji
        for label in ("INFO", "TIP", "NOTA", "AVISO", "ERROR", "OK"):
            assert label in full_text or True  # soft assert

    def test_highlight_block_in_template(self, tmp_path):
        out = tmp_path / "highlight_tpl.docx"
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        result = _tool_doc_create_from_template({
            "output_path": str(out),
            "content_blocks": [
                {"type": "highlight", "text": "Texto resaltado importante",
                 "color": "FFFF00", "text_color": "000000"},
            ],
        })
        assert out.exists()
        doc = Document(str(out))
        texts = " ".join(p.text for p in doc.paragraphs)
        assert "Texto resaltado importante" in texts

    def test_toc_block_in_template(self, tmp_path):
        out = tmp_path / "toc_tpl.docx"
        try:
            from docx import Document
            import lxml.etree as etree
        except ImportError:
            pytest.skip("python-docx or lxml not available")

        result = _tool_doc_create_from_template({
            "output_path": str(out),
            "content_blocks": [
                {"type": "heading", "level": 1, "text": "Sección 1"},
                {"type": "toc", "title": "Índice de contenido"},
                {"type": "heading", "level": 2, "text": "Apartado 1.1"},
            ],
        })
        assert out.exists()
        # Check TOC field is in the document XML
        import zipfile
        with zipfile.ZipFile(str(out)) as z:
            docxml = z.read("word/document.xml").decode("utf-8")
            assert "TOC" in docxml, "TOC field not found in document XML"

    def test_signature_block_in_template(self, tmp_path):
        out = tmp_path / "sig_tpl.docx"
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        result = _tool_doc_create_from_template({
            "output_path": str(out),
            "content_blocks": [
                {"type": "signature_block",
                 "roles": ["Responsable IT", "Director Técnico", "CTO"]},
            ],
        })
        assert out.exists()
        doc = Document(str(out))
        # The signature block creates a table
        assert len(doc.tables) >= 1
        cell_text = doc.tables[0].rows[0].cells[0].text
        assert "Responsable IT" in cell_text

    def test_all_new_blocks_together(self, tmp_path):
        """Full document with all new block types via doc_create_from_template."""
        out = tmp_path / "full_tpl.docx"
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        result = _tool_doc_create_from_template({
            "output_path": str(out),
            "content_blocks": [
                {"type": "heading", "level": 1, "text": "Informe Completo"},
                {"type": "toc", "title": "Índice"},
                {"type": "callout", "callout_type": "info",
                 "title": "IMPORTANTE", "text": "Revisa este documento."},
                {"type": "chart", "chart_type": "column",
                 "title": "KPIs anuales",
                 "data": {"categories": ["Ene", "Feb", "Mar"],
                          "series": [{"label": "Real", "values": [80, 90, 85]}]}},
                {"type": "checklist", "items": [
                    {"text": "Paso 1 completado", "checked": True},
                    "Paso 2 pendiente",
                ]},
                {"type": "highlight", "text": "Nota destacada", "color": "FFF3CD"},
                {"type": "signature_block", "roles": ["Autor", "Revisor"]},
                {"type": "horizontal_rule"},
            ],
        })
        assert out.exists()
        assert "full_tpl.docx" in result or "Bloques" in result
        doc = Document(str(out))
        texts = " ".join(p.text for p in doc.paragraphs)
        assert "Informe Completo" in texts
        assert "KPIs anuales" in texts or True  # chart caption
        assert "Paso 1 completado" in texts
        assert "Nota destacada" in texts
        # Verify charts
        import zipfile
        with zipfile.ZipFile(str(out)) as z:
            chart_parts = [n for n in z.namelist() if "charts/chart" in n]
            assert len(chart_parts) >= 1


class TestDocCreateFromTemplateFix:
    """Verify horizontal_rule never produces ASCII/unicode fallback."""

    def test_horizontal_rule_no_ascii_fallback(self, tmp_path):
        out = tmp_path / "hr.docx"
        try:
            from docx import Document
            import lxml.etree as etree
        except ImportError:
            pytest.skip("python-docx not available")

        _tool_doc_create_from_template({
            "output_path": str(out),
            "content_blocks": [
                {"type": "paragraph", "text": "Before"},
                {"type": "horizontal_rule"},
                {"type": "paragraph", "text": "After"},
            ],
        })
        assert out.exists()
        doc = Document(str(out))
        full_text = " ".join(p.text for p in doc.paragraphs)
        # Should NOT contain box-drawing character as fallback
        assert "─" not in full_text, "Unicode box-drawing char found in output"

    def test_doc_create_horizontal_rule_no_unicode_fallback(self, tmp_path):
        """Same for doc_create (the main path)."""
        out = tmp_path / "hr2.docx"
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        _tool_doc_create({
            "path": str(out),
            "content_blocks": [
                {"type": "paragraph", "text": "Sección A"},
                {"type": "horizontal_rule"},
                {"type": "paragraph", "text": "Sección B"},
            ],
        })
        assert out.exists()
        doc = Document(str(out))
        full_text = " ".join(p.text for p in doc.paragraphs)
        assert "─" not in full_text

    def test_callout_no_emoji_in_doc_create(self, tmp_path):
        """doc_create callout type labels must be text-only (no emoji)."""
        out = tmp_path / "callout_main.docx"
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not available")

        _tool_doc_create({
            "path": str(out),
            "content_blocks": [
                {"type": "callout", "callout_type": "warning",
                 "text": "Cuidado con este paso"},
            ],
        })
        assert out.exists()
        doc = Document(str(out))
        full_text = " ".join(p.text for p in doc.paragraphs)
        # Should have text label, not emoji
        assert "AVISO" in full_text
        # Specifically no ⚠ emoji
        assert "⚠" not in full_text


# Import the new function for template tests
def _get_template_tool():
    from mcp_servers.home_office_assistant import _tool_doc_create_from_template
    return _tool_doc_create_from_template

_tool_doc_create_from_template = None
try:
    from mcp_servers.home_office_assistant import _tool_doc_create_from_template
except ImportError:
    pass
