#!/usr/bin/env python3
"""Home Office Assistant MCP Server — secretaria IT eficaz para OOCode.

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 newline-delimited JSON).

Configuración: ~/.oocode/home_office.json  (ver _load_config() para esquema completo)
Proyecto:      OOCODE.md en cwd (templates_dir, docs_dir, naming, client, project_type)
Local:         .oocode-office.json en cwd (override de cualquier clave de config)

Tools (77):
  ── Email ──
  email_list          — lista emails de la bandeja de entrada (IMAP)
  email_read          — lee un email por UID o índice
  email_send          — envía un email (SMTP)
  email_search        — busca emails por criterio (IMAP SEARCH)
  ── Documentos O365 (núcleo) ──
  doc_create          — ★ NUEVA: crea .docx/.xlsx/.pptx con estilos O365 reales desde cero
                         Calibri/Calibri Light, colores Office theme, tablas nativas, TOC,
                         firma, bullets, heading hierarchy; markdown o content_blocks
  doc_fill_template   — rellena plantillas .docx/.xlsx/.pptx con campos
                         Motor primario: docxtpl/Jinja2 ({{ campo }}, loops, condicionales)
                         Preserva 100% los estilos originales de la plantilla de empresa
  doc_create_from_template — crea .docx desde plantilla con content_blocks + campos Jinja2
  doc_create_rfc      — genera RFC/Change Request .docx con estilos O365
  doc_apply_style     — aplica nombre de estilo Word a párrafos de un .docx
  doc_set_table_style — aplica estilo de tabla Word nativo a tablas existentes
  apply_document_theme — aplica tema de color/fuentes a todos los estilos de un .docx
  set_paragraph_format — formatea párrafos por índice (alineación, sangría, espaciado)
  doc_add_header_footer — añade cabecera/pie de página con número de página
  doc_add_toc         — inserta campo TOC (tabla de contenido) en un .docx
  doc_add_content_block — añade bloques a un .docx existente sin borrar contenido
  doc_set_page_layout — configura tamaño de página, orientación y márgenes
  doc_embed_image           — incrusta imagen en .docx con ancho configurable
  doc_insert_diagram        — inserta diagramas y gráficas en documentos .docx (PNG)
  doc_insert_chart_native   — ★ NUEVA: gráfica de alta calidad multi-series en .docx
                               (bar/line/pie/doughnut/area/scatter, estilos Office)
  doc_extract_metadata — extrae metadatos de .docx/.pptx/.pdf
  doc_compare         — diff unificado entre dos documentos
  doc_read_template_fields — extrae campos {{CAMPO}} de una plantilla
  doc_list_templates  — lista plantillas disponibles (.docx/.xlsx/.md)
  doc_convert         — convierte documentos con pandoc (md→pdf, docx→md, etc.)
  doc_word_count      — cuenta palabras, líneas y caracteres de un documento
  markdown_to_html    — convierte markdown a HTML
  pdf_extract_text    — extrae texto de un PDF (pdftotext o pdfplumber)
  doc_read            — lee contenido de .docx/.md; extrae sección opcional
  doc_update_section  — reemplaza contenido de una sección en .md/.docx
  doc_version_bump    — incrementa version: X.Y.Z en front matter YAML
  ── Hojas de cálculo ──
  xlsx_read           — lee celdas o rango de un archivo Excel o CSV
  xlsx_write          — escribe una celda en un archivo Excel (.xlsx)
  xlsx_fill_range     — escribe múltiples celdas a la vez en Excel
  xlsx_append_row     — añade una fila al final de una hoja Excel
  xlsx_create_report  — crea un informe Excel formateado con estilos
  csv_analyze         — análisis de CSV: cabeceras, primeras filas, estadísticas
  ── Calendario / Notas / Contactos ──
  cal_list            — lista eventos de un .ics local
  cal_add             — añade un evento VEVENT a un archivo .ics local
  cal_search          — busca eventos por texto o rango de fechas
  notes_list          — lista ficheros markdown en el vault de notas
  notes_search        — busca texto en notas markdown (ripgrep o grep)
  notes_save          — guarda o actualiza una nota markdown con front matter
  image_to_text       — extrae texto de una imagen con tesseract (OCR)
  contact_search      — busca en ficheros vCard (.vcf)
  ── Workspace / CMDB ──
  project_context_read — lee OOCODE.md y devuelve metadata del proyecto activo
  project_init_office  — inicializa estructura de directorios para proyecto IT
  doc_project_save     — guarda documento en subdir correcto con naming convention
  cmdb_search          — busca en CMDB (CSV/XLSX/JSON); soporta * para listar todo
  cmdb_update          — actualiza registro en CMDB CSV por campo clave
  asset_register_add   — añade activo al registro CSV (lo crea si no existe)

Prompts (13):
  ── Ofimática general ──
  draft_email               — borrador de email profesional con tono configurable
  summarize_document        — resumen estructurado con puntos clave y acción
  meeting_notes             — acta de reunión estructurada
  weekly_report             — informe semanal de actividades
  ── IT / Infraestructura / Datacenter ──
  datacenter_migration_report — informe técnico de migración de DC
  rfc_change_request          — RFC/Change Request formal para infraestructura IT
  server_migration_plan       — plan detallado de migración de servidor
  it_incident_report          — informe post-incidencia IT (Post-Mortem/RCA)
  infrastructure_change_plan  — plan de cambio de infraestructura con fases y riesgos
  ── Gestión / Negocio ──
  executive_summary           — resumen ejecutivo para dirección (1 página)
  business_case               — business case con análisis coste-beneficio y ROI
  project_status_report       — informe RAG de estado de proyecto con KPIs e hitos

Resources (9):
  office://emails_recent       — últimos 10 emails de la bandeja de entrada
  office://calendar_today      — eventos de hoy y los próximos 7 días
  office://notes_recent        — notas markdown más recientes (últimas 10)
  office://templates_available — plantillas de documentos disponibles
  office://rfc_pending         — RFCs/change requests en el directorio de notas
  office://tasks_today         — tareas pendientes del plugin todo de OOCode
  office://project_context     — metadata del proyecto activo (desde OOCODE.md)
  office://server_inventory    — listado completo de activos de la CMDB del proyecto
  office://style_gallery       — estilos de párrafo y tabla O365 disponibles
"""
import csv
import datetime
import email as _email_lib
import email.header
import email.mime.multipart
import email.mime.text
import imaplib
import json
import os
import re
import smtplib
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


# ── Configuración ─────────────────────────────────────────────────────────────

_CSV_SNIFF_BYTES = 65536   # bytes leídos para que csv.Sniffer detecte el dialect (64 KB)

_CONFIG_PATH = Path.home() / ".oocode" / "home_office.json"

_DEFAULT_CFG: dict = {
    "email": {
        "imap_host":     "",
        "imap_port":     993,
        "imap_ssl":      True,
        "smtp_host":     "",
        "smtp_port":     587,
        "user":          "",
        "password":      "",
        "smtp_user":     "",
        "smtp_password": "",
        "default_from":  "",
    },
    "notes_dir":      str(Path.home() / "Documents" / "notes"),
    "calendar_file":  str(Path.home() / "Documents" / "calendar.ics"),
    "contacts_dir":   str(Path.home() / "Documents" / "contacts"),
    "templates_dir":  str(Path.home() / "Documents" / "templates"),
}


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


def _load_config() -> dict:
    cfg = json.loads(json.dumps(_DEFAULT_CFG))
    if _CONFIG_PATH.exists():
        try:
            user = json.loads(_CONFIG_PATH.read_text())
            _deep_merge(cfg, user)
        except Exception:
            pass
    # Env var overrides
    em = cfg["email"]
    em["imap_host"]     = os.environ.get("HOME_OFFICE_IMAP_HOST",     em["imap_host"])
    em["imap_port"]     = int(os.environ.get("HOME_OFFICE_IMAP_PORT", em["imap_port"]))
    em["smtp_host"]     = os.environ.get("HOME_OFFICE_SMTP_HOST",     em["smtp_host"])
    em["smtp_port"]     = int(os.environ.get("HOME_OFFICE_SMTP_PORT", em["smtp_port"]))
    em["user"]          = os.environ.get("HOME_OFFICE_EMAIL_USER",    em["user"])
    em["password"]      = os.environ.get("HOME_OFFICE_EMAIL_PASS",    em["password"])
    cfg["notes_dir"]     = os.environ.get("HOME_OFFICE_NOTES_DIR",      cfg["notes_dir"])
    cfg["calendar_file"] = os.environ.get("HOME_OFFICE_CALENDAR_FILE", cfg["calendar_file"])
    cfg["contacts_dir"]  = os.environ.get("HOME_OFFICE_CONTACTS_DIR",  cfg["contacts_dir"])
    cfg["templates_dir"] = os.environ.get("HOME_OFFICE_TEMPLATES_DIR", cfg.get("templates_dir", str(Path.home() / "Documents" / "templates")))
    # Local project overrides: .oocode-office.json > OOCODE.md (both in cwd)
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


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _no_email_config() -> str:
    return (
        "⚙ Email no configurado.\n"
        f"Edita {_CONFIG_PATH} con tu configuración IMAP/SMTP:\n\n"
        '{\n  "email": {\n'
        '    "imap_host": "imap.gmail.com",\n'
        '    "imap_port": 993,\n'
        '    "smtp_host": "smtp.gmail.com",\n'
        '    "smtp_port": 587,\n'
        '    "user": "tu@email.com",\n'
        '    "password": "contraseña-de-aplicación"\n'
        "  }\n}\n\n"
        "Para Gmail: Configuración → Seguridad → Contraseñas de aplicación.\n"
        "Protege el fichero: chmod 600 ~/.oocode/home_office.json"
    )


# ── Protocolo MCP ────────────────────────────────────────────────────────────

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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _decode_header(raw: str) -> str:
    parts = email.header.decode_header(raw or "")
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(chunk))
    return "".join(out)


def _imap_connect(cfg: dict):
    """Conecta a IMAP. Devuelve cliente conectado y autenticado."""
    em = cfg["email"]
    if not em["imap_host"] or not em["user"]:
        return None, _no_email_config()
    try:
        if em["imap_ssl"]:
            client = imaplib.IMAP4_SSL(em["imap_host"], em["imap_port"])
        else:
            client = imaplib.IMAP4(em["imap_host"], em["imap_port"])
        client.login(em["user"], em["password"])
        return client, None
    except Exception as exc:
        return None, f"Error IMAP: {exc}"


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

