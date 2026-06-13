#!/usr/bin/env python3
"""PowerPoint Assistant MCP Server — presentaciones .pptx para OOCode.

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 newline-delimited JSON).

Crea y edita presentaciones PowerPoint nativas (python-pptx): diapositivas, gráficas,
notas del orador, fondos/temas y lectura de contenido. Soporta plantillas .pptx/.potx.

Presentaciones completas también vía doc_create del word-assistant (.pptx).

Split de office_assistant.py (v0.4.4): documentos Word → word_assistant.py;
hojas Excel → excel_assistant.py.
"""
import json
import sys
from pathlib import Path
from typing import Any, Optional






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

def _tool_pptx_create(args: dict) -> str:
    """Crea una presentación PowerPoint (.pptx).

    Si se provee template_path, usa esa plantilla de empresa heredando su tema,
    masters y layouts. Si no, crea desde cero con un tema de color.

    slides: [{"title": "...", "content": "...", "layout": "bullet|blank|two_col",
              "layout_name": "Title and Content", "notes": "..."}]
    theme: default | dark | light | corporate (solo si no hay template_path)
    """
    path          = Path(args.get("path", "presentation.pptx")).expanduser()
    title         = args.get("title", "Presentación")
    subtitle      = args.get("subtitle", "")
    slides        = args.get("slides", [])
    theme         = args.get("theme", "default")
    template_path = args.get("template_path", "")

    # Si hay plantilla de empresa, delegar a pptx_create_from_template
    if template_path:
        return _tool_pptx_create_from_template({
            "template_path": template_path,
            "output_path": str(path),
            "title": title,
            "subtitle": subtitle,
            "slides": slides,
        })

    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
    except ImportError:
        return "python-pptx no disponible. Instala con: pip install python-pptx"

    _THEMES = {
        "default":   {"bg": RGBColor(0xFF,0xFF,0xFF), "title": RGBColor(0x00,0x46,0x8C), "body": RGBColor(0x26,0x26,0x26)},
        "dark":      {"bg": RGBColor(0x1E,0x1E,0x2E), "title": RGBColor(0x89,0xB4,0xFA), "body": RGBColor(0xCD,0xD6,0xF4)},
        "light":     {"bg": RGBColor(0xF8,0xF9,0xFA), "title": RGBColor(0x21,0x25,0x29), "body": RGBColor(0x44,0x44,0x44)},
        "corporate": {"bg": RGBColor(0xFF,0xFF,0xFF), "title": RGBColor(0x00,0x33,0x66), "body": RGBColor(0x33,0x33,0x33)},
    }
    colors = _THEMES.get(theme, _THEMES["default"])

    prs = Presentation()
    prs.slide_width  = Inches(13.33)
    prs.slide_height = Inches(7.5)

    def _set_bg(slide):
        bg = slide.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = colors["bg"]

    def _fill_content(slide, content: str):
        for ph in slide.placeholders:
            if ph.placeholder_format.idx == 1:
                tf = ph.text_frame
                tf.text = ""
                for line in content.split("\n"):
                    if line.strip():
                        p = tf.add_paragraph()
                        p.text = line.strip().lstrip("•-* ")
                        p.level = 1 if line.startswith(("  ", "\t")) else 0
                        for run in p.runs:
                            run.font.color.rgb = colors["body"]
                            run.font.size = Pt(18)
                break

    # Diapositiva de título
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    _set_bg(slide)
    if slide.shapes.title:
        slide.shapes.title.text = title
    if subtitle:
        for ph in slide.placeholders:
            if ph.placeholder_format.idx == 1:
                ph.text = subtitle
                break

    # Diapositivas de contenido
    for sl in slides:
        sl_layout_nm = sl.get("layout", "bullet")
        layout_idx = {"bullet": 1, "blank": 6, "two_col": 3}.get(sl_layout_nm, 1)
        sl_obj = prs.slides.add_slide(prs.slide_layouts[min(layout_idx, len(prs.slide_layouts)-1)])
        _set_bg(sl_obj)
        if sl_obj.shapes.title:
            sl_obj.shapes.title.text = sl.get("title", "")
        _fill_content(sl_obj, sl.get("content", ""))
        if sl.get("notes"):
            try:
                sl_obj.notes_slide.notes_text_frame.text = sl["notes"]
            except Exception:
                pass

    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return f"✅ Presentación creada: {path.name}  |  Tema: {theme}  |  {len(prs.slides)} diapositivas"


