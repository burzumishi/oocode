#!/usr/bin/env python3
"""Excel Assistant MCP Server — hojas de cálculo .xlsx y CSV para OOCode.

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 newline-delimited JSON).

Crea y edita hojas Excel nativas (openpyxl): lectura/escritura de celdas y rangos,
informes formateados, tablas nativas, gráficas, formato condicional, validación de datos,
freeze panes, protección de hoja, y análisis de CSV.

Las gráficas/datos pueden generarse también vía doc_create del word-assistant (.xlsx).

Split de office_assistant.py (v0.4.4): documentos Word → word_assistant.py;
presentaciones PowerPoint → pptx_assistant.py.
"""
import csv
import json
import sys
from pathlib import Path
from typing import Any, Optional



_CSV_SNIFF_BYTES = 65536   # bytes para que csv.Sniffer detecte el dialect (64 KB)



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

def _tool_xlsx_insert_chart(args: dict) -> str:
    """Inserta una gráfica nativa de openpyxl en una hoja Excel (.xlsx). No requiere matplotlib."""
    path        = Path(args.get("path", "")).expanduser()
    chart_type  = args.get("chart_type", "bar")   # bar, line, pie, area, scatter
    sheet       = args.get("sheet", "")
    data_range  = args.get("data_range", "A1:B5")  # p.ej. "A1:C6"
    title       = args.get("title", "")
    position    = args.get("position", "E2")       # celda donde anclar el gráfico
    width       = args.get("width", 15)
    height      = args.get("height", 10)
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        import openpyxl
        from openpyxl.chart import (
            BarChart, LineChart, PieChart, AreaChart, ScatterChart,
            Reference, Series,
        )
        from openpyxl.chart.series import SeriesLabel
        wb = openpyxl.load_workbook(str(path))
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active

        # Parsear rango de datos
        try:
            min_col, min_row, max_col, max_row = openpyxl.utils.cell.range_boundaries(data_range)
        except Exception:
            return f"Rango de datos inválido: {data_range}  (usa formato 'A1:C6')"

        # Seleccionar tipo de gráfica
        _CHART_MAP = {
            "bar":          BarChart,
            "line":         LineChart,
            "pie":          PieChart,
            "area":         AreaChart,
            "scatter":      ScatterChart,
        }
        ChartClass = _CHART_MAP.get(chart_type)
        if ChartClass is None:
            return f"Tipo no soportado: {chart_type}. Usa: {', '.join(_CHART_MAP)}"

        chart = ChartClass()
        chart.title  = title or chart_type.capitalize()
        chart.width  = width
        chart.height = height

        # Estilos Office para gráficas nativas Excel
        if chart_type == "bar":
            chart.type    = "col"   # columnas verticales (default Office)
            chart.overlap = -10
            chart.grouping = "clustered"

        # Datos: columna 1 = categorías/eje X; columnas 2..N = series
        # Fila min_row = cabecera; datos desde min_row+1 hasta max_row
        if chart_type != "scatter":
            # Categorías: primera columna, solo filas de datos (sin cabecera)
            cats = Reference(ws, min_col=min_col, min_row=min_row + 1, max_row=max_row)
            # Series: columnas 2..N incluyendo fila de cabecera (titles_from_data=True)
            for col in range(min_col + 1, max_col + 1):
                data_ref = Reference(ws, min_col=col, min_row=min_row, max_row=max_row)
                chart.add_data(data_ref, titles_from_data=True)
            chart.set_categories(cats)
        else:
            # Scatter: X = columna 1 (datos), Y = columnas 2..N (datos)
            # Series(xvalues, yvalues) — orden correcto
            xvals = Reference(ws, min_col=min_col, min_row=min_row + 1, max_row=max_row)
            for col_idx, col in enumerate(range(min_col + 1, max_col + 1)):
                yvals = Reference(ws, min_col=col, min_row=min_row + 1, max_row=max_row)
                ser = Series(xvals, yvals)
                try:
                    ser.title = SeriesLabel(v=ws.cell(min_row, col).value or f"Serie {col_idx+1}")
                except Exception:
                    pass
                chart.series.append(ser)

        ws.add_chart(chart, position)
        wb.save(str(path))
        n_series = max_col - min_col
        return (
            f"✅ Gráfica nativa '{chart_type}' insertada en {path}\n"
            f"   Datos: {data_range}  Series: {n_series}  Posición: {position}"
        )
    except ImportError as e:
        return f"openpyxl no disponible: {e}. Instala con: pip install openpyxl"
    except Exception as exc:
        return f"Error insertando gráfica Excel: {exc}"


def _tool_xlsx_apply_conditional_format(args: dict) -> str:
    """Aplica formato condicional a un rango de celdas en Excel."""
    path       = Path(args.get("path", "")).expanduser()
    sheet      = args.get("sheet", "")
    cell_range = args.get("range", "A1:A10")  # p.ej. "B2:B20"
    rule_type  = args.get("rule_type", "color_scale")  # color_scale, data_bar, icon_set, cell_is
    # Para color_scale: {"min": "#FF0000", "mid": "#FFFF00", "max": "#00FF00"}
    # Para cell_is: {"operator": "greaterThan", "formula": "100", "fill": "#FF0000"}
    options    = args.get("options", {})
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        import openpyxl
        from openpyxl.formatting.rule import ColorScaleRule, DataBarRule, IconSetRule, CellIsRule
        from openpyxl.styles import PatternFill
        wb = openpyxl.load_workbook(str(path))
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active

        if rule_type == "color_scale":
            min_c = options.get("min", "F8696B")
            mid_c = options.get("mid", "FFEB84")
            max_c = options.get("max", "63BE7B")
            rule = ColorScaleRule(
                start_type="min",  start_color=min_c.lstrip("#"),
                mid_type="percentile", mid_value=50, mid_color=mid_c.lstrip("#"),
                end_type="max",    end_color=max_c.lstrip("#"),
            )
        elif rule_type == "data_bar":
            fill_c = options.get("fill", "638EC6")
            rule = DataBarRule(start_type="min", start_value=0,
                               end_type="max",   end_value=None,
                               color=fill_c.lstrip("#"))
        elif rule_type == "icon_set":
            icon = options.get("icon_style", "3TrafficLights1")
            rule = IconSetRule(icon_style=icon, type="percent",
                               values=[0, 33, 67])
        elif rule_type == "cell_is":
            op   = options.get("operator", "greaterThan")
            form = options.get("formula", ["0"])
            fill_c = options.get("fill", "FF0000")
            fill   = PatternFill(start_color=fill_c.lstrip("#"), end_color=fill_c.lstrip("#"), fill_type="solid")
            formula = [form] if isinstance(form, str) else form
            rule = CellIsRule(operator=op, formula=formula, fill=fill)
        else:
            return f"Tipo de regla no soportado: {rule_type}. Usa: color_scale, data_bar, icon_set, cell_is"

        ws.conditional_formatting.add(cell_range, rule)
        wb.save(str(path))
        return f"✅ Formato condicional '{rule_type}' aplicado en {cell_range} ({path})"
    except ImportError:
        return "openpyxl no disponible. Instala con: pip install openpyxl"
    except Exception as exc:
        return f"Error aplicando formato condicional: {exc}"


def _tool_xlsx_read(args: dict) -> str:
    path   = Path(args.get("path", "")).expanduser()
    sheet  = args.get("sheet", "")
    limit  = int(args.get("limit", 50))
    if not path:
        return "Parámetro requerido: path"
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    ext = path.suffix.lower()
    if ext == ".csv":
        return _read_csv_file(path, limit)
    # Excel
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        ws_name = sheet or wb.sheetnames[0]
        if ws_name not in wb.sheetnames:
            return f"Hoja '{ws_name}' no encontrada. Disponibles: {', '.join(wb.sheetnames)}"
        ws = wb[ws_name]
        lines = [f"📊 {path.name} — Hoja: {ws_name}"]
        count = 0
        for row in ws.iter_rows(values_only=True):
            if count >= limit:
                lines.append(f"  … (limitado a {limit} filas)")
                break
            cells = [str(c) if c is not None else "" for c in row]
            lines.append("  " + " | ".join(cells))
            count += 1
        return "\n".join(lines)
    except ImportError:
        return "openpyxl no instalado. Instala con: pip install openpyxl"
    except Exception as exc:
        return f"Error leyendo Excel: {exc}"