def _tool_email_list(args: dict) -> str:
    cfg     = _load_config()
    mailbox = args.get("mailbox", "INBOX")
    limit   = min(int(args.get("limit", 10)), 50)

    client, err = _imap_connect(cfg)
    if err:
        return err
    try:
        client.select(mailbox)
        _, data = client.search(None, "ALL")
        uids = data[0].split()
        uids = uids[-limit:][::-1]  # los más recientes primero
        lines = [f"📬 {mailbox} — {len(uids)} emails (mostrando {len(uids)})\n"]
        for uid in uids:
            _, msg_data = client.fetch(uid, "(RFC822.SIZE ENVELOPE)")
            raw = msg_data[0][1].decode("utf-8", errors="replace") if msg_data and msg_data[0] else ""
            # Parse ENVELOPE para extraer subject/from/date
            _, msg_data2 = client.fetch(uid, "(RFC822.HEADER)")
            if msg_data2 and msg_data2[0]:
                msg = _email_lib.message_from_bytes(msg_data2[0][1])
                subj = _decode_header(msg.get("Subject", "(sin asunto)"))[:70]
                frm  = _decode_header(msg.get("From", "?"))[:40]
                date = msg.get("Date", "?")[:30]
                lines.append(f"  [{uid.decode()}] {date}\n     De: {frm}\n     Asunto: {subj}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listando emails: {exc}"
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _tool_email_read(args: dict) -> str:
    cfg     = _load_config()
    uid     = str(args.get("uid", ""))
    mailbox = args.get("mailbox", "INBOX")
    if not uid:
        return "Parámetro requerido: uid"

    client, err = _imap_connect(cfg)
    if err:
        return err
    try:
        client.select(mailbox)
        _, msg_data = client.fetch(uid.encode(), "(RFC822)")
        if not msg_data or not msg_data[0]:
            return f"Email UID {uid} no encontrado."
        raw = msg_data[0][1]
        msg = _email_lib.message_from_bytes(raw)
        subj = _decode_header(msg.get("Subject", "(sin asunto)"))
        frm  = _decode_header(msg.get("From", "?"))
        to   = _decode_header(msg.get("To", "?"))
        date = msg.get("Date", "?")
        lines = [
            f"📧 Email UID {uid}",
            f"De:     {frm}",
            f"Para:   {to}",
            f"Asunto: {subj}",
            f"Fecha:  {date}",
            "─" * 60,
        ]
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                    break
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        raw_html = part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
                        body = re.sub(r"<[^>]+>", "", raw_html)
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        lines.append(body[:4000] if body else "(sin cuerpo)")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error leyendo email {uid}: {exc}"
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _tool_email_send(args: dict) -> str:
    cfg  = _load_config()
    em   = cfg["email"]
    if not em["smtp_host"] or not em["user"]:
        return _no_email_config()

    to      = args.get("to", "")
    subject = args.get("subject", "")
    body    = args.get("body", "")
    cc      = args.get("cc", "")
    bcc     = args.get("bcc", "")
    if not to or not subject:
        return "Parámetros requeridos: to, subject"

    smtp_user = em.get("smtp_user") or em["user"]
    smtp_pass = em.get("smtp_password") or em["password"]
    frm       = em.get("default_from") or smtp_user

    msg = email.mime.multipart.MIMEMultipart()
    msg["From"]    = frm
    msg["To"]      = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))

    recipients = [a.strip() for a in (to + "," + cc + "," + bcc).split(",") if a.strip()]
    try:
        with smtplib.SMTP(em["smtp_host"], em["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(frm, recipients, msg.as_string())
        return f"✅ Email enviado a {to}\n   Asunto: {subject}"
    except Exception as exc:
        return f"Error enviando email: {exc}"


def _tool_email_search(args: dict) -> str:
    cfg     = _load_config()
    query   = args.get("query", "")
    mailbox = args.get("mailbox", "INBOX")
    limit   = min(int(args.get("limit", 20)), 50)
    if not query:
        return "Parámetro requerido: query (texto a buscar en asunto/remitente)"

    client, err = _imap_connect(cfg)
    if err:
        return err
    try:
        client.select(mailbox)
        # Intenta búsqueda IMAP nativa en asunto y cuerpo
        clean = query.replace('"', '')
        _, data = client.search(None, f'SUBJECT "{clean}"')
        uids = data[0].split()
        if not uids:
            _, data = client.search(None, f'TEXT "{clean}"')
            uids = data[0].split()
        uids = uids[-limit:][::-1]
        if not uids:
            return f"Sin resultados para: {query}"
        lines = [f"🔍 Búsqueda '{query}' en {mailbox}: {len(uids)} resultados\n"]
        for uid in uids:
            _, msg_data = client.fetch(uid, "(RFC822.HEADER)")
            if msg_data and msg_data[0]:
                msg = _email_lib.message_from_bytes(msg_data[0][1])
                subj = _decode_header(msg.get("Subject", "(sin asunto)"))[:70]
                frm  = _decode_header(msg.get("From", "?"))[:40]
                date = msg.get("Date", "?")[:30]
                lines.append(f"  [{uid.decode()}] {date}\n     De: {frm}\n     Asunto: {subj}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error buscando emails: {exc}"
    finally:
        try:
            client.logout()
        except Exception:
            pass


# ── Document tools ───────────────────────────────────────────────────────────


def _tool_doc_embed_image(args: dict) -> str:
    """Inserta una imagen (PNG/JPG/SVG) en un documento .docx existente, con pie de figura opcional."""
    path        = Path(args.get("path", "")).expanduser()
    image_path  = Path(args.get("image_path", "")).expanduser()
    caption     = args.get("caption", "")
    width_in    = args.get("width_inches", 5.0)
    output_path = args.get("output_path", "")
    position    = args.get("position", "end")   # end | after_paragraph_N

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


def _tool_insert_chart(args: dict) -> str:
    """Inserta una gráfica OOXML nativa en un documento .docx (editable, vectorial).

    Usa DrawingML nativo como primera opción; cae a PNG matplotlib solo si falla.
    chart_type: bar | column | line | area | pie | doughnut | scatter | stacked_bar |
                stacked_column | line_markers | radar
    data:
      - categories: ["Ene","Feb","Mar"]
      - series: [{"label":"Ventas","values":[100,200,150]}, ...]
      - (legacy) values, sizes, y_values, x_labels también aceptados
    """
    path        = Path(args.get("path", "")).expanduser()
    chart_type  = args.get("chart_type", "bar").lower()
    data        = args.get("data", {})
    title       = args.get("title", "")
    output_path = args.get("output_path", "")
    width_in    = float(args.get("width_inches", 6.0))
    height_in   = float(args.get("height_inches", 3.5))

    if not path:
        return "Parámetro requerido: path"
    if not path.exists():
        return f"Fichero no encontrado: {path}"

    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document(str(path))

        # Normalise into categories + series_list
        categories  = data.get("categories", [])
        series_list = data.get("series", [])
        if not series_list:
            if chart_type in ("bar", "column", "stacked_bar", "stacked_column",
                              "area", "stacked_area", "line", "line_markers",
                              "radar", "doughnut"):
                vals   = data.get("values", [])
                labels = data.get("labels", categories)
                if vals:
                    series_list = [{"label": title or "Serie 1", "values": vals}]
                    if not categories:
                        categories = labels
            elif chart_type == "pie":
                sizes  = data.get("sizes", data.get("values", []))
                labels = data.get("labels", categories)
                if sizes:
                    series_list = [{"label": title or "Serie 1", "values": sizes}]
                    if not categories:
                        categories = labels
            elif chart_type == "scatter":
                xv = data.get("x_values", [])
                yv = data.get("y_values", [])
                if xv and yv:
                    series_list = [{"label": title or "Serie 1",
                                    "x_values": xv, "values": yv}]
            else:
                vals = data.get("values", data.get("y_values", []))
                cats = data.get("x_labels", data.get("categories", []))
                if vals:
                    series_list = [{"label": title or "Serie 1", "values": vals}]
                    if not categories:
                        categories = cats

        if not series_list:
            return "Sin datos. Especifica data.series=[{label, values}] o data.values=[...]"

        # ── Primary: native OOXML DrawingML chart ─────────────────────────────
        chart_xml = _build_word_chart_xml(chart_type, categories, series_list, title)
        ok = _embed_word_chart_native(doc, chart_xml,
                                      int(width_in * 914400), int(height_in * 914400))
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
                f"✅ Gráfica OOXML nativa '{chart_type}' insertada en: {dest}\n"
                f"   Series: {len(series_list)}  Categorías: {len(categories)}  "
                f"Vectorial — editable en Word/LibreOffice."
            )

        # ── Fallback: matplotlib PNG (raster) ──────────────────────────────────
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import tempfile

        office_colors = ["#4472C4", "#ED7D31", "#A9D18E", "#FFC000", "#5B9BD5", "#70AD47"]
        fig, ax = plt.subplots(figsize=(width_in, height_in))
        cats = categories or [f"Cat {i+1}" for i in range(
            len(series_list[0].get("values", [])) if series_list else 0)]

        if chart_type in ("bar", "column", "stacked_bar", "stacked_column"):
            x = range(len(cats))
            for idx, ser in enumerate(series_list):
                vals = ser.get("values", [])
                ax.bar([xi + idx * 0.8/max(len(series_list), 1) for xi in x],
                       vals, width=0.8/max(len(series_list), 1),
                       label=ser.get("label", ""), color=office_colors[idx % 6], alpha=0.85)
            ax.set_xticks(range(len(cats)))
            ax.set_xticklabels(cats, rotation=15, ha="right")
        elif chart_type == "pie":
            vals = series_list[0].get("values", [])
            ax.pie(vals, labels=cats[:len(vals)], colors=office_colors[:len(vals)],
                   autopct="%1.1f%%", startangle=90)
            ax.axis("equal")
        elif chart_type in ("line", "line_markers"):
            for idx, ser in enumerate(series_list):
                vals = ser.get("values", [])
                ax.plot(cats[:len(vals)], vals, marker="o",
                        color=office_colors[idx % 6], linewidth=2,
                        label=ser.get("label", ""))
        elif chart_type == "scatter":
            for idx, ser in enumerate(series_list):
                xv = ser.get("x_values", ser.get("values", []))
                yv = ser.get("y_values", xv)
                ax.scatter(xv, yv, color=office_colors[idx % 6], s=60, alpha=0.8,
                           label=ser.get("label", ""))
        else:
            vals = series_list[0].get("values", []) if series_list else []
            ax.bar(cats[:len(vals)], vals, color=office_colors[0])

        if title:
            ax.set_title(title, fontsize=13, fontweight="bold")
        if len(series_list) > 1:
            ax.legend()
        if chart_type not in ("pie", "doughnut"):
            ax.grid(True, alpha=0.3, linestyle="--")
        plt.tight_layout()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        plt.savefig(tmp_path, dpi=200, bbox_inches="tight")
        plt.close(fig)

        doc.add_picture(tmp_path, width=Inches(width_in))
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

        dest = output_path or str(path)
        doc.save(dest)
        return f"✅ Gráfica {chart_type} insertada (PNG raster — OOXML no disponible) en: {dest}"

    except ImportError as e:
        return f"Dependencia no disponible: {e}\nInstala: pip install python-docx"
    except Exception as exc:
        return f"Error generando gráfica: {exc}"


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
    path        = Path(args.get("path", "")).expanduser()
    chart_type  = args.get("chart_type", "bar").lower()
    data        = args.get("data", {})
    title       = args.get("title", "")
    style_nm    = args.get("style", "office")
    width_in    = float(args.get("width_inches", 5.5))
    height_in   = float(args.get("height_inches", 3.5))
    output_path = args.get("output_path", "")

    if not path.exists():
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
        from docx.shared import Inches, Pt, RGBColor, Emu
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

        # ── Fallback: matplotlib PNG de alta resolución ─────────────────────
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.switch_backend("Agg")
        import tempfile, numpy as np

        st     = _CHART_STYLES.get(style_nm, _CHART_STYLES["office"])
        colors = st["colors"]
        fig, ax = plt.subplots(figsize=(width_in, height_in))
        fig.patch.set_facecolor(st["bg"])
        ax.set_facecolor(st["bg"])

        ct = chart_type
        if ct in ("bar", "column"):
            x   = np.arange(len(categories)) if categories else np.arange(len(series_list[0].get("values", [])))
            n_s = len(series_list)
            bar_w = 0.8 / max(n_s, 1)
            for i, serie in enumerate(series_list):
                vals   = serie.get("values", [])
                label  = serie.get("label", f"Serie {i+1}")
                color  = colors[i % len(colors)]
                offset = (i - n_s / 2 + 0.5) * bar_w
                bars = ax.bar(x + offset, vals, bar_w, label=label, color=color, alpha=0.88)
                ax.bar_label(bars, fmt="%.0f", padding=2, fontsize=8, color=st["text_c"])
            if categories:
                ax.set_xticks(x)
                ax.set_xticklabels(categories, rotation=20, ha="right", fontsize=9)
            if n_s > 1:
                ax.legend(fontsize=8, facecolor=st["bg"], labelcolor=st["text_c"])
        elif ct == "line":
            x = list(range(len(series_list[0].get("values", []))))
            for i, serie in enumerate(series_list):
                vals  = serie.get("values", [])
                col   = colors[i % len(colors)]
                ax.plot(x, vals, marker="o", color=col, linewidth=2.2,
                        label=serie.get("label", f"Serie {i+1}"), markersize=5)
                ax.fill_between(x, vals, alpha=0.06, color=col)
            if categories:
                ax.set_xticks(x)
                ax.set_xticklabels(categories, rotation=20, ha="right", fontsize=9)
            if len(series_list) > 1:
                ax.legend(fontsize=8, facecolor=st["bg"], labelcolor=st["text_c"])
        elif ct in ("pie", "doughnut"):
            vals   = series_list[0].get("values", [])
            labels = categories or [f"Item {i+1}" for i in range(len(vals))]
            wp = {"width": 0.55} if ct == "doughnut" else {}
            ax.pie(vals, labels=labels, colors=colors[:len(vals)],
                   autopct="%1.1f%%", startangle=90,
                   wedgeprops=wp if wp else {})
            ax.axis("equal")
        elif ct == "area":
            x = list(range(len(series_list[0].get("values", []))))
            for i, serie in enumerate(series_list):
                vals  = serie.get("values", [])
                col   = colors[i % len(colors)]
                ax.fill_between(x, vals, alpha=0.45, color=col,
                                label=serie.get("label", f"Serie {i+1}"))
                ax.plot(x, vals, color=col, linewidth=1.5)
            if categories:
                ax.set_xticks(x)
                ax.set_xticklabels(categories, rotation=20, ha="right", fontsize=9)
            if len(series_list) > 1:
                ax.legend(fontsize=8, facecolor=st["bg"], labelcolor=st["text_c"])
        elif ct == "scatter":
            for i, serie in enumerate(series_list):
                xv = serie.get("x_values", serie.get("values", []))
                yv = serie.get("y_values", [])
                ax.scatter(xv, yv, color=colors[i % len(colors)],
                           label=serie.get("label", f"Serie {i+1}"),
                           s=55, alpha=0.85, edgecolors="white", linewidths=0.5)
            if len(series_list) > 1:
                ax.legend(fontsize=8, facecolor=st["bg"], labelcolor=st["text_c"])
        else:
            plt.close("all")
            return f"Tipo de gráfica no soportado: {chart_type}. Usa: bar, line, pie, doughnut, area, scatter"

        if title:
            ax.set_title(title, fontsize=11, fontweight="bold", color=st["text_c"], pad=8)
        _apply_chart_style(fig, ax, style_nm, is_pie=ct in ("pie", "doughnut"))
        plt.tight_layout(pad=0.4)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_path = tf.name
        plt.savefig(tmp_path, dpi=st["dpi"], bbox_inches="tight", facecolor=st["bg"])
        plt.close("all")

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(tmp_path, width=Inches(width_in))

        if title:
            cap = doc.add_paragraph()
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = cap.add_run(title)
            r.font.size = Pt(9)
            r.font.italic = True
            r.font.color.rgb = RGBColor(0x60, 0x60, 0x60)

        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

        dest = output_path or str(path)
        doc.save(dest)
        return (
            f"✅ Gráfica '{chart_type}' (PNG DPI:{st['dpi']}) insertada en {Path(dest).name}\n"
            f"   Series: {len(series_list)}  Categorías: {len(categories)}  Estilo: {style_nm}"
        )

    except ImportError as e:
        return f"Dependencia no disponible: {e}\nInstala: pip install python-docx matplotlib"
    except Exception as exc:
        return f"Error generando gráfica Word: {exc}"


def _tool_doc_insert_diagram(args: dict) -> str:
    """Inserta un diagrama o gráfica en un documento .docx existente.

    diagram_type: flowchart | bar_chart | pie_chart | line_chart | table | org_chart | scatter
    content: datos del diagrama en texto plano:
      - bar_chart/pie_chart/line_chart: "Label1,Label2,Label3\\nVal1,Val2,Val3"
      - table:  "Col1|Col2|Col3\\nFila1a|Fila1b|Fila1c"
      - flowchart: "Paso 1\\nPaso 2\\nPaso 3" (uno por línea)
      - org_chart: "CEO → CTO → Dev\\nCEO → CFO"
    title: título de la gráfica (opcional)
    style: office | dark | minimal | presentation
    width_inches: ancho en pulgadas (default: 5.5)
    output_path: ruta de salida (default: sobreescribe path)
    """
    _path_str   = args.get("path", "")
    diagram_type = args.get("diagram_type", "bar_chart").lower()
    content     = args.get("content", "")
    title       = args.get("title", "")
    style_nm    = args.get("style", "office")
    width_in    = float(args.get("width_inches", 5.5))
    output_path = args.get("output_path", "")

    if not _path_str:
        return "Error insertando diagrama: parámetro 'path' requerido"
    path = Path(_path_str).expanduser()
    if not path.exists():
        return f"Documento no encontrado: {path}"

    try:
        from docx import Document
        from docx.shared import Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.switch_backend("Agg")
        import tempfile

        st = _CHART_STYLES.get(style_nm, _CHART_STYLES["office"])
        colors = st["colors"]

        doc = Document(str(path))
        tmp_img = None

        # ── Table diagram ─────────────────────────────────────────────────
        if diagram_type == "table":
            # Parse pipe-separated or CSV table
            lines = [l for l in content.strip().splitlines() if l.strip()]
            if not lines:
                dest = output_path or str(path)
                doc.save(dest)
                return f"✅ Diagrama insertado (table): {dest}"
            sep = "|" if "|" in lines[0] else ","
            rows = [[c.strip() for c in l.split(sep)] for l in lines]
            n_cols = max(len(r) for r in rows)
            tbl = doc.add_table(rows=len(rows), cols=n_cols)
            try:
                tbl.style = doc.styles["Table Grid"]
            except Exception:
                pass
            from docx.shared import RGBColor
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement
            for r_i, row in enumerate(rows):
                for c_i, val in enumerate(row[:n_cols]):
                    cell = tbl.rows[r_i].cells[c_i]
                    cell.text = ""
                    p = cell.paragraphs[0]
                    run = p.add_run(val)
                    if r_i == 0:
                        run.bold = True
                        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                        try:
                            tcPr = cell._tc.get_or_add_tcPr()
                            shd = OxmlElement("w:shd")
                            shd.set(qn("w:val"), "clear")
                            shd.set(qn("w:color"), "auto")
                            shd.set(qn("w:fill"), "2F5496")
                            tcPr.append(shd)
                        except Exception:
                            pass
                    elif r_i % 2 == 0:
                        try:
                            tcPr = cell._tc.get_or_add_tcPr()
                            shd = OxmlElement("w:shd")
                            shd.set(qn("w:val"), "clear")
                            shd.set(qn("w:color"), "auto")
                            shd.set(qn("w:fill"), "EEF3FB")
                            tcPr.append(shd)
                        except Exception:
                            pass
            dest = output_path or str(path)
            doc.save(dest)
            return f"✅ Diagrama insertado (table): {dest}"

        # ── Flowchart diagram — nativo Word (tabla O365 por pasos) ───────
        elif diagram_type == "flowchart":
            steps = [l.strip() for l in content.strip().splitlines() if l.strip()]
            if not steps:
                dest = output_path or str(path)
                doc.save(dest)
                return f"✅ Diagrama insertado (flowchart): {dest}"
            from docx.shared import Pt, RGBColor
            from docx.oxml.ns import qn as _qn2
            from docx.oxml import OxmlElement as _OE2
            step_colors = ["2F5496", "4472C4", "5B9BD5", "70AD47", "ED7D31", "FFC000"]
            if title:
                tp = doc.add_paragraph()
                try:
                    tp.style = doc.styles["Heading 3"]
                except Exception:
                    pass
                tp.add_run(title)
            for i, step in enumerate(steps):
                is_decision = step.rstrip(".").endswith("?")
                color       = "FFC000" if is_decision else step_colors[i % len(step_colors)]
                s_tbl       = doc.add_table(rows=1, cols=1)
                s_tbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cell = s_tbl.rows[0].cells[0]
                cell.text = ""
                sp = cell.paragraphs[0]
                sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                sp.paragraph_format.space_before = Pt(5)
                sp.paragraph_format.space_after  = Pt(5)
                run = sp.add_run(step)
                run.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.font.size = Pt(11)
                try:
                    tcPr = cell._tc.get_or_add_tcPr()
                    shd  = _OE2("w:shd")
                    shd.set(_qn2("w:val"),   "clear")
                    shd.set(_qn2("w:color"), "auto")
                    shd.set(_qn2("w:fill"),  color)
                    tcPr.append(shd)
                except Exception:
                    pass
                if i < len(steps) - 1:
                    arr = doc.add_paragraph()
                    arr.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    arr.paragraph_format.space_before = Pt(0)
                    arr.paragraph_format.space_after  = Pt(0)
                    try:
                        pPr  = arr._p.get_or_add_pPr()
                        pBdr = _OE2("w:pBdr")
                        bot  = _OE2("w:bottom")
                        bot.set(_qn2("w:val"),   "single")
                        bot.set(_qn2("w:sz"),    "12")
                        bot.set(_qn2("w:space"), "1")
                        bot.set(_qn2("w:color"), "4472C4")
                        pBdr.append(bot)
                        pPr.append(pBdr)
                    except Exception:
                        pass
            dest = output_path or str(path)
            doc.save(dest)
            return f"✅ Diagrama insertado (flowchart): {dest}"

        # ── Org chart diagram — nativo Word (tabla O365) ──────────────────
        elif diagram_type == "org_chart":
            lines_oc = [l.strip() for l in content.strip().splitlines() if l.strip()]
            edges_oc: list = []
            all_nodes_oc: list = []
            for line_oc in lines_oc:
                parts_oc = [p.strip() for p in re.split(r'→|->|–>', line_oc) if p.strip()]
                for idx_oc in range(len(parts_oc) - 1):
                    if parts_oc[idx_oc] not in all_nodes_oc:
                        all_nodes_oc.append(parts_oc[idx_oc])
                    if parts_oc[idx_oc+1] not in all_nodes_oc:
                        all_nodes_oc.append(parts_oc[idx_oc+1])
                    edges_oc.append((parts_oc[idx_oc], parts_oc[idx_oc+1]))
            if not all_nodes_oc:
                all_nodes_oc = [content.strip()[:30] or "Nodo"]
            roots_oc = [n for n in all_nodes_oc if not any(b == n for _, b in edges_oc)]
            if not roots_oc:
                roots_oc = [all_nodes_oc[0]]
            from collections import deque as _dq2
            nl_oc: dict = {}
            q_oc = _dq2()
            for r in roots_oc:
                nl_oc[r] = 0; q_oc.append(r)
            while q_oc:
                cur = q_oc.popleft()
                for a, b in edges_oc:
                    if a == cur and b not in nl_oc:
                        nl_oc[b] = nl_oc[cur] + 1; q_oc.append(b)
            for n in all_nodes_oc:
                if n not in nl_oc:
                    nl_oc[n] = 0
            bl_oc: dict = {}
            for n, lv in nl_oc.items():
                bl_oc.setdefault(lv, []).append(n)
            ml_oc    = max(nl_oc.values()) if nl_oc else 0
            mpr_oc   = max(len(v) for v in bl_oc.values()) if bl_oc else 1
            lv_cols  = ["2F5496", "4472C4", "5B9BD5", "9DC3E6", "BDD7EE", "DEEAF1"]
            from docx.shared import Pt, RGBColor, Cm as _Cm
            from docx.oxml.ns import qn as _qn3
            from docx.oxml import OxmlElement as _OE3
            if title:
                tp3 = doc.add_paragraph()
                try:
                    tp3.style = doc.styles["Heading 3"]
                except Exception:
                    pass
                tp3.add_run(title)
            oc_tbl = doc.add_table(rows=ml_oc + 1, cols=max(mpr_oc, 1))
            try:
                oc_tbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception:
                pass

            def _shade_oc(cell, hx: str) -> None:
                try:
                    tcPr = cell._tc.get_or_add_tcPr()
                    shd  = _OE3("w:shd")
                    shd.set(_qn3("w:val"), "clear")
                    shd.set(_qn3("w:color"), "auto")
                    shd.set(_qn3("w:fill"), hx)
                    tcPr.append(shd)
                except Exception:
                    pass

            for lv_oc, lv_nodes in bl_oc.items():
                cpn_oc = max(1, max(mpr_oc, 1) // max(len(lv_nodes), 1))
                c_oc   = lv_cols[lv_oc % len(lv_cols)]
                for ni_oc, nid_oc in enumerate(lv_nodes):
                    sc_oc = ni_oc * cpn_oc
                    ec_oc = min(sc_oc + cpn_oc - 1, max(mpr_oc, 1) - 1)
                    try:
                        cell = (oc_tbl.rows[lv_oc].cells[sc_oc].merge(oc_tbl.rows[lv_oc].cells[ec_oc])
                                if ec_oc > sc_oc else oc_tbl.rows[lv_oc].cells[min(sc_oc, max(mpr_oc,1)-1)])
                    except Exception:
                        cell = oc_tbl.rows[lv_oc].cells[0]
                    cell.text = ""
                    cp = cell.paragraphs[0]
                    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cp.paragraph_format.space_before = Pt(5)
                    cp.paragraph_format.space_after  = Pt(5)
                    run_oc = cp.add_run(nid_oc)
                    run_oc.bold = True
                    run_oc.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                    run_oc.font.size = Pt(max(8, 11 - lv_oc))
                    _shade_oc(cell, c_oc)
                used_oc = len(lv_nodes) * cpn_oc
                for ci_oc in range(used_oc, max(mpr_oc, 1)):
                    try:
                        _shade_oc(oc_tbl.rows[lv_oc].cells[ci_oc], "F5F5F5")
                    except Exception:
                        pass
            oc_cw = _Cm(max(0.5, 16.0 / max(mpr_oc, 1)))
            for row in oc_tbl.rows:
                for cell in row.cells:
                    try:
                        cell.width = oc_cw
                    except Exception:
                        pass
            dest = output_path or str(path)
            doc.save(dest)
            return f"✅ Diagrama insertado (org_chart): {dest}"

        # ── Bar chart — native OOXML (with matplotlib fallback) ──────────
        elif diagram_type == "bar_chart":
            raw_lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
            sep = "," if raw_lines and "," in raw_lines[0] else "|"
            cats = [c.strip() for c in raw_lines[0].split(sep)] if raw_lines else []
            values: list = []
            if len(raw_lines) > 1:
                try:
                    values = [float(v.strip()) for v in raw_lines[1].split(sep)]
                except ValueError:
                    values = list(range(len(cats)))
            # Multiple series: row0=labels, row1=series1, row2=series2 …
            series_list = []
            for si, row in enumerate(raw_lines[1:]):
                try:
                    row_vals = [float(v.strip()) for v in row.split(sep)]
                    series_list.append({"label": f"Serie {si+1}", "values": row_vals})
                except ValueError:
                    pass
            if not series_list and values:
                series_list = [{"label": title or "Serie 1", "values": values}]

            cxml = _build_word_chart_xml("bar", cats, series_list, title)
            ok = _embed_word_chart_native(doc, cxml,
                                          int(width_in * 914400), int(int(width_in * 0.6) * 914400))
            if ok:
                if title:
                    from docx.shared import Pt, RGBColor
                    cap = doc.add_paragraph(title)
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for run in cap.runs:
                        run.font.size = Pt(9); run.font.italic = True
                        run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
                dest = output_path or str(path)
                doc.save(dest)
                return f"✅ Diagrama bar_chart OOXML insertado: {dest}"
            # matplotlib fallback
            fig, ax = plt.subplots(figsize=(width_in, width_in * 0.6))
            fig.patch.set_facecolor(st["bg"]); ax.set_facecolor(st["bg"])
            ax.bar(cats[:len(values)], values, color=colors[:len(values)],
                   edgecolor="white", linewidth=0.8)
            if title:
                ax.set_title(title, color=st["text_c"], fontsize=12, fontweight="bold", pad=10)
            _apply_chart_style(fig, ax, style_nm)
            plt.tight_layout()

        # ── Pie chart — native OOXML (with matplotlib fallback) ──────────
        elif diagram_type == "pie_chart":
            raw_lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
            sep = "," if raw_lines and "," in raw_lines[0] else "|"
            cats = [c.strip() for c in raw_lines[0].split(sep)] if raw_lines else []
            values = []
            if len(raw_lines) > 1:
                try:
                    values = [float(v.strip()) for v in raw_lines[1].split(sep)]
                except ValueError:
                    values = [1.0] * len(cats)
            series_list = [{"label": title or "Serie 1", "values": values}] if values else []

            cxml = _build_word_chart_xml("pie", cats, series_list, title)
            ok = _embed_word_chart_native(doc, cxml,
                                          int(width_in * 914400), int(width_in * 0.8 * 914400))
            if ok:
                if title:
                    from docx.shared import Pt, RGBColor
                    cap = doc.add_paragraph(title)
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for run in cap.runs:
                        run.font.size = Pt(9); run.font.italic = True
                        run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
                dest = output_path or str(path)
                doc.save(dest)
                return f"✅ Diagrama pie_chart OOXML insertado: {dest}"
            fig, ax = plt.subplots(figsize=(width_in, width_in * 0.8))
            fig.patch.set_facecolor(st["bg"])
            ax.pie(values[:len(cats)], labels=cats[:len(values)],
                   colors=colors[:len(values)], autopct="%1.1f%%",
                   startangle=140, wedgeprops={"edgecolor": st["bg"], "linewidth": 1.5})
            if title:
                ax.set_title(title, color=st["text_c"], fontsize=12, fontweight="bold", pad=10)
            _apply_chart_style(fig, ax, style_nm, is_pie=True)
            plt.tight_layout()

        # ── Line chart — native OOXML (with matplotlib fallback) ─────────
        elif diagram_type in ("line_chart", "line"):
            raw_lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
            sep = "," if raw_lines and "," in raw_lines[0] else "|"
            cats = [c.strip() for c in raw_lines[0].split(sep)] if raw_lines else []
            values = []
            if len(raw_lines) > 1:
                try:
                    values = [float(v.strip()) for v in raw_lines[1].split(sep)]
                except ValueError:
                    values = list(range(len(cats)))
            series_list: list = []
            for si, row in enumerate(raw_lines[1:]):
                try:
                    row_vals = [float(v.strip()) for v in row.split(sep)]
                    series_list.append({"label": f"Serie {si+1}", "values": row_vals})
                except ValueError:
                    pass
            if not series_list and values:
                series_list = [{"label": title or "Serie 1", "values": values}]

            cxml = _build_word_chart_xml("line", cats, series_list, title)
            ok = _embed_word_chart_native(doc, cxml,
                                          int(width_in * 914400), int(width_in * 0.6 * 914400))
            if ok:
                if title:
                    from docx.shared import Pt, RGBColor
                    cap = doc.add_paragraph(title)
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for run in cap.runs:
                        run.font.size = Pt(9); run.font.italic = True
                        run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
                dest = output_path or str(path)
                doc.save(dest)
                return f"✅ Diagrama line_chart OOXML insertado: {dest}"
            fig, ax = plt.subplots(figsize=(width_in, width_in * 0.6))
            fig.patch.set_facecolor(st["bg"]); ax.set_facecolor(st["bg"])
            ax.plot(cats[:len(values)], values, color=colors[0], marker="o",
                    linewidth=2, markersize=6)
            if title:
                ax.set_title(title, color=st["text_c"], fontsize=12, fontweight="bold", pad=10)
            _apply_chart_style(fig, ax, style_nm)
            plt.tight_layout()

        # ── Unknown type ─────────────────────────────────────────────────
        else:
            return (f"Tipo de diagrama no soportado: {diagram_type}. "
                    f"Usa: flowchart, bar_chart, pie_chart, line_chart, table, org_chart")

        # Save chart image and embed in docx (for flowchart/org_chart matplotlib paths)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_img = tf.name
        plt.savefig(tmp_img, dpi=st["dpi"], bbox_inches="tight", facecolor=st["bg"])
        plt.close("all")

        doc.add_picture(tmp_img, width=Inches(width_in))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        if title:
            cap = doc.add_paragraph(title)
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            try:
                from docx.shared import Pt, RGBColor
                for run in cap.runs:
                    run.font.size = Pt(9)
                    run.font.italic = True
                    run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
            except Exception:
                pass

        dest = output_path or str(path)
        doc.save(dest)
        return f"✅ Diagrama insertado ({diagram_type}): {dest}"

    except ImportError as exc:
        return f"Dependencia no disponible: {exc}. Instala: pip install matplotlib python-docx"
    except Exception as exc:
        return f"Error insertando diagrama: {exc}"
    finally:
        if tmp_img:
            try:
                Path(tmp_img).unlink(missing_ok=True)
            except Exception:
                pass


def _tool_create_bar_chart(args: dict) -> str:
    """Inserta gráfica de barras OOXML nativa en .docx (editable), o PNG como respaldo.

    Si 'path' apunta a un .docx, inserta un gráfico DrawingML nativo.
    Si solo se da 'output' (sin .docx), genera PNG con matplotlib.
    """
    doc_path = (args.get("path") or args.get("doc_path", "")).strip()
    if doc_path and Path(doc_path).expanduser().suffix.lower() == ".docx":
        p = Path(doc_path).expanduser()
        if not p.exists():
            try:
                from docx import Document as _D
                _d = _D()
                _apply_o365_styles_to_new_doc(_d)
                _d.save(str(p))
            except Exception:
                pass
        ct = "bar_horiz" if args.get("horizontal") else ("stacked_bar" if args.get("stacked") else "bar")
        return _tool_doc_insert_chart_native({**args, "path": str(p), "chart_type": ct})
    return _save_chart_image(args, "bar")


def _tool_create_pie_chart(args: dict) -> str:
    """Inserta gráfica circular OOXML nativa en .docx (editable), o PNG como respaldo."""
    doc_path = (args.get("path") or args.get("doc_path", "")).strip()
    if doc_path and Path(doc_path).expanduser().suffix.lower() == ".docx":
        p = Path(doc_path).expanduser()
        if not p.exists():
            try:
                from docx import Document as _D
                _d = _D()
                _apply_o365_styles_to_new_doc(_d)
                _d.save(str(p))
            except Exception:
                pass
        ct = "doughnut" if args.get("donut") else "pie"
        return _tool_doc_insert_chart_native({**args, "path": str(p), "chart_type": ct})
    return _save_chart_image(args, "pie")


def _tool_create_line_chart(args: dict) -> str:
    """Inserta gráfica de líneas OOXML nativa en .docx (editable), o PNG como respaldo."""
    doc_path = (args.get("path") or args.get("doc_path", "")).strip()
    if doc_path and Path(doc_path).expanduser().suffix.lower() == ".docx":
        p = Path(doc_path).expanduser()
        if not p.exists():
            try:
                from docx import Document as _D
                _d = _D()
                _apply_o365_styles_to_new_doc(_d)
                _d.save(str(p))
            except Exception:
                pass
        ct = "line_markers" if args.get("markers") else ("area" if args.get("fill_area") else "line")
        return _tool_doc_insert_chart_native({**args, "path": str(p), "chart_type": ct})
    return _save_chart_image(args, "line")


_CHART_STYLES: dict[str, dict] = {
    "office": {
        "colors":    ["#4472C4", "#ED7D31", "#A9D18E", "#FFC000", "#5B9BD5", "#70AD47", "#FF0000", "#7030A0"],
        "bg":        "white",
        "grid_c":    "#DDDDDD",
        "text_c":    "#404040",
        "spine_c":   "#CCCCCC",
        "dpi":       200,
    },
    "dark": {
        "colors":    ["#5B9BD5", "#ED7D31", "#A9D18E", "#FF8C00", "#B4C7E7", "#70AD47", "#FF6347", "#DDA0DD"],
        "bg":        "#1F1F1F",
        "grid_c":    "#444444",
        "text_c":    "#E0E0E0",
        "spine_c":   "#555555",
        "dpi":       200,
    },
    "minimal": {
        "colors":    ["#2C5F8A", "#5AA0C8", "#8BBFD4", "#B8D8E8", "#D6EAF2", "#92B4C8", "#4A7FA5", "#6EA0BE"],
        "bg":        "white",
        "grid_c":    "#EEEEEE",
        "text_c":    "#555555",
        "spine_c":   "white",
        "dpi":       200,
    },
    "presentation": {
        "colors":    ["#2F5496", "#ED7D31", "#70AD47", "#FFC000", "#FF0000", "#7030A0", "#00B0F0", "#92D050"],
        "bg":        "#F2F2F2",
        "grid_c":    "#DDDDDD",
        "text_c":    "#262626",
        "spine_c":   "#CCCCCC",
        "dpi":       250,
    },
}


def _apply_chart_style(fig, ax, style_name: str, is_pie: bool = False) -> None:
    s = _CHART_STYLES.get(style_name, _CHART_STYLES["office"])
    fig.patch.set_facecolor(s["bg"])
    ax.set_facecolor(s["bg"])
    if not is_pie:
        ax.grid(True, color=s["grid_c"], linestyle="--", linewidth=0.6, alpha=0.8)
        for spine in ax.spines.values():
            spine.set_edgecolor(s["spine_c"])
    ax.tick_params(colors=s["text_c"], labelsize=10)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(s["text_c"])
    if ax.get_title():
        ax.title.set_color(s["text_c"])
    if ax.get_xlabel():
        ax.xaxis.label.set_color(s["text_c"])
    if ax.get_ylabel():
        ax.yaxis.label.set_color(s["text_c"])


def _save_chart_image(args: dict, chart_type: str) -> str:
    """Helper mejorado: genera imagen de gráfica con matplotlib (multi-series, estilos, ejes)."""
    output    = args.get("output", f"/tmp/chart_{chart_type}.png")
    data      = args.get("data", {})
    title     = args.get("title", "")
    x_label   = args.get("x_label", "")
    y_label   = args.get("y_label", "")
    style_nm  = args.get("style", "office")
    horizontal= args.get("horizontal", False)
    stacked   = args.get("stacked", False)
    donut     = args.get("donut", False)
    fill_area = args.get("fill_area", False)
    width     = args.get("width", 8)
    height    = args.get("height", 5)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        st     = _CHART_STYLES.get(style_nm, _CHART_STYLES["office"])
        colors = st["colors"]

        fig, ax = plt.subplots(figsize=(width, height))
        fig.patch.set_facecolor(st["bg"])
        ax.set_facecolor(st["bg"])

        if chart_type == "bar":
            categories  = data.get("categories", [])
            # Multi-series support: series=[{label, values}] OR single values list
            series_list = data.get("series", [])
            if series_list:
                n_series  = len(series_list)
                x         = np.arange(len(categories))
                width_bar = 0.8 / n_series
                bottoms   = np.zeros(len(categories)) if stacked else None
                for i, serie in enumerate(series_list):
                    vals   = serie.get("values", [])
                    label  = serie.get("label", f"Serie {i+1}")
                    color  = colors[i % len(colors)]
                    offset = 0 if stacked else (i - n_series/2 + 0.5) * width_bar
                    if horizontal:
                        bars = ax.barh([c + offset for c in x], vals, width_bar,
                                       label=label, color=color,
                                       left=bottoms if stacked else None, alpha=0.85)
                    else:
                        bars = ax.bar(x + offset, vals, width_bar,
                                      label=label, color=color,
                                      bottom=bottoms if stacked else None, alpha=0.85)
                    if stacked and bottoms is not None:
                        bottoms = bottoms + np.array(vals, dtype=float)
                ax.legend(fontsize=9, facecolor=st["bg"], labelcolor=st["text_c"])
                if horizontal:
                    ax.set_yticks(x)
                    ax.set_yticklabels(categories)
                else:
                    ax.set_xticks(x)
                    ax.set_xticklabels(categories)
            else:
                values = data.get("values", [])
                if horizontal:
                    bars = ax.barh(categories, values, color=colors[:len(values)], alpha=0.85)
                    ax.bar_label(bars, fmt="%.0f", padding=4, color=st["text_c"])
                else:
                    bars = ax.bar(categories, values, color=colors[:len(values)], alpha=0.85)
                    ax.bar_label(bars, fmt="%.0f", padding=2, color=st["text_c"])

        elif chart_type == "pie":
            labels  = data.get("labels", [])
            sizes   = data.get("sizes", [])
            explode_list = data.get("explode", None)
            wedge_args: dict = {}
            if donut:
                wedge_args["wedgeprops"] = {"width": 0.5}
            ax.pie(sizes, labels=labels, colors=colors[:len(labels)],
                   autopct="%1.1f%%", startangle=90,
                   explode=explode_list, **wedge_args)
            ax.axis("equal")

        elif chart_type == "line":
            series_list = data.get("series", [])
            if series_list:
                x_labels = data.get("x_labels", list(range(len(series_list[0].get("values", [])))))
                x_pos    = list(range(len(x_labels)))
                for i, serie in enumerate(series_list):
                    vals  = serie.get("values", [])
                    label = serie.get("label", f"Serie {i+1}")
                    col   = colors[i % len(colors)]
                    ax.plot(x_pos, vals, marker="o", color=col, linewidth=2.5, label=label)
                    if fill_area:
                        ax.fill_between(x_pos, vals, alpha=0.08, color=col)
                ax.set_xticks(x_pos)
                ax.set_xticklabels(x_labels, rotation=30, ha="right")
                ax.legend(fontsize=9, facecolor=st["bg"], labelcolor=st["text_c"])
            else:
                x_labels = data.get("x_labels", [])
                y_values = data.get("y_values", [])
                x_pos    = list(range(len(x_labels)))
                ax.plot(x_pos, y_values, marker="o", color=colors[0], linewidth=2.5)
                if fill_area:
                    ax.fill_between(x_pos, y_values, alpha=0.1, color=colors[0])
                ax.set_xticks(x_pos)
                ax.set_xticklabels(x_labels, rotation=30, ha="right")

        if title:
            ax.set_title(title, fontsize=14, fontweight="bold", color=st["text_c"], pad=12)
        if x_label:
            ax.set_xlabel(x_label, fontsize=11, color=st["text_c"])
        if y_label:
            ax.set_ylabel(y_label, fontsize=11, color=st["text_c"])

        _apply_chart_style(fig, ax, style_nm, is_pie=(chart_type == "pie"))
        plt.tight_layout()
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output, dpi=st["dpi"], bbox_inches="tight", facecolor=st["bg"])
        plt.close(fig)
        return f"✅ Gráfica {chart_type} guardada en: {output}"

    except ImportError as e:
        return f"matplotlib no disponible: {e}\nInstala: pip install matplotlib"
    except Exception as exc:
        return f"Error creando gráfica: {exc}"


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
        from pptx.enum.text import PP_ALIGN
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
        from pptx.dml.color import RGBColor
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
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
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
        from docx.oxml.ns import qn
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

def _tool_xlsx_read(args: dict) -> str:
    path   = Path(args.get("path", "")).expanduser()
    sheet  = args.get("sheet", "")
    rng    = args.get("range", "")
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

def _parse_ics_events(path: Path) -> list[dict]:
    """Parser ICS mínimo sin dependencias externas."""
    events = []
    current: dict = {}
    in_event = False
    try:
        lines = path.read_text(errors="replace").splitlines()
        for line in lines:
            if line.startswith(" ") or line.startswith("\t"):
                # Continuación de propiedad
                if current and "_last_key" in current:
                    current[current["_last_key"]] += line[1:]
                continue
            if line.strip() == "BEGIN:VEVENT":
                current = {}
                in_event = True
            elif line.strip() == "END:VEVENT":
                events.append(current)
                in_event = False
                current = {}
            elif in_event and ":" in line:
                key, _, val = line.partition(":")
                key = key.split(";")[0].strip().upper()
                current[key] = val.strip()
                current["_last_key"] = key
    except Exception:
        pass
    return events


def _ics_date_str(raw: str) -> str:
    raw = raw.replace("Z", "").replace("-", "").replace(":", "")
    try:
        if len(raw) == 8:
            return datetime.datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
        return datetime.datetime.strptime(raw[:15], "%Y%m%dT%H%M%S").strftime("%Y-%m-%d %H:%M")
    except Exception:
        return raw


def _tool_cal_list(args: dict) -> str:
    cfg    = _load_config()
    source = args.get("source", cfg["calendar_file"])
    start  = args.get("start", "")
    end    = args.get("end", "")
    limit  = int(args.get("limit", 15))
    ics_path = Path(source).expanduser()
    if not ics_path.exists():
        return f"Fichero de calendario no encontrado: {ics_path}\nConfigura 'calendar_file' en {_CONFIG_PATH}"
    events = _parse_ics_events(ics_path)
    today = datetime.date.today()
    result_events = []
    for ev in events:
        dt_str = ev.get("DTSTART", "")
        dt_disp = _ics_date_str(dt_str)
        summary = ev.get("SUMMARY", "(sin título)")
        location = ev.get("LOCATION", "")
        result_events.append((dt_str, dt_disp, summary, location))
    result_events.sort(key=lambda x: x[0])
    # Filtrar por fechas si se proporcionan
    if start:
        result_events = [e for e in result_events if e[0] >= start.replace("-", "")]
    if end:
        result_events = [e for e in result_events if e[0] <= end.replace("-", "")]
    result_events = result_events[:limit]
    if not result_events:
        return f"📅 Sin eventos en {ics_path.name}"
    lines = [f"📅 Calendario: {ics_path.name} — {len(result_events)} eventos"]
    for _, dt_disp, summary, location in result_events:
        loc = f" @ {location}" if location else ""
        lines.append(f"  {dt_disp:<20} {summary}{loc}")
    return "\n".join(lines)


def _tool_cal_add(args: dict) -> str:
    cfg      = _load_config()
    title    = args.get("title", "")
    start    = args.get("start", "")
    end      = args.get("end", "")
    location = args.get("location", "")
    desc     = args.get("description", "")
    file     = args.get("file", cfg["calendar_file"])
    if not title or not start:
        return "Parámetros requeridos: title, start (formato: YYYY-MM-DD o YYYY-MM-DDTHH:MM)"
    ics_path = Path(file).expanduser()
    # Formatear fecha para ICS
    def _to_ics_dt(s: str) -> str:
        s = s.replace("-", "").replace(":", "").replace(" ", "T")
        return s if "T" in s else s + "T000000"
    uid = f"{datetime.datetime.now().strftime('%Y%m%dT%H%M%S')}-oocode@home"
    vevent_lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{_to_ics_dt(start)}",
    ]
    if end:
        vevent_lines.append(f"DTEND:{_to_ics_dt(end)}")
    vevent_lines.append(f"SUMMARY:{title}")
    if location:
        vevent_lines.append(f"LOCATION:{location}")
    if desc:
        vevent_lines.append(f"DESCRIPTION:{desc}")
    vevent_lines.append("END:VEVENT")
    vevent = "\r\n".join(vevent_lines) + "\r\n"
    try:
        if ics_path.exists():
            content = ics_path.read_text()
            if "END:VCALENDAR" in content:
                content = content.replace("END:VCALENDAR", vevent + "END:VCALENDAR")
            else:
                content += vevent
        else:
            ics_path.parent.mkdir(parents=True, exist_ok=True)
            content = (
                "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//OOCode//Home Office//ES\r\n"
                + vevent + "END:VCALENDAR\r\n"
            )
        ics_path.write_text(content)
        return f"✅ Evento añadido: {title}\n   Inicio: {start}\n   Fichero: {ics_path}"
    except Exception as exc:
        return f"Error añadiendo evento: {exc}"


def _tool_cal_search(args: dict) -> str:
    cfg    = _load_config()
    query  = args.get("query", "")
    source = args.get("source", cfg["calendar_file"])
    limit  = int(args.get("limit", 20))
    if not query:
        return "Parámetro requerido: query"
    ics_path = Path(source).expanduser()
    if not ics_path.exists():
        return f"Fichero de calendario no encontrado: {ics_path}"
    events  = _parse_ics_events(ics_path)
    q_lower = query.lower()
    matches = []
    for ev in events:
        summary = ev.get("SUMMARY", "")
        desc    = ev.get("DESCRIPTION", "")
        if q_lower in summary.lower() or q_lower in desc.lower():
            dt_disp  = _ics_date_str(ev.get("DTSTART", ""))
            location = ev.get("LOCATION", "")
            matches.append((ev.get("DTSTART", ""), dt_disp, summary, location))
    matches.sort(key=lambda x: x[0])
    matches = matches[:limit]
    if not matches:
        return f"Sin eventos que coincidan con: {query}"
    lines = [f"🔍 Búsqueda '{query}': {len(matches)} eventos"]
    for _, dt_disp, summary, location in matches:
        loc = f" @ {location}" if location else ""
        lines.append(f"  {dt_disp:<20} {summary}{loc}")
    return "\n".join(lines)


# ── Notes tools ──────────────────────────────────────────────────────────────

def _notes_dir(cfg: dict) -> Path:
    d = Path(cfg["notes_dir"]).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tool_notes_list(args: dict) -> str:
    cfg     = _load_config()
    dirpath = Path(args.get("directory", cfg["notes_dir"])).expanduser()
    pattern = args.get("pattern", "*.md")
    limit   = int(args.get("limit", 20))
    if not dirpath.exists():
        return f"Directorio de notas no encontrado: {dirpath}\nConfigura 'notes_dir' en {_CONFIG_PATH}"
    files = sorted(dirpath.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    if not files:
        return f"Sin notas en {dirpath} (patrón: {pattern})"
    lines = [f"📝 Notas en {dirpath} — {len(files)} ficheros"]
    for f in files:
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size  = f.stat().st_size
        # Intentar leer título del front matter o primera línea
        try:
            first = f.read_text(errors="replace")[:200]
            title_match = re.search(r"^title:\s*(.+)$", first, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else first.split("\n")[0][:60]
            title = title.lstrip("#").strip()
        except Exception:
            title = f.stem
        lines.append(f"  {mtime}  {size:>6} B  {f.name:<30} {title}")
    return "\n".join(lines)


def _tool_notes_search(args: dict) -> str:
    import shutil
    cfg     = _load_config()
    query   = args.get("query", "")
    dirpath = Path(args.get("directory", cfg["notes_dir"])).expanduser()
    limit   = int(args.get("limit", 10))
    if not query:
        return "Parámetro requerido: query"
    if not dirpath.exists():
        return f"Directorio de notas no encontrado: {dirpath}"
    # ripgrep o grep
    if shutil.which("rg"):
        rc, out, err = _run(["rg", "--color=never", "-l", "-i", query, str(dirpath)], timeout=15)
        tool = "rg"
    else:
        rc, out, err = _run(["grep", "-r", "-l", "-i", query, str(dirpath)], timeout=15)
        tool = "grep"
    if rc != 0 and not out:
        return f"Sin resultados para: {query}"
    files = [Path(p) for p in out.strip().splitlines() if p][:limit]
    if not files:
        return f"Sin notas que contengan: {query}"
    lines = [f"🔍 Búsqueda '{query}' en notas ({len(files)} ficheros)"]
    for f in files:
        # Mostrar líneas que coinciden
        if shutil.which("rg"):
            rc2, ctx, _ = _run(["rg", "--color=never", "-n", "-i", query, str(f)], timeout=10)
        else:
            rc2, ctx, _ = _run(["grep", "-n", "-i", query, str(f)], timeout=10)
        ctx_lines = ctx.strip().splitlines()[:3]
        lines.append(f"\n  📄 {f.name}")
        for cl in ctx_lines:
            lines.append(f"     {cl}")
    return "\n".join(lines)


def _tool_notes_save(args: dict) -> str:
    cfg     = _load_config()
    title   = args.get("title", "")
    content = args.get("content", "")
    dirpath = Path(args.get("directory", cfg["notes_dir"])).expanduser()
    if not title:
        return "Parámetro requerido: title"
    dirpath.mkdir(parents=True, exist_ok=True)
    # Sanitizar título como nombre de fichero
    fname = re.sub(r"[^\w\s\-]", "", title).strip().replace(" ", "_")[:60] + ".md"
    note_path = dirpath / fname
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    if note_path.exists():
        old = note_path.read_text(errors="replace")
        # Actualiza fecha de modificación en front matter si existe
        if old.startswith("---"):
            content_final = re.sub(r"^modified:.*$", f"modified: {now}", old, flags=re.MULTILINE)
            if "modified:" not in content_final:
                content_final = content_final.replace("---\n", f"---\nmodified: {now}\n", 1)
            # Reemplaza contenido del cuerpo (después del segundo ---)
            parts = content_final.split("---", 2)
            if len(parts) == 3 and content:
                content_final = "---" + parts[1] + "---\n\n" + content
        else:
            content_final = content or old
        note_path.write_text(content_final)
        return f"✅ Nota actualizada: {note_path}"
    else:
        front_matter = f"---\ntitle: {title}\ncreated: {now}\nmodified: {now}\n---\n\n"
        note_path.write_text(front_matter + (content or ""))
        return f"✅ Nota creada: {note_path}"


# ── Misc tools ───────────────────────────────────────────────────────────────

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


def _tool_contact_search(args: dict) -> str:
    cfg     = _load_config()
    query   = args.get("query", "")
    vcf_dir = Path(args.get("vcf_dir", cfg["contacts_dir"])).expanduser()
    if not query:
        return "Parámetro requerido: query"
    if not vcf_dir.exists():
        return f"Directorio de contactos no encontrado: {vcf_dir}\nConfigura 'contacts_dir' en {_CONFIG_PATH}"
    vcf_files = list(vcf_dir.glob("*.vcf")) + list(vcf_dir.glob("*.vcard"))
    if not vcf_files:
        return f"No se encontraron ficheros .vcf en {vcf_dir}"
    q_lower = query.lower()
    results = []
    for vcf_file in vcf_files:
        try:
            text = vcf_file.read_text(errors="replace")
        except Exception:
            continue
        if q_lower not in text.lower():
            continue
        # Extraer campos relevantes
        fn     = re.search(r"^FN:(.+)$",    text, re.MULTILINE)
        email  = re.search(r"^EMAIL.*:(.+)$", text, re.MULTILINE | re.IGNORECASE)
        tel    = re.search(r"^TEL.*:(.+)$",  text, re.MULTILINE | re.IGNORECASE)
        org    = re.search(r"^ORG:(.+)$",    text, re.MULTILINE)
        name   = fn.group(1).strip()    if fn    else vcf_file.stem
        e_val  = email.group(1).strip() if email else ""
        t_val  = tel.group(1).strip()   if tel   else ""
        o_val  = org.group(1).strip()   if org   else ""
        results.append((name, e_val, t_val, o_val))
    if not results:
        return f"Sin contactos que coincidan con: {query}"
    lines = [f"👤 Contactos ({len(results)} encontrados)"]
    for name, email_v, tel_v, org_v in results:
        lines.append(f"\n  {name}")
        if org_v:   lines.append(f"    Empresa: {org_v}")
        if email_v: lines.append(f"    Email:   {email_v}")
        if tel_v:   lines.append(f"    Tel:     {tel_v}")
    return "\n".join(lines)


def _tool_markdown_to_html(args: dict) -> str:
    import shutil
    content = args.get("content", "")
    path    = args.get("path", "")
    output  = args.get("output", "")
    if path:
        p = Path(path).expanduser()
        if not p.exists():
            return f"Fichero no encontrado: {p}"
        content = p.read_text(errors="replace")
    if not content:
        return "Parámetro requerido: content (markdown) o path (ruta a fichero .md)"
    # Intento 1: markdown lib
    try:
        import markdown as md_lib
        html = md_lib.markdown(content, extensions=["tables", "fenced_code", "nl2br"])
        html = f"<!DOCTYPE html>\n<html>\n<body>\n{html}\n</body>\n</html>"
        if output:
            Path(output).expanduser().write_text(html)
            return f"✅ HTML escrito en: {output}\n{html[:500]}…"
        return html[:6000]
    except ImportError:
        pass
    # Intento 2: pandoc
    if shutil.which("pandoc"):
        cmd = ["pandoc", "-f", "markdown", "-t", "html", "--standalone"]
        rc, out, err = _run(cmd, timeout=15, input_text=content)
        if rc == 0:
            if output:
                Path(output).expanduser().write_text(out)
                return f"✅ HTML escrito en: {output}"
            return out[:6000]
    # Fallback: conversión básica manual
    html = content
    html = re.sub(r"^# (.+)$",  r"<h1>\1</h1>",  html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>",  html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$",r"<h3>\1</h3>",  html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",         html)
    html = re.sub(r"`(.+?)`",       r"<code>\1</code>",      html)
    html = html.replace("\n\n", "</p>\n<p>")
    html = f"<p>{html}</p>"
    return html[:6000]


# ── Bloque 1: Workspace / Proyecto ───────────────────────────────────────────

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
        err = _write_docx_from_markdown(content, save_path)
        if err:
            save_path = save_path.with_suffix(".md")
            save_path.write_text(content)
            return (
                f"⚠ {err}\n✅ Guardado como Markdown: {save_path}\n"
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

def _cmdb_path_discover(cfg: dict, path_arg: str) -> Optional[Path]:
    """Find CMDB file: explicit arg > project cwd > ~/Documents/."""
    if path_arg:
        p = Path(path_arg).expanduser()
        return p if p.exists() else None
    cwd = Path.cwd()
    candidates = (
        [cwd / n for n in ("cmdb.csv", "cmdb.xlsx", "cmdb.json",
                           "inventario.csv", "inventario.xlsx",
                           "servers.csv", "servers.xlsx")]
        + [Path.home() / "Documents" / n for n in ("cmdb.csv", "inventario.csv")]
    )
    return next((p for p in candidates if p.exists()), None)


def _cmdb_rows_csv(path: Path, query: str, field: str, limit: int) -> str:
    try:
        q = query.lower() if query != "*" else None
        with path.open(newline="", errors="replace") as f:
            reader = csv.DictReader(f)
            results = []
            for row in reader:
                if q is None or (field and q in str(row.get(field, "")).lower()) \
                   or (not field and any(q in str(v).lower() for v in row.values())):
                    results.append(dict(row))
                if len(results) >= limit:
                    break
        if not results:
            return f"Sin resultados para '{query}' en {path.name}"
        lines = [f"🖥 CMDB {path.name} — {len(results)} entrada(s):\n"]
        for row in results:
            lines.append("  " + "  |  ".join(f"{k}: {v}" for k, v in row.items() if v))
        return "\n".join(lines)
    except Exception as exc:
        return f"Error leyendo CMDB CSV: {exc}"


def _cmdb_rows_xlsx(path: Path, query: str, field: str, limit: int) -> str:
    try:
        import openpyxl
        wb  = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        ws  = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            return f"CMDB vacío: {path.name}"
        headers = [str(c) if c is not None else "" for c in all_rows[0]]
        q = query.lower() if query != "*" else None
        field_idx: Optional[int] = None
        if field:
            try:
                field_idx = headers.index(field)
            except ValueError:
                pass
        results = []
        for row in all_rows[1:]:
            cells = [str(c) if c is not None else "" for c in row]
            if q is None or (field_idx is not None and q in cells[field_idx].lower()) \
               or (field_idx is None and any(q in c.lower() for c in cells)):
                results.append(dict(zip(headers, cells)))
            if len(results) >= limit:
                break
        if not results:
            return f"Sin resultados para '{query}' en {path.name}"
        lines = [f"🖥 CMDB {path.name} — {len(results)} entrada(s):\n"]
        for row in results:
            lines.append("  " + "  |  ".join(f"{k}: {v}" for k, v in row.items() if v))
        return "\n".join(lines)
    except ImportError:
        return "openpyxl requerido para CMDB .xlsx: pip install openpyxl"
    except Exception as exc:
        return f"Error leyendo CMDB xlsx: {exc}"


def _tool_cmdb_search(args: dict) -> str:
    """Search the CMDB (CSV/XLSX/JSON) for servers, services or assets by any field value."""
    query = args.get("query", "")
    if not query:
        return "Parámetro requerido: query (texto a buscar, o '*' para listar todo)"
    cfg   = _load_config()
    path  = _cmdb_path_discover(cfg, args.get("cmdb_path", "") or args.get("path", ""))
    if path is None:
        cwd = Path.cwd()
        return (
            "CMDB no encontrado. Crea uno de estos ficheros:\n"
            f"  {cwd}/cmdb.csv\n  {cwd}/inventario.csv\n"
            "  ~/Documents/cmdb.csv\n"
            "Usa 'project_init_office' para crear la estructura del proyecto."
        )
    field = args.get("field", "")
    limit = int(args.get("limit", 20))
    if path.suffix == ".csv":
        return _cmdb_rows_csv(path, query, field, limit)
    if path.suffix == ".xlsx":
        return _cmdb_rows_xlsx(path, query, field, limit)
    if path.suffix == ".json":
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                data = list(data.values())
            q = query.lower() if query != "*" else None
            results = [
                item for item in data
                if isinstance(item, dict) and (q is None or any(q in str(v).lower() for v in item.values()))
            ][:limit]
            if not results:
                return f"Sin resultados para '{query}'"
            lines = [f"🖥 CMDB {path.name} — {len(results)} entrada(s):\n"]
            for item in results:
                lines.append("  " + "  |  ".join(f"{k}: {v}" for k, v in item.items() if v))
            return "\n".join(lines)
        except Exception as exc:
            return f"Error leyendo CMDB JSON: {exc}"
    return f"Formato CMDB no soportado: {path.suffix}"


def _tool_cmdb_update(args: dict) -> str:
    """Update a CMDB entry (CSV only) by key field: finds row where key_field=key_value, applies updates dict."""
    key_field = args.get("key_field", "")
    key_value = args.get("key_value", "")
    updates   = args.get("updates", {})
    if not key_field or not key_value:
        return "Parámetros requeridos: key_field (p.ej. 'hostname'), key_value (p.ej. 'web-01')"
    if not updates or not isinstance(updates, dict):
        return "Parámetro requerido: updates (objeto {campo: nuevo_valor})"
    cfg  = _load_config()
    path = _cmdb_path_discover(cfg, args.get("cmdb_path", "") or args.get("path", ""))
    if path is None:
        return "CMDB no encontrado. Especifica 'cmdb_path' o crea cmdb.csv en el directorio de trabajo."
    if path.suffix != ".csv":
        return "cmdb_update solo soporta .csv. Para .xlsx usa xlsx_fill_range."
    try:
        rows: list[dict] = []
        headers: list[str] = []
        updated = 0
        with path.open(newline="", errors="replace") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            for row in reader:
                if str(row.get(key_field, "")).strip() == str(key_value).strip():
                    row.update(updates)
                    updated += 1
                rows.append(dict(row))
        if updated == 0:
            return f"No se encontró {key_field}={key_value!r} en {path.name}"
        for k in updates:
            if k not in headers:
                headers.append(k)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return (
            f"✅ CMDB actualizado: {path.name}\n"
            f"   Clave: {key_field}={key_value!r}\n"
            f"   Cambios: {', '.join(f'{k}={v!r}' for k, v in updates.items())}\n"
            f"   Entradas actualizadas: {updated}"
        )
    except Exception as exc:
        return f"Error actualizando CMDB: {exc}"


def _tool_asset_register_add(args: dict) -> str:
    """Add a new asset entry to the project asset register (CSV)."""
    asset = args.get("asset", {})
    if not asset or not isinstance(asset, dict):
        return 'Parámetro requerido: asset (objeto JSON con datos del activo, p.ej. {"hostname": "srv-01", "ip": "10.0.0.1"})'
    if "fecha_registro" not in asset:
        asset = {**asset, "fecha_registro": datetime.date.today().isoformat()}
    cfg = _load_config()
    cwd = Path.cwd()
    path_arg = args.get("register_path", "") or args.get("path", "")
    if path_arg:
        ar_path = Path(path_arg).expanduser()
    else:
        candidates = [
            cwd / "asset_register.csv",
            cwd / "activos.csv",
            Path.home() / "Documents" / "asset_register.csv",
        ]
        ar_path = next((p for p in candidates if p.exists()), cwd / "asset_register.csv")
    try:
        existing_headers: list[str] = []
        existing_rows: list[dict]   = []
        if ar_path.exists():
            with ar_path.open(newline="", errors="replace") as f:
                reader = csv.DictReader(f)
                existing_headers = list(reader.fieldnames or [])
                existing_rows    = list(reader)
        all_headers = list(existing_headers)
        for k in asset:
            if k not in all_headers:
                all_headers.append(k)
        existing_rows.append(asset)
        with ar_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(existing_rows)
        return (
            f"✅ Activo añadido al registro: {ar_path.name}\n"
            f"   Registro #{len(existing_rows)}\n"
            + "\n".join(f"   {k}: {v}" for k, v in asset.items())
        )
    except Exception as exc:
        return f"Error añadiendo activo: {exc}"


# ── Template and IT report tools ─────────────────────────────────────────────

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
    import copy

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


def _md_populate_doc(doc, content: str, is_new_doc: bool = False) -> None:
    """Populate a python-docx Document with rich markdown content using O365 styles.

    Handles: H1-H6, ATX/setext headings, bold/italic/code/strike/link inline,
    bullet/numbered lists (nested), GFM tables with header shading, fenced code
    blocks, blockquotes, horizontal rules, images, page breaks.

    If *is_new_doc* is True, applies O365 default styles before populating.
    Always preserves styles from a company template if already loaded in *doc*.
    """
    import re as _re
    from docx.shared import Pt, RGBColor, Inches, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    if is_new_doc:
        _apply_o365_styles_to_new_doc(doc)

    style_names = {s.name for s in doc.styles}

    def _safe(name: str, fallback: str = "Normal") -> str:
        return name if name in style_names else fallback

    def _add_h(text: str, level: int):
        style_nm = f"Heading {level}"
        p = doc.add_paragraph()
        try:
            p.style = doc.styles[_safe(style_nm)]
        except Exception:
            pass
        # Strip inline markdown from heading text (headings are plain)
        clean = _re.sub(r'\*\*(.+?)\*\*', r'\1',
                _re.sub(r'\*(.+?)\*', r'\1',
                _re.sub(r'`(.+?)`', r'\1', text)))
        p.add_run(clean)
        return p

    def _add_para(text: str, style: str = "Normal") -> object:
        p = doc.add_paragraph()
        try:
            p.style = doc.styles[_safe(style)]
        except Exception:
            pass
        _md_fill_para_inline(p, text)
        return p

    def _shade_cell(cell, hex_color: str):
        """Apply background shading to a table cell."""
        try:
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), hex_color)
            tcPr.append(shd)
        except Exception:
            pass

    def _flush_table(buf: list) -> None:
        if not buf:
            return
        n_cols = max(len(r) for r in buf)
        tbl = doc.add_table(rows=len(buf), cols=n_cols)
        try:
            tbl.style = doc.styles[_safe("Table Grid")]
        except Exception:
            pass
        for r_i, row in enumerate(buf):
            for c_i, cell_txt in enumerate(row):
                if c_i < n_cols:
                    cell = tbl.rows[r_i].cells[c_i]
                    cell.text = ""
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_before = Pt(4)
                    p.paragraph_format.space_after  = Pt(4)
                    _md_fill_para_inline(p, cell_txt.strip())
                    if r_i == 0:
                        # Header row: bold + blue background
                        for run in p.runs:
                            run.bold = True
                            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                        _shade_cell(cell, "2F5496")
                    elif r_i % 2 == 0:
                        _shade_cell(cell, "EEF3FB")  # alternate row light blue
        # Auto-fit columns
        try:
            tbl.autofit = True
        except Exception:
            pass

    def _add_code_block(code_text: str, lang: str = ""):
        """Add a code block paragraph with Consolas font and light grey background."""
        p = doc.add_paragraph()
        try:
            p.style = doc.styles[_safe("No Spacing", "Normal")]
        except Exception:
            pass
        # Light grey background via paragraph shading
        try:
            pPr = p._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "F2F2F2")
            pPr.append(shd)
            # Left border (code bar)
            pBdr = OxmlElement("w:pBdr")
            left = OxmlElement("w:left")
            left.set(qn("w:val"), "single")
            left.set(qn("w:sz"), "18")
            left.set(qn("w:space"), "4")
            left.set(qn("w:color"), "4472C4")
            pBdr.append(left)
            pPr.append(pBdr)
            # Indent
            ind = OxmlElement("w:ind")
            ind.set(qn("w:left"), "360")
            pPr.append(ind)
        except Exception:
            pass
        run = p.add_run(code_text)
        run.font.name = "Consolas"
        try:
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x26, 0x26, 0x26)
        except Exception:
            pass
        return p

    lines  = content.splitlines()
    i      = 0
    tbl_buf: list = []
    list_stack: list = []  # track nested list levels

    while i < len(lines):
        line = lines[i]

        # Fenced code block (``` or ~~~)
        m_fence = _re.match(r"^(`{3,}|~{3,})(\w*)", line.strip())
        if m_fence:
            if tbl_buf: _flush_table(tbl_buf); tbl_buf = []
            fence_char = m_fence.group(1)[0]
            lang = m_fence.group(2)
            code_lines: list = []
            i += 1
            while i < len(lines) and not _re.match(r"^" + fence_char + r"{3,}", lines[i].strip()):
                code_lines.append(lines[i])
                i += 1
            _add_code_block("\n".join(code_lines), lang)
            i += 1
            continue

        # Horizontal rule
        if _re.match(r"^(\*{3,}|-{3,}|_{3,})\s*$", line.strip()):
            if tbl_buf: _flush_table(tbl_buf); tbl_buf = []
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
                sep.add_run("─" * 72)
            i += 1
            continue

        # ATX heading (#, ##, ...)
        m_h = _re.match(r"^(#{1,6})\s+(.*)", line)
        if m_h:
            if tbl_buf: _flush_table(tbl_buf); tbl_buf = []
            _add_h(m_h.group(2).strip(), len(m_h.group(1)))
            i += 1
            continue

        # Setext heading (=== or ---)
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            if _re.match(r"^={3,}\s*$", nxt) and line.strip():
                if tbl_buf: _flush_table(tbl_buf); tbl_buf = []
                _add_h(line.strip(), 1); i += 2; continue
            if _re.match(r"^-{3,}\s*$", nxt) and line.strip() and not _re.match(r"^\|", line.strip()):
                if tbl_buf: _flush_table(tbl_buf); tbl_buf = []
                _add_h(line.strip(), 2); i += 2; continue

        # GFM table row
        if "|" in line and line.strip().startswith("|"):
            stripped = line.strip()
            if _re.match(r"^\|[\s\|\-:]+\|?\s*$", stripped):  # separator row
                i += 1; continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            tbl_buf.append(cells)
            i += 1
            continue
        else:
            if tbl_buf: _flush_table(tbl_buf); tbl_buf = []

        # Blockquote (> text or >text)
        if line.startswith("> ") or (line.startswith(">") and len(line) > 1 and not line.startswith(">>")):
            bq_text = line[2:] if line.startswith("> ") else line[1:]
            p_bq = doc.add_paragraph()
            try:
                p_bq.style = doc.styles[_safe("Intense Quote", _safe("Quote", "Normal"))]
            except Exception:
                pass
            _md_fill_para_inline(p_bq, bq_text)
            try:
                pPr = p_bq._p.get_or_add_pPr()
                pBdr = OxmlElement("w:pBdr")
                left = OxmlElement("w:left")
                left.set(qn("w:val"), "single")
                left.set(qn("w:sz"), "24")
                left.set(qn("w:space"), "4")
                left.set(qn("w:color"), "5B9BD5")
                pBdr.append(left)
                pPr.append(pBdr)
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "F0F4FA")
                pPr.append(shd)
                ind = OxmlElement("w:ind")
                ind.set(qn("w:left"), "720")
                ind.set(qn("w:right"), "360")
                pPr.append(ind)
            except Exception:
                pass
            i += 1
            continue

        # Bullet list (supports -, *, +; nested via indent)
        m_ul = _re.match(r"^(\s*)([-*+])\s+(.*)", line)
        if m_ul:
            indent_spaces = len(m_ul.group(1))
            level = min(indent_spaces // 2 + 1, 3)
            style_nm = f"List Bullet{' ' + str(level) if level > 1 else ''}"
            p = doc.add_paragraph()
            try:
                p.style = doc.styles[_safe(style_nm, "List Bullet")]
            except Exception:
                pass
            _md_fill_para_inline(p, m_ul.group(3))
            i += 1
            continue

        # Numbered list
        m_ol = _re.match(r"^(\s*)(\d+)[.)]\s+(.*)", line)
        if m_ol:
            indent_spaces = len(m_ol.group(1))
            level = min(indent_spaces // 3 + 1, 3)
            style_nm = f"List Number{' ' + str(level) if level > 1 else ''}"
            p = doc.add_paragraph()
            try:
                p.style = doc.styles[_safe(style_nm, "List Number")]
            except Exception:
                pass
            _md_fill_para_inline(p, m_ol.group(3))
            i += 1
            continue

        # Inline image on its own line
        m_img = _re.match(r"^!\[([^\]]*)\]\(([^\)]+)\)\s*$", line.strip())
        if m_img:
            img_p = Path(m_img.group(2)).expanduser()
            if img_p.exists():
                try:
                    doc.add_picture(str(img_p), width=Inches(5.5))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    # Add caption
                    alt = m_img.group(1)
                    if alt:
                        cap = doc.add_paragraph(alt)
                        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        try:
                            cap.style = doc.styles[_safe("Caption", "Normal")]
                        except Exception:
                            for run in cap.runs:
                                run.font.size = Pt(9)
                                run.italic = True
                except Exception:
                    doc.add_paragraph(f"[Imagen: {m_img.group(1)}]")
            else:
                doc.add_paragraph(f"[Imagen no encontrada: {m_img.group(2)}]")
            i += 1
            continue

        # Page break keyword
        if line.strip().lower() in ("<pagebreak>", "<!-- pagebreak -->", "[pagebreak]", "\\pagebreak"):
            doc.add_page_break()
            i += 1
            continue

        # Empty line — skip (Word handles paragraph spacing via style spacing)
        if not line.strip():
            i += 1
            continue

        # Regular paragraph
        _add_para(line, "Normal")
        i += 1

    if tbl_buf:
        _flush_table(tbl_buf)


def _write_docx_from_markdown(content: str, path: Path, reference_doc: str = "") -> str | None:
    """Convert markdown text to a professional .docx with O365 styles.

    Uses python-docx with _apply_o365_styles_to_new_doc for fresh docs.
    If *reference_doc* is given (.docx/.dotx company template), inherits
    all styles, page layout, fonts and branding from it.
    Falls back to pandoc if python-docx fails.
    Returns None on success or an error string.
    """
    try:
        from docx import Document as _Doc
        from docx.oxml.ns import qn

        is_new = not bool(reference_doc)
        if reference_doc:
            ref = Path(reference_doc).expanduser()
            if ref.exists():
                doc = _Doc(str(ref))
                if ref.suffix.lower() in (".dotx", ".dot"):
                    body = doc.element.body
                    for p in body.findall(qn("w:p"))[:-1]:
                        body.remove(p)
                    for t in body.findall(qn("w:tbl")):
                        body.remove(t)
            else:
                doc = _Doc()
                is_new = True
        else:
            doc = _Doc()

        _md_populate_doc(doc, content, is_new_doc=is_new)
        path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(path))
        return None

    except ImportError:
        try:
            import subprocess as _sp
            ref_args = ["--reference-doc", reference_doc] if reference_doc and Path(reference_doc).exists() else []
            r = _sp.run(
                ["pandoc", "-f", "markdown", "-t", "docx",
                 "--highlight-style=tango"] + ref_args + ["-o", str(path)],
                input=content, text=True, capture_output=True, timeout=30,
            )
            if r.returncode == 0 and path.exists() and path.stat().st_size > 0:
                return None
        except (FileNotFoundError, Exception):
            pass
        return "python-docx no disponible — instala con: pip install python-docx"
    except Exception as exc:
        return f"Error generando .docx: {exc}"


def _tool_doc_create(args: dict) -> str:
    """Create a professional Word (.docx) or Excel (.xlsx) or PowerPoint (.pptx) document
    from scratch with O365-quality formatting.

    For .docx: accepts markdown content OR structured content_blocks.
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
      {"type": "markdown",      "text": "# H1\\n**bold** párrafo..."}
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
    path           = Path(args.get("path", "")).expanduser()
    theme          = args.get("theme", "office")
    fmt            = args.get("format", "").lower() or (path.suffix.lstrip(".").lower() if path.suffix else "docx")
    markdown       = args.get("markdown", "")
    content_blocks = args.get("content_blocks", [])
    title          = args.get("title", "")
    subtitle       = args.get("subtitle", "")
    metadata       = args.get("metadata", {})  # author, subject, company, keywords
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
            from docx.shared import Pt, RGBColor, Inches, Cm
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
                    from docx.oxml.ns import qn as _qn2
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
                        doc.add_paragraph(f"[Gráfica '{c_type}' — OOXML no disponible, usa doc_insert_chart_native]")
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
                _md_populate_doc(doc, block.get("text", ""), is_new_doc=False)

            elif btype == "code_block":
                code = block.get("code", block.get("text", ""))
                lang = block.get("language", block.get("lang", ""))
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

        # If only markdown given (no content_blocks)
        if markdown and not content_blocks:
            if title:
                _add_cover_title(title, subtitle)
                doc.add_paragraph()
            _md_populate_doc(doc, markdown, is_new_doc=False)
            n_blocks += 1

        doc.save(str(path))
        _tpl_note = f"  |  Plantilla: {Path(template_path).name}" if _used_template else ""
        return (
            f"✅ Documento Word creado: {path}\n"
            f"   Tema: {theme}  |  Bloques: {n_blocks}  |  Tamaño: {path.stat().st_size:,} bytes{_tpl_note}\n"
            f"   Abre en Word/LibreOffice — estilos O365 aplicados."
        )

    # ── Excel .xlsx ─────────────────────────────────────────────────────────
    elif ext == ".xlsx":
        sheets = args.get("sheets", [])
        if not sheets and args.get("headers"):
            sheets = [{"name": args.get("sheet", "Hoja1"), "headers": args["headers"],
                       "rows": args.get("rows", []), "title": title}]
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
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
                thin = Side(style="thin", color="CCCCCC")
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
                            formula  = f'RANK(A1,A$1:A$100)<="{rank}"'
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
                        from openpyxl.chart.series import SeriesLabel
                        from openpyxl.chart.label import DataLabel
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
        slides_data = args.get("slides", [])
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
                            from lxml import etree as _et
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
                    from pptx.chart.data import ChartData, CategoryChartData
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
                            from pptx.util import Pt as _Pt2
                            from pptx.enum.shapes import MSO_SHAPE_TYPE
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
    """Generate a structured RFC/Request for Change document (.docx by default, or .md)."""
    title            = args.get("title", "")
    requester        = args.get("requester", "")
    if not title or not requester:
        return "Parámetros requeridos: title, requester"

    date             = args.get("date", datetime.date.today().isoformat())
    priority         = args.get("priority", "Media")
    change_type      = args.get("change_type", "Normal")
    affected_systems = args.get("affected_systems", "_Por especificar_")
    description      = args.get("description", "_Por completar_")
    justification    = args.get("justification", "_Por completar_")
    risk             = args.get("risk", "_Por analizar_")
    risk_level       = args.get("risk_level", "Bajo")
    rollback_plan    = args.get("rollback_plan", "_Por definir_")
    testing_plan     = args.get("testing_plan", "_Por definir_")
    impl_steps       = args.get("implementation_steps", "_Por definir_")
    scheduled_date   = args.get("scheduled_date", "Por definir")
    scheduled_window = args.get("scheduled_window", "Por definir")
    approver         = args.get("approver", "Por asignar")
    output_path      = args.get("output_path", "")
    fmt              = args.get("format", "docx").lower()

    rfc_id = f"RFC-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
    doc = f"""# {rfc_id} — {title}

| Campo | Valor |
|-------|-------|
| **ID RFC** | {rfc_id} |
| **Título** | {title} |
| **Solicitante** | {requester} |
| **Fecha solicitud** | {date} |
| **Tipo de cambio** | {change_type} |
| **Prioridad** | {priority} |
| **Nivel de riesgo** | {risk_level} |
| **Fecha programada** | {scheduled_date} |
| **Ventana de cambio** | {scheduled_window} |
| **Aprobador** | {approver} |

---

## 1. Descripción del cambio

{description}

## 2. Justificación

{justification}

## 3. Sistemas afectados

{affected_systems}

## 4. Plan de implementación

{impl_steps}

## 5. Plan de pruebas y validación

{testing_plan}

## 6. Análisis de riesgos

**Nivel de riesgo:** {risk_level}

{risk}

## 7. Plan de marcha atrás (Rollback)

{rollback_plan}

---

## 8. Aprobaciones

| Rol | Nombre | Firma | Fecha |
|-----|--------|-------|-------|
| Solicitante | {requester} | | {date} |
| Aprobador técnico | {approver} | | |
| Responsable de negocio | | | |
| Gestor de cambios | | | |

---
*Documento generado por OOCode Home Office Assistant — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    if output_path:
        try:
            out = Path(output_path).expanduser()
            # If path has no extension, apply format preference
            if not out.suffix:
                out = out.with_suffix(".docx" if fmt == "docx" else ".md")
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.suffix.lower() == ".docx":
                err = _write_docx_from_markdown(doc, out)
                if err:
                    out = out.with_suffix(".md")
                    out.write_text(doc)
                    return f"⚠ {err}\n✅ RFC guardado como Markdown: {out}\n   ID: {rfc_id}"
            else:
                out.write_text(doc)
            return f"✅ RFC generado: {out}\n   ID: {rfc_id}"
        except Exception as exc:
            return f"Error guardando RFC: {exc}"
    # No path given: return inline content (compatible with all callers)
    return f"📋 RFC generado (ID: {rfc_id}):\n\n{doc}"


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
    summary_row  = args.get("summary_row", False)

    if not path:
        return "Parámetro requerido: path"
    if not headers:
        return "Parámetro requerido: headers (lista de nombres de columnas)"
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
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


# ── Nuevas tools matplotlib avanzadas ────────────────────────────────────────

def _tool_create_scatter_chart(args: dict) -> str:
    """Inserta scatter plot OOXML nativo en .docx (editable), o PNG como respaldo."""
    doc_path = (args.get("path") or args.get("doc_path", "")).strip()
    if doc_path and Path(doc_path).expanduser().suffix.lower() == ".docx":
        p = Path(doc_path).expanduser()
        if not p.exists():
            try:
                from docx import Document as _D
                _d = _D()
                _apply_o365_styles_to_new_doc(_d)
                _d.save(str(p))
            except Exception:
                pass
        return _tool_doc_insert_chart_native({**args, "path": str(p), "chart_type": "scatter"})
    output    = args.get("output", "/tmp/scatter.png")
    data      = args.get("data", {})
    title     = args.get("title", "")
    x_label   = args.get("x_label", "")
    y_label   = args.get("y_label", "")
    trend     = args.get("trend_line", False)
    style_nm  = args.get("style", "office")
    width     = args.get("width", 8)
    height    = args.get("height", 5)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        st     = _CHART_STYLES.get(style_nm, _CHART_STYLES["office"])
        colors = st["colors"]
        fig, ax = plt.subplots(figsize=(width, height))

        series_list = data.get("series", [])
        if series_list:
            for i, serie in enumerate(series_list):
                x_vals = serie.get("x_values", [])
                y_vals = serie.get("y_values", [])
                label  = serie.get("label", f"Serie {i+1}")
                col    = colors[i % len(colors)]
                ax.scatter(x_vals, y_vals, color=col, s=70, alpha=0.8, label=label, zorder=3)
                if trend and len(x_vals) >= 2:
                    xn, yn = np.array(x_vals, float), np.array(y_vals, float)
                    z = np.polyfit(xn, yn, 1)
                    p = np.poly1d(z)
                    ax.plot(sorted(xn), p(sorted(xn)), "--", color=col, linewidth=1.5, alpha=0.6)
            ax.legend(fontsize=9, facecolor=st["bg"], labelcolor=st["text_c"])
        else:
            x_vals = data.get("x_values", [])
            y_vals = data.get("y_values", [])
            labels = data.get("point_labels", [])
            ax.scatter(x_vals, y_vals, color=colors[0], s=70, alpha=0.8, zorder=3)
            for i, lbl in enumerate(labels):
                if i < len(x_vals):
                    ax.annotate(lbl, (x_vals[i], y_vals[i]), textcoords="offset points",
                                xytext=(5, 5), fontsize=8, color=st["text_c"])
            if trend and len(x_vals) >= 2:
                xn, yn = np.array(x_vals, float), np.array(y_vals, float)
                z = np.polyfit(xn, yn, 1)
                p = np.poly1d(z)
                ax.plot(sorted(xn), p(sorted(xn)), "--", color=colors[1], linewidth=1.5, alpha=0.7)

        if title:
            ax.set_title(title, fontsize=14, fontweight="bold", color=st["text_c"], pad=12)
        if x_label:
            ax.set_xlabel(x_label, fontsize=11, color=st["text_c"])
        if y_label:
            ax.set_ylabel(y_label, fontsize=11, color=st["text_c"])
        _apply_chart_style(fig, ax, style_nm)
        plt.tight_layout()
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output, dpi=st["dpi"], bbox_inches="tight", facecolor=st["bg"])
        plt.close(fig)
        return f"✅ Scatter guardado en: {output}"
    except ImportError as e:
        return f"matplotlib no disponible: {e}\nInstala: pip install matplotlib"
    except Exception as exc:
        return f"Error creando scatter: {exc}"


