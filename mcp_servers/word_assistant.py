#!/usr/bin/env python3
"""Word Assistant MCP Server — documentos Word/PDF y núcleo ofimático O365 para OOCode.

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 newline-delimited JSON).

Genera documentos Word (.docx) O365 nativos con estilos Calibri, tablas, TOC, firmas,
gráficas OOXML DrawingML editables (insert_chart) y plantillas docxtpl/Jinja2. Incluye la
tool unificada doc_create (genera .docx/.xlsx/.pptx según extensión) y utilidades
transversales: conversión (pandoc), OCR (tesseract), extracción de PDF, metadatos,
comparación de documentos y gestión de proyecto ofimático.

Configuración: ~/.oocode/office.json  (fallback legacy: ~/.oocode/home_office.json)
Proyecto:      OOCODE.md en cwd (templates_dir, docs_dir, naming, client, project_type)

Split de office_assistant.py (v0.4.4): hojas Excel → excel_assistant.py;
presentaciones PowerPoint → pptx_assistant.py.
"""
import csv
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


# ── Configuración ────────────────────────────────────────────────────────────

_CSV_SNIFF_BYTES = 65536   # bytes leídos para que csv.Sniffer detecte el dialect (64 KB)

# Config principal del servidor (con fallback al legacy ~/.oocode/{office,home_office}.json)
_CONFIG_PATH         = Path.home() / ".oocode" / "office.json"
_LEGACY_CONFIG_PATHS = [Path.home() / ".oocode" / "office.json",
                        Path.home() / ".oocode" / "home_office.json"]

_DEFAULT_CFG: dict = {
    "notes_dir":     str(Path.home() / "Documents" / "notes"),
    "templates_dir": str(Path.home() / "Documents" / "templates"),
}


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _load_config() -> dict:
    cfg = json.loads(json.dumps(_DEFAULT_CFG))
    src = next((p for p in _LEGACY_CONFIG_PATHS if p.exists()), None)
    if src:
        try:
            _deep_merge(cfg, json.loads(src.read_text()))
        except Exception:
            pass
    cfg["notes_dir"]     = os.environ.get("HOME_OFFICE_NOTES_DIR",     cfg["notes_dir"])
    cfg["templates_dir"] = os.environ.get("HOME_OFFICE_TEMPLATES_DIR", cfg.get("templates_dir", str(Path.home() / "Documents" / "templates")))
    cwd = Path.cwd()
    local_cfg = cwd / ".oocode-office.json"
    if local_cfg.exists():
        try:
            _deep_merge(cfg, json.loads(local_cfg.read_text()))
        except Exception:
            pass
    oocode_md = cwd / "OOCODE.md"
    if oocode_md.exists():
        proj = _parse_oocode_md(oocode_md)
        if proj:
            cfg["_project"] = proj
            if "templates_dir" in proj:
                p = Path(proj["templates_dir"])
                cfg["templates_dir"] = str(p if p.is_absolute() else cwd / p)
            if "docs_dir" in proj:
                p = Path(proj["docs_dir"])
                cfg["_docs_dir"] = str(p if p.is_absolute() else cwd / p)
            if "notes_dir" in proj:
                p = Path(proj["notes_dir"])
                cfg["notes_dir"] = str(p if p.is_absolute() else cwd / p)
    return cfg





# ── Protocolo MCP ──────────────────────────────────────────────────────────────

def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _recv() -> Optional[dict]:
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue


def _ok(req_id: Any, result: dict) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: Any, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})




# ── Helpers y tools ────────────────────────────────────────────────────────────

def _parse_oocode_md(path: Path) -> dict:
    """Parse YAML front matter from an OOCODE.md file. Returns {} on failure."""
    if not path.exists():
        return {}
    try:
        text = path.read_text(errors="replace")
        meta: dict = {}
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                for line in text[3:end].splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        meta[k.strip()] = v.strip().strip('"').strip("'")
        return meta
    except Exception:
        return {}


def _apply_naming(cfg: dict, doc_type: str) -> str:
    """Return a filename (without extension) applying the project naming convention."""
    proj    = cfg.get("_project", {})
    pattern = proj.get("naming", "{TYPE}-{YYMMDD}")
    today   = datetime.date.today().strftime("%y%m%d")
    client  = re.sub(r"\s+", "", proj.get("client", "PROJ"))[:8].upper()
    project = re.sub(r"\W+", "-", proj.get("project", "PROJ"))[:12].upper()
    return (
        pattern
        .replace("{CLIENT}", client)
        .replace("{TYPE}",    doc_type.upper()[:4])
        .replace("{YYMMDD}", today)
        .replace("{VER}",    "1")
        .replace("{PROJECT}", project)
    )


def _run(cmd: list, timeout: int = 30, input_text: str = "") -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout,
            input=input_text or None
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", f"Comando no encontrado: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout ({timeout}s) ejecutando {cmd[0]}"


# ── Email tools ──────────────────────────────────────────────────────────────


def _tool_doc_embed_image(args: dict) -> str:
    """Inserta una imagen (PNG/JPG/SVG) en un documento .docx existente, con pie de figura opcional."""
    path        = Path(args.get("path", "")).expanduser()
    image_path  = Path(args.get("image_path", "")).expanduser()
    caption     = args.get("caption", "")
    width_in    = args.get("width_inches", 5.0)
    output_path = args.get("output_path", "")

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    if not image_path.exists():
        return f"Imagen no encontrada: {image_path}"
    try:
        from docx import Document
        from docx.shared import Inches, Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document(str(path))
        doc.add_picture(str(image_path), width=Inches(float(width_in)))
        # Center the last paragraph (the image)
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        if caption:
            cap = doc.add_paragraph(caption)
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            try:
                cap.style = doc.styles["Caption"]
            except KeyError:
                for run in cap.runs:
                    run.italic = True
                    run.font.size = Pt(9)
        dest = output_path or str(path)
        doc.save(dest)
        return f"✅ Imagen insertada en {Path(dest).name}  ({image_path.name})"
    except ImportError:
        return "python-docx no disponible. Instala con: pip install python-docx"
    except Exception as exc:
        return f"Error insertando imagen: {exc}"


def _build_word_chart_xml(chart_type: str, categories: list, series_list: list,
                          title: str = "", show_data_labels: bool = False,
                          chart_style: int = 2, show_legend: bool = True,
                          show_gridlines: bool = True, x_title: str = "",
                          y_title: str = "") -> str:
    """Build OOXML DrawingML chart XML for native embedding in a Word document.

    Generates a proper c:chartSpace XML that Word/LibreOffice can render as
    a native editable chart (not a rasterized PNG).

    chart_type: bar | column | stacked_bar | stacked_column | 100_stacked_bar |
                100_stacked_column | line | line_markers | area | stacked_area |
                pie | doughnut | scatter | bubble
    chart_style: 1-48 (Office chart style number; 2 = default Office blue)
    """
    C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
    A = 'http://schemas.openxmlformats.org/drawingml/2006/main'

    # Office accent colors for series (theme colors 1-6)
    _SERIES_COLORS = [
        "4472C4",  # Blue (Accent 1)
        "ED7D31",  # Orange (Accent 2)
        "A5A5A5",  # Grey (Accent 3)
        "FFC000",  # Gold (Accent 4)
        "5B9BD5",  # Light Blue (Accent 5)
        "70AD47",  # Green (Accent 6)
    ]

    def _esc(s: str) -> str:
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    def _series_color_xml(idx: int) -> str:
        color = _SERIES_COLORS[idx % len(_SERIES_COLORS)]
        return (
            f'<c:spPr>'
            f'<a:solidFill xmlns:a="{A}"><a:srgbClr val="{color}"/></a:solidFill>'
            f'<a:ln xmlns:a="{A}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln>'
            f'</c:spPr>'
        )

    ct = chart_type.lower()
    cat_count = len(categories)
    col_letters = 'BCDEFGHIJKLMNOPQRSTUVWXYZ'
    ax1, ax2 = 100, 200

    # ── Category data (shared by bar/line/area/pie) ──────────────────────────
    cat_pts = "".join(
        f'<c:pt idx="{i}"><c:v>{_esc(cat)}</c:v></c:pt>' for i, cat in enumerate(categories)
    )
    cat_ref = (
        f'<c:cat><c:strRef>'
        f'<c:f>Sheet1!$A$2:$A${max(cat_count, 1) + 1}</c:f>'
        f'<c:strCache><c:ptCount val="{cat_count}"/>{cat_pts}</c:strCache>'
        f'</c:strRef></c:cat>'
    )

    def _axis_title_xml(text: str, horiz: bool = True) -> str:
        if not text:
            return ""
        return (
            f'<c:title>'
            f'<c:tx><c:rich>'
            f'<a:bodyPr xmlns:a="{A}" rot="{"0" if horiz else "-5400000"}"/>'
            f'<a:lstStyle xmlns:a="{A}"/>'
            f'<a:p xmlns:a="{A}"><a:r><a:t>{_esc(text)}</a:t></a:r></a:p>'
            f'</c:rich></c:tx>'
            f'<c:overlay val="0"/>'
            f'</c:title>'
        )

    gridline_xml = (
        '<c:majorGridlines>'
        '<c:spPr>'
        f'<a:ln xmlns:a="{A}" w="6350"><a:solidFill><a:srgbClr val="D9D9D9"/></a:solidFill></a:ln>'
        '</c:spPr>'
        '</c:majorGridlines>'
    ) if show_gridlines else ""

    # ── Shared axes for bar/line/area ────────────────────────────────────────
    cat_ax = (
        f'<c:catAx>'
        f'<c:axId val="{ax1}"/>'
        f'<c:scaling><c:orientation val="minMax"/></c:scaling>'
        f'<c:delete val="0"/><c:axPos val="b"/>'
        f'<c:numFmt formatCode="General" sourceLinked="1"/>'
        f'<c:tickLblPos val="nextTo"/>'
        f'{_axis_title_xml(x_title, horiz=True)}'
        f'<c:crossAx val="{ax2}"/>'
        f'<c:auto val="1"/><c:lblAlgn val="ctr"/><c:noMultiLvlLbl val="0"/>'
        f'</c:catAx>'
    )
    val_ax = (
        f'<c:valAx>'
        f'<c:axId val="{ax2}"/>'
        f'<c:scaling><c:orientation val="minMax"/></c:scaling>'
        f'<c:delete val="0"/><c:axPos val="l"/>'
        f'<c:numFmt formatCode="General" sourceLinked="1"/>'
        f'<c:tickLblPos val="nextTo"/>'
        f'{_axis_title_xml(y_title, horiz=False)}'
        f'{gridline_xml}'
        f'<c:crossAx val="{ax1}"/>'
        f'</c:valAx>'
    )

    data_labels_xml = (
        '<c:dLbls>'
        '<c:numFmt formatCode="General" sourceLinked="0"/>'
        '<c:spPr/><c:txPr><a:bodyPr xmlns:a="' + A + '"/><a:lstStyle xmlns:a="' + A + '"/>'
        '<a:p xmlns:a="' + A + '"><a:pPr><a:defRPr sz="900"/></a:pPr></a:p></c:txPr>'
        '<c:showLegendKey val="0"/><c:showVal val="1"/><c:showCatName val="0"/>'
        '<c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/>'
        '</c:dLbls>'
    ) if show_data_labels else ""

    def _make_ser(idx: int, label: str, values: list, col: str,
                  with_color: bool = True, with_labels: bool = False) -> str:
        n = len(values)
        val_pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(values))
        color_xml = _series_color_xml(idx) if with_color else ""
        lbl_xml = data_labels_xml if with_labels else ""
        return (
            f'<c:ser>'
            f'<c:idx val="{idx}"/><c:order val="{idx}"/>'
            f'<c:tx><c:strRef>'
            f'<c:f>Sheet1!${col}$1</c:f>'
            f'<c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>{_esc(label)}</c:v></c:pt></c:strCache>'
            f'</c:strRef></c:tx>'
            f'{color_xml}'
            f'{lbl_xml}'
            f'{cat_ref}'
            f'<c:val><c:numRef>'
            f'<c:f>Sheet1!${col}$2:${col}${max(n, 1) + 1}</c:f>'
            f'<c:numCache><c:formatCode>General</c:formatCode>'
            f'<c:ptCount val="{n}"/>{val_pts}</c:numCache>'
            f'</c:numRef></c:val>'
            f'</c:ser>'
        )

    # Normalize chart type aliases
    ct = chart_type.lower().replace("-", "_")
    _CT_ALIASES = {
        "bar": "column", "horizontal_bar": "bar_horiz",
        "bar_horizontal": "bar_horiz", "column_stacked": "stacked_column",
        "bar_stacked": "stacked_bar", "line_chart": "line",
        "column_chart": "column", "pie_chart": "pie",
    }
    ct = _CT_ALIASES.get(ct, ct)

    # ── Build chart-type-specific XML ────────────────────────────────────────
    if ct in ("column", "bar"):
        # Clustered vertical bars (column) — this is ct="column" or ct="bar" after alias
        all_ser = "".join(
            _make_ser(i, s.get("label", f"Serie {i+1}"), s.get("values", []),
                      col_letters[min(i, len(col_letters)-1)],
                      with_labels=show_data_labels)
            for i, s in enumerate(series_list)
        )
        inner = (
            f'<c:barChart>'
            f'<c:barDir val="col"/>'
            f'<c:grouping val="clustered"/>'
            f'<c:varyColors val="0"/>'
            f'{all_ser}'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:barChart>'
            f'{cat_ax}{val_ax}'
        )

    elif ct == "bar_horiz":
        # Horizontal bar chart
        all_ser = "".join(
            _make_ser(i, s.get("label", f"Serie {i+1}"), s.get("values", []),
                      col_letters[min(i, len(col_letters)-1)],
                      with_labels=show_data_labels)
            for i, s in enumerate(series_list)
        )
        cat_ax_h = cat_ax.replace('axPos val="b"', 'axPos val="l"')
        val_ax_h = val_ax.replace('axPos val="l"', 'axPos val="b"')
        inner = (
            f'<c:barChart>'
            f'<c:barDir val="bar"/>'
            f'<c:grouping val="clustered"/>'
            f'<c:varyColors val="0"/>'
            f'{all_ser}'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:barChart>'
            f'{cat_ax_h}{val_ax_h}'
        )

    elif ct in ("stacked_column", "stacked_bar"):
        bar_dir = "col" if ct == "stacked_column" else "bar"
        all_ser = "".join(
            _make_ser(i, s.get("label", f"Serie {i+1}"), s.get("values", []),
                      col_letters[min(i, len(col_letters)-1)],
                      with_labels=show_data_labels)
            for i, s in enumerate(series_list)
        )
        inner = (
            f'<c:barChart>'
            f'<c:barDir val="{bar_dir}"/>'
            f'<c:grouping val="stacked"/>'
            f'<c:varyColors val="0"/>'
            f'{all_ser}'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:barChart>'
            f'{cat_ax}{val_ax}'
        )

    elif ct in ("100_stacked_column", "100_stacked_bar"):
        bar_dir = "col" if "column" in ct else "bar"
        all_ser = "".join(
            _make_ser(i, s.get("label", f"Serie {i+1}"), s.get("values", []),
                      col_letters[min(i, len(col_letters)-1)])
            for i, s in enumerate(series_list)
        )
        pct_val_ax = val_ax.replace('formatCode="General"', 'formatCode="0%"')
        inner = (
            f'<c:barChart>'
            f'<c:barDir val="{bar_dir}"/>'
            f'<c:grouping val="percentStacked"/>'
            f'<c:varyColors val="0"/>'
            f'{all_ser}'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:barChart>'
            f'{cat_ax}{pct_val_ax}'
        )

    elif ct in ("line", "line_markers"):
        smooth = "1" if ct == "line" else "0"
        marker_xml = '<c:marker><c:symbol val="circle"/><c:size val="4"/></c:marker>' if ct == "line_markers" else ""
        all_ser = "".join(
            (
                f'<c:ser>'
                f'<c:idx val="{i}"/><c:order val="{i}"/>'
                f'<c:tx><c:strRef>'
                f'<c:f>Sheet1!${col_letters[min(i, len(col_letters)-1)]}$1</c:f>'
                f'<c:strCache><c:ptCount val="1"/>'
                f'<c:pt idx="0"><c:v>{_esc(s.get("label", f"Serie {i+1}"))}</c:v></c:pt>'
                f'</c:strCache></c:strRef></c:tx>'
                f'{_series_color_xml(i)}'
                f'{marker_xml}'
                f'{cat_ref}'
                f'<c:val><c:numRef>'
                f'<c:f>Sheet1!${col_letters[min(i, len(col_letters)-1)]}$2:${col_letters[min(i, len(col_letters)-1)]}${max(len(s.get("values", [])), 1) + 1}</c:f>'
                f'<c:numCache><c:formatCode>General</c:formatCode>'
                f'<c:ptCount val="{len(s.get("values", []))}"/>'
                f'{"".join(f"<c:pt idx=\"{j}\"><c:v>{v}</c:v></c:pt>" for j, v in enumerate(s.get("values", [])))}'
                f'</c:numCache></c:numRef></c:val>'
                f'<c:smooth val="{smooth}"/>'
                f'</c:ser>'
            )
            for i, s in enumerate(series_list)
        )
        inner = (
            f'<c:lineChart>'
            f'<c:grouping val="standard"/>'
            f'<c:varyColors val="0"/>'
            f'{all_ser}'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:lineChart>'
            f'{cat_ax}{val_ax}'
        )

    elif ct in ("area", "stacked_area"):
        grouping = "stacked" if ct == "stacked_area" else "standard"
        all_ser = "".join(
            _make_ser(i, s.get("label", f"Serie {i+1}"), s.get("values", []),
                      col_letters[min(i, len(col_letters)-1)])
            for i, s in enumerate(series_list)
        )
        inner = (
            f'<c:areaChart>'
            f'<c:grouping val="{grouping}"/>'
            f'<c:varyColors val="0"/>'
            f'{all_ser}'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:areaChart>'
            f'{cat_ax}{val_ax}'
        )

    elif ct in ("pie", "doughnut"):
        s0 = series_list[0] if series_list else {}
        values = s0.get("values", [])
        n = len(values)
        val_pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(values))
        pie_cat_pts = "".join(
            f'<c:pt idx="{i}"><c:v>{_esc(cat)}</c:v></c:pt>' for i, cat in enumerate(categories)
        )
        pie_cat = (
            f'<c:cat><c:strRef>'
            f'<c:f>Sheet1!$A$2:$A${max(cat_count,1)+1}</c:f>'
            f'<c:strCache><c:ptCount val="{cat_count}"/>{pie_cat_pts}</c:strCache>'
            f'</c:strRef></c:cat>'
        )
        # Pie/doughnut data labels always show percentage + category name
        pie_datalabels = (
            '<c:dLbls>'
            '<c:numFmt formatCode="0%" sourceLinked="0"/>'
            '<c:spPr/><c:txPr>'
            f'<a:bodyPr xmlns:a="{A}"/><a:lstStyle xmlns:a="{A}"/>'
            f'<a:p xmlns:a="{A}"><a:pPr><a:defRPr sz="900"/></a:pPr></a:p>'
            '</c:txPr>'
            '<c:showLegendKey val="0"/><c:showVal val="0"/><c:showCatName val="1"/>'
            '<c:showSerName val="0"/><c:showPercent val="1"/><c:showBubbleSize val="0"/>'
            '<c:separator>, </c:separator>'
            '</c:dLbls>'
        ) if show_data_labels else ""
        pie_ser = (
            f'<c:ser>'
            f'<c:idx val="0"/><c:order val="0"/>'
            f'<c:tx><c:strRef>'
            f'<c:f>Sheet1!$B$1</c:f>'
            f'<c:strCache><c:ptCount val="1"/>'
            f'<c:pt idx="0"><c:v>{_esc(s0.get("label", "Serie 1"))}</c:v></c:pt>'
            f'</c:strCache></c:strRef></c:tx>'
            f'{pie_datalabels}'
            f'{pie_cat}'
            f'<c:val><c:numRef>'
            f'<c:f>Sheet1!$B$2:$B${max(n,1)+1}</c:f>'
            f'<c:numCache><c:formatCode>General</c:formatCode>'
            f'<c:ptCount val="{n}"/>{val_pts}</c:numCache>'
            f'</c:numRef></c:val>'
            f'</c:ser>'
        )
        if ct == "doughnut":
            inner = (
                f'<c:doughnutChart>'
                f'<c:varyColors val="1"/>'
                f'{pie_ser}'
                f'<c:firstSliceAng val="0"/>'
                f'<c:holeSize val="50"/>'
                f'</c:doughnutChart>'
            )
        else:
            inner = (
                f'<c:pieChart>'
                f'<c:varyColors val="1"/>'
                f'{pie_ser}'
                f'<c:firstSliceAng val="0"/>'
                f'</c:pieChart>'
            )

    elif ct == "scatter":
        # Scatter uses valAx for both axes (not catAx)
        sc_parts = []
        for idx, s in enumerate(series_list):
            xvals = s.get("x_values", s.get("values", []))
            yvals = s.get("y_values", [])
            label = _esc(s.get("label", f"Serie {idx+1}"))
            col = col_letters[min(idx, len(col_letters)-1)]
            nx, ny = len(xvals), len(yvals)
            xv_pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(xvals))
            yv_pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(yvals))
            sc_parts.append(
                f'<c:ser>'
                f'<c:idx val="{idx}"/><c:order val="{idx}"/>'
                f'<c:tx><c:strRef><c:f>Sheet1!${col}$1</c:f>'
                f'<c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>{label}</c:v></c:pt></c:strCache>'
                f'</c:strRef></c:tx>'
                f'{_series_color_xml(idx)}'
                f'<c:xVal><c:numRef>'
                f'<c:f>Sheet1!$A$2:$A${max(nx,1)+1}</c:f>'
                f'<c:numCache><c:formatCode>General</c:formatCode>'
                f'<c:ptCount val="{nx}"/>{xv_pts}</c:numCache>'
                f'</c:numRef></c:xVal>'
                f'<c:yVal><c:numRef>'
                f'<c:f>Sheet1!${col}$2:${col}${max(ny,1)+1}</c:f>'
                f'<c:numCache><c:formatCode>General</c:formatCode>'
                f'<c:ptCount val="{ny}"/>{yv_pts}</c:numCache>'
                f'</c:numRef></c:yVal>'
                f'<c:smooth val="0"/>'
                f'</c:ser>'
            )
        # Scatter needs two valAx (x and y), not catAx+valAx
        sc_xax = (
            f'<c:valAx>'
            f'<c:axId val="{ax1}"/>'
            f'<c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="b"/>'
            f'<c:numFmt formatCode="General" sourceLinked="1"/>'
            f'<c:tickLblPos val="nextTo"/>'
            f'{_axis_title_xml(x_title, horiz=True)}'
            f'<c:crossAx val="{ax2}"/>'
            f'</c:valAx>'
        )
        sc_yax = (
            f'<c:valAx>'
            f'<c:axId val="{ax2}"/>'
            f'<c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="l"/>'
            f'<c:numFmt formatCode="General" sourceLinked="1"/>'
            f'<c:tickLblPos val="nextTo"/>'
            f'{_axis_title_xml(y_title, horiz=False)}'
            f'{gridline_xml}'
            f'<c:crossAx val="{ax1}"/>'
            f'</c:valAx>'
        )
        inner = (
            f'<c:scatterChart>'
            f'<c:scatterStyle val="marker"/>'
            f'<c:varyColors val="0"/>'
            f'{"".join(sc_parts)}'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:scatterChart>'
            f'{sc_xax}{sc_yax}'
        )

    elif ct in ("radar", "radar_filled", "radar_markers"):
        radar_style = "filled" if ct == "radar_filled" else "marker"
        radar_parts = []
        for idx, s in enumerate(series_list):
            label = _esc(s.get("label", f"Serie {idx+1}"))
            values = s.get("values", [])
            n = len(values)
            val_pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(values))
            col = col_letters[min(idx, len(col_letters)-1)]
            radar_parts.append(
                f'<c:ser><c:idx val="{idx}"/><c:order val="{idx}"/>'
                f'<c:tx><c:strRef><c:f>Sheet1!${col}$1</c:f>'
                f'<c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>{label}</c:v></c:pt></c:strCache>'
                f'</c:strRef></c:tx>'
                f'{_series_color_xml(idx)}'
                f'{cat_ref}'
                f'<c:val><c:numRef><c:f>Sheet1!${col}$2:${col}${max(n,1)+1}</c:f>'
                f'<c:numCache><c:formatCode>General</c:formatCode>'
                f'<c:ptCount val="{n}"/>{val_pts}</c:numCache>'
                f'</c:numRef></c:val>'
                f'</c:ser>'
            )
        inner = (
            f'<c:radarChart>'
            f'<c:radarStyle val="{radar_style}"/>'
            f'<c:varyColors val="0"/>'
            f'{"".join(radar_parts)}'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:radarChart>'
            f'{cat_ax}{val_ax}'
        )

    elif ct == "bubble":
        bubble_parts = []
        for idx, s in enumerate(series_list):
            xvals = s.get("x_values", s.get("values", []))
            yvals = s.get("y_values", [])
            sizes = s.get("bubble_sizes", s.get("sizes", [10] * len(xvals)))
            label = _esc(s.get("label", f"Serie {idx+1}"))
            col = col_letters[min(idx, len(col_letters)-1)]
            nx, ny, ns = len(xvals), len(yvals), len(sizes)
            xv_pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(xvals))
            yv_pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(yvals))
            sz_pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(sizes))
            bubble_parts.append(
                f'<c:ser><c:idx val="{idx}"/><c:order val="{idx}"/>'
                f'<c:tx><c:strRef><c:f>Sheet1!${col}$1</c:f>'
                f'<c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>{label}</c:v></c:pt></c:strCache>'
                f'</c:strRef></c:tx>'
                f'{_series_color_xml(idx)}'
                f'<c:xVal><c:numRef><c:f>Sheet1!$A$2:$A${max(nx,1)+1}</c:f>'
                f'<c:numCache><c:formatCode>General</c:formatCode><c:ptCount val="{nx}"/>{xv_pts}</c:numCache>'
                f'</c:numRef></c:xVal>'
                f'<c:yVal><c:numRef><c:f>Sheet1!${col}$2:${col}${max(ny,1)+1}</c:f>'
                f'<c:numCache><c:formatCode>General</c:formatCode><c:ptCount val="{ny}"/>{yv_pts}</c:numCache>'
                f'</c:numRef></c:yVal>'
                f'<c:bubbleSize><c:numRef><c:f>Sheet1!$Z$2:$Z${max(ns,1)+1}</c:f>'
                f'<c:numCache><c:formatCode>General</c:formatCode><c:ptCount val="{ns}"/>{sz_pts}</c:numCache>'
                f'</c:numRef></c:bubbleSize>'
                f'</c:ser>'
            )
        sc_xax = (
            f'<c:valAx><c:axId val="{ax1}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="b"/>'
            f'<c:numFmt formatCode="General" sourceLinked="1"/><c:tickLblPos val="nextTo"/>'
            f'{_axis_title_xml(x_title, horiz=True)}<c:crossAx val="{ax2}"/></c:valAx>'
        )
        sc_yax = (
            f'<c:valAx><c:axId val="{ax2}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="l"/>'
            f'<c:numFmt formatCode="General" sourceLinked="1"/><c:tickLblPos val="nextTo"/>'
            f'{_axis_title_xml(y_title, horiz=False)}{gridline_xml}<c:crossAx val="{ax1}"/></c:valAx>'
        )
        inner = (
            f'<c:bubbleChart><c:varyColors val="0"/>'
            f'{"".join(bubble_parts)}'
            f'<c:bubbleScale val="100"/><c:showNegBubbles val="0"/>'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:bubbleChart>{sc_xax}{sc_yax}'
        )

    else:
        # Fallback: clustered column
        all_ser = "".join(
            _make_ser(i, s.get("label", f"Serie {i+1}"), s.get("values", []),
                      col_letters[min(i, len(col_letters)-1)])
            for i, s in enumerate(series_list)
        )
        inner = (
            f'<c:barChart>'
            f'<c:barDir val="col"/><c:grouping val="clustered"/>'
            f'<c:varyColors val="0"/>{all_ser}'
            f'<c:axId val="{ax1}"/><c:axId val="{ax2}"/>'
            f'</c:barChart>{cat_ax}{val_ax}'
        )

    title_xml = ""
    if title:
        title_xml = (
            f'<c:title>'
            f'<c:tx><c:rich>'
            f'<a:bodyPr/><a:lstStyle/>'
            f'<a:p><a:pPr><a:defRPr b="1" sz="1200" spc="-1"/></a:pPr>'
            f'<a:r><a:t>{_esc(title)}</a:t></a:r></a:p>'
            f'</c:rich></c:tx>'
            f'<c:overlay val="0"/>'
            f'</c:title>'
        )

    if show_legend and (ct not in ("pie", "doughnut") or len(series_list) > 1):
        legend_xml = '<c:legend><c:legendPos val="r"/><c:overlay val="0"/></c:legend>'
    else:
        legend_xml = ""

    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<c:chartSpace xmlns:c="{C}" xmlns:a="{A}"'
        f' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<c:lang val="es-ES"/>'
        f'<c:style val="{chart_style}"/>'
        f'<c:roundedCorners val="0"/>'
        f'<c:chart>'
        f'{title_xml}'
        f'<c:autoTitleDeleted val="{"0" if title else "1"}"/>'
        f'<c:plotArea><c:layout/>{inner}</c:plotArea>'
        f'{legend_xml}'
        f'<c:plotVisOnly val="1"/>'
        f'<c:dispBlanksAs val="gap"/>'
        f'</c:chart>'
        f'</c:chartSpace>'
    )


def _embed_word_chart_native(doc, chart_xml: str, width_emu: int, height_emu: int, chart_id: int = 1) -> bool:
    """Add a native OOXML DrawingML chart Part to a python-docx Document.

    Returns True on success, False if python-docx internals are unavailable.
    The chart is added as an inline drawing in a centered paragraph.
    """
    try:
        from docx.opc.part import Part
        from docx.opc.packuri import PackURI
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        import lxml.etree as etree

        pkg = doc.part.package

        # Find a unique chart number in this package
        try:
            existing = [
                p for p in pkg.iter_parts()
                if hasattr(p, 'partname') and '/word/charts/' in str(p.partname)
            ]
            chart_id = len(existing) + 1
        except Exception:
            chart_id = chart_id

        chart_partname = PackURI(f'/word/charts/chart{chart_id}.xml')
        chart_ct = 'application/vnd.openxmlformats-officedocument.drawingml.chart+xml'
        chart_part = Part(chart_partname, chart_ct, chart_xml.encode('utf-8'), pkg)

        chart_rId = doc.part.relate_to(
            chart_part,
            'http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart'
        )

        # Build the inline drawing element that references the chart part
        drawing_xml = (
            f'<w:drawing'
            f' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<wp:inline'
            f' xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
            f' distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{width_emu}" cy="{height_emu}"/>'
            f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{chart_id}" name="Gráfica {chart_id}"/>'
            f'<wp:cNvGraphicFramePr>'
            f'<a:graphicFrameLocks'
            f' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
            f' noChangeAspect="1"/>'
            f'</wp:cNvGraphicFramePr>'
            f'<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            f'<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            f'<c:chart'
            f' xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"'
            f' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
            f' r:id="{chart_rId}"/>'
            f'</a:graphicData>'
            f'</a:graphic>'
            f'</wp:inline>'
            f'</w:drawing>'
        )

        drawing_elem = etree.fromstring(drawing_xml)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run._r.append(drawing_elem)
        return True

    except Exception:
        return False


def _tool_doc_insert_chart_native(args: dict) -> str:
    """Inserta una gráfica nativa OOXML DrawingML en un .docx (editable en Word/LibreOffice).

    Genera un objeto c:chartSpace real embebido en el documento — editable, vectorial,
    sin pérdida de calidad. Si los internals de python-docx no están disponibles,
    cae en modo PNG de alta resolución como respaldo.

    chart_type: bar | column | line | area | pie | doughnut | scatter
    data:
      - categories: ["Ene", "Feb", "Mar"]
      - series: [{"label": "Ventas", "values": [100, 200, 150]}, ...]
    title: título de la gráfica
    style: office | dark | minimal | presentation  (solo afecta al modo PNG fallback)
    width_inches: ancho en pulgadas (default 5.5)
    height_inches: alto en pulgadas (default 3.5)
    output_path: si se omite, sobreescribe path
    """
    raw_path    = (args.get("path") or args.get("doc_path") or "").strip()
    path        = Path(raw_path).expanduser()
    chart_type  = args.get("chart_type", "bar").lower()
    data        = args.get("data", {})
    title       = args.get("title", "")
    width_in    = float(args.get("width_inches", args.get("width", 5.5)))
    height_in   = float(args.get("height_inches", args.get("height", 3.5)))
    output_path = args.get("output_path", "")

    if not raw_path:
        return "Parámetro requerido: path (ruta al .docx donde insertar la gráfica)."
    # Auto-crear el .docx con estilos O365 si no existe todavía
    if not path.exists():
        if raw_path.lower().endswith(".docx"):
            try:
                from docx import Document as _D
                _d = _D()
                _apply_o365_styles_to_new_doc(_d)
                _d.save(str(path))
            except Exception as _e:
                return f"No se pudo crear el documento {path}: {_e}"
        else:
            return f"Documento no encontrado: {path}"

    categories  = data.get("categories", [])
    series_list = data.get("series", [])
    if not series_list:
        vals   = data.get("values", data.get("sizes", []))
        labels = data.get("labels", categories)
        if vals:
            series_list = [{"label": title or "Serie 1", "values": vals}]
            if not categories:
                categories = labels

    if not series_list:
        return "Parámetro requerido: data.series=[{label, values}] o data.values=[...]"

    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document(str(path))

        # Inches → EMU (English Metric Units used by OOXML): 1 inch = 914400 EMU
        width_emu  = int(width_in  * 914400)
        height_emu = int(height_in * 914400)

        # ── Attempt native OOXML chart ──────────────────────────────────────
        chart_xml = _build_word_chart_xml(chart_type, categories, series_list, title)
        ok = _embed_word_chart_native(doc, chart_xml, width_emu, height_emu)

        if ok:
            if title:
                cap = doc.add_paragraph()
                cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = cap.add_run(title)
                r.font.size = Pt(9)
                r.font.italic = True
                r.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
            dest = output_path or str(path)
            doc.save(dest)
            return (
                f"✅ Gráfica OOXML nativa '{chart_type}' insertada en {Path(dest).name}\n"
                f"   Series: {len(series_list)}  Categorías: {len(categories)}  "
                f"Editable en Word/LibreOffice — vectorial sin pérdida de calidad."
            )

        # Native-only: si python-docx no pudo embeber el chartSpace OOXML, no caemos a PNG.
        return (
            f"No se pudo generar la gráfica OOXML nativa '{chart_type}'. "
            f"Verifica python-docx y que chart_type sea válido "
            f"(bar, column, line, line_markers, area, pie, doughnut, scatter, "
            f"stacked_bar, stacked_column, radar)."
        )

    except ImportError as e:
        return f"Dependencia no disponible: {e}\nInstala: pip install python-docx"
    except Exception as exc:
        return f"Error generando gráfica Word: {exc}"