def _read_csv_file(path: Path, limit: int) -> str:
    try:
        with path.open(newline="", errors="replace") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return f"CSV vacío: {path.name}"
        headers = rows[0]
        data    = rows[1:limit + 1]
        lines = [f"📊 {path.name} — CSV ({len(rows)-1} filas, {len(headers)} columnas)"]
        lines.append("  " + " | ".join(headers))
        lines.append("  " + " | ".join(["─" * min(len(h), 12) for h in headers]))
        for row in data:
            lines.append("  " + " | ".join(row))
        if len(rows) - 1 > limit:
            lines.append(f"  … ({len(rows)-1-limit} filas más)")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error leyendo CSV: {exc}"


def _apply_cell_style(cell, style: dict) -> None:
    """Aplica un dict de estilo a una celda openpyxl.

    Claves soportadas:
      bold, italic, underline (bool)
      font_size (int), font_color (str hex RRGGBB p.ej. "FF0000")
      bg_color (str hex RRGGBB), align (str: left/center/right/fill)
      number_format (str, p.ej. "#,##0.00", "0%", "DD/MM/YYYY")
      border (bool) — añade borde fino en los 4 lados
      wrap_text (bool)
    """
    try:
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side  # type: ignore
        kw: dict = {}
        if style.get("bold"):       kw["bold"]      = True
        if style.get("italic"):     kw["italic"]    = True
        if style.get("underline"):  kw["underline"] = "single"
        if style.get("font_size"):  kw["size"]      = int(style["font_size"])
        if style.get("font_color"): kw["color"]     = style["font_color"].lstrip("#").upper()
        if kw:
            cell.font = Font(**kw)
        bg = style.get("bg_color", "")
        if bg:
            cell.fill = PatternFill("solid", fgColor=bg.lstrip("#").upper())
        align = style.get("align", "")
        wrap  = bool(style.get("wrap_text"))
        if align or wrap:
            cell.alignment = Alignment(horizontal=align or None, wrap_text=wrap or None)
        if style.get("border"):
            thin = Side(style="thin")
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        if style.get("number_format"):
            cell.number_format = style["number_format"]
    except Exception:
        pass


def _tool_xlsx_write(args: dict) -> str:
    path  = Path(args.get("path", "")).expanduser()
    sheet = args.get("sheet", "Hoja1")
    cell  = args.get("cell", "A1")
    value = args.get("value", "")
    style = args.get("style", {})
    if not path or not cell:
        return "Parámetros requeridos: path, cell (p.ej. 'B3'), value"
    try:
        import openpyxl
        if path.exists():
            wb = openpyxl.load_workbook(str(path))
        else:
            wb = openpyxl.Workbook()
        if sheet not in wb.sheetnames:
            wb.create_sheet(sheet)
        ws = wb[sheet]
        c = ws[cell.upper()]
        c.value = value
        if style and isinstance(style, dict):
            _apply_cell_style(c, style)
        wb.save(str(path))
        return f"✅ Escrito en {path.name} [{sheet}]{cell.upper()} = {value!r}"
    except ImportError:
        return "openpyxl no instalado. Instala con: pip install openpyxl"
    except Exception as exc:
        return f"Error escribiendo Excel: {exc}"


def _tool_csv_analyze(args: dict) -> str:
    path  = Path(args.get("path", "")).expanduser()
    limit = int(args.get("limit", 5))
    if not path:
        return "Parámetro requerido: path"
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        with path.open(newline="", errors="replace") as f:
            sample = f.read(_CSV_SNIFF_BYTES)
        dialect = csv.Sniffer().sniff(sample[:2048])
        with path.open(newline="", errors="replace") as f:
            reader = csv.DictReader(f, dialect=dialect)
            rows   = [row for _, row in zip(range(limit + 1), reader)]
        headers = list(rows[0].keys()) if rows else []
        n_rows  = sum(1 for _ in path.open(newline="")) - 1
        lines = [
            f"📊 Análisis CSV: {path.name}",
            f"  Filas (aprox):  {n_rows}",
            f"  Columnas:       {len(headers)}",
            f"  Delimitador:    {dialect.delimiter!r}",
            f"  Columnas: {', '.join(headers)}",
            f"\n  Primeras {min(limit, len(rows))} filas:",
        ]
        for i, row in enumerate(rows[:limit]):
            lines.append(f"  [{i+1}] " + " | ".join(f"{k}={v!r}" for k, v in row.items()))
        # Stats básicas para columnas numéricas
        numeric: dict[str, list] = {h: [] for h in headers}
        with path.open(newline="", errors="replace") as f:
            reader2 = csv.DictReader(f, dialect=dialect)
            for row in reader2:
                for h in headers:
                    try:
                        numeric[h].append(float(row[h]))
                    except (ValueError, TypeError, KeyError):
                        pass
        num_cols = [(h, vals) for h, vals in numeric.items() if len(vals) >= n_rows * 0.5]
        if num_cols:
            lines.append("\n  Estadísticas numéricas:")
            for h, vals in num_cols:
                mn = min(vals); mx = max(vals); avg = sum(vals) / len(vals)
                lines.append(f"    {h}: min={mn:.2f}  max={mx:.2f}  avg={avg:.2f}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error analizando CSV: {exc}"


# ── Calendar tools ───────────────────────────────────────────────────────────


def _tool_xlsx_fill_range(args: dict) -> str:
    """Write multiple cells at once in an Excel file.

    cells: dict {cell_addr: value} OR list of {cell, value, style} objects.
    style (por celda o global): bold, italic, font_color, bg_color, align, border…
    """
    path        = Path(args.get("path", "")).expanduser()
    sheet       = args.get("sheet", "Hoja1")
    cells       = args.get("cells", {})
    global_style = args.get("style", {})
    if not path:
        return "Parámetro requerido: path"
    if not cells:
        return 'Parámetro requerido: cells ({"A1": "valor"} o [{"cell":"A1","value":…,"style":{…}}])'
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path)) if path.exists() else openpyxl.Workbook()
        if sheet not in wb.sheetnames:
            wb.create_sheet(sheet)
        ws  = wb[sheet]
        written: list[str] = []
        # Soportar tanto dict simple como lista de objetos {cell, value, style}
        items: list[tuple[str, object, dict]]
        if isinstance(cells, dict):
            items = [(addr, val, global_style) for addr, val in cells.items()]
        elif isinstance(cells, list):
            items = []
            for entry in cells:
                if isinstance(entry, dict):
                    addr = str(entry.get("cell", ""))
                    val  = entry.get("value", "")
                    sty  = {**global_style, **entry.get("style", {})}
                    items.append((addr, val, sty))
        else:
            return 'cells debe ser un dict {"A1": valor} o una lista de objetos {cell, value, style}'
        for cell_addr, value, cell_style in items:
            if not cell_addr:
                continue
            c = ws[cell_addr.upper()]
            c.value = value
            if cell_style:
                _apply_cell_style(c, cell_style)
            written.append(f"{cell_addr.upper()}={value!r}")
        wb.save(str(path))
        return (
            f"✅ {len(written)} celdas escritas en {path.name} [{sheet}]:\n"
            + "\n".join(f"   {w}" for w in written)
        )
    except ImportError:
        return "openpyxl no instalado. Instala con: pip install openpyxl"
    except Exception as exc:
        return f"Error escribiendo rango Excel: {exc}"