def _tool_create_stacked_bar_chart(args: dict) -> str:
    """Inserta gráfica de barras apiladas OOXML nativa en .docx, o PNG como respaldo."""
    doc_path = (args.get("path") or args.get("doc_path", "")).strip()
    if doc_path and Path(doc_path).expanduser().suffix.lower() == ".docx":
        p = Path(doc_path).expanduser()
        if not p.exists():
            try:
                from docx import Document as _D
                _d = _D()
                _apply_o365_styles_to_new_doc(_d)
                _d.save(str(p))
            except Exception:
                pass
        ct = "stacked_bar"
        return _tool_doc_insert_chart_native({**args, "path": str(p), "chart_type": ct})
    args_copy = {**args, "stacked": True}
    data = args_copy.get("data", {})
    if "series" not in data and "categories" in data:
        return "Se requiere data.series=[{label, values}] para barras apiladas."
    result = _save_chart_image(args_copy, "bar")
    return result.replace("Gráfica bar guardada", "Gráfica stacked_bar guardada")


def _tool_create_gantt_chart(args: dict) -> str:
    """Genera un diagrama de Gantt con matplotlib."""
    output   = args.get("output", "/tmp/gantt.png")
    tasks    = args.get("tasks", [])
    title    = args.get("title", "Diagrama de Gantt")
    style_nm = args.get("style", "office")
    width    = args.get("width", 12)
    height   = args.get("height", None)

    if not tasks:
        return "Se requiere tasks=[{name, start, end, category?}] para el Gantt."

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from datetime import datetime, date as dt_date
        import numpy as np

        st     = _CHART_STYLES.get(style_nm, _CHART_STYLES["office"])
        colors = st["colors"]

        # Parse dates (support strings YYYY-MM-DD or numbers as day offsets)
        def to_num(d):
            if isinstance(d, (int, float)):
                return float(d)
            try:
                return (datetime.strptime(str(d), "%Y-%m-%d") - datetime(2000, 1, 1)).days
            except Exception:
                return 0.0

        n_tasks  = len(tasks)
        fig_h    = height or max(4, n_tasks * 0.55 + 1.5)
        fig, ax  = plt.subplots(figsize=(width, fig_h))
        fig.patch.set_facecolor(st["bg"])
        ax.set_facecolor(st["bg"])

        categories = list(dict.fromkeys(t.get("category", "General") for t in tasks))
        cat_colors = {c: colors[i % len(colors)] for i, c in enumerate(categories)}

        y_ticks  = []
        y_labels = []
        for i, task in enumerate(tasks):
            y      = n_tasks - i - 1
            start  = to_num(task.get("start", 0))
            end    = to_num(task.get("end", start + 1))
            dur    = end - start
            cat    = task.get("category", "General")
            col    = cat_colors[cat]
            ax.barh(y, dur, left=start, height=0.5, color=col, alpha=0.85,
                    edgecolor=st["spine_c"], linewidth=0.5)
            ax.text(start + dur / 2, y, task.get("name", ""),
                    ha="center", va="center", fontsize=8, color="white",
                    fontweight="bold", clip_on=True)
            y_ticks.append(y)
            y_labels.append(task.get("name", f"Tarea {i+1}"))

        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_labels, fontsize=9, color=st["text_c"])
        ax.set_title(title, fontsize=14, fontweight="bold", color=st["text_c"], pad=12)
        ax.tick_params(colors=st["text_c"])
        ax.grid(True, axis="x", color=st["grid_c"], linestyle="--", linewidth=0.6, alpha=0.8)
        for spine in ax.spines.values():
            spine.set_edgecolor(st["spine_c"])
        if len(categories) > 1:
            legend_patches = [mpatches.Patch(color=cat_colors[c], label=c) for c in categories]
            ax.legend(handles=legend_patches, fontsize=9, loc="lower right",
                      facecolor=st["bg"], labelcolor=st["text_c"])

        plt.tight_layout()
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output, dpi=st["dpi"], bbox_inches="tight", facecolor=st["bg"])
        plt.close(fig)
        return f"✅ Gantt guardado en: {output} ({n_tasks} tareas)"
    except ImportError as e:
        return f"matplotlib no disponible: {e}\nInstala: pip install matplotlib"
    except Exception as exc:
        return f"Error creando Gantt: {exc}"