def _tool_doc_apply_style(args: dict) -> str:
    """Aplica estilos de párrafo/titular O365 a un documento .docx (Heading 1, Normal, Title, etc.)."""
    path      = Path(args.get("path", "")).expanduser()
    style_map = args.get("style_map", [])
    # style_map: [{"search": "texto o vacío para párrafo N", "style": "Heading 1", "paragraph": 0}]
    output_path = args.get("output_path", "")
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        from docx import Document
        doc = Document(str(path))
        applied = 0
        paras = doc.paragraphs
        for rule in style_map:
            target_style = rule.get("style", "Normal")
            search_text  = rule.get("search", "")
            para_idx     = rule.get("paragraph")
            if para_idx is not None and 0 <= para_idx < len(paras):
                try:
                    paras[para_idx].style = target_style
                    applied += 1
                except Exception:
                    pass
            elif search_text:
                for p in paras:
                    if search_text.lower() in p.text.lower():
                        try:
                            p.style = target_style
                            applied += 1
                        except Exception:
                            pass
        dest = output_path or str(path)
        doc.save(dest)
        return f"✅ Estilos aplicados: {applied} párrafo(s) en {dest}"
    except ImportError:
        return "python-docx no disponible. Instala con: pip install python-docx"
    except Exception as exc:
        return f"Error aplicando estilos: {exc}"


def _tool_doc_set_table_style(args: dict) -> str:
    """Aplica un estilo de tabla O365 a todas o una tabla específica de un .docx."""
    path        = Path(args.get("path", "")).expanduser()
    style       = args.get("style", "Table Grid")
    table_index = args.get("table_index", -1)  # -1 = todas las tablas
    output_path = args.get("output_path", "")
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        from docx import Document
        doc = Document(str(path))
        tables = doc.tables
        if not tables:
            return "El documento no contiene tablas."
        changed = 0
        for i, tbl in enumerate(tables):
            if table_index < 0 or i == table_index:
                try:
                    tbl.style = style
                    changed += 1
                except Exception:
                    pass
        dest = output_path or str(path)
        doc.save(dest)
        return f"✅ Estilo de tabla '{style}' aplicado a {changed} tabla(s) en {dest}"
    except ImportError:
        return "python-docx no disponible. Instala con: pip install python-docx"
    except Exception as exc:
        return f"Error aplicando estilo de tabla: {exc}"


def _tool_doc_extract_metadata(args: dict) -> str:
    """Extrae metadatos de un documento .docx, .pdf o .pptx (autor, título, fechas, etc.)."""
    path = Path(args.get("path", "")).expanduser()
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    ext = path.suffix.lower()
    try:
        if ext == ".docx":
            from docx import Document
            doc  = Document(str(path))
            core = doc.core_properties
            lines = [f"📄 Metadatos: {path.name}"]
            for attr in ("title", "author", "subject", "description", "keywords",
                         "created", "modified", "last_modified_by", "revision",
                         "category", "content_status", "language"):
                val = getattr(core, attr, None)
                if val:
                    lines.append(f"  {attr:22s}: {val}")
            lines.append(f"  {'parrafos':22s}: {len(doc.paragraphs)}")
            lines.append(f"  {'tablas':22s}: {len(doc.tables)}")
            return "\n".join(lines)
        elif ext == ".pptx":
            from pptx import Presentation
            prs  = Presentation(str(path))
            core = prs.core_properties
            lines = [f"📊 Metadatos: {path.name}"]
            for attr in ("title", "author", "subject", "description", "created", "modified"):
                val = getattr(core, attr, None)
                if val:
                    lines.append(f"  {attr:22s}: {val}")
            lines.append(f"  {'diapositivas':22s}: {len(prs.slides)}")
            return "\n".join(lines)
        elif ext == ".pdf":
            import subprocess
            res = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return f"📄 Metadatos PDF: {path.name}\n{res.stdout}"
            return f"pdfinfo no disponible — instala: apt install poppler-utils\n(returncode={res.returncode}: {res.stderr})"
        else:
            return f"Formato no soportado para metadatos: {ext}. Usa .docx, .pptx o .pdf"
    except ImportError as e:
        return f"Dependencia no disponible: {e}"
    except Exception as exc:
        return f"Error extrayendo metadatos: {exc}"


def _tool_doc_compare(args: dict) -> str:
    """Compara el texto de dos documentos .docx o .md y devuelve un diff unificado."""
    path_a = Path(args.get("path_a", "")).expanduser()
    path_b = Path(args.get("path_b", "")).expanduser()
    context = int(args.get("context", 3))
    for p in (path_a, path_b):
        if not p.exists():
            return f"Fichero no encontrado: {p}"

    def _extract(p: Path) -> list[str]:
        if p.suffix.lower() == ".docx":
            try:
                from docx import Document
                return [para.text for para in Document(str(p)).paragraphs]
            except ImportError:
                return p.read_text(errors="replace").splitlines()
        elif p.suffix.lower() == ".pptx":
            try:
                from pptx import Presentation
                prs = Presentation(str(p))
                lines = []
                for i, sl in enumerate(prs.slides, 1):
                    lines.append(f"[Diapositiva {i}]")
                    for sh in sl.shapes:
                        if sh.has_text_frame:
                            lines.extend(para.text for para in sh.text_frame.paragraphs if para.text.strip())
                return lines
            except ImportError:
                return []
        else:
            return p.read_text(errors="replace").splitlines()

    import difflib
    a_lines = _extract(path_a)
    b_lines = _extract(path_b)
    diff = list(difflib.unified_diff(
        a_lines, b_lines,
        fromfile=path_a.name, tofile=path_b.name,
        lineterm="", n=context,
    ))
    if not diff:
        return f"✅ Los documentos son idénticos: {path_a.name} ↔ {path_b.name}"
    changed = sum(1 for l in diff if l.startswith("+") or l.startswith("-"))
    header  = f"📋 Diff: {path_a.name} ↔ {path_b.name}  ({changed} líneas diferentes)\n"
    return header + "\n".join(diff[:300]) + ("\n[… diff truncado …]" if len(diff) > 300 else "")


def _tool_doc_convert(args: dict) -> str:
    import shutil
    if not shutil.which("pandoc"):
        return (
            "pandoc no encontrado. Instala con:\n"
            "  Linux: sudo apt install pandoc\n"
            "  Mac: brew install pandoc\n"
            "  Windows (WSL): sudo apt install pandoc"
        )
    input_path  = Path(args.get("input_path", "")).expanduser()
    out_format  = args.get("output_format", "")
    output_path = args.get("output_path", "")
    if not input_path or not out_format:
        return "Parámetros requeridos: input_path, output_format (p.ej. 'pdf', 'html', 'docx', 'md')"
    if not input_path.exists():
        return f"Fichero no encontrado: {input_path}"
    if not output_path:
        output_path = str(input_path.with_suffix(f".{out_format}"))
    cmd = ["pandoc", str(input_path), "-o", output_path, "--standalone"]
    if out_format == "pdf":
        cmd += ["--pdf-engine=xelatex"]
    rc, out, err = _run(cmd, timeout=60)
    if rc != 0:
        return f"Error convirtiendo documento:\n{err}"
    size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
    return f"✅ Convertido: {input_path.name} → {output_path}\n   Tamaño: {size:,} bytes"


def _tool_pdf_extract_text(args: dict) -> str:
    import shutil
    path   = Path(args.get("path", "")).expanduser()
    pages  = args.get("pages", "")
    if not path:
        return "Parámetro requerido: path"
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    # Intento 1: pdftotext (poppler-utils)
    if shutil.which("pdftotext"):
        cmd = ["pdftotext"]
        if pages:
            parts = pages.split("-")
            if len(parts) == 2:
                cmd += ["-f", parts[0], "-l", parts[1]]
        cmd += [str(path), "-"]
        rc, out, err = _run(cmd, timeout=30)
        if rc == 0:
            text = out.strip()
            note = f"\n[Extraídas páginas: {pages}]" if pages else ""
            return f"📄 {path.name}{note}\n{'─'*50}\n{text[:8000]}"
        return f"Error con pdftotext: {err}"
    # Intento 2: pdfplumber (pip)
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts)
        return f"📄 {path.name}\n{'─'*50}\n{text[:8000]}"
    except ImportError:
        pass
    return (
        "Necesitas pdftotext o pdfplumber:\n"
        "  Linux: sudo apt install poppler-utils\n"
        "  pip:   pip install pdfplumber"
    )


def _tool_doc_word_count(args: dict) -> str:
    raw = args.get("path", "")
    if not raw:
        return "Parámetro requerido: path"
    path = Path(raw).expanduser()
    if path.is_dir():
        return f"Parámetro requerido: path a un fichero, no a un directorio: {path}"
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        text = path.read_text(errors="replace")
        lines = text.splitlines()
        words = len(text.split())
        chars = len(text)
        chars_no_spaces = len(text.replace(" ", "").replace("\n", ""))
        paragraphs = len([p for p in text.split("\n\n") if p.strip()])
        return (
            f"📊 {path.name}\n"
            f"  Líneas:         {len(lines):>8,}\n"
            f"  Palabras:       {words:>8,}\n"
            f"  Caracteres:     {chars:>8,}\n"
            f"  (sin espacios): {chars_no_spaces:>8,}\n"
            f"  Párrafos:       {paragraphs:>8,}\n"
            f"  Tamaño:         {path.stat().st_size:>8,} bytes"
        )
    except Exception as exc:
        return f"Error leyendo fichero: {exc}"


# ── Spreadsheet tools ────────────────────────────────────────────────────────


def _tool_image_to_text(args: dict) -> str:
    import shutil
    path = Path(args.get("path", "")).expanduser()
    lang = args.get("lang", "spa+eng")
    if not path:
        return "Parámetro requerido: path"
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    if not shutil.which("tesseract"):
        return (
            "tesseract no encontrado. Instala con:\n"
            "  Linux: sudo apt install tesseract-ocr tesseract-ocr-spa\n"
            "  Mac: brew install tesseract tesseract-lang"
        )
    rc, out, err = _run(["tesseract", str(path), "stdout", "-l", lang], timeout=60)
    if rc != 0:
        return f"Error OCR: {err}"
    return f"🔤 OCR de {path.name}:\n{'─'*50}\n{out.strip()}"


def _tool_project_context_read(args: dict) -> str:
    """Read and display project context from OOCODE.md in the workspace or a given path."""
    raw = args.get("path", "OOCODE.md")
    p   = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        return (
            f"No se encontró OOCODE.md en {p.parent}\n"
            "Usa 'project_init_office' para crear la estructura de un proyecto IT."
        )
    meta = _parse_oocode_md(p)
    text = p.read_text(errors="replace")
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            body = text[end + 3:].strip()
    lines = [f"📋 Proyecto: {p}"]
    if meta:
        lines.append("\n**Metadatos:**")
        for k, v in meta.items():
            lines.append(f"  {k}: {v}")
    lines.append(f"\n**Contenido:**\n{body[:3000]}")
    if len(body) > 3000:
        lines.append(f"… [{len(body)-3000} caracteres más]")
    return "\n".join(lines)


def _tool_project_init_office(args: dict) -> str:
    """Initialize an IT project structure: OOCODE.md, doc folders, skeleton CMDB/registers."""
    project   = args.get("project", "")
    if not project:
        return "Parámetro requerido: project (nombre del proyecto)"
    client    = args.get("client", "")
    proj_type = args.get("type", "general")
    dc_source = args.get("dc_source", "")
    dc_target = args.get("dc_target", "")
    team      = args.get("team", "")
    approver  = args.get("approver", "")
    naming    = args.get("naming", "{CLIENT}-{TYPE}-{YYMMDD}-v{VER}")
    base      = Path(args.get("directory", ".")).expanduser()
    if not base.is_absolute():
        base = Path.cwd() / base
    base.mkdir(parents=True, exist_ok=True)

    dirs_spec = ["templates", "docs/rfcs", "docs/reports", "docs/meetings",
                 "docs/incidents", "docs/plans"]
    created_dirs = []
    for d in dirs_spec:
        p = base / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created_dirs.append(d)

    today     = datetime.date.today().isoformat()
    fm: dict  = {
        "project": project, "client": client, "type": proj_type,
        "created": today, "team": team, "approver": approver,
        "naming": naming, "docs_dir": "./docs", "templates_dir": "./templates",
    }
    if dc_source:
        fm["dc_source"] = dc_source
    if dc_target:
        fm["dc_target"] = dc_target
    fm_text = "---\n" + "\n".join(f'{k}: "{v}"' for k, v in fm.items() if v) + "\n---\n"
    descriptions = {
        "migration":   f"Migración de infraestructura desde {dc_source or 'origen'} → {dc_target or 'destino'}.",
        "datacenter":  "Gestión y operación de centro de datos.",
        "rfc":         "Gestión de cambios y RFCs de infraestructura IT.",
        "audit":       "Auditoría de infraestructura IT.",
        "cloud":       "Migración y gestión de infraestructura cloud.",
        "general":     "Proyecto de infraestructura IT.",
    }
    desc = descriptions.get(proj_type, descriptions["general"])
    oocode_content = (
        fm_text
        + f"\n# {project}\n\n{desc}\n\n"
        "## Estructura del proyecto\n\n"
        "```\n./templates/      — Plantillas de documentos\n"
        "./docs/rfcs/      — RFC y Change Requests\n"
        "./docs/reports/   — Informes y reportes\n"
        "./docs/meetings/  — Actas de reunión\n"
        "./docs/incidents/ — Informes de incidencias\n"
        "./docs/plans/     — Planes de migración/cambio\n"
        "```\n"
    )
    oocode_md = base / "OOCODE.md"
    existed = oocode_md.exists()
    if not existed:
        oocode_md.write_text(oocode_content)

    created_files = []
    cmdb_path = base / "cmdb.csv"
    if not cmdb_path.exists():
        with cmdb_path.open("w", newline="") as f:
            csv.writer(f).writerow(
                ["hostname", "ip", "os", "role", "environment", "owner", "status", "location", "notes"]
            )
        created_files.append("cmdb.csv")
    risk_path = base / "risk_register.csv"
    if not risk_path.exists():
        with risk_path.open("w", newline="") as f:
            csv.writer(f).writerow(
                ["id", "description", "probability", "impact", "level", "mitigation", "owner", "status", "date"]
            )
        created_files.append("risk_register.csv")

    lines = [f"✅ Proyecto '{project}' {'encontrado' if existed else 'inicializado'} en {base}"]
    lines.append(f"   {'ℹ️  OOCODE.md existente — no modificado' if existed else '📄 OOCODE.md creado'}")
    if created_dirs:
        lines.append(f"   📁 Directorios: {', '.join(created_dirs)}")
    if created_files:
        lines.append(f"   📊 Registros: {', '.join(created_files)}")
    lines.append(f"   Tipo: {proj_type}  |  Cliente: {client or 'N/A'}  |  Equipo: {team or 'N/A'}")
    lines.append("\nPróximos pasos:")
    lines.append("  1. Añade plantillas .docx/.md en ./templates/")
    lines.append("  2. Rellena cmdb.csv con el inventario de servidores")
    lines.append("  3. Usa doc_create_rfc / datacenter_migration_report para comenzar")
    return "\n".join(lines)


def _tool_doc_project_save(args: dict) -> str:
    """Save generated document content to the correct project folder using naming convention."""
    content  = args.get("content", "")
    doc_type = args.get("doc_type", "general")
    filename = args.get("filename", "")
    # Formal types default to .docx; loose notes/general default to .md
    _FORMAL_TYPES = {"rfc", "change_request", "report", "informe", "meeting", "acta",
                     "incident", "incidencia", "plan", "migration"}
    default_ext = ".docx" if doc_type.lower() in _FORMAL_TYPES else ".md"
    ext      = args.get("ext", default_ext)
    if not content:
        return "Parámetro requerido: content (texto del documento)"

    cfg  = _load_config()
    cwd  = Path.cwd()
    docs_base = Path(args.get("directory", cfg.get("_docs_dir", str(cwd / "docs")))).expanduser()
    type_dirs = {
        "rfc": "rfcs", "change_request": "rfcs",
        "report": "reports", "informe": "reports",
        "meeting": "meetings", "acta": "meetings",
        "incident": "incidents", "incidencia": "incidents",
        "plan": "plans", "migration": "plans",
        "general": ".",
    }
    subdir = type_dirs.get(doc_type.lower(), "general")
    # Evitar doble directorio: si docs_base ya termina en el subdir, no lo añadimos
    if subdir == "." or docs_base.name == subdir:
        save_dir = docs_base
    else:
        save_dir = docs_base / subdir
    save_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        name = re.sub(r"[^\w\-]", "", _apply_naming(cfg, doc_type))
        filename = (name or f"{doc_type}-{datetime.date.today().strftime('%Y%m%d')}") + ext

    save_path = save_dir / filename
    if save_path.exists():
        stem, sfx = save_path.stem, save_path.suffix
        i = 2
        while save_path.exists():
            save_path = save_dir / f"{stem}_v{i}{sfx}"
            i += 1

    if save_path.suffix.lower() == ".docx":
        # Documento O365 nativo: crea el .docx con estilos y vuelca el texto como
        # párrafos nativos (énfasis inline). Para estructura rica, usar doc_create.
        try:
            from docx import Document as _Doc
            _d = _Doc()
            _apply_o365_styles_to_new_doc(_d)
            _render_native_paragraphs(_d, content)
            _d.save(str(save_path))
        except Exception as exc:
            save_path = save_path.with_suffix(".md")
            save_path.write_text(content)
            return (
                f"⚠ No se pudo generar .docx nativo ({exc}); guardado como Markdown: {save_path}\n"
                f"   Tipo: {doc_type}  |  Tamaño: {save_path.stat().st_size:,} bytes"
            )
    else:
        save_path.write_text(content)
    return (
        f"✅ Documento guardado: {save_path}\n"
        f"   Tipo: {doc_type}  |  Tamaño: {save_path.stat().st_size:,} bytes"
    )


# ── Bloque 2: Documento inteligente ──────────────────────────────────────────


def _extract_section_text(text: str, section: str) -> tuple[str, int, int]:
    """Find section by heading in markdown text. Returns (section_text, start_line, end_line)."""
    lines = text.splitlines()
    start = end = None
    heading_lvl = 0
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            lvl = len(m.group(1))
            if section.lower() in m.group(2).lower():
                start = i
                heading_lvl = lvl
            elif start is not None and lvl <= heading_lvl:
                end = i
                break
    if start is None:
        return "", -1, -1
    if end is None:
        end = len(lines)
    return "\n".join(lines[start:end]), start, end


def _tool_doc_read(args: dict) -> str:
    """Read text content from a .docx, .md, or .txt file. Optionally extract a specific section."""
    raw = args.get("path", "")
    if not raw or not str(raw).strip():
        return "Parámetro requerido: path"
    path      = Path(raw).expanduser()
    max_chars = int(args.get("max_chars", 8000))
    section   = args.get("section", "")
    if not path.exists():
        return f"Fichero no encontrado: {path}"

    ext = path.suffix.lower()
    # Plain text formats
    if ext in (".md", ".txt", ".rst", ".html", ".csv"):
        text = path.read_text(errors="replace")
        if section:
            stext, sl, el = _extract_section_text(text, section)
            if sl == -1:
                return f"Sección '{section}' no encontrada en {path.name}"
            return f"📄 {path.name} — Sección: {section}\n{'─'*50}\n{stext[:max_chars]}"
        return f"📄 {path.name}\n{'─'*50}\n{text[:max_chars]}"

    if ext == ".docx":
        # Try python-docx
        try:
            from docx import Document  # type: ignore
            doc = Document(str(path))
            parts: list[str] = []
            in_sec = not bool(section)
            sec_lvl = 0
            for para in doc.paragraphs:
                style = para.style.name
                is_heading = style.startswith("Heading")
                if section:
                    if is_heading and section.lower() in para.text.lower():
                        in_sec = True
                        try:
                            sec_lvl = int(style.split()[-1])
                        except (ValueError, IndexError):
                            sec_lvl = 1
                        parts.append(f"{'#'*sec_lvl} {para.text}")
                        continue
                    if is_heading and in_sec:
                        try:
                            if int(style.split()[-1]) <= sec_lvl:
                                break
                        except (ValueError, IndexError):
                            break
                if in_sec:
                    if is_heading:
                        try:
                            lvl = int(style.split()[-1])
                        except (ValueError, IndexError):
                            lvl = 2
                        parts.append(f"{'#'*lvl} {para.text}")
                    elif para.text.strip():
                        parts.append(para.text)
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            text = "\n".join(parts)
            label = f" — Sección: {section}" if section else ""
            return f"📄 {path.name}{label}\n{'─'*50}\n{text[:max_chars]}"
        except ImportError:
            pass

        # Fallback: pandoc
        import shutil
        if shutil.which("pandoc"):
            rc, out, err = _run(["pandoc", str(path), "-t", "plain"], timeout=30)
            if rc == 0:
                text = out.strip()
                if section:
                    stext, sl, _ = _extract_section_text(text, section)
                    if sl != -1:
                        text = stext
                return f"📄 {path.name} (pandoc)\n{'─'*50}\n{text[:max_chars]}"

        # Last resort: strip XML
        try:
            import zipfile
            with zipfile.ZipFile(str(path)) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()
            return f"📄 {path.name} (XML extraído)\n{'─'*50}\n{text[:max_chars]}"
        except Exception as exc:
            return f"Error leyendo .docx: {exc}"

    return f"Formato no soportado para doc_read: {ext}. Usa pdf_extract_text para PDFs."


def _tool_doc_update_section(args: dict) -> str:
    """Replace the content of a section (by heading text) in a .md or .docx file."""
    raw = args.get("path", "")
    if not raw or not str(raw).strip():
        return "Parámetro requerido: path"
    path        = Path(raw).expanduser()
    section     = args.get("section", "")
    new_content = args.get("new_content") or args.get("content", "")
    if not section:
        return "Parámetro requerido: section (texto del encabezado a actualizar)"
    if new_content is None or new_content == "":
        return "Parámetro requerido: new_content (nuevo contenido de la sección)"
    if not path.exists():
        return f"Fichero no encontrado: {path}"

    ext = path.suffix.lower()
    if ext in (".md", ".txt", ".rst"):
        text = path.read_text(errors="replace")
        lines = text.splitlines()
        _, start, end = _extract_section_text(text, section)
        if start == -1:
            return f"Sección '{section}' no encontrada en {path.name}"
        heading_line = lines[start]
        new_lines = lines[:start + 1] + [""] + new_content.splitlines() + [""] + lines[end:]
        path.write_text("\n".join(new_lines))
        replaced = end - start - 1
        return (
            f"✅ Sección '{section}' actualizada en {path.name}\n"
            f"   Línea {start+1}: {heading_line[:60]}\n"
            f"   Líneas reemplazadas: {replaced} → {len(new_content.splitlines())}"
        )

    if ext == ".docx":
        try:
            from docx import Document  # type: ignore
            doc = Document(str(path))
            paras = doc.paragraphs
            start_idx = end_idx = None
            sec_lvl = 0
            for i, para in enumerate(paras):
                style = para.style.name
                if style.startswith("Heading") and section.lower() in para.text.lower():
                    start_idx = i
                    try:
                        sec_lvl = int(style.split()[-1])
                    except (ValueError, IndexError):
                        sec_lvl = 1
                elif start_idx is not None and style.startswith("Heading"):
                    try:
                        if int(style.split()[-1]) <= sec_lvl:
                            end_idx = i
                            break
                    except (ValueError, IndexError):
                        end_idx = i
                        break
            if start_idx is None:
                return f"Sección '{section}' no encontrada en {path.name}"
            if end_idx is None:
                end_idx = len(paras)

            # Delete paragraphs between heading and end (from end-1 down to start+1)
            body = doc.element.body
            body_children = list(body)
            heading_elem = paras[start_idx]._element
            end_elem     = paras[end_idx]._element if end_idx < len(paras) else None
            h_pos  = body_children.index(heading_elem)
            e_pos  = body_children.index(end_elem) if end_elem is not None else len(body_children)
            for elem in body_children[h_pos + 1:e_pos]:
                body.remove(elem)

            # Insert new paragraphs after heading
            from docx.oxml import OxmlElement  # type: ignore
            ref = heading_elem
            for line in new_content.splitlines():
                p = OxmlElement("w:p")
                r = OxmlElement("w:r")
                t = OxmlElement("w:t")
                t.text = line
                if line.startswith(" "):
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                r.append(t)
                p.append(r)
                ref.addnext(p)
                ref = p

            doc.save(str(path))
            return f"✅ Sección '{section}' actualizada en {path.name}"
        except ImportError:
            return "python-docx requerido para editar .docx: pip install python-docx"
        except Exception as exc:
            return f"Error actualizando sección .docx: {exc}"

    return f"Formato no soportado para doc_update_section: {ext}"


def _tool_doc_version_bump(args: dict) -> str:
    """Increment the version number in a document's front matter or first heading."""
    raw = args.get("path", "")
    if not raw or not str(raw).strip():
        return "Parámetro requerido: path"
    path = Path(raw).expanduser()
    bump = args.get("bump", "patch")  # major | minor | patch
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    text  = path.read_text(errors="replace")
    today = datetime.date.today().isoformat()

    # Match "version: X.Y.Z" or "version: X.Y" in front matter
    ver_fm = re.compile(r"^(version:\s*)([0-9]+)\.([0-9]+)\.?([0-9]*)(.*)$", re.MULTILINE | re.IGNORECASE)
    m = ver_fm.search(text)
    if m:
        major, minor, patch_v = int(m.group(2)), int(m.group(3)), int(m.group(4) or 0)
        old_ver = f"{major}.{minor}.{patch_v}" if m.group(4) else f"{major}.{minor}"
        if bump == "major":
            major += 1; minor = 0; patch_v = 0
        elif bump == "minor":
            minor += 1; patch_v = 0
        else:
            patch_v += 1
        new_ver = f"{major}.{minor}.{patch_v}"
        new_text = ver_fm.sub(lambda mm: mm.group(1) + new_ver + mm.group(5), text, count=1)
        new_text = re.sub(r"^(modified:\s*).*$", f"\\g<1>{today}", new_text, flags=re.MULTILINE)
        path.write_text(new_text)
        return f"✅ Versión: {old_ver} → {new_ver} en {path.name}\n   Modificado: {today}"

    # Fallback: "vX.Y" anywhere in the first 30 lines
    first_block = "\n".join(text.splitlines()[:30])
    m2 = re.search(r"\bv?([0-9]+)\.([0-9]+)\.?([0-9]*)\b", first_block)
    if m2:
        old_ver_str = m2.group(0)
        major, minor, patch_v = int(m2.group(1)), int(m2.group(2)), int(m2.group(3) or 0)
        if bump == "major":
            major += 1; minor = 0; patch_v = 0
        elif bump == "minor":
            minor += 1; patch_v = 0
        else:
            patch_v += 1
        new_ver = f"{major}.{minor}.{patch_v}"
        path.write_text(text.replace(old_ver_str, new_ver, 1))
        return f"✅ Versión: {old_ver_str} → {new_ver} en {path.name}"

    # No version found — add to front matter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            new_text = text[:end] + f"version: 1.0.0\nmodified: {today}\n" + text[end:]
            path.write_text(new_text)
            return f"✅ Versión añadida: 1.0.0 en {path.name}"
    return (
        f"No se encontró versión en {path.name}\n"
        "Añade 'version: 1.0.0' al front matter YAML (entre --- y ---)"
    )


# ── Bloque 3: CMDB y activos ──────────────────────────────────────────────────


def _tool_doc_read_template_fields(args: dict) -> str:
    """Extract {{FIELD}} placeholders from a .docx, .md or .txt template."""
    raw = args.get("path", "")
    if not raw or not str(raw).strip():
        return "Parámetro requerido: path"
    path = Path(raw).expanduser()
    if not path.exists():
        return f"Fichero no encontrado: {path}"

    fields: set[str] = set()
    field_re = re.compile(r"\{\{([A-Z0-9_\s]+?)\}\}", re.IGNORECASE)

    if path.suffix.lower() == ".docx":
        try:
            import zipfile as _zf
            from lxml import etree as _et
            W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            WQN = f"{{{W}}}"
            field_info: dict[str, list[str]] = {}  # field → [context, ...]

            with _zf.ZipFile(str(path)) as z:
                for xml_name in z.namelist():
                    if not (xml_name.startswith("word/") and xml_name.endswith(".xml")):
                        continue
                    if any(s in xml_name for s in ("theme", "fontTable", "numbering")):
                        continue
                    try:
                        root = _et.fromstring(z.read(xml_name))
                    except Exception:
                        continue

                    for para in root.iter(f"{WQN}p"):
                        # Get paragraph style
                        ppr = para.find(f"{WQN}pPr")
                        style_val = ""
                        if ppr is not None:
                            ps = ppr.find(f"{WQN}pStyle")
                            if ps is not None:
                                style_val = ps.get(f"{WQN}val", "")
                        # Determine context label
                        if "header" in xml_name:
                            ctx = "cabecera"
                        elif "footer" in xml_name:
                            ctx = "pie de página"
                        elif style_val.startswith("Heading") or style_val.startswith("heading"):
                            lvl = style_val[-1] if style_val[-1].isdigit() else "?"
                            ctx = f"título nivel {lvl}"
                        elif style_val in ("portadaDatos", "Contenidodelmarcouser"):
                            ctx = "portada/cuadro de texto"
                        elif style_val in ("TablaInfo", "TablaNormal", "TablaNormal0"):
                            ctx = "tabla"
                        elif style_val == "toc 1" or style_val.startswith("toc"):
                            ctx = "índice"
                        else:
                            ctx = "cuerpo"

                        # Concatenate all run texts to heal split placeholders
                        full = "".join(
                            (r.find(f"{WQN}t").text or "")
                            if r.find(f"{WQN}t") is not None else ""
                            for r in para.findall(f"{WQN}r")
                        )
                        for m in field_re.finditer(full):
                            key = m.group(1).strip().upper()
                            if key not in field_info:
                                field_info[key] = []
                            if ctx not in field_info[key]:
                                field_info[key].append(ctx)

        except Exception as exc:
            return f"Error leyendo .docx: {exc}"

        if not field_info:
            return f"No se encontraron campos {{{{CAMPO}}}} en: {path.name}"

        lines = [
            f"📋 Campos de plantilla en {path.name} — {len(field_info)} campo(s):",
            f"   Herramienta recomendada: doc_fill_corporate_template",
            "",
        ]
        for key in sorted(field_info):
            ctx_str = " · ".join(field_info[key])
            lines.append(f"  {{{{{key}}}}}  →  {ctx_str}")
        lines.append("")
        lines.append("Ejemplo de llamada:")
        lines.append('  doc_fill_corporate_template(template_path="' + str(path) + '",')
        lines.append('    fields={' + ", ".join(f'"{k}": "..."' for k in sorted(field_info)[:4]) + ("}, ...)" if len(field_info) > 4 else "})"))
        return "\n".join(lines)

    else:
        try:
            text = path.read_text(errors="replace")
            for m in field_re.finditer(text):
                fields.add(m.group(1).strip().upper())
        except Exception as exc:
            return f"Error leyendo fichero: {exc}"

    if not fields:
        return f"No se encontraron campos {{{{CAMPO}}}} en: {path.name}"
    lines = [f"📋 Campos de plantilla en {path.name} — {len(fields)} campo(s):"]
    for f in sorted(fields):
        lines.append(f"  {{{{  {f}  }}}}")
    return "\n".join(lines)


