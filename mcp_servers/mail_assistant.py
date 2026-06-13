#!/usr/bin/env python3
"""Mail Assistant MCP Server — comunicación y agenda (PIM) para OOCode.

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 newline-delimited JSON).

Email (IMAP/SMTP), calendario (.ics local), notas markdown y contactos vCard.

Configuración: ~/.oocode/mail.json  (fallback legacy: ~/.oocode/home_office.json)
  {"email": {"imap_host": "...", "smtp_host": "...", "user": "...", "password": "..."},
   "notes_dir": "...", "calendar_file": "...", "contacts_dir": "..."}

Dividido desde home_office_assistant.py (v0.4.4): documentos O365 →
office_assistant.py; CMDB/inventario → cmdb_assistant.py.
"""
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


# ── Configuración ────────────────────────────────────────────────────────────

# Config principal del servidor (con fallback al legacy ~/.oocode/home_office.json)
_CONFIG_PATH        = Path.home() / ".oocode" / "mail.json"
_LEGACY_CONFIG_PATH = Path.home() / ".oocode" / "home_office.json"

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
    "notes_dir":     str(Path.home() / "Documents" / "notes"),
    "calendar_file": str(Path.home() / "Documents" / "calendar.ics"),
    "contacts_dir":  str(Path.home() / "Documents" / "contacts"),
}


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _load_config() -> dict:
    cfg = json.loads(json.dumps(_DEFAULT_CFG))
    src = _CONFIG_PATH if _CONFIG_PATH.exists() else _LEGACY_CONFIG_PATH
    if src.exists():
        try:
            _deep_merge(cfg, json.loads(src.read_text()))
        except Exception:
            pass
    em = cfg["email"]
    em["imap_host"] = os.environ.get("HOME_OFFICE_IMAP_HOST", em["imap_host"])
    em["imap_port"] = int(os.environ.get("HOME_OFFICE_IMAP_PORT", em["imap_port"]))
    em["smtp_host"] = os.environ.get("HOME_OFFICE_SMTP_HOST", em["smtp_host"])
    em["smtp_port"] = int(os.environ.get("HOME_OFFICE_SMTP_PORT", em["smtp_port"]))
    em["user"]      = os.environ.get("HOME_OFFICE_EMAIL_USER", em["user"])
    em["password"]  = os.environ.get("HOME_OFFICE_EMAIL_PASS", em["password"])
    cfg["notes_dir"]     = os.environ.get("HOME_OFFICE_NOTES_DIR",     cfg["notes_dir"])
    cfg["calendar_file"] = os.environ.get("HOME_OFFICE_CALENDAR_FILE", cfg["calendar_file"])
    cfg["contacts_dir"]  = os.environ.get("HOME_OFFICE_CONTACTS_DIR",  cfg["contacts_dir"])
    local_cfg = Path.cwd() / ".oocode-office.json"
    if local_cfg.exists():
        try:
            _deep_merge(cfg, json.loads(local_cfg.read_text()))
        except Exception:
            pass
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



# Límite de truncado de salida (configurable: tools.mcpMaxOutputChars en oocode.json)
def _mcp_max_output(default: int = 4000) -> int:
    try:
        _f = Path.home() / ".oocode" / "oocode.json"
        if _f.exists():
            return int(json.loads(_f.read_text()).get("tools", {}).get("mcpMaxOutputChars", default))
    except Exception:
        pass
    return default


_MAX_OUTPUT = _mcp_max_output()


# ── Helpers y tools ────────────────────────────────────────────────────────────

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
        f"Protege el fichero: chmod 600 {_CONFIG_PATH}"
    )


# ── Protocolo MCP ────────────────────────────────────────────────────────────


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
        lines.append(body[:_MAX_OUTPUT] if body else "(sin cuerpo)")
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
    else:
        rc, out, err = _run(["grep", "-r", "-l", "-i", query, str(dirpath)], timeout=15)
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


# ── Bloque 1: Workspace / Proyecto ───────────────────────────────────────────


# ── Tools registry ──────────────────────────────────────────────────────────────