def _tool_create_org_chart(args: dict) -> str:
    """Genera un organigrama jerárquico en Word con tabla nativa O365 (editable, sin matplotlib).

    nodes: [{id, label, parent?}]  — parent es el id del nodo padre (omitir para raíz).
    path/output: ruta del .docx a crear o en el que insertar el organigrama.
    """
    doc_path = (args.get("path") or args.get("output", "/tmp/org_chart.docx")).strip()
    nodes    = args.get("nodes", [])
    title    = args.get("title", "Organigrama")

    if not nodes:
        return "Se requiere nodes=[{id, label, parent?}] para el organigrama."

    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Cm
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        from collections import deque

        by_id: dict    = {n["id"]: n for n in nodes}
        children: dict = {n["id"]: [] for n in nodes}
        roots: list    = []
        for n in nodes:
            p_id = n.get("parent")
            if p_id and p_id in children:
                children[p_id].append(n["id"])
            else:
                roots.append(n["id"])

        levels: dict = {}
        order:  list = []
        q = deque()
        for r in roots:
            levels[r] = 0
            q.append(r)
        while q:
            nid = q.popleft()
            order.append(nid)
            for c in children.get(nid, []):
                levels[c] = levels[nid] + 1
                q.append(c)
        for n in nodes:
            if n["id"] not in levels:
                levels[n["id"]] = 0
                order.append(n["id"])

        by_level: dict = {}
        for nid in order:
            lv = levels.get(nid, 0)
            by_level.setdefault(lv, []).append(nid)

        max_level    = max(levels.values()) if levels else 0
        max_per_row  = max(len(v) for v in by_level.values()) if by_level else 1
        level_colors = ["2F5496", "4472C4", "5B9BD5", "9DC3E6", "BDD7EE", "DEEAF1"]

        p_path = Path(doc_path).expanduser()
        if p_path.exists():
            doc = Document(str(p_path))
        else:
            doc = Document()
            _apply_o365_styles_to_new_doc(doc)

        if title:
            h = doc.add_paragraph()
            try:
                h.style = doc.styles["Heading 2"]
            except Exception:
                pass
            h.add_run(title)

        def _shade(cell, hex_color: str) -> None:
            try:
                tcPr = cell._tc.get_or_add_tcPr()
                shd  = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), hex_color)
                tcPr.append(shd)
            except Exception:
                pass

        n_cols = max(max_per_row, 1)
        n_rows = max_level + 1
        tbl    = doc.add_table(rows=n_rows, cols=n_cols)
        try:
            tbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception:
            pass

        for level in range(n_rows):
            row_nodes      = by_level.get(level, [])
            n_in_row       = len(row_nodes)
            color          = level_colors[level % len(level_colors)]
            cells_per_node = max(1, n_cols // max(n_in_row, 1))

            for node_i, nid in enumerate(row_nodes):
                node_label = by_id.get(nid, {}).get("label", nid)
                start_col  = node_i * cells_per_node
                end_col    = min(start_col + cells_per_node - 1, n_cols - 1)

                try:
                    if end_col > start_col:
                        cell = tbl.rows[level].cells[start_col].merge(
                            tbl.rows[level].cells[end_col])
                    else:
                        cell = tbl.rows[level].cells[min(start_col, n_cols - 1)]
                except Exception:
                    cell = tbl.rows[level].cells[min(start_col, n_cols - 1)]

                cell.text = ""
                p_cell = cell.paragraphs[0]
                p_cell.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_cell.paragraph_format.space_before = Pt(6)
                p_cell.paragraph_format.space_after  = Pt(6)
                run = p_cell.add_run(node_label)
                run.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.font.size = Pt(max(8, 11 - min(level, 3)))
                _shade(cell, color)

            for c_i in range(n_in_row * cells_per_node, n_cols):
                try:
                    _shade(tbl.rows[level].cells[c_i], "F5F5F5")
                except Exception:
                    pass

        col_w = Cm(max(0.5, 16.0 / n_cols))
        for row in tbl.rows:
            for cell in row.cells:
                try:
                    cell.width = col_w
                except Exception:
                    pass

        dest = str(p_path)
        doc.save(dest)
        return f"✅ Organigrama guardado en: {dest} ({len(nodes)} nodos, {max_level+1} niveles)"

    except ImportError as e:
        return f"python-docx no disponible: {e}"
    except Exception as exc:
        return f"Error creando organigrama: {exc}"


def _tool_create_heatmap(args: dict) -> str:
    """Genera un heatmap nativo en Word (tabla O365 con celdas coloreadas, sin matplotlib).

    data: matriz 2D de valores [[fila1], [fila2], ...]
    path/output: ruta del .docx a crear o en el que insertar el heatmap.
    colormap: Blues | Reds | RdYlGn | YlOrRd | viridis
    """
    doc_path   = (args.get("path") or args.get("output", "/tmp/heatmap.docx")).strip()
    data_vals  = args.get("data", [])
    row_labels = args.get("row_labels", [])
    col_labels = args.get("col_labels", [])
    title      = args.get("title", "")
    colormap   = args.get("colormap", "Blues")
    show_vals  = args.get("show_values", True)
    fmt        = args.get("value_format", ".1f")

    if not data_vals:
        return "Se requiere data=[[...], [...]] con los valores del heatmap."

    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Cm
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        flat  = [v for row in data_vals for v in row if isinstance(v, (int, float))]
        v_min = min(flat) if flat else 0.0
        v_max = max(flat) if flat else 1.0
        v_rng = max(v_max - v_min, 1e-9)

        palettes = {
            "Blues":   ((222, 235, 247), (8,   48,  107)),
            "Reds":    ((254, 229, 217), (165, 15,  21)),
            "RdYlGn":  ((215, 48,  39),  (26,  152, 80)),
            "YlOrRd":  ((255, 255, 178), (189, 0,   38)),
            "viridis": ((68,  1,   84),   (253, 231, 37)),
        }

        def _interp(t: float) -> str:
            t = max(0.0, min(1.0, t))
            lo, hi = palettes.get(colormap, palettes["Blues"])
            r = int(lo[0] + (hi[0] - lo[0]) * t)
            g = int(lo[1] + (hi[1] - lo[1]) * t)
            b = int(lo[2] + (hi[2] - lo[2]) * t)
            return f"{max(0,min(255,r)):02X}{max(0,min(255,g)):02X}{max(0,min(255,b)):02X}"

        def _shade(cell, hex_color: str) -> None:
            try:
                tcPr = cell._tc.get_or_add_tcPr()
                shd  = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), hex_color)
                tcPr.append(shd)
            except Exception:
                pass

        n_rows = len(data_vals)
        n_cols = max(len(r) for r in data_vals) if data_vals else 1
        has_rl = bool(row_labels)
        has_cl = bool(col_labels)

        p_path = Path(doc_path).expanduser()
        if p_path.exists():
            doc = Document(str(p_path))
        else:
            doc = Document()
            _apply_o365_styles_to_new_doc(doc)

        if title:
            h = doc.add_paragraph()
            try:
                h.style = doc.styles["Heading 2"]
            except Exception:
                pass
            h.add_run(title)

        tbl_rows = n_rows + (1 if has_cl else 0)
        tbl_cols = n_cols + (1 if has_rl else 0)
        tbl      = doc.add_table(rows=tbl_rows, cols=tbl_cols)

        if has_cl:
            h_row = tbl.rows[0]
            if has_rl:
                _shade(h_row.cells[0], "2F5496")
            for c_i, lbl in enumerate(col_labels[:n_cols]):
                cell = h_row.cells[c_i + (1 if has_rl else 0)]
                cell.text = lbl
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in cell.paragraphs[0].runs:
                    run.bold = True
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                _shade(cell, "2F5496")

        for r_i, row_data in enumerate(data_vals):
            tr_i = r_i + (1 if has_cl else 0)
            if tr_i >= len(tbl.rows):
                break
            row = tbl.rows[tr_i]
            if has_rl:
                lbl_cell = row.cells[0]
                lbl_cell.text = row_labels[r_i] if r_i < len(row_labels) else ""
                for run in lbl_cell.paragraphs[0].runs:
                    run.bold = True
                    run.font.size = Pt(9)
                _shade(lbl_cell, "E9EFF7")
            for c_i, val in enumerate(row_data[:n_cols]):
                if not isinstance(val, (int, float)):
                    continue
                t    = (val - v_min) / v_rng
                hx   = _interp(t)
                cell = row.cells[c_i + (1 if has_rl else 0)]
                _shade(cell, hx)
                if show_vals:
                    cell.text = ""
                    p_cell = cell.paragraphs[0]
                    p_cell.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p_cell.add_run(format(val, fmt))
                    run.font.size = Pt(8)
                    run.font.color.rgb = (RGBColor(0xFF, 0xFF, 0xFF)
                                          if t > 0.55 else RGBColor(0x30, 0x30, 0x30))

        cell_w = Cm(max(0.7, 15.0 / max(tbl_cols, 1)))
        for row in tbl.rows:
            for cell in row.cells:
                try:
                    cell.width = cell_w
                except Exception:
                    pass

        dest = str(p_path)
        doc.save(dest)
        return f"✅ Heatmap guardado en: {dest} ({n_rows}×{n_cols})"

    except ImportError as e:
        return f"python-docx no disponible: {e}"
    except Exception as exc:
        return f"Error creando heatmap: {exc}"