def _tool_pptx_add_slide(args: dict) -> str:
    """Añade una diapositiva a una presentación .pptx existente."""
    path    = Path(args.get("path", "")).expanduser()
    title   = args.get("title", "")
    content = args.get("content", "")
    layout  = args.get("layout", "bullet")  # bullet, blank, two_col, image
    notes   = args.get("notes", "")
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        from pptx import Presentation
        from pptx.util import Pt
        prs = Presentation(str(path))
        layout_idx = {"bullet": 1, "blank": 6, "two_col": 3, "title_only": 5}.get(layout, 1)
        sl = prs.slides.add_slide(prs.slide_layouts[min(layout_idx, len(prs.slide_layouts)-1)])
        if sl.shapes.title:
            sl.shapes.title.text = title
        for ph in sl.placeholders:
            if ph.placeholder_format.idx == 1:
                tf = ph.text_frame
                tf.text = ""
                for line in content.split("\n"):
                    if line.strip():
                        p = tf.add_paragraph()
                        p.text = line.strip().lstrip("•-* ")
                        p.level = 1 if line.startswith(("  ", "\t")) else 0
                        for run in p.runs:
                            run.font.size = Pt(18)
                break
        if notes:
            sl.notes_slide.notes_text_frame.text = notes
        prs.save(str(path))
        return f"✅ Diapositiva añadida a: {path}\n   Total diapositivas: {len(prs.slides)}"
    except ImportError:
        return "python-pptx no disponible. Instala con: pip install python-pptx"
    except Exception as exc:
        return f"Error añadiendo diapositiva: {exc}"