def _tool_xlsx_append_row(args: dict) -> str:
    """Append a row of values to the next empty row in an Excel sheet.

    values: lista de valores, o lista de {value, style} para estilos por celda.
    style (global): se aplica a todas las celdas de la fila.
    """
    path         = Path(args.get("path", "")).expanduser()
    sheet        = args.get("sheet", "Hoja1")
    values       = args.get("values", [])
    global_style = args.get("style", {})
    if not path:
        return "Parámetro requerido: path"
    if not values:
        return "Parámetro requerido: values (lista de valores para la nueva fila)"
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path)) if path.exists() else openpyxl.Workbook()
        if sheet not in wb.sheetnames:
            wb.create_sheet(sheet)
        ws = wb[sheet]
        # Determinar si hay estilos por celda
        has_per_cell = isinstance(values, list) and values and isinstance(values[0], dict)
        if has_per_cell:
            raw_values = [v.get("value", "") if isinstance(v, dict) else v for v in values]
        else:
            raw_values = list(values)
        ws.append(raw_values)
        row_num = ws.max_row
        # Aplicar estilos tras append
        if global_style or has_per_cell:
            for col_idx, val in enumerate(values, 1):
                c = ws.cell(row=row_num, column=col_idx)
                cell_style = {**global_style}
                if has_per_cell and isinstance(val, dict):
                    cell_style.update(val.get("style", {}))
                if cell_style:
                    _apply_cell_style(c, cell_style)
        wb.save(str(path))
        return (
            f"✅ Fila {row_num} añadida en {path.name} [{sheet}]:\n"
            f"   {' | '.join(str(v.get('value', v) if isinstance(v, dict) else v) for v in values)}"
        )
    except ImportError:
        return "openpyxl no instalado. Instala con: pip install openpyxl"
    except Exception as exc:
        return f"Error añadiendo fila: {exc}"


def _tool_xlsx_create_report(args: dict) -> str:
    """Crea un informe Excel formateado con tabla nativa, estilos nombrados y auto-ancho.

    table_style: nombre de estilo de tabla Excel. Default: TableStyleMedium9
      Opciones: TableStyleLight1-21, TableStyleMedium1-28, TableStyleDark1-11
    freeze_header: congela la fila de cabecera (default: True)
    summary_row: añade una fila de totales al final (default: False)
    """
    path         = Path(args.get("path", "")).expanduser()
    sheet        = args.get("sheet", "Informe")
    headers      = args.get("headers", [])
    rows         = args.get("rows", [])
    title        = args.get("title", "")
    table_style  = args.get("table_style", "TableStyleMedium9")
    freeze_hdr   = args.get("freeze_header", True)

    if not path:
        return "Parámetro requerido: path"
    if not headers:
        return "Parámetro requerido: headers (lista de nombres de columnas)"
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.table import Table, TableStyleInfo

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet

        data_start_row = 1

        # Título del informe (por encima de la tabla, sin ser parte de ella)
        if title:
            n_cols = max(len(headers), 1)
            end_col = get_column_letter(n_cols)
            ws.merge_cells(f"A1:{end_col}1")
            c = ws["A1"]
            c.value = title
            c.font = Font(bold=True, size=14, color="1F4E79")
            c.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[1].height = 24
            data_start_row = 2

        # Cabecera + datos
        for c_i, h in enumerate(headers):
            ws.cell(row=data_start_row, column=c_i + 1, value=h)

        for r_i, row_data in enumerate(rows):
            row_list = list(row_data) if not isinstance(row_data, list) else row_data
            for c_i, val in enumerate(row_list):
                ws.cell(row=data_start_row + 1 + r_i, column=c_i + 1, value=val)

        # Crear tabla Excel nativa con estilo nombrado
        end_row    = data_start_row + len(rows)
        end_col_l  = get_column_letter(len(headers))
        table_ref  = f"A{data_start_row}:{end_col_l}{end_row}"
        tbl        = Table(displayName="InformeTabla", ref=table_ref)
        tbl.tableStyleInfo = TableStyleInfo(
            name=table_style,
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(tbl)

        # Congelar cabecera
        if freeze_hdr:
            ws.freeze_panes = ws.cell(row=data_start_row + 1, column=1)

        # Auto-ancho de columnas
        for c_i, h in enumerate(headers):
            col_letter = get_column_letter(c_i + 1)
            max_w = max(
                len(str(h)),
                max((len(str(r[c_i])) for r in rows if c_i < len(r)), default=0),
            )
            ws.column_dimensions[col_letter].width = min(max_w + 4, 60)

        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(path))
        return (
            f"✅ Informe Excel creado: {path.name}\n"
            f"   Hoja: {sheet}  |  Tabla: {table_ref}  |  Estilo: {table_style}\n"
            f"   {len(headers)} columnas · {len(rows)} filas de datos\n"
            f"   Tamaño: {path.stat().st_size:,} bytes"
        )
    except ImportError:
        return "openpyxl no instalado. Instala con: pip install openpyxl"
    except Exception as exc:
        return f"Error creando informe Excel: {exc}"


# ── Nuevas tools Excel avanzadas ──────────────────────────────────────────────


def _tool_apply_cell_formatting(args: dict) -> str:
    """Aplica formato rico (fuente/relleno/borde/alineación) a un rango de celdas Excel."""
    path   = Path(args.get("path", "")).expanduser()
    sheet  = args.get("sheet", None)
    rng    = args.get("range", "A1")
    font   = args.get("font", {})
    fill   = args.get("fill", {})
    border = args.get("border", {})
    align  = args.get("alignment", {})
    nfmt   = args.get("number_format", None)

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

        wb = openpyxl.load_workbook(str(path))
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active

        # Build style objects
        font_obj = None
        if font:
            font_obj = Font(
                name      = font.get("name", "Calibri"),
                size      = font.get("size", 11),
                bold      = font.get("bold", False),
                italic    = font.get("italic", False),
                underline = font.get("underline", None),
                color     = font.get("color", "FF000000"),
                strike    = font.get("strike", False),
            )

        fill_obj = None
        if fill:
            fill_obj = PatternFill(
                start_color = fill.get("color", "FFFFFFFF"),
                end_color   = fill.get("color", "FFFFFFFF"),
                fill_type   = fill.get("type", "solid"),
            )

        border_obj = None
        if border:
            def _side(d, key):
                b = d.get(key, {})
                return Side(style=b.get("style", "thin"), color=b.get("color", "FF000000")) if b else None
            border_obj = Border(
                left   = _side(border, "left")   or (Side(style=border.get("style", "thin")) if "style" in border else None),
                right  = _side(border, "right")  or (Side(style=border.get("style", "thin")) if "style" in border else None),
                top    = _side(border, "top")    or (Side(style=border.get("style", "thin")) if "style" in border else None),
                bottom = _side(border, "bottom") or (Side(style=border.get("style", "thin")) if "style" in border else None),
            )

        align_obj = None
        if align:
            align_obj = Alignment(
                horizontal = align.get("horizontal", None),
                vertical   = align.get("vertical", None),
                wrap_text  = align.get("wrap_text", False),
                text_rotation = align.get("rotation", 0),
            )

        count = 0
        for row in ws[rng]:
            cells = row if isinstance(row, tuple) else (row,)
            for cell in cells:
                if font_obj:
                    cell.font      = font_obj
                if fill_obj:
                    cell.fill      = fill_obj
                if border_obj:
                    cell.border    = border_obj
                if align_obj:
                    cell.alignment = align_obj
                if nfmt:
                    cell.number_format = nfmt
                count += 1

        wb.save(str(path))
        return f"✅ Formato aplicado a {count} celdas en {rng} — {path.name}"
    except Exception as exc:
        return f"Error aplicando formato: {exc}"