def _tool_create_radar_chart(args: dict) -> str:
    """Inserta gráfico radar/spider OOXML nativo en .docx (editable, sin matplotlib).

    Si 'path' apunta a un .docx (existente o nuevo), inserta radar DrawingML nativo.
    categories: ejes del radar; series: [{label, values}].
    """
    doc_path   = (args.get("path") or args.get("doc_path") or "").strip()
    categories = args.get("categories", [])
    series     = args.get("series", [])
    title      = args.get("title", "")

    if not categories or not series:
        return "Se requiere categories=[...] y series=[{label, values}]."

    if not doc_path:
        return "Se requiere 'path' con la ruta al .docx donde insertar el gráfico radar."

    p = Path(doc_path).expanduser()
    if not p.exists() and doc_path.lower().endswith(".docx"):
        try:
            from docx import Document as _D
            _d = _D()
            _apply_o365_styles_to_new_doc(_d)
            _d.save(str(p))
        except Exception:
            pass

    return _tool_doc_insert_chart_native({
        "path":          str(p),
        "chart_type":    "radar",
        "data":          {"categories": categories, "series": series},
        "title":         title,
        "width_inches":  float(args.get("width", 5.5)),
        "height_inches": float(args.get("height", 4.0)),
        "output_path":   args.get("output_path", ""),
    })


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
                from copy import copy as _copy
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
        from pptx.util import Inches
        from pptx.dml.color import RGBColor as PptxRGB
        from pptx.oxml.ns import qn as pqn
        from lxml import etree

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
            layout = slide.slide_layout

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
      {"type": "markdown",      "text": "# H1\\n**bold** párrafo..."}
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
            _md_populate_doc(doc, block.get("text", ""))
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
        from docx.shared import Cm, Emu
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
        from pptx.util import Inches, Pt

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