def _tool_doc_fill_template(args: dict) -> str:
    """Fill template placeholders in .docx/.xlsx/.pptx or text files.

    Supports two template syntaxes:
    - Jinja2/docxtpl: {{ campo }} or {% if ... %}  (recommended for .docx)
    - Simple substitution: {{CAMPO}} or {{campo}}  (any format)

    For .docx: uses docxtpl (Jinja2 engine) as primary — handles run-split
    placeholders perfectly, preserves ALL original styles, supports loops/conditionals.
    For .xlsx: openpyxl cell replacement.
    For .pptx: python-pptx text replacement.
    For text (.md/.txt/.html): simple string replacement.
    """
    _tpl_str      = args.get("template_path", "")
    output_path   = args.get("output_path", "")
    fields        = args.get("fields", {})
    use_jinja     = args.get("use_jinja", True)  # default True — use docxtpl

    if not _tpl_str:
        return "Parámetro requerido: template_path"
    template_path = Path(_tpl_str).expanduser()
    if not template_path.exists():
        return f"Plantilla no encontrada: {template_path}"
    if not isinstance(fields, dict):
        return "Parámetro requerido: fields (objeto JSON de {campo: valor})"
    if not fields:
        return "Parámetro requerido: fields — el diccionario de campos no puede estar vacío"

    if not output_path:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(template_path.parent / f"{template_path.stem}_{ts}{template_path.suffix}")
    out_path = Path(output_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ext = template_path.suffix.lower()

    # ── .docx — docxtpl (Jinja2) as primary ─────────────────────────────────
    if ext in (".docx", ".dotx"):
        # Primary: docxtpl (handles split runs, Jinja2 syntax, loops, conditionals)
        if use_jinja:
            try:
                from docxtpl import DocxTemplate
                tpl = DocxTemplate(str(template_path))
                # Build context: provide both UPPER and lower versions of each key
                context: dict = {}
                for k, v in fields.items():
                    context[str(k)]       = v
                    context[str(k).upper()] = v
                    context[str(k).lower()] = v
                tpl.render(context)
                tpl.save(str(out_path))
                filled = len([k for k in fields if k])
                return (
                    f"✅ Plantilla rellenada con docxtpl (Jinja2): {out_path.name}\n"
                    f"   Origen: {template_path.name}\n"
                    f"   Campos provistos: {filled}  |  Estilos originales preservados\n"
                    f"   Tamaño: {out_path.stat().st_size:,} bytes"
                )
            except ImportError:
                pass  # fall through to python-docx
            except Exception as exc:
                # If Jinja2 rendering fails (template uses {{CAMPO}} not {{ campo }}),
                # fall through to the run-by-run approach
                if "unexpected" not in str(exc).lower() and "jinja" not in str(exc).lower():
                    return f"Error con docxtpl: {exc}"

        # Secondary: python-docx run-by-run with cross-run healing
        try:
            from docx import Document

            def _replace_all(text: str) -> tuple[str, int]:
                n = 0
                for key, val in fields.items():
                    for ph in (
                        f"{{{{{str(key)}}}}}",
                        f"{{{{{str(key).upper()}}}}}",
                        f"{{{{{str(key).lower()}}}}}",
                        f"{{{{ {str(key)} }}}}",
                        f"{{{{ {str(key).upper()} }}}}",
                    ):
                        if ph in text:
                            text = text.replace(ph, str(val))
                            n += 1
                return text, n

            def _heal_para(para) -> int:
                """Heal run-split placeholders preserving run-level formatting.

                For placeholders split across multiple runs (Word artifact), we
                locate the affected run span and put the replacement in the first
                run of the span while clearing the others — keeping each run's
                formatting intact for surrounding text.
                """
                n = 0
                # First pass: replace within individual runs (fast path)
                for run in para.runs:
                    t, c = _replace_all(run.text)
                    if c:
                        run.text = t
                        n += c

                # Second pass: cross-run healing for split placeholders
                runs = para.runs
                if not runs:
                    return n
                full = "".join(r.text for r in runs)
                new_full, c2 = _replace_all(full)
                if not c2:
                    return n

                # Build cumulative byte positions for each run boundary in old text
                cum = []
                pos = 0
                for r in runs:
                    pos += len(r.text)
                    cum.append(pos)

                # Distribute new_full back across runs by old proportions,
                # keeping each run's formatting object (bold/italic/font/color).
                new_pos = 0
                old_pos = 0
                for r_i, run in enumerate(runs):
                    old_end  = cum[r_i]
                    old_len  = old_end - old_pos
                    old_pos  = old_end
                    is_last  = (r_i == len(runs) - 1)

                    if new_pos >= len(new_full):
                        run.text = ""
                        continue
                    if is_last:
                        run.text = new_full[new_pos:]
                        new_pos = len(new_full)
                    else:
                        # Proportional slice: give this run the same char count
                        # as it had before; last run absorbs any remainder.
                        slice_end = new_pos + old_len
                        run.text  = new_full[new_pos:slice_end]
                        new_pos   = slice_end
                n += c2
                return n

            doc = Document(str(template_path))
            total = 0
            for p in doc.paragraphs:
                total += _heal_para(p)
            for tbl in doc.tables:
                for row in tbl.rows:
                    for cell in row.cells:
                        for p in cell.paragraphs:
                            total += _heal_para(p)
            for section in doc.sections:
                for p in getattr(section.header, "paragraphs", []):
                    total += _heal_para(p)
                for p in getattr(section.footer, "paragraphs", []):
                    total += _heal_para(p)
            doc.save(str(out_path))
            return (
                f"✅ Plantilla rellenada (python-docx): {out_path.name}\n"
                f"   Origen: {template_path.name}  |  Reemplazos: {total}\n"
                f"   Tamaño: {out_path.stat().st_size:,} bytes\n"
                f"   Consejo: usa {{ campo }} en tu plantilla para compatibilidad docxtpl."
            )
        except ImportError:
            pass
        except Exception as exc:
            return f"Error rellenando .docx: {exc}"

        # Last resort: raw zip/XML replacement
        try:
            import zipfile
            with zipfile.ZipFile(str(template_path), "r") as zin:
                files_data = {n: zin.read(n) for n in zin.namelist()}
            total = 0
            for xml_name in [n for n in files_data if n.startswith("word/") and n.endswith(".xml")]:
                try:
                    text = files_data[xml_name].decode("utf-8", errors="replace")
                    text, n = _replace_all(text)  # type: ignore[name-defined]
                    total += n
                    files_data[xml_name] = text.encode("utf-8")
                except Exception:
                    pass
            with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as zout:
                for name, data in files_data.items():
                    zout.writestr(name, data)
            return (
                f"✅ Plantilla rellenada (zip/XML fallback): {out_path.name}\n"
                f"   Reemplazos XML: {total}  |  Instala docxtpl para mejor soporte."
            )
        except Exception as exc:
            return f"Error rellenando .docx (zip): {exc}"

    # ── .xlsx — openpyxl cell replacement ───────────────────────────────────
    elif ext == ".xlsx":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(template_path))
            total = 0
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for cell in row:
                        if cell.value and isinstance(cell.value, str):
                            new_val = cell.value
                            for key, val in fields.items():
                                for ph in (f"{{{{{key}}}}}", f"{{{{{str(key).upper()}}}}}", f"{{{{ {key} }}}}"):
                                    if ph in new_val:
                                        new_val = new_val.replace(ph, str(val))
                                        total += 1
                            cell.value = new_val
            wb.save(str(out_path))
            return (
                f"✅ Plantilla .xlsx rellenada: {out_path.name}\n"
                f"   Celdas modificadas: {total}  |  Tamaño: {out_path.stat().st_size:,} bytes"
            )
        except Exception as exc:
            return f"Error rellenando .xlsx: {exc}"

    # ── .pptx — python-pptx text replacement ────────────────────────────────
    elif ext in (".pptx", ".potx"):
        try:
            from pptx import Presentation
            prs = Presentation(str(template_path))
            total = 0
            def _repl_pptx(text: str) -> tuple[str, int]:
                n = 0
                for key, val in fields.items():
                    for ph in (f"{{{{{key}}}}}", f"{{{{{str(key).upper()}}}}}", f"{{{{ {key} }}}}"):
                        if ph in text:
                            text = text.replace(ph, str(val))
                            n += 1
                return text, n
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            for run in para.runs:
                                new_t, n = _repl_pptx(run.text)
                                if n:
                                    run.text = new_t
                                    total += n
            prs.save(str(out_path))
            return (
                f"✅ Plantilla .pptx rellenada: {out_path.name}\n"
                f"   Reemplazos: {total}  |  Tamaño: {out_path.stat().st_size:,} bytes"
            )
        except ImportError:
            return "python-pptx no disponible. Instala con: pip install python-pptx"
        except Exception as exc:
            return f"Error rellenando .pptx: {exc}"

    # ── Texto plano (.md, .txt, .html, .csv…) ────────────────────────────────
    else:
        try:
            text = template_path.read_text(errors="replace")
            total = 0
            for key, val in fields.items():
                for ph in (f"{{{{{key}}}}}", f"{{{{{str(key).upper()}}}}}", f"{{{{ {key} }}}}",
                           f"{{{{{str(key).lower()}}}}}"):
                    if ph in text:
                        text = text.replace(ph, str(val))
                        total += 1
            out_path.write_text(text, encoding="utf-8")
            return (
                f"✅ Plantilla rellenada: {out_path.name}\n"
                f"   Reemplazos: {total}  |  Tamaño: {out_path.stat().st_size:,} bytes"
            )
        except Exception as exc:
            return f"Error rellenando plantilla: {exc}"


def _tool_doc_fill_corporate_template(args: dict) -> str:
    """Fill a corporate .docx template preserving ALL original formatting.

    Uses ZIP+lxml for full XML control:
    - Heals run-split {{CAMPO}} placeholders (Word XML artifact)
    - Replaces in body paragraphs, tables, headers, footers, text boxes
    - Multi-paragraph values: provide a list or use '\\n\\n' as paragraph separator
    - Updates TOC: sets updateFields in settings.xml so Word recalculates on open
    - Preserves ALL original styles, images, backgrounds, page layout at 100%
    """
    import zipfile as _zipfile
    import re as _re
    from copy import deepcopy as _deepcopy

    _tpl   = args.get("template_path", "")
    _out   = args.get("output_path", "")
    fields     = args.get("fields", {})
    update_toc = args.get("update_toc", True)

    if not _tpl:
        return "Parámetro requerido: template_path"
    template_path = Path(_tpl).expanduser()
    if not template_path.exists():
        return f"Plantilla no encontrada: {template_path}"
    if template_path.suffix.lower() not in (".docx", ".dotx"):
        return "doc_fill_corporate_template solo soporta .docx/.dotx"
    if not isinstance(fields, dict) or not fields:
        return "Parámetro requerido: fields — diccionario no vacío {CAMPO: valor}"

    if not _out:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        _out = str(template_path.parent / f"{template_path.stem}_{ts}{template_path.suffix}")
    out_path = Path(_out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from lxml import etree as _etree
    except ImportError:
        return "lxml no disponible. Instala con: pip install lxml"

    W        = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    WQN      = f"{{{W}}}"
    XML_SPC  = "{http://www.w3.org/XML/1998/namespace}space"
    PH_RE    = _re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")

    # Build lookup: UPPER, lower, original → value
    lookup: dict[str, object] = {}
    for k, v in fields.items():
        lookup[str(k).upper()] = v
        lookup[str(k).lower()] = v
        lookup[str(k)]         = v

    def _heal_runs(para_elem) -> str:
        """Merge runs in paragraph to fix split {{CAMPO}} placeholders.

        Word splits placeholder text across multiple <w:r> elements.
        Strategy: concatenate all run texts, place result in first run,
        clear subsequent runs. Paragraph style and pPr are untouched.
        """
        runs = para_elem.findall(f"{WQN}r")
        if not runs:
            return ""
        full = "".join(
            (r.find(f"{WQN}t").text or "") if r.find(f"{WQN}t") is not None else ""
            for r in runs
        )
        if not PH_RE.search(full):
            return full  # No placeholder — nothing to heal
        t0 = runs[0].find(f"{WQN}t")
        if t0 is None:
            t0 = _etree.SubElement(runs[0], f"{WQN}t")
        t0.text = full
        t0.set(XML_SPC, "preserve")
        for r in runs[1:]:
            t = r.find(f"{WQN}t")
            if t is not None:
                t.text = ""
        return full

    def _do_replace(text: str) -> str:
        return PH_RE.sub(
            lambda m: str(lookup.get(m.group(1).upper(), m.group(0))), text
        )

    def _expand_para(para_elem, lines: list) -> None:
        """Replace placeholder paragraph with one paragraph per line.

        First line is set in-place. Subsequent lines are deep-copied
        paragraphs inserted after the original, preserving the style.
        """
        parent = para_elem.getparent()
        if parent is None:
            return
        idx = list(parent).index(para_elem)

        # First line: update existing runs
        runs = para_elem.findall(f"{WQN}r")
        if runs:
            t0 = runs[0].find(f"{WQN}t")
            if t0 is None:
                t0 = _etree.SubElement(runs[0], f"{WQN}t")
            t0.text = lines[0] if lines else ""
            if t0.text and (t0.text[0] == " " or t0.text[-1] == " "):
                t0.set(XML_SPC, "preserve")
            for extra in runs[1:]:
                para_elem.remove(extra)

        # Subsequent lines: clone paragraph, set new text
        for i, line in enumerate(lines[1:], 1):
            new_p = _deepcopy(para_elem)
            new_runs = new_p.findall(f"{WQN}r")
            if new_runs:
                new_t = new_runs[0].find(f"{WQN}t")
                if new_t is None:
                    new_t = _etree.SubElement(new_runs[0], f"{WQN}t")
                new_t.text = line
                if line and (line[0] == " " or line[-1] == " "):
                    new_t.set(XML_SPC, "preserve")
                for extra in new_runs[1:]:
                    new_p.remove(extra)
            parent.insert(idx + i, new_p)

    def _process_para(para_elem) -> int:
        """Heal and replace placeholders in one paragraph. Returns 1 if replaced."""
        full = _heal_runs(para_elem)
        if not PH_RE.search(full):
            return 0

        stripped = full.strip()

        # Whole paragraph = single placeholder → multi-paragraph expansion possible
        m = PH_RE.fullmatch(stripped)
        if m:
            key = m.group(1).upper()
            val = lookup.get(key)
            if val is not None:
                if isinstance(val, list):
                    lines = [str(x) for x in val if str(x) != ""] or [""]
                    _expand_para(para_elem, lines)
                    return 1
                if isinstance(val, str) and "\n\n" in val:
                    # Split on double newline = paragraph separator
                    lines = [p.strip() for p in _re.split(r"\n\s*\n", val) if p.strip()]
                    if len(lines) > 1:
                        _expand_para(para_elem, lines)
                        return 1

        # Simple in-place replacement
        new_text = _do_replace(full)
        if new_text == full:
            return 0
        runs = para_elem.findall(f"{WQN}r")
        if runs:
            t = runs[0].find(f"{WQN}t")
            if t is None:
                t = _etree.SubElement(runs[0], f"{WQN}t")
            t.text = new_text
            if new_text and (new_text[0] == " " or new_text[-1] == " "):
                t.set(XML_SPC, "preserve")
        return 1

    # ── Read template ZIP ────────────────────────────────────────────────────
    try:
        with _zipfile.ZipFile(str(template_path), "r") as zin:
            zip_data = {name: zin.read(name) for name in zin.namelist()}
    except Exception as e:
        return f"Error abriendo plantilla: {e}"

    total = 0
    skip = {"theme", "fontTable", "numbering"}

    for part_name in list(zip_data):
        if not (part_name.startswith("word/") and part_name.endswith(".xml")):
            continue
        if any(s in part_name for s in skip):
            continue
        try:
            root = _etree.fromstring(zip_data[part_name])
        except Exception:
            continue
        # Collect paragraphs first to avoid iterator invalidation during _expand_para
        paras = list(root.iter(f"{WQN}p"))
        part_count = sum(_process_para(p) for p in paras)
        if part_count:
            total += part_count
            zip_data[part_name] = _etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone=True
            )

    # ── Force TOC recalculation on open ─────────────────────────────────────
    if update_toc and "word/settings.xml" in zip_data:
        try:
            s_root = _etree.fromstring(zip_data["word/settings.xml"])
            uf = s_root.find(f"{WQN}updateFields")
            if uf is None:
                uf = _etree.SubElement(s_root, f"{WQN}updateFields")
            uf.set(f"{WQN}val", "1")
            zip_data["word/settings.xml"] = _etree.tostring(
                s_root, xml_declaration=True, encoding="UTF-8", standalone=True
            )
        except Exception:
            pass

    # ── Write output ZIP ─────────────────────────────────────────────────────
    try:
        with _zipfile.ZipFile(str(out_path), "w", _zipfile.ZIP_DEFLATED) as zout:
            for name, data in zip_data.items():
                zout.writestr(name, data)
    except Exception as e:
        return f"Error guardando documento: {e}"

    size = out_path.stat().st_size
    toc_note = "marcado para actualizar al abrir" if update_toc else "sin cambios"
    return (
        f"✅ Plantilla corporativa rellenada: {out_path.name}\n"
        f"   Origen: {template_path.name}\n"
        f"   Reemplazos: {total}  |  TOC: {toc_note}\n"
        f"   Estilos, imágenes y layout originales preservados al 100%\n"
        f"   Tamaño: {size:,} bytes"
    )


def _tool_doc_list_templates(args: dict) -> str:
    """List available document templates: project dir, workspace, and configured templates_dir."""
    cfg  = _load_config()
    cwd  = Path.cwd()
    dirs_to_scan: list[Path] = []
    # 1. Explicit arg
    if args.get("directory"):
        dirs_to_scan.append(Path(args["directory"]).expanduser())
    # 2. Project dir (cwd/templates, cwd/plantillas)
    for local in ("templates", "plantillas"):
        p = cwd / local
        if p.exists() and p not in dirs_to_scan:
            dirs_to_scan.append(p)
    # 3. Configured templates_dir (may already overlap with above)
    conf_dir = Path(cfg.get("templates_dir", str(Path.home() / "Documents" / "templates"))).expanduser()
    if conf_dir not in dirs_to_scan:
        dirs_to_scan.append(conf_dir)

    patterns = ("*.docx", "*.xlsx", "*.md", "*.txt", "*.odt")
    seen: set[Path] = set()
    all_files: list[tuple[Path, Path]] = []  # (dir, file)
    for d in dirs_to_scan:
        if not d.exists():
            continue
        for pattern in patterns:
            for f in d.glob(pattern):
                if f not in seen:
                    seen.add(f)
                    all_files.append((d, f))
    all_files.sort(key=lambda x: x[1].stat().st_mtime, reverse=True)

    if not all_files:
        dirs_str = ", ".join(str(d) for d in dirs_to_scan)
        return (
            f"Sin plantillas en: {dirs_str}\n"
            f"Coloca ficheros .docx, .xlsx o .md en {cwd / 'templates'} o configura 'templates_dir'."
        )
    lines = [f"📁 Plantillas disponibles ({len(all_files)}):"]
    last_dir = None
    for d, f in all_files:
        if d != last_dir:
            label = "workspace" if d.parent == cwd or d == cwd else str(d)
            lines.append(f"\n  📂 {label}/")
            last_dir = d
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
        lines.append(f"     {mtime}  {f.stat().st_size:>8,} B  {f.name}")
    return "\n".join(lines)


def _apply_o365_styles_to_new_doc(doc) -> None:
    """Apply proper O365 (Word 2016+) default styles to a freshly created document.

    Sets Calibri 11pt body, Calibri Light headings with correct Office accent colors,
    proper paragraph spacing, and line spacing matching a real Word document.
    Only applies to styles that already exist in the document style gallery.
    """
    from docx.shared import Pt, RGBColor, Cm
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    # Office theme accent colors (matches Word default Office theme)
    _H_COLORS = {
        1: RGBColor(0x2F, 0x54, 0x96),  # Heading 1 — dark blue
        2: RGBColor(0x2E, 0x74, 0xB5),  # Heading 2 — medium blue
        3: RGBColor(0x1F, 0x4E, 0x79),  # Heading 3 — darker blue
        4: RGBColor(0x2E, 0x74, 0xB5),  # Heading 4
        5: RGBColor(0x40, 0x40, 0x40),  # Heading 5
        6: RGBColor(0x59, 0x59, 0x59),  # Heading 6
    }
    _H_SIZES = {1: 16, 2: 13, 3: 12, 4: 11, 5: 11, 6: 10}
    _H_SPACE_BEFORE = {1: 24, 2: 18, 3: 14, 4: 12, 5: 10, 6: 10}  # pt

    style_names = {s.name for s in doc.styles}

    def _set_spacing(style, before_pt: float, after_pt: float, line_rule=None):
        pPr = style.element.get_or_add_pPr()
        sp = pPr.find(qn("w:spacing"))
        if sp is None:
            sp = OxmlElement("w:spacing")
            pPr.append(sp)
        sp.set(qn("w:before"), str(int(before_pt * 20)))
        sp.set(qn("w:after"),  str(int(after_pt * 20)))
        if line_rule:
            sp.set(qn("w:lineRule"), line_rule[0])
            sp.set(qn("w:line"),     str(line_rule[1]))

    # Normal — Calibri 11pt, 0pt before, 8pt after, 1.15 line spacing
    if "Normal" in style_names:
        s = doc.styles["Normal"]
        s.font.name = "Calibri"
        s.font.size = Pt(11)
        s.font.color.rgb = RGBColor(0x26, 0x26, 0x26)
        try:
            _set_spacing(s, 0, 8, ("auto", 276))  # 276/240 ≈ 1.15
        except Exception:
            pass

    # Body Text — same as Normal
    if "Body Text" in style_names:
        s = doc.styles["Body Text"]
        s.font.name = "Calibri"
        s.font.size = Pt(11)
        try:
            _set_spacing(s, 0, 8, ("auto", 276))
        except Exception:
            pass

    # Headings 1-6
    for lvl in range(1, 7):
        name = f"Heading {lvl}"
        if name not in style_names:
            continue
        s = doc.styles[name]
        s.font.name = "Calibri Light"
        s.font.size = Pt(_H_SIZES[lvl])
        s.font.color.rgb = _H_COLORS[lvl]
        s.font.bold = False  # Calibri Light headings are not bold in Office default
        try:
            _set_spacing(s, _H_SPACE_BEFORE[lvl], 4)
        except Exception:
            pass

    # List Bullet / List Number
    for nm in ("List Bullet", "List Bullet 2", "List Number", "List Number 2"):
        if nm in style_names:
            s = doc.styles[nm]
            s.font.name = "Calibri"
            s.font.size = Pt(11)
            try:
                _set_spacing(s, 0, 4)
            except Exception:
                pass

    # Quote / Block Text
    for nm in ("Quote", "Intense Quote", "Block Text"):
        if nm in style_names:
            s = doc.styles[nm]
            s.font.name = "Calibri"
            s.font.size = Pt(11)
            s.font.italic = True
            s.font.color.rgb = RGBColor(0x40, 0x40, 0x40)

    # Table styles
    for nm in ("Table Grid", "Normal Table"):
        if nm in style_names:
            s = doc.styles[nm]
            if hasattr(s, "font"):
                s.font.name = "Calibri"
                s.font.size = Pt(10)

    # List Paragraph — Calibri 11pt with left indent, used for checklists/nested lists
    if "List Paragraph" in style_names:
        s = doc.styles["List Paragraph"]
        s.font.name = "Calibri"
        s.font.size = Pt(11)
        try:
            _set_spacing(s, 0, 4)
        except Exception:
            pass

    # Caption — Calibri 9pt italic grey (for figure/table captions)
    if "Caption" in style_names:
        s = doc.styles["Caption"]
        s.font.name = "Calibri"
        s.font.size = Pt(9)
        s.font.italic = True
        s.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
        try:
            _set_spacing(s, 4, 8)
        except Exception:
            pass

    # Strong — bold Calibri 11pt
    if "Strong" in style_names:
        s = doc.styles["Strong"]
        s.font.name = "Calibri"
        s.font.size = Pt(11)
        s.font.bold = True

    # Emphasis — italic Calibri 11pt
    if "Emphasis" in style_names:
        s = doc.styles["Emphasis"]
        s.font.name = "Calibri"
        s.font.size = Pt(11)
        s.font.italic = True

    # Intense Emphasis — bold italic Calibri with accent color
    if "Intense Emphasis" in style_names:
        s = doc.styles["Intense Emphasis"]
        s.font.name = "Calibri"
        s.font.size = Pt(11)
        s.font.bold = True
        s.font.italic = True
        s.font.color.rgb = RGBColor(0x2F, 0x54, 0x96)

    # Subtle Reference / Intense Reference — Calibri small-caps
    for nm in ("Subtle Reference", "Intense Reference"):
        if nm in style_names:
            s = doc.styles[nm]
            s.font.name = "Calibri"
            s.font.size = Pt(10)

    # No Spacing — Calibri 11pt zero spacing (used for code blocks)
    if "No Spacing" in style_names:
        s = doc.styles["No Spacing"]
        s.font.name = "Calibri"
        s.font.size = Pt(11)
        try:
            _set_spacing(s, 0, 0)
        except Exception:
            pass

    # Set default page margins (A4: 2.5cm top/bottom, 3cm left, 2.5cm right)
    try:
        from docx.shared import Cm
        sect = doc.sections[0]
        sect.top_margin    = Cm(2.5)
        sect.bottom_margin = Cm(2.5)
        sect.left_margin   = Cm(3.0)
        sect.right_margin  = Cm(2.5)
        sect.page_width    = Cm(21.0)
        sect.page_height   = Cm(29.7)
    except Exception:
        pass


def _md_fill_para_inline(para, text: str) -> None:
    """Fill a python-docx paragraph with rich inline formatting.

    Handles: ***bold+italic***, **bold**, *italic*, _italic_, __bold__,
    `code`, ~~strikethrough~~, [link](url), <u>underline</u>,
    ==highlight==, ^superscript^, ~subscript~,
    <sup>…</sup>, <sub>…</sub>, <s>…</s>, <b>…</b>, <i>…</i>,
    <mark color="#RRGGBB">…</mark>.
    """
    import re as _re
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn as _qn
    from docx.oxml import OxmlElement as _OE

    _PAT = _re.compile(
        r'(\*\*\*(?P<bi>.+?)\*\*\*'
        r'|\*\*(?P<b>.+?)\*\*'
        r'|__(?P<b2>.+?)__'
        r'|\*(?P<i>.+?)\*'
        r'|_(?P<i2>.+?)_'
        r'|`(?P<code>.+?)`'
        r'|~~(?P<s>.+?)~~'
        r'|==(?P<hi>.+?)=='
        r'|\^(?P<sup>.+?)\^'
        r'|(?<!~)~(?!~)(?P<sub>.+?)(?<!~)~(?!~)'
        r'|<u>(?P<u>.+?)</u>'
        r'|<s>(?P<hs>.+?)</s>'
        r'|<b>(?P<hb>.+?)</b>'
        r'|<i>(?P<hit>.+?)</i>'
        r'|<sup>(?P<hsup>.+?)</sup>'
        r'|<sub>(?P<hsub>.+?)</sub>'
        r'|<mark(?:\s+color=["\'](?P<mc>[0-9A-Fa-f#]{6,7})["\'])?>(?P<mkt>.+?)</mark>'
        r'|\[(?P<lt>[^\]]+)\]\((?P<lu>[^\)]+)\)'
        r')',
        _re.DOTALL,
    )

    def _apply_highlight(run, hex_color: str):
        """Apply paragraph shading to a run via rPr/highlight or w:shd."""
        try:
            rPr = run._r.get_or_add_rPr()
            shd = _OE("w:shd")
            shd.set(_qn("w:val"), "clear")
            shd.set(_qn("w:color"), "auto")
            shd.set(_qn("w:fill"), hex_color.lstrip("#").upper())
            rPr.append(shd)
        except Exception:
            pass

    pos = 0
    for m in _PAT.finditer(text):
        if m.start() > pos:
            para.add_run(text[pos:m.start()])
        pos = m.end()

        if m.group("bi"):
            r = para.add_run(m.group("bi")); r.bold = True; r.italic = True
        elif m.group("b") or m.group("b2"):
            r = para.add_run(m.group("b") or m.group("b2")); r.bold = True
        elif m.group("hb"):
            r = para.add_run(m.group("hb")); r.bold = True
        elif m.group("i") or m.group("i2"):
            r = para.add_run(m.group("i") or m.group("i2")); r.italic = True
        elif m.group("hit"):
            r = para.add_run(m.group("hit")); r.italic = True
        elif m.group("code"):
            r = para.add_run(m.group("code"))
            r.font.name = "Consolas"
            try:
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(0xC7, 0x25, 0x2B)
                _apply_highlight(r, "F2F2F2")
            except Exception:
                pass
        elif m.group("s") or m.group("hs"):
            r = para.add_run(m.group("s") or m.group("hs")); r.font.strike = True
        elif m.group("hi"):
            r = para.add_run(m.group("hi"))
            _apply_highlight(r, "FFFF00")
            r.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
        elif m.group("mkt"):
            r = para.add_run(m.group("mkt"))
            mc = (m.group("mc") or "FFFF00").lstrip("#")
            _apply_highlight(r, mc)
        elif m.group("sup") or m.group("hsup"):
            r = para.add_run(m.group("sup") or m.group("hsup"))
            try:
                rPr = r._r.get_or_add_rPr()
                vertAlign = _OE("w:vertAlign")
                vertAlign.set(_qn("w:val"), "superscript")
                rPr.append(vertAlign)
            except Exception:
                pass
        elif m.group("sub") or m.group("hsub"):
            r = para.add_run(m.group("sub") or m.group("hsub"))
            try:
                rPr = r._r.get_or_add_rPr()
                vertAlign = _OE("w:vertAlign")
                vertAlign.set(_qn("w:val"), "subscript")
                rPr.append(vertAlign)
            except Exception:
                pass
        elif m.group("u"):
            r = para.add_run(m.group("u")); r.underline = True
        elif m.group("lt"):
            r = para.add_run(m.group("lt"))
            r.font.color.rgb = RGBColor(0x05, 0x63, 0xC1)
            r.underline = True
            if m.group("lu") and m.group("lt") != m.group("lu"):
                para.add_run(f" ({m.group('lu')})")

    if pos < len(text):
        para.add_run(text[pos:])


def _render_native_paragraphs(doc, text: str) -> int:
    """Renderiza texto como párrafos nativos de Word (con énfasis inline **/*/`).

    No es un conversor markdown: separa por líneas en blanco y crea un párrafo
    nativo por bloque, aplicando solo el formato inline de runs (negrita/cursiva/
    código) vía _md_fill_para_inline. Pensado para volcar texto plano en O365.
    """
    n = 0
    for para_text in str(text or "").split("\n\n"):
        para_text = para_text.strip()
        if not para_text:
            continue
        p = doc.add_paragraph()
        _md_fill_para_inline(p, para_text.replace("\n", " "))
        n += 1
    return n