def _tool_pptx_insert_chart(args: dict) -> str:
    """Inserta una gráfica NATIVA de python-pptx en una presentación .pptx.

    Las gráficas son vectoriales y editables en PowerPoint/LibreOffice Impress.
    No requiere matplotlib ni genera imágenes PNG.

    chart_type: column_clustered | column_stacked | bar_clustered | bar_stacked |
                line | line_markers | pie | doughnut | area | scatter
    series: [{label: "Ventas", values: [10, 20, 30]}, ...]
    categories: ["Ene", "Feb", "Mar"]
    slide_index: índice de diapositiva (0-based, -1 = última)
    """
    path        = Path(args.get("path", "")).expanduser()
    chart_type  = args.get("chart_type", "column_clustered").lower()
    categories  = args.get("categories", [])
    series_list = args.get("series", [])
    title       = args.get("title", "")
    slide_index = int(args.get("slide_index", -1))
    left_in     = float(args.get("left", 1.0))
    top_in      = float(args.get("top", 2.0))
    width_in    = float(args.get("width", 8.0))
    height_in   = float(args.get("height", 4.5))
    output_path = args.get("output_path", "")

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    if not series_list:
        return "Parámetro requerido: series=[{label, values}, ...]"
    if not categories:
        return "Parámetro requerido: categories=[...]"

    try:
        from pptx import Presentation
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE
        from pptx.util import Inches
    except ImportError:
        return "python-pptx no disponible. Instala con: pip install python-pptx"

    _CHART_TYPE_MAP = {
        "column_clustered":   XL_CHART_TYPE.COLUMN_CLUSTERED,
        "column_stacked":     XL_CHART_TYPE.COLUMN_STACKED,
        "column_stacked_100": XL_CHART_TYPE.COLUMN_STACKED_100,
        "bar_clustered":      XL_CHART_TYPE.BAR_CLUSTERED,
        "bar_stacked":        XL_CHART_TYPE.BAR_STACKED,
        "line":               XL_CHART_TYPE.LINE,
        "line_markers":       XL_CHART_TYPE.LINE_MARKERS,
        "pie":                XL_CHART_TYPE.PIE,
        "doughnut":           XL_CHART_TYPE.DOUGHNUT,
        "area":               XL_CHART_TYPE.AREA,
        "area_stacked":       XL_CHART_TYPE.AREA_STACKED,
        "scatter":            XL_CHART_TYPE.XY_SCATTER,
        "scatter_smooth":     XL_CHART_TYPE.XY_SCATTER_SMOOTH,
        "radar":              XL_CHART_TYPE.RADAR,
    }
    xl_type = _CHART_TYPE_MAP.get(chart_type)
    if xl_type is None:
        return (f"Tipo no soportado: {chart_type}. Usa: "
                + ", ".join(_CHART_TYPE_MAP.keys()))

    try:
        prs = Presentation(str(path))
        n_slides = len(prs.slides)
        if n_slides == 0:
            return "La presentación no tiene diapositivas. Añade una primero con pptx_add_slide."

        # Seleccionar diapositiva
        idx = slide_index if slide_index >= 0 else n_slides - 1
        idx = max(0, min(idx, n_slides - 1))
        slide = prs.slides[idx]

        # Construir datos de la gráfica
        chart_data = CategoryChartData()
        chart_data.categories = categories
        for serie in series_list:
            chart_data.add_series(serie.get("label", "Serie"), serie.get("values", []))

        # Añadir gráfica a la diapositiva
        chart_shape = slide.shapes.add_chart(
            xl_type,
            Inches(left_in), Inches(top_in),
            Inches(width_in), Inches(height_in),
            chart_data,
        )
        chart = chart_shape.chart

        # Título
        if title:
            chart.has_title = True
            chart.chart_title.text_frame.text = title

        # Leyenda si hay más de 1 serie
        chart.has_legend = len(series_list) > 1
        if chart.has_legend:
            from pptx.enum.chart import XL_LEGEND_POSITION
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False

        dest = output_path or str(path)
        prs.save(dest)
        return (f"✅ Gráfica nativa '{chart_type}' insertada en {path}\n"
                f"   Diapositiva: {idx+1}/{n_slides}  Series: {len(series_list)}  "
                f"Categorías: {len(categories)}")

    except Exception as exc:
        return f"Error insertando gráfica PPTX: {exc}"


def _tool_pptx_read(args: dict) -> str:
    """Lee el contenido de texto de una presentación .pptx."""
    path   = Path(args.get("path", "")).expanduser()
    slides = args.get("slides", "")  # "1-3", "2", "" = todas
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        from pptx import Presentation
        prs = Presentation(str(path))
        n_total = len(prs.slides)
        # Parsear rango de diapositivas
        if slides:
            parts = slides.split("-")
            start = max(1, int(parts[0])) - 1
            end   = min(n_total, int(parts[1]) if len(parts) > 1 else int(parts[0]))
        else:
            start, end = 0, n_total
        lines = [f"📊 Presentación: {path.name}  |  {n_total} diapositivas"]
        for i, sl in enumerate(list(prs.slides)[start:end], start + 1):
            lines.append(f"\n── Diapositiva {i} ──────────────────────")
            for shape in sl.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        txt = para.text.strip()
                        if txt:
                            prefix = "  • " if para.level > 0 else "  "
                            lines.append(f"{prefix}{txt}")
            if sl.has_notes_slide:
                notes = sl.notes_slide.notes_text_frame.text.strip()
                if notes:
                    lines.append(f"  [Notas: {notes[:120]}{'…' if len(notes)>120 else ''}]")
        return "\n".join(lines)
    except ImportError:
        return "python-pptx no disponible. Instala con: pip install python-pptx"
    except Exception as exc:
        return f"Error leyendo presentación: {exc}"