_TOOLS = [
    {
        "name": "email_list",
        "description": "Lista emails de una bandeja de entrada (IMAP). Requiere configuración en ~/.oocode/home_office.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mailbox": {"type": "string", "description": "Carpeta IMAP. Default: INBOX"},
                "limit":   {"type": "integer", "description": "Máximo de emails a devolver (max 50). Default: 10"},
            },
        },
    },
    {
        "name": "email_read",
        "description": "Lee un email completo por su UID IMAP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uid":     {"type": "string",  "description": "UID del email (obtenido de email_list)"},
                "mailbox": {"type": "string",  "description": "Carpeta IMAP. Default: INBOX"},
            },
            "required": ["uid"],
        },
    },
    {
        "name": "email_send",
        "description": "Envía un email por SMTP. Requiere configuración en ~/.oocode/home_office.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to":      {"type": "string", "description": "Destinatario(s), separados por coma"},
                "subject": {"type": "string", "description": "Asunto del email"},
                "body":    {"type": "string", "description": "Cuerpo del email (texto plano)"},
                "cc":      {"type": "string", "description": "CC (opcional)"},
                "bcc":     {"type": "string", "description": "BCC (opcional)"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "email_search",
        "description": "Busca emails por asunto o contenido usando IMAP SEARCH.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":   {"type": "string",  "description": "Texto a buscar en asunto y cuerpo"},
                "mailbox": {"type": "string",  "description": "Carpeta IMAP. Default: INBOX"},
                "limit":   {"type": "integer", "description": "Máximo de resultados. Default: 20"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "doc_convert",
        "description": "Convierte documentos entre formatos usando pandoc (md↔docx, md→pdf, html→md, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path":    {"type": "string", "description": "Ruta al fichero de entrada"},
                "output_format": {"type": "string", "description": "Formato de salida: pdf, docx, html, md, odt, rst, epub"},
                "output_path":   {"type": "string", "description": "Ruta del fichero de salida (opcional; por defecto mismo nombre con nueva extensión)"},
            },
            "required": ["input_path", "output_format"],
        },
    },
    {
        "name": "pdf_extract_text",
        "description": "Extrae texto de un PDF. Usa pdftotext (poppler) o pdfplumber.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Ruta al fichero PDF"},
                "pages": {"type": "string", "description": "Rango de páginas, p.ej. '1-5' (opcional)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "doc_word_count",
        "description": "Cuenta palabras, líneas, caracteres y párrafos de un documento de texto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta al fichero (txt, md, rst, html…)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "xlsx_read",
        "description": "Lee celdas o rango de un archivo Excel (.xlsx) o CSV. Requiere openpyxl para .xlsx.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string",  "description": "Ruta al fichero .xlsx o .csv"},
                "sheet": {"type": "string",  "description": "Nombre de la hoja (solo .xlsx; por defecto la primera)"},
                "range": {"type": "string",  "description": "Rango de celdas, p.ej. 'A1:D10' (pendiente en v1)"},
                "limit": {"type": "integer", "description": "Máximo de filas a devolver. Default: 50"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "xlsx_write",
        "description": "Escribe un valor en una celda de un archivo Excel (.xlsx). Crea el fichero si no existe.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Ruta al fichero .xlsx"},
                "sheet": {"type": "string", "description": "Nombre de la hoja. Default: Hoja1"},
                "cell":  {"type": "string", "description": "Celda, p.ej. 'B3'"},
                "value": {"description": "Valor a escribir (string, número o booleano)"},
                "style": {"type": "object", "description": 'Estilo de la celda (opcional): {"bold": true, "italic": true, "underline": true, "font_size": 12, "font_color": "#FF0000", "bg_color": "#FFFF00", "align": "center", "wrap_text": true, "border": true, "number_format": "#,##0.00"}'},
            },
            "required": ["path", "cell", "value"],
        },
    },
    {
        "name": "csv_analyze",
        "description": "Analiza un fichero CSV: cabeceras, primeras filas, estadísticas de columnas numéricas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string",  "description": "Ruta al fichero CSV"},
                "limit": {"type": "integer", "description": "Filas de muestra a mostrar. Default: 5"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "cal_list",
        "description": "Lista eventos de un fichero .ics local, con filtro opcional por rango de fechas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Ruta al fichero .ics (por defecto: calendar_file en config)"},
                "start":  {"type": "string", "description": "Fecha inicio filtro, formato YYYY-MM-DD (opcional)"},
                "end":    {"type": "string", "description": "Fecha fin filtro, formato YYYY-MM-DD (opcional)"},
                "limit":  {"type": "integer", "description": "Máximo de eventos. Default: 15"},
            },
        },
    },
    {
        "name": "cal_add",
        "description": "Añade un evento a un fichero .ics local.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string", "description": "Título del evento"},
                "start":       {"type": "string", "description": "Fecha/hora inicio: YYYY-MM-DD o YYYY-MM-DDTHH:MM"},
                "end":         {"type": "string", "description": "Fecha/hora fin (opcional)"},
                "location":    {"type": "string", "description": "Lugar (opcional)"},
                "description": {"type": "string", "description": "Descripción (opcional)"},
                "file":        {"type": "string", "description": "Ruta al fichero .ics (por defecto: calendar_file en config)"},
            },
            "required": ["title", "start"],
        },
    },
    {
        "name": "cal_search",
        "description": "Busca eventos en un fichero .ics por texto en título o descripción.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":  {"type": "string", "description": "Texto a buscar"},
                "source": {"type": "string", "description": "Ruta al fichero .ics (opcional)"},
                "limit":  {"type": "integer", "description": "Máximo de resultados. Default: 20"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "notes_list",
        "description": "Lista ficheros markdown en el directorio de notas, ordenados por fecha de modificación.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string",  "description": "Directorio de notas (por defecto: notes_dir en config)"},
                "pattern":   {"type": "string",  "description": "Patrón glob. Default: *.md"},
                "limit":     {"type": "integer", "description": "Máximo de notas. Default: 20"},
            },
        },
    },
    {
        "name": "notes_search",
        "description": "Busca texto en ficheros markdown del directorio de notas usando ripgrep o grep.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":     {"type": "string",  "description": "Texto a buscar"},
                "directory": {"type": "string",  "description": "Directorio de notas (opcional)"},
                "limit":     {"type": "integer", "description": "Máximo de ficheros con resultados. Default: 10"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "notes_save",
        "description": "Guarda o actualiza una nota markdown con front matter (title, created, modified).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title":     {"type": "string", "description": "Título de la nota (también determina el nombre del fichero)"},
                "content":   {"type": "string", "description": "Contenido en markdown"},
                "directory": {"type": "string", "description": "Directorio donde guardar (opcional)"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "image_to_text",
        "description": "Extrae texto de una imagen usando tesseract OCR. Requiere tesseract instalado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta a la imagen (PNG, JPG, TIFF…)"},
                "lang": {"type": "string", "description": "Idiomas tesseract, p.ej. 'spa+eng'. Default: spa+eng"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "contact_search",
        "description": "Busca en ficheros vCard (.vcf) por nombre, email, teléfono u organización.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":   {"type": "string", "description": "Texto a buscar en los contactos"},
                "vcf_dir": {"type": "string", "description": "Directorio de contactos (por defecto: contacts_dir en config)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "markdown_to_html",
        "description": "Convierte markdown a HTML. Usa python-markdown, pandoc o conversión básica.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Texto markdown (alternativa a path)"},
                "path":    {"type": "string", "description": "Ruta a un fichero .md (alternativa a content)"},
                "output":  {"type": "string", "description": "Ruta de salida .html (opcional; sin ruta: devuelve el HTML)"},
            },
        },
    },
    # ── Template and IT report tools ────────────────────────────────────────
    {
        "name": "doc_read_template_fields",
        "description": "Extrae los campos {{CAMPO}} de una plantilla .docx, .md o .txt. Útil para saber qué datos rellenar antes de usar doc_fill_template.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta a la plantilla (.docx, .md, .txt, .html)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "doc_fill_template",
        "description": "Rellena una plantilla .docx/.xlsx/.pptx o texto con valores de campos. "
                       "Motor primario: docxtpl (Jinja2 — soporta {{ campo }}, loops y condicionales, preserva estilos). "
                       "Fallback automático a python-docx para plantillas con {{CAMPO}} sin Jinja2. "
                       "Para .xlsx usa openpyxl; para .pptx usa python-pptx. "
                       "NOTA: Para plantillas corporativas con {{CAMPO}} y estilos avanzados (portada, TOC, pie de página), "
                       "usa doc_fill_corporate_template que garantiza preservación 100% del formato.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_path": {"type": "string", "description": "Ruta a la plantilla (.docx, .dotx, .xlsx, .pptx, .md, .txt)"},
                "fields":        {"type": "object", "description": 'Objeto JSON con {campo: valor}. Se proveen automáticamente en mayúsculas y minúsculas. Ej: {"nombre": "Juan", "fecha": "2026-05-21"}'},
                "output_path":   {"type": "string", "description": "Ruta del fichero de salida (opcional; añade timestamp por defecto)"},
                "use_jinja":     {"type": "boolean", "description": "Usar motor Jinja2/docxtpl (default: true). Pon false solo si la plantilla tiene sintaxis custom no-Jinja."},
            },
            "required": ["template_path", "fields"],
        },
    },
    {
        "name": "doc_fill_corporate_template",
        "description": "Rellena una plantilla .docx corporativa preservando AL 100% los estilos, imágenes, fondos, "
                       "tablas, cabeceras, pies de página y layout originales. "
                       "Usa manipulación XML directa (ZIP+lxml) para sanear placeholders {{CAMPO}} partidos entre "
                       "runs de Word, reemplazar en cuerpo/tablas/cabeceras/pies/cuadros de texto, "
                       "y marcar el TOC para que Word lo actualice al abrir. "
                       "Para contenido multipárrafo: proporciona el valor como lista de strings o string con \\n\\n "
                       "entre párrafos. "
                       "FLUJO RECOMENDADO: 1) doc_read_template_fields → 2) doc_fill_corporate_template. "
                       "USAR SIEMPRE para plantillas corporativas (.docx) con portada, TOC o estilos de empresa.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_path": {
                    "type": "string",
                    "description": "Ruta absoluta a la plantilla .docx o .dotx corporativa",
                },
                "fields": {
                    "type": "object",
                    "description": (
                        "Diccionario de campos a rellenar. Claves = nombres de los {{CAMPO}} (sin llaves). "
                        "Valores = string para una línea, lista de strings para múltiples párrafos, "
                        "o string con \\n\\n como separador de párrafos. "
                        'Ejemplo: {"TITULO": "Documento de Análisis", "PROYECTO": "MiProyecto", '
                        '"FECHA": "2026-05-28", "CONTENIDO_SECCION_1": ["Intro párrafo 1.", "Intro párrafo 2."]}'
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": "Ruta de salida del documento rellenado (opcional; añade timestamp al nombre por defecto)",
                },
                "update_toc": {
                    "type": "boolean",
                    "description": "Marcar el TOC para que Word lo recalcule al abrir (default: true). Requiere abrir el .docx en Word/LibreOffice.",
                },
            },
            "required": ["template_path", "fields"],
        },
    },
    {
        "name": "doc_create",
        "description": "Crea un documento Word (.docx), Excel (.xlsx) o PowerPoint (.pptx) profesional con estilos O365 nativos (Calibri/Calibri Light, colores Office, OOXML nativo). "
                       "Para .docx: soporta content_blocks (title, heading, paragraph, bullet_list, numbered_list, table, chart OOXML, image, checklist, callout, highlight, toc, signature_block, code_block, pagebreak, horizontal_rule) "
                       "o markdown (convertido a OOXML completo). Con template_path hereda todos los estilos, cabecera/pie y márgenes corporativos. "
                       "Para .xlsx: hojas con tablas nativas, gráficas O365 y formatos condicionales. "
                       "Para .pptx: diapositivas con temas, gráficas nativas y layouts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":           {"type": "string", "description": "Ruta de salida del documento (.docx/.xlsx/.pptx)"},
                "title":          {"type": "string", "description": "Título del documento (portada/hoja/presentación)"},
                "subtitle":       {"type": "string", "description": "Subtítulo (solo .docx y .pptx)"},
                "theme":          {"type": "string", "description": "Tema de color: office (default) | modern | professional | minimal | corporate | dark"},
                "template_path":  {"type": "string", "description": "Plantilla corporativa .docx/.dotx para heredar estilos, fuentes, cabecera/pie y márgenes. El contenido blocks se añade conservando el formato de la plantilla."},
                "markdown":       {"type": "string", "description": "Contenido markdown para .docx. Se convierte a Word OOXML completo (estilos, tablas, listas, imágenes inline)."},
                "content_blocks": {
                    "type": "array",
                    "description": "Bloques O365 nativos para .docx. Tipos: title, heading, paragraph, bullet_list, numbered_list, table, chart (DrawingML OOXML nativo — NO matplotlib), image, checklist, callout, highlight, toc, signature_block, code_block, markdown, pagebreak, horizontal_rule.",
                    "items": {"type": "object"},
                },
                "sheets": {
                    "type": "array",
                    "description": "Hojas Excel para .xlsx. Cada hoja: {name, title, headers, rows, charts, conditional_formats}",
                    "items": {"type": "object"},
                },
                "slides": {
                    "type": "array",
                    "description": "Diapositivas para .pptx. Cada slide: {title, content, layout, notes, blocks}",
                    "items": {"type": "object"},
                },
                "metadata": {
                    "type": "object",
                    "description": "Metadatos del documento Word: {author, subject, company, keywords}",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "doc_list_templates",
        "description": "Lista las plantillas de documentos disponibles (.docx, .xlsx, .md) en el directorio de plantillas configurado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directorio de plantillas (por defecto: templates_dir en config)"},
            },
        },
    },
    {
        "name": "doc_create_rfc",
        "description": "Genera un documento RFC/Request for Change estructurado para cambios de infraestructura IT. Por defecto genera .docx (usando pandoc o python-docx); usa format='md' para markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title":            {"type": "string", "description": "Título del cambio"},
                "requester":        {"type": "string", "description": "Nombre del solicitante"},
                "date":             {"type": "string", "description": "Fecha de solicitud (YYYY-MM-DD). Default: hoy"},
                "priority":         {"type": "string", "description": "Prioridad: Alta/Media/Baja. Default: Media"},
                "change_type":      {"type": "string", "description": "Tipo: Normal/Estándar/Urgente. Default: Normal"},
                "affected_systems": {"type": "string", "description": "Sistemas/servidores afectados"},
                "description":      {"type": "string", "description": "Descripción detallada del cambio"},
                "justification":    {"type": "string", "description": "Justificación y beneficios"},
                "risk":             {"type": "string", "description": "Descripción de riesgos identificados"},
                "risk_level":       {"type": "string", "description": "Nivel de riesgo: Alto/Medio/Bajo. Default: Bajo"},
                "rollback_plan":    {"type": "string", "description": "Plan de marcha atrás"},
                "testing_plan":     {"type": "string", "description": "Plan de pruebas post-implementación"},
                "implementation_steps": {"type": "string", "description": "Pasos de implementación"},
                "scheduled_date":   {"type": "string", "description": "Fecha programada del cambio"},
                "scheduled_window": {"type": "string", "description": "Ventana de mantenimiento"},
                "approver":         {"type": "string", "description": "Nombre del aprobador"},
                "output_path":      {"type": "string", "description": "Ruta del fichero de salida (la extensión puede ser .docx o .md). Si se omite, se guarda automáticamente en notes_dir."},
                "format":           {"type": "string", "description": "Formato de salida: 'docx' (default) o 'md'. Con 'docx' requiere pandoc o python-docx; si no están disponibles cae a .md."},
            },
            "required": ["title", "requester"],
        },
    },
    {
        "name": "xlsx_fill_range",
        "description": "Escribe múltiples celdas a la vez en un fichero Excel. Ideal para rellenar plantillas de informes. Soporta estilos por celda.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Ruta al fichero .xlsx (se crea si no existe)"},
                "sheet": {"type": "string", "description": "Nombre de la hoja. Default: Hoja1"},
                "cells": {"description": 'Dict simple {"A1": "Título", "B2": 42} O lista de objetos [{"cell": "A1", "value": "Título", "style": {"bold": true, "bg_color": "#4472C4", "font_color": "#FFFFFF"}}]'},
                "style": {"type": "object", "description": 'Estilo global aplicado a todas las celdas (opcional): {"bold": true, "italic": true, "font_size": 11, "font_color": "#000000", "bg_color": "#FFFFFF", "align": "center", "wrap_text": false, "border": false, "number_format": "General"}'},
            },
            "required": ["path", "cells"],
        },
    },
    {
        "name": "xlsx_append_row",
        "description": "Añade una fila de datos al final de una hoja Excel. Útil para registros de incidencias o logs. Soporta estilos por celda.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":   {"type": "string", "description": "Ruta al fichero .xlsx"},
                "sheet":  {"type": "string", "description": "Nombre de la hoja. Default: Hoja1"},
                "values": {"type": "array",  "description": 'Lista de valores para la nueva fila. Cada elemento puede ser un valor simple o un objeto {"value": ..., "style": {"bold": true, "font_color": "#FF0000", ...}}'},
                "style":  {"type": "object", "description": 'Estilo global para toda la fila (opcional): {"bold": true, "bg_color": "#D9E1F2", "border": true, "align": "center"}'},
            },
            "required": ["path", "values"],
        },
    },
    {
        "name": "xlsx_create_report",
        "description": "Crea un informe Excel con tabla nativa con estilo nombrado, auto-ancho y cabecera congelada.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":         {"type": "string", "description": "Ruta del fichero .xlsx a crear"},
                "headers":      {"type": "array",  "description": "Lista de nombres de columnas"},
                "rows":         {"type": "array",  "description": "Lista de listas con los datos (una lista por fila)"},
                "title":        {"type": "string", "description": "Título del informe (fila superior fusionada, opcional)"},
                "sheet":        {"type": "string", "description": "Nombre de la hoja. Default: Informe"},
                "table_style":  {"type": "string", "description": "Estilo de tabla Excel. Default: TableStyleMedium9. Opciones: TableStyleLight1-21, TableStyleMedium1-28, TableStyleDark1-11"},
                "freeze_header":{"type": "boolean","description": "Congelar fila de cabecera. Default: true"},
            },
            "required": ["path", "headers"],
        },
    },
    {
        "name": "xlsx_create_table",
        "description": "Crea una tabla Excel nativa (objeto Table) con estilo nombrado, filtros y ordenación automáticos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":         {"type": "string", "description": "Ruta del fichero .xlsx (se crea si no existe)"},
                "sheet":        {"type": "string", "description": "Nombre de la hoja. Default: Datos"},
                "headers":      {"type": "array",  "description": "Lista de nombres de columnas"},
                "rows":         {"type": "array",  "description": "Lista de listas de datos"},
                "table_style":  {"type": "string", "description": "Estilo de tabla. Default: TableStyleMedium9"},
                "table_name":   {"type": "string", "description": "Nombre interno de la tabla Excel. Default: Tabla1"},
                "start_cell":   {"type": "string", "description": "Celda de inicio. Default: A1"},
                "freeze_header":{"type": "boolean","description": "Congelar cabecera. Default: true"},
            },
            "required": ["path", "headers"],
        },
    },
    # ── Workspace / Project context ──────────────────────────────────────────
    {
        "name": "project_context_read",
        "description": "Lee el fichero OOCODE.md del directorio de trabajo y devuelve metadatos del proyecto (cliente, tipo, naming, directorios) junto con el cuerpo completo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta al OOCODE.md (opcional; por defecto: OOCODE.md en cwd)"},
            },
        },
    },
    {
        "name": "project_init_office",
        "description": "Inicializa la estructura de directorios para un proyecto IT/oficina: crea OOCODE.md, subdirectorios (docs/rfcs, docs/reports, etc.), cmdb.csv y risk_register.csv.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project":      {"type": "string", "description": "Nombre del proyecto"},
                "client":       {"type": "string", "description": "Cliente o empresa"},
                "project_type": {"type": "string", "description": "Tipo: IT/DC/Cloud/Infra/General. Default: IT"},
                "naming":       {"type": "string", "description": "Patrón de nombres: p.ej. {CLIENT}-{TYPE}-{YYMMDD}-v{VER}"},
                "templates_dir":{"type": "string", "description": "Directorio de plantillas relativo al proyecto (opcional)"},
                "directory":    {"type": "string", "description": "Directorio donde crear el proyecto (por defecto: cwd)"},
            },
            "required": ["project"],
        },
    },
    {
        "name": "doc_project_save",
        "description": "Guarda un documento en el subdirectorio correcto del proyecto (docs/rfcs, docs/reports, docs/incidents…). Los tipos formales (rfc, report, meeting, plan, incident) usan .docx por defecto; 'general' usa .md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content":   {"type": "string", "description": "Contenido del documento en markdown o texto"},
                "doc_type":  {"type": "string", "description": "Tipo: rfc/change_request/report/informe/meeting/acta/incident/incidencia/plan/migration/general"},
                "filename":  {"type": "string", "description": "Nombre de fichero completo (con extensión). Si se omite se genera automáticamente con naming convention."},
                "ext":       {"type": "string", "description": "Extensión cuando no se da filename: '.docx' (default para tipos formales) o '.md'"},
                "directory": {"type": "string", "description": "Directorio base del proyecto (por defecto: cwd/docs)"},
            },
            "required": ["content", "doc_type"],
        },
    },
    # ── Document intelligence ────────────────────────────────────────────────
    {
        "name": "doc_read",
        "description": "Lee el contenido de un documento .docx o .md. Opcionalmente extrae sólo una sección por su encabezado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Ruta al documento (.docx o .md)"},
                "section": {"type": "string", "description": "Encabezado de sección a extraer (opcional; sin él devuelve todo)"},
                "max_chars":{"type": "integer","description": "Límite de caracteres devueltos. Default: 8000"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "doc_update_section",
        "description": "Reemplaza el contenido de una sección (identificada por su encabezado) en un documento .md o .docx. Para .md hace edición nativa; para .docx requiere python-docx.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string", "description": "Ruta al documento (.md o .docx)"},
                "section":     {"type": "string", "description": "Texto exacto del encabezado de la sección a reemplazar"},
                "new_content": {"type": "string", "description": "Nuevo contenido de la sección (markdown o texto)"},
            },
            "required": ["path", "section", "new_content"],
        },
    },
    {
        "name": "doc_version_bump",
        "description": "Incrementa la versión de un documento .md con front matter YAML (version: X.Y.Z) o que contenga vX.Y en sus primeras líneas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta al documento .md"},
                "bump": {"type": "string", "description": "Parte a incrementar: major/minor/patch. Default: patch"},
            },
            "required": ["path"],
        },
    },
    # ── CMDB & Asset register ────────────────────────────────────────────────
    {
        "name": "cmdb_search",
        "description": "Busca en la base de datos de gestión de configuración (CMDB) en formato CSV/XLSX/JSON. Soporta búsqueda por texto libre o por campo específico.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":      {"type": "string",  "description": "Texto a buscar (usa * para listar todo)"},
                "field":      {"type": "string",  "description": "Columna donde buscar (opcional; sin ella busca en todas)"},
                "cmdb_path":  {"type": "string",  "description": "Ruta al fichero CMDB (opcional; auto-detectado en cwd y ~/Documents/)"},
                "limit":      {"type": "integer", "description": "Máximo de resultados. Default: 20"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "cmdb_update",
        "description": "Actualiza un registro en la CMDB CSV identificado por un campo clave.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key_field":  {"type": "string", "description": "Nombre de la columna clave (p.ej. 'hostname' o 'asset_id')"},
                "key_value":  {"type": "string", "description": "Valor del campo clave del registro a actualizar"},
                "updates":    {"type": "object", "description": "Dict con {columna: nuevo_valor} a actualizar"},
                "cmdb_path":  {"type": "string", "description": "Ruta al fichero CMDB CSV (opcional; auto-detectado)"},
            },
            "required": ["key_field", "key_value", "updates"],
        },
    },
    {
        "name": "asset_register_add",
        "description": "Añade un nuevo activo al registro de activos CSV. Si el fichero no existe lo crea con las cabeceras apropiadas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset":       {"type": "object", "description": "Dict con los campos del activo: {hostname, ip, type, os, location, owner, status, ...}"},
                "register_path":{"type": "string","description": "Ruta al fichero CSV del registro (opcional; por defecto: asset_register.csv en cwd)"},
            },
            "required": ["asset"],
        },
    },
    # ── Creación de documentos O365 desde plantilla ───────────────────────────
    {
        "name": "doc_create_from_template",
        "description": "Crea un .docx NUEVO desde plantilla corporativa (.docx/.dotx), heredando estilos, fuentes, cabecera/pie, logo y márgenes. Soporta TODOS los block types: heading, paragraph, bullet_list, numbered_list, table, chart (OOXML nativo), image, checklist, callout, highlight, toc, signature_block, code_block, markdown, pagebreak, horizontal_rule. USAR SIEMPRE cuando el usuario tiene plantillas corporativas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_path":       {"type": "string", "description": "Ruta a la plantilla .docx o .dotx de la empresa"},
                "output_path":         {"type": "string", "description": "Ruta del fichero de salida .docx"},
                "content_blocks":      {"type": "array",  "description": "Lista de bloques de contenido O365 nativos. Tipos: heading, paragraph, bullet_list, numbered_list, table, chart, image, checklist, callout, highlight, toc, signature_block, code_block, markdown, pagebreak, horizontal_rule"},
                "fields":              {"type": "object", "description": "Campos Jinja2 para rellenar la plantilla antes de añadir bloques (ej: {NOMBRE: 'Juan', FECHA: '2024-01'})"},
                "clear_template_body": {"type": "boolean","description": "Limpiar el cuerpo antes de añadir bloques (para .dotx siempre se limpia). Default: false"},
            },
            "required": ["output_path", "content_blocks"],
        },
    },
    {
        "name": "doc_add_content_block",
        "description": "Añade bloques de contenido a un .docx EXISTENTE sin borrar el contenido previo. Útil para añadir secciones a un documento rellenado desde plantilla.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":           {"type": "string", "description": "Ruta al .docx existente"},
                "content_blocks": {"type": "array",  "description": "Lista de bloques a añadir (mismos tipos que doc_create_from_template)"},
                "output_path":    {"type": "string", "description": "Ruta de salida (omitir = sobreescribe el original)"},
            },
            "required": ["path", "content_blocks"],
        },
    },
    {
        "name": "doc_set_page_layout",
        "description": "Configura el diseño de página de un .docx: tamaño (A4/Letter/Legal/A3), orientación (portrait/landscape) y márgenes en cm.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string", "description": "Ruta al fichero .docx"},
                "page_size":   {"type": "string", "description": "Tamaño: A4 (default), Letter, Legal, A3"},
                "orientation": {"type": "string", "description": "portrait (default) | landscape"},
                "margins_cm":  {"type": "object", "description": "Márgenes en cm: {top, bottom, left, right}. Ej: {top:2.5, bottom:2.5, left:3.0, right:2.5}"},
                "output_path": {"type": "string", "description": "Ruta de salida (omitir = sobreescribe el original)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "pptx_create_from_template",
        "description": "Crea una presentación .pptx NUEVA desde una plantilla de empresa (.pptx/.potx), heredando el tema, masters y layouts. USAR cuando el usuario tiene plantillas corporativas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_path": {"type": "string", "description": "Ruta a la plantilla .pptx o .potx de la empresa"},
                "output_path":   {"type": "string", "description": "Ruta del fichero de salida .pptx"},
                "title":         {"type": "string", "description": "Título de la presentación (diapositiva de portada)"},
                "subtitle":      {"type": "string", "description": "Subtítulo de la portada"},
                "slides":        {"type": "array",  "description": "Lista de diapositivas: [{title, content, layout_name, notes, image_path}]. layout_name debe coincidir con los layouts de la plantilla"},
            },
            "required": ["template_path", "output_path"],
        },
    },
    # ── Tools de diagramas e imágenes ────────────────────────────────────────
    {
        "name": "doc_embed_image",
        "description": "Inserta una imagen (PNG/JPG) en un documento .docx existente, con pie de figura opcional.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":         {"type": "string", "description": "Ruta al fichero .docx"},
                "image_path":   {"type": "string", "description": "Ruta a la imagen (PNG/JPG/EMF)"},
                "caption":      {"type": "string", "description": "Texto del pie de figura (opcional)"},
                "width_inches": {"type": "number", "description": "Ancho de la imagen en pulgadas. Default: 5.0"},
                "output_path":  {"type": "string", "description": "Ruta de salida (omitir = sobreescribe el original)"},
            },
            "required": ["path", "image_path"],
        },
    },
    {
        "name": "insert_chart",
        "description": "Inserta una gráfica matplotlib (bar, pie, line, scatter) como imagen PNG en un documento .docx.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":          {"type": "string", "description": "Ruta al fichero .docx"},
                "chart_type":    {"type": "string", "description": "Tipo: bar, pie, line, scatter"},
                "data":          {"type": "object", "description": "Datos: {categories:[...], values:[...]} para bar/line; {labels:[...], sizes:[...]} para pie"},
                "title":         {"type": "string", "description": "Título de la gráfica"},
                "width_inches":  {"type": "number", "description": "Ancho en pulgadas (default: 6)"},
                "output_path":   {"type": "string", "description": "Ruta de salida (omitir = sobreescribe el original)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "doc_insert_chart_native",
        "description": "★ Inserta gráfica OOXML nativa en .docx (editable en Word/LibreOffice). Tipos: bar|column|stacked_bar|stacked_column|line|line_markers|area|pie|doughnut|scatter|radar|bubble.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":          {"type": "string", "description": "Ruta al fichero .docx existente"},
                "chart_type":    {"type": "string", "description": "Tipo: bar | line | pie | doughnut | area | scatter"},
                "data":          {"type": "object", "description": "Datos: {categories:[...], series:[{label, values},...]} o {values:[...], labels:[...]} para pie"},
                "title":         {"type": "string", "description": "Título de la gráfica"},
                "style":         {"type": "string", "description": "Estilo: office | dark | minimal | presentation"},
                "width_inches":  {"type": "number", "description": "Ancho en pulgadas (default: 5.5)"},
                "height_inches": {"type": "number", "description": "Alto en pulgadas (default: 3.5)"},
                "output_path":   {"type": "string", "description": "Ruta de salida (omitir = sobreescribe el original)"},
            },
            "required": ["path", "chart_type", "data"],
        },
    },
    {
        "name": "doc_insert_diagram",
        "description": "Inserta diagramas y gráficas en documentos .docx: flowchart, bar_chart, pie_chart, line_chart, table, org_chart.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":          {"type": "string",  "description": "Ruta al fichero .docx existente"},
                "diagram_type":  {"type": "string",  "description": "Tipo: flowchart | bar_chart | pie_chart | line_chart | table | org_chart"},
                "content":       {"type": "string",  "description": "Datos del diagrama. bar/pie/line: 'Label1,Label2\\nVal1,Val2'. table: 'Col1|Col2\\nFil1a|Fil1b'. flowchart: 'Paso1\\nPaso2'"},
                "title":         {"type": "string",  "description": "Título (opcional)"},
                "style":         {"type": "string",  "description": "Estilo: office | dark | minimal | presentation"},
                "width_inches":  {"type": "number",  "description": "Ancho en pulgadas (default: 5.5)"},
                "output_path":   {"type": "string",  "description": "Ruta de salida (omitir = sobreescribe el original)"},
            },
            "required": ["path", "diagram_type"],
        },
    },
    {
        "name": "create_bar_chart",
        "description": "★ Crea gráfica de barras OOXML nativa en .docx (editable) si se da 'path'. Sin path, genera PNG. Soporta multi-series, barras apiladas, horizontales.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data":   {"type": "object", "description": "Datos: {categories:[...], values:[...]}"},
                "output": {"type": "string", "description": "Ruta de salida PNG (default: /tmp/chart_bar.png)"},
                "title":  {"type": "string", "description": "Título de la gráfica"},
            },
        },
    },
    {
        "name": "create_pie_chart",
        "description": "★ Crea gráfica circular OOXML nativa en .docx (editable) si se da 'path'. Sin path, genera PNG. Soporta doughnut.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data":   {"type": "object", "description": "Datos: {labels:[...], sizes:[...]}"},
                "output": {"type": "string", "description": "Ruta de salida PNG (default: /tmp/chart_pie.png)"},
                "title":  {"type": "string", "description": "Título de la gráfica"},
            },
        },
    },
    {
        "name": "create_line_chart",
        "description": "★ Crea gráfica de líneas OOXML nativa en .docx (editable) si se da 'path'. Sin path, genera PNG. Soporta área, marcadores, multi-series.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data":   {"type": "object", "description": "Datos: {x_labels:[...], y_values:[...]}"},
                "output": {"type": "string", "description": "Ruta de salida PNG (default: /tmp/chart_line.png)"},
                "title":  {"type": "string", "description": "Título de la gráfica"},
            },
        },
    },
    # ── Nuevas tools O365 nativas ──────────────────────────────────────────────
    {
        "name": "pptx_create",
        "description": "Crea una presentación PowerPoint (.pptx). Si se indica template_path, usa la plantilla de empresa (equivale a pptx_create_from_template). Si no, usa un tema de color.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":          {"type": "string", "description": "Ruta del fichero .pptx a crear"},
                "title":         {"type": "string", "description": "Título de la presentación"},
                "subtitle":      {"type": "string", "description": "Subtítulo (opcional)"},
                "theme":         {"type": "string", "description": "Tema visual: default, dark, light, corporate (solo sin template_path)"},
                "template_path": {"type": "string", "description": "Plantilla .pptx/.potx de empresa (opcional; si se da, hereda tema y layouts)"},
                "slides":        {"type": "array",  "description": "Diapositivas: [{title, content, layout, layout_name, notes}]"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "pptx_add_slide",
        "description": "Añade una diapositiva a una presentación .pptx existente.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Ruta al fichero .pptx"},
                "title":   {"type": "string", "description": "Título de la diapositiva"},
                "content": {"type": "string", "description": "Contenido (bullet points, uno por línea). Prefija con 2 espacios para nivel 2."},
                "layout":  {"type": "string", "description": "Diseño: bullet (predeterminado), blank, two_col, title_only"},
                "notes":   {"type": "string", "description": "Notas del presentador (opcional)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "pptx_read",
        "description": "Lee el contenido de texto de una presentación .pptx, diapositiva por diapositiva.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":   {"type": "string", "description": "Ruta al fichero .pptx"},
                "slides": {"type": "string", "description": "Rango de diapositivas, p.ej. '1-5' o '3'. Omitir = todas."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "pptx_insert_chart",
        "description": (
            "Inserta una gráfica NATIVA de python-pptx en una diapositiva existente. "
            "Las gráficas son vectoriales y editables en PowerPoint/LibreOffice. "
            "Usa CategoryChartData para tipos de barra/columna/línea/tarta. "
            "Tipos: column_clustered, column_stacked, bar_clustered, bar_stacked, "
            "line, line_markers, pie, doughnut, area, scatter, radar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string",  "description": "Ruta al fichero .pptx"},
                "chart_type":  {"type": "string",  "description": "Tipo de gráfica: column_clustered, bar_clustered, line, pie, doughnut, area, scatter, radar"},
                "categories":  {"type": "array",   "description": "Categorías del eje X: ['Ene', 'Feb', 'Mar']"},
                "series":      {"type": "array",   "description": "Series: [{label: 'Ventas', values: [10,20,30]}, ...]"},
                "title":       {"type": "string",  "description": "Título de la gráfica"},
                "slide_index": {"type": "integer", "description": "Índice de diapositiva (0-based, -1=última)"},
                "left":        {"type": "number",  "description": "Posición izquierda en pulgadas (default: 1.0)"},
                "top":         {"type": "number",  "description": "Posición superior en pulgadas (default: 2.0)"},
                "width":       {"type": "number",  "description": "Ancho en pulgadas (default: 8.0)"},
                "height":      {"type": "number",  "description": "Alto en pulgadas (default: 4.5)"},
                "output_path": {"type": "string",  "description": "Ruta de salida (omitir = sobreescribe el original)"},
            },
            "required": ["path", "categories", "series"],
        },
    },
    {
        "name": "doc_apply_style",
        "description": "Aplica estilos de párrafo O365 a un .docx (Heading 1, Heading 2, Normal, Title, Quote, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string", "description": "Ruta al fichero .docx"},
                "style_map":   {"type": "array",  "description": "Reglas: [{search: 'texto', style: 'Heading 1'} | {paragraph: 0, style: 'Title'}]"},
                "output_path": {"type": "string", "description": "Ruta de salida (omitir = sobreescribe el original)"},
            },
            "required": ["path", "style_map"],
        },
    },
    {
        "name": "doc_set_table_style",
        "description": "Aplica un estilo de tabla O365 a todas o una tabla específica de un .docx.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":         {"type": "string",  "description": "Ruta al fichero .docx"},
                "style":        {"type": "string",  "description": "Nombre del estilo: 'Table Grid', 'Light Shading', 'Medium Shading 1', 'Dark List', etc."},
                "table_index":  {"type": "integer", "description": "Índice de la tabla (0-based); -1 = todas (default: -1)"},
                "output_path":  {"type": "string",  "description": "Ruta de salida (omitir = sobreescribe el original)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "xlsx_insert_chart",
        "description": "Inserta una gráfica nativa de openpyxl en una hoja Excel. No requiere matplotlib.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":       {"type": "string",  "description": "Ruta al fichero .xlsx"},
                "chart_type": {"type": "string",  "description": "Tipo: bar, line, pie, area, scatter"},
                "sheet":      {"type": "string",  "description": "Nombre de la hoja (por defecto: la activa)"},
                "data_range": {"type": "string",  "description": "Rango de datos, p.ej. 'A1:C6'. Primera fila = cabeceras, primera columna = categorías."},
                "title":      {"type": "string",  "description": "Título de la gráfica"},
                "position":   {"type": "string",  "description": "Celda donde anclar la gráfica (default: E2)"},
                "width":      {"type": "number",  "description": "Ancho de la gráfica en cm (default: 15)"},
                "height":     {"type": "number",  "description": "Alto de la gráfica en cm (default: 10)"},
            },
            "required": ["path", "data_range"],
        },
    },
    {
        "name": "xlsx_apply_conditional_format",
        "description": "Aplica formato condicional (escala de color, barra de datos, iconos, regla de celda) a un rango Excel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":       {"type": "string", "description": "Ruta al fichero .xlsx"},
                "sheet":      {"type": "string", "description": "Nombre de la hoja (por defecto: la activa)"},
                "range":      {"type": "string", "description": "Rango, p.ej. 'B2:B20'"},
                "rule_type":  {"type": "string", "description": "Tipo: color_scale, data_bar, icon_set, cell_is"},
                "options":    {"type": "object", "description": "Para color_scale: {min, mid, max} en hex. Para cell_is: {operator, formula, fill}. Para icon_set: {icon_style}."},
            },
            "required": ["path", "range"],
        },
    },
    {
        "name": "doc_extract_metadata",
        "description": "Extrae metadatos de un .docx, .pptx o .pdf: autor, título, fechas de creación/modificación, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta al fichero (.docx, .pptx, .pdf)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "doc_compare",
        "description": "Compara el texto de dos documentos (.docx, .pptx o .md) y devuelve un diff unificado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path_a":  {"type": "string",  "description": "Ruta al primer documento"},
                "path_b":  {"type": "string",  "description": "Ruta al segundo documento"},
                "context": {"type": "integer", "description": "Líneas de contexto en el diff (default: 3)"},
            },
            "required": ["path_a", "path_b"],
        },
    },
    # ── Nuevas tools matplotlib avanzadas ─────────────────────────────────────
    {
        "name": "create_scatter_chart",
        "description": "★ Crea scatter plot OOXML nativo en .docx si se da 'path', o PNG como respaldo. Soporta multi-serie y línea de tendencia.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output":       {"type": "string",  "description": "Ruta de salida PNG (default: /tmp/scatter.png)"},
                "title":        {"type": "string",  "description": "Título del gráfico"},
                "x_label":      {"type": "string",  "description": "Etiqueta eje X"},
                "y_label":      {"type": "string",  "description": "Etiqueta eje Y"},
                "trend_line":   {"type": "boolean", "description": "Añadir línea de tendencia (regresión lineal)"},
                "style":        {"type": "string",  "description": "Estilo visual: office|dark|minimal|presentation"},
                "data": {
                    "type": "object",
                    "description": "Datos: {x_values:[...], y_values:[...]} o {series:[{label, x_values, y_values}]}",
                },
            },
            "required": ["data"],
        },
    },
    {
        "name": "create_stacked_bar_chart",
        "description": "★ Crea gráfica de barras apiladas OOXML nativa en .docx si se da 'path', o PNG. Requiere data.series=[{label, values}].",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output":      {"type": "string", "description": "Ruta PNG de salida"},
                "title":       {"type": "string", "description": "Título del gráfico"},
                "x_label":     {"type": "string", "description": "Etiqueta eje X"},
                "y_label":     {"type": "string", "description": "Etiqueta eje Y"},
                "horizontal":  {"type": "boolean","description": "Barras horizontales"},
                "style":       {"type": "string", "description": "Estilo: office|dark|minimal|presentation"},
                "data": {
                    "type": "object",
                    "description": "{categories:[...], series:[{label, values}]}",
                },
            },
            "required": ["data"],
        },
    },
    {
        "name": "create_gantt_chart",
        "description": "★ Genera diagrama de Gantt nativo en Word (tabla O365 editable). path/output: .docx destino. Soporta categorías por color y fechas YYYY-MM-DD.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output":  {"type": "string", "description": "Ruta PNG de salida"},
                "title":   {"type": "string", "description": "Título del diagrama"},
                "style":   {"type": "string", "description": "Estilo: office|dark|minimal|presentation"},
                "width":   {"type": "number", "description": "Ancho de la figura (default: 12)"},
                "tasks": {
                    "type": "array",
                    "description": "Lista de tareas: [{name, start:'YYYY-MM-DD', end:'YYYY-MM-DD', category?}]",
                    "items": {"type": "object"},
                },
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "create_org_chart",
        "description": "★ Genera organigrama jerárquico nativo en Word (tabla O365 editable). path/output: .docx destino. Nodos y relaciones padre-hijo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output":  {"type": "string", "description": "Ruta PNG de salida"},
                "title":   {"type": "string", "description": "Título del organigrama"},
                "style":   {"type": "string", "description": "Estilo: office|dark|minimal|presentation"},
                "nodes": {
                    "type": "array",
                    "description": "Lista de nodos: [{id, label, parent?}] donde parent es el id del nodo padre",
                    "items": {"type": "object"},
                },
            },
            "required": ["nodes"],
        },
    },
    {
        "name": "create_heatmap",
        "description": "★ Genera heatmap (mapa de calor) nativo en Word (tabla O365 con celdas coloreadas). path/output: .docx destino.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output":       {"type": "string",  "description": "Ruta PNG de salida"},
                "title":        {"type": "string",  "description": "Título del heatmap"},
                "colormap":     {"type": "string",  "description": "Paleta: Blues|Reds|RdYlGn|YlOrRd|coolwarm|viridis"},
                "show_values":  {"type": "boolean", "description": "Mostrar valores en cada celda"},
                "value_format": {"type": "string",  "description": "Formato de valor: .0f|.1f|.2f|d"},
                "style":        {"type": "string",  "description": "Estilo: office|dark|minimal"},
                "data":         {"type": "array",   "description": "Matriz 2D de valores [[fila1], [fila2], ...]"},
                "row_labels":   {"type": "array",   "description": "Etiquetas de filas"},
                "col_labels":   {"type": "array",   "description": "Etiquetas de columnas"},
            },
            "required": ["data"],
        },
    },
    {
        "name": "create_radar_chart",
        "description": "★ Inserta gráfico radar/spider OOXML nativo en .docx (editable, sin matplotlib). Requiere 'path' al .docx.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output":     {"type": "string",  "description": "Ruta PNG de salida"},
                "title":      {"type": "string",  "description": "Título del gráfico"},
                "fill":       {"type": "boolean", "description": "Rellenar áreas (default: true)"},
                "style":      {"type": "string",  "description": "Estilo: office|dark|minimal|presentation"},
                "categories": {"type": "array",   "description": "Categorías del radar (ejes)"},
                "series": {
                    "type": "array",
                    "description": "Series: [{label, values:[...]}] — los values deben estar en el mismo rango numérico",
                    "items": {"type": "object"},
                },
            },
            "required": ["categories", "series"],
        },
    },
    # ── Nuevas tools Excel avanzadas ──────────────────────────────────────────
    {
        "name": "apply_cell_formatting",
        "description": "Aplica formato rico a un rango de celdas Excel: fuente, relleno, borde, alineación, formato numérico.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":          {"type": "string", "description": "Ruta al .xlsx"},
                "sheet":         {"type": "string", "description": "Nombre de la hoja (default: activa)"},
                "range":         {"type": "string", "description": "Rango de celdas: A1, A1:C5, etc."},
                "number_format": {"type": "string", "description": "Formato numérico: #,##0.00 | 0.0% | mmm-dd-yy | @"},
                "font": {
                    "type": "object",
                    "description": "{name, size, bold, italic, color:'FF000000', underline, strike}",
                },
                "fill": {
                    "type": "object",
                    "description": "{color:'FFFF0000', type:'solid'}",
                },
                "border": {
                    "type": "object",
                    "description": "{style:'thin'} o {left:{style,color}, right:{..}, top:{..}, bottom:{..}}",
                },
                "alignment": {
                    "type": "object",
                    "description": "{horizontal:'center'|'left'|'right', vertical:'center', wrap_text:true, rotation:45}",
                },
            },
            "required": ["path", "range"],
        },
    },
    {
        "name": "xlsx_freeze_panes",
        "description": "Congela filas/columnas en una hoja Excel. Ej: cell='B2' congela fila 1 y columna A.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Ruta al .xlsx"},
                "sheet": {"type": "string", "description": "Nombre de la hoja (default: activa)"},
                "cell":  {"type": "string", "description": "Celda de congelación: 'B2', 'A2', 'C1', 'none' para eliminar"},
            },
            "required": ["path", "cell"],
        },
    },
    {
        "name": "xlsx_set_column_width",
        "description": "Establece el ancho de columnas en Excel. Soporta auto-ajuste o anchos manuales.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string",  "description": "Ruta al .xlsx"},
                "sheet":   {"type": "string",  "description": "Nombre de la hoja (default: activa)"},
                "auto":    {"type": "boolean", "description": "Auto-ajustar todos los anchos al contenido"},
                "columns": {"type": "object",  "description": "Anchos manuales: {'A': 20, 'B': 15, 'C': 25}"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "xlsx_merge_cells",
        "description": "Fusiona o separa un rango de celdas en Excel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string",  "description": "Ruta al .xlsx"},
                "sheet": {"type": "string",  "description": "Nombre de la hoja (default: activa)"},
                "range": {"type": "string",  "description": "Rango a fusionar: 'A1:C1', 'B2:D4'"},
                "merge": {"type": "boolean", "description": "true=fusionar, false=separar (default: true)"},
            },
            "required": ["path", "range"],
        },
    },
    {
        "name": "xlsx_add_sheet",
        "description": "Añade, renombra, elimina o lista hojas en un fichero Excel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":      {"type": "string",  "description": "Ruta al .xlsx"},
                "action":    {"type": "string",  "description": "Acción: add|rename|delete|list"},
                "name":      {"type": "string",  "description": "Nombre de la hoja a operar"},
                "new_name":  {"type": "string",  "description": "Nuevo nombre (para rename)"},
                "position":  {"type": "integer", "description": "Posición de inserción (para add)"},
                "copy_from": {"type": "string",  "description": "Nombre de hoja origen (para copia)"},
            },
            "required": ["path", "action"],
        },
    },
    {
        "name": "xlsx_protect_sheet",
        "description": "Protege o desprotege una hoja Excel con contraseña opcional.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":     {"type": "string",  "description": "Ruta al .xlsx"},
                "sheet":    {"type": "string",  "description": "Nombre de la hoja (default: activa)"},
                "protect":  {"type": "boolean", "description": "true=proteger, false=desproteger (default: true)"},
                "password": {"type": "string",  "description": "Contraseña de protección (opcional)"},
                "options": {
                    "type": "object",
                    "description": "{allow_format_cells, allow_insert_rows, allow_delete_rows, allow_sort, allow_filter}",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "xlsx_add_data_validation",
        "description": "Añade validación de datos (lista desplegable, rango numérico) a un rango de celdas Excel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":          {"type": "string", "description": "Ruta al .xlsx"},
                "sheet":         {"type": "string", "description": "Nombre de la hoja (default: activa)"},
                "range":         {"type": "string", "description": "Rango: 'A1:A100'"},
                "type":          {"type": "string", "description": "Tipo: list|whole|decimal"},
                "items":         {"type": "array",  "description": "Opciones para dropdown: ['Sí','No','Pendiente']"},
                "formula":       {"type": "string", "description": "Fórmula alternativa o rango numérico 'min:max'"},
                "error_message": {"type": "string", "description": "Mensaje de error al introducir valor inválido"},
                "prompt":        {"type": "string", "description": "Mensaje de ayuda al seleccionar la celda"},
            },
            "required": ["path", "range", "type"],
        },
    },
    # ── Nuevas tools Word avanzadas ───────────────────────────────────────────
    {
        "name": "set_paragraph_format",
        "description": "Formatea un párrafo específico de un .docx: fuente, tamaño, color, negrita, alineación, espaciado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":            {"type": "string",  "description": "Ruta al .docx"},
                "paragraph_index": {"type": "integer", "description": "Índice del párrafo (0 = primero)"},
                "font_name":       {"type": "string",  "description": "Nombre de fuente: Calibri, Arial, Times New Roman"},
                "font_size":       {"type": "number",  "description": "Tamaño en puntos: 10, 11, 12, 14, 16, 18"},
                "color":           {"type": "string",  "description": "Color hexadecimal: '#2E74B5' o '#000000'"},
                "bold":            {"type": "boolean", "description": "Negrita"},
                "italic":          {"type": "boolean", "description": "Cursiva"},
                "underline":       {"type": "boolean", "description": "Subrayado"},
                "alignment":       {"type": "string",  "description": "Alineación: left|center|right|justify"},
                "space_before":    {"type": "number",  "description": "Espacio antes del párrafo en puntos"},
                "space_after":     {"type": "number",  "description": "Espacio después del párrafo en puntos"},
                "line_spacing":    {"type": "number",  "description": "Interlineado: 1.0, 1.15, 1.5, 2.0"},
                "style":           {"type": "string",  "description": "Estilo de párrafo: Normal, Heading 1, etc."},
            },
            "required": ["path", "paragraph_index"],
        },
    },
    {
        "name": "apply_document_theme",
        "description": "Aplica un tema de colores y fuentes (office/modern/professional/minimal/corporate) a todos los estilos de un .docx.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string", "description": "Ruta al .docx"},
                "theme":       {"type": "string", "description": "Tema: office|modern|professional|minimal|corporate"},
                "output_path": {"type": "string", "description": "Ruta de salida (default: sobreescribe el original)"},
            },
            "required": ["path", "theme"],
        },
    },
    {
        "name": "doc_add_header_footer",
        "description": "Añade cabecera y/o pie de página a un documento .docx, con número de página opcional.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string",  "description": "Ruta al .docx"},
                "header":      {"type": "string",  "description": "Texto de la cabecera"},
                "footer":      {"type": "string",  "description": "Texto del pie de página"},
                "page_number": {"type": "boolean", "description": "Incluir número de página en el pie"},
                "alignment":   {"type": "string",  "description": "Alineación: left|center|right"},
                "font_size":   {"type": "number",  "description": "Tamaño de fuente en puntos (default: 10)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "doc_add_toc",
        "description": "Inserta una Tabla de Contenidos (TOC) al inicio de un .docx basada en los estilos Heading.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":      {"type": "string",  "description": "Ruta al .docx"},
                "title":     {"type": "string",  "description": "Título de la TOC (default: 'Tabla de Contenidos')"},
                "max_level": {"type": "integer", "description": "Nivel máximo de headings a incluir (default: 3)"},
            },
            "required": ["path"],
        },
    },
    # ── Nuevas tools PPTX avanzadas ───────────────────────────────────────────
    {
        "name": "pptx_add_notes",
        "description": "Añade notas del presentador a una o varias diapositivas de un .pptx.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string",  "description": "Ruta al .pptx"},
                "slide_index": {"description":     "Índice de diapositiva (0=primera), lista de índices, o 'all'"},
                "notes":       {"type": "string",  "description": "Texto de las notas del presentador"},
                "append":      {"type": "boolean", "description": "Añadir al final en lugar de reemplazar (default: false)"},
            },
            "required": ["path", "notes"],
        },
    },
    {
        "name": "pptx_set_background",
        "description": "Establece el fondo de una o todas las diapositivas: sólido, gradiente o imagen.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":          {"type": "string", "description": "Ruta al .pptx"},
                "slide_index":   {"description":    "Índice (0=primera), lista, o 'all' para todas"},
                "type":          {"type": "string", "description": "Tipo de fondo: solid|gradient|image"},
                "color":         {"type": "string", "description": "Color sólido en hex: '#1F4E79'"},
                "gradient_from": {"type": "string", "description": "Color inicial del gradiente: '#1F4E79'"},
                "gradient_to":   {"type": "string", "description": "Color final del gradiente: '#FFFFFF'"},
                "image_path":    {"type": "string", "description": "Ruta a imagen PNG/JPG para fondo de imagen"},
            },
            "required": ["path", "type"],
        },
    },
]