def _tool_xlsx_freeze_panes(args: dict) -> str:
    """Congela filas/columnas en una hoja Excel (freeze_panes)."""
    path  = Path(args.get("path", "")).expanduser()
    sheet = args.get("sheet", None)
    cell  = args.get("cell", "B2")

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path))
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active
        ws.freeze_panes = cell if cell != "none" else None
        wb.save(str(path))
        action = "eliminado" if cell == "none" else f"fijado en {cell}"
        return f"✅ Freeze panes {action} en {ws.title} — {path.name}"
    except Exception as exc:
        return f"Error en freeze_panes: {exc}"


def _tool_xlsx_set_column_width(args: dict) -> str:
    """Establece el ancho de columnas en una hoja Excel."""
    path    = Path(args.get("path", "")).expanduser()
    sheet   = args.get("sheet", None)
    columns = args.get("columns", {})
    auto    = args.get("auto", False)

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path))
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active

        if auto:
            for col_cells in ws.columns:
                max_len = 0
                col_letter = col_cells[0].column_letter
                for cell in col_cells:
                    try:
                        val_len = len(str(cell.value)) if cell.value is not None else 0
                        max_len = max(max_len, val_len)
                    except Exception:
                        pass
                ws.column_dimensions[col_letter].width = min(max_len + 2, 50)
            wb.save(str(path))
            return f"✅ Anchos de columna auto-ajustados en {ws.title} — {path.name}"

        if not columns:
            return "Proporciona columns={'A': 20, 'B': 15} o auto=true"

        for col_letter, width in columns.items():
            ws.column_dimensions[col_letter.upper()].width = width
        wb.save(str(path))
        set_cols = ", ".join(f"{k}={v}" for k, v in columns.items())
        return f"✅ Anchos establecidos ({set_cols}) en {ws.title} — {path.name}"
    except Exception as exc:
        return f"Error ajustando anchos: {exc}"


def _tool_xlsx_merge_cells(args: dict) -> str:
    """Fusiona o separa un rango de celdas en Excel."""
    path  = Path(args.get("path", "")).expanduser()
    sheet = args.get("sheet", None)
    rng   = args.get("range", "A1:C1")
    merge = args.get("merge", True)

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path))
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active
        if merge:
            ws.merge_cells(rng)
            action = "fusionadas"
        else:
            ws.unmerge_cells(rng)
            action = "separadas"
        wb.save(str(path))
        return f"✅ Celdas {rng} {action} en {ws.title} — {path.name}"
    except Exception as exc:
        return f"Error fusionando celdas: {exc}"


def _tool_xlsx_add_sheet(args: dict) -> str:
    """Añade, renombra o elimina hojas en un fichero Excel."""
    path      = Path(args.get("path", "")).expanduser()
    action    = args.get("action", "add")
    name      = args.get("name", "HojaNueva")
    new_name  = args.get("new_name", "")
    position  = args.get("position", None)
    copy_from = args.get("copy_from", None)

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path))

        if action == "add":
            if copy_from and copy_from in wb.sheetnames:
                source = wb[copy_from]
                ws = wb.copy_worksheet(source)
                ws.title = name
            else:
                wb.create_sheet(title=name, index=position)
            wb.save(str(path))
            return f"✅ Hoja '{name}' añadida en {path.name}"
        elif action == "rename":
            if name not in wb.sheetnames:
                return f"Hoja '{name}' no encontrada. Hojas: {wb.sheetnames}"
            wb[name].title = new_name or name
            wb.save(str(path))
            return f"✅ Hoja '{name}' renombrada a '{new_name}' — {path.name}"
        elif action == "delete":
            if name not in wb.sheetnames:
                return f"Hoja '{name}' no encontrada. Hojas: {wb.sheetnames}"
            del wb[name]
            wb.save(str(path))
            return f"✅ Hoja '{name}' eliminada — {path.name}"
        elif action == "list":
            return f"Hojas en {path.name}: {wb.sheetnames}"
        else:
            return f"Acción no válida: {action}. Usa: add, rename, delete, list"
    except Exception as exc:
        return f"Error gestionando hoja: {exc}"


def _tool_xlsx_protect_sheet(args: dict) -> str:
    """Protege o desprotege una hoja Excel con contraseña."""
    path     = Path(args.get("path", "")).expanduser()
    sheet    = args.get("sheet", None)
    protect  = args.get("protect", True)
    password = args.get("password", "")
    options  = args.get("options", {})

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path))
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active

        ws.protection.sheet                = protect
        ws.protection.selectLockedCells    = options.get("lock_cells", False)
        ws.protection.selectUnlockedCells  = options.get("lock_unlocked", False)
        ws.protection.formatCells          = not options.get("allow_format_cells", True)
        ws.protection.insertRows           = not options.get("allow_insert_rows", True)
        ws.protection.deleteRows           = not options.get("allow_delete_rows", True)
        ws.protection.sort                 = not options.get("allow_sort", True)
        ws.protection.autoFilter           = not options.get("allow_filter", True)
        if password:
            ws.protection.password = password

        wb.save(str(path))
        action = "protegida" if protect else "desprotegida"
        return f"✅ Hoja '{ws.title}' {action} — {path.name}"
    except Exception as exc:
        return f"Error protegiendo hoja: {exc}"


def _tool_xlsx_add_data_validation(args: dict) -> str:
    """Añade validación de datos (dropdown, rango numérico) a celdas Excel."""
    path     = Path(args.get("path", "")).expanduser()
    sheet    = args.get("sheet", None)
    rng      = args.get("range", "A1")
    val_type = args.get("type", "list")
    formula  = args.get("formula", "")
    items    = args.get("items", [])
    error_msg= args.get("error_message", "Valor no válido")
    prompt   = args.get("prompt", "")

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        import openpyxl
        from openpyxl.worksheet.datavalidation import DataValidation
        wb = openpyxl.load_workbook(str(path))
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active

        if val_type == "list":
            if items:
                formula1 = '"' + ",".join(str(i) for i in items) + '"'
            else:
                formula1 = formula
            dv = DataValidation(type="list", formula1=formula1, allow_blank=True,
                                showErrorMessage=True,
                                error=error_msg, errorTitle="Error de validación",
                                showInputMessage=bool(prompt),
                                prompt=prompt, promptTitle="Selección")
        elif val_type == "whole":
            min_v, max_v = formula.split(":") if ":" in formula else (formula, "")
            dv = DataValidation(type="whole", operator="between",
                                formula1=min_v.strip(), formula2=max_v.strip(),
                                allow_blank=True, showErrorMessage=True,
                                error=error_msg, errorTitle="Error de validación")
        elif val_type == "decimal":
            min_v, max_v = formula.split(":") if ":" in formula else (formula, "")
            dv = DataValidation(type="decimal", operator="between",
                                formula1=min_v.strip(), formula2=max_v.strip(),
                                allow_blank=True, showErrorMessage=True,
                                error=error_msg, errorTitle="Error de validación")
        else:
            dv = DataValidation(type=val_type, formula1=formula, allow_blank=True)

        dv.sqref = rng
        ws.add_data_validation(dv)
        wb.save(str(path))
        return f"✅ Validación '{val_type}' añadida en {rng} — {path.name}"
    except Exception as exc:
        return f"Error añadiendo validación: {exc}"


# ── Nuevas tools Word avanzadas ───────────────────────────────────────────────