def _tool_pptx_add_notes(args: dict) -> str:
    """Añade notas del presentador a una o varias diapositivas."""
    path      = Path(args.get("path", "")).expanduser()
    slide_idx = args.get("slide_index", 0)
    notes     = args.get("notes", "")
    append    = args.get("append", False)

    if not path.exists():
        return f"Fichero no encontrado: {path}"
    try:
        from pptx import Presentation

        prs   = Presentation(str(path))
        n_sld = len(prs.slides)

        if slide_idx == -1 or slide_idx == "all":
            targets = list(range(n_sld))
        elif isinstance(slide_idx, list):
            targets = [i for i in slide_idx if 0 <= i < n_sld]
        else:
            targets = [int(slide_idx)] if 0 <= int(slide_idx) < n_sld else []

        if not targets:
            return f"Índice de diapositiva inválido. El fichero tiene {n_sld} diapositivas (0..{n_sld-1})."

        changed = []
        for i in targets:
            slide      = prs.slides[i]
            notes_sld  = slide.notes_slide
            tf         = notes_sld.notes_text_frame
            if append and tf.text:
                tf.text = tf.text + "\n" + notes
            else:
                tf.text = notes
            changed.append(i)

        prs.save(str(path))
        return f"✅ Notas añadidas a diapositivas {changed} — {path.name}"
    except ImportError:
        return "python-pptx no disponible. Instala: pip install python-pptx"
    except Exception as exc:
        return f"Error añadiendo notas: {exc}"


def _tool_pptx_set_background(args: dict) -> str:
    """Establece el fondo de una o todas las diapositivas (.pptx)."""
    path      = Path(args.get("path", "")).expanduser()
    slide_idx = args.get("slide_index", "all")
    bg_type   = args.get("type", "solid")
    color     = args.get("color", "#FFFFFF")
    grad_from = args.get("gradient_from", "#FFFFFF")
    grad_to   = args.get("gradient_to", "#CCCCCC")
    image_path= args.get("image_path", "")

    if not path.exists():
        return f"Fichero no encontrado: {path}"

    def _hex_to_rgb(h: str):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor as PptxRGB

        prs   = Presentation(str(path))
        n_sld = len(prs.slides)

        if slide_idx == "all":
            targets = list(range(n_sld))
        elif isinstance(slide_idx, list):
            targets = [i for i in slide_idx if 0 <= i < n_sld]
        else:
            targets = [int(slide_idx)] if 0 <= int(slide_idx) < n_sld else []

        if not targets:
            return f"Índice inválido. El fichero tiene {n_sld} diapositivas."

        for i in targets:
            slide  = prs.slides[i]

            if bg_type == "solid":
                r, g, b = _hex_to_rgb(color)
                fill = slide.background.fill
                fill.solid()
                fill.fore_color.rgb = PptxRGB(r, g, b)

            elif bg_type == "gradient":
                fill = slide.background.fill
                fill.gradient()
                gs   = fill.gradient_stops
                r1, g1, b1 = _hex_to_rgb(grad_from)
                r2, g2, b2 = _hex_to_rgb(grad_to)
                gs[0].color.rgb = PptxRGB(r1, g1, b1)
                gs[1].color.rgb = PptxRGB(r2, g2, b2)

            elif bg_type == "image" and image_path:
                img  = Path(image_path).expanduser()
                if img.exists():
                    sp = slide.shapes.add_picture(
                        str(img), 0, 0, prs.slide_width, prs.slide_height
                    )
                    slide.shapes._spTree.remove(sp._element)
                    slide.shapes._spTree.insert(2, sp._element)

        prs.save(str(path))
        return f"✅ Fondo '{bg_type}' aplicado a diapositivas {targets} — {path.name}"
    except ImportError:
        return "python-pptx no disponible. Instala: pip install python-pptx"
    except Exception as exc:
        return f"Error estableciendo fondo: {exc}"


# ── Nuevas tools de creación de documentos O365 ───────────────────────────────