def _tool_doc_create(args: dict) -> str:
    """Create a professional Word (.docx) or Excel (.xlsx) or PowerPoint (.pptx) document
    from scratch with O365-quality formatting.

    Usa SIEMPRE content_blocks (contenido O365 NATIVO). El parámetro `markdown` solo
    vuelca texto plano como párrafos nativos (con énfasis inline **/*/`) — NO genera
    estructura (headings, listas, tablas): para eso usa content_blocks.

    For .xlsx: creates a formatted workbook with sheets and data.
    For .pptx: creates a presentation with slides.

    content_blocks types (docx):
      {"type": "title",         "text": "...", "subtitle": "..."}
      {"type": "heading",       "level": 1-6, "text": "..."}
      {"type": "paragraph",     "text": "...", "style": "Normal|Body Text|Quote|..."}
      {"type": "bullet_list",   "items": ["item1", {"text":"item2","items":["sub"]}], "indent": 0}
      {"type": "numbered_list", "items": ["paso1", "paso2"]}
      {"type": "table",         "headers": ["C1","C2"], "rows": [["a","b"]],
                                "style": "Light Grid Accent 1",
                                "merge_cells": [{"start_row":0,"start_col":0,"end_row":0,"end_col":1}]}
      {"type": "chart",         "chart_type": "bar|line|pie|doughnut|area|scatter",
                                "title": "Mi Gráfica", "width_inches": 5.5, "height_inches": 3.5,
                                "data": {"categories": [...], "series": [{"label":"...", "values":[...]}]}}
      {"type": "image",         "path": "/ruta/img.png", "width_inches": 5.0,
                                "caption": "Fig 1", "align": "center|left|right"}
      {"type": "code_block",    "code": "...", "language": "python"}
      {"type": "markdown",      "text": "Texto plano con **negrita**/*cursiva* inline (NO parsea # ni listas)"}
      {"type": "checklist",     "items": [{"text":"Tarea 1","checked":true}, "Tarea 2"]}
      {"type": "callout",       "callout_type": "info|tip|note|warning|error|success",
                                "title": "Título opcional", "text": "Mensaje..."}
      {"type": "highlight",     "text": "Texto resaltado", "color": "FFFF00",
                                "text_color": "000000"}
      {"type": "pagebreak"}
      {"type": "horizontal_rule"}
      {"type": "toc",           "title": "Índice"}
      {"type": "signature_block", "roles": ["Autor", "Revisor", "Aprobador"]}

    slides (pptx): lista de diapositivas con blocks avanzados:
      {"title": "...", "content": "texto\\nbullet", "layout": "bullet|blank|two_col",
       "notes": "...", "blocks": [
         {"type": "chart", "chart_type": "column", "title": "...", "x":1, "y":2, "width":8, "height":4.5,
          "data": {"categories":[...], "series":[{"label":"...", "values":[...]}]}},
         {"type": "table", "headers":[...], "rows":[[...]], "x":0.5, "y":1.5, "width":12},
         {"type": "image", "path":"...", "x":1, "y":2, "width":6},
         {"type": "text",  "text":"...", "x":1, "y":6, "width":10, "size":14}
       ]}

    sheets (xlsx): lista de hojas con charts y formatos condicionales:
      {"name": "Ventas", "headers":[...], "rows":[[...]], "title":"...",
       "charts": [{"type":"bar|column|stacked_bar|stacked_column|100_stacked_column|line|stacked_line|area|stacked_area|pie|doughnut|scatter",
                   "title":"...","data_range":"A1:C6","position":"E2","width":15,"height":10}],
       "conditional_formats": [
         {"range":"B2:B20","format_type":"color_scale","start_color":"FFAAAA","mid_color":"FFFF88","end_color":"AAFFAA"},
         {"range":"C2:C20","format_type":"data_bar","color":"638EC6"},
         {"range":"D2:D20","format_type":"cell_is","operator":"greaterThan","formula":"100","fill_color":"AAFFAA"}
       ]}
    Nota: valores de celda que empiezan con '=' se escriben como fórmulas Excel (ej: "=SUM(B2:B10)").

    theme: office (default) | modern | professional | minimal | corporate
    """
    # Coerce args that LLMs sometimes pass as JSON strings instead of native types
    def _coerce_json(val, default):
        if isinstance(val, str) and val.strip():
            try:
                import json as _json
                return _json.loads(val)
            except Exception:
                return val
        return val if val else default

    def _norm_blocks(blocks):
        """Normalize a content_blocks list: wrap plain strings as paragraph blocks
        and drop entries that are neither str nor dict (avoids 'str'.get errors)."""
        if isinstance(blocks, dict):
            blocks = [blocks]
        out = []
        for b in (blocks or []):
            if isinstance(b, str):
                out.append({"type": "paragraph", "text": b})
            elif isinstance(b, dict):
                out.append(b)
            # else: silently skip non-str/non-dict entries
        return out

    path           = Path(args.get("path", "")).expanduser()
    theme          = args.get("theme", "office")
    fmt            = args.get("format", "").lower() or (path.suffix.lstrip(".").lower() if path.suffix else "docx")
    markdown       = args.get("markdown", "")
    content_blocks = _norm_blocks(_coerce_json(args.get("content_blocks", []), []))
    title          = args.get("title", "")
    subtitle       = args.get("subtitle", "")
    metadata       = _coerce_json(args.get("metadata", {}), {})  # author, subject, company, keywords
    if not isinstance(metadata, dict):
        metadata = {}
    template_path  = args.get("template_path", args.get("reference_doc", ""))

    if not path:
        return "Parámetro requerido: path"

    # Normalize extension
    if not path.suffix:
        path = path.with_suffix(f".{fmt or 'docx'}")
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()

    # ── Word .docx ──────────────────────────────────────────────────────────
    if ext in (".docx", ".dotx"):
        try:
            from docx import Document
            from docx.shared import Pt, RGBColor, Inches
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement
        except ImportError:
            return "python-docx no disponible. Instala con: pip install python-docx"

        _THEME_COLORS = {
            "office":       {"h1": (0x2F,0x54,0x96), "h2": (0x2E,0x74,0xB5), "accent": (0x70,0xAD,0x47)},
            "modern":       {"h1": (0x1F,0x4E,0x79), "h2": (0x2F,0x54,0x96), "accent": (0xED,0x7D,0x31)},
            "professional": {"h1": (0x17,0x37,0x5E), "h2": (0x26,0x5F,0x8B), "accent": (0x70,0xAD,0x47)},
            "minimal":      {"h1": (0x20,0x20,0x20), "h2": (0x40,0x40,0x40), "accent": (0x40,0x40,0x40)},
            "corporate":    {"h1": (0x00,0x3A,0x70), "h2": (0x00,0x55,0x99), "accent": (0xFF,0xC0,0x00)},
        }
        tc = _THEME_COLORS.get(theme, _THEME_COLORS["office"])

        # Load template or create fresh document
        _used_template = False
        if template_path:
            tpl = Path(template_path).expanduser()
            if tpl.exists():
                doc = Document(str(tpl))
                _used_template = True
                # Clear body content for .dotx templates or when explicitly requested
                if tpl.suffix.lower() in (".dotx", ".dot") or args.get("clear_template_body", False):
                    body = doc.element.body
                    for _p in list(body.findall(qn("w:p")))[:-1]:
                        body.remove(_p)
                    for _t in list(body.findall(qn("w:tbl"))):
                        body.remove(_t)
                # Use template heading colors for theme overrides
                try:
                    _h1 = doc.styles.get("Heading 1") if hasattr(doc.styles, 'get') else None
                    if _h1 and _h1.font.color.rgb:
                        r, g, b = _h1.font.color.rgb.red, _h1.font.color.rgb.green, _h1.font.color.rgb.blue
                        tc["h1"] = (r, g, b)
                except Exception:
                    pass
            else:
                doc = Document()
                _apply_o365_styles_to_new_doc(doc)
        else:
            doc = Document()
            _apply_o365_styles_to_new_doc(doc)

        # Override heading colors for chosen theme only when NOT using a corporate template
        style_names = {s.name for s in doc.styles}
        if not _used_template:
            for lvl, key in ((1,"h1"),(2,"h2"),(3,"h2")):
                nm = f"Heading {lvl}"
                if nm in style_names:
                    try:
                        doc.styles[nm].font.color.rgb = RGBColor(*tc[key])
                    except Exception:
                        pass

        # Set document core properties (metadata)
        try:
            cp = doc.core_properties
            if metadata.get("author"):   cp.author   = metadata["author"]
            if metadata.get("subject"):  cp.subject  = metadata["subject"]
            if metadata.get("company"):  cp.company  = metadata["company"]
            if metadata.get("keywords"): cp.keywords = metadata["keywords"]
            if title: cp.title = title
        except Exception:
            pass

        def _add_cover_title(title_text: str, sub: str = ""):
            p = doc.add_paragraph()
            try:
                p.style = doc.styles["Title"] if "Title" in style_names else doc.styles["Heading 1"]
            except Exception:
                pass
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(title_text)
            run.font.name = "Calibri Light"
            run.font.size = Pt(28)
            run.font.color.rgb = RGBColor(*tc["h1"])
            if sub:
                sp = doc.add_paragraph()
                sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                sr = sp.add_run(sub)
                sr.font.name = "Calibri"
                sr.font.size = Pt(14)
                sr.font.color.rgb = RGBColor(0x60, 0x60, 0x60)

        def _add_toc(toc_title: str = "Índice de contenido"):
            p = doc.add_paragraph()
            try:
                p.style = doc.styles[("Heading 1" if "Heading 1" in style_names else "Normal")]
            except Exception:
                pass
            p.add_run(toc_title)
            # TOC field instruction (Word renders it on open/F9)
            try:
                para = doc.add_paragraph()
                fldChar1 = OxmlElement("w:fldChar")
                fldChar1.set(qn("w:fldCharType"), "begin")
                instrText = OxmlElement("w:instrText")
                instrText.set(qn("xml:space"), "preserve")
                instrText.text = ' TOC \\o "1-3" \\h \\z \\u '
                fldChar2 = OxmlElement("w:fldChar")
                fldChar2.set(qn("w:fldCharType"), "separate")
                fldChar3 = OxmlElement("w:fldChar")
                fldChar3.set(qn("w:fldCharType"), "end")
                r = para._p.add_r()
                r.append(fldChar1)
                r.append(instrText)
                r.append(fldChar2)
                r.append(fldChar3)
                rp = para.add_run("[Actualiza con F9 en Word]")
                rp.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
                rp.font.size = Pt(10)
            except Exception:
                doc.add_paragraph("[Tabla de contenido — Actualiza con Ctrl+A, F9 en Word]")

        def _add_signature_block(roles: list):
            doc.add_paragraph()
            n = len(roles) or 1
            tbl = doc.add_table(rows=3, cols=n)
            try:
                tbl.style = doc.styles["Table Grid"] if "Table Grid" in style_names else None
            except Exception:
                pass
            for c_i, role in enumerate(roles):
                # Row 0: role label
                tbl.rows[0].cells[c_i].text = role
                for run in tbl.rows[0].cells[c_i].paragraphs[0].runs:
                    run.bold = True
                # Row 1: signature line — OOXML bottom border (no ASCII underscores)
                p = tbl.rows[1].cells[c_i].paragraphs[0]
                try:
                    pPr = p._p.get_or_add_pPr()
                    pBdr = OxmlElement("w:pBdr")
                    bot = OxmlElement("w:bottom")
                    bot.set(qn("w:val"), "single")
                    bot.set(qn("w:sz"), "8")
                    bot.set(qn("w:space"), "1")
                    bot.set(qn("w:color"), "CCCCCC")
                    pBdr.append(bot)
                    pPr.append(pBdr)
                    spc = OxmlElement("w:spacing")
                    spc.set(qn("w:before"), "240")
                    pPr.append(spc)
                except Exception:
                    p.add_run("_" * 30).font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
                # Row 2: date line — also OOXML bottom border
                dp = tbl.rows[2].cells[c_i].paragraphs[0]
                dp.add_run("Fecha:")
                try:
                    dpPr = dp._p.get_or_add_pPr()
                    dpBdr = OxmlElement("w:pBdr")
                    dbot = OxmlElement("w:bottom")
                    dbot.set(qn("w:val"), "single")
                    dbot.set(qn("w:sz"), "4")
                    dbot.set(qn("w:space"), "1")
                    dbot.set(qn("w:color"), "CCCCCC")
                    dpBdr.append(dbot)
                    dpPr.append(dpBdr)
                    dspc = OxmlElement("w:spacing")
                    dspc.set(qn("w:before"), "120")
                    dpPr.append(dspc)
                except Exception:
                    dp.add_run(" ___________")

        def _shade_cell_docx(cell, hex_color: str):
            """Apply background shading to a Word table cell via OOXML."""
            try:
                tc_el = cell._tc
                tcPr = tc_el.get_or_add_tcPr()
                # Remove existing shd to avoid duplicates
                for old in tcPr.findall(qn("w:shd")):
                    tcPr.remove(old)
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), hex_color)
                tcPr.append(shd)
            except Exception:
                pass

        def _add_cell_border(cell, border_style: str = "single", sz: str = "4", color: str = "BFBFBF"):
            """Add thin bottom border to a table cell."""
            try:
                tc_el = cell._tc
                tcPr = tc_el.get_or_add_tcPr()
                tcBdr = OxmlElement("w:tcBdr")
                for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                    b = OxmlElement(f"w:{side}")
                    b.set(qn("w:val"), border_style)
                    b.set(qn("w:sz"), sz)
                    b.set(qn("w:space"), "0")
                    b.set(qn("w:color"), color)
                    tcBdr.append(b)
                tcPr.append(tcBdr)
            except Exception:
                pass

        # Map theme to Word built-in table styles (with fallback chain)
        _WORD_TABLE_STYLES = [
            "Light Grid Accent 1",
            "Light Shading Accent 1",
            "Table Grid Light",
            "Table Grid",
            "Normal Table",
        ]

        def _add_table_block(block: dict):
            headers   = block.get("headers", [])
            rows_data = block.get("rows", [])
            tbl_style = block.get("style", "")
            merge_cells = block.get("merge_cells", [])  # [{"range": "A1:B1"}, ...]
            if not headers:
                return
            n_cols = len(headers)
            n_rows = len(rows_data)
            tbl = doc.add_table(rows=1 + n_rows, cols=n_cols)

            # Apply style: explicit > built-in chain > manual
            applied_builtin = False
            style_to_try = [tbl_style] + _WORD_TABLE_STYLES if tbl_style else _WORD_TABLE_STYLES
            for sn in style_to_try:
                if sn and sn in style_names:
                    try:
                        tbl.style = doc.styles[sn]
                        applied_builtin = True
                        break
                    except Exception:
                        continue

            header_hex = "%02X%02X%02X" % tc["h1"]
            alt_hex    = "EEF3FB"

            # Header row
            for c_i, h in enumerate(headers):
                cell = tbl.rows[0].cells[c_i]
                cell.text = ""
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(4)
                p.paragraph_format.space_after  = Pt(4)
                run = p.add_run(str(h))
                run.bold = True
                run.font.name = "Calibri"
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                _shade_cell_docx(cell, header_hex)

            # Data rows
            for r_i, row_data in enumerate(rows_data):
                for c_i, val in enumerate(row_data[:n_cols]):
                    cell = tbl.rows[r_i + 1].cells[c_i]
                    cell.text = ""
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_before = Pt(3)
                    p.paragraph_format.space_after  = Pt(3)
                    _md_fill_para_inline(p, str(val))
                    for run in p.runs:
                        run.font.name = "Calibri"
                        run.font.size = Pt(10)
                    if not applied_builtin and r_i % 2 == 0:
                        _shade_cell_docx(cell, alt_hex)
                    elif not applied_builtin:
                        _add_cell_border(cell)

            # Handle cell merges (e.g. merge_cells=[{"start":"A1","end":"B1"}])
            for mc in merge_cells:
                try:
                    sr, sc_ = mc.get("start_row", 0), mc.get("start_col", 0)
                    er, ec  = mc.get("end_row", 0),   mc.get("end_col", 0)
                    if sr < len(tbl.rows) and sc_ < n_cols:
                        a = tbl.rows[sr].cells[sc_]
                        b = tbl.rows[er].cells[ec]
                        a.merge(b)
                except Exception:
                    pass

            try:
                tbl.autofit = True
            except Exception:
                pass
            doc.add_paragraph()  # spacing after table

        n_blocks = 0

        # Add title block first if top-level title/subtitle args given
        if title and not content_blocks:
            _add_cover_title(title, subtitle)
            doc.add_paragraph()
            n_blocks += 1

        # Process content_blocks
        for block in content_blocks:
            btype = block.get("type", "paragraph")

            if btype == "title":
                _add_cover_title(block.get("text", title), block.get("subtitle", ""))
                doc.add_paragraph()

            elif btype == "heading":
                lvl = max(1, min(6, int(block.get("level", 1))))
                try:
                    p = doc.add_paragraph()
                    p.style = doc.styles[f"Heading {lvl}" if f"Heading {lvl}" in style_names else "Normal"]
                    p.add_run(block.get("text", ""))
                except Exception:
                    doc.add_paragraph(block.get("text", ""))

            elif btype == "paragraph":
                style_nm = block.get("style", "Normal")
                p = doc.add_paragraph()
                try:
                    p.style = doc.styles[style_nm if style_nm in style_names else "Normal"]
                except Exception:
                    pass
                _md_fill_para_inline(p, block.get("text", ""))

            elif btype in ("bullet_list", "numbered_list"):
                items      = block.get("items", [])
                is_numbered = btype == "numbered_list" or block.get("numbered", False)
                indent_lvl  = int(block.get("indent", 0))
                style_key   = "List Number" if is_numbered else "List Bullet"
                style_key2  = f"List Number {indent_lvl+1}" if is_numbered else f"List Bullet {indent_lvl+1}"
                for item in items:
                    p = doc.add_paragraph()
                    # Try style chain: exact level > base level > XML fallback
                    applied_list_style = False
                    for sn in (style_key2, style_key):
                        if sn in style_names:
                            try:
                                p.style = doc.styles[sn]
                                applied_list_style = True
                                break
                            except Exception:
                                continue
                    if not applied_list_style:
                        # XML fallback: manual bullet/numbering via paragraph properties
                        try:
                            pPr = p._p.get_or_add_pPr()
                            ind = OxmlElement("w:ind")
                            ind.set(qn("w:left"), str(360 * (indent_lvl + 1)))
                            ind.set(qn("w:hanging"), "360")
                            pPr.append(ind)
                        except Exception:
                            pass
                    sub_items = item if isinstance(item, dict) else {}
                    item_text = sub_items.get("text", str(item)) if isinstance(item, dict) else str(item)
                    _md_fill_para_inline(p, item_text)
                    # Sub-items (nested list)
                    if isinstance(item, dict) and item.get("items"):
                        for sub in item["items"]:
                            sp = doc.add_paragraph()
                            sub_style = (f"List Number {min(indent_lvl+2,5)}" if is_numbered
                                         else f"List Bullet {min(indent_lvl+2,5)}")
                            for sn in (sub_style, style_key):
                                if sn in style_names:
                                    try:
                                        sp.style = doc.styles[sn]
                                        break
                                    except Exception:
                                        continue
                            _md_fill_para_inline(sp, str(sub))

            elif btype == "table":
                _add_table_block(block)

            elif btype == "image":
                img_path = Path(block.get("path", "")).expanduser()
                if img_path.exists():
                    try:
                        w = float(block.get("width_inches", 5.5))
                        align_str = block.get("align", "center").lower()
                        align_map = {
                            "center": WD_ALIGN_PARAGRAPH.CENTER,
                            "left":   WD_ALIGN_PARAGRAPH.LEFT,
                            "right":  WD_ALIGN_PARAGRAPH.RIGHT,
                        }
                        img_align = align_map.get(align_str, WD_ALIGN_PARAGRAPH.CENTER)
                        # Validate supported formats
                        _SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".emf", ".wmf"}
                        if img_path.suffix.lower() not in _SUPPORTED_IMG:
                            doc.add_paragraph(f"[Formato de imagen no soportado: {img_path.suffix} — usa PNG/JPEG/GIF/BMP]")
                        else:
                            # Proportional sizing via Pillow if available
                            h_arg = None
                            try:
                                from PIL import Image as _PIL_Image
                                with _PIL_Image.open(img_path) as im:
                                    if im.width > 0 and im.height > 0:
                                        ratio = im.height / im.width
                                        h_calc = w * ratio
                                        # Cap at page height (A4 usable ~9.7 in)
                                        if h_calc > 9.5:
                                            h_calc = 9.5
                                            w = h_calc / ratio
                                        h_arg = Inches(h_calc)
                            except Exception:
                                pass
                            if h_arg:
                                doc.add_picture(str(img_path), width=Inches(w), height=h_arg)
                            else:
                                doc.add_picture(str(img_path), width=Inches(w))
                            doc.paragraphs[-1].alignment = img_align
                            cap = block.get("caption", "")
                            if cap:
                                cp = doc.add_paragraph(cap)
                                cp.alignment = img_align
                                try:
                                    cp.style = doc.styles["Caption" if "Caption" in style_names else "Normal"]
                                except Exception:
                                    for r in cp.runs:
                                        r.font.size = Pt(9)
                                        r.italic = True
                    except Exception as img_err:
                        doc.add_paragraph(f"[Imagen no cargada: {img_path.name} — {img_err}]")
                else:
                    doc.add_paragraph(f"[Imagen no encontrada: {block.get('path', '')}]")

            elif btype == "chart":
                # Native OOXML chart block embedded in Word document
                chart_data = block.get("data", {})
                c_type     = block.get("chart_type", "bar")
                c_title    = block.get("title", "")
                c_cats     = chart_data.get("categories", [])
                c_series   = chart_data.get("series", chart_data.get("series_list", []))
                if not c_series:
                    vals   = chart_data.get("values", [])
                    labels = chart_data.get("labels", c_cats)
                    if vals:
                        c_series = [{"label": c_title or "Serie 1", "values": vals}]
                        if not c_cats:
                            c_cats = labels
                if c_series:
                    w_in = float(block.get("width_inches", 5.5))
                    h_in = float(block.get("height_inches", 3.5))
                    cxml = _build_word_chart_xml(c_type, c_cats, c_series, c_title)
                    ok   = _embed_word_chart_native(doc, cxml, int(w_in*914400), int(h_in*914400))
                    if not ok:
                        doc.add_paragraph(f"[Gráfica '{c_type}' — OOXML no disponible, usa insert_chart]")
                    elif c_title:
                        cap = doc.add_paragraph()
                        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        r = cap.add_run(c_title)
                        r.font.size = Pt(9)
                        r.font.italic = True
                        r.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
                else:
                    doc.add_paragraph(f"[Gráfica sin datos: especifica data.series o data.values]")

            elif btype == "markdown":
                _render_native_paragraphs(doc, block.get("text", ""))

            elif btype == "code_block":
                code = block.get("code", block.get("text", ""))
                for code_line in (code.splitlines() or [""]):
                    p = doc.add_paragraph()
                    try:
                        p.style = doc.styles["No Spacing" if "No Spacing" in style_names else "Normal"]
                    except Exception:
                        pass
                    try:
                        pPr = p._p.get_or_add_pPr()
                        # Grey background
                        shd = OxmlElement("w:shd")
                        shd.set(qn("w:val"), "clear")
                        shd.set(qn("w:color"), "auto")
                        shd.set(qn("w:fill"), "F2F2F2")
                        pPr.append(shd)
                        # Left accent bar using theme h1 color
                        accent = "%02X%02X%02X" % tc["h1"]
                        pBdr = OxmlElement("w:pBdr")
                        left = OxmlElement("w:left")
                        left.set(qn("w:val"), "single")
                        left.set(qn("w:sz"), "16")
                        left.set(qn("w:space"), "8")
                        left.set(qn("w:color"), accent)
                        pBdr.append(left)
                        pPr.append(pBdr)
                        # Indent
                        ind = OxmlElement("w:ind")
                        ind.set(qn("w:left"), "360")
                        pPr.append(ind)
                    except Exception:
                        pass
                    run = p.add_run(code_line)
                    run.font.name = "Consolas"
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(0x24, 0x29, 0x2E)

            elif btype == "pagebreak":
                doc.add_page_break()

            elif btype == "toc":
                _add_toc(block.get("title", "Índice de contenido"))

            elif btype == "signature_block":
                _add_signature_block(block.get("roles", ["Autor", "Revisor", "Aprobador"]))

            elif btype == "horizontal_rule":
                sep = doc.add_paragraph()
                try:
                    pPr = sep._p.get_or_add_pPr()
                    pBdr = OxmlElement("w:pBdr")
                    bot = OxmlElement("w:bottom")
                    bot.set(qn("w:val"), "single")
                    bot.set(qn("w:sz"), "6")
                    bot.set(qn("w:space"), "1")
                    bot.set(qn("w:color"), "CCCCCC")
                    pBdr.append(bot)
                    pPr.append(pBdr)
                except Exception:
                    pass  # OOXML border failed silently — no ASCII fallback

            elif btype == "checklist":
                items = block.get("items", [])
                for item in items:
                    if isinstance(item, dict):
                        checked   = bool(item.get("checked", False))
                        item_text = item.get("text", "")
                    else:
                        checked   = False
                        item_text = str(item)
                    p = doc.add_paragraph()
                    try:
                        p.style = doc.styles["List Paragraph" if "List Paragraph" in style_names else "Normal"]
                    except Exception:
                        pass
                    try:
                        pPr = p._p.get_or_add_pPr()
                        ind = OxmlElement("w:ind")
                        ind.set(qn("w:left"), "360")
                        ind.set(qn("w:hanging"), "360")
                        pPr.append(ind)
                    except Exception:
                        pass
                    sym_run = p.add_run("☑  " if checked else "☐  ")
                    sym_run.font.size = Pt(11)
                    sym_run.font.bold = checked
                    sym_run.font.color.rgb = RGBColor(0x44, 0x72, 0xC4) if checked else RGBColor(0x60, 0x60, 0x60)
                    _md_fill_para_inline(p, item_text)
                    if checked:
                        # Strikethrough for checked items
                        for r in p.runs[1:]:
                            r.font.strike = True
                            r.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

            elif btype == "callout":
                _CALLOUT_STYLES = {
                    "info":    ("EBF3FB", "4472C4", "INFO"),
                    "tip":     ("E8F5E9", "70AD47", "TIP"),
                    "note":    ("FFF9E6", "FFC000", "NOTA"),
                    "warning": ("FFF3CD", "ED7D31", "AVISO"),
                    "error":   ("FDEDED", "C00000", "ERROR"),
                    "success": ("E8F5E9", "70AD47", "OK"),
                }
                kind        = block.get("callout_type", block.get("kind", "info")).lower()
                fill_hex, border_hex, default_label = _CALLOUT_STYLES.get(kind, _CALLOUT_STYLES["info"])
                box_title   = block.get("title", default_label)
                box_text    = block.get("text", "")

                def _apply_box_shading(para, fill: str, border: str, show_left_bar: bool = True):
                    try:
                        pp = para._p.get_or_add_pPr()
                        shd = OxmlElement("w:shd")
                        shd.set(qn("w:val"), "clear")
                        shd.set(qn("w:color"), "auto")
                        shd.set(qn("w:fill"), fill)
                        pp.append(shd)
                        ind = OxmlElement("w:ind")
                        ind.set(qn("w:left"), "360" if show_left_bar else "360")
                        ind.set(qn("w:right"), "180")
                        pp.append(ind)
                        if show_left_bar:
                            pBdr = OxmlElement("w:pBdr")
                            left_b = OxmlElement("w:left")
                            left_b.set(qn("w:val"), "single")
                            left_b.set(qn("w:sz"), "24")
                            left_b.set(qn("w:space"), "6")
                            left_b.set(qn("w:color"), border)
                            pBdr.append(left_b)
                            pp.append(pBdr)
                    except Exception:
                        pass

                bdr_r = int(border_hex[:2], 16)
                bdr_g = int(border_hex[2:4], 16)
                bdr_b = int(border_hex[4:], 16)

                # Title row
                tp = doc.add_paragraph()
                try:
                    tp.style = doc.styles["No Spacing" if "No Spacing" in style_names else "Normal"]
                except Exception:
                    pass
                _apply_box_shading(tp, fill_hex, border_hex, show_left_bar=True)
                tr = tp.add_run(box_title)
                tr.bold = True
                tr.font.size = Pt(10)
                tr.font.color.rgb = RGBColor(bdr_r, bdr_g, bdr_b)

                # Body lines
                for line in (box_text.splitlines() if box_text else [""]):
                    bp = doc.add_paragraph()
                    try:
                        bp.style = doc.styles["No Spacing" if "No Spacing" in style_names else "Normal"]
                    except Exception:
                        pass
                    _apply_box_shading(bp, fill_hex, border_hex, show_left_bar=False)
                    _md_fill_para_inline(bp, line)
                doc.add_paragraph()  # spacing after callout

            elif btype == "highlight":
                text       = block.get("text", "")
                bg_color   = block.get("color", "FFFF00").upper().lstrip("#")
                text_color = block.get("text_color", "000000").upper().lstrip("#")
                p = doc.add_paragraph()
                try:
                    p.style = doc.styles[block.get("style", "Normal") if block.get("style", "Normal") in style_names else "Normal"]
                except Exception:
                    pass
                try:
                    pPr = p._p.get_or_add_pPr()
                    shd = OxmlElement("w:shd")
                    shd.set(qn("w:val"), "clear")
                    shd.set(qn("w:color"), "auto")
                    shd.set(qn("w:fill"), bg_color[:6])
                    pPr.append(shd)
                    ind = OxmlElement("w:ind")
                    ind.set(qn("w:left"), "180")
                    ind.set(qn("w:right"), "180")
                    pPr.append(ind)
                    spc = OxmlElement("w:spacing")
                    spc.set(qn("w:before"), "60")
                    spc.set(qn("w:after"), "60")
                    pPr.append(spc)
                except Exception:
                    pass
                _md_fill_para_inline(p, text)
                # Apply text color and bold to all runs
                tc_r = int(text_color[:2], 16)
                tc_g = int(text_color[2:4], 16)
                tc_b = int(text_color[4:6], 16)
                for r in p.runs:
                    r.font.color.rgb = RGBColor(tc_r, tc_g, tc_b)

            n_blocks += 1

        # Texto plano suelto (sin content_blocks): se vuelca como párrafos nativos
        if markdown and not content_blocks:
            if title:
                _add_cover_title(title, subtitle)
                doc.add_paragraph()
            n_blocks += _render_native_paragraphs(doc, markdown)

        doc.save(str(path))
        _tpl_note = f"  |  Plantilla: {Path(template_path).name}" if _used_template else ""
        return (
            f"✅ Documento Word creado: {path}\n"
            f"   Tema: {theme}  |  Bloques: {n_blocks}  |  Tamaño: {path.stat().st_size:,} bytes{_tpl_note}\n"
            f"   Abre en Word/LibreOffice — estilos O365 aplicados."
        )

    # ── Excel .xlsx ─────────────────────────────────────────────────────────
    elif ext == ".xlsx":
        sheets = _coerce_json(args.get("sheets", []), [])
        if isinstance(sheets, dict):
            sheets = [sheets]
        sheets = [s for s in (sheets or []) if isinstance(s, dict)]
        if not sheets and args.get("headers"):
            sheets = [{"name": args.get("sheet", "Hoja1"), "headers": args["headers"],
                       "rows": args.get("rows", []), "title": title}]
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            from openpyxl.worksheet.table import Table, TableStyleInfo

            _THEME_XLSX = {
                "office":       {"hdr_fill": "2F5496", "hdr_font": "FFFFFF", "title_fill": "1F4E79"},
                "modern":       {"hdr_fill": "1F4E79", "hdr_font": "FFFFFF", "title_fill": "2F5496"},
                "professional": {"hdr_fill": "17375E", "hdr_font": "FFFFFF", "title_fill": "265F8B"},
                "minimal":      {"hdr_fill": "404040", "hdr_font": "FFFFFF", "title_fill": "202020"},
                "corporate":    {"hdr_fill": "003A70", "hdr_font": "FFFFFF", "title_fill": "005599"},
            }
            xt = _THEME_XLSX.get(theme, _THEME_XLSX["office"])

            wb = openpyxl.Workbook()
            wb.remove(wb.active)

            for sh in (sheets or [{"name": "Hoja1", "headers": [], "rows": []}]):
                ws = wb.create_sheet(sh.get("name", "Hoja1"))
                sh_title = sh.get("title", "")
                headers  = sh.get("headers", [])
                rows_data = sh.get("rows", [])
                data_start = 1

                if sh_title:
                    n_cols = max(len(headers), 1)
                    ws.merge_cells(f"A1:{get_column_letter(n_cols)}1")
                    c = ws["A1"]
                    c.value = sh_title
                    c.font      = Font(bold=True, size=14, color=xt["hdr_font"], name="Calibri Light")
                    c.fill      = PatternFill("solid", fgColor=xt["title_fill"])
                    c.alignment = Alignment(horizontal="center", vertical="center")
                    ws.row_dimensions[1].height = 28
                    data_start = 2

                # Header row
                for c_i, h in enumerate(headers):
                    cell = ws.cell(row=data_start, column=c_i + 1, value=h)
                    cell.font      = Font(bold=True, size=10, color=xt["hdr_font"], name="Calibri")
                    cell.fill      = PatternFill("solid", fgColor=xt["hdr_fill"])
                    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                ws.row_dimensions[data_start].height = 22

                # Data rows
                for r_i, row_data in enumerate(rows_data):
                    row_list = list(row_data) if not isinstance(row_data, list) else row_data
                    fill = PatternFill("solid", fgColor="EEF3FB") if r_i % 2 == 0 else PatternFill()
                    for c_i, val in enumerate(row_list[:len(headers)] if headers else row_list):
                        cell = ws.cell(row=data_start + 1 + r_i, column=c_i + 1)
                        # Formula support: strings starting with '=' are written as-is (openpyxl handles them)
                        if isinstance(val, str) and val.startswith("="):
                            cell.value = val
                        else:
                            cell.value = val
                        cell.font      = Font(size=10, name="Calibri")
                        cell.fill      = fill
                        cell.alignment = Alignment(vertical="center", wrap_text=False)
                        cell.border    = Border(bottom=Side(style="thin", color="E0E0E0"))
                        # Auto number format (skip for formulas — let Excel resolve)
                        if not (isinstance(val, str) and val.startswith("=")):
                            if isinstance(val, float):
                                cell.number_format = "#,##0.00"
                            elif isinstance(val, int):
                                cell.number_format = "#,##0"

                # Excel native table (allows sort/filter + native O365 style)
                _THEME_TABLE_STYLE = {
                    "office":       "TableStyleMedium2",
                    "modern":       "TableStyleMedium3",
                    "professional": "TableStyleMedium4",
                    "minimal":      "TableStyleLight1",
                    "corporate":    "TableStyleDark2",
                }
                if headers and rows_data:
                    end_row = data_start + len(rows_data)
                    end_col = get_column_letter(len(headers))
                    tbl_ref = f"A{data_start}:{end_col}{end_row}"
                    tbl_nm  = f"Tabla_{ws.title.replace(' ','_').replace('-','_')}"
                    tbl = Table(displayName=tbl_nm, ref=tbl_ref)
                    tbl.tableStyleInfo = TableStyleInfo(
                        name=_THEME_TABLE_STYLE.get(theme, "TableStyleMedium2"),
                        showFirstColumn=False, showLastColumn=False,
                        showRowStripes=True, showColumnStripes=False,
                    )
                    ws.add_table(tbl)
                    ws.freeze_panes = ws.cell(row=data_start + 1, column=1)

                # Conditional formats for this sheet
                for cf_def in sh.get("conditional_formats", []):
                    try:
                        from openpyxl.formatting.rule import (
                            ColorScaleRule, DataBarRule, CellIsRule,
                            IconSetRule, Rule,
                        )
                        from openpyxl.styles import PatternFill as _PF, Font as _CF_Font
                        cf_range = cf_def.get("range", "A1:A10")
                        cf_type  = cf_def.get("format_type", "color_scale")
                        rule     = None

                        if cf_type == "color_scale":
                            mid_c = cf_def.get("mid_color", "")
                            kwargs = dict(
                                start_type="min",  start_color=cf_def.get("start_color", "FFAAAA"),
                                end_type="max",    end_color=cf_def.get("end_color", "AAFFAA"),
                            )
                            if mid_c:
                                kwargs.update(mid_type="percentile", mid_value=50, mid_color=mid_c)
                            rule = ColorScaleRule(**kwargs)

                        elif cf_type == "data_bar":
                            rule = DataBarRule(
                                start_type="min", start_value=0,
                                end_type="max",   end_value=100,
                                color=cf_def.get("color", "638EC6"),
                            )

                        elif cf_type == "cell_is":
                            op   = cf_def.get("operator", "greaterThan")
                            form = cf_def.get("formula", "0")
                            fc   = cf_def.get("fill_color", "AAFFAA")
                            fnt  = cf_def.get("font_color", "")
                            kw: dict = {"fill": _PF("solid", fgColor=fc)}
                            if fnt:
                                kw["font"] = _CF_Font(color=fnt)
                            rule = CellIsRule(operator=op, formula=[str(form)], **kw)

                        elif cf_type == "icon_set":
                            icon_style = cf_def.get("icon_style", "3TrafficLights1")
                            rule = IconSetRule(
                                icon_style=icon_style,
                                type="percent",
                                values=cf_def.get("thresholds", [0, 33, 67]),
                            )

                        elif cf_type in ("top", "bottom", "top_bottom"):
                            rank     = cf_def.get("rank", 10)
                            pct      = cf_def.get("percent", False)
                            bottom   = cf_def.get("bottom", cf_type == "bottom")
                            fc       = cf_def.get("fill_color", "FFD700")
                            rule = Rule(
                                type="top10",
                                rank=rank,
                                percent=pct,
                                bottom=bottom,
                                dxf=None,
                            )
                            # openpyxl 3.1+ supports dxf in Rule; build manually
                            try:
                                from openpyxl.formatting.rule import Rule as _Rule
                                from openpyxl.styles.differential import DifferentialStyle
                                dxf = DifferentialStyle(fill=_PF("solid", fgColor=fc))
                                rule = _Rule(type="top10", rank=rank, percent=pct,
                                             bottom=bottom, dxf=dxf)
                            except Exception:
                                pass

                        elif cf_type in ("contains_text", "text_contains"):
                            txt = cf_def.get("text", "")
                            fc  = cf_def.get("fill_color", "FFF2CC")
                            try:
                                from openpyxl.styles.differential import DifferentialStyle
                                dxf = DifferentialStyle(fill=_PF("solid", fgColor=fc))
                                rule = Rule(
                                    type="containsText",
                                    operator="containsText",
                                    text=txt,
                                    dxf=dxf,
                                    formula=[f'NOT(ISERROR(SEARCH("{txt}",A1)))'],
                                )
                            except Exception:
                                pass

                        elif cf_type == "formula":
                            form = cf_def.get("formula", "A1>0")
                            fc   = cf_def.get("fill_color", "E2EFDA")
                            try:
                                from openpyxl.styles.differential import DifferentialStyle
                                dxf = DifferentialStyle(fill=_PF("solid", fgColor=fc))
                                rule = Rule(type="expression", dxf=dxf, formula=[form])
                            except Exception:
                                pass

                        if rule is not None:
                            ws.conditional_formatting.add(cf_range, rule)
                    except Exception:
                        pass

                # Native charts for this sheet (embedded openpyxl chart objects)
                for ch_def in sh.get("charts", []):
                    try:
                        from openpyxl.chart import (BarChart, LineChart, PieChart, AreaChart,
                                                     ScatterChart, DoughnutChart, RadarChart,
                                                     BubbleChart, Reference, Series)
                        _CH_TYPE_MAP = {
                            "bar":                 ("bar",     "col", "clustered"),
                            "column":              ("bar",     "col", "clustered"),
                            "horizontal_bar":      ("bar",     "bar", "clustered"),
                            "stacked_bar":         ("bar",     "bar", "stacked"),
                            "stacked_column":      ("bar",     "col", "stacked"),
                            "100_stacked_column":  ("bar",     "col", "percentStacked"),
                            "100_stacked_bar":     ("bar",     "bar", "percentStacked"),
                            "line":                ("line",    None,  "standard"),
                            "stacked_line":        ("line",    None,  "stacked"),
                            "line_markers":        ("line",    None,  "standard"),
                            "area":                ("area",    None,  "standard"),
                            "stacked_area":        ("area",    None,  "stacked"),
                            "pie":                 ("pie",     None,  None),
                            "doughnut":            ("donut",   None,  None),
                            "scatter":             ("scatter", None,  None),
                            "radar":               ("radar",   None,  "standard"),
                            "radar_filled":        ("radar",   None,  "filled"),
                            "bubble":              ("bubble",  None,  None),
                        }
                        ch_type  = ch_def.get("type", "bar").lower()
                        kind, bar_dir, grouping = _CH_TYPE_MAP.get(ch_type, ("bar", "col", "clustered"))

                        if kind == "bar":
                            ch = BarChart()
                            ch.type     = bar_dir or "col"
                            ch.grouping = grouping or "clustered"
                            if ch_type in ("line_markers",):
                                ch.marker = True
                        elif kind == "line":
                            ch = LineChart()
                            ch.grouping = grouping or "standard"
                            if ch_type == "line_markers":
                                for s in getattr(ch, "series", []):
                                    s.marker = None
                        elif kind == "area":
                            ch = AreaChart()
                            ch.grouping = grouping or "standard"
                        elif kind == "pie":
                            ch = PieChart()
                        elif kind == "donut":
                            ch = DoughnutChart()
                            ch.holeSize = ch_def.get("hole_size", 50)
                        elif kind == "scatter":
                            ch = ScatterChart()
                        elif kind == "radar":
                            ch = RadarChart()
                            ch.radarStyle = grouping or "standard"
                        elif kind == "bubble":
                            ch = BubbleChart()
                        else:
                            ch = BarChart()

                        ch.title  = ch_def.get("title", "") or None
                        ch.width  = ch_def.get("width",  15)
                        ch.height = ch_def.get("height", 10)
                        ch_pos    = ch_def.get("position", "E2")

                        # Axis titles
                        x_title = ch_def.get("x_title", "")
                        y_title = ch_def.get("y_title", "")
                        if x_title and hasattr(ch, "x_axis"):
                            ch.x_axis.title = x_title
                        if y_title and hasattr(ch, "y_axis"):
                            ch.y_axis.title = y_title

                        # Data labels
                        show_labels = ch_def.get("show_data_labels", False)

                        # Style (1–48 Office chart styles)
                        ch_style = ch_def.get("style", 2)
                        try:
                            ch.style = int(ch_style)
                        except Exception:
                            pass

                        # Legend position
                        legend_pos = ch_def.get("legend", "r")
                        if legend_pos:
                            ch.legend = ch.legend or type("L", (), {"position": legend_pos})()
                            try:
                                ch.legend.position = legend_pos
                            except Exception:
                                pass

                        dr = ch_def.get("data_range", "")
                        if dr:
                            mc, mr, xc, xr = openpyxl.utils.cell.range_boundaries(dr)
                            if kind == "scatter":
                                xv = Reference(ws, min_col=mc, min_row=mr+1, max_row=xr)
                                yv = Reference(ws, min_col=mc+1, min_row=mr+1, max_row=xr)
                                ser = Series(xv, yv)
                                ch.series.append(ser)
                            elif kind == "bubble":
                                xv = Reference(ws, min_col=mc, min_row=mr+1, max_row=xr)
                                yv = Reference(ws, min_col=mc+1, min_row=mr+1, max_row=xr)
                                bv = Reference(ws, min_col=mc+2, min_row=mr+1, max_row=xr)
                                ser = Series(xv, yv, bv)
                                ch.series.append(ser)
                            else:
                                ch.add_data(Reference(ws, min_col=mc+1, min_row=mr,
                                                      max_col=xc, max_row=xr),
                                            titles_from_data=True)
                                if kind not in ("pie", "donut"):
                                    ch.set_categories(
                                        Reference(ws, min_col=mc, min_row=mr+1, max_row=xr))

                        # Apply data labels after series are added
                        if show_labels:
                            try:
                                from openpyxl.chart.label import DataLabelList
                                ch.dLbls = DataLabelList()
                                ch.dLbls.showVal = True
                            except Exception:
                                pass

                        ws.add_chart(ch, ch_pos)
                    except Exception:
                        pass

                # Auto column widths
                for c_i, h in enumerate(headers):
                    col = get_column_letter(c_i + 1)
                    max_w = max(
                        len(str(h)),
                        max((len(str(r[c_i])) for r in rows_data if c_i < len(r)), default=0),
                    )
                    ws.column_dimensions[col].width = min(max(max_w + 3, 10), 60)

            wb.save(str(path))
            return (
                f"✅ Excel creado: {path}\n"
                f"   Hojas: {len(wb.worksheets)}  |  Tema: {theme}  |  Tamaño: {path.stat().st_size:,} bytes"
            )
        except Exception as exc:
            return f"Error creando .xlsx: {exc}"

    # ── PowerPoint .pptx ─────────────────────────────────────────────────────
    elif ext == ".pptx":
        slides_data = _coerce_json(args.get("slides", []), [])
        if isinstance(slides_data, dict):
            slides_data = [slides_data]
        slides_data = [s for s in (slides_data or []) if isinstance(s, dict)]
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt, Emu
            from pptx.dml.color import RGBColor as PptRGB
            from pptx.enum.text import PP_ALIGN

            _PPTX_THEMES = {
                "office":       {"bg": (0xFF,0xFF,0xFF), "title_c": (0x2F,0x54,0x96), "body_c": (0x26,0x26,0x26), "accent": (0x70,0xAD,0x47), "tbl_hdr": (0x2F,0x54,0x96)},
                "modern":       {"bg": (0xF5,0xF5,0xF5), "title_c": (0x1F,0x4E,0x79), "body_c": (0x33,0x33,0x33), "accent": (0xED,0x7D,0x31), "tbl_hdr": (0x1F,0x4E,0x79)},
                "professional": {"bg": (0xFF,0xFF,0xFF), "title_c": (0x17,0x37,0x5E), "body_c": (0x33,0x33,0x33), "accent": (0x70,0xAD,0x47), "tbl_hdr": (0x17,0x37,0x5E)},
                "minimal":      {"bg": (0xFF,0xFF,0xFF), "title_c": (0x20,0x20,0x20), "body_c": (0x40,0x40,0x40), "accent": (0x80,0x80,0x80), "tbl_hdr": (0x40,0x40,0x40)},
                "corporate":    {"bg": (0xFF,0xFF,0xFF), "title_c": (0x00,0x3A,0x70), "body_c": (0x33,0x33,0x33), "accent": (0xFF,0xC0,0x00), "tbl_hdr": (0x00,0x3A,0x70)},
                "dark":         {"bg": (0x1E,0x1E,0x2E), "title_c": (0x89,0xB4,0xFA), "body_c": (0xCD,0xD6,0xF4), "accent": (0xA6,0xE3,0xA1), "tbl_hdr": (0x31,0x35,0x4A)},
            }
            pt = _PPTX_THEMES.get(theme, _PPTX_THEMES["office"])

            prs = Presentation()
            prs.slide_width  = Inches(13.33)
            prs.slide_height = Inches(7.5)

            def _set_bg(slide, bg_override: dict | None = None):
                """Set slide background: solid, gradient or image."""
                bg = slide.background
                if bg_override:
                    bg_t = bg_override.get("type", "solid")
                    if bg_t == "gradient":
                        try:
                            # Build gradient XML directly — python-pptx gradient API
                            bg.fill.gradient()
                            gs = bg.fill.gradient_stops
                            c1 = bg_override.get("color1", "#1F4E79").lstrip("#")
                            c2 = bg_override.get("color2", "#2F5496").lstrip("#")
                            gs[0].color.rgb = PptRGB(
                                int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16))
                            gs[1].color.rgb = PptRGB(
                                int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16))
                        except Exception:
                            bg.fill.solid()
                            c1 = bg_override.get("color1", "#1F4E79").lstrip("#")
                            bg.fill.fore_color.rgb = PptRGB(
                                int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16))
                    elif bg_t == "image":
                        img_p = Path(bg_override.get("path", "")).expanduser()
                        if img_p.exists():
                            try:
                                sp = slide.shapes.add_picture(
                                    str(img_p), 0, 0, prs.slide_width, prs.slide_height)
                                slide.shapes._spTree.remove(sp._element)
                                slide.shapes._spTree.insert(2, sp._element)
                            except Exception:
                                pass
                    else:
                        c = bg_override.get("color", "#FFFFFF").lstrip("#")
                        bg.fill.solid()
                        bg.fill.fore_color.rgb = PptRGB(
                            int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
                else:
                    bg.fill.solid()
                    bg.fill.fore_color.rgb = PptRGB(*pt["bg"])

            def _add_accent_bar(slide):
                try:
                    bar = slide.shapes.add_shape(
                        1, 0, prs.slide_height - Emu(228600),
                        prs.slide_width, Emu(114300),
                    )
                    bar.fill.solid()
                    bar.fill.fore_color.rgb = PptRGB(*pt["accent"])
                    bar.line.fill.background()
                except Exception:
                    pass

            def _find_body_ph(slide):
                """Find the body/content placeholder robustly by type then idx."""
                try:
                    from pptx.enum.shapes import PP_PLACEHOLDER
                    body_types = (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT,
                                  PP_PLACEHOLDER.CENTER_TITLE)
                    for ph in slide.placeholders:
                        if ph.placeholder_format.type in body_types:
                            return ph
                except Exception:
                    pass
                # Fallback: idx == 1
                for ph in slide.placeholders:
                    if ph.placeholder_format.idx == 1:
                        return ph
                # Any non-title placeholder
                title_ph = slide.shapes.title
                for ph in slide.placeholders:
                    if ph is not title_ph:
                        return ph
                return None

            def _fill_body_text(ph, content: str):
                tf = ph.text_frame
                tf.word_wrap = True
                tf.text = ""
                for line in content.split("\n"):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    p = tf.add_paragraph()
                    indent = len(line) - len(line.lstrip())
                    p.level = min(indent // 2, 4)
                    p.text  = stripped.lstrip("•-*# ").lstrip("0123456789.) ")
                    for run in p.runs:
                        run.font.name = "Calibri"
                        run.font.size = Pt(max(14, 18 - p.level * 2))
                        run.font.color.rgb = PptRGB(*pt["body_c"])

            def _add_pptx_chart_native(slide, ch_def: dict):
                """Add a native python-pptx chart to a slide."""
                try:
                    from pptx.chart.data import CategoryChartData
                    from pptx.enum.chart import XL_CHART_TYPE
                    _XL = {
                        "bar":       XL_CHART_TYPE.BAR_CLUSTERED,
                        "column":    XL_CHART_TYPE.COLUMN_CLUSTERED,
                        "line":      XL_CHART_TYPE.LINE,
                        "pie":       XL_CHART_TYPE.PIE,
                        "doughnut":  XL_CHART_TYPE.DOUGHNUT,
                        "area":      XL_CHART_TYPE.AREA,
                        "scatter":   XL_CHART_TYPE.XY_SCATTER,
                    }
                    c_type    = ch_def.get("chart_type", ch_def.get("type", "column"))
                    xl_type   = _XL.get(c_type, XL_CHART_TYPE.COLUMN_CLUSTERED)
                    c_data    = ch_def.get("data", {})
                    cats      = c_data.get("categories", [])
                    ser_list  = c_data.get("series", [])
                    c_title   = ch_def.get("title", "")
                    x_in      = float(ch_def.get("x", 1.0))
                    y_in      = float(ch_def.get("y", 1.5))
                    w_in      = float(ch_def.get("width", 8.0))
                    h_in      = float(ch_def.get("height", 4.5))

                    if c_type == "scatter":
                        from pptx.chart.data import XyChartData
                        chart_data = XyChartData()
                        for s in ser_list:
                            series = chart_data.add_series(s.get("label", "Serie"))
                            xvals  = s.get("x_values", s.get("values", []))
                            yvals  = s.get("y_values", [])
                            for xv, yv in zip(xvals, yvals):
                                series.add_data_point(xv, yv)
                    else:
                        chart_data = CategoryChartData()
                        chart_data.categories = cats or [f"Cat {i+1}" for i in range(
                            len(ser_list[0].get("values", [])) if ser_list else 0
                        )]
                        for s in ser_list:
                            chart_data.add_series(s.get("label", "Serie"), s.get("values", []))

                    chart_shape = slide.shapes.add_chart(
                        xl_type,
                        Inches(x_in), Inches(y_in),
                        Inches(w_in), Inches(h_in),
                        chart_data,
                    )
                    chart = chart_shape.chart
                    if c_title:
                        chart.has_title = True
                        chart.chart_title.text_frame.text = c_title
                    chart.has_legend = len(ser_list) > 1
                    return True
                except Exception:
                    return False

            def _add_pptx_table(slide, tbl_def: dict):
                """Add a native python-pptx table to a slide."""
                try:
                    headers   = tbl_def.get("headers", [])
                    rows_data = tbl_def.get("rows", [])
                    if not headers:
                        return
                    x_in = float(tbl_def.get("x", 0.5))
                    y_in = float(tbl_def.get("y", 1.5))
                    w_in = float(tbl_def.get("width", 12.0))
                    h_in = float(tbl_def.get("height", 0.5 + 0.35 * (len(rows_data) + 1)))
                    n_cols = len(headers)
                    n_rows = 1 + len(rows_data)
                    tbl = slide.shapes.add_table(
                        n_rows, n_cols,
                        Inches(x_in), Inches(y_in),
                        Inches(w_in), Inches(h_in),
                    ).table
                    hdr_rgb = PptRGB(*pt["tbl_hdr"])
                    # Header row
                    for c_i, h in enumerate(headers):
                        cell = tbl.cell(0, c_i)
                        cell.text = str(h)
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = hdr_rgb
                        for para in cell.text_frame.paragraphs:
                            for run in para.runs:
                                run.font.bold  = True
                                run.font.color.rgb = PptRGB(0xFF, 0xFF, 0xFF)
                                run.font.size  = Pt(10)
                                run.font.name  = "Calibri"
                    # Data rows
                    alt_rgb = PptRGB(0xEE, 0xF3, 0xFB)
                    for r_i, row_d in enumerate(rows_data):
                        for c_i, val in enumerate(row_d[:n_cols]):
                            cell = tbl.cell(r_i + 1, c_i)
                            cell.text = str(val)
                            if r_i % 2 == 0:
                                cell.fill.solid()
                                cell.fill.fore_color.rgb = alt_rgb
                            for para in cell.text_frame.paragraphs:
                                for run in para.runs:
                                    run.font.size = Pt(10)
                                    run.font.name = "Calibri"
                                    run.font.color.rgb = PptRGB(*pt["body_c"])
                except Exception:
                    pass

            # ── Title slide ──────────────────────────────────────────────────
            if title:
                lyt = prs.slide_layouts[0]
                slide = prs.slides.add_slide(lyt)
                _set_bg(slide)
                if slide.shapes.title:
                    slide.shapes.title.text = title
                    tf = slide.shapes.title.text_frame
                    for para in tf.paragraphs:
                        para.alignment = PP_ALIGN.CENTER
                        for run in para.runs:
                            run.font.name  = "Calibri Light"
                            run.font.size  = Pt(40)
                            run.font.color.rgb = PptRGB(*pt["title_c"])
                            run.font.bold  = False
                if subtitle:
                    sub_ph = _find_body_ph(slide)
                    if sub_ph:
                        sub_ph.text = subtitle
                        for para in sub_ph.text_frame.paragraphs:
                            para.alignment = PP_ALIGN.CENTER
                            for run in para.runs:
                                run.font.name  = "Calibri"
                                run.font.size  = Pt(20)
                                run.font.color.rgb = PptRGB(*pt["body_c"])
                _add_accent_bar(slide)

            # ── Content slides ───────────────────────────────────────────────
            for sl in slides_data:
                sl_title   = sl.get("title", "")
                sl_content = sl.get("content", "")
                sl_layout  = sl.get("layout", "bullet")
                sl_notes   = sl.get("notes", "")
                sl_blocks  = sl.get("blocks", [])  # advanced: list of block dicts

                lyt_idx = {"title": 0, "bullet": 1, "blank": 6, "two_col": 3}.get(sl_layout, 1)
                try:
                    lyt = prs.slide_layouts[lyt_idx]
                except IndexError:
                    lyt = prs.slide_layouts[min(lyt_idx, len(prs.slide_layouts)-1)]

                slide = prs.slides.add_slide(lyt)
                _set_bg(slide, sl.get("background"))

                # Apply slide title
                if slide.shapes.title and sl_title:
                    slide.shapes.title.text = sl_title
                    tf = slide.shapes.title.text_frame
                    for para in tf.paragraphs:
                        for run in para.runs:
                            run.font.name  = "Calibri Light"
                            run.font.size  = Pt(28)
                            run.font.color.rgb = PptRGB(*pt["title_c"])
                            run.font.bold  = False

                # Apply slide content (text bullets)
                if sl_content:
                    body_ph = _find_body_ph(slide)
                    if body_ph:
                        _fill_body_text(body_ph, sl_content)

                # Advanced blocks: chart, table, image, text
                for blk in sl_blocks:
                    btype = blk.get("type", "text")
                    if btype in ("chart", "column_chart", "bar_chart", "line_chart",
                                 "pie_chart", "doughnut_chart", "scatter_chart"):
                        if btype != "chart":
                            blk["chart_type"] = btype.replace("_chart", "")
                        ok = _add_pptx_chart_native(slide, blk)
                        if not ok:
                            # Fallback: add text box
                            tb = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1))
                            tb.text_frame.text = f"[Gráfica '{blk.get('chart_type','bar')}' — instala python-pptx>=0.6.21]"
                    elif btype == "table":
                        _add_pptx_table(slide, blk)
                    elif btype == "image":
                        img_p = Path(blk.get("path", "")).expanduser()
                        if img_p.exists():
                            try:
                                slide.shapes.add_picture(
                                    str(img_p),
                                    Inches(float(blk.get("x", 1.0))),
                                    Inches(float(blk.get("y", 1.5))),
                                    width=Inches(float(blk.get("width", 6.0))),
                                )
                            except Exception:
                                pass
                    elif btype == "text":
                        tb = slide.shapes.add_textbox(
                            Inches(float(blk.get("x", 1.0))),
                            Inches(float(blk.get("y", 1.5))),
                            Inches(float(blk.get("width", 6.0))),
                            Inches(float(blk.get("height", 1.0))),
                        )
                        tf = tb.text_frame
                        tf.word_wrap = True
                        tf.text = blk.get("text", "")
                        for para in tf.paragraphs:
                            for run in para.runs:
                                run.font.name  = blk.get("font", "Calibri")
                                run.font.size  = Pt(float(blk.get("size", 18)))
                                run.font.color.rgb = PptRGB(*pt["body_c"])

                    elif btype == "checklist":
                        items = blk.get("items", [])
                        x_in  = float(blk.get("x", 1.0))
                        y_in  = float(blk.get("y", 1.5))
                        w_in  = float(blk.get("width", 6.0))
                        h_per = float(blk.get("item_height", 0.4))
                        tb = slide.shapes.add_textbox(
                            Inches(x_in), Inches(y_in),
                            Inches(w_in), Inches(max(h_per * len(items), 0.5)),
                        )
                        tf = tb.text_frame
                        tf.word_wrap = True
                        tf.text = ""
                        for item in items:
                            if isinstance(item, dict):
                                checked   = bool(item.get("checked", False))
                                item_text = item.get("text", "")
                            else:
                                checked   = False
                                item_text = str(item)
                            p = tf.add_paragraph()
                            p.text = ("☑  " if checked else "☐  ") + item_text
                            for run in p.runs:
                                run.font.name  = "Calibri"
                                run.font.size  = Pt(float(blk.get("size", 14)))
                                run.font.color.rgb = (PptRGB(0x44,0x72,0xC4) if checked
                                                      else PptRGB(*pt["body_c"]))
                                if checked:
                                    run.font.strike = True

                    elif btype == "code_block":
                        code = blk.get("code", blk.get("text", ""))
                        x_in = float(blk.get("x", 0.5))
                        y_in = float(blk.get("y", 1.5))
                        w_in = float(blk.get("width", 12.0))
                        lines = code.splitlines() or [""]
                        h_in = float(blk.get("height", max(0.3 * len(lines), 0.5)))
                        try:
                            code_shape = slide.shapes.add_textbox(
                                Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in)
                            )
                            code_shape.fill.solid()
                            code_shape.fill.fore_color.rgb = PptRGB(0x1E, 0x1E, 0x2E)
                            tf_c = code_shape.text_frame
                            tf_c.word_wrap = False
                            tf_c.text = ""
                            for line in lines:
                                p = tf_c.add_paragraph()
                                p.text = line
                                for run in p.runs:
                                    run.font.name  = "Consolas"
                                    run.font.size  = Pt(float(blk.get("size", 11)))
                                    run.font.color.rgb = PptRGB(0xCD, 0xD6, 0xF4)
                        except Exception:
                            pass

                    elif btype == "callout":
                        _PPT_CALLOUT = {
                            "info":    ((0xEB,0xF3,0xFB), (0x44,0x72,0xC4), "ℹ  Info"),
                            "tip":     ((0xE8,0xF5,0xE9), (0x70,0xAD,0x47), "💡 Tip"),
                            "note":    ((0xFF,0xF9,0xE6), (0xFF,0xC0,0x00), "📝 Note"),
                            "warning": ((0xFF,0xF3,0xCD), (0xED,0x7D,0x31), "⚠  Warning"),
                            "error":   ((0xFD,0xED,0xED), (0xC0,0x00,0x00), "✖  Error"),
                        }
                        kind     = blk.get("callout_type", blk.get("kind", "info")).lower()
                        fill_rgb, border_rgb, default_lbl = _PPT_CALLOUT.get(kind, _PPT_CALLOUT["info"])
                        box_text  = blk.get("text", "")
                        box_title = blk.get("title", default_lbl)
                        x_in = float(blk.get("x", 0.5))
                        y_in = float(blk.get("y", 1.5))
                        w_in = float(blk.get("width", 12.0))
                        h_in = float(blk.get("height", 1.2))
                        try:
                            box_shape = slide.shapes.add_textbox(
                                Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in)
                            )
                            box_shape.fill.solid()
                            box_shape.fill.fore_color.rgb = PptRGB(*fill_rgb)
                            tf_b = box_shape.text_frame
                            tf_b.word_wrap = True
                            tf_b.text = ""
                            p_title = tf_b.add_paragraph()
                            p_title.text = box_title
                            for run in p_title.runs:
                                run.font.bold  = True
                                run.font.color.rgb = PptRGB(*border_rgb)
                                run.font.size  = Pt(12)
                                run.font.name  = "Calibri"
                            if box_text:
                                p_body = tf_b.add_paragraph()
                                p_body.text = box_text
                                for run in p_body.runs:
                                    run.font.name  = "Calibri"
                                    run.font.size  = Pt(11)
                                    run.font.color.rgb = PptRGB(*pt["body_c"])
                        except Exception:
                            pass

                # Speaker notes
                if sl_notes:
                    try:
                        notes_slide = slide.notes_slide
                        notes_slide.notes_text_frame.text = sl_notes
                    except Exception:
                        pass

                _add_accent_bar(slide)

            prs.save(str(path))
            n_slides = len(prs.slides)
            return (
                f"✅ Presentación PowerPoint creada: {path}\n"
                f"   Diapositivas: {n_slides}  |  Tema: {theme}  |  Tamaño: {path.stat().st_size:,} bytes\n"
                f"   Charts y tablas nativos python-pptx — editables en PowerPoint/LibreOffice Impress."
            )
        except ImportError:
            return "python-pptx no disponible. Instala con: pip install python-pptx"
        except Exception as exc:
            return f"Error creando .pptx: {exc}"

    else:
        return f"Formato no soportado: {ext}. Usa .docx, .xlsx o .pptx"