def _tool_xlsx_create_table(args: dict) -> str:
    """Crea una tabla Excel con estilo de tabla nombrado (TableStyleMedium9, etc.).

    table_style: nombre de estilo de tabla Excel (TableStyleLight1-21,
                 TableStyleMedium1-28, TableStyleDark1-11).
    El rango de datos se convierte en un objeto Table de Excel nativo con
    filtros, ordenación y formato automático.
    """
    path         = Path(args.get("path", "")).expanduser()
    sheet        = args.get("sheet", "Datos")
    headers      = args.get("headers", [])
    rows         = args.get("rows", [])
    table_style  = args.get("table_style", "TableStyleMedium9")
    table_name   = args.get("table_name", "Tabla1")
    start_cell   = args.get("start_cell", "A1")
    freeze_header = args.get("freeze_header", True)

    if not path:
        return "Parámetro requerido: path"
    if not headers:
        return "Parámetro requerido: headers"

    try:
        import openpyxl
        from openpyxl.utils import get_column_letter, column_index_from_string, coordinate_from_string
        from openpyxl.worksheet.table import Table, TableStyleInfo

        wb = openpyxl.load_workbook(str(path)) if path.exists() else openpyxl.Workbook()
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active
        if ws.title == "Sheet" and sheet:
            ws.title = sheet

        # Determinar celda de inicio
        col_letter, start_row = coordinate_from_string(start_cell)
        start_col = column_index_from_string(col_letter)

        # Escribir cabeceras
        for c_i, h in enumerate(headers):
            ws.cell(row=start_row, column=start_col + c_i, value=h)

        # Escribir filas
        for r_i, row_data in enumerate(rows):
            for c_i, val in enumerate(row_data):
                ws.cell(row=start_row + 1 + r_i, column=start_col + c_i, value=val)

        # Calcular rango de tabla
        end_row = start_row + len(rows)
        end_col = start_col + len(headers) - 1
        end_col_letter = get_column_letter(end_col)
        table_ref = f"{start_cell}:{end_col_letter}{end_row}"

        # Crear tabla Excel nativa
        tbl = Table(displayName=table_name, ref=table_ref)
        tbl.tableStyleInfo = TableStyleInfo(
            name=table_style,
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(tbl)

        # Congelar cabecera
        if freeze_header:
            ws.freeze_panes = ws.cell(row=start_row + 1, column=1)

        # Auto-ancho de columnas
        for c_i, h in enumerate(headers):
            col_letter_i = get_column_letter(start_col + c_i)
            max_w = max(
                len(str(h)),
                max((len(str(r[c_i])) for r in rows if c_i < len(r)), default=0),
            )
            ws.column_dimensions[col_letter_i].width = min(max_w + 4, 60)

        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(path))
        return (
            f"✅ Tabla Excel creada: {path.name}\n"
            f"   Hoja: {ws.title}  Rango: {table_ref}  Estilo: {table_style}\n"
            f"   {len(headers)} columnas · {len(rows)} filas"
        )
    except ImportError:
        return "openpyxl no disponible. Instala con: pip install openpyxl"
    except Exception as exc:
        return f"Error creando tabla Excel: {exc}"


# ── Herramientas — esquemas ──────────────────────────────────────────────────


# ── Tools registry ──────────────────────────────────────────────────────────────


# ── Tools registry ──────────────────────────────────────────────────────────────