def _tool_pptx_create_from_template(args: dict) -> str:
    """Crea una presentación .pptx nueva usando una plantilla de empresa (.pptx/.potx).

    Hereda todos los masters, layouts, fuentes, colores y tema de la plantilla.
    Añade diapositivas especificadas en slides usando los layouts disponibles.

    slides: lista de {"title": "...", "content": "...", "layout_name": "Title and Content",
                       "notes": "...", "image_path": "/ruta/img.png"}
    """
    template_path = args.get("template_path", "")
    output_path   = args.get("output_path", "presentation.pptx")
    title         = args.get("title", "")
    subtitle      = args.get("subtitle", "")
    slides        = args.get("slides", [])

    if not template_path:
        return "Parámetro requerido: template_path (.pptx o .potx de la empresa)"

    tpl = Path(template_path).expanduser()
    if not tpl.exists():
        return f"Plantilla no encontrada: {tpl}"

    out = Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        from pptx import Presentation
        from pptx.util import Inches

        prs = Presentation(str(tpl))

        # Mapa de layouts por nombre
        layout_map: dict = {}
        for layout in prs.slide_layouts:
            layout_map[layout.name] = layout

        def _find_layout(name: str):
            if name in layout_map:
                return layout_map[name]
            for lname, layout in layout_map.items():
                if name.lower() in lname.lower():
                    return layout
            return prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0]

        def _set_placeholder(slide, idx: int, text: str) -> bool:
            for ph in slide.placeholders:
                if ph.placeholder_format.idx == idx:
                    tf = ph.text_frame
                    tf.text = ""
                    for line in text.split("\n"):
                        p = tf.add_paragraph()
                        p.text = line.strip().lstrip("•-* ")
                        p.level = 1 if line.startswith(("  ", "\t")) else 0
                    return True
            return False

        # Diapositiva de título
        if title:
            title_layout = _find_layout("Title Slide")
            sl = prs.slides.add_slide(title_layout)
            if sl.shapes.title:
                sl.shapes.title.text = title
            _set_placeholder(sl, 1, subtitle)

        # Diapositivas de contenido
        for sl_def in slides:
            layout_name = sl_def.get("layout_name", "Title and Content")
            layout      = _find_layout(layout_name)
            sl          = prs.slides.add_slide(layout)
            if sl.shapes.title:
                sl.shapes.title.text = sl_def.get("title", "")
            _set_placeholder(sl, 1, sl_def.get("content", ""))

            # Imagen
            img_p = sl_def.get("image_path", "")
            if img_p:
                img_path = Path(img_p).expanduser()
                if img_path.exists():
                    try:
                        sl.shapes.add_picture(str(img_path), Inches(1), Inches(2), Inches(8))
                    except Exception:
                        pass

            # Notas del presentador
            notes = sl_def.get("notes", "")
            if notes:
                try:
                    sl.notes_slide.notes_text_frame.text = notes
                except Exception:
                    pass

        prs.save(str(out))
        return (
            f"✅ Presentación creada: {out.name}\n"
            f"   Plantilla: {tpl.name}\n"
            f"   Layouts disponibles: {', '.join(list(layout_map.keys())[:6])}{'…' if len(layout_map) > 6 else ''}\n"
            f"   Diapositivas: {len(prs.slides)}"
        )
    except ImportError:
        return "python-pptx no disponible. Instala con: pip install python-pptx"
    except Exception as exc:
        return f"Error creando presentación desde plantilla: {exc}"


# ── Tools registry ──────────────────────────────────────────────────────────────