def _tool_doc_create_rfc(args: dict) -> str:
    """Genera un RFC/Request for Change como documento O365 nativo (.docx) con content_blocks.

    Construye bloques nativos (title, tablas, headings, párrafos) y delega en doc_create.
    Sin path se devuelve un resumen de texto plano del RFC.
    """
    title            = args.get("title", "")
    requester        = args.get("requester", "")
    if not title or not requester:
        return "Parámetros requeridos: title, requester"

    date             = args.get("date", datetime.date.today().isoformat())
    priority         = args.get("priority", "Media")
    change_type      = args.get("change_type", "Normal")
    affected_systems = args.get("affected_systems", "Por especificar")
    description      = args.get("description", "Por completar")
    justification    = args.get("justification", "Por completar")
    risk             = args.get("risk", "Por analizar")
    risk_level       = args.get("risk_level", "Bajo")
    rollback_plan    = args.get("rollback_plan", "Por definir")
    testing_plan     = args.get("testing_plan", "Por definir")
    impl_steps       = args.get("implementation_steps", "Por definir")
    scheduled_date   = args.get("scheduled_date", "Por definir")
    scheduled_window = args.get("scheduled_window", "Por definir")
    approver         = args.get("approver", "Por asignar")
    output_path      = args.get("output_path", "")
    fmt              = args.get("format", "docx").lower()

    rfc_id = f"RFC-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"

    content_blocks = [
        {"type": "title", "text": f"{rfc_id} — {title}"},
        {"type": "table", "headers": ["Campo", "Valor"], "rows": [
            ["ID RFC", rfc_id],
            ["Título", title],
            ["Solicitante", requester],
            ["Fecha solicitud", date],
            ["Tipo de cambio", change_type],
            ["Prioridad", priority],
            ["Nivel de riesgo", risk_level],
            ["Fecha programada", scheduled_date],
            ["Ventana de cambio", scheduled_window],
            ["Aprobador", approver],
        ]},
        {"type": "horizontal_rule"},
        {"type": "heading", "level": 1, "text": "1. Descripción del cambio"},
        {"type": "paragraph", "text": description},
        {"type": "heading", "level": 1, "text": "2. Justificación"},
        {"type": "paragraph", "text": justification},
        {"type": "heading", "level": 1, "text": "3. Sistemas afectados"},
        {"type": "paragraph", "text": affected_systems},
        {"type": "heading", "level": 1, "text": "4. Plan de implementación"},
        {"type": "paragraph", "text": impl_steps},
        {"type": "heading", "level": 1, "text": "5. Plan de pruebas y validación"},
        {"type": "paragraph", "text": testing_plan},
        {"type": "heading", "level": 1, "text": "6. Análisis de riesgos"},
        {"type": "paragraph", "text": f"**Nivel de riesgo:** {risk_level}"},
        {"type": "paragraph", "text": risk},
        {"type": "heading", "level": 1, "text": "7. Plan de marcha atrás (Rollback)"},
        {"type": "paragraph", "text": rollback_plan},
        {"type": "horizontal_rule"},
        {"type": "heading", "level": 1, "text": "8. Aprobaciones"},
        {"type": "table", "headers": ["Rol", "Nombre", "Firma", "Fecha"], "rows": [
            ["Solicitante", requester, "", date],
            ["Aprobador técnico", approver, "", ""],
            ["Responsable de negocio", "", "", ""],
            ["Gestor de cambios", "", "", ""],
        ]},
    ]

    # Representación de texto plano (para .md/.txt y para retorno inline sin path)
    text = (
        f"{rfc_id} — {title}\n\n"
        f"Solicitante: {requester}    Fecha: {date}    Tipo: {change_type}    "
        f"Prioridad: {priority}    Riesgo: {risk_level}    Aprobador: {approver}\n\n"
        f"1. Descripción del cambio\n{description}\n\n"
        f"2. Justificación\n{justification}\n\n"
        f"3. Sistemas afectados\n{affected_systems}\n\n"
        f"4. Plan de implementación\n{impl_steps}\n\n"
        f"5. Plan de pruebas y validación\n{testing_plan}\n\n"
        f"6. Análisis de riesgos (Nivel: {risk_level})\n{risk}\n\n"
        f"7. Plan de marcha atrás (Rollback)\n{rollback_plan}\n\n"
        f"8. Aprobaciones\n"
        f"   Solicitante: {requester} ({date})\n"
        f"   Aprobador técnico: {approver}\n"
        f"   Responsable de negocio:\n"
        f"   Gestor de cambios:\n"
    )

    if output_path:
        out = Path(output_path).expanduser()
        if not out.suffix:
            out = out.with_suffix(".docx" if fmt == "docx" else ".md")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() == ".docx":
            res = _tool_doc_create({
                "path":           str(out),
                "content_blocks": content_blocks,
                "theme":          args.get("theme", "office"),
            })
            return f"{res}\n   ID RFC: {rfc_id}"
        out.write_text(text)
        return f"✅ RFC generado: {out}\n   ID: {rfc_id}"
    return f"📋 RFC generado (ID: {rfc_id}):\n\n{text}"


def _tool_set_paragraph_format(args: dict) -> str:
    """Formatea un párrafo específico en .docx por índice: fuente, tamaño, color, alineación, espaciado."""
    path      = Path(args.get("path", "")).expanduser()
    idx       = args.get("paragraph_index", 0)
    font_name = args.get("font_name", None)
    font_size = args.get("font_size", None)
    color     = args.get("color", None)
    bold      = args.get("bold", None)
    italic    = args.get("italic", None)
    underline = args.get("underline", None)
    alignment = args.get("alignment", None)
    sp_before = args.get("space_before", None)
    sp_after  = args.get("space_after", None)
    line_sp   = args.get("line_spacing", None)
    style_nm  = args.get("style", None)

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc  = Document(str(path))
        paras = doc.paragraphs
        if idx < 0 or idx >= len(paras):
            return f"Índice {idx} fuera de rango. El documento tiene {len(paras)} párrafos."
        para = paras[idx]

        if style_nm:
            try:
                para.style = doc.styles[style_nm]
            except KeyError:
                pass

        _align_map = {
            "left":    WD_ALIGN_PARAGRAPH.LEFT,
            "center":  WD_ALIGN_PARAGRAPH.CENTER,
            "right":   WD_ALIGN_PARAGRAPH.RIGHT,
            "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
        }
        if alignment and alignment.lower() in _align_map:
            para.alignment = _align_map[alignment.lower()]

        pf = para.paragraph_format
        if sp_before is not None:
            pf.space_before = Pt(sp_before)
        if sp_after is not None:
            pf.space_after  = Pt(sp_after)
        if line_sp is not None:
            pf.line_spacing = line_sp

        for run in para.runs:
            if font_name:
                run.font.name = font_name
            if font_size:
                run.font.size = Pt(font_size)
            if color:
                hex_c = color.lstrip("#")
                r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
                run.font.color.rgb = RGBColor(r, g, b)
            if bold is not None:
                run.bold = bold
            if italic is not None:
                run.italic = italic
            if underline is not None:
                run.underline = underline

        doc.save(str(path))
        return f"✅ Párrafo {idx} formateado — {path.name}"
    except Exception as exc:
        return f"Error formateando párrafo: {exc}"


def _tool_apply_document_theme(args: dict) -> str:
    """Aplica un tema de colores y fuentes a todos los estilos de un .docx."""
    path     = Path(args.get("path", "")).expanduser()
    theme    = args.get("theme", "office")
    output   = args.get("output_path", "")

    _THEMES = {
        "office": {
            "h1_color": (0x2E, 0x74, 0xB5), "h2_color": (0x2E, 0x74, 0xB5),
            "h1_size": 18, "h2_size": 14, "h3_size": 12,
            "body_font": "Calibri", "heading_font": "Calibri Light",
        },
        "modern": {
            "h1_color": (0x1F, 0x4E, 0x79), "h2_color": (0x2F, 0x54, 0x96),
            "h1_size": 20, "h2_size": 16, "h3_size": 13,
            "body_font": "Calibri", "heading_font": "Calibri Light",
        },
        "professional": {
            "h1_color": (0x17, 0x37, 0x5E), "h2_color": (0x26, 0x5F, 0x8B),
            "h1_size": 18, "h2_size": 14, "h3_size": 12,
            "body_font": "Georgia", "heading_font": "Cambria",
        },
        "minimal": {
            "h1_color": (0x40, 0x40, 0x40), "h2_color": (0x60, 0x60, 0x60),
            "h1_size": 18, "h2_size": 14, "h3_size": 12,
            "body_font": "Arial", "heading_font": "Arial",
        },
        "corporate": {
            "h1_color": (0x00, 0x3A, 0x70), "h2_color": (0x00, 0x55, 0x99),
            "h1_size": 20, "h2_size": 15, "h3_size": 12,
            "body_font": "Calibri", "heading_font": "Calibri Light",
        },
    }

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    cfg = _THEMES.get(theme, _THEMES["office"])

    try:
        from docx import Document
        from docx.shared import Pt, RGBColor

        doc = Document(str(path))
        _style_map = {
            "Heading 1": (cfg["heading_font"], cfg["h1_size"], cfg["h1_color"]),
            "Heading 2": (cfg["heading_font"], cfg["h2_size"], cfg["h2_color"]),
            "Heading 3": (cfg["heading_font"], cfg["h3_size"], cfg["h2_color"]),
            "Normal":    (cfg["body_font"],    11,              None),
            "Body Text": (cfg["body_font"],    11,              None),
        }
        applied = []
        for style_name, (font_nm, size, col) in _style_map.items():
            try:
                s = doc.styles[style_name]
                s.font.name = font_nm
                s.font.size = Pt(size)
                if col:
                    s.font.color.rgb = RGBColor(*col)
                applied.append(style_name)
            except KeyError:
                pass

        dest = output or str(path)
        doc.save(dest)
        return f"✅ Tema '{theme}' aplicado ({', '.join(applied)}) — {Path(dest).name}"
    except Exception as exc:
        return f"Error aplicando tema: {exc}"


def _tool_doc_add_header_footer(args: dict) -> str:
    """Añade cabecera y/o pie de página a un documento .docx."""
    path        = Path(args.get("path", "")).expanduser()
    header_text = args.get("header", "")
    footer_text = args.get("footer", "")
    page_num    = args.get("page_number", False)
    align       = args.get("alignment", "center")
    font_size   = args.get("font_size", 10)

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        _align_map = {
            "left":   WD_ALIGN_PARAGRAPH.LEFT,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right":  WD_ALIGN_PARAGRAPH.RIGHT,
        }
        a = _align_map.get(align, WD_ALIGN_PARAGRAPH.CENTER)

        doc     = Document(str(path))
        section = doc.sections[0]
        changed = []

        if header_text:
            section.different_first_page_header_footer = False
            header = section.header
            p      = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
            p.clear()
            run = p.add_run(header_text)
            run.font.size = Pt(font_size)
            p.alignment = a
            changed.append("cabecera")

        if footer_text or page_num:
            footer = section.footer
            p      = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
            p.clear()
            if footer_text:
                run = p.add_run(footer_text)
                run.font.size = Pt(font_size)
            if page_num:
                if footer_text:
                    p.add_run("  —  ").font.size = Pt(font_size)
                run_pg = p.add_run()
                fldChar1 = OxmlElement("w:fldChar")
                fldChar1.set(qn("w:fldCharType"), "begin")
                instrText = OxmlElement("w:instrText")
                instrText.text = " PAGE "
                fldChar2 = OxmlElement("w:fldChar")
                fldChar2.set(qn("w:fldCharType"), "end")
                run_pg._r.extend([fldChar1, instrText, fldChar2])
            p.alignment = a
            changed.append("pie de página")

        doc.save(str(path))
        return f"✅ Añadidos: {', '.join(changed)} — {path.name}"
    except Exception as exc:
        return f"Error añadiendo cabecera/pie: {exc}"


def _tool_doc_add_toc(args: dict) -> str:
    """Inserta un campo de Tabla de Contenidos (TOC) al inicio de un .docx."""
    path      = Path(args.get("path", "")).expanduser()
    title     = args.get("title", "Tabla de Contenidos")
    max_level = args.get("max_level", 3)

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        doc = Document(str(path))

        # Insert TOC title paragraph before any existing content
        toc_title = doc.add_paragraph(title)
        toc_title.style = doc.styles["Heading 1"] if "Heading 1" in [s.name for s in doc.styles] else doc.styles["Normal"]
        doc.element.body.insert(0, toc_title._element)

        # Build TOC field XML
        toc_para = doc.add_paragraph()
        doc.element.body.insert(1, toc_para._element)
        run = toc_para.add_run()

        fldChar_begin = OxmlElement("w:fldChar")
        fldChar_begin.set(qn("w:fldCharType"), "begin")

        instrText = OxmlElement("w:instrText")
        instrText.set(qn("xml:space"), "preserve")
        instrText.text = f' TOC \\o "1-{max_level}" \\h \\z \\u '

        fldChar_separate = OxmlElement("w:fldChar")
        fldChar_separate.set(qn("w:fldCharType"), "separate")

        fldChar_end = OxmlElement("w:fldChar")
        fldChar_end.set(qn("w:fldCharType"), "end")

        run._r.extend([fldChar_begin, instrText, fldChar_separate, fldChar_end])

        doc.save(str(path))
        return (f"✅ TOC insertada al inicio de {path.name}\n"
                f"   Niveles: 1-{max_level}. Actualiza con Ctrl+A → F9 en Word/LibreOffice.")
    except Exception as exc:
        return f"Error insertando TOC: {exc}"