_TOOLS = [{'name': 'xlsx_read',
  'description': 'Lee celdas o rango de un archivo Excel (.xlsx) o CSV. Requiere openpyxl para '
                 '.xlsx.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta al fichero .xlsx o .csv'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja (solo .xlsx; por '
                                                          'defecto la primera)'},
                                 'range': {'type': 'string',
                                           'description': "Rango de celdas, p.ej. 'A1:D10' "
                                                          '(pendiente en v1)'},
                                 'limit': {'type': 'integer',
                                           'description': 'Máximo de filas a devolver. Default: '
                                                          '50'}},
                  'required': ['path']}},
 {'name': 'xlsx_write',
  'description': 'Escribe un valor en una celda de un archivo Excel (.xlsx). Crea el fichero si no '
                 'existe.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .xlsx'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja. Default: Hoja1'},
                                 'cell': {'type': 'string', 'description': "Celda, p.ej. 'B3'"},
                                 'value': {'type': ['string', 'number', 'boolean'],
                                           'description': 'Valor a escribir (string, número o '
                                                          'booleano)'},
                                 'style': {'type': 'object',
                                           'description': 'Estilo de la celda (opcional): {"bold": '
                                                          'true, "italic": true, "underline": '
                                                          'true, "font_size": 12, "font_color": '
                                                          '"#FF0000", "bg_color": "#FFFF00", '
                                                          '"align": "center", "wrap_text": true, '
                                                          '"border": true, "number_format": '
                                                          '"#,##0.00"}'}},
                  'required': ['path', 'cell', 'value']}},
 {'name': 'csv_analyze',
  'description': 'Analiza un fichero CSV: cabeceras, primeras filas, estadísticas de columnas '
                 'numéricas.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero CSV'},
                                 'limit': {'type': 'integer',
                                           'description': 'Filas de muestra a mostrar. Default: '
                                                          '5'}},
                  'required': ['path']}},
 {'name': 'xlsx_fill_range',
  'description': 'Escribe múltiples celdas a la vez en un fichero Excel. Ideal para rellenar '
                 'plantillas de informes. Soporta estilos por celda.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta al fichero .xlsx (se crea si no '
                                                         'existe)'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja. Default: Hoja1'},
                                 'cells': {'type': ['object', 'array'],
                                           'description': 'Dict simple {"A1": "Título", "B2": 42} '
                                                          'O lista de objetos [{"cell": "A1", '
                                                          '"value": "Título", "style": {"bold": '
                                                          'true, "bg_color": "#4472C4", '
                                                          '"font_color": "#FFFFFF"}}]'},
                                 'style': {'type': 'object',
                                           'description': 'Estilo global aplicado a todas las '
                                                          'celdas (opcional): {"bold": true, '
                                                          '"italic": true, "font_size": 11, '
                                                          '"font_color": "#000000", "bg_color": '
                                                          '"#FFFFFF", "align": "center", '
                                                          '"wrap_text": false, "border": false, '
                                                          '"number_format": "General"}'}},
                  'required': ['path', 'cells']}},
 {'name': 'xlsx_append_row',
  'description': 'Añade una fila de datos al final de una hoja Excel. Útil para registros de '
                 'incidencias o logs. Soporta estilos por celda.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .xlsx'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja. Default: Hoja1'},
                                 'values': {'type': 'array',
                                            'description': 'Lista de valores para la nueva fila. '
                                                           'Cada elemento puede ser un valor '
                                                           'simple o un objeto {"value": ..., '
                                                           '"style": {"bold": true, "font_color": '
                                                           '"#FF0000", ...}}'},
                                 'style': {'type': 'object',
                                           'description': 'Estilo global para toda la fila '
                                                          '(opcional): {"bold": true, "bg_color": '
                                                          '"#D9E1F2", "border": true, "align": '
                                                          '"center"}'}},
                  'required': ['path', 'values']}},
 {'name': 'xlsx_create_report',
  'description': 'Crea un informe Excel con tabla nativa con estilo nombrado, auto-ancho y '
                 'cabecera congelada.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta del fichero .xlsx a crear'},
                                 'headers': {'type': 'array',
                                             'description': 'Lista de nombres de columnas'},
                                 'rows': {'type': 'array',
                                          'description': 'Lista de listas con los datos (una lista '
                                                         'por fila)'},
                                 'title': {'type': 'string',
                                           'description': 'Título del informe (fila superior '
                                                          'fusionada, opcional)'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja. Default: Informe'},
                                 'table_style': {'type': 'string',
                                                 'description': 'Estilo de tabla Excel. Default: '
                                                                'TableStyleMedium9. Opciones: '
                                                                'TableStyleLight1-21, '
                                                                'TableStyleMedium1-28, '
                                                                'TableStyleDark1-11'},
                                 'freeze_header': {'type': 'boolean',
                                                   'description': 'Congelar fila de cabecera. '
                                                                  'Default: true'}},
                  'required': ['path', 'headers']}},
 {'name': 'xlsx_create_table',
  'description': 'Crea una tabla Excel nativa (objeto Table) con estilo nombrado, filtros y '
                 'ordenación automáticos.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta del fichero .xlsx (se crea si no '
                                                         'existe)'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja. Default: Datos'},
                                 'headers': {'type': 'array',
                                             'description': 'Lista de nombres de columnas'},
                                 'rows': {'type': 'array',
                                          'description': 'Lista de listas de datos'},
                                 'table_style': {'type': 'string',
                                                 'description': 'Estilo de tabla. Default: '
                                                                'TableStyleMedium9'},
                                 'table_name': {'type': 'string',
                                                'description': 'Nombre interno de la tabla Excel. '
                                                               'Default: Tabla1'},
                                 'start_cell': {'type': 'string',
                                                'description': 'Celda de inicio. Default: A1'},
                                 'freeze_header': {'type': 'boolean',
                                                   'description': 'Congelar cabecera. Default: '
                                                                  'true'}},
                  'required': ['path', 'headers']}},
 {'name': 'xlsx_insert_chart',
  'description': 'Inserta una gráfica nativa de openpyxl en una hoja Excel. No requiere '
                 'matplotlib.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .xlsx'},
                                 'chart_type': {'type': 'string',
                                                'description': 'Tipo: bar, line, pie, area, '
                                                               'scatter'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja (por defecto: la '
                                                          'activa)'},
                                 'data_range': {'type': 'string',
                                                'description': "Rango de datos, p.ej. 'A1:C6'. "
                                                               'Primera fila = cabeceras, primera '
                                                               'columna = categorías.'},
                                 'title': {'type': 'string', 'description': 'Título de la gráfica'},
                                 'position': {'type': 'string',
                                              'description': 'Celda donde anclar la gráfica '
                                                             '(default: E2)'},
                                 'width': {'type': 'number',
                                           'description': 'Ancho de la gráfica en cm (default: '
                                                          '15)'},
                                 'height': {'type': 'number',
                                            'description': 'Alto de la gráfica en cm (default: '
                                                           '10)'}},
                  'required': ['path', 'data_range']}},
 {'name': 'xlsx_apply_conditional_format',
  'description': 'Aplica formato condicional (escala de color, barra de datos, iconos, regla de '
                 'celda) a un rango Excel.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .xlsx'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja (por defecto: la '
                                                          'activa)'},
                                 'range': {'type': 'string',
                                           'description': "Rango, p.ej. 'B2:B20'"},
                                 'rule_type': {'type': 'string',
                                               'description': 'Tipo: color_scale, data_bar, '
                                                              'icon_set, cell_is'},
                                 'options': {'type': 'object',
                                             'description': 'Para color_scale: {min, mid, max} en '
                                                            'hex. Para cell_is: {operator, '
                                                            'formula, fill}. Para icon_set: '
                                                            '{icon_style}.'}},
                  'required': ['path', 'range']}},
 {'name': 'apply_cell_formatting',
  'description': 'Aplica formato rico a un rango de celdas Excel: fuente, relleno, borde, '
                 'alineación, formato numérico.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .xlsx'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja (default: activa)'},
                                 'range': {'type': 'string',
                                           'description': 'Rango de celdas: A1, A1:C5, etc.'},
                                 'number_format': {'type': 'string',
                                                   'description': 'Formato numérico: #,##0.00 | '
                                                                  '0.0% | mmm-dd-yy | @'},
                                 'font': {'type': 'object',
                                          'description': '{name, size, bold, italic, '
                                                         "color:'FF000000', underline, strike}"},
                                 'fill': {'type': 'object',
                                          'description': "{color:'FFFF0000', type:'solid'}"},
                                 'border': {'type': 'object',
                                            'description': "{style:'thin'} o {left:{style,color}, "
                                                           'right:{..}, top:{..}, bottom:{..}}'},
                                 'alignment': {'type': 'object',
                                               'description': "{horizontal:'center'|'left'|'right', "
                                                              "vertical:'center', wrap_text:true, "
                                                              'rotation:45}'}},
                  'required': ['path', 'range']}},
 {'name': 'xlsx_freeze_panes',
  'description': "Congela filas/columnas en una hoja Excel. Ej: cell='B2' congela fila 1 y columna "
                 'A.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .xlsx'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja (default: activa)'},
                                 'cell': {'type': 'string',
                                          'description': "Celda de congelación: 'B2', 'A2', 'C1', "
                                                         "'none' para eliminar"}},
                  'required': ['path', 'cell']}},
 {'name': 'xlsx_set_column_width',
  'description': 'Establece el ancho de columnas en Excel. Soporta auto-ajuste o anchos manuales.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .xlsx'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja (default: activa)'},
                                 'auto': {'type': 'boolean',
                                          'description': 'Auto-ajustar todos los anchos al '
                                                         'contenido'},
                                 'columns': {'type': 'object',
                                             'description': "Anchos manuales: {'A': 20, 'B': 15, "
                                                            "'C': 25}"}},
                  'required': ['path']}},
 {'name': 'xlsx_merge_cells',
  'description': 'Fusiona o separa un rango de celdas en Excel.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .xlsx'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja (default: activa)'},
                                 'range': {'type': 'string',
                                           'description': "Rango a fusionar: 'A1:C1', 'B2:D4'"},
                                 'merge': {'type': 'boolean',
                                           'description': 'true=fusionar, false=separar (default: '
                                                          'true)'}},
                  'required': ['path', 'range']}},
 {'name': 'xlsx_add_sheet',
  'description': 'Añade, renombra, elimina o lista hojas en un fichero Excel.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .xlsx'},
                                 'action': {'type': 'string',
                                            'description': 'Acción: add|rename|delete|list'},
                                 'name': {'type': 'string',
                                          'description': 'Nombre de la hoja a operar'},
                                 'new_name': {'type': 'string',
                                              'description': 'Nuevo nombre (para rename)'},
                                 'position': {'type': 'integer',
                                              'description': 'Posición de inserción (para add)'},
                                 'copy_from': {'type': 'string',
                                               'description': 'Nombre de hoja origen (para '
                                                              'copia)'}},
                  'required': ['path', 'action']}},
 {'name': 'xlsx_protect_sheet',
  'description': 'Protege o desprotege una hoja Excel con contraseña opcional.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .xlsx'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja (default: activa)'},
                                 'protect': {'type': 'boolean',
                                             'description': 'true=proteger, false=desproteger '
                                                            '(default: true)'},
                                 'password': {'type': 'string',
                                              'description': 'Contraseña de protección (opcional)'},
                                 'options': {'type': 'object',
                                             'description': '{allow_format_cells, '
                                                            'allow_insert_rows, allow_delete_rows, '
                                                            'allow_sort, allow_filter}'}},
                  'required': ['path']}},
 {'name': 'xlsx_add_data_validation',
  'description': 'Añade validación de datos (lista desplegable, rango numérico) a un rango de '
                 'celdas Excel.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .xlsx'},
                                 'sheet': {'type': 'string',
                                           'description': 'Nombre de la hoja (default: activa)'},
                                 'range': {'type': 'string', 'description': "Rango: 'A1:A100'"},
                                 'type': {'type': 'string',
                                          'description': 'Tipo: list|whole|decimal'},
                                 'items': {'type': 'array',
                                           'description': 'Opciones para dropdown: '
                                                          "['Sí','No','Pendiente']"},
                                 'formula': {'type': 'string',
                                             'description': 'Fórmula alternativa o rango numérico '
                                                            "'min:max'"},
                                 'error_message': {'type': 'string',
                                                   'description': 'Mensaje de error al introducir '
                                                                  'valor inválido'},
                                 'prompt': {'type': 'string',
                                            'description': 'Mensaje de ayuda al seleccionar la '
                                                           'celda'}},
                  'required': ['path', 'range', 'type']}}]