_TOOLS = [{'name': 'email_list',
  'description': 'Lista emails de una bandeja de entrada (IMAP). Requiere configuración en '
                 '~/.oocode/mail.json.',
  'inputSchema': {'type': 'object',
                  'properties': {'mailbox': {'type': 'string',
                                             'description': 'Carpeta IMAP. Default: INBOX'},
                                 'limit': {'type': 'integer',
                                           'description': 'Máximo de emails a devolver (max 50). '
                                                          'Default: 10'}}}},
 {'name': 'email_read',
  'description': 'Lee un email completo por su UID IMAP.',
  'inputSchema': {'type': 'object',
                  'properties': {'uid': {'type': 'string',
                                         'description': 'UID del email (obtenido de email_list)'},
                                 'mailbox': {'type': 'string',
                                             'description': 'Carpeta IMAP. Default: INBOX'}},
                  'required': ['uid']}},
 {'name': 'email_send',
  'description': 'Envía un email por SMTP. Requiere configuración en ~/.oocode/mail.json.',
  'inputSchema': {'type': 'object',
                  'properties': {'to': {'type': 'string',
                                        'description': 'Destinatario(s), separados por coma'},
                                 'subject': {'type': 'string', 'description': 'Asunto del email'},
                                 'body': {'type': 'string',
                                          'description': 'Cuerpo del email (texto plano)'},
                                 'cc': {'type': 'string', 'description': 'CC (opcional)'},
                                 'bcc': {'type': 'string', 'description': 'BCC (opcional)'}},
                  'required': ['to', 'subject', 'body']}},
 {'name': 'email_search',
  'description': 'Busca emails por asunto o contenido usando IMAP SEARCH.',
  'inputSchema': {'type': 'object',
                  'properties': {'query': {'type': 'string',
                                           'description': 'Texto a buscar en asunto y cuerpo'},
                                 'mailbox': {'type': 'string',
                                             'description': 'Carpeta IMAP. Default: INBOX'},
                                 'limit': {'type': 'integer',
                                           'description': 'Máximo de resultados. Default: 20'}},
                  'required': ['query']}},
 {'name': 'cal_list',
  'description': 'Lista eventos de un fichero .ics local, con filtro opcional por rango de fechas.',
  'inputSchema': {'type': 'object',
                  'properties': {'source': {'type': 'string',
                                            'description': 'Ruta al fichero .ics (por defecto: '
                                                           'calendar_file en config)'},
                                 'start': {'type': 'string',
                                           'description': 'Fecha inicio filtro, formato YYYY-MM-DD '
                                                          '(opcional)'},
                                 'end': {'type': 'string',
                                         'description': 'Fecha fin filtro, formato YYYY-MM-DD '
                                                        '(opcional)'},
                                 'limit': {'type': 'integer',
                                           'description': 'Máximo de eventos. Default: 15'}}}},
 {'name': 'cal_add',
  'description': 'Añade un evento a un fichero .ics local.',
  'inputSchema': {'type': 'object',
                  'properties': {'title': {'type': 'string', 'description': 'Título del evento'},
                                 'start': {'type': 'string',
                                           'description': 'Fecha/hora inicio: YYYY-MM-DD o '
                                                          'YYYY-MM-DDTHH:MM'},
                                 'end': {'type': 'string',
                                         'description': 'Fecha/hora fin (opcional)'},
                                 'location': {'type': 'string', 'description': 'Lugar (opcional)'},
                                 'description': {'type': 'string',
                                                 'description': 'Descripción (opcional)'},
                                 'file': {'type': 'string',
                                          'description': 'Ruta al fichero .ics (por defecto: '
                                                         'calendar_file en config)'}},
                  'required': ['title', 'start']}},
 {'name': 'cal_search',
  'description': 'Busca eventos en un fichero .ics por texto en título o descripción.',
  'inputSchema': {'type': 'object',
                  'properties': {'query': {'type': 'string', 'description': 'Texto a buscar'},
                                 'source': {'type': 'string',
                                            'description': 'Ruta al fichero .ics (opcional)'},
                                 'limit': {'type': 'integer',
                                           'description': 'Máximo de resultados. Default: 20'}},
                  'required': ['query']}},
 {'name': 'notes_list',
  'description': 'Lista ficheros markdown en el directorio de notas, ordenados por fecha de '
                 'modificación.',
  'inputSchema': {'type': 'object',
                  'properties': {'directory': {'type': 'string',
                                               'description': 'Directorio de notas (por defecto: '
                                                              'notes_dir en config)'},
                                 'pattern': {'type': 'string',
                                             'description': 'Patrón glob. Default: *.md'},
                                 'limit': {'type': 'integer',
                                           'description': 'Máximo de notas. Default: 20'}}}},
 {'name': 'notes_search',
  'description': 'Busca texto en ficheros markdown del directorio de notas usando ripgrep o grep.',
  'inputSchema': {'type': 'object',
                  'properties': {'query': {'type': 'string', 'description': 'Texto a buscar'},
                                 'directory': {'type': 'string',
                                               'description': 'Directorio de notas (opcional)'},
                                 'limit': {'type': 'integer',
                                           'description': 'Máximo de ficheros con resultados. '
                                                          'Default: 10'}},
                  'required': ['query']}},
 {'name': 'notes_save',
  'description': 'Guarda o actualiza una nota markdown con front matter (title, created, '
                 'modified).',
  'inputSchema': {'type': 'object',
                  'properties': {'title': {'type': 'string',
                                           'description': 'Título de la nota (también determina el '
                                                          'nombre del fichero)'},
                                 'content': {'type': 'string',
                                             'description': 'Contenido en markdown'},
                                 'directory': {'type': 'string',
                                               'description': 'Directorio donde guardar '
                                                              '(opcional)'}},
                  'required': ['title']}},
 {'name': 'contact_search',
  'description': 'Busca en ficheros vCard (.vcf) por nombre, email, teléfono u organización.',
  'inputSchema': {'type': 'object',
                  'properties': {'query': {'type': 'string',
                                           'description': 'Texto a buscar en los contactos'},
                                 'vcf_dir': {'type': 'string',
                                             'description': 'Directorio de contactos (por defecto: '
                                                            'contacts_dir en config)'}},
                  'required': ['query']}}]