# ── Nuevas tools PPTX avanzadas ───────────────────────────────────────────────


def _tool_doc_create_from_template(args: dict) -> str:
    """Crea un .docx a partir de una plantilla de empresa (.docx/.dotx) y bloques de contenido.

    La plantilla hereda estilos, fuentes, cabecera/pie, logo y márgenes.
    Después se añaden los content_blocks al documento.

    Tipos de bloque (TODOS los tipos de doc_create están soportados):
      {"type": "heading",       "level": 1-6, "text": "..."}
      {"type": "paragraph",     "text": "...", "style": "Normal|Body Text|Quote|..."}
      {"type": "bullet_list",   "items": ["item1", {"text":"item2","items":["sub"]}]}
      {"type": "numbered_list", "items": ["paso1", "paso2"]}
      {"type": "table",         "headers": ["C1","C2"], "rows": [["a","b"]], "style": "Table Grid"}
      {"type": "image",         "path": "/ruta/img.png", "width_inches": 5.0, "caption": "Fig 1"}
      {"type": "chart",         "chart_type": "bar|line|pie|doughnut|area|scatter|radar",
                                "title": "...", "width_inches": 5.5, "height_inches": 3.5,
                                "data": {"categories":[...], "series":[{"label":"...","values":[...]}]}}
      {"type": "checklist",     "items": [{"text":"Tarea 1","checked":true}, "Tarea 2"]}
      {"type": "callout",       "callout_type": "info|tip|note|warning|error|success",
                                "title": "opcional", "text": "mensaje"}
      {"type": "highlight",     "text": "Texto resaltado", "color": "FFFF00", "text_color": "000000"}
      {"type": "toc",           "title": "Tabla de contenido"}
      {"type": "signature_block","roles": ["Autor", "Revisor", "Aprobador"]}
      {"type": "code_block",    "code": "...", "language": "python"}
      {"type": "markdown",      "text": "Texto plano con **negrita**/*cursiva* inline (NO parsea # ni listas)"}
      {"type": "pagebreak"}
      {"type": "horizontal_rule"}
    """
    template_path   = args.get("template_path", "")
    output_path     = args.get("output_path", "")
    content_blocks  = args.get("content_blocks", [])
    fields          = args.get("fields", {})  # optional Jinja2 fields to fill first
    clear_body      = args.get("clear_template_body", False)

    if not output_path:
        return "Parámetro requerido: output_path"

    out = Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
    except ImportError:
        return "python-docx no disponible. Instala con: pip install python-docx"

    # If template has Jinja2 fields AND fields dict provided, render via docxtpl first
    if template_path and fields:
        try:
            from docxtpl import DocxTemplate
            tpl_path = Path(template_path).expanduser()
            if tpl_path.exists():
                tpl = DocxTemplate(str(tpl_path))
                ctx = {str(k): v for k, v in fields.items()}
                ctx.update({str(k).upper(): v for k, v in fields.items()})
                tpl.render(ctx)
                # Save to temp, then load for content_blocks
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                    tmp_path = tmp.name
                tpl.save(tmp_path)
                doc = Document(tmp_path)
                Path(tmp_path).unlink(missing_ok=True)
                template_path = ""  # already loaded
        except ImportError:
            pass
        except Exception:
            pass  # fall through to normal loading

    # Cargar plantilla o crear en blanco
    if template_path:
        tpl = Path(template_path).expanduser()
        if not tpl.exists():
            return f"Plantilla no encontrada: {tpl}"
        doc = Document(str(tpl))
        # Limpiar cuerpo si es .dotx o se pide explícitamente
        if tpl.suffix.lower() in (".dotx", ".dot") or clear_body:
            body = doc.element.body
            for p in body.findall(qn("w:p"))[:-1]:
                body.remove(p)
            for t in body.findall(qn("w:tbl")):
                body.remove(t)
    elif not fields:
        doc = Document()

    style_names = {s.name for s in doc.styles}

    def _safe(name: str, fallback: str = "Normal") -> str:
        return name if name in style_names else fallback

    n_added = 0
    for block in content_blocks:
        btype = block.get("type", "paragraph")

        if btype == "heading":
            level = max(1, min(9, int(block.get("level", 1))))
            try:
                doc.add_heading(block.get("text", ""), level=level)
            except Exception:
                doc.add_paragraph(block.get("text", ""))
            n_added += 1

        elif btype == "paragraph":
            style_nm = _safe(block.get("style", "Normal"))
            p = doc.add_paragraph()
            try:
                p.style = doc.styles[style_nm]
            except Exception:
                pass
            _md_fill_para_inline(p, block.get("text", ""))
            n_added += 1

        elif btype == "bullet_list":
            style_nm = _safe("List Bullet", "Normal")
            for item in block.get("items", []):
                p = doc.add_paragraph(style=style_nm)
                _md_fill_para_inline(p, str(item))
            n_added += 1

        elif btype == "numbered_list":
            style_nm = _safe("List Number", "Normal")
            for item in block.get("items", []):
                p = doc.add_paragraph(style=style_nm)
                _md_fill_para_inline(p, str(item))
            n_added += 1

        elif btype == "table":
            headers  = block.get("headers", [])
            rows     = block.get("rows", [])
            style_nm = block.get("style", "Table Grid")
            n_cols   = max(len(headers), max((len(r) for r in rows), default=0), 1)
            n_rows   = (1 if headers else 0) + len(rows)
            tbl = doc.add_table(rows=n_rows, cols=n_cols)
            try:
                tbl.style = doc.styles[_safe(style_nm, "Table Grid")]
            except Exception:
                pass
            row_off = 0
            if headers:
                for c_i, h in enumerate(headers[:n_cols]):
                    cell = tbl.rows[0].cells[c_i]
                    cell.text = ""
                    p = cell.paragraphs[0]
                    _md_fill_para_inline(p, str(h))
                    for run in p.runs:
                        run.bold = True
                row_off = 1
            for r_i, row_data in enumerate(rows):
                for c_i, val in enumerate(row_data[:n_cols]):
                    cell = tbl.rows[r_i + row_off].cells[c_i]
                    cell.text = ""
                    p = cell.paragraphs[0]
                    _md_fill_para_inline(p, str(val))
            n_added += 1

        elif btype == "image":
            img_p   = Path(block.get("path", "")).expanduser()
            width   = float(block.get("width_inches", 5.0))
            caption = block.get("caption", "")
            if img_p.exists():
                try:
                    doc.add_picture(str(img_p), width=Inches(width))
                    doc.paragraphs[-1].alignment = 1  # CENTER
                    if caption:
                        cp = doc.add_paragraph(caption)
                        cp.alignment = 1
                        try:
                            cp.style = doc.styles[_safe("Caption")]
                        except Exception:
                            for run in cp.runs:
                                run.italic = True
                                try:
                                    run.font.size = Pt(9)
                                except Exception:
                                    pass
                    n_added += 1
                except Exception as exc:
                    doc.add_paragraph(f"[Error imagen: {exc}]")
            else:
                doc.add_paragraph(f"[Imagen no encontrada: {block.get('path','')}]")

        elif btype == "code_block":
            code = block.get("code", "")
            p = doc.add_paragraph()
            try:
                p.style = doc.styles[_safe("Code", "Normal")]
            except Exception:
                pass
            run = p.add_run(code)
            run.font.name = "Consolas"
            try:
                run.font.size = Pt(9)
            except Exception:
                pass
            n_added += 1

        elif btype == "markdown":
            _render_native_paragraphs(doc, block.get("text", ""))
            n_added += 1

        elif btype == "pagebreak":
            doc.add_page_break()
            n_added += 1

        elif btype == "horizontal_rule":
            p = doc.add_paragraph()
            try:
                pPr = p._p.get_or_add_pPr()
                pBdr = OxmlElement("w:pBdr")
                bot = OxmlElement("w:bottom")
                bot.set(qn("w:val"), "single")
                bot.set(qn("w:sz"), "6")
                bot.set(qn("w:space"), "1")
                bot.set(qn("w:color"), "CCCCCC")
                pBdr.append(bot)
                pPr.append(pBdr)
            except Exception:
                pass  # OOXML border failed silently — no ASCII fallback
            n_added += 1

        elif btype == "chart":
            # Native OOXML DrawingML chart — same as doc_create
            chart_data = block.get("data", {})
            c_type     = block.get("chart_type", "bar")
            c_title    = block.get("title", "")
            c_cats     = chart_data.get("categories", [])
            c_series   = chart_data.get("series", chart_data.get("series_list", []))
            if not c_series:
                vals   = chart_data.get("values", [])
                labels = chart_data.get("labels", c_cats)
                if vals:
                    c_series = [{"label": c_title or "Serie 1", "values": vals}]
                    if not c_cats:
                        c_cats = labels
            if c_series:
                w_in = float(block.get("width_inches", 5.5))
                h_in = float(block.get("height_inches", 3.5))
                cxml = _build_word_chart_xml(c_type, c_cats, c_series, c_title)
                ok   = _embed_word_chart_native(doc, cxml, int(w_in * 914400), int(h_in * 914400))
                if ok:
                    if c_title:
                        cap = doc.add_paragraph()
                        cap.alignment = 1  # CENTER
                        r = cap.add_run(c_title)
                        r.font.size = Pt(9)
                        r.font.italic = True
                        r.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
                    n_added += 1
                else:
                    doc.add_paragraph(f"[Gráfica '{c_type}' — requiere python-docx 1.0+ con lxml]")
            else:
                doc.add_paragraph("[Gráfica sin datos: especifica data.series o data.values]")

        elif btype == "checklist":
            items = block.get("items", [])
            for item in items:
                checked   = bool(item.get("checked", False)) if isinstance(item, dict) else False
                item_text = item.get("text", "") if isinstance(item, dict) else str(item)
                p = doc.add_paragraph()
                try:
                    p.style = doc.styles[_safe("List Paragraph", "Normal")]
                except Exception:
                    pass
                try:
                    pPr = p._p.get_or_add_pPr()
                    ind = OxmlElement("w:ind")
                    ind.set(qn("w:left"), "360")
                    ind.set(qn("w:hanging"), "360")
                    pPr.append(ind)
                except Exception:
                    pass
                sym_run = p.add_run("☑  " if checked else "☐  ")
                sym_run.font.size = Pt(11)
                sym_run.font.bold = checked
                sym_run.font.color.rgb = RGBColor(0x44, 0x72, 0xC4) if checked else RGBColor(0x60, 0x60, 0x60)
                _md_fill_para_inline(p, item_text)
                if checked:
                    for r in p.runs[1:]:
                        r.font.strike = True
                        r.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
            n_added += 1

        elif btype == "callout":
            _CALLOUT = {
                "info":    ("EBF3FB", "4472C4", "INFO"),
                "tip":     ("E8F5E9", "70AD47", "TIP"),
                "note":    ("FFF9E6", "FFC000", "NOTA"),
                "warning": ("FFF3CD", "ED7D31", "AVISO"),
                "error":   ("FDEDED", "C00000", "ERROR"),
                "success": ("E8F5E9", "70AD47", "OK"),
            }
            kind        = block.get("callout_type", block.get("kind", "info")).lower()
            fill_hex, border_hex, default_label = _CALLOUT.get(kind, _CALLOUT["info"])
            box_title   = block.get("title", default_label)
            box_text    = block.get("text", "")
            # Title paragraph with colored background and left bar
            def _shd_para(para, fill, border):
                try:
                    pp = para._p.get_or_add_pPr()
                    shd = OxmlElement("w:shd")
                    shd.set(qn("w:val"), "clear")
                    shd.set(qn("w:color"), "auto")
                    shd.set(qn("w:fill"), fill)
                    pp.append(shd)
                    pBdr = OxmlElement("w:pBdr")
                    left = OxmlElement("w:left")
                    left.set(qn("w:val"), "single")
                    left.set(qn("w:sz"), "24")
                    left.set(qn("w:space"), "8")
                    left.set(qn("w:color"), border)
                    pBdr.append(left)
                    pp.append(pBdr)
                    ind = OxmlElement("w:ind")
                    ind.set(qn("w:left"), "360")
                    pp.append(ind)
                    spc = OxmlElement("w:spacing")
                    spc.set(qn("w:before"), "60")
                    spc.set(qn("w:after"), "60")
                    pp.append(spc)
                except Exception:
                    pass
            pt = doc.add_paragraph()
            _shd_para(pt, fill_hex, border_hex)
            tr = pt.add_run(box_title)
            tr.bold = True
            tr.font.color.rgb = RGBColor(int(border_hex[:2], 16), int(border_hex[2:4], 16), int(border_hex[4:], 16))
            if box_text:
                pb = doc.add_paragraph()
                _shd_para(pb, fill_hex, border_hex)
                _md_fill_para_inline(pb, box_text)
                for r in pb.runs:
                    r.font.color.rgb = RGBColor(0x24, 0x24, 0x24)
            doc.add_paragraph()  # spacing after callout
            n_added += 1

        elif btype == "highlight":
            text      = block.get("text", "")
            bg_color  = block.get("color", "FFFF00").lstrip("#")
            txt_color = block.get("text_color", "000000").lstrip("#")
            p = doc.add_paragraph()
            try:
                pPr = p._p.get_or_add_pPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), bg_color)
                pPr.append(shd)
            except Exception:
                pass
            r = p.add_run(text)
            try:
                r.font.color.rgb = RGBColor(int(txt_color[:2], 16), int(txt_color[2:4], 16), int(txt_color[4:], 16))
            except Exception:
                pass
            n_added += 1

        elif btype == "toc":
            toc_title = block.get("title", "Tabla de contenido")
            p = doc.add_paragraph()
            try:
                p.style = doc.styles[_safe("Heading 1", "Normal")]
            except Exception:
                pass
            p.add_run(toc_title)
            try:
                para = doc.add_paragraph()
                fldChar1  = OxmlElement("w:fldChar")
                fldChar1.set(qn("w:fldCharType"), "begin")
                instrText = OxmlElement("w:instrText")
                instrText.set(qn("xml:space"), "preserve")
                instrText.text = ' TOC \\o "1-3" \\h \\z \\u '
                fldChar2  = OxmlElement("w:fldChar")
                fldChar2.set(qn("w:fldCharType"), "separate")
                fldChar3  = OxmlElement("w:fldChar")
                fldChar3.set(qn("w:fldCharType"), "end")
                r_fld = para._p.add_r()
                r_fld.append(fldChar1)
                r_fld.append(instrText)
                r_fld.append(fldChar2)
                r_fld.append(fldChar3)
                rp = para.add_run("[Actualiza con F9 en Word]")
                rp.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
                rp.font.size = Pt(10)
            except Exception:
                doc.add_paragraph("[Tabla de contenido — Ctrl+A, F9 para actualizar]")
            n_added += 1

        elif btype == "signature_block":
            roles = block.get("roles", ["Autor", "Revisor", "Aprobador"])
            doc.add_paragraph()
            n_r = len(roles) or 1
            tbl = doc.add_table(rows=3, cols=n_r)
            try:
                tbl.style = doc.styles[_safe("Table Grid")]
            except Exception:
                pass
            for c_i, role in enumerate(roles):
                tbl.rows[0].cells[c_i].text = role
                for run in tbl.rows[0].cells[c_i].paragraphs[0].runs:
                    run.bold = True
                sig_p = tbl.rows[1].cells[c_i].paragraphs[0]
                try:
                    spPr = sig_p._p.get_or_add_pPr()
                    spBdr = OxmlElement("w:pBdr")
                    sbot = OxmlElement("w:bottom")
                    sbot.set(qn("w:val"), "single")
                    sbot.set(qn("w:sz"), "8")
                    sbot.set(qn("w:space"), "1")
                    sbot.set(qn("w:color"), "CCCCCC")
                    spBdr.append(sbot)
                    spPr.append(spBdr)
                    sspc = OxmlElement("w:spacing")
                    sspc.set(qn("w:before"), "240")
                    spPr.append(sspc)
                except Exception:
                    pass
                dp = tbl.rows[2].cells[c_i].paragraphs[0]
                dp.add_run("Fecha: ")
            n_added += 1

    doc.save(str(out))
    return (
        f"✅ Documento creado: {out.name}\n"
        f"   Plantilla: {Path(template_path).name if template_path else 'en blanco'}\n"
        f"   Bloques añadidos: {n_added}\n"
        f"   Tamaño: {out.stat().st_size:,} bytes"
    )


def _tool_doc_add_content_block(args: dict) -> str:
    """Añade uno o más bloques de contenido a un .docx existente (sin borrar el contenido previo).

    Útil para añadir secciones, tablas o imágenes a un documento rellenado desde plantilla.
    Usa los mismos tipos de bloque que doc_create_from_template.
    """
    path           = Path(args.get("path", "")).expanduser()
    content_blocks = args.get("content_blocks", [])
    output_path    = args.get("output_path", "")

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    if not content_blocks:
        return "Parámetro requerido: content_blocks (lista de bloques)"

    # Reutiliza doc_create_from_template con clear_template_body=False
    dest = output_path or str(path)
    result = _tool_doc_create_from_template({
        "template_path": str(path),
        "output_path": dest,
        "content_blocks": content_blocks,
        "clear_template_body": False,
    })
    return result


def _tool_doc_set_page_layout(args: dict) -> str:
    """Configura el diseño de página de un .docx: tamaño, orientación y márgenes.

    page_size: A4 | Letter | Legal | A3 | custom
    orientation: portrait | landscape
    margins_cm: {"top": 2.5, "bottom": 2.5, "left": 3.0, "right": 2.5}
    """
    path        = Path(args.get("path", "")).expanduser()
    page_size   = args.get("page_size", "A4").upper()
    orientation = args.get("orientation", "portrait").lower()
    margins_cm  = args.get("margins_cm", {})
    output_path = args.get("output_path", "")

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        from docx import Document
        from docx.shared import Cm
        from docx.enum.section import WD_ORIENT

        _PAGE_SIZES = {
            "A4":     (21.0, 29.7),
            "A3":     (29.7, 42.0),
            "LETTER": (21.59, 27.94),
            "LEGAL":  (21.59, 35.56),
        }

        doc  = Document(str(path))
        sect = doc.sections[0]

        w_cm, h_cm = _PAGE_SIZES.get(page_size, (21.0, 29.7))
        if orientation == "landscape":
            w_cm, h_cm = h_cm, w_cm
            sect.orientation = WD_ORIENT.LANDSCAPE
        else:
            sect.orientation = WD_ORIENT.PORTRAIT

        sect.page_width  = Cm(w_cm)
        sect.page_height = Cm(h_cm)

        if margins_cm:
            if "top"    in margins_cm: sect.top_margin    = Cm(float(margins_cm["top"]))
            if "bottom" in margins_cm: sect.bottom_margin = Cm(float(margins_cm["bottom"]))
            if "left"   in margins_cm: sect.left_margin   = Cm(float(margins_cm["left"]))
            if "right"  in margins_cm: sect.right_margin  = Cm(float(margins_cm["right"]))

        dest = output_path or str(path)
        doc.save(dest)
        return (
            f"✅ Diseño de página actualizado: {Path(dest).name}\n"
            f"   Tamaño: {page_size} ({w_cm}×{h_cm} cm)  Orientación: {orientation}\n"
            f"   Márgenes: {margins_cm or 'sin cambios'}"
        )
    except ImportError:
        return "python-docx no disponible. Instala con: pip install python-docx"
    except Exception as exc:
        return f"Error configurando diseño de página: {exc}"


def _resource_templates_available() -> str:
    return _tool_doc_list_templates({})


def _resource_rfc_pending() -> str:
    cfg      = _load_config()
    notes_d  = Path(cfg["notes_dir"]).expanduser()
    if not notes_d.exists():
        return f"Directorio de notas no encontrado: {notes_d}"
    rfc_files = sorted(
        [f for f in notes_d.glob("*.md") if re.search(r"rfc|change.?request|cambio", f.stem, re.IGNORECASE)],
        key=lambda f: f.stat().st_mtime, reverse=True
    )[:20]
    if not rfc_files:
        return f"Sin RFCs/Change Requests en {notes_d}"
    lines = [f"📋 RFCs en {notes_d} — {len(rfc_files)} ficheros:"]
    for f in rfc_files:
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
        lines.append(f"  {mtime}  {f.name}")
    return "\n".join(lines)


def _resource_project_context() -> str:
    return _tool_project_context_read({})


def _resource_style_gallery() -> str:
    lines = [
        "🎨 Estilos O365 disponibles para doc_apply_style y doc_set_table_style:",
        "",
        "── Estilos de Párrafo ──────────────────────────────────────────",
        "  Normal              — Texto normal del cuerpo",
        "  Title               — Título de documento (grande, centrado)",
        "  Subtitle            — Subtítulo del documento",
        "  Heading 1           — Titular nivel 1 (H1)",
        "  Heading 2           — Titular nivel 2 (H2)",
        "  Heading 3           — Titular nivel 3 (H3)",
        "  Heading 4           — Titular nivel 4 (H4)",
        "  Quote               — Texto en cursiva/sangrado (cita)",
        "  Intense Quote       — Cita destacada con color de acento",
        "  List Paragraph      — Elemento de lista con sangrado",
        "  Caption             — Pie de figura/tabla (pequeño, cursiva)",
        "  No Spacing          — Texto sin espaciado extra",
        "  Body Text           — Texto de cuerpo alternativo",
        "  Body Text 2         — Cuerpo de texto compacto",
        "  Macro Text          — Para código/macros (mono)",
        "",
        "── Estilos de Tabla ────────────────────────────────────────────",
        "  Table Grid          — Tabla simple con bordes en todas las celdas",
        "  Light Shading       — Cabecera sombreada, sin bordes",
        "  Light Grid          — Fila de cabecera, bordes en columnas",
        "  Medium Shading 1    — Sombreado alternado de filas",
        "  Medium Grid 1       — Cabecera con fondo, bordes en todo",
        "  Dark List           — Cabecera oscura, filas alternas",
        "  Colorful Shading    — Sombreado colorido por columnas",
        "  Colorful Grid       — Bordes + sombreado colorido",
        "  Table Normal        — Sin formato (bordes invisibles)",
        "  Table Contemporary  — Estilo moderno, líneas horizontales",
        "",
        "Uso: doc_apply_style(path, style_map=[{search:'texto', style:'Heading 1'}])",
        "     doc_set_table_style(path, style='Medium Shading 1')",
    ]
    return "\n".join(lines)


def _resource_style_presets() -> str:
    import json
    presets = {
        "paragraph_styles": {
            "Title":      {"font": "Calibri Light", "size": 28, "bold": True,  "color": "#1F4E79", "align": "center"},
            "Subtitle":   {"font": "Calibri",       "size": 18, "bold": False, "color": "#2E74B5", "align": "center"},
            "Heading 1":  {"font": "Calibri Light", "size": 18, "bold": True,  "color": "#2E74B5", "align": "left"},
            "Heading 2":  {"font": "Calibri Light", "size": 14, "bold": True,  "color": "#2E74B5", "align": "left"},
            "Heading 3":  {"font": "Calibri",       "size": 12, "bold": True,  "color": "#1F4E79", "align": "left"},
            "Normal":     {"font": "Calibri",       "size": 11, "bold": False, "color": "#000000", "line_spacing": 1.15},
            "Caption":    {"font": "Calibri",       "size": 9,  "bold": False, "color": "#595959", "italic": True},
            "Quote":      {"font": "Calibri",       "size": 11, "bold": False, "color": "#404040", "italic": True},
            "Code":       {"font": "Consolas",      "size": 10, "bold": False, "color": "#262626"},
        },
        "table_styles": {
            "professional": {"style": "Medium Shading 1", "header_bold": True, "alternate_rows": True},
            "simple":       {"style": "Table Grid",       "header_bold": True, "alternate_rows": False},
            "minimal":      {"style": "Table Normal",     "header_bold": True, "alternate_rows": False},
            "colorful":     {"style": "Colorful Shading", "header_bold": True, "alternate_rows": True},
        },
    }
    return json.dumps(presets, ensure_ascii=False, indent=2)


def _resource_theme_colors() -> str:
    import json
    themes = {
        "office": {
            "primary": "#2E74B5", "secondary": "#1F4E79", "accent": "#ED7D31",
            "background": "#FFFFFF", "text": "#000000", "muted": "#595959",
            "success": "#70AD47", "warning": "#FFC000", "danger": "#FF0000",
        },
        "modern": {
            "primary": "#2F5496", "secondary": "#1F4E79", "accent": "#5B9BD5",
            "background": "#FFFFFF", "text": "#0D0D0D", "muted": "#666666",
            "success": "#548235", "warning": "#ED7D31", "danger": "#C00000",
        },
        "professional": {
            "primary": "#17375E", "secondary": "#0F2D4A", "accent": "#265F8B",
            "background": "#FFFFFF", "text": "#0D0D0D", "muted": "#555555",
            "success": "#375623", "warning": "#974706", "danger": "#843C0C",
        },
        "minimal": {
            "primary": "#404040", "secondary": "#595959", "accent": "#808080",
            "background": "#FFFFFF", "text": "#000000", "muted": "#A0A0A0",
            "success": "#505050", "warning": "#707070", "danger": "#303030",
        },
        "corporate": {
            "primary": "#003A70", "secondary": "#005599", "accent": "#0070C0",
            "background": "#FFFFFF", "text": "#000000", "muted": "#595959",
            "success": "#00703C", "warning": "#FF8200", "danger": "#CC0000",
        },
        "chart_palette": {
            "office":       ["#4472C4", "#ED7D31", "#A9D18E", "#FFC000", "#5B9BD5", "#70AD47"],
            "colorblind":   ["#0077BB", "#EE7733", "#009988", "#CC3311", "#33BBEE", "#EE3377"],
            "monochrome":   ["#000000", "#404040", "#808080", "#A0A0A0", "#C0C0C0", "#E0E0E0"],
            "pastel":       ["#AEC6CF", "#FFD1DC", "#B5EAD7", "#FFDAC1", "#C7CEEA", "#E2F0CB"],
        },
    }
    return json.dumps(themes, ensure_ascii=False, indent=2)


def _resource_font_combinations() -> str:
    import json
    combos = [
        {"name": "Office Classic",  "heading": "Calibri Light", "body": "Calibri",  "mono": "Consolas",     "use_case": "Documentos corporativos O365"},
        {"name": "Modern Clean",    "heading": "Calibri Light", "body": "Calibri",  "mono": "Courier New",  "use_case": "Presentaciones y informes modernos"},
        {"name": "Academic",        "heading": "Cambria",       "body": "Cambria",  "mono": "Courier New",  "use_case": "Documentos académicos y formales"},
        {"name": "Tech Report",     "heading": "Arial",         "body": "Arial",    "mono": "Consolas",     "use_case": "Documentación técnica y TI"},
        {"name": "Elegant",         "heading": "Garamond",      "body": "Georgia",  "mono": "Courier New",  "use_case": "Documentos ejecutivos y de dirección"},
        {"name": "Compact",         "heading": "Tahoma",        "body": "Tahoma",   "mono": "Lucida Console","use_case": "Informes compactos con mucha información"},
        {"name": "LibreOffice Safe","heading": "Liberation Sans","body": "Liberation Sans","mono": "Liberation Mono","use_case": "Máxima compatibilidad con LibreOffice"},
    ]
    return json.dumps(combos, ensure_ascii=False, indent=2)


def _resource_chart_types() -> str:
    import json
    chart_types = [
        {"name": "bar",            "use_case": "Comparar categorías (barras verticales agrupadas)", "multi_series": True},
        {"name": "column",         "use_case": "Columnas verticales",                               "multi_series": True},
        {"name": "stacked_bar",    "use_case": "Proporciones apiladas (horizontal)",                "multi_series": True},
        {"name": "stacked_column", "use_case": "Proporciones apiladas (vertical)",                  "multi_series": True},
        {"name": "line",           "use_case": "Tendencias temporales",                             "multi_series": True},
        {"name": "line_markers",   "use_case": "Tendencias con marcadores en cada punto",           "multi_series": True},
        {"name": "area",           "use_case": "Áreas acumuladas / volumen",                        "multi_series": True},
        {"name": "pie",            "use_case": "Distribución porcentual",                           "multi_series": False},
        {"name": "doughnut",       "use_case": "Distribución porcentual con hueco central",         "multi_series": False},
        {"name": "scatter",        "use_case": "Correlación X/Y (series con x_values/y_values)",     "multi_series": True},
        {"name": "radar",          "use_case": "Comparar perfiles multidimensionales (≤8 ejes)",    "multi_series": True},
    ]
    return json.dumps({
        "word_insert_chart": {
            "tool": "insert_chart",
            "note": "Gráfica OOXML NATIVA en .docx (objeto editable de Word, vectorial). Crea el documento si no existe.",
            "data_format": {"categories": ["..."], "series": [{"label": "...", "values": ["..."]}]},
            "chart_types": chart_types,
        },
        "excel_chart": {
            "tool": "xlsx_insert_chart",
            "note": "Gráfica nativa de openpyxl anclada a un rango de celdas en .xlsx.",
            "chart_types": ["bar", "line", "pie", "area", "scatter"],
            "key_params": ["path", "sheet", "data_range", "chart_type", "position"],
        },
        "pptx_chart": {
            "tool": "pptx_insert_chart",
            "note": "Gráfica nativa en una diapositiva .pptx.",
            "chart_types": ["bar", "column", "line", "pie"],
        },
    }, ensure_ascii=False, indent=2)


# ── Tools registry ──────────────────────────────────────────────────────────────