_TOOL_FNS: dict[str, Any] = {
    'xlsx_read'                     : _tool_xlsx_read,
    'xlsx_write'                    : _tool_xlsx_write,
    'csv_analyze'                   : _tool_csv_analyze,
    'xlsx_fill_range'               : _tool_xlsx_fill_range,
    'xlsx_append_row'               : _tool_xlsx_append_row,
    'xlsx_create_report'            : _tool_xlsx_create_report,
    'xlsx_create_table'             : _tool_xlsx_create_table,
    'xlsx_insert_chart'             : _tool_xlsx_insert_chart,
    'xlsx_apply_conditional_format' : _tool_xlsx_apply_conditional_format,
    'apply_cell_formatting'         : _tool_apply_cell_formatting,
    'xlsx_freeze_panes'             : _tool_xlsx_freeze_panes,
    'xlsx_set_column_width'         : _tool_xlsx_set_column_width,
    'xlsx_merge_cells'              : _tool_xlsx_merge_cells,
    'xlsx_add_sheet'                : _tool_xlsx_add_sheet,
    'xlsx_protect_sheet'            : _tool_xlsx_protect_sheet,
    'xlsx_add_data_validation'      : _tool_xlsx_add_data_validation,
}



# ── Prompts ─────────────────────────────────────────────────────────────────────