_TOOLS = [{'name': 'pptx_create_from_template',
  'description': 'Crea una presentación .pptx NUEVA desde una plantilla de empresa (.pptx/.potx), '
                 'heredando el tema, masters y layouts. USAR cuando el usuario tiene plantillas '
                 'corporativas.',
  'inputSchema': {'type': 'object',
                  'properties': {'template_path': {'type': 'string',
                                                   'description': 'Ruta a la plantilla .pptx o '
                                                                  '.potx de la empresa'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta del fichero de salida .pptx'},
                                 'title': {'type': 'string',
                                           'description': 'Título de la presentación (diapositiva '
                                                          'de portada)'},
                                 'subtitle': {'type': 'string',
                                              'description': 'Subtítulo de la portada'},
                                 'slides': {'type': 'array',
                                            'description': 'Lista de diapositivas: [{title, '
                                                           'content, layout_name, notes, '
                                                           'image_path}]. layout_name debe '
                                                           'coincidir con los layouts de la '
                                                           'plantilla'}},
                  'required': ['template_path', 'output_path']}},
 {'name': 'pptx_create',
  'description': 'Crea una presentación PowerPoint (.pptx). Si se indica template_path, usa la '
                 'plantilla de empresa (equivale a pptx_create_from_template). Si no, usa un tema '
                 'de color.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string',
                                          'description': 'Ruta del fichero .pptx a crear'},
                                 'title': {'type': 'string',
                                           'description': 'Título de la presentación'},
                                 'subtitle': {'type': 'string',
                                              'description': 'Subtítulo (opcional)'},
                                 'theme': {'type': 'string',
                                           'description': 'Tema visual: default, dark, light, '
                                                          'corporate (solo sin template_path)'},
                                 'template_path': {'type': 'string',
                                                   'description': 'Plantilla .pptx/.potx de '
                                                                  'empresa (opcional; si se da, '
                                                                  'hereda tema y layouts)'},
                                 'slides': {'type': 'array',
                                            'description': 'Diapositivas: [{title, content, '
                                                           'layout, layout_name, notes}]'}},
                  'required': ['path']}},
 {'name': 'pptx_add_slide',
  'description': 'Añade una diapositiva a una presentación .pptx existente.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .pptx'},
                                 'title': {'type': 'string',
                                           'description': 'Título de la diapositiva'},
                                 'content': {'type': 'string',
                                             'description': 'Contenido (bullet points, uno por '
                                                            'línea). Prefija con 2 espacios para '
                                                            'nivel 2.'},
                                 'layout': {'type': 'string',
                                            'description': 'Diseño: bullet (predeterminado), '
                                                           'blank, two_col, title_only'},
                                 'notes': {'type': 'string',
                                           'description': 'Notas del presentador (opcional)'}},
                  'required': ['path']}},
 {'name': 'pptx_read',
  'description': 'Lee el contenido de texto de una presentación .pptx, diapositiva por '
                 'diapositiva.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .pptx'},
                                 'slides': {'type': 'string',
                                            'description': "Rango de diapositivas, p.ej. '1-5' o "
                                                           "'3'. Omitir = todas."}},
                  'required': ['path']}},
 {'name': 'pptx_insert_chart',
  'description': 'Inserta una gráfica NATIVA de python-pptx en una diapositiva existente. Las '
                 'gráficas son vectoriales y editables en PowerPoint/LibreOffice. Usa '
                 'CategoryChartData para tipos de barra/columna/línea/tarta. Tipos: '
                 'column_clustered, column_stacked, bar_clustered, bar_stacked, line, '
                 'line_markers, pie, doughnut, area, scatter, radar.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al fichero .pptx'},
                                 'chart_type': {'type': 'string',
                                                'description': 'Tipo de gráfica: column_clustered, '
                                                               'bar_clustered, line, pie, '
                                                               'doughnut, area, scatter, radar'},
                                 'categories': {'type': 'array',
                                                'description': "Categorías del eje X: ['Ene', "
                                                               "'Feb', 'Mar']"},
                                 'series': {'type': 'array',
                                            'description': "Series: [{label: 'Ventas', values: "
                                                           '[10,20,30]}, ...]'},
                                 'title': {'type': 'string', 'description': 'Título de la gráfica'},
                                 'slide_index': {'type': 'integer',
                                                 'description': 'Índice de diapositiva (0-based, '
                                                                '-1=última)'},
                                 'left': {'type': 'number',
                                          'description': 'Posición izquierda en pulgadas (default: '
                                                         '1.0)'},
                                 'top': {'type': 'number',
                                         'description': 'Posición superior en pulgadas (default: '
                                                        '2.0)'},
                                 'width': {'type': 'number',
                                           'description': 'Ancho en pulgadas (default: 8.0)'},
                                 'height': {'type': 'number',
                                            'description': 'Alto en pulgadas (default: 4.5)'},
                                 'output_path': {'type': 'string',
                                                 'description': 'Ruta de salida (omitir = '
                                                                'sobreescribe el original)'}},
                  'required': ['path', 'categories', 'series']}},
 {'name': 'pptx_add_notes',
  'description': 'Añade notas del presentador a una o varias diapositivas de un .pptx.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .pptx'},
                                 'slide_index': {'type': ['integer', 'array', 'string'],
                                                 'description': 'Índice de diapositiva '
                                                                '(0=primera), lista de índices, o '
                                                                "'all'"},
                                 'notes': {'type': 'string',
                                           'description': 'Texto de las notas del presentador'},
                                 'append': {'type': 'boolean',
                                            'description': 'Añadir al final en lugar de reemplazar '
                                                           '(default: false)'}},
                  'required': ['path', 'notes']}},
 {'name': 'pptx_set_background',
  'description': 'Establece el fondo de una o todas las diapositivas: sólido, gradiente o imagen.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string', 'description': 'Ruta al .pptx'},
                                 'slide_index': {'type': ['integer', 'array', 'string'],
                                                 'description': 'Índice (0=primera), lista, o '
                                                                "'all' para todas"},
                                 'type': {'type': 'string',
                                          'description': 'Tipo de fondo: solid|gradient|image'},
                                 'color': {'type': 'string',
                                           'description': "Color sólido en hex: '#1F4E79'"},
                                 'gradient_from': {'type': 'string',
                                                   'description': 'Color inicial del gradiente: '
                                                                  "'#1F4E79'"},
                                 'gradient_to': {'type': 'string',
                                                 'description': 'Color final del gradiente: '
                                                                "'#FFFFFF'"},
                                 'image_path': {'type': 'string',
                                                'description': 'Ruta a imagen PNG/JPG para fondo '
                                                               'de imagen'}},
                  'required': ['path', 'type']}}]