_TOOLS = [{'name': 'doc_convert',
  'description': 'Convierte documentos entre formatos usando pandoc (md↔docx, md→pdf, html→md, '
                 'etc.).',
  'inputSchema': {'type': 'object',
                  'properties': {'input_path': {'type': 'string',
                                                'description': 'Ruta al fichero de entrada'},
                                 'output_format': {'type': 'string',
                                                   'description': 'Formato de salida: pdf, docx, '
                                                                  'html, md, odt, rst, epub'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta del fichero de salida '
                                                                '(opcional; por defecto mismo '
                                                                'nombre con nueva extensión)'}},
                  'required': ['input_path', 'output_format']}},
 {'name': 'pdf_extract_text',
  'description': 'Extrae texto de un PDF. Usa pdftotext (poppler) o pdfplumber.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero PDF'},
                                 'pages': {'type': 'string',
                                           'description': "Rango de páginas, p.ej. '1-5' "
                                                          '(opcional)'}},
                  'required': ['path']}},
 {'name': 'doc_word_count',
  'description': 'Cuenta palabras, líneas, caracteres y párrafos de un documento de texto.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta al fichero (txt, md, rst, html…)'}},
                  'required': ['path']}},
 {'name': 'image_to_text',
  'description': 'Extrae texto de una imagen usando tesseract OCR. Requiere tesseract instalado.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta a la imagen (PNG, JPG, TIFF…)'},
                                 'lang': {'type': 'string',
                                          'description': "Idiomas tesseract, p.ej. 'spa+eng'. "
                                                         'Default: spa+eng'}},
                  'required': ['path']}},
 {'name': 'doc_read_template_fields',
  'description': 'Extrae los campos {{CAMPO}} de una plantilla .docx, .md o .txt. Útil para saber '
                 'qué datos rellenar antes de usar doc_fill_template.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta a la plantilla (.docx, .md, .txt, '
                                                         '.html)'}},
                  'required': ['path']}},
 {'name': 'doc_fill_template',
  'description': 'Rellena una plantilla .docx/.xlsx/.pptx o texto con valores de campos. Motor '
                 'primario: docxtpl (Jinja2 — soporta {{ campo }}, loops y condicionales, preserva '
                 'estilos). Fallback automático a python-docx para plantillas con {{CAMPO}} sin '
                 'Jinja2. Para .xlsx usa openpyxl; para .pptx usa python-pptx. NOTA: Para '
                 'plantillas corporativas con {{CAMPO}} y estilos avanzados (portada, TOC, pie de '
                 'página), usa doc_fill_corporate_template que garantiza preservación 100% del '
                 'formato.',
  'inputSchema': {'type': 'object',
                  'properties': {'template_path': {'type': 'string',
                                                   'description': 'Ruta a la plantilla (.docx, '
                                                                  '.dotx, .xlsx, .pptx, .md, '
                                                                  '.txt)'},
                                 'fields': {'type': 'object',
                                            'description': 'Objeto JSON con {campo: valor}. Se '
                                                           'proveen automáticamente en mayúsculas '
                                                           'y minúsculas. Ej: {"nombre": "Juan", '
                                                           '"fecha": "2026-05-21"}'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta del fichero de salida '
                                                                '(opcional; añade timestamp por '
                                                                'defecto)'},
                                 'use_jinja': {'type': 'boolean',
                                               'description': 'Usar motor Jinja2/docxtpl (default: '
                                                              'true). Pon false solo si la '
                                                              'plantilla tiene sintaxis custom '
                                                              'no-Jinja.'}},
                  'required': ['template_path', 'fields']}},
 {'name': 'doc_fill_corporate_template',
  'description': 'Rellena una plantilla .docx corporativa preservando AL 100% los estilos, '
                 'imágenes, fondos, tablas, cabeceras, pies de página y layout originales. Usa '
                 'manipulación XML directa (ZIP+lxml) para sanear placeholders {{CAMPO}} partidos '
                 'entre runs de Word, reemplazar en cuerpo/tablas/cabeceras/pies/cuadros de texto, '
                 'y marcar el TOC para que Word lo actualice al abrir. Para contenido '
                 'multipárrafo: proporciona el valor como lista de strings o string con \\n\\n '
                 'entre párrafos. FLUJO RECOMENDADO: 1) doc_read_template_fields → 2) '
                 'doc_fill_corporate_template. USAR SIEMPRE para plantillas corporativas (.docx) '
                 'con portada, TOC o estilos de empresa.',
  'inputSchema': {'type': 'object',
                  'properties': {'template_path': {'type': 'string',
                                                   'description': 'Ruta absoluta a la plantilla '
                                                                  '.docx o .dotx corporativa'},
                                 'fields': {'type': 'object',
                                            'description': 'Diccionario de campos a rellenar. '
                                                           'Claves = nombres de los {{CAMPO}} (sin '
                                                           'llaves). Valores = string para una '
                                                           'línea, lista de strings para múltiples '
                                                           'párrafos, o string con \\n\\n como '
                                                           'separador de párrafos. Ejemplo: '
                                                           '{"TITULO": "Documento de Análisis", '
                                                           '"PROYECTO": "MiProyecto", "FECHA": '
                                                           '"2026-05-28", "CONTENIDO_SECCION_1": '
                                                           '["Intro párrafo 1.", "Intro párrafo '
                                                           '2."]}'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta de salida del documento '
                                                                'rellenado (opcional; añade '
                                                                'timestamp al nombre por defecto)'},
                                 'update_toc': {'type': 'boolean',
                                                'description': 'Marcar el TOC para que Word lo '
                                                               'recalcule al abrir (default: '
                                                               'true). Requiere abrir el .docx en '
                                                               'Word/LibreOffice.'}},
                  'required': ['template_path', 'fields']}},
 {'name': 'doc_create',
  'description': 'Crea un documento Word (.docx), Excel (.xlsx) o PowerPoint (.pptx) profesional '
                 'con estilos O365 nativos (Calibri/Calibri Light, colores Office, OOXML nativo). '
                 'Para .docx usa SIEMPRE content_blocks para contenido nativo (title, heading, '
                 'paragraph, bullet_list, numbered_list, table, chart OOXML, image, checklist, '
                 'callout, highlight, toc, signature_block, code_block, pagebreak, '
                 'horizontal_rule). El parámetro markdown solo vuelca texto plano como párrafos '
                 '(énfasis inline **/*); no genera estructura. Con template_path hereda todos los '
                 'estilos, cabecera/pie y márgenes corporativos. Para .xlsx: hojas con tablas '
                 'nativas, gráficas O365 y formatos condicionales. Para .pptx: diapositivas con '
                 'temas, gráficas nativas y layouts.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta de salida del documento '
                                                         '(.docx/.xlsx/.pptx)'},
                                 'title': {'type': 'string',
                                           'description': 'Título del documento '
                                                          '(portada/hoja/presentación)'},
                                 'subtitle': {'type': 'string',
                                              'description': 'Subtítulo (solo .docx y .pptx)'},
                                 'theme': {'type': 'string',
                                           'description': 'Tema de color: office (default) | '
                                                          'modern | professional | minimal | '
                                                          'corporate | dark'},
                                 'template_path': {'type': 'string',
                                                   'description': 'Plantilla corporativa '
                                                                  '.docx/.dotx para heredar '
                                                                  'estilos, fuentes, cabecera/pie '
                                                                  'y márgenes. El contenido blocks '
                                                                  'se añade conservando el formato '
                                                                  'de la plantilla.'},
                                 'markdown': {'type': 'string',
                                              'description': 'Contenido markdown para .docx. Se '
                                                             'convierte a Word OOXML completo '
                                                             '(estilos, tablas, listas, imágenes '
                                                             'inline).'},
                                 'content_blocks': {'type': 'array',
                                                    'description': 'Bloques O365 nativos para '
                                                                   '.docx. Tipos: title, heading, '
                                                                   'paragraph, bullet_list, '
                                                                   'numbered_list, table, chart '
                                                                   '(DrawingML OOXML nativo — NO '
                                                                   'matplotlib), image, checklist, '
                                                                   'callout, highlight, toc, '
                                                                   'signature_block, code_block, '
                                                                   'markdown, pagebreak, '
                                                                   'horizontal_rule.',
                                                    'items': {'type': 'object'}},
                                 'sheets': {'type': 'array',
                                            'description': 'Hojas Excel para .xlsx. Cada hoja: '
                                                           '{name, title, headers, rows, charts, '
                                                           'conditional_formats}',
                                            'items': {'type': 'object'}},
                                 'slides': {'type': 'array',
                                            'description': 'Diapositivas para .pptx. Cada slide: '
                                                           '{title, content, layout, notes, '
                                                           'blocks}',
                                            'items': {'type': 'object'}},
                                 'metadata': {'type': 'object',
                                              'description': 'Metadatos del documento Word: '
                                                             '{author, subject, company, '
                                                             'keywords}'}},
                  'required': ['path']}},
 {'name': 'doc_list_templates',
  'description': 'Lista las plantillas de documentos disponibles (.docx, .xlsx, .md) en el '
                 'directorio de plantillas configurado.',
  'inputSchema': {'type': 'object',
                  'properties': {'directory': {'type': 'string',
                                               'description': 'Directorio de plantillas (por '
                                                              'defecto: templates_dir en '
                                                              'config)'}}}},
 {'name': 'doc_create_rfc',
  'description': 'Genera un documento RFC/Request for Change estructurado para cambios de '
                 'infraestructura IT. Por defecto genera .docx (usando pandoc o python-docx); usa '
                 "format='md' para markdown.",
  'inputSchema': {'type': 'object',
                  'properties': {'title': {'type': 'string', 'description': 'Título del cambio'},
                                 'requester': {'type': 'string',
                                               'description': 'Nombre del solicitante'},
                                 'date': {'type': 'string',
                                          'description': 'Fecha de solicitud (YYYY-MM-DD). '
                                                         'Default: hoy'},
                                 'priority': {'type': 'string',
                                              'description': 'Prioridad: Alta/Media/Baja. Default: '
                                                             'Media'},
                                 'change_type': {'type': 'string',
                                                 'description': 'Tipo: Normal/Estándar/Urgente. '
                                                                'Default: Normal'},
                                 'affected_systems': {'type': 'string',
                                                      'description': 'Sistemas/servidores '
                                                                     'afectados'},
                                 'description': {'type': 'string',
                                                 'description': 'Descripción detallada del cambio'},
                                 'justification': {'type': 'string',
                                                   'description': 'Justificación y beneficios'},
                                 'risk': {'type': 'string',
                                          'description': 'Descripción de riesgos identificados'},
                                 'risk_level': {'type': 'string',
                                                'description': 'Nivel de riesgo: Alto/Medio/Bajo. '
                                                               'Default: Bajo'},
                                 'rollback_plan': {'type': 'string',
                                                   'description': 'Plan de marcha atrás'},
                                 'testing_plan': {'type': 'string',
                                                  'description': 'Plan de pruebas '
                                                                 'post-implementación'},
                                 'implementation_steps': {'type': 'string',
                                                          'description': 'Pasos de implementación'},
                                 'scheduled_date': {'type': 'string',
                                                    'description': 'Fecha programada del cambio'},
                                 'scheduled_window': {'type': 'string',
                                                      'description': 'Ventana de mantenimiento'},
                                 'approver': {'type': 'string',
                                              'description': 'Nombre del aprobador'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta del fichero de salida (la '
                                                                'extensión puede ser .docx o .md). '
                                                                'Si se omite, se guarda '
                                                                'automáticamente en notes_dir.'},
                                 'format': {'type': 'string',
                                            'description': "Formato de salida: 'docx' (default) o "
                                                           "'md'. Con 'docx' requiere pandoc o "
                                                           'python-docx; si no están disponibles '
                                                           'cae a .md.'}},
                  'required': ['title', 'requester']}},
 {'name': 'project_context_read',
  'description': 'Lee el fichero OOCODE.md del directorio de trabajo y devuelve metadatos del '
                 'proyecto (cliente, tipo, naming, directorios) junto con el cuerpo completo.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta al OOCODE.md (opcional; por '
                                                         'defecto: OOCODE.md en cwd)'}}}},
 {'name': 'project_init_office',
  'description': 'Inicializa la estructura de directorios para un proyecto IT/oficina: crea '
                 'OOCODE.md, subdirectorios (docs/rfcs, docs/reports, etc.), cmdb.csv y '
                 'risk_register.csv.',
  'inputSchema': {'type': 'object',
                  'properties': {'project': {'type': 'string',
                                             'description': 'Nombre del proyecto'},
                                 'client': {'type': 'string', 'description': 'Cliente o empresa'},
                                 'project_type': {'type': 'string',
                                                  'description': 'Tipo: IT/DC/Cloud/Infra/General. '
                                                                 'Default: IT'},
                                 'naming': {'type': 'string',
                                            'description': 'Patrón de nombres: p.ej. '
                                                           '{CLIENT}-{TYPE}-{YYMMDD}-v{VER}'},
                                 'templates_dir': {'type': 'string',
                                                   'description': 'Directorio de plantillas '
                                                                  'relativo al proyecto '
                                                                  '(opcional)'},
                                 'directory': {'type': 'string',
                                               'description': 'Directorio donde crear el proyecto '
                                                              '(por defecto: cwd)'}},
                  'required': ['project']}},
 {'name': 'doc_project_save',
  'description': 'Guarda un documento en el subdirectorio correcto del proyecto (docs/rfcs, '
                 'docs/reports, docs/incidents…). Los tipos formales (rfc, report, meeting, plan, '
                 "incident) usan .docx por defecto; 'general' usa .md.",
  'inputSchema': {'type': 'object',
                  'properties': {'content': {'type': 'string',
                                             'description': 'Contenido del documento en markdown o '
                                                            'texto'},
                                 'doc_type': {'type': 'string',
                                              'description': 'Tipo: '
                                                             'rfc/change_request/report/informe/meeting/acta/incident/incidencia/plan/migration/general'},
                                 'filename': {'type': 'string',
                                              'description': 'Nombre de fichero completo (con '
                                                             'extensión). Si se omite se genera '
                                                             'automáticamente con naming '
                                                             'convention.'},
                                 'ext': {'type': 'string',
                                         'description': 'Extensión cuando no se da filename: '
                                                        "'.docx' (default para tipos formales) o "
                                                        "'.md'"},
                                 'directory': {'type': 'string',
                                               'description': 'Directorio base del proyecto (por '
                                                              'defecto: cwd/docs)'}},
                  'required': ['content', 'doc_type']}},
 {'name': 'doc_read',
  'description': 'Lee el contenido de un documento .docx o .md. Opcionalmente extrae sólo una '
                 'sección por su encabezado.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta al documento (.docx o .md)'},
                                 'section': {'type': 'string',
                                             'description': 'Encabezado de sección a extraer '
                                                            '(opcional; sin él devuelve todo)'},
                                 'max_chars': {'type': 'integer',
                                               'description': 'Límite de caracteres devueltos. '
                                                              'Default: 8000'}},
                  'required': ['path']}},
 {'name': 'doc_update_section',
  'description': 'Reemplaza el contenido de una sección (identificada por su encabezado) en un '
                 'documento .md o .docx. Para .md hace edición nativa; para .docx requiere '
                 'python-docx.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta al documento (.md o .docx)'},
                                 'section': {'type': 'string',
                                             'description': 'Texto exacto del encabezado de la '
                                                            'sección a reemplazar'},
                                 'new_content': {'type': 'string',
                                                 'description': 'Nuevo contenido de la sección '
                                                                '(markdown o texto)'}},
                  'required': ['path', 'section', 'new_content']}},
 {'name': 'doc_version_bump',
  'description': 'Incrementa la versión de un documento .md con front matter YAML (version: X.Y.Z) '
                 'o que contenga vX.Y en sus primeras líneas.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al documento .md'},
                                 'bump': {'type': 'string',
                                          'description': 'Parte a incrementar: major/minor/patch. '
                                                         'Default: patch'}},
                  'required': ['path']}},
 {'name': 'doc_create_from_template',
  'description': 'Crea un .docx NUEVO desde plantilla corporativa (.docx/.dotx), heredando '
                 'estilos, fuentes, cabecera/pie, logo y márgenes. Soporta TODOS los block types: '
                 'heading, paragraph, bullet_list, numbered_list, table, chart (OOXML nativo), '
                 'image, checklist, callout, highlight, toc, signature_block, code_block, '
                 'markdown, pagebreak, horizontal_rule. USAR SIEMPRE cuando el usuario tiene '
                 'plantillas corporativas.',
  'inputSchema': {'type': 'object',
                  'properties': {'template_path': {'type': 'string',
                                                   'description': 'Ruta a la plantilla .docx o '
                                                                  '.dotx de la empresa'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta del fichero de salida .docx'},
                                 'content_blocks': {'type': 'array',
                                                    'description': 'Lista de bloques de contenido '
                                                                   'O365 nativos. Tipos: heading, '
                                                                   'paragraph, bullet_list, '
                                                                   'numbered_list, table, chart, '
                                                                   'image, checklist, callout, '
                                                                   'highlight, toc, '
                                                                   'signature_block, code_block, '
                                                                   'markdown, pagebreak, '
                                                                   'horizontal_rule'},
                                 'fields': {'type': 'object',
                                            'description': 'Campos Jinja2 para rellenar la '
                                                           'plantilla antes de añadir bloques (ej: '
                                                           "{NOMBRE: 'Juan', FECHA: '2024-01'})"},
                                 'clear_template_body': {'type': 'boolean',
                                                         'description': 'Limpiar el cuerpo antes '
                                                                        'de añadir bloques (para '
                                                                        '.dotx siempre se limpia). '
                                                                        'Default: false'}},
                  'required': ['output_path', 'content_blocks']}},
 {'name': 'doc_add_content_block',
  'description': 'Añade bloques de contenido a un .docx EXISTENTE sin borrar el contenido previo. '
                 'Útil para añadir secciones a un documento rellenado desde plantilla.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta al .docx existente'},
                                 'content_blocks': {'type': 'array',
                                                    'description': 'Lista de bloques a añadir '
                                                                   '(mismos tipos que '
                                                                   'doc_create_from_template)'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta de salida (omitir = '
                                                                'sobreescribe el original)'}},
                  'required': ['path', 'content_blocks']}},
 {'name': 'doc_set_page_layout',
  'description': 'Configura el diseño de página de un .docx: tamaño (A4/Letter/Legal/A3), '
                 'orientación (portrait/landscape) y márgenes en cm.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .docx'},
                                 'page_size': {'type': 'string',
                                               'description': 'Tamaño: A4 (default), Letter, '
                                                              'Legal, A3'},
                                 'orientation': {'type': 'string',
                                                 'description': 'portrait (default) | landscape'},
                                 'margins_cm': {'type': 'object',
                                                'description': 'Márgenes en cm: {top, bottom, '
                                                               'left, right}. Ej: {top:2.5, '
                                                               'bottom:2.5, left:3.0, right:2.5}'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta de salida (omitir = '
                                                                'sobreescribe el original)'}},
                  'required': ['path']}},
 {'name': 'doc_embed_image',
  'description': 'Inserta una imagen (PNG/JPG) en un documento .docx existente, con pie de figura '
                 'opcional.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .docx'},
                                 'image_path': {'type': 'string',
                                                'description': 'Ruta a la imagen (PNG/JPG/EMF)'},
                                 'caption': {'type': 'string',
                                             'description': 'Texto del pie de figura (opcional)'},
                                 'width_inches': {'type': 'number',
                                                  'description': 'Ancho de la imagen en pulgadas. '
                                                                 'Default: 5.0'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta de salida (omitir = '
                                                                'sobreescribe el original)'}},
                  'required': ['path', 'image_path']}},
 {'name': 'insert_chart',
  'description': 'Inserta una gráfica OOXML nativa (objeto editable de Word, vectorial) en un '
                 '.docx. Crea el documento si no existe. Tipos: bar, column, line, line_markers, '
                 'area, pie, doughnut, scatter, stacked_bar, stacked_column, radar.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta al fichero .docx (se crea con '
                                                         'estilos O365 si no existe)'},
                                 'chart_type': {'type': 'string',
                                                'description': 'bar | column | line | line_markers '
                                                               '| area | pie | doughnut | scatter '
                                                               '| stacked_bar | stacked_column | '
                                                               'radar'},
                                 'data': {'type': 'object',
                                          'description': '{categories:[...], series:[{label, '
                                                         'values:[...]}]}. Para scatter: series '
                                                         'con {x_values, y_values}. También acepta '
                                                         'data.values=[...] como serie única.'},
                                 'title': {'type': 'string', 'description': 'Título de la gráfica'},
                                 'width_inches': {'type': 'number',
                                                  'description': 'Ancho en pulgadas (default: '
                                                                 '5.5)'},
                                 'height_inches': {'type': 'number',
                                                   'description': 'Alto en pulgadas (default: '
                                                                  '3.5)'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta de salida (omitir = '
                                                                'sobreescribe el original)'}},
                  'required': ['path', 'chart_type', 'data']}},
 {'name': 'doc_apply_style',
  'description': 'Aplica estilos de párrafo O365 a un .docx (Heading 1, Heading 2, Normal, Title, '
                 'Quote, etc.).',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .docx'},
                                 'style_map': {'type': 'array',
                                               'description': "Reglas: [{search: 'texto', style: "
                                                              "'Heading 1'} | {paragraph: 0, "
                                                              "style: 'Title'}]"},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta de salida (omitir = '
                                                                'sobreescribe el original)'}},
                  'required': ['path', 'style_map']}},
 {'name': 'doc_set_table_style',
  'description': 'Aplica un estilo de tabla O365 a todas o una tabla específica de un .docx.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .docx'},
                                 'style': {'type': 'string',
                                           'description': "Nombre del estilo: 'Table Grid', 'Light "
                                                          "Shading', 'Medium Shading 1', 'Dark "
                                                          "List', etc."},
                                 'table_index': {'type': 'integer',
                                                 'description': 'Índice de la tabla (0-based); -1 '
                                                                '= todas (default: -1)'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta de salida (omitir = '
                                                                'sobreescribe el original)'}},
                  'required': ['path']}},
 {'name': 'doc_extract_metadata',
  'description': 'Extrae metadatos de un .docx, .pptx o .pdf: autor, título, fechas de '
                 'creación/modificación, etc.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta al fichero (.docx, .pptx, .pdf)'}},
                  'required': ['path']}},
 {'name': 'doc_compare',
  'description': 'Compara el texto de dos documentos (.docx, .pptx o .md) y devuelve un diff '
                 'unificado.',
  'inputSchema': {'type': 'object',
                  'properties': {'path_a': {'type': 'string',
                                            'description': 'Ruta al primer documento'},
                                 'path_b': {'type': 'string',
                                            'description': 'Ruta al segundo documento'},
                                 'context': {'type': 'integer',
                                             'description': 'Líneas de contexto en el diff '
                                                            '(default: 3)'}},
                  'required': ['path_a', 'path_b']}},
 {'name': 'set_paragraph_format',
  'description': 'Formatea un párrafo específico de un .docx: fuente, tamaño, color, negrita, '
                 'alineación, espaciado.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .docx'},
                                 'paragraph_index': {'type': 'integer',
                                                     'description': 'Índice del párrafo (0 = '
                                                                    'primero)'},
                                 'font_name': {'type': 'string',
                                               'description': 'Nombre de fuente: Calibri, Arial, '
                                                              'Times New Roman'},
                                 'font_size': {'type': 'number',
                                               'description': 'Tamaño en puntos: 10, 11, 12, 14, '
                                                              '16, 18'},
                                 'color': {'type': 'string',
                                           'description': "Color hexadecimal: '#2E74B5' o "
                                                          "'#000000'"},
                                 'bold': {'type': 'boolean', 'description': 'Negrita'},
                                 'italic': {'type': 'boolean', 'description': 'Cursiva'},
                                 'underline': {'type': 'boolean', 'description': 'Subrayado'},
                                 'alignment': {'type': 'string',
                                               'description': 'Alineación: '
                                                              'left|center|right|justify'},
                                 'space_before': {'type': 'number',
                                                  'description': 'Espacio antes del párrafo en '
                                                                 'puntos'},
                                 'space_after': {'type': 'number',
                                                 'description': 'Espacio después del párrafo en '
                                                                'puntos'},
                                 'line_spacing': {'type': 'number',
                                                  'description': 'Interlineado: 1.0, 1.15, 1.5, '
                                                                 '2.0'},
                                 'style': {'type': 'string',
                                           'description': 'Estilo de párrafo: Normal, Heading 1, '
                                                          'etc.'}},
                  'required': ['path', 'paragraph_index']}},
 {'name': 'apply_document_theme',
  'description': 'Aplica un tema de colores y fuentes '
                 '(office/modern/professional/minimal/corporate) a todos los estilos de un .docx.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .docx'},
                                 'theme': {'type': 'string',
                                           'description': 'Tema: '
                                                          'office|modern|professional|minimal|corporate'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta de salida (default: '
                                                                'sobreescribe el original)'}},
                  'required': ['path', 'theme']}},
 {'name': 'doc_add_header_footer',
  'description': 'Añade cabecera y/o pie de página a un documento .docx, con número de página '
                 'opcional.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .docx'},
                                 'header': {'type': 'string',
                                            'description': 'Texto de la cabecera'},
                                 'footer': {'type': 'string',
                                            'description': 'Texto del pie de página'},
                                 'page_number': {'type': 'boolean',
                                                 'description': 'Incluir número de página en el '
                                                                'pie'},
                                 'alignment': {'type': 'string',
                                               'description': 'Alineación: left|center|right'},
                                 'font_size': {'type': 'number',
                                               'description': 'Tamaño de fuente en puntos '
                                                              '(default: 10)'}},
                  'required': ['path']}},
 {'name': 'doc_add_toc',
  'description': 'Inserta una Tabla de Contenidos (TOC) al inicio de un .docx basada en los '
                 'estilos Heading.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .docx'},
                                 'title': {'type': 'string',
                                           'description': "Título de la TOC (default: 'Tabla de "
                                                          "Contenidos')"},
                                 'max_level': {'type': 'integer',
                                               'description': 'Nivel máximo de headings a incluir '
                                                              '(default: 3)'}},
                  'required': ['path']}}]


_TOOL_FNS: dict[str, Any] = {
    'doc_convert'                 : _tool_doc_convert,
    'pdf_extract_text'            : _tool_pdf_extract_text,
    'doc_word_count'              : _tool_doc_word_count,
    'image_to_text'               : _tool_image_to_text,
    'doc_read_template_fields'    : _tool_doc_read_template_fields,
    'doc_fill_template'           : _tool_doc_fill_template,
    'doc_fill_corporate_template' : _tool_doc_fill_corporate_template,
    'doc_create'                  : _tool_doc_create,
    'doc_list_templates'          : _tool_doc_list_templates,
    'doc_create_rfc'              : _tool_doc_create_rfc,
    'project_context_read'        : _tool_project_context_read,
    'project_init_office'         : _tool_project_init_office,
    'doc_project_save'            : _tool_doc_project_save,
    'doc_read'                    : _tool_doc_read,
    'doc_update_section'          : _tool_doc_update_section,
    'doc_version_bump'            : _tool_doc_version_bump,
    'doc_create_from_template'    : _tool_doc_create_from_template,
    'doc_add_content_block'       : _tool_doc_add_content_block,
    'doc_set_page_layout'         : _tool_doc_set_page_layout,
    'doc_embed_image'             : _tool_doc_embed_image,
    'insert_chart'                : _tool_doc_insert_chart_native,
    'doc_apply_style'             : _tool_doc_apply_style,
    'doc_set_table_style'         : _tool_doc_set_table_style,
    'doc_extract_metadata'        : _tool_doc_extract_metadata,
    'doc_compare'                 : _tool_doc_compare,
    'set_paragraph_format'        : _tool_set_paragraph_format,
    'apply_document_theme'        : _tool_apply_document_theme,
    'doc_add_header_footer'       : _tool_doc_add_header_footer,
    'doc_add_toc'                 : _tool_doc_add_toc,
}



# ── Prompts ─────────────────────────────────────────────────────────────────────

_PROMPTS: dict[str, dict] = {'summarize_document': {'description': 'Resume un documento con puntos clave, decisiones y '
                                       'acciones requeridas.',
                        'arguments': [{'name': 'content',
                                       'description': 'Texto del documento a resumir',
                                       'required': True},
                                      {'name': 'max_words',
                                       'description': 'Longitud máxima del resumen en palabras',
                                       'required': False},
                                      {'name': 'focus',
                                       'description': "Aspecto en el que enfocarse (p.ej. 'puntos "
                                                      "de acción')",
                                       'required': False}]},
 'weekly_report': {'description': 'Genera un informe semanal de actividades con resumen, logros y '
                                  'próximos pasos.',
                   'arguments': [{'name': 'completed',
                                  'description': 'Tareas completadas esta semana',
                                  'required': True},
                                 {'name': 'in_progress',
                                  'description': 'Tareas en progreso',
                                  'required': False},
                                 {'name': 'next_week',
                                  'description': 'Plan para la próxima semana',
                                  'required': False},
                                 {'name': 'blockers',
                                  'description': 'Bloqueos o problemas',
                                  'required': False}]},
 'datacenter_migration_report': {'description': 'Genera un informe técnico formal de migración de '
                                                'centro de datos con fases, inventario y '
                                                'resultados.',
                                 'arguments': [{'name': 'project_name',
                                                'description': 'Nombre del proyecto de migración',
                                                'required': True},
                                               {'name': 'source_dc',
                                                'description': 'Centro de datos o entorno origen',
                                                'required': True},
                                               {'name': 'target_dc',
                                                'description': 'Centro de datos o entorno destino',
                                                'required': True},
                                               {'name': 'systems',
                                                'description': 'Lista de sistemas/servidores '
                                                               'migrados',
                                                'required': True},
                                               {'name': 'date',
                                                'description': 'Fecha de la migración (YYYY-MM-DD)',
                                                'required': False},
                                               {'name': 'team',
                                                'description': 'Equipo o responsables',
                                                'required': False},
                                               {'name': 'issues',
                                                'description': 'Incidencias ocurridas durante la '
                                                               'migración',
                                                'required': False},
                                               {'name': 'result',
                                                'description': 'Resultado: exitoso / parcial / '
                                                               'fallido',
                                                'required': False}]},
 'rfc_change_request': {'description': 'Genera un RFC/Change Request completo y formal para '
                                       'cambios de infraestructura IT.',
                        'arguments': [{'name': 'title',
                                       'description': 'Título del cambio',
                                       'required': True},
                                      {'name': 'requester',
                                       'description': 'Nombre del solicitante',
                                       'required': True},
                                      {'name': 'description',
                                       'description': 'Descripción detallada del cambio',
                                       'required': True},
                                      {'name': 'affected_systems',
                                       'description': 'Sistemas o servicios afectados',
                                       'required': True},
                                      {'name': 'risk_level',
                                       'description': 'Nivel de riesgo: Alto/Medio/Bajo',
                                       'required': False},
                                      {'name': 'rollback_plan',
                                       'description': 'Plan de marcha atrás',
                                       'required': False},
                                      {'name': 'scheduled_date',
                                       'description': 'Fecha y ventana de mantenimiento',
                                       'required': False}]},
 'server_migration_plan': {'description': 'Genera un plan detallado de migración de servidor con '
                                          'checklist, validaciones y rollback.',
                           'arguments': [{'name': 'server_name',
                                          'description': 'Nombre o hostname del servidor',
                                          'required': True},
                                         {'name': 'source_env',
                                          'description': 'Entorno/infraestructura origen',
                                          'required': True},
                                         {'name': 'target_env',
                                          'description': 'Entorno/infraestructura destino',
                                          'required': True},
                                         {'name': 'services',
                                          'description': 'Servicios o aplicaciones en el servidor',
                                          'required': False},
                                         {'name': 'downtime_window',
                                          'description': 'Ventana de mantenimiento',
                                          'required': False},
                                         {'name': 'dependencies',
                                          'description': 'Dependencias del servidor',
                                          'required': False}]},
 'it_incident_report': {'description': 'Genera un informe post-incidencia IT (Post-Mortem) con '
                                       'RCA, timeline y plan de acción preventivo.',
                        'arguments': [{'name': 'title',
                                       'description': 'Título de la incidencia',
                                       'required': True},
                                      {'name': 'severity',
                                       'description': 'Severidad: Crítica/Alta/Media/Baja',
                                       'required': True},
                                      {'name': 'start_time',
                                       'description': 'Fecha/hora de inicio del incidente',
                                       'required': True},
                                      {'name': 'end_time',
                                       'description': 'Fecha/hora de resolución',
                                       'required': False},
                                      {'name': 'affected',
                                       'description': 'Sistemas y usuarios afectados',
                                       'required': False},
                                      {'name': 'root_cause',
                                       'description': 'Causa raíz identificada',
                                       'required': False},
                                      {'name': 'timeline',
                                       'description': 'Cronología de eventos clave',
                                       'required': False},
                                      {'name': 'actions_taken',
                                       'description': 'Acciones tomadas para resolverlo',
                                       'required': False},
                                      {'name': 'preventive',
                                       'description': 'Medidas preventivas propuestas',
                                       'required': False}]},
 'infrastructure_change_plan': {'description': 'Genera un plan de cambio de infraestructura con '
                                               'análisis de impacto, fases, riesgos y '
                                               'aprobaciones.',
                                'arguments': [{'name': 'project',
                                               'description': 'Nombre del proyecto/cambio',
                                               'required': True},
                                              {'name': 'requester',
                                               'description': 'Responsable del proyecto',
                                               'required': True},
                                              {'name': 'objective',
                                               'description': 'Objetivo del cambio',
                                               'required': True},
                                              {'name': 'scope',
                                               'description': 'Alcance: sistemas y servicios '
                                                              'incluidos',
                                               'required': False},
                                              {'name': 'phases',
                                               'description': 'Fases del proyecto',
                                               'required': False},
                                              {'name': 'risks',
                                               'description': 'Riesgos identificados',
                                               'required': False},
                                              {'name': 'timeline',
                                               'description': 'Cronograma estimado',
                                               'required': False},
                                              {'name': 'approvers',
                                               'description': 'Lista de aprobadores requeridos',
                                               'required': False}]},
 'executive_summary': {'description': 'Genera un resumen ejecutivo de un proyecto o situación IT '
                                      'para presentar a dirección.',
                       'arguments': [{'name': 'project',
                                      'description': 'Nombre del proyecto o situación',
                                      'required': True},
                                     {'name': 'context',
                                      'description': 'Contexto o descripción del contenido',
                                      'required': True},
                                     {'name': 'audience',
                                      'description': 'Audiencia objetivo (CIO, CEO, comité…)',
                                      'required': False},
                                     {'name': 'max_pages',
                                      'description': 'Extensión máxima en páginas. Default: 1',
                                      'required': False}]},
 'business_case': {'description': 'Genera un business case IT con análisis coste-beneficio, ROI y '
                                  'justificación de inversión.',
                   'arguments': [{'name': 'project',
                                  'description': 'Nombre del proyecto/inversión',
                                  'required': True},
                                 {'name': 'requester',
                                  'description': 'Responsable o departamento solicitante',
                                  'required': True},
                                 {'name': 'description',
                                  'description': 'Descripción de la inversión propuesta',
                                  'required': True},
                                 {'name': 'cost',
                                  'description': 'Coste estimado (CAPEX/OPEX)',
                                  'required': False},
                                 {'name': 'benefits',
                                  'description': 'Beneficios esperados '
                                                 '(cuantitativos/cualitativos)',
                                  'required': False},
                                 {'name': 'alternatives',
                                  'description': 'Alternativas consideradas',
                                  'required': False},
                                 {'name': 'timeline',
                                  'description': 'Plazo de amortización o retorno',
                                  'required': False}]},
 'project_status_report': {'description': 'Genera un informe de estado de proyecto IT (RAG status) '
                                          'con hitos, riesgos y próximos pasos.',
                           'arguments': [{'name': 'project',
                                          'description': 'Nombre del proyecto',
                                          'required': True},
                                         {'name': 'period',
                                          'description': "Período del informe (p.ej. 'Mayo 2026')",
                                          'required': True},
                                         {'name': 'status',
                                          'description': 'Estado general: Verde/Ámbar/Rojo',
                                          'required': True},
                                         {'name': 'completed',
                                          'description': 'Hitos o tareas completadas en el período',
                                          'required': False},
                                         {'name': 'in_progress',
                                          'description': 'Tareas en curso',
                                          'required': False},
                                         {'name': 'risks',
                                          'description': 'Riesgos o problemas identificados',
                                          'required': False},
                                         {'name': 'next_steps',
                                          'description': 'Próximos hitos o acciones',
                                          'required': False},
                                         {'name': 'budget',
                                          'description': 'Estado del presupuesto',
                                          'required': False}]},
 'create_technical_doc': {'description': 'Crea un documento Word (.docx) técnico profesional con '
                                         'estilos O365 nativos usando doc_create. Incluye TOC '
                                         'automático, cabecera/pie de página, tabla de versiones, '
                                         'headings jerárquicos, tablas con estilos Office, '
                                         'checklists, callouts, bloques de código y firma digital.',
                          'arguments': [{'name': 'title',
                                         'description': 'Título del documento',
                                         'required': True},
                                        {'name': 'sections',
                                         'description': 'Secciones a incluir (comma-separated)',
                                         'required': True},
                                        {'name': 'doc_type',
                                         'description': 'Tipo: especificacion | procedimiento | '
                                                        'informe | manual | arquitectura',
                                         'required': False},
                                        {'name': 'author',
                                         'description': 'Autor del documento',
                                         'required': False},
                                        {'name': 'version',
                                         'description': 'Versión del documento (default: 1.0)',
                                         'required': False},
                                        {'name': 'language',
                                         'description': 'Idioma (español por defecto)',
                                         'required': False},
                                        {'name': 'template_path',
                                         'description': 'Ruta a plantilla .docx/.dotx corporativa',
                                         'required': False},
                                        {'name': 'output_path',
                                         'description': 'Ruta de salida para el .docx',
                                         'required': False}]},
 'generate_report_with_charts': {'description': 'Genera un informe Word (.docx) con gráficas '
                                                'nativas O365 incrustadas usando doc_create. Las '
                                                'gráficas se insertan como objetos DrawingML '
                                                'nativos (editables en Word), no como imágenes '
                                                'PNG. Soporta bar, line, pie, doughnut, scatter, '
                                                'stacked_bar, area y todos los tipos O365.',
                                 'arguments': [{'name': 'title',
                                                'description': 'Título del informe',
                                                'required': True},
                                               {'name': 'data',
                                                'description': 'Datos a visualizar (tabla CSV, '
                                                               'descripción o JSON)',
                                                'required': True},
                                               {'name': 'chart_types',
                                                'description': 'bar | line | pie | doughnut | '
                                                               'scatter | stacked_bar | area',
                                                'required': False},
                                               {'name': 'period',
                                                'description': 'Período analizado (mes, trimestre, '
                                                               'año)',
                                                'required': False},
                                               {'name': 'conclusions',
                                                'description': 'Conclusiones o puntos clave a '
                                                               'destacar',
                                                'required': False},
                                               {'name': 'output_path',
                                                'description': 'Ruta de salida para el .docx',
                                                'required': False}]},
 'create_word_document': {'description': 'Guía completa para crear cualquier documento Word '
                                         '(.docx) con doc_create y content_blocks O365. Muestra el '
                                         'uso correcto de todos los tipos de bloque: title, '
                                         'heading, paragraph, bullet_list, numbered_list, table '
                                         '(con merge_cells y estilos), chart (nativo DrawingML), '
                                         'checklist, callout, highlight, code_block, markdown, '
                                         'toc, signature_block, pagebreak, horizontal_rule.',
                          'arguments': [{'name': 'title',
                                         'description': 'Título del documento a crear',
                                         'required': True},
                                        {'name': 'purpose',
                                         'description': 'Propósito: informe | manual | RFC | acta '
                                                        '| propuesta',
                                         'required': False},
                                        {'name': 'blocks',
                                         'description': 'Lista de tipos de bloque a incluir '
                                                        '(comma-separated)',
                                         'required': False},
                                        {'name': 'output_path',
                                         'description': 'Ruta de salida para el .docx',
                                         'required': False}]}}