_TOOL_FNS: dict[str, Any] = {
    "email_list":               _tool_email_list,
    "email_read":               _tool_email_read,
    "email_send":               _tool_email_send,
    "email_search":             _tool_email_search,
    "doc_convert":              _tool_doc_convert,
    "pdf_extract_text":         _tool_pdf_extract_text,
    "doc_word_count":           _tool_doc_word_count,
    "xlsx_read":                _tool_xlsx_read,
    "xlsx_write":               _tool_xlsx_write,
    "csv_analyze":              _tool_csv_analyze,
    "cal_list":                 _tool_cal_list,
    "cal_add":                  _tool_cal_add,
    "cal_search":               _tool_cal_search,
    "notes_list":               _tool_notes_list,
    "notes_search":             _tool_notes_search,
    "notes_save":               _tool_notes_save,
    "image_to_text":            _tool_image_to_text,
    "contact_search":           _tool_contact_search,
    "markdown_to_html":         _tool_markdown_to_html,
    "doc_read_template_fields": _tool_doc_read_template_fields,
    "doc_fill_template":            _tool_doc_fill_template,
    "doc_fill_corporate_template":  _tool_doc_fill_corporate_template,
    "doc_list_templates":       _tool_doc_list_templates,
    "doc_create_rfc":           _tool_doc_create_rfc,
    "xlsx_fill_range":          _tool_xlsx_fill_range,
    "xlsx_append_row":          _tool_xlsx_append_row,
    "xlsx_create_report":       _tool_xlsx_create_report,
    "project_context_read":     _tool_project_context_read,
    "project_init_office":      _tool_project_init_office,
    "doc_project_save":         _tool_doc_project_save,
    "doc_read":                 _tool_doc_read,
    "doc_update_section":       _tool_doc_update_section,
    "doc_version_bump":         _tool_doc_version_bump,
    "cmdb_search":              _tool_cmdb_search,
    "cmdb_update":              _tool_cmdb_update,
    "asset_register_add":       _tool_asset_register_add,
    "doc_embed_image":              _tool_doc_embed_image,
    "doc_create_from_template":    _tool_doc_create_from_template,
    "doc_add_content_block":       _tool_doc_add_content_block,
    "doc_set_page_layout":         _tool_doc_set_page_layout,
    "pptx_create_from_template":   _tool_pptx_create_from_template,
    "xlsx_create_table":           _tool_xlsx_create_table,
    "doc_insert_diagram":          _tool_doc_insert_diagram,
    "insert_chart":                _tool_insert_chart,
    "doc_insert_chart_native":     _tool_doc_insert_chart_native,
    "create_bar_chart":         _tool_create_bar_chart,
    "create_pie_chart":         _tool_create_pie_chart,
    "create_line_chart":        _tool_create_line_chart,
    # ── Nuevas tools O365 nativas ──────────────────────────────────────────
    "pptx_create":                    _tool_pptx_create,
    "pptx_add_slide":                 _tool_pptx_add_slide,
    "pptx_insert_chart":              _tool_pptx_insert_chart,
    "pptx_read":                      _tool_pptx_read,
    "doc_apply_style":                _tool_doc_apply_style,
    "doc_set_table_style":            _tool_doc_set_table_style,
    "xlsx_insert_chart":              _tool_xlsx_insert_chart,
    "xlsx_apply_conditional_format":  _tool_xlsx_apply_conditional_format,
    "doc_extract_metadata":           _tool_doc_extract_metadata,
    "doc_compare":                    _tool_doc_compare,
    # ── Matplotlib avanzado ────────────────────────────────────────────────
    "create_scatter_chart":           _tool_create_scatter_chart,
    "create_stacked_bar_chart":       _tool_create_stacked_bar_chart,
    "create_gantt_chart":             _tool_create_gantt_chart,
    "create_org_chart":               _tool_create_org_chart,
    "create_heatmap":                 _tool_create_heatmap,
    "create_radar_chart":             _tool_create_radar_chart,
    # ── Excel avanzado ─────────────────────────────────────────────────────
    "apply_cell_formatting":          _tool_apply_cell_formatting,
    "xlsx_freeze_panes":              _tool_xlsx_freeze_panes,
    "xlsx_set_column_width":          _tool_xlsx_set_column_width,
    "xlsx_merge_cells":               _tool_xlsx_merge_cells,
    "xlsx_add_sheet":                 _tool_xlsx_add_sheet,
    "xlsx_protect_sheet":             _tool_xlsx_protect_sheet,
    "xlsx_add_data_validation":       _tool_xlsx_add_data_validation,
    # ── Word avanzado ──────────────────────────────────────────────────────
    "set_paragraph_format":           _tool_set_paragraph_format,
    "apply_document_theme":           _tool_apply_document_theme,
    "doc_add_header_footer":          _tool_doc_add_header_footer,
    "doc_add_toc":                    _tool_doc_add_toc,
    # ── PPTX avanzado ──────────────────────────────────────────────────────
    "pptx_add_notes":                 _tool_pptx_add_notes,
    "pptx_set_background":            _tool_pptx_set_background,
    # ── Nueva tool principal ────────────────────────────────────────────────
    "doc_create":                     _tool_doc_create,
}


# ── Prompts ──────────────────────────────────────────────────────────────────