_TOOL_FNS: dict[str, Any] = {
    'pptx_create_from_template' : _tool_pptx_create_from_template,
    'pptx_create'               : _tool_pptx_create,
    'pptx_add_slide'            : _tool_pptx_add_slide,
    'pptx_read'                 : _tool_pptx_read,
    'pptx_insert_chart'         : _tool_pptx_insert_chart,
    'pptx_add_notes'            : _tool_pptx_add_notes,
    'pptx_set_background'       : _tool_pptx_set_background,
}



# ── Prompts ─────────────────────────────────────────────────────────────────────

_PROMPTS: dict[str, dict] = {'create_presentation': {'description': 'Crea una presentación PowerPoint (.pptx) nativa O365 con '
                                        'doc_create. Soporta diapositivas con bloques avanzados: '
                                        'gráficas nativas (chart), tablas, imágenes, texto. '
                                        'Produce un .pptx real con estilos Office, no una imagen '
                                        'ni un PDF.',
                         'arguments': [{'name': 'topic',
                                        'description': 'Tema de la presentación',
                                        'required': True},
                                       {'name': 'audience',
                                        'description': 'Audiencia: técnica/ejecutiva/mixta',
                                        'required': False},
                                       {'name': 'slides',
                                        'description': 'Número aproximado de diapositivas '
                                                       '(default: 8)',
                                        'required': False},
                                       {'name': 'context',
                                        'description': 'Puntos clave, datos o contexto a incluir',
                                        'required': False},
                                       {'name': 'language',
                                        'description': 'Idioma (español por defecto)',
                                        'required': False},
                                       {'name': 'template_path',
                                        'description': 'Ruta a plantilla .pptx/.potx corporativa',
                                        'required': False},
                                       {'name': 'output_path',
                                        'description': 'Ruta de salida para el .pptx',
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

    if name == "create_presentation":
        topic       = args.get("topic", "")
        audience    = args.get("audience", "mixta")
        n_slides    = args.get("slides", "8")
        context     = args.get("context", "")
        lang        = args.get("language", "español")
        tpl         = args.get("template_path", "")
        out         = args.get("output_path", f"{topic.lower().replace(' ','_')}.pptx" if topic else "presentacion.pptx")
        ctx_str     = f"\n\nCONTEXTO / PUNTOS CLAVE:\n{context}" if context else ""
        tpl_str     = f"\n\nPLANTILLA CORPORATIVA: {tpl}\n→ Usa pptx_create_from_template en lugar de doc_create." if tpl else ""
        prompt = (
            f"Crea una presentación PowerPoint (.pptx) nativa O365 en {lang} usando doc_create.{ctx_str}{tpl_str}\n\n"
            f"TEMA: {topic}\nAUDIENCIA: {audience}\nDIAPOSITIVAS: {n_slides}\n"
            f"SALIDA: {out}\n\n"
            "## HERRAMIENTA A USAR: `doc_create`\n\n"
            "```json\n"
            "{\n"
            f'  "output_path": "{out}",\n'
            '  "slides": [\n'
            "    {\n"
            '      "title": "Título de la presentación",\n'
            '      "content": "Subtítulo o tagline",\n'
            '      "layout": "bullet"\n'
            "    },\n"
            "    {\n"
            '      "title": "Agenda",\n'
            '      "content": "1. Punto 1\\n2. Punto 2\\n3. Punto 3",\n'
            '      "layout": "bullet"\n'
            "    },\n"
            "    {\n"
            '      "title": "Diapositiva con gráfica nativa",\n'
            '      "layout": "blank",\n'
            '      "blocks": [\n'
            '        {"type": "chart", "chart_type": "bar|column|line|pie|doughnut|scatter",\n'
            '         "title": "Título gráfica", "x": 0.5, "y": 1.5, "width": 8, "height": 4.5,\n'
            '         "data": {"categories": ["A","B","C"], "series": [{"label": "Serie 1", "values": [10,20,30]}]}}\n'
            "      ]\n"
            "    },\n"
            "    {\n"
            '      "title": "Diapositiva con tabla",\n'
            '      "layout": "blank",\n'
            '      "blocks": [\n'
            '        {"type": "table", "headers": ["Col1","Col2","Col3"],\n'
            '         "rows": [["A","B","C"],["D","E","F"]], "x": 0.5, "y": 1.5, "width": 12}\n'
            "      ]\n"
            "    },\n"
            "    {\n"
            '      "title": "Dos columnas",\n'
            '      "layout": "two_col",\n'
            '      "content": "Columna izquierda\\n• Punto 1\\n• Punto 2"\n'
            "    },\n"
            "    {\n"
            '      "title": "Conclusiones",\n'
            '      "content": "• Conclusión 1\\n• Conclusión 2\\n• Próximos pasos",\n'
            '      "layout": "bullet",\n'
            '      "notes": "Notas del presentador aquí"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n\n"
            f"## ESTRUCTURA REQUERIDA ({n_slides} diapositivas, audiencia: {audience}):\n\n"
            "1. [PORTADA] — título, subtítulo, fecha\n"
            "2. [AGENDA] — puntos de la presentación\n"
            "3-N. [CONTENIDO] — adaptar por punto: bullet, tabla o gráfica según datos\n"
            f"   - Audiencia {audience}: "
            + ("gráficas y datos concretos, sin adornos" if audience == "técnica"
               else "resumen visual, KPIs, mínimo texto" if audience == "ejecutiva"
               else "mezcla de texto y datos visuales")
            + "\n"
            "N-1. [CONCLUSIONES] — 3-5 bullets con próximos pasos\n"
            "N. [PREGUNTAS / CONTACTO]\n\n"
            "Genera el JSON completo para doc_create con todas las diapositivas."
            + _tpl_hint
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
            "serverInfo": {"name": "pptx-assistant", "version": "1.0.0"},
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
    sys.stderr.write("[pptx-assistant] MCP server v1.0.0 iniciado (7 tools, 1 prompts, 0 resources)\n")
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
            sys.stderr.write(f"[pptx-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()