def _get_prompt(name: str, args: dict) -> list[dict]:  # noqa: C901
    _tpl = args.get("template_path", "")
    _tpl_hint = (
        f"\n\nPLANTILLA DE EMPRESA: {_tpl}\n"
        "→ USA doc_create_from_template o pptx_create_from_template con esta ruta para heredar estilos corporativos."
        if _tpl else
        "\n\nNOTA: Si el usuario tiene plantillas .docx/.dotx o .pptx/.potx de empresa, usa doc_create_from_template "
        "o pptx_create_from_template en lugar de crear desde cero para respetar el formato corporativo."
    )

    if name == "summarize_document":
        content   = args.get("content", "")
        max_words = args.get("max_words", "300")
        focus     = args.get("focus", "")
        focus_str = f"\nEnfoca especialmente en: {focus}" if focus else ""
        prompt = (
            f"Resume el siguiente documento en máximo {max_words} palabras.{focus_str}\n\n"
            "Estructura del resumen:\n"
            "## Resumen ejecutivo\n[2-3 frases clave]\n\n"
            "## Puntos principales\n[lista con viñetas]\n\n"
            "## Decisiones / Conclusiones\n[si las hay]\n\n"
            "## Acciones requeridas\n[con responsable y plazo si se mencionan]\n\n"
            f"DOCUMENTO:\n{content[:8000]}"
        )
    elif name == "weekly_report":
        completed   = args.get("completed", "")
        in_progress = args.get("in_progress", "")
        next_week   = args.get("next_week", "")
        blockers    = args.get("blockers", "")
        week = datetime.date.today().isocalendar()[1]
        prompt = (
            f"Genera un informe semanal profesional (semana {week}).\n\n"
            f"COMPLETADO:\n{completed}\n\n"
            f"EN PROGRESO:\n{in_progress or 'Ninguno'}\n\n"
            f"PRÓXIMA SEMANA:\n{next_week or 'Por definir'}\n\n"
            f"BLOQUEOS:\n{blockers or 'Ninguno'}\n\n"
            "Formato:\n"
            "# Informe Semanal — Semana [N]\n\n"
            "## ✅ Completado\n[lista con impacto breve de cada ítem]\n\n"
            "## 🔄 En progreso\n[con % estimado de avance]\n\n"
            "## 📅 Plan próxima semana\n[prioridades ordenadas]\n\n"
            "## ⚠ Bloqueos / Riesgos\n[acciones necesarias]"
        )
    elif name == "datacenter_migration_report":
        project_name = args.get("project_name", "")
        source_dc    = args.get("source_dc", "")
        target_dc    = args.get("target_dc", "")
        systems      = args.get("systems", "")
        date         = args.get("date", datetime.date.today().isoformat())
        team         = args.get("team", "No especificado")
        issues       = args.get("issues", "Ninguna")
        result       = args.get("result", "Exitoso")
        prompt = (
            f"Genera un informe técnico formal de migración de centro de datos para la fecha {date}.\n\n"
            f"PROYECTO: {project_name}\nORIGEN: {source_dc}\nDESTINO: {target_dc}\n"
            f"SISTEMAS MIGRADOS:\n{systems}\nEQUIPO: {team}\nINCIDENCIAS: {issues}\nRESULTADO: {result}\n\n"
            "Formato requerido (markdown formal):\n\n"
            "# Informe de Migración — [Nombre Proyecto]\n\n"
            "## Resumen Ejecutivo\n[Estado, resultado y contexto en 3-4 líneas]\n\n"
            "## Datos del Proyecto\n| Campo | Valor |\n[Tabla: proyecto, fecha, origen, destino, equipo, resultado]\n\n"
            "## Inventario de Sistemas Migrados\n| Sistema | Tipo | IP Origen | IP Destino | Estado | Observaciones |\n\n"
            "## Fases de Migración Ejecutadas\n[Lista numerada con estado ✅/⚠/❌]\n\n"
            "## Incidencias y Resolución\n[Si las hubo, con descripción, impacto y resolución]\n\n"
            "## Validaciones Post-Migración\n[Checklist: conectividad, servicios, datos, rendimiento]\n\n"
            "## Resultados y Conclusiones\n\n"
            "## Próximos Pasos\n\n"
            "## Firmas y Aprobaciones\n| Rol | Nombre | Firma | Fecha |"
        )
    elif name == "rfc_change_request":
        title            = args.get("title", "")
        requester        = args.get("requester", "")
        description      = args.get("description", "")
        affected_systems = args.get("affected_systems", "")
        risk_level       = args.get("risk_level", "Medio")
        rollback_plan    = args.get("rollback_plan", "Por definir")
        scheduled_date   = args.get("scheduled_date", "Por definir")
        rfc_id = f"RFC-{datetime.date.today().strftime('%Y%m%d')}"
        prompt = (
            f"Genera un documento RFC/Request for Change completo y formal para entorno corporativo.\n\n"
            f"ID RFC: {rfc_id}\nTÍTULO: {title}\nSOLICITANTE: {requester}\n"
            f"DESCRIPCIÓN: {description}\nSISTEMAS AFECTADOS: {affected_systems}\n"
            f"NIVEL DE RIESGO: {risk_level}\nFECHA PROGRAMADA: {scheduled_date}\n"
            f"PLAN DE ROLLBACK: {rollback_plan}\n\n"
            "Formato requerido (markdown formal):\n\n"
            f"# {rfc_id} — [Título]\n\n"
            "## 1. Información General\n[Tabla completa con todos los campos]\n\n"
            "## 2. Descripción del Cambio\n[Detallada y técnica]\n\n"
            "## 3. Justificación y Beneficios\n\n"
            "## 4. Alcance e Impacto\n[Sistemas afectados, usuarios, tiempo de inactividad estimado]\n\n"
            "## 5. Plan de Implementación\n[Pasos numerados con tiempo estimado y responsable]\n\n"
            "## 6. Análisis de Riesgos\n| Riesgo | Probabilidad | Impacto | Mitigación |\n\n"
            "## 7. Plan de Pruebas y Validación\n[Pasos de verificación post-cambio]\n\n"
            "## 8. Plan de Marcha Atrás\n[Pasos detallados para revertir]\n\n"
            "## 9. Plan de Comunicaciones\n[A quién notificar, cuándo y cómo]\n\n"
            "## 10. Aprobaciones\n| Rol | Nombre | Firma | Fecha |"
        )
    elif name == "server_migration_plan":
        server_name     = args.get("server_name", "")
        source_env      = args.get("source_env", "")
        target_env      = args.get("target_env", "")
        services        = args.get("services", "No especificados")
        downtime_window = args.get("downtime_window", "Por definir")
        dependencies    = args.get("dependencies", "Por analizar")
        prompt = (
            f"Genera un plan técnico detallado de migración de servidor.\n\n"
            f"SERVIDOR: {server_name}\nORIGEN: {source_env}\nDESTINO: {target_env}\n"
            f"SERVICIOS: {services}\nVENTANA DE MANTENIMIENTO: {downtime_window}\n"
            f"DEPENDENCIAS: {dependencies}\n\n"
            "Formato requerido (markdown técnico):\n\n"
            "# Plan de Migración — [Servidor]\n\n"
            "## Pre-requisitos\n[Checks y preparativos antes de la migración]\n\n"
            "## Inventario del Sistema Origen\n[HW, SO, servicios, datos, configuración de red]\n\n"
            "## Plan de Migración Paso a Paso\n| Paso | Descripción | Duración | Responsable |\n\n"
            "## Comandos de Migración\n[Código/comandos para cada fase crítica]\n\n"
            "## Plan de Pruebas\n[Checklist de validaciones post-migración]\n\n"
            "## Plan de Rollback\n[Pasos ordenados para revertir]\n\n"
            "## Plan de Comunicaciones\n[Pre/durante/post migración]\n\n"
            "## Criterios de Éxito\n[Qué debe estar operativo para dar la migración por correcta]"
        )
    elif name == "it_incident_report":
        title         = args.get("title", "")
        severity      = args.get("severity", "Media")
        start_time    = args.get("start_time", "")
        end_time      = args.get("end_time", "En curso")
        affected      = args.get("affected", "Por determinar")
        root_cause    = args.get("root_cause", "En investigación")
        timeline      = args.get("timeline", "Por documentar")
        actions_taken = args.get("actions_taken", "Por documentar")
        preventive    = args.get("preventive", "Por definir")
        prompt = (
            f"Genera un informe post-incidencia (Post-Mortem) IT completo y profesional.\n\n"
            f"TÍTULO: {title}\nSEVERIDAD: {severity}\nINICIO: {start_time}\nFIN: {end_time}\n"
            f"AFECTADOS: {affected}\nCAUSA RAÍZ: {root_cause}\nCRONOLOGÍA: {timeline}\n"
            f"ACCIONES: {actions_taken}\nMEDIDAS PREVENTIVAS: {preventive}\n\n"
            "Formato requerido (markdown formal):\n\n"
            "# Informe de Incidencia — [Título]\n\n"
            "## Resumen Ejecutivo\n[Qué pasó, impacto y resultado en 3-4 líneas]\n\n"
            "## Información del Incidente\n[Tabla: ID, título, severidad, inicio, fin, duración, estado]\n\n"
            "## Cronología de Eventos\n| Hora | Evento | Responsable | Acción |\n\n"
            "## Análisis de Causa Raíz (RCA)\n[Técnica 5 Porqués]\n\n"
            "## Impacto\n[Sistemas, usuarios, negocio, SLA afectado]\n\n"
            "## Acciones de Resolución Tomadas\n[Numeradas con responsable y hora]\n\n"
            "## Lecciones Aprendidas\n\n"
            "## Plan de Acción Preventivo\n| Acción | Responsable | Fecha límite | Estado |\n\n"
            "## Aprobaciones\n| Rol | Nombre | Firma | Fecha |"
        )
    elif name == "infrastructure_change_plan":
        project   = args.get("project", "")
        requester = args.get("requester", "")
        objective = args.get("objective", "")
        scope     = args.get("scope", "Por definir")
        phases    = args.get("phases", "Por definir")
        risks     = args.get("risks", "Por analizar")
        timeline  = args.get("timeline", "Por definir")
        approvers = args.get("approvers", "Por definir")
        prompt = (
            f"Genera un plan de cambio de infraestructura IT formal y detallado.\n\n"
            f"PROYECTO: {project}\nRESPONSABLE: {requester}\nOBJETIVO: {objective}\n"
            f"ALCANCE: {scope}\nFASES: {phases}\nRIESGOS: {risks}\n"
            f"CRONOGRAMA: {timeline}\nAPROBADORES: {approvers}\n\n"
            "Formato requerido (markdown formal):\n\n"
            "# Plan de Cambio de Infraestructura — [Proyecto]\n\n"
            "## Resumen Ejecutivo\n\n"
            "## Objetivos y Beneficios Esperados\n\n"
            "## Alcance del Proyecto\n[Tabla: En scope / Fuera de scope]\n\n"
            "## Análisis del Estado Actual (As-Is)\n\n"
            "## Estado Objetivo (To-Be)\n\n"
            "## Fases del Proyecto\n| Fase | Descripción | Inicio | Fin | Responsable | Estado |\n\n"
            "## Análisis de Riesgos\n| Riesgo | Probabilidad | Impacto | Mitigación |\n\n"
            "## Plan de Rollback\n\n"
            "## Cronograma — Hitos Principales\n\n"
            "## Recursos Necesarios\n[HW, SW, licencias, equipo]\n\n"
            "## Plan de Comunicaciones\n\n"
            "## Aprobaciones\n| Rol | Nombre | Firma | Fecha |"
        )
    elif name == "executive_summary":
        project   = args.get("project", "")
        context   = args.get("context", "")
        audience  = args.get("audience", "Dirección / Comité de IT")
        max_pages = args.get("max_pages", "1")
        prompt = (
            f"Genera un resumen ejecutivo de máximo {max_pages} página(s) para la audiencia: {audience}.\n\n"
            f"PROYECTO/SITUACIÓN: {project}\n\nCONTEXTO:\n{context}\n\n"
            "Formato requerido (markdown ejecutivo):\n\n"
            "# Resumen Ejecutivo — [Proyecto]\n\n"
            "## Situación Actual\n[2-3 frases: qué está pasando, contexto de negocio]\n\n"
            "## Objetivo\n[Qué se pretende conseguir y por qué es importante ahora]\n\n"
            "## Puntos Clave\n[3-5 bullets con hechos o datos relevantes]\n\n"
            "## Estado / Avance\n[Verde ✅ / Ámbar ⚠ / Rojo 🔴 con justificación breve]\n\n"
            "## Decisiones / Acciones Requeridas\n[Qué necesita la dirección aprobar, decidir o saber]\n\n"
            "## Riesgos Críticos\n[Solo los top 2-3; impacto y mitigación en una línea cada uno]\n\n"
            "## Próximos Hitos\n[Con fecha y responsable]\n\n"
            "Tono: directo, ejecutivo, sin tecnicismos innecesarios. Máximo concisión."
        )
    elif name == "business_case":
        project     = args.get("project", "")
        requester   = args.get("requester", "")
        description = args.get("description", "")
        cost        = args.get("cost", "Por determinar")
        benefits    = args.get("benefits", "Por analizar")
        alternatives= args.get("alternatives", "No aplica")
        timeline    = args.get("timeline", "Por definir")
        prompt = (
            f"Genera un Business Case IT completo y profesional para presentar a dirección.\n\n"
            f"PROYECTO: {project}\nSOLICITANTE: {requester}\n"
            f"DESCRIPCIÓN: {description}\nCOSTE ESTIMADO: {cost}\n"
            f"BENEFICIOS: {benefits}\nALTERNATIVAS: {alternatives}\n"
            f"PLAZO DE RETORNO: {timeline}\n\n"
            "Formato requerido (markdown formal):\n\n"
            "# Business Case — [Proyecto]\n\n"
            "## 1. Resumen Ejecutivo\n[Media página máxima]\n\n"
            "## 2. Situación Actual y Problema\n[As-Is: problema, pain points, coste de no actuar]\n\n"
            "## 3. Solución Propuesta\n[Descripción técnica y funcional]\n\n"
            "## 4. Análisis de Alternativas\n| Opción | Descripción | Ventajas | Inconvenientes | Coste |\n\n"
            "## 5. Análisis Coste-Beneficio\n"
            "### 5.1 Costes (CAPEX + OPEX)\n| Concepto | Año 1 | Año 2 | Año 3 | Total |\n"
            "### 5.2 Beneficios Cuantificables\n| Beneficio | Valor anual estimado |\n"
            "### 5.3 ROI y Período de Retorno\n[Fórmula y resultado]\n\n"
            "## 6. Riesgos\n| Riesgo | Probabilidad | Impacto | Mitigación |\n\n"
            "## 7. Cronograma de Implementación\n[Hitos principales con fecha]\n\n"
            "## 8. Recomendación\n[Opción recomendada y justificación]\n\n"
            "## 9. Aprobaciones\n| Rol | Nombre | Decisión | Fecha |"
        )
    elif name == "project_status_report":
        project     = args.get("project", "")
        period      = args.get("period", datetime.date.today().strftime("%B %Y"))
        status      = args.get("status", "Verde")
        completed   = args.get("completed", "Sin detalles")
        in_progress = args.get("in_progress", "Sin detalles")
        risks       = args.get("risks", "Sin riesgos identificados")
        next_steps  = args.get("next_steps", "Por definir")
        budget      = args.get("budget", "Sin información")
        status_icon = {"Verde": "✅", "Ámbar": "⚠", "Rojo": "🔴"}.get(status, "ℹ")
        prompt = (
            f"Genera un informe de estado (RAG Status Report) del proyecto {project} para el período {period}.\n\n"
            f"ESTADO GENERAL: {status_icon} {status}\n"
            f"COMPLETADO:\n{completed}\n\n"
            f"EN CURSO:\n{in_progress}\n\n"
            f"RIESGOS/PROBLEMAS:\n{risks}\n\n"
            f"PRÓXIMOS PASOS:\n{next_steps}\n\n"
            f"ESTADO PRESUPUESTO: {budget}\n\n"
            "Formato requerido (markdown formal):\n\n"
            f"# Informe de Estado — {project}\n**Período:** {period}  |  **Estado:** {status_icon} {status}\n\n"
            "## Resumen Ejecutivo\n[2-3 líneas del estado global]\n\n"
            "## KPIs del Período\n| Indicador | Objetivo | Real | Estado |\n\n"
            "## Hitos Completados\n[Lista con ✅ y fecha real]\n\n"
            "## Tareas en Curso\n[Con % avance y fecha estimada de fin]\n\n"
            "## Riesgos e Issues\n| # | Descripción | Impacto | Probabilidad | Acción | Responsable |\n\n"
            "## Presupuesto\n| Concepto | Presupuesto | Ejecutado | Desviación |\n\n"
            "## Próximos Hitos\n| Hito | Fecha prevista | Responsable |\n\n"
            "## Decisiones / Escaladas Requeridas\n[Si las hay]"
        )
    elif name == "create_technical_doc":
        title    = args.get("title", "Documento Técnico")
        sections = args.get("sections", "")
        doc_type = args.get("doc_type", "especificacion")
        author   = args.get("author", "")
        version  = args.get("version", "1.0")
        lang     = args.get("language", "español")
        tpl      = args.get("template_path", "")
        out      = args.get("output_path", f"{title.lower().replace(' ','_')}.docx" if title else "documento.docx")
        tpl_str  = f"\n\nPLANTILLA CORPORATIVA: {tpl}\n→ Usa doc_create_from_template en lugar de doc_create." if tpl else ""
        sec_list = [s.strip() for s in sections.split(",") if s.strip()]
        sec_blocks = "\n".join(
            f'    {{"type": "heading", "level": 1, "text": "{s}"}},\n'
            f'    {{"type": "paragraph", "text": "Contenido de la sección {s}..."}},'
            for s in sec_list
        )
        prompt = (
            f"Crea un documento técnico profesional Word (.docx) con estilos O365 nativos.{tpl_str}\n\n"
            f"TÍTULO: {title}\nTIPO: {doc_type}\nVERSIÓN: {version}\n"
            + (f"AUTOR: {author}\n" if author else "")
            + f"IDIOMA: {lang}\nSECCIONES: {sections}\nSALIDA: {out}\n\n"
            "## HERRAMIENTA: `doc_create` con `content_blocks`\n\n"
            "```json\n"
            "{\n"
            f'  "output_path": "{out}",\n'
            '  "content_blocks": [\n'
            '    {"type": "title", "text": "' + title + '",\n'
            '     "subtitle": "' + doc_type.capitalize() + ' v' + version + ' — ' + (author or 'Autor') + '"},\n'
            '    {"type": "toc", "title": "Tabla de Contenidos"},\n'
            '    {"type": "table",\n'
            '     "headers": ["Campo", "Valor"],\n'
            '     "rows": [["Título", "' + title + '"], ["Tipo", "' + doc_type + '"],\n'
            '              ["Versión", "' + version + '"], ["Autor", "' + (author or "—") + '"],\n'
            '              ["Idioma", "' + lang + '"], ["Estado", "Borrador"]],\n'
            '     "style": "Light Grid Accent 1"},\n'
            '    {"type": "pagebreak"},\n'
            + sec_blocks +
            '\n    {"type": "heading", "level": 1, "text": "Referencias"},\n'
            '    {"type": "bullet_list", "items": ["Referencia 1", "Referencia 2"]},\n'
            '    {"type": "signature_block", "roles": ["Autor", "Revisor", "Aprobador"]}\n'
            "  ]\n"
            "}\n"
            "```\n\n"
            "## TIPOS DE BLOQUE DISPONIBLES PARA content_blocks:\n\n"
            "| Tipo | Uso |\n"
            "|------|-----|\n"
            '| `title` | Portada con text + subtitle |\n'
            '| `heading` | Título de sección, level 1-6 |\n'
            '| `paragraph` | Párrafo normal, estilo configurable |\n'
            '| `bullet_list` | Lista con viñetas, anidable con items.items |\n'
            '| `numbered_list` | Lista numerada |\n'
            '| `table` | Tabla con headers, rows, style y merge_cells |\n'
            '| `chart` | Gráfica nativa DrawingML (bar/line/pie/doughnut/scatter/column/stacked_bar/area) |\n'
            '| `image` | Imagen PNG/JPG incrustada, con caption |\n'
            '| `code_block` | Bloque de código con sintaxis (language) |\n'
            '| `markdown` | Texto Markdown convertido a formato Word |\n'
            '| `checklist` | Lista con checkboxes |\n'
            '| `callout` | Cuadro de aviso (info/tip/note/warning/error/success) |\n'
            '| `highlight` | Texto resaltado con color de fondo |\n'
            '| `toc` | Tabla de contenidos automática |\n'
            '| `signature_block` | Bloque de firmas con roles |\n'
            '| `pagebreak` | Salto de página |\n'
            '| `horizontal_rule` | Línea horizontal |\n\n'
            "Genera el JSON completo para doc_create con contenido profesional en cada sección."
            + _tpl_hint
        )

    elif name == "generate_report_with_charts":
        title       = args.get("title", "Informe")
        data        = args.get("data", "")
        chart_types = args.get("chart_types", "bar, line")
        period      = args.get("period", "período actual")
        conclusions = args.get("conclusions", "")
        out         = args.get("output_path", f"{title.lower().replace(' ','_')}.docx" if title else "informe.docx")
        charts_list = [c.strip() for c in chart_types.split(",") if c.strip()]
        charts_blocks = "\n".join(
            f'    {{"type": "chart", "chart_type": "{ct}",\n'
            f'     "title": "Gráfica {ct.capitalize()}",\n'
            f'     "width_inches": 5.5, "height_inches": 3.5,\n'
            f'     "data": {{"categories": ["Ene","Feb","Mar","Abr"], "series": [{{"label": "Serie 1", "values": [10,20,15,25]}}]}}}},\n'
            for ct in charts_list
        )
        prompt = (
            f"Genera un informe Word (.docx) con gráficas nativas O365 usando doc_create.\n\n"
            f"TÍTULO: {title}\nPERÍODO: {period}\nDATA: {data}\nGRÁFICAS: {chart_types}\n"
            + (f"CONCLUSIONES: {conclusions}\n" if conclusions else "")
            + f"SALIDA: {out}\n\n"
            "## IMPORTANTE — Usa gráficas NATIVAS O365 (DrawingML), NO matplotlib:\n"
            "Las gráficas con `\"type\": \"chart\"` en content_blocks se insertan como objetos\n"
            "DrawingML nativos en Word — son editables directamente en Microsoft Word/LibreOffice.\n\n"
            "## HERRAMIENTA: `doc_create` con content_blocks\n\n"
            "```json\n"
            "{\n"
            f'  "output_path": "{out}",\n'
            '  "content_blocks": [\n'
            f'    {{"type": "title", "text": "{title}", "subtitle": "Período: {period}"}},\n'
            '    {"type": "toc", "title": "Índice"},\n'
            '    {"type": "pagebreak"},\n'
            '    {"type": "heading", "level": 1, "text": "Resumen Ejecutivo"},\n'
            '    {"type": "paragraph", "text": "Resumen de 3-5 frases con los hallazgos principales..."},\n'
            '    {"type": "heading", "level": 1, "text": "Datos y Análisis"},\n'
            '    {"type": "table", "headers": ["Período","Valor","Variación"],\n'
            '     "rows": [["Ene","100","—"],["Feb","120","+20%"]], "style": "Medium Shading 1 Accent 1"},\n'
            + charts_blocks +
            '    {"type": "heading", "level": 1, "text": "Conclusiones"},\n'
            '    {"type": "bullet_list", "items": '
            + (f'["{conclusions}"]' if conclusions else '["Conclusión 1", "Conclusión 2", "Recomendación"]')
            + '},\n'
            '    {"type": "callout", "callout_type": "info", "title": "Próximos pasos",\n'
            '     "text": "Acción requerida basada en el análisis..."}\n'
            "  ]\n"
            "}\n"
            "```\n\n"
            "## TIPOS DE GRÁFICA NATIVA SOPORTADOS:\n"
            "`bar`, `column`, `stacked_bar`, `stacked_column`, `100_stacked_column`,\n"
            "`line`, `stacked_line`, `area`, `stacked_area`, `pie`, `doughnut`, `scatter`\n\n"
            "Genera el JSON completo con datos reales basados en la descripción proporcionada."
            + _tpl_hint
        )

    elif name == "create_word_document":
        title   = args.get("title", "Documento")
        purpose = args.get("purpose", "informe")
        blocks  = args.get("blocks", "heading,paragraph,table,chart,checklist,callout")
        out     = args.get("output_path", f"{title.lower().replace(' ','_')}.docx" if title else "documento.docx")
        prompt = (
            f"Crea el documento Word '{title}' (.docx) con estilos O365 nativos usando doc_create.\n\n"
            f"PROPÓSITO: {purpose}\nBLOQUES A INCLUIR: {blocks}\nSALIDA: {out}\n\n"
            "## REFERENCIA COMPLETA DE content_blocks PARA doc_create:\n\n"
            "```json\n"
            "{\n"
            f'  "output_path": "{out}",\n'
            '  "content_blocks": [\n'
            "\n    // ─── PORTADA ───\n"
            '    {"type": "title", "text": "Título Principal",\n'
            '     "subtitle": "Subtítulo o descripción breve"},\n'
            "\n    // ─── TABLA DE CONTENIDOS (actualizable con F9 en Word) ───\n"
            '    {"type": "toc", "title": "Tabla de Contenidos"},\n'
            '    {"type": "pagebreak"},\n'
            "\n    // ─── HEADINGS (nivel 1-6, estilos Calibri Light O365) ───\n"
            '    {"type": "heading", "level": 1, "text": "1. Introducción"},\n'
            '    {"type": "heading", "level": 2, "text": "1.1 Contexto"},\n'
            "\n    // ─── PÁRRAFOS (estilos: Normal, Body Text, Quote, Caption) ───\n"
            '    {"type": "paragraph", "text": "Texto del párrafo.", "style": "Normal"},\n'
            "\n    // ─── LISTAS ───\n"
            '    {"type": "bullet_list", "items": [\n'
            '      "Elemento simple",\n'
            '      {"text": "Con subitems", "items": ["Sub 1", "Sub 2"]}\n'
            "    ]},\n"
            '    {"type": "numbered_list", "items": ["Paso 1", "Paso 2", "Paso 3"]},\n'
            "\n    // ─── CHECKLIST ───\n"
            '    {"type": "checklist", "items": [\n'
            '      {"text": "Tarea completada", "checked": true},\n'
            '      {"text": "Tarea pendiente", "checked": false},\n'
            '      "Texto simple (no checked)"\n'
            "    ]},\n"
            "\n    // ─── TABLA (con merge, estilos Office, alineación) ───\n"
            '    {"type": "table",\n'
            '     "headers": ["Columna 1", "Columna 2", "Columna 3"],\n'
            '     "rows": [["A", "B", "C"], ["D", "E", "F"]],\n'
            '     "style": "Light Grid Accent 1",\n'
            '     "merge_cells": [{"start_row": 0, "start_col": 0, "end_row": 0, "end_col": 1}]},\n'
            "\n    // ─── GRÁFICA NATIVA DrawingML (editable en Word) ───\n"
            '    {"type": "chart",\n'
            '     "chart_type": "bar|column|stacked_bar|stacked_column|100_stacked_column|\n'
            '                    line|stacked_line|area|stacked_area|pie|doughnut|scatter",\n'
            '     "title": "Título de la gráfica",\n'
            '     "width_inches": 5.5, "height_inches": 3.5,\n'
            '     "data": {\n'
            '       "categories": ["Ene", "Feb", "Mar"],\n'
            '       "series": [\n'
            '         {"label": "Serie A", "values": [10, 20, 15]},\n'
            '         {"label": "Serie B", "values": [5, 12, 18]}\n'
            "       ]\n"
            "     }},\n"
            "\n    // ─── IMAGEN ───\n"
            '    {"type": "image", "path": "/ruta/imagen.png",\n'
            '     "width_inches": 5.0, "caption": "Figura 1", "align": "center"},\n'
            "\n    // ─── CÓDIGO ───\n"
            '    {"type": "code_block", "code": "def hello():\\n    return \'world\'",\n'
            '     "language": "python"},\n'
            "\n    // ─── MARKDOWN (convertido a formato Word nativo) ───\n"
            '    {"type": "markdown", "text": "## Sección\\n**Negrita**, _cursiva_, `código`"},\n'
            "\n    // ─── CALLOUTS (info/tip/note/warning/error/success) ───\n"
            '    {"type": "callout", "callout_type": "warning",\n'
            '     "title": "Atención", "text": "Mensaje de advertencia importante."},\n'
            "\n    // ─── HIGHLIGHT ───\n"
            '    {"type": "highlight", "text": "Texto resaltado en amarillo",\n'
            '     "color": "FFFF00", "text_color": "000000"},\n'
            "\n    // ─── SEPARADORES ───\n"
            '    {"type": "horizontal_rule"},\n'
            '    {"type": "pagebreak"},\n'
            "\n    // ─── FIRMA ───\n"
            '    {"type": "signature_block",\n'
            '     "roles": ["Autor", "Revisor", "Aprobador", "Director"]}\n'
            "  ]\n"
            "}\n"
            "```\n\n"
            "## ESTILOS DE TABLA DISPONIBLES (style en bloque table):\n"
            "Light Grid Accent 1 | Medium Shading 1 Accent 1 | Dark List Accent 1\n"
            "Table Grid | Light List | Medium List 2 Accent 1\n\n"
            "Genera el JSON completo para doc_create con el contenido de '" + title + "'."
            + _tpl_hint
        )

    else:
        prompt = f"Prompt {name} no disponible."
    return [{"role": "user", "content": {"type": "text", "text": prompt}}]


# ── Resources ────────────────────────────────────────────────────────────────


# ── Resources ───────────────────────────────────────────────────────────────────


# ── Resources ───────────────────────────────────────────────────────────────────

_RESOURCES = [{'uri': 'office://templates_available',
  'name': 'Plantillas disponibles',
  'description': 'Lista de plantillas de documentos disponibles (.docx, .xlsx, .md)',
  'mimeType': 'text/plain'},
 {'uri': 'office://rfc_pending',
  'name': 'RFCs pendientes',
  'description': 'Lista de documentos RFC/Change Request en el directorio de notas',
  'mimeType': 'text/plain'},
 {'uri': 'office://project_context',
  'name': 'Contexto del proyecto',
  'description': 'Metadata del proyecto activo: nombre, cliente, tipo, directorios, naming '
                 'convention (desde OOCODE.md del cwd)',
  'mimeType': 'text/plain'},
 {'uri': 'office://style_gallery',
  'name': 'Galería de estilos O365',
  'description': 'Lista de estilos de párrafo y tabla disponibles para documentos .docx y '
                 'presentaciones .pptx',
  'mimeType': 'text/plain'},
 {'uri': 'office://style_presets',
  'name': 'Presets de estilos O365',
  'description': 'Configuraciones de estilo predefinidas para títulos, subtítulos, cuerpo y tablas '
                 'con valores concretos',
  'mimeType': 'application/json'},
 {'uri': 'office://theme_colors',
  'name': 'Paletas de colores de temas O365',
  'description': 'Paletas de colores de los temas office/modern/professional/minimal/corporate con '
                 'códigos hex',
  'mimeType': 'application/json'},
 {'uri': 'office://font_combinations',
  'name': 'Combinaciones de fuentes recomendadas',
  'description': 'Combinaciones de fuentes compatibles con O365 y LibreOffice: heading + body + '
                 'mono',
  'mimeType': 'application/json'},
 {'uri': 'office://chart_types',
  'name': 'Tipos de gráficas disponibles',
  'description': 'Referencia completa de tipos de gráficas con sus tools y parámetros clave',
  'mimeType': 'application/json'}]


_RESOURCE_FNS = {
    'office://templates_available' : _resource_templates_available,
    'office://rfc_pending'         : _resource_rfc_pending,
    'office://project_context'     : _resource_project_context,
    'office://style_gallery'       : _resource_style_gallery,
    'office://style_presets'       : _resource_style_presets,
    'office://theme_colors'        : _resource_theme_colors,
    'office://font_combinations'   : _resource_font_combinations,
    'office://chart_types'         : _resource_chart_types,
}



# ── Bucle principal ─────────────────────────────────────────────────────────────

def _handle(req: dict) -> None:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "word-assistant", "version": "1.0.0"},
            "capabilities": {
                "tools":     {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts":   {"listChanged": False},
            },
        })

    elif method == "notifications/initialized":
        pass

    elif method == "tools/list":
        _ok(req_id, {"tools": _TOOLS})

    elif method == "tools/call":
        name      = params.get("name", "")
        arguments = params.get("arguments", {})
        fn        = _TOOL_FNS.get(name)
        if fn is None:
            _err(req_id, -32601, f"Tool desconocida: {name}")
            return
        try:
            result = fn(arguments)
            _ok(req_id, {"content": [{"type": "text", "text": result}], "isError": False})
        except Exception as exc:
            _ok(req_id, {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True})

    elif method == "resources/list":
        _ok(req_id, {"resources": _RESOURCES})

    elif method == "resources/read":
        uri = params.get("uri", "")
        fn  = _RESOURCE_FNS.get(uri)
        if fn is None:
            _err(req_id, -32601, f"Recurso desconocido: {uri}")
            return
        try:
            content = fn()
            _ok(req_id, {"contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]})
        except Exception as exc:
            _err(req_id, -32603, f"Error leyendo recurso: {exc}")

    elif method == "prompts/list":
        prompts = [
            {"name": k, "description": v["description"], "arguments": v["arguments"]}
            for k, v in _PROMPTS.items()
        ]
        _ok(req_id, {"prompts": prompts})

    elif method == "prompts/get":
        name      = params.get("name", "")
        arguments = params.get("arguments", {})
        if name not in _PROMPTS:
            _err(req_id, -32601, f"Prompt desconocido: {name}")
            return
        messages = _get_prompt(name, arguments)
        _ok(req_id, {"description": _PROMPTS[name]["description"], "messages": messages})

    elif req_id is not None:
        _err(req_id, -32601, f"Método desconocido: {method}")


def main() -> None:
    sys.stderr.write("[word-assistant] MCP server v1.0.0 iniciado (29 tools, 13 prompts, 8 resources)\n")
    sys.stderr.flush()
    while True:
        try:
            req = _recv()
            if req is None:
                break
            _handle(req)
        except (EOFError, BrokenPipeError):
            break
        except Exception as exc:
            sys.stderr.write(f"[word-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()