_PROMPTS: dict[str, dict] = {'create_excel_report': {'description': 'Guía completa para crear un informe Excel (.xlsx) con '
                                        'doc_create. Muestra el uso correcto de hojas con datos, '
                                        'todos los tipos de gráfica nativa O365, formatos '
                                        'condicionales (color_scale, data_bar, cell_is), '
                                        'freeze_panes, column widths, protección de hojas y '
                                        'validación de datos.',
                         'arguments': [{'name': 'title',
                                        'description': 'Título del informe Excel',
                                        'required': True},
                                       {'name': 'sheets',
                                        'description': 'Nombres de las hojas a crear '
                                                       '(comma-separated)',
                                        'required': False},
                                       {'name': 'chart_types',
                                        'description': 'Tipos de gráficas a incluir',
                                        'required': False},
                                       {'name': 'output_path',
                                        'description': 'Ruta de salida para el .xlsx',
                                        'required': False}]},
 'create_dashboard': {'description': 'Crea un dashboard Excel (.xlsx) profesional con doc_create. '
                                     'Incluye hojas de datos y resumen, gráficas nativas O365 '
                                     '(bar/line/pie/doughnut/scatter/stacked), formatos '
                                     'condicionales (color_scale, data_bar, cell_is), columnas '
                                     'ajustadas y paneles congelados.',
                      'arguments': [{'name': 'title',
                                     'description': 'Título del dashboard',
                                     'required': True},
                                    {'name': 'kpis',
                                     'description': 'KPIs a mostrar: ventas, satisfacción, tasa, '
                                                    'etc.',
                                     'required': True},
                                    {'name': 'data',
                                     'description': 'Datos en formato tabla (CSV, descripción o '
                                                    'JSON)',
                                     'required': True},
                                    {'name': 'chart_types',
                                     'description': 'Tipos de gráficas: bar, line, pie, scatter, '
                                                    'doughnut, stacked_bar',
                                     'required': False},
                                    {'name': 'period',
                                     'description': 'Período del dashboard (mes, trimestre, año)',
                                     'required': False},
                                    {'name': 'output_path',
                                     'description': 'Ruta de salida para el .xlsx',
                                     'required': False}]},
 'data_visualization': {'description': 'Selecciona y genera la gráfica O365 nativa más adecuada '
                                       'para los datos y el objetivo. Soporta: bar, column, '
                                       'stacked_bar, stacked_column, line, line_markers, area, '
                                       'pie, doughnut, scatter, radar — todas nativas en docx '
                                       '(insert_chart), xlsx (xlsx_insert_chart) y pptx '
                                       '(pptx_insert_chart).',
                        'arguments': [{'name': 'data_description',
                                       'description': 'Descripción de los datos disponibles '
                                                      '(categorías, series, valores)',
                                       'required': True},
                                      {'name': 'objective',
                                       'description': 'comparar | tendencia | distribución | '
                                                      'correlación | jerarquía | proyecto',
                                       'required': True},
                                      {'name': 'audience',
                                       'description': 'técnica | ejecutiva | general',
                                       'required': False},
                                      {'name': 'format',
                                       'description': 'Formato de salida: docx | xlsx | pptx | png',
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

    if name == "create_excel_report":
        title       = args.get("title", "Informe Excel")
        sheets      = args.get("sheets", "Resumen, Datos")
        chart_types = args.get("chart_types", "column, line, pie")
        out         = args.get("output_path", f"{title.lower().replace(' ','_')}.xlsx" if title else "informe.xlsx")
        sheet_list  = [s.strip() for s in sheets.split(",") if s.strip()]
        prompt = (
            f"Crea el informe Excel '{title}' (.xlsx) con doc_create.\n\n"
            f"HOJAS: {sheets}\nGRÁFICAS: {chart_types}\nSALIDA: {out}\n\n"
            "## HERRAMIENTA: `doc_create` con `sheets`\n\n"
            "```json\n"
            "{\n"
            f'  "output_path": "{out}",\n'
            '  "sheets": [\n'
            "    {\n"
            f'      "name": "{sheet_list[0] if sheet_list else "Resumen"}",\n'
            f'      "title": "{title}",\n'
            '      "headers": ["Col A", "Col B", "Col C", "Col D"],\n'
            '      "rows": [\n'
            '        ["Fila 1", 100, 200, 150],\n'
            '        ["Fila 2", 120, 180, 210]\n'
            '      ],\n'
            "\n      // Gráficas nativas O365 (DrawingML editable):\n"
            '      "charts": [\n'
            '        {\n'
            '          "type": "bar|column|stacked_bar|stacked_column|100_stacked_column|\n'
            '                   line|stacked_line|area|stacked_area|pie|doughnut|scatter",\n'
            '          "title": "Título de la gráfica",\n'
            '          "data_range": "A1:D3",\n'
            '          "position": "F2",\n'
            '          "width": 15,\n'
            '          "height": 10\n'
            '        }\n'
            '      ],\n'
            "\n      // Formatos condicionales:\n"
            '      "conditional_formats": [\n'
            '        {\n'
            '          "range": "B2:B100",\n'
            '          "format_type": "color_scale",\n'
            '          "start_color": "FFAAAA",\n'
            '          "mid_color": "FFFF88",\n'
            '          "end_color": "AAFFAA"\n'
            '        },\n'
            '        {\n'
            '          "range": "C2:C100",\n'
            '          "format_type": "data_bar",\n'
            '          "color": "638EC6"\n'
            '        },\n'
            '        {\n'
            '          "range": "D2:D100",\n'
            '          "format_type": "cell_is",\n'
            '          "operator": "greaterThan",\n'
            '          "formula": "200",\n'
            '          "fill_color": "AAFFAA",\n'
            '          "font_color": "006100"\n'
            '        }\n'
            '      ]\n'
            "    }"
            + (",\n    {\n"
               f'      "name": "{sheet_list[1] if len(sheet_list) > 1 else "Datos"}",\n'
               '      "headers": ["Fecha", "Categoría", "Valor"],\n'
               '      "rows": [["2026-01", "A", 100], ["2026-02", "B", 120]]\n'
               "    }" if len(sheet_list) > 1 else "")
            + "\n  ]\n"
            "}\n"
            "```\n\n"
            "## TIPOS DE GRÁFICA NATIVA O365 PARA XLSX:\n"
            "```\n"
            "bar          — barras horizontales\n"
            "column       — barras verticales  \n"
            "stacked_bar  — barras apiladas horizontal\n"
            "stacked_column — barras apiladas vertical\n"
            "100_stacked_column — 100% apiladas\n"
            "line         — línea simple\n"
            "stacked_line — líneas apiladas\n"
            "area         — área bajo curva\n"
            "stacked_area — área apilada\n"
            "pie          — pastel (<6 categorías)\n"
            "doughnut     — dona\n"
            "scatter      — dispersión XY\n"
            "```\n\n"
            "## HERRAMIENTAS COMPLEMENTARIAS:\n"
            "- `xlsx_freeze_panes(file, cell='A2')` — congela fila de cabecera\n"
            "- `xlsx_set_column_width(file, auto=true)` — ajusta anchos automáticamente\n"
            "- `xlsx_protect_sheet(file, password)` — protege la hoja\n"
            "- `apply_cell_formatting(file, range, font, fill, border)` — formato avanzado de celdas\n"
            "- `xlsx_add_data_validation(file, range, type)` — lista desplegable, fecha, número\n\n"
            "Genera el JSON completo para doc_create con el informe '" + title + "'."
        )

    elif name == "create_dashboard":
        title       = args.get("title", "Dashboard")
        kpis        = args.get("kpis", "")
        data        = args.get("data", "")
        chart_types = args.get("chart_types", "bar, line, pie")
        period      = args.get("period", "período actual")
        out         = args.get("output_path", f"{title.lower().replace(' ','_')}.xlsx" if title else "dashboard.xlsx")
        prompt = (
            f"Crea un dashboard Excel (.xlsx) profesional con doc_create.\n\n"
            f"TÍTULO: {title}\nPERÍODO: {period}\nKPIs: {kpis}\nDATA: {data}\n"
            f"GRÁFICAS: {chart_types}\nSALIDA: {out}\n\n"
            "## HERRAMIENTA: `doc_create` con `sheets`\n\n"
            "```json\n"
            "{\n"
            f'  "output_path": "{out}",\n'
            '  "sheets": [\n'
            "    {\n"
            '      "name": "Resumen",\n'
            '      "title": "' + title + ' — ' + period + '",\n'
            '      "headers": ["KPI", "Objetivo", "Real", "Desviación", "Estado"],\n'
            '      "rows": [\n'
            '        ["KPI 1", "100", "95", "-5%", "⚠"],\n'
            '        ["KPI 2", "200", "210", "+5%", "✅"]\n'
            "      ],\n"
            '      "charts": [\n'
            "        {\n"
            '          "type": "bar|column|stacked_column|100_stacked_column|line|stacked_line|area|pie|doughnut|scatter",\n'
            '          "title": "Título de la gráfica",\n'
            '          "data_range": "A1:C6",\n'
            '          "position": "E2",\n'
            '          "width": 15, "height": 10\n'
            "        }\n"
            "      ],\n"
            '      "conditional_formats": [\n'
            '        {"range": "B2:B20", "format_type": "color_scale",\n'
            '         "start_color": "FFAAAA", "mid_color": "FFFF88", "end_color": "AAFFAA"},\n'
            '        {"range": "C2:C20", "format_type": "data_bar", "color": "638EC6"},\n'
            '        {"range": "D2:D20", "format_type": "cell_is",\n'
            '         "operator": "greaterThan", "formula": "100", "fill_color": "AAFFAA"}\n'
            "      ]\n"
            "    },\n"
            "    {\n"
            '      "name": "Datos",\n'
            '      "headers": ["Fecha", "Categoría", "Valor"],\n'
            '      "rows": [["2026-01", "A", 100], ["2026-02", "B", 120]]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n\n"
            "## ESTRUCTURA REQUERIDA DEL DASHBOARD:\n\n"
            "### Hoja 'Resumen':\n"
            f"- Título: {title} — {period}\n"
            f"- Tabla de KPIs: {kpis}\n"
            "- Gráfica principal de tendencia (line o column)\n"
            "- Formato condicional semáforo RAG en columna de estado\n\n"
            "### Hoja 'Datos' (datos brutos):\n"
            "- Todos los datos fuente con headers descriptivos\n"
            "- Formato condicional data_bar en columnas numéricas\n"
            f"- Gráficas adicionales: {chart_types}\n\n"
            "Genera el JSON completo para una única llamada a doc_create con todos los datos."
            + _tpl_hint
        )

    elif name == "data_visualization":
        desc      = args.get("data_description", "")
        objective = args.get("objective", "")
        audience  = args.get("audience", "general")
        fmt       = args.get("format", "docx")
        prompt = (
            f"Selecciona y genera la visualización más adecuada para los datos y el objetivo.\n\n"
            f"DATOS: {desc}\n"
            f"OBJETIVO: {objective}\n"
            f"AUDIENCIA: {audience}\n"
            f"FORMATO DE SALIDA: {fmt}\n\n"
            "## CATÁLOGO DE TIPOS DISPONIBLES:\n\n"
            "### Gráficas NATIVAS O365 en doc_create (DrawingML — editables en Office):\n"
            "| Tipo | Cuándo usar |\n"
            "|------|--------------|\n"
            "| `bar` | Comparar categorías horizontalmente |\n"
            "| `column` | Comparar categorías verticalmente |\n"
            "| `stacked_bar` | Comparar partes de un todo horizontalmente |\n"
            "| `stacked_column` | Comparar partes de un todo verticalmente |\n"
            "| `100_stacked_column` | Distribución porcentual vertical |\n"
            "| `100_stacked_bar` | Distribución porcentual horizontal |\n"
            "| `line` | Tendencias temporales con una o varias series |\n"
            "| `stacked_line` | Tendencias acumuladas de series |\n"
            "| `area` | Magnitud de tendencia temporal |\n"
            "| `stacked_area` | Composición acumulada temporal |\n"
            "| `pie` | Distribución porcentual (<6 categorías) |\n"
            "| `doughnut` | Igual que pie, con espacio central para KPI |\n"
            "| `scatter` | Correlación entre dos variables continuas |\n"
            "| `radar` | Comparar perfiles multidimensionales (≤8 ejes) |\n\n"
            "Todas se generan con `insert_chart` (Word, OOXML nativo), `xlsx_insert_chart` "
            "(Excel) o `pptx_insert_chart` (PowerPoint) — objetos editables, sin imágenes PNG.\n\n"
            "## RECOMENDACIÓN:\n\n"
            "1. Selecciona el tipo más adecuado para los datos y el objetivo (justifica)\n"
            "2. Si hay varias opciones, ordénalas por efectividad para la audiencia\n"
            "3. Proporciona el JSON exacto de parámetros para la tool elegida:\n"
            "   - Para doc_create (.docx): el bloque `{\"type\": \"chart\", ...}` dentro de content_blocks\n"
            "   - Para doc_create (.xlsx): la entrada `{\"type\": \"bar\", ...}` dentro de `charts` de una hoja\n"
            "   - Para doc_create (.pptx): el bloque `{\"type\": \"chart\", ...}` dentro de `blocks` de un slide\n"
            "   - Para insert_chart (.docx): path, chart_type y data={categories, series}\n\n"
            f"Formato de salida objetivo: **{fmt}**"
        )

    else:
        prompt = f"Prompt {name} no disponible."
    return [{"role": "user", "content": {"type": "text", "text": prompt}}]


# ── Resources ────────────────────────────────────────────────────────────────


# ── Resources ───────────────────────────────────────────────────────────────────


# ── Resources ───────────────────────────────────────────────────────────────────

_RESOURCES = []


_RESOURCE_FNS: dict = {}



# ── Bucle principal ─────────────────────────────────────────────────────────────

def _handle(req: dict) -> None:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "excel-assistant", "version": "1.0.0"},
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
    sys.stderr.write("[excel-assistant] MCP server v1.0.0 iniciado (16 tools, 3 prompts, 0 resources)\n")
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
            sys.stderr.write(f"[excel-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()