_TOOL_FNS: dict[str, Any] = {
    'email_list'     : _tool_email_list,
    'email_read'     : _tool_email_read,
    'email_send'     : _tool_email_send,
    'email_search'   : _tool_email_search,
    'cal_list'       : _tool_cal_list,
    'cal_add'        : _tool_cal_add,
    'cal_search'     : _tool_cal_search,
    'notes_list'     : _tool_notes_list,
    'notes_search'   : _tool_notes_search,
    'notes_save'     : _tool_notes_save,
    'contact_search' : _tool_contact_search,
}



# ── Prompts ─────────────────────────────────────────────────────────────────────

_PROMPTS: dict[str, dict] = {'draft_email': {'description': 'Redacta un email profesional con tono y estructura configurables.',
                 'arguments': [{'name': 'to', 'description': 'Destinatario', 'required': True},
                               {'name': 'subject', 'description': 'Asunto', 'required': True},
                               {'name': 'context',
                                'description': 'Contexto o propósito',
                                'required': True},
                               {'name': 'tone',
                                'description': 'formal/informal/amigable',
                                'required': False},
                               {'name': 'language',
                                'description': 'Idioma (español por defecto)',
                                'required': False}]},
 'meeting_notes': {'description': 'Genera un acta de reunión estructurada con asistentes, puntos '
                                  'tratados y decisiones.',
                   'arguments': [{'name': 'attendees',
                                  'description': 'Lista de asistentes',
                                  'required': True},
                                 {'name': 'agenda',
                                  'description': 'Puntos de la agenda',
                                  'required': True},
                                 {'name': 'notes',
                                  'description': 'Notas o puntos discutidos',
                                  'required': False},
                                 {'name': 'date',
                                  'description': 'Fecha de la reunión (YYYY-MM-DD)',
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
    else:
        prompt = f"Prompt {name} no disponible."
    return [{"role": "user", "content": {"type": "text", "text": prompt}}]


# ── Resources ────────────────────────────────────────────────────────────────


# ── Resources ───────────────────────────────────────────────────────────────────

def _resource_emails_recent() -> str:
    return _tool_email_list({"limit": 10})


def _resource_calendar_today() -> str:
    cfg   = _load_config()
    today = datetime.date.today().isoformat()
    end   = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    return _tool_cal_list({"start": today, "end": end, "limit": 20, "source": cfg["calendar_file"]})


def _resource_notes_recent() -> str:
    return _tool_notes_list({"limit": 10})


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


_RESOURCES = [{'uri': 'mail://emails_recent',
  'name': 'Emails recientes',
  'description': 'Últimos 10 emails de la bandeja de entrada',
  'mimeType': 'text/plain'},
 {'uri': 'mail://calendar_today',
  'name': 'Calendario',
  'description': 'Eventos de hoy y los próximos 7 días',
  'mimeType': 'text/plain'},
 {'uri': 'mail://notes_recent',
  'name': 'Notas recientes',
  'description': 'Notas markdown más recientes (últimas 10)',
  'mimeType': 'text/plain'},
 {'uri': 'mail://tasks_today',
  'name': 'Tareas de hoy',
  'description': 'Tareas pendientes de la jornada (desde el plugin todo de OOCode)',
  'mimeType': 'text/plain'}]


_RESOURCE_FNS = {
    'mail://emails_recent'  : _resource_emails_recent,
    'mail://calendar_today' : _resource_calendar_today,
    'mail://notes_recent'   : _resource_notes_recent,
    'mail://tasks_today'    : _resource_tasks_today,
}



# ── Bucle principal ─────────────────────────────────────────────────────────────

def _handle(req: dict) -> None:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "mail-assistant", "version": "1.0.0"},
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
    sys.stderr.write("[mail-assistant] MCP server v1.0.0 iniciado (11 tools, 2 prompts, 4 resources)\n")
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
            sys.stderr.write(f"[mail-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()