_PROMPTS: dict[str, dict] = {
    "draft_email": {
        "description": "Redacta un email profesional con tono y estructura configurables.",
        "arguments": [
            {"name": "to",       "description": "Destinatario",         "required": True},
            {"name": "subject",  "description": "Asunto",               "required": True},
            {"name": "context",  "description": "Contexto o propósito", "required": True},
            {"name": "tone",     "description": "formal/informal/amigable", "required": False},
            {"name": "language", "description": "Idioma (español por defecto)", "required": False},
        ],
    },
    "summarize_document": {
        "description": "Resume un documento con puntos clave, decisiones y acciones requeridas.",
        "arguments": [
            {"name": "content",   "description": "Texto del documento a resumir", "required": True},
            {"name": "max_words", "description": "Longitud máxima del resumen en palabras", "required": False},
            {"name": "focus",     "description": "Aspecto en el que enfocarse (p.ej. 'puntos de acción')", "required": False},
        ],
    },
    "meeting_notes": {
        "description": "Genera un acta de reunión estructurada con asistentes, puntos tratados y decisiones.",
        "arguments": [
            {"name": "attendees",  "description": "Lista de asistentes",          "required": True},
            {"name": "agenda",     "description": "Puntos de la agenda",           "required": True},
            {"name": "notes",      "description": "Notas o puntos discutidos",     "required": False},
            {"name": "date",       "description": "Fecha de la reunión (YYYY-MM-DD)", "required": False},
        ],
    },
    "weekly_report": {
        "description": "Genera un informe semanal de actividades con resumen, logros y próximos pasos.",
        "arguments": [
            {"name": "completed",   "description": "Tareas completadas esta semana", "required": True},
            {"name": "in_progress", "description": "Tareas en progreso",             "required": False},
            {"name": "next_week",   "description": "Plan para la próxima semana",    "required": False},
            {"name": "blockers",    "description": "Bloqueos o problemas",           "required": False},
        ],
    },
    # ── IT / Datacenter prompts ──────────────────────────────────────────────
    "datacenter_migration_report": {
        "description": "Genera un informe técnico formal de migración de centro de datos con fases, inventario y resultados.",
        "arguments": [
            {"name": "project_name", "description": "Nombre del proyecto de migración",          "required": True},
            {"name": "source_dc",    "description": "Centro de datos o entorno origen",          "required": True},
            {"name": "target_dc",    "description": "Centro de datos o entorno destino",         "required": True},
            {"name": "systems",      "description": "Lista de sistemas/servidores migrados",     "required": True},
            {"name": "date",         "description": "Fecha de la migración (YYYY-MM-DD)",        "required": False},
            {"name": "team",         "description": "Equipo o responsables",                     "required": False},
            {"name": "issues",       "description": "Incidencias ocurridas durante la migración","required": False},
            {"name": "result",       "description": "Resultado: exitoso / parcial / fallido",    "required": False},
        ],
    },
    "rfc_change_request": {
        "description": "Genera un RFC/Change Request completo y formal para cambios de infraestructura IT.",
        "arguments": [
            {"name": "title",            "description": "Título del cambio",                     "required": True},
            {"name": "requester",        "description": "Nombre del solicitante",                "required": True},
            {"name": "description",      "description": "Descripción detallada del cambio",      "required": True},
            {"name": "affected_systems", "description": "Sistemas o servicios afectados",        "required": True},
            {"name": "risk_level",       "description": "Nivel de riesgo: Alto/Medio/Bajo",      "required": False},
            {"name": "rollback_plan",    "description": "Plan de marcha atrás",                  "required": False},
            {"name": "scheduled_date",   "description": "Fecha y ventana de mantenimiento",      "required": False},
        ],
    },
    "server_migration_plan": {
        "description": "Genera un plan detallado de migración de servidor con checklist, validaciones y rollback.",
        "arguments": [
            {"name": "server_name",     "description": "Nombre o hostname del servidor",         "required": True},
            {"name": "source_env",      "description": "Entorno/infraestructura origen",         "required": True},
            {"name": "target_env",      "description": "Entorno/infraestructura destino",        "required": True},
            {"name": "services",        "description": "Servicios o aplicaciones en el servidor","required": False},
            {"name": "downtime_window", "description": "Ventana de mantenimiento",               "required": False},
            {"name": "dependencies",    "description": "Dependencias del servidor",              "required": False},
        ],
    },
    "it_incident_report": {
        "description": "Genera un informe post-incidencia IT (Post-Mortem) con RCA, timeline y plan de acción preventivo.",
        "arguments": [
            {"name": "title",         "description": "Título de la incidencia",                  "required": True},
            {"name": "severity",      "description": "Severidad: Crítica/Alta/Media/Baja",       "required": True},
            {"name": "start_time",    "description": "Fecha/hora de inicio del incidente",       "required": True},
            {"name": "end_time",      "description": "Fecha/hora de resolución",                 "required": False},
            {"name": "affected",      "description": "Sistemas y usuarios afectados",            "required": False},
            {"name": "root_cause",    "description": "Causa raíz identificada",                  "required": False},
            {"name": "timeline",      "description": "Cronología de eventos clave",              "required": False},
            {"name": "actions_taken", "description": "Acciones tomadas para resolverlo",         "required": False},
            {"name": "preventive",    "description": "Medidas preventivas propuestas",           "required": False},
        ],
    },
    "infrastructure_change_plan": {
        "description": "Genera un plan de cambio de infraestructura con análisis de impacto, fases, riesgos y aprobaciones.",
        "arguments": [
            {"name": "project",   "description": "Nombre del proyecto/cambio",                   "required": True},
            {"name": "requester", "description": "Responsable del proyecto",                     "required": True},
            {"name": "objective", "description": "Objetivo del cambio",                          "required": True},
            {"name": "scope",     "description": "Alcance: sistemas y servicios incluidos",      "required": False},
            {"name": "phases",    "description": "Fases del proyecto",                           "required": False},
            {"name": "risks",     "description": "Riesgos identificados",                        "required": False},
            {"name": "timeline",  "description": "Cronograma estimado",                          "required": False},
            {"name": "approvers", "description": "Lista de aprobadores requeridos",              "required": False},
        ],
    },
    # ── Bloque 4: Gestión IT / Negocio ───────────────────────────────────────
    "executive_summary": {
        "description": "Genera un resumen ejecutivo de un proyecto o situación IT para presentar a dirección.",
        "arguments": [
            {"name": "project",    "description": "Nombre del proyecto o situación",             "required": True},
            {"name": "context",    "description": "Contexto o descripción del contenido",        "required": True},
            {"name": "audience",   "description": "Audiencia objetivo (CIO, CEO, comité…)",      "required": False},
            {"name": "max_pages",  "description": "Extensión máxima en páginas. Default: 1",     "required": False},
        ],
    },
    "business_case": {
        "description": "Genera un business case IT con análisis coste-beneficio, ROI y justificación de inversión.",
        "arguments": [
            {"name": "project",     "description": "Nombre del proyecto/inversión",              "required": True},
            {"name": "requester",   "description": "Responsable o departamento solicitante",     "required": True},
            {"name": "description", "description": "Descripción de la inversión propuesta",      "required": True},
            {"name": "cost",        "description": "Coste estimado (CAPEX/OPEX)",                "required": False},
            {"name": "benefits",    "description": "Beneficios esperados (cuantitativos/cualitativos)", "required": False},
            {"name": "alternatives","description": "Alternativas consideradas",                  "required": False},
            {"name": "timeline",    "description": "Plazo de amortización o retorno",            "required": False},
        ],
    },
    "project_status_report": {
        "description": "Genera un informe de estado de proyecto IT (RAG status) con hitos, riesgos y próximos pasos.",
        "arguments": [
            {"name": "project",     "description": "Nombre del proyecto",                        "required": True},
            {"name": "period",      "description": "Período del informe (p.ej. 'Mayo 2026')",    "required": True},
            {"name": "status",      "description": "Estado general: Verde/Ámbar/Rojo",           "required": True},
            {"name": "completed",   "description": "Hitos o tareas completadas en el período",   "required": False},
            {"name": "in_progress", "description": "Tareas en curso",                            "required": False},
            {"name": "risks",       "description": "Riesgos o problemas identificados",          "required": False},
            {"name": "next_steps",  "description": "Próximos hitos o acciones",                  "required": False},
            {"name": "budget",      "description": "Estado del presupuesto",                     "required": False},
        ],
    },
    "create_presentation": {
        "description": (
            "Crea una presentación PowerPoint (.pptx) nativa O365 con doc_create. "
            "Soporta diapositivas con bloques avanzados: gráficas nativas (chart), tablas, imágenes, texto. "
            "Produce un .pptx real con estilos Office, no una imagen ni un PDF."
        ),
        "arguments": [
            {"name": "topic",          "description": "Tema de la presentación",                          "required": True},
            {"name": "audience",       "description": "Audiencia: técnica/ejecutiva/mixta",               "required": False},
            {"name": "slides",         "description": "Número aproximado de diapositivas (default: 8)",   "required": False},
            {"name": "context",        "description": "Puntos clave, datos o contexto a incluir",         "required": False},
            {"name": "language",       "description": "Idioma (español por defecto)",                     "required": False},
            {"name": "template_path",  "description": "Ruta a plantilla .pptx/.potx corporativa",        "required": False},
            {"name": "output_path",    "description": "Ruta de salida para el .pptx",                    "required": False},
        ],
    },
    "data_visualization": {
        "description": (
            "Selecciona y genera la gráfica más adecuada para los datos y el objetivo. "
            "Soporta: bar, stacked_bar, stacked_column, 100_stacked_column, line, stacked_line, "
            "area, stacked_area, pie, doughnut, scatter — todas nativas O365 en docx/xlsx/pptx. "
            "También: heatmap, radar, gantt, org_chart (matplotlib PNG incrustado)."
        ),
        "arguments": [
            {"name": "data_description", "description": "Descripción de los datos disponibles (categorías, series, valores)", "required": True},
            {"name": "objective",        "description": "comparar | tendencia | distribución | correlación | jerarquía | proyecto", "required": True},
            {"name": "audience",         "description": "técnica | ejecutiva | general",                   "required": False},
            {"name": "format",           "description": "Formato de salida: docx | xlsx | pptx | png",    "required": False},
        ],
    },
    "create_dashboard": {
        "description": (
            "Crea un dashboard Excel (.xlsx) profesional con doc_create. "
            "Incluye hojas de datos y resumen, gráficas nativas O365 (bar/line/pie/doughnut/scatter/stacked), "
            "formatos condicionales (color_scale, data_bar, cell_is), columnas ajustadas y paneles congelados."
        ),
        "arguments": [
            {"name": "title",       "description": "Título del dashboard",                              "required": True},
            {"name": "kpis",        "description": "KPIs a mostrar: ventas, satisfacción, tasa, etc.",  "required": True},
            {"name": "data",        "description": "Datos en formato tabla (CSV, descripción o JSON)",  "required": True},
            {"name": "chart_types", "description": "Tipos de gráficas: bar, line, pie, scatter, doughnut, stacked_bar", "required": False},
            {"name": "period",      "description": "Período del dashboard (mes, trimestre, año)",       "required": False},
            {"name": "output_path", "description": "Ruta de salida para el .xlsx",                     "required": False},
        ],
    },
    "create_technical_doc": {
        "description": (
            "Crea un documento Word (.docx) técnico profesional con estilos O365 nativos usando doc_create. "
            "Incluye TOC automático, cabecera/pie de página, tabla de versiones, headings jerárquicos, "
            "tablas con estilos Office, checklists, callouts, bloques de código y firma digital."
        ),
        "arguments": [
            {"name": "title",         "description": "Título del documento",                                      "required": True},
            {"name": "sections",      "description": "Secciones a incluir (comma-separated)",                     "required": True},
            {"name": "doc_type",      "description": "Tipo: especificacion | procedimiento | informe | manual | arquitectura", "required": False},
            {"name": "author",        "description": "Autor del documento",                                       "required": False},
            {"name": "version",       "description": "Versión del documento (default: 1.0)",                      "required": False},
            {"name": "language",      "description": "Idioma (español por defecto)",                              "required": False},
            {"name": "template_path", "description": "Ruta a plantilla .docx/.dotx corporativa",                 "required": False},
            {"name": "output_path",   "description": "Ruta de salida para el .docx",                             "required": False},
        ],
    },
    "generate_report_with_charts": {
        "description": (
            "Genera un informe Word (.docx) con gráficas nativas O365 incrustadas usando doc_create. "
            "Las gráficas se insertan como objetos DrawingML nativos (editables en Word), no como imágenes PNG. "
            "Soporta bar, line, pie, doughnut, scatter, stacked_bar, area y todos los tipos O365."
        ),
        "arguments": [
            {"name": "title",        "description": "Título del informe",                                          "required": True},
            {"name": "data",         "description": "Datos a visualizar (tabla CSV, descripción o JSON)",          "required": True},
            {"name": "chart_types",  "description": "bar | line | pie | doughnut | scatter | stacked_bar | area",  "required": False},
            {"name": "period",       "description": "Período analizado (mes, trimestre, año)",                     "required": False},
            {"name": "conclusions",  "description": "Conclusiones o puntos clave a destacar",                     "required": False},
            {"name": "output_path",  "description": "Ruta de salida para el .docx",                               "required": False},
        ],
    },
    # ── Guías de uso de doc_create ────────────────────────────────────────────
    "create_word_document": {
        "description": (
            "Guía completa para crear cualquier documento Word (.docx) con doc_create y content_blocks O365. "
            "Muestra el uso correcto de todos los tipos de bloque: title, heading, paragraph, bullet_list, "
            "numbered_list, table (con merge_cells y estilos), chart (nativo DrawingML), checklist, callout, "
            "highlight, code_block, markdown, toc, signature_block, pagebreak, horizontal_rule."
        ),
        "arguments": [
            {"name": "title",       "description": "Título del documento a crear",                        "required": True},
            {"name": "purpose",     "description": "Propósito: informe | manual | RFC | acta | propuesta", "required": False},
            {"name": "blocks",      "description": "Lista de tipos de bloque a incluir (comma-separated)", "required": False},
            {"name": "output_path", "description": "Ruta de salida para el .docx",                       "required": False},
        ],
    },
    "create_excel_report": {
        "description": (
            "Guía completa para crear un informe Excel (.xlsx) con doc_create. "
            "Muestra el uso correcto de hojas con datos, todos los tipos de gráfica nativa O365, "
            "formatos condicionales (color_scale, data_bar, cell_is), freeze_panes, column widths, "
            "protección de hojas y validación de datos."
        ),
        "arguments": [
            {"name": "title",       "description": "Título del informe Excel",                    "required": True},
            {"name": "sheets",      "description": "Nombres de las hojas a crear (comma-separated)", "required": False},
            {"name": "chart_types", "description": "Tipos de gráficas a incluir",                "required": False},
            {"name": "output_path", "description": "Ruta de salida para el .xlsx",               "required": False},
        ],
    },
}


def _get_prompt(name: str, args: dict) -> list[dict]:  # noqa: C901
    _tpl = args.get("template_path", "")
    _tpl_hint = (
        f"\n\nPLANTILLA DE EMPRESA: {_tpl}\n"
        "→ USA doc_create_from_template o pptx_create_from_template con esta ruta para heredar estilos corporativos."
        if _tpl else
        "\n\nNOTA: Si el usuario tiene plantillas .docx/.dotx o .pptx/.potx de empresa, usa doc_create_from_template "
        "o pptx_create_from_template en lugar de crear desde cero para respetar el formato corporativo."
    )

    if name == "draft_email":
        to      = args.get("to", "")
        subject = args.get("subject", "")
        context = args.get("context", "")
        tone    = args.get("tone", "profesional")
        lang    = args.get("language", "español")
        prompt  = (
            f"Redacta un email profesional en {lang} con tono {tone}.\n\n"
            f"Para: {to}\nAsunto: {subject}\nContexto: {context}\n\n"
            "Estructura:\n"
            "- Saludo apropiado al destinatario y tono\n"
            "- Párrafo de apertura con el propósito\n"
            "- Cuerpo con los puntos clave (usa listas si hay varios puntos)\n"
            "- Llamada a la acción clara si corresponde\n"
            "- Cierre y despedida profesional\n\n"
            "Después del borrador, usa email_send para enviarlo si el usuario lo confirma.\n"
            "Devuelve solo el cuerpo del email listo para copiar o enviar."
        )
    elif name == "summarize_document":
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
    elif name == "meeting_notes":
        attendees = args.get("attendees", "")
        agenda    = args.get("agenda", "")
        notes     = args.get("notes", "")
        date      = args.get("date", datetime.date.today().isoformat())
        out_path  = args.get("output_path", "")
        prompt = (
            f"Genera un acta de reunión formal para la fecha {date} y guárdala como documento .docx.\n\n"
            f"ASISTENTES:\n{attendees}\n\n"
            f"AGENDA:\n{agenda}\n\n"
            f"NOTAS / PUNTOS DISCUTIDOS:\n{notes or 'No proporcionadas'}\n\n"
            "INSTRUCCIONES DE TOOL CALLS — sigue esta secuencia exacta:\n\n"
            "1. Llama a doc_create_from_template (o doc_create_rfc si no hay plantilla) con content_blocks:\n"
            "   - {type: heading, level: 1, text: 'Acta de Reunión — " + date + "'}\n"
            "   - {type: table, headers: ['Campo','Valor'], rows: [['Fecha','" + date + "'],['Asistentes','...'],['Lugar/Canal','...']]}\n"
            "   - {type: heading, level: 2, text: 'Puntos tratados'}\n"
            "   - {type: numbered_list, items: [cada punto de la agenda con decisiones]}\n"
            "   - {type: heading, level: 2, text: 'Decisiones tomadas'}\n"
            "   - {type: table, headers: ['Decisión','Responsable','Fecha límite'], rows: [...]}\n"
            "   - {type: heading, level: 2, text: 'Próximos pasos'}\n"
            "   - {type: table, headers: ['Acción','Responsable','Fecha límite','Estado'], rows: [...]}\n"
            + (f"   output_path: '{out_path}'\n" if out_path else "   output_path: 'acta_" + date + ".docx'\n")
            + f"\n2. Si hay plantilla de empresa, usa template_path.\n"
            + _tpl_hint
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
    elif name == "create_presentation":
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
            "| `scatter` | Correlación entre dos variables continuas |\n\n"
            "### Diagramas matplotlib (PNG incrustado):\n"
            "| Tool | Cuándo usar |\n"
            "|------|-------------|\n"
            "| `create_heatmap` | Matrices de correlación o KPIs 2D |\n"
            "| `create_radar_chart` | Comparar perfiles multidimensionales (≤8 ejes) |\n"
            "| `create_gantt_chart` | Planificación temporal de tareas |\n"
            "| `create_org_chart` | Jerarquías organizativas |\n"
            "| `create_scatter_chart` | Scatter con múltiples series o burbujas |\n"
            "| `create_stacked_bar_chart` | Stacked bars con matplotlib (más customizable) |\n\n"
            "## RECOMENDACIÓN:\n\n"
            "1. Selecciona el tipo más adecuado para los datos y el objetivo (justifica)\n"
            "2. Si hay varias opciones, ordénalas por efectividad para la audiencia\n"
            "3. Proporciona el JSON exacto de parámetros para la tool elegida:\n"
            "   - Para doc_create (.docx): el bloque `{\"type\": \"chart\", ...}` dentro de content_blocks\n"
            "   - Para doc_create (.xlsx): la entrada `{\"type\": \"bar\", ...}` dentro de `charts` de una hoja\n"
            "   - Para doc_create (.pptx): el bloque `{\"type\": \"chart\", ...}` dentro de `blocks` de un slide\n"
            "   - Para matplotlib: los args exactos de la tool correspondiente\n\n"
            f"Formato de salida objetivo: **{fmt}**"
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

    elif name == "create_excel_report":
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

    else:
        prompt = f"Prompt {name} no disponible."
    return [{"role": "user", "content": {"type": "text", "text": prompt}}]


# ── Resources ────────────────────────────────────────────────────────────────

_RESOURCES = [
    {
        "uri":         "office://emails_recent",
        "name":        "Emails recientes",
        "description": "Últimos 10 emails de la bandeja de entrada",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "office://calendar_today",
        "name":        "Calendario",
        "description": "Eventos de hoy y los próximos 7 días",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "office://notes_recent",
        "name":        "Notas recientes",
        "description": "Notas markdown más recientes (últimas 10)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "office://templates_available",
        "name":        "Plantillas disponibles",
        "description": "Lista de plantillas de documentos disponibles (.docx, .xlsx, .md)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "office://rfc_pending",
        "name":        "RFCs pendientes",
        "description": "Lista de documentos RFC/Change Request en el directorio de notas",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "office://tasks_today",
        "name":        "Tareas de hoy",
        "description": "Tareas pendientes de la jornada (desde el plugin todo de OOCode)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "office://project_context",
        "name":        "Contexto del proyecto",
        "description": "Metadata del proyecto activo: nombre, cliente, tipo, directorios, naming convention (desde OOCODE.md del cwd)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "office://server_inventory",
        "name":        "Inventario de servidores",
        "description": "Listado completo de activos de la CMDB del proyecto (auto-detectada en cwd y ~/Documents/)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "office://style_gallery",
        "name":        "Galería de estilos O365",
        "description": "Lista de estilos de párrafo y tabla disponibles para documentos .docx y presentaciones .pptx",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "office://style_presets",
        "name":        "Presets de estilos O365",
        "description": "Configuraciones de estilo predefinidas para títulos, subtítulos, cuerpo y tablas con valores concretos",
        "mimeType":    "application/json",
    },
    {
        "uri":         "office://theme_colors",
        "name":        "Paletas de colores de temas O365",
        "description": "Paletas de colores de los temas office/modern/professional/minimal/corporate con códigos hex",
        "mimeType":    "application/json",
    },
    {
        "uri":         "office://font_combinations",
        "name":        "Combinaciones de fuentes recomendadas",
        "description": "Combinaciones de fuentes compatibles con O365 y LibreOffice: heading + body + mono",
        "mimeType":    "application/json",
    },
    {
        "uri":         "office://chart_types",
        "name":        "Tipos de gráficas disponibles",
        "description": "Referencia completa de tipos de gráficas con sus tools y parámetros clave",
        "mimeType":    "application/json",
    },
    {
        "uri":         "office://diagram_templates",
        "name":        "Plantillas de diagramas",
        "description": "Plantillas y ejemplos JSON para flowchart, Gantt, organigrama, heatmap y radar",
        "mimeType":    "application/json",
    },
    {
        "uri":         "office://flowchart_shapes",
        "name":        "Referencia de formas para diagramas de flujo",
        "description": "Lista de formas estándar BPMN/UML para diagramas de flujo con descripción y uso",
        "mimeType":    "application/json",
    },
]


def _resource_emails_recent() -> str:
    return _tool_email_list({"limit": 10})


def _resource_calendar_today() -> str:
    cfg   = _load_config()
    today = datetime.date.today().isoformat()
    end   = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    return _tool_cal_list({"start": today, "end": end, "limit": 20, "source": cfg["calendar_file"]})


def _resource_notes_recent() -> str:
    return _tool_notes_list({"limit": 10})


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
        # Fallback: search by content
        return _tool_notes_search({"query": "RFC", "limit": 10})
    lines = [f"📋 RFCs en {notes_d} — {len(rfc_files)} ficheros:"]
    for f in rfc_files:
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
        lines.append(f"  {mtime}  {f.name}")
    return "\n".join(lines)


def _resource_tasks_today() -> str:
    todo_path = Path.home() / ".oocode" / "todos.json"
    if not todo_path.exists():
        return "Sin tareas pendientes. Usa el plugin todo (/todo) para añadir tareas."
    try:
        data   = json.loads(todo_path.read_text())
        todos  = data if isinstance(data, list) else data.get("todos", [])
        today  = datetime.date.today().isoformat()
        pending = [t for t in todos if t.get("status", "pending") != "done"]
        done    = [t for t in todos if t.get("status") == "done"]
        if not pending:
            return f"✅ Sin tareas pendientes hoy ({today}). {len(done)} completadas."
        lines = [f"📋 Tareas pendientes ({len(pending)}) — {today}:"]
        for t in pending[:25]:
            icon  = "◻" if t.get("status") == "pending" else "◼"
            title = t.get("title", t.get("text", str(t)))
            cat   = t.get("category", "")
            cat_s = f" [{cat}]" if cat else ""
            lines.append(f"  {icon} {title}{cat_s}")
        if done:
            lines.append(f"\n✅ Completadas hoy: {len(done)}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error leyendo tareas: {exc}"


def _resource_project_context() -> str:
    return _tool_project_context_read({})


def _resource_server_inventory() -> str:
    return _tool_cmdb_search({"query": "*", "limit": 50})


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
        {"name": "bar",           "tool": "create_bar_chart",         "use_case": "Comparar categorías",           "multi_series": True,  "key_params": ["categories", "values/series", "x_label", "y_label", "horizontal", "stacked"]},
        {"name": "stacked_bar",   "tool": "create_stacked_bar_chart", "use_case": "Comparar proporciones apiladas","multi_series": True,  "key_params": ["categories", "series", "horizontal"]},
        {"name": "line",          "tool": "create_line_chart",        "use_case": "Tendencias temporales",         "multi_series": True,  "key_params": ["x_labels", "y_values/series", "fill_area"]},
        {"name": "pie",           "tool": "create_pie_chart",         "use_case": "Distribución porcentual",       "multi_series": False, "key_params": ["labels", "sizes", "donut", "explode"]},
        {"name": "scatter",       "tool": "create_scatter_chart",     "use_case": "Correlación entre variables",   "multi_series": True,  "key_params": ["x_values", "y_values", "trend_line", "point_labels"]},
        {"name": "heatmap",       "tool": "create_heatmap",           "use_case": "Matrices de correlación, KPIs", "multi_series": False, "key_params": ["data", "row_labels", "col_labels", "colormap"]},
        {"name": "radar",         "tool": "create_radar_chart",       "use_case": "Comparar perfiles/habilidades", "multi_series": True,  "key_params": ["categories", "series", "fill"]},
        {"name": "gantt",         "tool": "create_gantt_chart",       "use_case": "Planificación de proyectos",    "multi_series": False, "key_params": ["tasks[{name,start,end,category}]"]},
        {"name": "org_chart",     "tool": "create_org_chart",         "use_case": "Jerarquías organizativas",      "multi_series": False, "key_params": ["nodes[{id,label,parent}]"]},
        {"name": "xlsx_bar/line/pie", "tool": "xlsx_insert_chart",    "use_case": "Gráfica nativa incrustada en .xlsx","multi_series": True, "key_params": ["path", "sheet", "data_range", "chart_type"]},
    ]
    return json.dumps(chart_types, ensure_ascii=False, indent=2)


def _resource_diagram_templates() -> str:
    import json
    templates = {
        "gantt_example": {
            "description": "Diagrama de Gantt básico para un proyecto de 3 semanas",
            "tool": "create_gantt_chart",
            "args": {
                "title": "Plan de Proyecto Q1",
                "style": "office",
                "tasks": [
                    {"name": "Análisis de requisitos", "start": "2026-01-05", "end": "2026-01-10", "category": "Análisis"},
                    {"name": "Diseño de arquitectura", "start": "2026-01-08", "end": "2026-01-15", "category": "Diseño"},
                    {"name": "Desarrollo módulo A",    "start": "2026-01-13", "end": "2026-01-22", "category": "Desarrollo"},
                    {"name": "Desarrollo módulo B",    "start": "2026-01-16", "end": "2026-01-26", "category": "Desarrollo"},
                    {"name": "Testing integración",    "start": "2026-01-23", "end": "2026-01-30", "category": "QA"},
                    {"name": "Despliegue producción",  "start": "2026-01-29", "end": "2026-01-31", "category": "Release"},
                ],
            },
        },
        "org_chart_example": {
            "description": "Organigrama de departamento TI",
            "tool": "create_org_chart",
            "args": {
                "title": "Departamento de TI",
                "nodes": [
                    {"id": "cto",      "label": "CTO",                "parent": None},
                    {"id": "dev_lead", "label": "Dev Lead",            "parent": "cto"},
                    {"id": "ops_lead", "label": "Ops Lead",            "parent": "cto"},
                    {"id": "qa_lead",  "label": "QA Lead",             "parent": "cto"},
                    {"id": "fe_dev",   "label": "Frontend Dev",        "parent": "dev_lead"},
                    {"id": "be_dev",   "label": "Backend Dev",         "parent": "dev_lead"},
                    {"id": "sre",      "label": "SRE Engineer",        "parent": "ops_lead"},
                    {"id": "qa_eng",   "label": "QA Engineer",         "parent": "qa_lead"},
                ],
            },
        },
        "radar_example": {
            "description": "Gráfico radar para comparar habilidades de dos personas",
            "tool": "create_radar_chart",
            "args": {
                "title": "Evaluación de Competencias",
                "categories": ["Python", "DevOps", "SQL", "Comunicación", "Liderazgo", "Cloud"],
                "series": [
                    {"label": "Ana", "values": [9, 7, 8, 7, 6, 8]},
                    {"label": "Pedro", "values": [7, 9, 6, 8, 9, 7]},
                ],
            },
        },
        "heatmap_example": {
            "description": "Heatmap de KPIs mensuales por región",
            "tool": "create_heatmap",
            "args": {
                "title": "KPIs por Región — Q1 2026",
                "colormap": "RdYlGn",
                "row_labels": ["Norte", "Sur", "Este", "Oeste"],
                "col_labels": ["Enero", "Febrero", "Marzo"],
                "data": [[78, 82, 85], [90, 88, 92], [65, 70, 75], [85, 87, 90]],
            },
        },
    }
    return json.dumps(templates, ensure_ascii=False, indent=2)


def _resource_flowchart_shapes() -> str:
    import json
    shapes = [
        {"name": "Terminal (oval)",     "use": "Inicio/Fin del proceso",          "symbol": "( )"},
        {"name": "Process (rectangle)", "use": "Acción o paso del proceso",       "symbol": "[  ]"},
        {"name": "Decision (diamond)",  "use": "Condición o pregunta Sí/No",      "symbol": "<  >"},
        {"name": "IO (parallelogram)",  "use": "Entrada/Salida de datos",         "symbol": "/  /"},
        {"name": "Document",            "use": "Documento generado o consultado", "symbol": "[~]"},
        {"name": "Database (cylinder)", "use": "Base de datos o almacenamiento",  "symbol": "[DB]"},
        {"name": "Manual input",        "use": "Entrada manual por el usuario",   "symbol": "[M]"},
        {"name": "Connector (circle)",  "use": "Referencia a otro punto del flujo","symbol": "(A)"},
        {"name": "Subprocess",          "use": "Subproceso o función externa",    "symbol": "[+]"},
        {"name": "Delay",               "use": "Espera o retraso en el proceso",  "symbol": "[D>]"},
        {"name": "Merge",               "use": "Unión de flujos paralelos",       "symbol": "[V]"},
        {"name": "Parallel",            "use": "División en flujos paralelos",    "symbol": "[||]"},
    ]
    return json.dumps(shapes, ensure_ascii=False, indent=2)


_RESOURCE_FNS = {
    "office://emails_recent":       _resource_emails_recent,
    "office://calendar_today":      _resource_calendar_today,
    "office://notes_recent":        _resource_notes_recent,
    "office://templates_available": _resource_templates_available,
    "office://rfc_pending":         _resource_rfc_pending,
    "office://tasks_today":         _resource_tasks_today,
    "office://project_context":     _resource_project_context,
    "office://server_inventory":    _resource_server_inventory,
    "office://style_gallery":       _resource_style_gallery,
    "office://style_presets":       _resource_style_presets,
    "office://theme_colors":        _resource_theme_colors,
    "office://font_combinations":   _resource_font_combinations,
    "office://chart_types":         _resource_chart_types,
    "office://diagram_templates":   _resource_diagram_templates,
    "office://flowchart_shapes":    _resource_flowchart_shapes,
}


# ── Bucle principal ───────────────────────────────────────────────────────────

def _handle(req: dict) -> None:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "home-office-assistant", "version": "2.0.0"},
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
    sys.stderr.write("[home-office-assistant] MCP server v4.2 iniciado (77 tools, 17 prompts, 15 resources)\n")
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
            sys.stderr.write(f"[home-office-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
