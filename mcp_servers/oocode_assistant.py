#!/usr/bin/env python3
"""OOCode Assistant MCP Server — utilidades de desarrollo para OOCode.

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 con Content-Length framing).

Tools:
  get_datetime        — fecha/hora actual en múltiples zonas y formatos
  system_info         — OS, Python, CPU, memoria, disco
  list_recent_files   — ficheros modificados recientemente en un directorio
  read_project_file   — lee un fichero del proyecto (README, OOCODE.md, etc.)
  run_quick_check     — ejecuta un comando de verificación corto (lint, test)
  search_todos        — busca TODO/FIXME/HACK/NOTE en el código con file:line
  port_check          — verifica qué puertos locales están en uso
  read_files          — lee varios ficheros en una sola llamada
  http_get            — GET a una URL local (APIs de desarrollo, health checks)
  calculate           — evalúa expresiones matemáticas de forma segura
  diff_files          — diff entre dos ficheros o dos bloques de texto
  grep_code           — grep con regex y contexto en el código fuente del proyecto
  env_check           — muestra variables de entorno de desarrollo (sin secretos)
  json_format         — valida, formatea y consulta JSON con path simple
  hash_text           — calcula MD5/SHA1/SHA256 de texto o de un fichero
  write_file          — escribe/sobreescribe un fichero con diff en la respuesta (append, mkdir)
  find_files          — find avanzado: por nombre glob, extensión, tamaño y edad
  process_list        — procesos activos filtrados (Python, Node, etc.) con PID y puerto
  url_encode          — codifica/decodifica URL percent-encoding y Base64
  count_lines         — cuenta líneas de código por lenguaje en un directorio (estilo cloc)
  template_fill       — rellena una plantilla de texto con variables {{clave}}
  git_status          — estado del repositorio: rama, archivos modificados, staged, untracked
  git_diff            — diferencias: unstaged, staged o respecto a un commit/rama
  git_log             — historial de commits con gráfico de ramas; admite filtro por fichero
  git_add             — añade ficheros al área de staging
  git_commit          — crea un commit con los cambios staged
  git_push            — sube commits al repositorio remoto
  git_pull            — descarga y fusiona commits del repositorio remoto
  git_branch          — gestiona ramas: listar, crear, cambiar, eliminar, renombrar
  git_stash           — gestiona el stash: push, pop, list (con diff), drop
  git_patch           — crea o aplica parches (create, format, apply)
  git_clone           — clona un repositorio remoto
  git_worktree        — gestiona git worktrees: listar, crear, eliminar, podar, bloquear
  docker_ps           — lista contenedores Docker en ejecución o todos
  docker_logs         — muestra los logs recientes de un contenedor
  docker_exec         — ejecuta un comando en un contenedor en ejecución
  docker_inspect      — detalles de un contenedor: imagen, estado, IP, puertos, env
  docker_images       — lista las imágenes Docker disponibles localmente
  docker_stop         — detiene un contenedor en ejecución
  docker_rm           — elimina un contenedor detenido
  compose_version     — versión de Docker Compose y binario detectado
  compose_services    — servicios definidos en el fichero docker-compose
  compose_status      — estado de los servicios de Docker Compose
  compose_up          — levanta los servicios de Docker Compose
  compose_down        — detiene y elimina contenedores de Compose
  compose_stop        — detiene servicios sin eliminar los contenedores
  compose_restart     — reinicia servicios de Docker Compose
  compose_build       — construye o reconstruye imágenes de Docker Compose
  compose_pull        — descarga últimas versiones de las imágenes de Compose
  compose_logs        — logs de los servicios de Docker Compose
  compose_exec        — ejecuta un comando en un servicio en ejecución de Compose
  compose_run         — ejecuta un comando puntual en un nuevo contenedor del servicio
  compose_config      — valida y muestra la configuración efectiva de Compose
  compose_images      — imágenes utilizadas por los servicios de Compose
  compose_top         — procesos corriendo dentro de los contenedores de Compose
  build_symbol_index  — genera índice de símbolos con ctags (funciones, clases, variables)
  find_symbol         — busca dónde está definida una función, clase o variable
  list_symbols        — lista símbolos definidos en un fichero
  lint_file           — ejecuta linters sobre un fichero (ruff, mypy, eslint, shellcheck…)
  lint_project        — ejecuta linters sobre todo el proyecto de forma resumida
  ls_file             — información detallada (stat) de un fichero o directorio
  ls_dir              — lista directorio con permisos, propietario, tamaño y fecha
  find_file           — busca ficheros por patrón glob en un directorio
  find_dir            — busca directorios por patrón glob
  grep_file           — busca regex en un fichero con números de línea y contexto
  chmod_file          — cambia permisos de un fichero
  chmod_dir           — cambia permisos de un directorio (opcionalmente recursivo)
  chown_file          — cambia propietario de un fichero
  chown_dir           — cambia propietario de un directorio (opcionalmente recursivo)
  mv_file             — mueve o renombra un fichero o directorio
  cp_file             — copia un fichero o directorio
  rm_file             — elimina un fichero
  rm_dir              — elimina un directorio (vacío o recursivo)
  mkdir_dir           — crea un directorio con mkdir -p
  touch_file          — crea un fichero vacío o actualiza su timestamp

Tools de debug de procesos:
  strace_run          — traza syscalls de un comando o proceso PID con strace
  gdb_run             — ejecuta GDB sobre un binario en modo batch con comandos
  pdb_run             — ejecuta un script Python bajo pdb con comandos (no interactivo)
  valgrind_run        — analiza memoria de un binario con Valgrind (memcheck)

Tools de build y ejecución:
  make_run            — ejecuta targets de Makefile con salida estructurada
  run_script          — ejecuta un script (Python, bash, sh, node) con timeout
  format_code         — formatea código con black/prettier/gofmt/rustfmt/isort
  mypy_check          — comprueba tipos con mypy sobre un fichero o directorio

Tools Python:
  python_exec         — ejecuta un fragmento de código Python y captura stdout/stderr
  pip_tool            — gestión de paquetes pip: list/show/install/freeze/check/outdated

Tools Node.js:
  npm_tool            — gestión de paquetes npm: list/run/info/install/audit/outdated

Tools de archivo/compresión:
  archive_extract     — extrae tar, zip, tar.gz, tar.bz2, tar.xz
  archive_create      — crea archivos tar.gz, tar.bz2, tar.xz o zip
  archive_list        — lista el contenido de un archivo comprimido

Tools de metadatos de ficheros:
  file_stat           — metadatos completos de un fichero: permisos, propietario, tiempos, inode
  symlink_create      — crea un enlace simbólico (ln -s)
  readlink            — resuelve el destino de un enlace simbólico

Herramientas de parches:
  patch_apply         — aplica un diff unificado a ficheros del proyecto

Resources:
  project://context   — OOCODE.md + README.md del directorio actual
  project://structure — árbol de directorios (2 niveles)
  project://git       — git status + últimos 10 commits + diff stats
  project://deps      — dependencias del proyecto (pyproject.toml/requirements/package.json)
  project://tests     — tests encontrados en el proyecto con su ruta y estado
  project://env       — variables de entorno de desarrollo relevantes (filtradas)
  project://errors    — últimas líneas de logs de error del sistema (journalctl/syslog)
  project://metrics   — métricas de código: líneas, ficheros, lenguajes (por extensión)
  project://changelog — CHANGELOG.md o CHANGES.rst más reciente del proyecto
  project://docker    — estado Docker: contenedores activos, imágenes y volúmenes
  project://coverage  — informe de cobertura más reciente (.coverage / htmlcov / coverage.xml)

Prompts:
  code_review         — revisión de código estructurada
  debug_session       — inicio de sesión de debugging
  commit_message      — genera un mensaje de commit a partir de un diff
  test_cases          — genera casos de test (pytest) para una función o clase
  sql_query           — genera queries PostgreSQL a partir de descripción en lenguaje natural
  explain_code        — explicación profunda con complejidad, invariantes y edge cases
  refactor_code       — refactoriza código para mejor legibilidad o rendimiento
  api_design          — diseña una API REST o interfaz Python
  documentation       — genera docstrings, README o comentarios de módulo
  security_audit      — auditoría de seguridad de código con OWASP top 10
  architecture_review — revisión de arquitectura de un sistema o módulo
  pr_description      — genera descripción de PR a partir de commits y diff
  error_analysis      — analiza un stack trace completo y propone soluciones concretas
  data_model          — diseña un modelo de datos (tablas SQL o dataclasses Python)
  code_migration      — plan de migración entre versiones, lenguajes o frameworks
"""
import difflib
import hashlib
import json
import os
import re
import sys
import datetime
import platform
import subprocess
import tempfile as _tempfile
from pathlib import Path
from typing import Any, Optional


def _get_tmp_dir() -> Path:
    """Devuelve ~/.oocode/tmp, creándolo si no existe."""
    d = Path.home() / ".oocode" / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Helpers de protocolo MCP (stdio, newline-delimited JSON) ─────────────────

def _send(obj: dict) -> None:
    body = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(body + "\n")
    sys.stdout.flush()


def _recv() -> Optional[dict]:
    """Lee un mensaje MCP de stdin (una línea JSON). Devuelve None en EOF."""
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
    _send({"jsonrpc": "2.0", "id": req_id,
           "error": {"code": code, "message": message}})


# ── Tools originales ──────────────────────────────────────────────────────────

def _tool_get_datetime(args: dict) -> str:
    fmt    = args.get("format", "iso")
    tz     = args.get("timezone", "local")
    now    = datetime.datetime.now()
    utcnow = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    if fmt == "iso":
        result = now.isoformat(timespec="seconds")
    elif fmt == "human":
        result = now.strftime("%A, %d de %B de %Y — %H:%M:%S")
    elif fmt == "unix":
        result = str(int(now.timestamp()))
    elif fmt == "date":
        result = now.strftime("%Y-%m-%d")
    elif fmt == "time":
        result = now.strftime("%H:%M:%S")
    else:
        result = now.isoformat(timespec="seconds")
    lines = [f"Hora local: {result}"]
    if tz == "utc" or fmt == "iso":
        lines.append(f"UTC:        {utcnow.isoformat(timespec='seconds')}Z")
    return "\n".join(lines)


def _tool_system_info(args: dict) -> str:
    lines = [
        f"OS:     {platform.system()} {platform.release()} ({platform.machine()})",
        f"Python: {platform.python_version()} ({sys.executable})",
        f"Host:   {platform.node()}",
    ]
    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem     = psutil.virtual_memory()
        disk    = psutil.disk_usage("/")
        lines += [
            f"CPU:    {cpu_pct:.1f}% ({psutil.cpu_count(logical=False)} físicos, {psutil.cpu_count()} lógicos)",
            f"RAM:    {mem.used // 1024**2} MB usados / {mem.total // 1024**2} MB total ({mem.percent:.1f}%)",
            f"Disco:  {disk.used // 1024**3} GB usados / {disk.total // 1024**3} GB total ({disk.percent:.1f}%)",
        ]
    except ImportError:
        lines.append("(psutil no disponible — instalar para stats de CPU/RAM/disco)")
    try:
        uptime_s = float(Path("/proc/uptime").read_text().split()[0])
        h, rem = divmod(int(uptime_s), 3600)
        m, s   = divmod(rem, 60)
        lines.append(f"Uptime: {h}h {m}m {s}s")
    except Exception:
        pass
    return "\n".join(lines)


def _tool_list_recent_files(args: dict) -> str:
    directory = args.get("directory", ".")
    n         = min(int(args.get("count", 20)), 100)
    ext       = args.get("extension", "")
    root      = Path(directory).expanduser().resolve()
    if not root.exists():
        return f"Error: directorio no encontrado: {directory}"
    try:
        files = sorted(
            (f for f in root.rglob("*") if f.is_file()
             and not any(p in f.parts for p in
                         [".git", "__pycache__", "node_modules", ".venv",
                          "venv", ".mypy_cache", "dist", "build"])
             and (not ext or f.suffix.lower() == ("." + ext.lstrip(".").lower()))),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:n]
    except Exception as exc:
        return f"Error listando ficheros: {exc}"
    if not files:
        return "No se encontraron ficheros."
    lines = [f"Últimos {n} ficheros modificados en {root}:\n"]
    now = datetime.datetime.now().timestamp()
    for f in files:
        mtime = f.stat().st_mtime
        age_s = now - mtime
        if age_s < 3600:
            age = f"{int(age_s // 60)}m"
        elif age_s < 86400:
            age = f"{int(age_s // 3600)}h"
        else:
            age = f"{int(age_s // 86400)}d"
        rel = f.relative_to(root) if f.is_relative_to(root) else f
        lines.append(f"  {age:>4}  {rel}")
    return "\n".join(lines)


def _tool_read_project_file(args: dict) -> str:
    filename  = args.get("filename", "OOCODE.md")
    directory = args.get("directory", ".")
    max_chars = int(args.get("max_chars", 4000))
    root      = Path(directory).expanduser().resolve()
    candidates = [root / filename, Path.cwd() / filename]
    for path in candidates:
        if path.exists():
            text = path.read_text(errors="replace")
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n... [truncado a {max_chars} chars]"
            return f"# {path}\n\n{text}"
    return f"Fichero no encontrado: {filename} en {directory}"


def _tool_run_quick_check(args: dict) -> str:
    cmd       = args.get("command", "")
    directory = args.get("directory", ".")
    timeout   = min(int(args.get("timeout", 30)), 120)
    if not cmd:
        return "Error: 'command' requerido."

    # Bloquear comandos destructivos
    _blocked = re.compile(
        r'\b(rm\s+-rf|dd\s+if=|mkfs|shutdown|reboot|halt|poweroff|'
        r'killall|pkill|wipefs|fdisk|parted)\b',
        re.IGNORECASE,
    )
    if _blocked.search(cmd):
        return (
            f"Error: comando bloqueado por seguridad: {cmd}\n"
            "Usa la tool bash del agente principal para comandos destructivos con permiso explícito."
        )

    cwd = directory if Path(directory).is_dir() else "."
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
            start_new_session=True,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        status = "OK" if proc.returncode == 0 else f"exit {proc.returncode}"

        parts = [f"[{status}] $ {cmd}"]
        if stdout:
            lines = stdout.splitlines()
            if len(lines) > 200:
                lines = lines[:200] + [f"… ({len(lines)-200} líneas más)"]
            parts.append("STDOUT:\n" + "\n".join(lines))
        if stderr:
            elines = stderr.splitlines()
            if len(elines) > 100:
                elines = elines[:100] + [f"… ({len(elines)-100} líneas más)"]
            parts.append("STDERR:\n" + "\n".join(elines))
        if not stdout and not stderr:
            parts.append("(sin salida)")
        return "\n\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s): {cmd}"
    except Exception as exc:
        return f"Error: {exc}"


# ── Tools nuevas ──────────────────────────────────────────────────────────────

def _tool_search_todos(args: dict) -> str:
    """Busca TODO/FIXME/HACK/NOTE/XXX en el código fuente con file:line."""
    directory  = args.get("directory", ".")
    tags_arg   = args.get("tags", "TODO,FIXME,HACK,NOTE,XXX")
    extensions = args.get("extensions", "py,js,ts,c,h,cpp,rs,go,java,rb,sh")
    max_results = min(int(args.get("max_results", 100)), 500)

    root = Path(directory).expanduser().resolve()
    if not root.exists():
        return f"Error: directorio no encontrado: {directory}"

    tags   = [t.strip().upper() for t in tags_arg.split(",") if t.strip()]
    exts   = {"." + e.lstrip(".").lower() for e in extensions.split(",")}
    tag_re = re.compile(r"(?:#|//|/\*|<!--)\s*(" + "|".join(re.escape(t) for t in tags) + r")\b[:\s]*(.*)", re.IGNORECASE)

    _IGNORE = {".git", "__pycache__", "node_modules", ".venv", "venv",
               ".mypy_cache", "dist", "build", "target"}

    results: list[tuple[str, int, str, str]] = []  # (file, line, tag, text)
    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in exts:
            if any(p in f.parts for p in _IGNORE):
                continue
            try:
                for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                    m = tag_re.search(line)
                    if m:
                        rel = str(f.relative_to(root) if f.is_relative_to(root) else f)
                        results.append((rel, i, m.group(1).upper(), m.group(2).strip()))
                        if len(results) >= max_results:
                            break
            except Exception:
                continue
        if len(results) >= max_results:
            break

    if not results:
        return f"No se encontraron {', '.join(tags)} en {root}"

    # Agrupar por tag
    by_tag: dict[str, list] = {}
    for rel, lineno, tag, text in results:
        by_tag.setdefault(tag, []).append((rel, lineno, text))

    lines = [f"Encontrados {len(results)} comentarios en {root}:\n"]
    for tag in tags:
        if tag not in by_tag:
            continue
        entries = by_tag[tag]
        lines.append(f"## {tag} ({len(entries)})")
        for rel, lineno, text in entries:
            snippet = text[:80] + ("…" if len(text) > 80 else "")
            lines.append(f"  {rel}:{lineno}  {snippet}")
        lines.append("")
    return "\n".join(lines)


def _tool_port_check(args: dict) -> str:
    """Verifica qué puertos TCP locales están en uso."""
    ports_arg = args.get("ports", "")
    # Si se pasan puertos específicos, verificarlos; si no, listar todos los LISTEN
    if ports_arg:
        ports = [int(p.strip()) for p in ports_arg.split(",") if p.strip().isdigit()]
    else:
        ports = []

    try:
        # ss es más rápido que netstat y disponible en Linux moderno
        proc = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5,
        )
        output = proc.stdout
    except Exception:
        try:
            proc = subprocess.run(
                ["netstat", "-tlnp"],
                capture_output=True, text=True, timeout=5,
            )
            output = proc.stdout
        except Exception as exc:
            return f"Error obteniendo puertos: {exc}"

    # Parsear líneas de ss/netstat
    listening: dict[int, str] = {}
    for line in output.splitlines():
        # ss format: State Recv-Q Send-Q Local Address:Port  Peer  Process
        # netstat:   tcp   0      0      0.0.0.0:port         ...  LISTEN pid/name
        m = re.search(r"[:\s](\d{2,5})\s+\S*\s+LISTEN\s+(.*)", line)
        if m:
            port = int(m.group(1))
            proc_info = m.group(2).strip()
            listening[port] = proc_info
        else:
            # ss output con Local Address:Port al final del campo
            m2 = re.search(r"LISTEN\s+\d+\s+\d+\s+[\d.*:]+:(\d+)", line)
            if m2:
                port = int(m2.group(1))
                # Extraer proceso si aparece en la línea
                pm = re.search(r'users:\(\("([^"]+)"', line)
                listening[port] = pm.group(1) if pm else ""

    if ports:
        lines = [f"Estado de puertos solicitados en {platform.node()}:\n"]
        for p in sorted(ports):
            if p in listening:
                proc_info = listening[p]
                lines.append(f"  :{p:5d}  ● ACTIVO   {proc_info}")
            else:
                lines.append(f"  :{p:5d}  ○ libre")
    else:
        if not listening:
            return "No se encontraron puertos TCP en LISTEN."
        lines = [f"Puertos TCP en LISTEN en {platform.node()}:\n"]
        for p in sorted(listening):
            proc_info = listening[p]
            lines.append(f"  :{p:5d}  {proc_info}")

    return "\n".join(lines)


def _tool_read_files(args: dict) -> str:
    """Lee varios ficheros en una sola llamada y los devuelve concatenados."""
    paths_arg  = args.get("paths", "")
    max_chars  = min(int(args.get("max_chars_each", 3000)), 8000)
    show_line_numbers = args.get("show_line_numbers", False)

    if not paths_arg:
        return "Error: 'paths' requerido (lista de rutas separadas por coma o JSON array)."

    # Aceptar JSON array o CSV
    if paths_arg.strip().startswith("["):
        try:
            paths = json.loads(paths_arg)
        except json.JSONDecodeError:
            paths = [p.strip() for p in paths_arg.split(",") if p.strip()]
    else:
        paths = [p.strip() for p in paths_arg.split(",") if p.strip()]

    parts = []
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.exists():
            parts.append(f"# {raw}\n(fichero no encontrado)")
            continue
        if p.is_dir():
            parts.append(f"# {raw}\n(es un directorio, no un fichero)")
            continue
        try:
            text = p.read_text(errors="replace")
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            if show_line_numbers:
                text = "\n".join(f"{i+1:4d}  {ln}" for i, ln in enumerate(text.splitlines()))
            suffix = f"\n... [truncado a {max_chars} chars]" if truncated else ""
            parts.append(f"# {p}\n\n{text}{suffix}")
        except Exception as exc:
            parts.append(f"# {raw}\n(error leyendo: {exc})")


    return "\n\n---\n\n".join(parts)


def _tool_http_get(args: dict) -> str:
    """Realiza una petición GET a una URL local (APIs de desarrollo, health checks)."""
    url     = args.get("url", "")
    timeout = min(int(args.get("timeout", 10)), 30)
    headers_arg = args.get("headers", {})

    if not url:
        return "Error: 'url' requerido."

    # Solo permite URLs locales para evitar que se use como proxy de web pública
    _local_prefixes = ("http://localhost", "http://127.", "http://0.0.0.0",
                       "http://192.168.", "http://10.", "http://172.")
    if not any(url.startswith(p) for p in _local_prefixes):
        return (
            "Error: solo se permiten URLs locales (localhost, 127.x, 192.168.x, 10.x, 172.x).\n"
            "Para URLs públicas usa la tool web_fetch de OOCode."
        )

    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "oocode-mcp/1.0")
        if isinstance(headers_arg, dict):
            for k, v in headers_arg.items():
                req.add_header(str(k), str(v))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status  = resp.status
            ct      = resp.headers.get("Content-Type", "")
            body    = resp.read(16_000).decode(errors="replace")
            # Formatear JSON si la respuesta es JSON
            if "json" in ct:
                try:
                    body = json.dumps(json.loads(body), indent=2, ensure_ascii=False)
                except Exception:
                    pass
            return f"HTTP {status} — {url}\nContent-Type: {ct}\n\n{body[:4000]}"
    except Exception as exc:
        return f"Error en GET {url}: {exc}"


def _tool_calculate(args: dict) -> str:
    """Evalúa expresiones matemáticas de forma segura (sin exec/eval de código arbitrario)."""
    expression = args.get("expression", "").strip()
    if not expression:
        return "Error: 'expression' requerido."

    # Whitelist estricta: solo operaciones matemáticas
    _allowed = re.compile(r'^[\d\s\.\+\-\*\/\%\(\)\*\*\^eE,]+$')
    _funcs   = re.compile(r'\b(abs|round|min|max|sum|pow|sqrt|log|log2|log10|sin|cos|tan|pi|e|inf)\b')
    expr_clean = _funcs.sub(lambda m: m.group(0), expression)

    if not _allowed.match(re.sub(r'\b(abs|round|min|max|sum|pow|sqrt|log|log2|log10|sin|cos|tan|pi|e|inf)\b', '', expr_clean)):
        return f"Error: expresión no permitida — solo operaciones matemáticas básicas.\nExpresión: {expression}"

    try:
        import math
        _safe_globals = {
            "__builtins__": {},
            "abs": abs, "round": round, "min": min, "max": max,
            "sum": sum, "pow": pow,
            "sqrt": math.sqrt, "log": math.log, "log2": math.log2,
            "log10": math.log10, "sin": math.sin, "cos": math.cos,
            "tan": math.tan, "pi": math.pi, "e": math.e, "inf": math.inf,
        }
        # Reemplazar ^ por ** (notación matemática común)
        expr_eval = expression.replace("^", "**")
        result = eval(expr_eval, _safe_globals, {})  # noqa: S307
        if isinstance(result, float):
            if result == int(result) and abs(result) < 1e15:
                return f"{expression} = {int(result)}"
            return f"{expression} = {result:.10g}"
        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "Error: división por cero."
    except Exception as exc:
        return f"Error evaluando '{expression}': {exc}"


# ── Tools adicionales ─────────────────────────────────────────────────────────

def _tool_diff_files(args: dict) -> str:
    """Diff entre dos ficheros o dos bloques de texto."""
    file_a   = args.get("file_a", "")
    file_b   = args.get("file_b", "")
    text_a   = args.get("text_a", "")
    text_b   = args.get("text_b", "")
    context  = min(int(args.get("context_lines", 3)), 20)
    unified  = args.get("unified", True)

    # Resolver modo: ficheros o texto inline
    if file_a and file_b:
        pa, pb = Path(file_a).expanduser(), Path(file_b).expanduser()
        if not pa.exists():
            return f"Error: fichero no encontrado: {file_a}"
        if not pb.exists():
            return f"Error: fichero no encontrado: {file_b}"
        lines_a = pa.read_text(errors="replace").splitlines(keepends=True)
        lines_b = pb.read_text(errors="replace").splitlines(keepends=True)
        label_a, label_b = str(pa), str(pb)
    elif text_a or text_b:
        lines_a = [ln + "\n" for ln in text_a.splitlines()]
        lines_b = [ln + "\n" for ln in text_b.splitlines()]
        label_a, label_b = "texto_a", "texto_b"
    else:
        return "Error: proporciona (file_a + file_b) o (text_a + text_b)."

    if unified:
        diff = list(difflib.unified_diff(
            lines_a, lines_b, fromfile=label_a, tofile=label_b, n=context,
        ))
    else:
        diff = list(difflib.context_diff(
            lines_a, lines_b, fromfile=label_a, tofile=label_b, n=context,
        ))

    if not diff:
        return "Los ficheros/textos son idénticos."

    result = "".join(diff[:500])  # cap a 500 líneas de diff
    lines_shown = len(diff)
    suffix = f"\n... [{lines_shown - 500} líneas omitidas]" if lines_shown > 500 else ""
    return result + suffix


def _tool_code_compare(args: dict) -> str:
    """Compara dos secciones de código: por nombre de función/símbolo, por rango de líneas,
    o compara la misma función entre dos ficheros. Evita hacer múltiples grep_code + read_file
    para comparar código — lo hace en una sola llamada.
    """
    file_a      = args.get("file_a", "")
    file_b      = args.get("file_b", "")
    symbol      = args.get("symbol", "")      # función/símbolo a comparar
    line_a      = int(args.get("line_a", 0))  # línea de inicio en file_a
    line_b      = int(args.get("line_b", 0))  # línea de inicio en file_b
    num_lines   = min(int(args.get("num_lines", 60)), 300)
    context     = min(int(args.get("context_lines", 3)), 20)

    def _extract_block(path: str, sym: str, start_line: int) -> tuple[list[str], str]:
        """Extrae un bloque de código: por símbolo o por número de línea."""
        try:
            content = Path(path).read_text(errors="replace")
        except FileNotFoundError:
            return [], f"Error: {path} no encontrado"

        lines = content.splitlines(keepends=True)

        if sym:
            # Buscar la definición del símbolo
            patterns = [
                re.compile(rf'^[^\s].*\b{re.escape(sym)}\s*\(', re.M),
                re.compile(rf'#define\s+{re.escape(sym)}\b', re.M),
                re.compile(rf'typedef\s+.*\b{re.escape(sym)}\b', re.M),
                re.compile(rf'\b{re.escape(sym)}\s*[=({{]', re.M),
            ]
            found_line = None
            for pat in patterns:
                m = pat.search(content)
                if m:
                    found_line = content[:m.start()].count('\n')
                    break
            if found_line is None:
                return [], f"Símbolo '{sym}' no encontrado en {path}"
            start = found_line
        elif start_line > 0:
            start = start_line - 1
        else:
            start = 0

        block = lines[start:start + num_lines]
        label = f"{path}:{start+1}-{start+len(block)}"
        return block, label

    if not file_a:
        return "Error: 'file_a' es obligatorio."

    if not file_b:
        file_b = file_a  # comparar el mismo fichero en dos ubicaciones

    block_a, label_a = _extract_block(file_a, symbol, line_a)
    block_b, label_b = _extract_block(file_b, symbol, line_b)

    if isinstance(block_a, str) and block_a.startswith("Error"):
        return block_a
    if isinstance(block_b, str) and block_b.startswith("Error"):
        return block_b

    if not block_a and not block_b:
        return f"No se encontró '{symbol}' en ninguno de los ficheros."

    diff = list(difflib.unified_diff(
        block_a, block_b,
        fromfile=label_a, tofile=label_b,
        n=context,
    ))

    if not diff:
        return (
            f"Los bloques de '{symbol or 'código'}' son idénticos.\n"
            f"  {label_a}  ({len(block_a)} líneas)\n"
            f"  {label_b}  ({len(block_b)} líneas)"
        )

    result = "".join(diff[:400])
    if len(diff) > 400:
        result += f"\n... [{len(diff) - 400} líneas de diff omitidas]"
    return result


def _tool_grep_code(args: dict) -> str:
    """Busca un patrón regex en el código fuente con líneas de contexto.
    Usa ripgrep (rg) si está disponible — hasta 100× más rápido en proyectos grandes."""
    pattern               = args.get("pattern", "")
    directory             = args.get("directory", ".")
    extensions            = args.get("extensions", "py,js,ts,c,h,hpp,hxx,cpp,cc,cxx,rs,go,java,rb,sh,bash,md,json,yaml,yml,toml,xml,sql,html,css,lua,ini,cfg,conf")
    context               = min(int(args.get("context_lines", 2)), 20)
    max_matches           = min(int(args.get("max_matches", 50)), 200)
    ignore_case           = args.get("ignore_case", True)
    exclude_pattern       = args.get("exclude_pattern", "")   # como grep -v
    count_only            = args.get("count_only", False)
    files_with_matches    = args.get("files_with_matches", False)
    files_without_matches = args.get("files_without_matches", False)

    if not pattern:
        return "Error: 'pattern' requerido."

    root = Path(directory).expanduser().resolve()
    if not root.exists():
        return f"Error: directorio no encontrado: {directory}"

    # ── Intentar ripgrep primero (mucho más rápido en proyectos grandes) ──
    import shutil
    if shutil.which("rg"):
        exts_list = [e.lstrip(".").lower() for e in extensions.split(",") if e.strip()]
        cmd = ["rg", "--no-heading", "--color=never"]
        if count_only:
            cmd.append("--count")
        elif files_with_matches:
            cmd.append("--files-with-matches")
        elif files_without_matches:
            cmd.append("--files-without-match")
        else:
            cmd += ["--line-number", f"--context={context}", f"--max-count={max_matches}"]
        if ignore_case:
            cmd.append("--ignore-case")
        for ext in exts_list:
            cmd += ["--glob", f"*.{ext}"]
        cmd += ["--", pattern, str(root)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            out = r.stdout or ""
            if r.returncode not in (0, 1):  # 1 = sin resultados (normal)
                pass  # caer a Python
            elif out.strip():
                lines = out.splitlines()
                # Aplicar exclude_pattern como post-filtro (equivale a | grep -v)
                if exclude_pattern:
                    try:
                        excl_rx = re.compile(exclude_pattern, re.IGNORECASE if ignore_case else 0)
                        lines = [ln for ln in lines if not excl_rx.search(ln)]
                    except re.error:
                        pass
                if not lines:
                    return f"Sin resultados para '{pattern}' (excluido: '{exclude_pattern}') en {root}"
                if count_only:
                    total = sum(int(ln.split(":")[-1]) for ln in lines if ":" in ln and ln.split(":")[-1].isdigit())
                    excl_note = f" (excluido: '{exclude_pattern}')" if exclude_pattern else ""
                    header = f"# grep -c '{pattern}'{excl_note} en {root} — total {total} coincidencias (rg)\n\n"
                    return header + "\n".join(lines)
                elif files_with_matches:
                    excl_note = f" (excluido: '{exclude_pattern}')" if exclude_pattern else ""
                    header = f"# grep -l '{pattern}'{excl_note} en {root} — {len(lines)} ficheros (rg)\n\n"
                    return header + "\n".join(lines)
                elif files_without_matches:
                    header = f"# grep -L '{pattern}' en {root} — {len(lines)} ficheros sin coincidencia (rg)\n\n"
                    return header + "\n".join(lines)
                else:
                    n_matches = sum(1 for ln in lines if ":" in ln and not ln.startswith("--"))
                    excl_note = f" (excluido: '{exclude_pattern}')" if exclude_pattern else ""
                    header = f"# grep '{pattern}'{excl_note} en {root} — {n_matches}+ coincidencias (rg)\n\n"
                    if len(lines) > 500:
                        lines = lines[:500]
                        lines.append("\n... [recortado a 500 líneas; usa max_matches para ampliar]")
                    return header + "\n".join(lines)
            else:
                return f"Sin resultados para '{pattern}' en {root}"
        except Exception:
            pass  # ripgrep falló; caer a Python

    # ── Fallback Python ───────────────────────────────────────────────────────
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        return f"Error en regex: {exc}"
    excl_rx: re.Pattern | None = None
    if exclude_pattern:
        try:
            excl_rx = re.compile(exclude_pattern, flags)
        except re.error:
            pass

    exts   = {"." + e.lstrip(".").lower() for e in extensions.split(",")}
    _IGNORE = {".git", "__pycache__", "node_modules", ".venv", "venv",
               ".mypy_cache", "dist", "build", "target"}

    # Modos especiales: count_only, files_with_matches, files_without_matches
    if count_only:
        lines_out = []
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in exts:
                continue
            if any(p in f.parts for p in _IGNORE):
                continue
            try:
                content = f.read_text(errors="replace").splitlines()
            except Exception:
                continue
            count = sum(1 for ln in content if rx.search(ln) and not (excl_rx and excl_rx.search(ln)))
            if count:
                rel = str(f.relative_to(root) if f.is_relative_to(root) else f)
                lines_out.append(f"{rel}:{count}")
        if not lines_out:
            return f"Sin resultados para '{pattern}' en {root}"
        total = sum(int(l.split(":")[-1]) for l in lines_out)
        header = f"# grep -c '{pattern}' en {root} — total {total} coincidencias\n\n"
        return header + "\n".join(lines_out)

    if files_with_matches or files_without_matches:
        matched_files = []
        all_files = []
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in exts:
                continue
            if any(p in f.parts for p in _IGNORE):
                continue
            rel = str(f.relative_to(root) if f.is_relative_to(root) else f)
            all_files.append(rel)
            try:
                content_lines = f.read_text(errors="replace").splitlines()
            except Exception:
                continue
            hits = [ln for ln in content_lines if rx.search(ln) and not (excl_rx and excl_rx.search(ln))]
            if hits:
                matched_files.append(rel)
        if files_with_matches:
            if not matched_files:
                return f"Sin ficheros con '{pattern}' en {root}"
            header = f"# grep -l '{pattern}' en {root} — {len(matched_files)} ficheros\n\n"
            return header + "\n".join(matched_files)
        else:  # files_without_matches
            without = [f for f in all_files if f not in set(matched_files)]
            if not without:
                return f"Todos los ficheros contienen '{pattern}' en {root}"
            header = f"# grep -L '{pattern}' en {root} — {len(without)} ficheros sin coincidencia\n\n"
            return header + "\n".join(without)

    results = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in exts:
            continue
        if any(p in f.parts for p in _IGNORE):
            continue
        try:
            lines = f.read_text(errors="replace").splitlines()
        except Exception:
            continue
        rel = str(f.relative_to(root) if f.is_relative_to(root) else f)
        for i, line in enumerate(lines):
            if rx.search(line) and not (excl_rx and excl_rx.search(line)):
                start = max(0, i - context)
                end   = min(len(lines), i + context + 1)
                block = []
                for j in range(start, end):
                    marker = "→" if j == i else " "
                    block.append(f"  {j+1:4d}{marker} {lines[j]}")
                results.append(f"{rel}:{i+1}\n" + "\n".join(block))
                if len(results) >= max_matches:
                    break
        if len(results) >= max_matches:
            break

    if not results:
        excl_note = f" (excluido: '{exclude_pattern}')" if exclude_pattern else ""
        return f"Sin resultados para '{pattern}'{excl_note} en {root}"

    excl_note = f" (excluido: '{exclude_pattern}')" if exclude_pattern else ""
    header = f"# grep '{pattern}'{excl_note} en {root} — {len(results)} coincidencias\n\n"
    suffix = f"\n\n... [limitado a {max_matches} resultados]" if len(results) >= max_matches else ""
    return header + "\n\n".join(results) + suffix


def _tool_multi_grep(args: dict) -> str:
    """Busca múltiples patrones a la vez en el código fuente — equivale a hacer N llamadas a grep_code."""
    patterns    = args.get("patterns", [])
    directory   = args.get("directory", ".")
    extensions  = args.get("extensions", "py,js,ts,c,h,hpp,cpp,rs,go,java,rb,sh,md,json,yaml,toml")
    context     = min(int(args.get("context_lines", 2)), 10)
    max_per_pat = min(int(args.get("max_per_pattern", 20)), 100)
    ignore_case = args.get("ignore_case", True)

    if not patterns:
        return "Error: 'patterns' debe ser una lista de patrones a buscar."
    if isinstance(patterns, str):
        patterns = [p.strip() for p in patterns.split(",") if p.strip()]

    results_parts = []
    for pat in patterns[:10]:  # máximo 10 patrones por llamada
        r = _tool_grep_code({
            "pattern": pat,
            "directory": directory,
            "extensions": extensions,
            "context_lines": context,
            "max_matches": max_per_pat,
            "ignore_case": ignore_case,
        })
        results_parts.append(f"### Patrón: `{pat}`\n{r}")

    return "\n\n" + "\n\n".join(results_parts)


def _tool_affected_files(args: dict) -> str:
    """Devuelve todos los ficheros que referencian un símbolo (función, clase, variable, macro).
    Ideal para saber qué hay que actualizar antes de renombrar o cambiar una interfaz."""
    symbol        = args.get("symbol", "").strip()
    directory     = args.get("directory", ".")
    extensions    = args.get("extensions", "py,js,ts,jsx,tsx,c,h,cpp,cc,cxx,hpp,hxx,go,rs,java,rb,sh,md")
    exclude_tests = args.get("exclude_tests", False)
    whole_word    = args.get("whole_word", True)
    max_files     = min(int(args.get("max_files", 40)), 100)

    if not symbol:
        return "Error: 'symbol' es obligatorio."

    root = Path(directory).expanduser().resolve()
    if not root.exists():
        return f"Error: directorio no encontrado: {directory}"

    import shutil as _sh, os as _os
    exts = [e.strip().lstrip(".") for e in extensions.split(",") if e.strip()]

    # ── Construir comando ──────────────────────────────────────────────────────
    if _sh.which("rg"):
        cmd = ["rg", "--no-heading", "--line-number", "--color=never",
               "--max-count=50", "--ignore-case"]
        if whole_word:
            cmd.append("--word-regexp")
        for ext in exts:
            cmd += ["--glob", f"*.{ext}"]
        if exclude_tests:
            for pat in ("!test_*.py", "!*_test.py", "!*.test.*", "!*.spec.*"):
                cmd += ["--glob", pat]
            cmd += ["--glob", "!tests/**", "--glob", "!test/**", "--glob", "!__tests__/**"]
        cmd += ["--", symbol, str(root)]
    elif _sh.which("grep"):
        cmd = ["grep", "-rn", "--color=never"]
        if whole_word:
            cmd.append("--word-regexp")
        cmd.append("--ignore-case")
        ext_globs: list[str] = []
        for ext in exts:
            ext_globs += ["--include", f"*.{ext}"]
        cmd += ext_globs
        cmd += [symbol, str(root)]
    else:
        return "Error: ni rg ni grep están disponibles."

    # ── Ejecutar ───────────────────────────────────────────────────────────────
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode not in (0, 1):
            return f"Error ejecutando búsqueda: {proc.stderr.strip()[:300]}"
        raw = proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return "Timeout: la búsqueda tardó más de 30s. Afina el directorio o las extensiones."
    except Exception as exc:
        return f"Error: {exc}"

    if not raw:
        suffix = " (whole-word)" if whole_word else ""
        return f"Ningún fichero referencia '{symbol}'{suffix} en {root}"

    # ── Parsear y agrupar por fichero ─────────────────────────────────────────
    files: dict[str, list[tuple[int, str]]] = {}
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        fpath, lineno_s, text = parts[0], parts[1], parts[2]
        try:
            lno = int(lineno_s)
        except ValueError:
            continue
        files.setdefault(fpath, []).append((lno, text.strip()))

    if not files:
        return f"Ningún fichero referencia '{symbol}' en {root}"

    total_refs = sum(len(v) for v in files.values())
    sorted_files = sorted(files.items(), key=lambda x: len(x[1]), reverse=True)

    # ── Formatear salida ───────────────────────────────────────────────────────
    word_note = "" if whole_word else " (parcial)"
    lines_out = [
        f"# affected_files: '{symbol}'{word_note}",
        f"# {len(files)} fichero(s) — {total_refs} referencia(s) total",
        "",
    ]
    for fpath, matches in sorted_files[:max_files]:
        try:
            rel = _os.path.relpath(fpath, str(root))
        except ValueError:
            rel = fpath
        n = len(matches)
        lines_out.append(f"{'─'*50}")
        lines_out.append(f"{rel}  ({n} ref{'s' if n != 1 else ''})")
        for lno, text in matches[:8]:
            lines_out.append(f"  {lno:5d}│ {text[:120]}")
        if n > 8:
            lines_out.append(f"       … +{n - 8} más en este fichero")

    if len(files) > max_files:
        lines_out.append(f"\n… y {len(files) - max_files} fichero(s) más (aumenta max_files)")

    return "\n".join(lines_out)


def _docstring_first_line(node) -> str:
    """Devuelve la primera línea no vacía del docstring del nodo, o ''."""
    import ast as _ast
    doc = _ast.get_docstring(node, clean=True)
    if not doc:
        return ""
    for line in doc.splitlines():
        line = line.strip()
        if line:
            return line[:90]
    return ""


def _outline_python(path: str, text: str, n_lines: int,
                    with_docstrings: bool = False) -> str:
    """Genera el outline de un fichero .py usando ast.parse."""
    import ast as _ast
    from pathlib import Path as _P
    try:
        tree = _ast.parse(text, filename=path)
    except SyntaxError as _e:
        return f"# code_outline: {_P(path).name}  ({n_lines} líneas)\n# SyntaxError: {_e}"

    def _doc_suffix(node) -> str:
        if not with_docstrings:
            return ""
        first = _docstring_first_line(node)
        return f"  — {first}" if first else ""

    out = [f"# code_outline: {_P(path).name}  ({n_lines} líneas)\n"]
    # Top-level constants (UPPER_CASE) y TYPE_VAR
    for node in _ast.iter_child_nodes(tree):
        if isinstance(node, (_ast.Assign, _ast.AnnAssign)):
            targets = (
                node.targets if isinstance(node, _ast.Assign) else [node.target]
            )
            for t in targets:
                if isinstance(t, _ast.Name) and (t.id.isupper() or t.id.startswith("_")):
                    out.append(f"L{node.lineno:<6d} {t.id}")
            continue
        if isinstance(node, _ast.ClassDef):
            bases = ", ".join(
                getattr(b, "id", getattr(b, "attr", "?")) for b in node.bases
            )
            header = f"class {node.name}" + (f"({bases})" if bases else ":")
            out.append(f"\nL{node.lineno:<6d} {header}{_doc_suffix(node)}")
            for child in _ast.iter_child_nodes(node):
                if isinstance(child, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(child, _ast.AsyncFunctionDef) else "def"
                    _args = child.args.args
                    extra = [a.arg for a in _args[1:3]] if len(_args) > 1 else []
                    hint = f"({', '.join(extra)}…)" if extra else "()"
                    out.append(f"  L{child.lineno:<6d} {prefix} {child.name}{hint}{_doc_suffix(child)}")
        elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, _ast.AsyncFunctionDef) else "def"
            out.append(f"\nL{node.lineno:<6d} {prefix} {node.name}{_doc_suffix(node)}")
    return "\n".join(out)


def _outline_ctags(path: str, text: str, n_lines: int) -> str:
    """Genera el outline usando universal-ctags (para lenguajes no-Python)."""
    import subprocess as _sp
    from pathlib import Path as _P
    try:
        proc = _sp.run(
            ["ctags", "-x", "--sort=no", path],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            out = [f"# code_outline: {_P(path).name}  ({n_lines} líneas)\n"]
            seen: set[str] = set()
            for line in proc.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    name, kind, lineno = parts[0], parts[1], parts[2]
                    key = f"{lineno}:{name}"
                    if key not in seen:
                        seen.add(key)
                        out.append(f"L{lineno:<6s} {kind:<12s} {name}")
            return "\n".join(out)
    except (FileNotFoundError, _sp.TimeoutExpired):
        pass
    return _outline_regex(path, text, n_lines)


def _outline_regex(path: str, text: str, n_lines: int) -> str:
    """Fallback: outline por regex para cuando ctags no está disponible."""
    import re as _re
    from pathlib import Path as _P
    _PATS = [
        _re.compile(r'^\s*(class\s+\w[\w\d_]*)'),
        _re.compile(r'^\s*((?:async\s+)?def\s+\w[\w\d_]*)'),
        _re.compile(r'^\s*((?:export\s+)?(?:async\s+)?function\s+\w[\w\d_]*)'),
        _re.compile(r'^\s*(func\s+\w[\w\d_]*)'),           # Go
        _re.compile(r'^\s*((?:pub\s+)?fn\s+\w[\w\d_]*)'),  # Rust
        _re.compile(r'^\s*((?:public\s+)?(?:static\s+)?(?:class|interface|enum)\s+\w[\w\d_]*)'),
    ]
    out = [f"# code_outline: {_P(path).name}  ({n_lines} líneas)\n"]
    for i, line in enumerate(text.splitlines(), 1):
        for pat in _PATS:
            m = pat.match(line)
            if m:
                out.append(f"L{i:<6d} {m.group(1)[:80]}")
                break
    return "\n".join(out)


def _tool_code_outline(args: dict) -> str:
    """Devuelve la estructura de un fichero: clases, funciones y sus líneas.

    Para .py usa ast.parse (preciso, sin dependencias).
    Para otros lenguajes usa ctags y cae a regex como fallback.
    """
    path = (args.get("path") or args.get("file_path") or "").strip()
    min_lines = int(args.get("min_lines", 0))

    from pathlib import Path as _P
    p = _P(path)
    if not path:
        return "Error: parámetro 'path' obligatorio."
    if not p.exists():
        return f"Error: {path} no encontrado."
    if p.is_dir():
        return f"Error: {path} es un directorio — pasa un fichero."

    try:
        text = p.read_text(errors="replace")
    except Exception as _e:
        return f"Error leyendo {path}: {_e}"

    n_lines = len(text.splitlines())
    if min_lines > 0 and n_lines < min_lines:
        return (
            f"# code_outline: {p.name}  ({n_lines} líneas)\n"
            f"# Fichero < {min_lines} líneas — usa read_file directamente."
        )

    with_docstrings = bool(args.get("with_docstrings", False))

    ext = p.suffix.lower()
    if ext == ".py":
        return _outline_python(str(p), text, n_lines, with_docstrings=with_docstrings)
    return _outline_ctags(str(p), text, n_lines)


def _read_sections_python(path: str, text: str, sections: list) -> str:
    """Extract named functions/classes/methods from Python source using ast."""
    import ast as _ast
    from pathlib import Path as _P

    try:
        tree = _ast.parse(text, filename=path)
    except SyntaxError as _e:
        return f"SyntaxError en {path}: {_e}"

    lines = text.splitlines(keepends=True)
    name = _P(path).name

    # index: simple_name → [(qualified_name, node)]
    # also index: "ClassName.method" for qualified lookups
    index: dict = {}

    def _add(qname: str, node) -> None:
        index.setdefault(qname, []).append((qname, node))

    for node in _ast.walk(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            _add(node.name, node)

    for node in _ast.walk(tree):
        if isinstance(node, _ast.ClassDef):
            for child in node.body:
                if isinstance(child, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    _add(f"{node.name}.{child.name}", child)

    results = []
    not_found = []

    for section in sections:
        matches = index.get(section)
        if not matches:
            not_found.append(section)
            continue
        for qname, node in matches:
            # Include decorator lines
            start = node.lineno
            if getattr(node, "decorator_list", None):
                start = node.decorator_list[0].lineno
            end = node.end_lineno  # type: ignore[attr-defined]
            src = "".join(lines[start - 1 : end]).rstrip()
            results.append(f"## {qname}  ({name}:{start}–{end})\n\n{src}")

    if not results and not_found:
        return f"No se encontraron secciones: {', '.join(not_found)} en {path}"

    out = "\n\n".join(results)
    if not_found:
        out += f"\n\n# No encontrado: {', '.join(not_found)}"
    return out


def _read_sections_other(path: str, text: str, sections: list) -> str:
    """Extract named functions/classes from non-Python source using ctags."""
    import subprocess, shutil
    from pathlib import Path as _P

    name = _P(path).name
    lines = text.splitlines(keepends=True)
    n = len(lines)

    # Build start-line index via ctags
    start_map: dict = {}  # symbol → list of int (1-based)
    if shutil.which("ctags"):
        try:
            out = subprocess.check_output(
                ["ctags", "-x", "--sort=no", path],
                stderr=subprocess.DEVNULL, text=True, timeout=10,
            )
            for raw in out.splitlines():
                parts = raw.split()
                if len(parts) >= 3:
                    sym, _kind, lineno_s = parts[0], parts[1], parts[2]
                    try:
                        start_map.setdefault(sym, []).append(int(lineno_s))
                    except ValueError:
                        pass
        except Exception:
            pass

    # Collect all start lines sorted to compute end via next symbol
    all_starts = sorted({ln for lns in start_map.values() for ln in lns})

    def _end_of(start: int) -> int:
        idx = all_starts.index(start) if start in all_starts else -1
        if idx >= 0 and idx + 1 < len(all_starts):
            return all_starts[idx + 1] - 1
        return min(start + 80, n)

    results = []
    not_found = []

    for section in sections:
        starts = start_map.get(section)
        if not starts:
            not_found.append(section)
            continue
        for start in starts:
            end = _end_of(start)
            src = "".join(lines[start - 1 : end]).rstrip()
            results.append(f"## {section}  ({name}:{start}–{end})\n\n{src}")

    if not results and not_found:
        return f"No se encontraron secciones: {', '.join(not_found)} en {path}"

    out = "\n\n".join(results)
    if not_found:
        out += f"\n\n# No encontrado: {', '.join(not_found)}"
    return out


def _tool_read_sections(args: dict) -> str:
    """Lee las secciones (funciones/clases/métodos) indicadas de un fichero."""
    from pathlib import Path as _P

    path = (args.get("path") or args.get("file_path") or "").strip()
    sections_raw = args.get("sections") or args.get("names") or []
    if isinstance(sections_raw, str):
        sections_raw = [s.strip() for s in sections_raw.split(",") if s.strip()]
    sections = [str(s).strip() for s in sections_raw if str(s).strip()]

    if not path:
        return "Error: parámetro 'path' obligatorio."
    if not sections:
        return "Error: parámetro 'sections' obligatorio — lista de nombres de función/clase."

    p = _P(path)
    if not p.exists():
        return f"Error: {path} no encontrado."
    if p.is_dir():
        return f"Error: {path} es un directorio."

    try:
        text = p.read_text(errors="replace")
    except Exception as _e:
        return f"Error leyendo {path}: {_e}"

    if p.suffix.lower() == ".py":
        return _read_sections_python(str(p), text, sections)
    return _read_sections_other(str(p), text, sections)


def _tool_symbol_lookup(args: dict) -> str:
    """Busca la definición de un símbolo (función, macro, typedef, variable) probando
    múltiples estrategias automáticamente al nivel del agente Python — sin consumir
    tokens del LLM en cada intento fallido.

    Útil cuando grep_code devuelve 'Sin resultados' repetidamente con variantes del mismo nombre.
    """
    symbol      = args.get("symbol", "").strip()
    directory   = args.get("directory", ".")
    extensions  = args.get("extensions", "")
    context     = min(int(args.get("context_lines", 3)), 10)
    max_matches = min(int(args.get("max_matches", 10)), 50)

    if not symbol:
        return "Error: 'symbol' es obligatorio."

    sym_esc = re.escape(symbol)

    # Extensiones automáticas según contexto
    if not extensions:
        # Si el directorio contiene .c/.h se asume C/C++, si no Python
        try:
            sample = list(Path(directory).rglob("*.c"))[:1]
            extensions = "c,h,cpp,hpp,hxx,cxx,cc" if sample else "py,js,ts"
        except Exception:
            extensions = "c,h,py,js,ts,rs,go"

    # Estrategias de búsqueda en orden de especificidad
    strategies: list[tuple[str, str]] = [
        # C/C++ macros y typedefs
        (f"#define\\s+{sym_esc}\\b",          "macro #define"),
        (f"typedef\\s+.*\\b{sym_esc}\\b",     "typedef"),
        (f"#define\\s+{sym_esc.upper()}\\b",  "macro #define (mayúsculas)"),
        (f"typedef\\s+.*\\b{sym_esc.upper()}\\b", "typedef (mayúsculas)"),
        # Definición de función/estructura
        (f"\\b{sym_esc}\\s*\\(",              "función/macro con paréntesis"),
        (f"^\\s*{sym_esc}\\s*[=({{]",         "asignación/apertura"),
        # Nombre exacto como palabra entera
        (f"\\b{sym_esc}\\b",                  "palabra exacta"),
        # Nombre sin distinguir mayúsculas (último recurso)
        (f"{sym_esc}",                         "substring"),
    ]

    tried: list[str] = []
    for pattern, label in strategies:
        try:
            result = _tool_grep_code({
                "pattern":       pattern,
                "directory":     directory,
                "extensions":    extensions,
                "context_lines": context,
                "max_matches":   max_matches,
                "ignore_case":   False,  # primero sin ignorar case para ser más preciso
            })
        except Exception as exc:
            result = f"error: {exc}"

        tried.append(f"'{pattern}' ({label})")

        if "Sin resultados" not in result and result.strip():
            n = len(tried)
            return (
                f"[symbol_lookup: encontrado con estrategia {n}/{len(strategies)}: {label}]\n"
                f"Patrón usado: {pattern}\n\n{result}"
            )

    # Segunda pasada: ignorar mayúsculas para los 3 más relevantes
    for pattern, label in strategies[:4]:
        try:
            result = _tool_grep_code({
                "pattern":       pattern,
                "directory":     directory,
                "extensions":    extensions,
                "context_lines": context,
                "max_matches":   max_matches,
                "ignore_case":   True,
            })
        except Exception:
            continue

        tried.append(f"'{pattern}' ({label}, ignore_case)")

        if "Sin resultados" not in result and result.strip():
            n = len(tried)
            return (
                f"[symbol_lookup: encontrado con estrategia {n} (ignore_case): {label}]\n"
                f"Patrón: {pattern}\n\n{result}"
            )

    return (
        f"No se encontró '{symbol}' tras {len(tried)} estrategias en {directory}.\n"
        f"Probado: {tried[:6]}.\n"
        "Sugerencias:\n"
        f"• Lee directamente el fichero principal: read_file(path, limit=100)\n"
        f"• Verifica el nombre exacto: puede ser '{symbol.lower()}' o '{symbol.upper()}'\n"
        f"• El símbolo puede estar en un fichero de extensión diferente"
    )


def _tool_env_check(args: dict) -> str:
    """Muestra variables de entorno relevantes para desarrollo, ocultando secretos."""
    prefix_filter = args.get("prefix", "")  # filtro opcional, ej. "PYTHONPATH"
    show_all      = args.get("show_all", False)

    # Patrones de secretos que NO se muestran nunca
    _SECRET_PATTERNS = re.compile(
        r'(password|passwd|secret|token|key|api_key|auth|credential|private|'
        r'access_key|client_secret|client_id|oauth|bearer|jwt|cookie)',
        re.IGNORECASE,
    )
    # Variables de desarrollo que SÍ interesan
    _DEV_PREFIXES = (
        "PATH", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
        "VIRTUAL_ENV", "CONDA_", "POETRY_", "NODE_", "NPM_", "YARN_",
        "HOME", "USER", "SHELL", "LANG", "LC_", "TERM", "COLORTERM",
        "EDITOR", "VISUAL", "GIT_", "CARGO_", "GOPATH", "GOROOT",
        "JAVA_HOME", "OLLAMA_", "OOCODE_", "DOCKER_", "COMPOSE_",
        "DATABASE_URL", "REDIS_URL", "PORT", "HOST", "DEBUG",
        "LOG_LEVEL", "ENV", "APP_ENV", "NODE_ENV", "FLASK_", "DJANGO_",
        "FASTAPI_", "UVICORN_", "GUNICORN_",
    )

    env = dict(os.environ)
    lines = []

    for k, v in sorted(env.items()):
        # Filtro por prefijo solicitado
        if prefix_filter and not k.upper().startswith(prefix_filter.upper()):
            continue
        # Ocultar secretos siempre
        if _SECRET_PATTERNS.search(k):
            lines.append(f"  {k} = *** (oculto)")
            continue
        # Si show_all, mostrar todo; si no, filtrar por prefijos de desarrollo
        if not show_all and not any(k.upper().startswith(p) for p in _DEV_PREFIXES):
            continue
        # Truncar valores largos
        display = v if len(v) <= 120 else v[:117] + "..."
        lines.append(f"  {k} = {display}")

    if not lines:
        return f"No se encontraron variables de entorno{'con prefijo ' + prefix_filter if prefix_filter else ' de desarrollo'}."

    header = f"Variables de entorno de desarrollo ({len(lines)} entradas)"
    if prefix_filter:
        header += f" — filtro: {prefix_filter}"
    return header + ":\n\n" + "\n".join(lines)


def _tool_json_format(args: dict) -> str:
    """Valida, formatea y consulta JSON. Permite extraer sub-objetos con path simple."""
    text    = args.get("text", "")
    path    = args.get("path", "")   # ej. "data.items.0.name"
    compact = args.get("compact", False)
    indent  = min(int(args.get("indent", 2)), 8)

    if not text:
        return "Error: 'text' requerido (contenido JSON)."

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # Intentar dar ubicación del error
        lines = text.splitlines()
        ctx   = []
        if hasattr(exc, "lineno") and exc.lineno:
            start = max(0, exc.lineno - 2)
            for i, ln in enumerate(lines[start:exc.lineno + 1], start + 1):
                marker = "→ " if i == exc.lineno else "  "
                ctx.append(f"{marker}{i:4d}  {ln}")
        ctx_str = "\n" + "\n".join(ctx) if ctx else ""
        return f"JSON inválido en línea {getattr(exc, 'lineno', '?')}: {exc.msg}{ctx_str}"

    # Navegar por path si se especifica
    if path:
        current = data
        for segment in path.split("."):
            try:
                if isinstance(current, list):
                    current = current[int(segment)]
                elif isinstance(current, dict):
                    current = current[segment]
                else:
                    return f"Error: no se puede navegar a '{segment}' desde {type(current).__name__}"
            except (KeyError, IndexError, ValueError) as exc:
                return f"Error navegando path '{path}' en segmento '{segment}': {exc}"
        data = current

    # Serializar resultado
    if compact:
        out = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    else:
        out = json.dumps(data, indent=indent, ensure_ascii=False)

    # Info de tipo/tamaño
    type_name = type(data).__name__
    if isinstance(data, (list, dict)):
        size_info = f" — {len(data)} {'elementos' if isinstance(data, list) else 'claves'}"
    else:
        size_info = ""

    header = f"JSON válido ({type_name}{size_info})"
    if path:
        header += f" — path: {path}"
    return f"{header}\n\n{out[:6000]}"


def _tool_hash_text(args: dict) -> str:
    """Calcula hashes MD5/SHA1/SHA256/SHA512 de texto o de un fichero."""
    text      = args.get("text", "")
    file_path = args.get("file_path", "")
    algorithm = args.get("algorithm", "sha256")  # md5|sha1|sha256|sha512|all

    _ALGOS = {"md5": hashlib.md5, "sha1": hashlib.sha1,
              "sha256": hashlib.sha256, "sha512": hashlib.sha512}

    if not text and not file_path:
        return "Error: proporciona 'text' o 'file_path'."

    if file_path:
        p = Path(file_path).expanduser()
        if not p.exists():
            return f"Error: fichero no encontrado: {file_path}"
        try:
            data = p.read_bytes()
            source_desc = f"fichero: {p} ({len(data):,} bytes)"
        except Exception as exc:
            return f"Error leyendo {file_path}: {exc}"
    else:
        data        = text.encode("utf-8")
        source_desc = f"texto: {repr(text[:60])}{'...' if len(text) > 60 else ''}"

    lines = [f"Hash de {source_desc}\n"]
    if algorithm == "all":
        for name, fn in _ALGOS.items():
            lines.append(f"  {name.upper():8s}  {fn(data).hexdigest()}")
    else:
        fn = _ALGOS.get(algorithm.lower())
        if fn is None:
            return f"Error: algoritmo desconocido '{algorithm}'. Usa: md5, sha1, sha256, sha512, all."
        lines.append(f"  {algorithm.upper():8s}  {fn(data).hexdigest()}")

    return "\n".join(lines)


# ── Tools v4 — write_file mejorado + git completo ────────────────────────────

def _tool_write_file(args: dict) -> str:
    """Escribe o sobreescribe un fichero; incluye diff unificado en la respuesta."""
    file_path = args.get("file_path", "")
    content   = args.get("content", "")
    append    = args.get("append", False)
    mkdir_p   = args.get("mkdir", True)

    if not file_path:
        return "Error: 'file_path' requerido."

    p = Path(file_path).expanduser()
    try:
        resolved = p.resolve()
        home = Path.home().resolve()
        cwd  = Path.cwd().resolve()
        blocked = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/boot", "/proc", "/sys", "/dev")
        if any(str(resolved).startswith(b) for b in blocked):
            return f"Error: ruta bloqueada por seguridad: {resolved}"
        if not (str(resolved).startswith(str(home)) or str(resolved).startswith(str(cwd))):
            return f"Error: solo se permiten rutas dentro del home o del directorio de trabajo.\nRuta: {resolved}"
    except Exception as exc:
        return f"Error resolviendo ruta: {exc}"

    old_content = ""
    if resolved.exists() and resolved.is_file():
        try:
            old_content = resolved.read_text(errors="replace")
        except Exception:
            pass

    if mkdir_p and not resolved.parent.exists():
        resolved.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"
    try:
        with open(resolved, mode, encoding="utf-8") as f:
            f.write(content)
    except Exception as exc:
        return f"Error escribiendo {resolved}: {exc}"

    new_content = old_content + content if append else content
    action = "Contenido añadido" if append else "Fichero escrito"
    n_lines = new_content.count("\n") + 1
    size    = resolved.stat().st_size
    result  = f"{action}: {resolved}\n{size:,} bytes, {n_lines} líneas."

    # Solo incluir diff si el fichero existía antes (ficheros nuevos no necesitan diff)
    if old_content:
        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{resolved.name}",
            tofile=f"b/{resolved.name}",
            n=2,
        ))
        if diff_lines:
            # Cap inteligente: 80 líneas para ficheros pequeños, menos si el fichero es grande
            cap = 60 if n_lines > 500 else 80
            diff_text = "".join(diff_lines[:cap])
            result += f"\n\n```diff\n{diff_text}```"
            if len(diff_lines) > cap:
                result += f"\n... ({len(diff_lines) - cap} líneas más en el diff)"
    else:
        # Fichero nuevo: mostrar las primeras líneas como contexto
        preview = new_content.splitlines()[:10]
        if preview:
            result += "\n\n```\n" + "\n".join(preview)
            if n_lines > 10:
                result += f"\n... ({n_lines - 10} líneas más)"
            result += "\n```"

    return result


# ── Git tools ─────────────────────────────────────────────────────────────────

def _git_run(args_list: list[str], cwd: str | None = None, timeout: int = 60) -> str:
    wd = cwd or os.getcwd()
    try:
        proc = subprocess.Popen(
            ["git"] + args_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=wd,
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                import signal as _sig
                os.killpg(os.getpgid(proc.pid), _sig.SIGKILL)
            except Exception:
                proc.kill()
            proc.communicate()
            return f"Error: git {args_list[0]} superó el timeout de {timeout}s."
        combined = (out or "") + (err or "")
        if proc.returncode != 0 and not combined.strip():
            combined = f"(git {args_list[0]} terminó con código {proc.returncode})"
        return combined.strip()
    except FileNotFoundError:
        return "Error: git no está instalado o no está en el PATH."
    except Exception as e:
        return f"Error ejecutando git {args_list[0]}: {e}"


def _tool_git_status(args: dict) -> str:
    cwd = args.get("path") or None
    branch = _git_run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    status = _git_run(["status", "--short"], cwd=cwd)
    ahead_behind = _git_run(["rev-list", "--left-right", "--count", "@{upstream}...HEAD"], cwd=cwd)
    result = f"Rama: {branch}\n"
    if "no upstream" in ahead_behind.lower() or "fatal" in ahead_behind.lower():
        result += "(sin upstream configurado)\n"
    else:
        parts = ahead_behind.split()
        if len(parts) == 2:
            behind, ahead = parts
            result += f"↑{ahead} commits por subir  ↓{behind} commits por bajar\n"
    result += "\n" + (status if status else "(árbol limpio, sin cambios)")
    return result


def _tool_git_diff(args: dict) -> str:
    path   = args.get("path") or None
    staged = args.get("staged", False)
    ref    = args.get("ref", "")
    files  = args.get("files", "")
    git_args = ["diff"]
    if staged:
        git_args.append("--staged")
    if ref:
        git_args.append(ref)
    if files:
        git_args += ["--"] + files.split()
    result = _git_run(git_args, cwd=path)
    if not result:
        return "(sin diferencias)" if not staged else "(sin cambios en staging)"
    lines = result.splitlines()
    if len(lines) > 500:
        result = "\n".join(lines[:500]) + f"\n\n... ({len(lines)-500} líneas omitidas)"
    return result


def _tool_git_log(args: dict) -> str:
    path      = args.get("path") or None
    n         = min(int(args.get("n", 15)), 100)
    fmt       = args.get("format", "medium")
    since     = args.get("since", "")
    file_path = args.get("file_path", "")
    show_diff = args.get("show_diff", False)

    fmt_map = {
        "oneline": "%h %s (%an, %ar)",
        "short":   "%h %s\n   %an <%ae>  %ar",
        "medium":  "%h %s\n   %an  %ad\n   %b",
    }
    git_args = ["log", f"-{n}"]
    if fmt in fmt_map:
        git_args += [f"--pretty=format:{fmt_map[fmt]}"]
    git_args += ["--graph", "--decorate"]
    if since:
        git_args += [f"--since={since}"]
    if file_path:
        git_args += ["--", file_path]

    result = _git_run(git_args, cwd=path) or "(sin historial)"

    if show_diff and file_path:
        sha = _git_run(["log", "-1", "--pretty=format:%H", "--", file_path], cwd=path).strip()
        if sha:
            diff = _git_run(["show", "--stat", "--unified=3", sha, "--", file_path], cwd=path)
            result += f"\n\n## Diff del último commit ({sha[:8]})\n\n{diff[:3000]}"

    return result


def _tool_git_add(args: dict) -> str:
    files = args.get("files", ".")
    path  = args.get("path") or None
    _git_run(["add"] + files.split(), cwd=path)
    status = _git_run(["status", "--short"], cwd=path)
    return f"Staged:\n{status}" if status else "Archivos añadidos al staging."


def _tool_git_commit(args: dict) -> str:
    message = args.get("message", "")
    path    = args.get("path") or None
    all_    = args.get("all", False)
    if not message:
        return "Error: 'message' requerido."
    git_args = ["commit"]
    if all_:
        git_args.append("-a")
    git_args += ["-m", message]
    return _git_run(git_args, cwd=path)


def _tool_git_push(args: dict) -> str:
    remote = args.get("remote", "origin")
    branch = args.get("branch", "")
    path   = args.get("path") or None
    force  = args.get("force", False)
    git_args = ["push", remote]
    if branch:
        git_args.append(branch)
    if force:
        git_args.append("--force-with-lease")
    return _git_run(git_args, cwd=path, timeout=120)


def _tool_git_pull(args: dict) -> str:
    remote = args.get("remote", "origin")
    branch = args.get("branch", "")
    path   = args.get("path") or None
    git_args = ["pull", remote]
    if branch:
        git_args.append(branch)
    return _git_run(git_args, cwd=path, timeout=120)


def _tool_git_branch(args: dict) -> str:
    action = args.get("action", "list")
    name   = args.get("name", "")
    path   = args.get("path") or None
    if action == "list":
        return _git_run(["branch", "-avv"], cwd=path) or "(sin ramas)"
    elif action == "create":
        return _git_run(["checkout", "-b", name], cwd=path)
    elif action == "checkout":
        return _git_run(["checkout", name], cwd=path)
    elif action == "delete":
        return _git_run(["branch", "-d", name], cwd=path)
    elif action == "rename":
        parts = name.split()
        if len(parts) != 2:
            return "Para rename, proporciona 'nombre_antiguo nombre_nuevo' en el campo name."
        return _git_run(["branch", "-m", parts[0], parts[1]], cwd=path)
    return f"Acción desconocida: {action}. Usa list, create, checkout, delete o rename."


def _tool_git_stash(args: dict) -> str:
    action     = args.get("action", "list")
    name       = args.get("name", "")
    path       = args.get("path") or None
    diff_index = int(args.get("diff_index", -1))

    if action == "push":
        git_args = ["stash", "push"]
        if name:
            git_args += ["-m", name]
        return _git_run(git_args, cwd=path)
    elif action == "pop":
        return _git_run(["stash", "pop"], cwd=path)
    elif action == "list":
        out = _git_run(["stash", "list", "--format=%gd|%ci|%gs"], cwd=path)
        if not out:
            return "(stash vacío)"
        lines = ["Stashes:\n"]
        for entry in out.splitlines():
            parts_s = entry.split("|", 2)
            if len(parts_s) == 3:
                ref, date, msg = parts_s
                lines.append(f"  {ref:<12}  {date[:10]}  {msg}")
            else:
                lines.append(f"  {entry}")
        if diff_index >= 0:
            diff = _git_run(["stash", "show", "-p", f"stash@{{{diff_index}}}"], cwd=path)
            lines.append(f"\n## Diff stash@{{{diff_index}}}\n\n{diff[:3000]}")
        return "\n".join(lines)
    elif action == "drop":
        ref = name or "stash@{0}"
        return _git_run(["stash", "drop", ref], cwd=path)
    return f"Acción desconocida: {action}. Usa push, pop, list o drop."


def _tool_git_patch(args: dict) -> str:
    action        = args.get("action", "create")
    files         = args.get("files", "")
    path          = args.get("path") or None
    patch_content = args.get("patch_content", "")
    since_commit  = args.get("since_commit", "HEAD~1")

    if action == "create":
        git_args = ["diff"]
        if files:
            git_args += ["--"] + files.split()
        return _git_run(git_args, cwd=path) or "(sin cambios para generar parche)"
    elif action == "format":
        return _git_run(["format-patch", since_commit, "--stdout"], cwd=path)
    elif action == "apply":
        if not patch_content.strip():
            return "Error: patch_content vacío."
        with _tempfile.NamedTemporaryFile(suffix=".patch", mode="w", delete=False,
                                                encoding="utf-8", dir=_get_tmp_dir()) as f:
            f.write(patch_content)
            fname = f.name
        try:
            check = _git_run(["apply", "--check", fname], cwd=path)
            if "error" in check.lower():
                return f"Parche no aplicable:\n{check}"
            return _git_run(["apply", fname], cwd=path) or "Parche aplicado correctamente."
        finally:
            os.unlink(fname)
    return f"Acción desconocida: {action}. Usa create, format o apply."


def _tool_git_clone(args: dict) -> str:
    url    = args.get("url", "")
    target = args.get("target", "")
    depth  = int(args.get("depth", 0))
    branch = args.get("branch", "")
    if not url:
        return "Error: 'url' requerido."
    git_args = ["clone"]
    if depth > 0:
        git_args += ["--depth", str(depth)]
    if branch:
        git_args += ["-b", branch]
    git_args.append(url)
    if target:
        git_args.append(target)
    return _git_run(git_args, timeout=300)


def _tool_git_worktree(args: dict) -> str:
    action  = args.get("action", "list")
    wt_path = args.get("path", "")
    branch  = args.get("branch", "")
    force   = args.get("force", False)
    repo    = args.get("repo") or None

    if action == "list":
        raw = _git_run(["worktree", "list", "--porcelain"], cwd=repo)
        if not raw or "fatal" in raw.lower():
            return raw or "No hay worktrees."
        worktrees: list[dict] = []
        current: dict = {}
        for line in raw.splitlines():
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line[9:]}
            elif line.startswith("HEAD "):
                current["head"] = line[5:13]
            elif line.startswith("branch "):
                current["branch"] = line[7:].replace("refs/heads/", "")
            elif line == "bare":
                current["bare"] = True
            elif line == "detached":
                current["detached"] = True
        if current:
            worktrees.append(current)
        lines = ["Worktrees:\n"]
        for wt in worktrees:
            b = wt.get("branch", "(detached)" if wt.get("detached") else "(bare)")
            lines.append(f"  {wt['path']}  [{b}]  {wt.get('head', '?')}")
        return "\n".join(lines)
    elif action == "add":
        if not wt_path:
            return "Error: 'path' requerido para add."
        git_args = ["worktree", "add"]
        if force:
            git_args.append("--force")
        git_args.append(wt_path)
        if branch:
            git_args += ["-b", branch]
        return _git_run(git_args, cwd=repo)
    elif action == "remove":
        if not wt_path:
            return "Error: 'path' requerido para remove."
        git_args = ["worktree", "remove"]
        if force:
            git_args.append("--force")
        git_args.append(wt_path)
        return _git_run(git_args, cwd=repo) or f"Worktree eliminado: {wt_path}"
    elif action == "prune":
        return _git_run(["worktree", "prune", "--verbose"], cwd=repo) or "Prune completado."
    elif action in ("lock", "unlock"):
        if not wt_path:
            return f"Error: 'path' requerido para {action}."
        return _git_run(["worktree", action, wt_path], cwd=repo) or f"Worktree {action}: {wt_path}"
    return f"Acción desconocida: {action}. Usa list, add, remove, prune, lock o unlock."


def _tool_git_blame(args: dict) -> str:
    path  = args.get("path", "")
    start = args.get("start_line", 0)
    end   = args.get("end_line", 0)
    repo  = args.get("repo") or None
    if not path:
        return "Error: 'path' requerido."
    cmd = ["blame", "--date=short", "-w"]
    if start and end:
        cmd += [f"-L{start},{end}"]
    cmd.append(path)
    return _git_run(cmd, cwd=repo) or "Sin resultado de blame."


def _tool_git_rebase(args: dict) -> str:
    branch   = args.get("branch", "")
    action   = args.get("action", "start")
    onto     = args.get("onto", "")
    repo     = args.get("repo") or None
    if action == "start":
        if not branch:
            return "Error: 'branch' requerido para rebase."
        cmd = ["rebase"]
        if onto:
            cmd += ["--onto", onto]
        cmd.append(branch)
        return _git_run(cmd, cwd=repo) or f"Rebase sobre {branch} completado."
    elif action == "continue":
        return _git_run(["rebase", "--continue"], cwd=repo) or "Rebase continuado."
    elif action == "abort":
        return _git_run(["rebase", "--abort"], cwd=repo) or "Rebase abortado."
    elif action == "skip":
        return _git_run(["rebase", "--skip"], cwd=repo) or "Commit saltado."
    return f"Acción desconocida: {action}. Usa start, continue, abort o skip."


def _tool_git_tag(args: dict) -> str:
    action  = args.get("action", "list")
    name    = args.get("name", "")
    message = args.get("message", "")
    target  = args.get("target", "HEAD")
    repo    = args.get("repo") or None
    if action == "list":
        raw = _git_run(["tag", "-l", "--sort=-version:refname"], cwd=repo)
        return raw or "(sin tags)"
    elif action == "create":
        if not name:
            return "Error: 'name' requerido para crear tag."
        if message:
            cmd = ["tag", "-a", name, "-m", message, target]
        else:
            cmd = ["tag", name, target]
        return _git_run(cmd, cwd=repo) or f"Tag '{name}' creado en {target}."
    elif action == "delete":
        if not name:
            return "Error: 'name' requerido para eliminar tag."
        return _git_run(["tag", "-d", name], cwd=repo) or f"Tag '{name}' eliminado."
    elif action == "push":
        remote = args.get("remote", "origin")
        cmd = ["push", remote, name] if name else ["push", remote, "--tags"]
        return _git_run(cmd, cwd=repo) or "Tags enviados."
    return f"Acción desconocida: {action}. Usa list, create, delete o push."


def _tool_git_cherry_pick(args: dict) -> str:
    commit  = args.get("commit", "")
    action  = args.get("action", "pick")
    no_commit = args.get("no_commit", False)
    repo    = args.get("repo") or None
    if action == "pick":
        if not commit:
            return "Error: 'commit' requerido."
        cmd = ["cherry-pick"]
        if no_commit:
            cmd.append("-n")
        cmd.append(commit)
        return _git_run(cmd, cwd=repo) or f"Cherry-pick de {commit} completado."
    elif action == "continue":
        return _git_run(["cherry-pick", "--continue"], cwd=repo) or "Cherry-pick continuado."
    elif action == "abort":
        return _git_run(["cherry-pick", "--abort"], cwd=repo) or "Cherry-pick abortado."
    return f"Acción desconocida: {action}. Usa pick, continue o abort."


def _tool_json_validate(args: dict) -> str:
    source = args.get("content") or args.get("path", "")
    if not source:
        return "Error: proporciona 'content' (texto JSON) o 'path' (ruta al fichero)."
    import json as _json
    if args.get("path") and not args.get("content"):
        p, perr = _safe_path(args["path"])
        if perr:
            return perr
        try:
            content = p.read_text(errors="replace")
        except Exception as exc:
            return f"Error leyendo fichero: {exc}"
    else:
        content = source
    try:
        data = _json.loads(content)
        keys = list(data.keys()) if isinstance(data, dict) else None
        info = f"  Tipo: {type(data).__name__}"
        if keys is not None:
            info += f"\n  Claves raíz: {', '.join(str(k) for k in keys[:10])}"
        if isinstance(data, list):
            info += f"\n  Elementos: {len(data)}"
        return f"JSON válido.\n{info}"
    except _json.JSONDecodeError as exc:
        return f"JSON inválido: {exc}"


def _tool_yaml_validate(args: dict) -> str:
    source = args.get("content") or args.get("path", "")
    if not source:
        return "Error: proporciona 'content' (texto YAML) o 'path' (ruta al fichero)."
    if args.get("path") and not args.get("content"):
        p, perr = _safe_path(args["path"])
        if perr:
            return perr
        try:
            content = p.read_text(errors="replace")
        except Exception as exc:
            return f"Error leyendo fichero: {exc}"
    else:
        content = source
    try:
        import yaml as _yaml
        data = _yaml.safe_load(content)
        if data is None:
            return "YAML válido (vacío)."
        info = f"  Tipo: {type(data).__name__}"
        if isinstance(data, dict):
            info += f"\n  Claves raíz: {', '.join(str(k) for k in list(data.keys())[:10])}"
        elif isinstance(data, list):
            info += f"\n  Elementos: {len(data)}"
        return f"YAML válido.\n{info}"
    except ImportError:
        return "Error: PyYAML no instalado. Instala con: pip install pyyaml"
    except Exception as exc:
        return f"YAML inválido: {exc}"


def _tool_jq_query(args: dict) -> str:
    query   = args.get("query", ".")
    source  = args.get("content") or args.get("path", "")
    compact = args.get("compact", False)
    if not source:
        return "Error: proporciona 'content' (texto JSON) o 'path' (ruta)."
    import shutil as _sh
    if not _sh.which("jq"):
        # Fallback Python puro para queries básicas
        import json as _json
        try:
            if args.get("path") and not args.get("content"):
                p, perr = _safe_path(args["path"])
                content = p.read_text(errors="replace") if not perr else ""
            else:
                content = source
            data = _json.loads(content)
            if query == "." or query == "":
                return _json.dumps(data, indent=2, ensure_ascii=False)
            return f"Error: jq no instalado. Instala con: apt install jq\nFallback solo soporta query '.'"
        except Exception as exc:
            return f"Error: {exc}"
    import subprocess as _sp
    if args.get("path") and not args.get("content"):
        p, perr = _safe_path(args["path"])
        if perr:
            return perr
        input_text = p.read_text(errors="replace")
    else:
        input_text = source
    cmd = ["jq"]
    if compact:
        cmd.append("-c")
    cmd.append(query)
    try:
        r = _sp.run(cmd, input=input_text, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return f"Error jq: {r.stderr.strip()}"
        return r.stdout.strip()
    except Exception as exc:
        return f"Error ejecutando jq: {exc}"


def _tool_find_files(args: dict) -> str:
    """Búsqueda avanzada de ficheros: por nombre glob, extensión, tamaño y edad."""
    directory  = args.get("directory", ".")
    name_glob  = args.get("name", "")          # glob: "*.py", "test_*", etc.
    extension  = args.get("extension", "")     # ej. "py" (sin punto)
    min_size   = int(args.get("min_size_kb", 0)) * 1024
    max_size   = int(args.get("max_size_kb", 0)) * 1024
    max_age_d  = int(args.get("max_age_days", 0))
    min_age_d  = int(args.get("min_age_days", 0))
    max_depth  = min(int(args.get("max_depth", 10)), 20)
    max_results = min(int(args.get("max_results", 50)), 500)
    include_hidden = args.get("include_hidden", False)

    root = Path(directory).expanduser().resolve()
    if not root.exists():
        return f"Error: directorio no encontrado: {directory}"

    _IGNORE = {".git", "__pycache__", "node_modules", ".venv", "venv",
               ".mypy_cache", "dist", "build", "target"}
    now = datetime.datetime.now().timestamp()

    results = []

    def _walk(path: Path, depth: int) -> None:
        if depth > max_depth or len(results) >= max_results:
            return
        try:
            for entry in sorted(path.iterdir(), key=lambda e: e.name):
                if not include_hidden and entry.name.startswith("."):
                    continue
                if entry.name in _IGNORE:
                    continue
                if entry.is_dir():
                    _walk(entry, depth + 1)
                elif entry.is_file():
                    # Filtro por nombre glob (soporta múltiples patrones: "*.py,*.pyi")
                    if name_glob:
                        from fnmatch import fnmatch
                        _globs = [g.strip() for g in name_glob.split(",") if g.strip()]
                        if not any(fnmatch(entry.name, g) for g in _globs):
                            continue
                    # Filtro por extensión
                    if extension and entry.suffix.lower() != "." + extension.lstrip(".").lower():
                        continue
                    # Filtro por tamaño
                    try:
                        st = entry.stat()
                        size = st.st_size
                        age_s = now - st.st_mtime
                    except OSError:
                        continue
                    if min_size and size < min_size:
                        continue
                    if max_size and size > max_size:
                        continue
                    if max_age_d and age_s > max_age_d * 86400:
                        continue
                    if min_age_d and age_s < min_age_d * 86400:
                        continue
                    results.append((entry, size, age_s))
        except PermissionError:
            pass

    _walk(root, 1)

    if not results:
        return f"Sin resultados con los filtros indicados en {root}"

    lines = [f"Encontrados {len(results)} ficheros en {root}:\n"]
    for entry, size, age_s in results[:max_results]:
        rel   = entry.relative_to(root) if entry.is_relative_to(root) else entry
        if size < 1024:
            size_str = f"{size}B"
        elif size < 1024**2:
            size_str = f"{size//1024}KB"
        else:
            size_str = f"{size//1024**2}MB"
        if age_s < 3600:
            age_str = f"{int(age_s//60)}m"
        elif age_s < 86400:
            age_str = f"{int(age_s//3600)}h"
        else:
            age_str = f"{int(age_s//86400)}d"
        lines.append(f"  {age_str:>5}  {size_str:>7}  {rel}")
    if len(results) >= max_results:
        lines.append(f"\n... [limitado a {max_results} resultados]")
    return "\n".join(lines)


def _tool_process_list(args: dict) -> str:
    """Lista procesos activos filtrados por nombre o usuario."""
    filter_name = args.get("filter", "")   # ej. "python", "node", "uvicorn"
    show_ports  = args.get("show_ports", True)
    max_results = min(int(args.get("max_results", 30)), 100)

    try:
        r = subprocess.run(
            ["ps", "aux", "--no-headers"],
            capture_output=True, text=True, timeout=8,
        )
        lines_raw = r.stdout.strip().splitlines()
    except Exception as exc:
        return f"Error ejecutando ps: {exc}"

    # Parsear: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
    processes = []
    for line in lines_raw:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        user, pid, cpu, mem = parts[0], parts[1], parts[2], parts[3]
        cmd = parts[10]
        # Filtrar si se especificó nombre
        if filter_name and filter_name.lower() not in cmd.lower():
            continue
        # Excluir el propio ps y grep
        if "ps aux" in cmd or "ps --" in cmd:
            continue
        processes.append((pid, user, cpu, mem, cmd[:120]))

    if not processes:
        target = f" con '{filter_name}'" if filter_name else ""
        return f"No se encontraron procesos{target}."

    processes = processes[:max_results]

    lines = [f"{'PID':>7}  {'USER':<12}  {'CPU%':>5}  {'MEM%':>5}  COMANDO"]
    lines.append("-" * 70)
    for pid, user, cpu, mem, cmd in processes:
        lines.append(f"  {pid:>5}  {user:<12}  {cpu:>5}  {mem:>5}  {cmd}")

    if show_ports and processes:
        # Añadir puertos asociados via ss
        try:
            ss_r = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True, text=True, timeout=5,
            )
            pid_ports: dict[str, list[int]] = {}
            for ss_line in ss_r.stdout.splitlines():
                pm = re.search(r'pid=(\d+)', ss_line)
                port_m = re.search(r':(\d{2,5})\s', ss_line)
                if pm and port_m:
                    pid_str = pm.group(1)
                    pid_ports.setdefault(pid_str, []).append(int(port_m.group(1)))
            if pid_ports:
                lines.append("\nPuertos asociados:")
                for pid, _user, _cpu, _mem, _cmd in processes:
                    if pid in pid_ports:
                        ports_str = ", ".join(str(p) for p in pid_ports[pid])
                        lines.append(f"  PID {pid}: :{ports_str}")
        except Exception:
            pass

    return "\n".join(lines)


# ── Docker tools ──────────────────────────────────────────────────────────────

_DOCKER_MAX_OUTPUT = 8000


def _docker_run(cmd: list[str], cwd: str | None = None, timeout: int = 60,
                input_text: str | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if input_text else subprocess.DEVNULL,
            text=True,
            cwd=cwd or os.getcwd(),
            start_new_session=True,
        )
        try:
            out, _ = proc.communicate(input=input_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                import signal as _sig
                os.killpg(os.getpgid(proc.pid), _sig.SIGKILL)
            except Exception:
                proc.kill()
            proc.communicate()
            return -1, f"Timeout ({timeout}s)"
        return proc.returncode, (out or "").strip()
    except FileNotFoundError:
        return -2, f"Comando no encontrado: {cmd[0]}"
    except Exception as e:
        return -3, str(e)


def _docker_trim(out: str) -> str:
    if len(out) <= _DOCKER_MAX_OUTPUT:
        return out
    half = _DOCKER_MAX_OUTPUT // 2
    return out[:half] + "\n…\n" + out[-half:]


import functools as _functools  # noqa: E402

@_functools.lru_cache(maxsize=1)
def _compose_bin() -> tuple[str, ...]:
    rc, _ = _docker_run(["docker", "compose", "version"])
    if rc == 0:
        return ("docker", "compose")
    import shutil as _sh
    if _sh.which("docker-compose"):
        return ("docker-compose",)
    return ("docker", "compose")


def _docker_compose(subcmd: list[str], cwd: str, timeout: int = 60) -> tuple[int, str]:
    return _docker_run(list(_compose_bin()) + subcmd, cwd=cwd, timeout=timeout)


def _find_compose_dir(path: str | None = None) -> str | None:
    root = Path(path or os.getcwd())
    names = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
    for d in [root] + list(root.parents)[:3]:
        for name in names:
            if (d / name).exists():
                return str(d)
    return None


def _require_compose(path: str = "") -> tuple[str, str]:
    cwd = _find_compose_dir(path or None)
    if cwd is None:
        return "", f"No se encontró docker-compose.yml/yaml ni compose.yml/yaml en '{path or os.getcwd()}'."
    return cwd, ""


def _tool_docker_ps(args: dict) -> str:
    all_ = args.get("all", False)
    cmd = ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"]
    if all_:
        cmd.append("-a")
    rc, out = _docker_run(cmd)
    if rc == -2:
        return "Error: Docker no está instalado o no corre."
    return out or "No hay contenedores en ejecución."


def _tool_docker_logs(args: dict) -> str:
    container = args.get("container", "")
    lines     = int(args.get("lines", 50))
    follow    = args.get("follow", False)
    if not container:
        return "Error: 'container' requerido."
    cmd = ["docker", "logs", "--tail", str(lines)]
    if follow:
        cmd.append("-f")
    cmd.append(container)
    timeout = 10 if follow else 30
    rc, out = _docker_run(cmd, timeout=timeout)
    if rc != 0 and not out:
        return f"Error: contenedor '{container}' no encontrado o sin logs."
    return _docker_trim(out) or f"(Sin logs en '{container}')"


def _tool_docker_exec(args: dict) -> str:
    container = args.get("container", "")
    command   = args.get("command", "")
    if not container or not command:
        return "Error: 'container' y 'command' requeridos."
    rc, out = _docker_run(["docker", "exec", container, "sh", "-c", command], timeout=30)
    if rc == -2:
        return "Error: Docker no está disponible."
    return _docker_trim(out) or f"(Comando ejecutado en '{container}', sin salida)"


def _tool_docker_inspect(args: dict) -> str:
    container = args.get("container", "")
    if not container:
        return "Error: 'container' requerido."
    fmt = (
        "Name: {{.Name}}\nImage: {{.Config.Image}}\nStatus: {{.State.Status}}\n"
        "IP: {{.NetworkSettings.IPAddress}}\nPorts: {{json .NetworkSettings.Ports}}\n"
        "Env: {{json .Config.Env}}"
    )
    rc, out = _docker_run(["docker", "inspect", "--format", fmt, container])
    if rc != 0:
        return f"Error: contenedor '{container}' no encontrado."
    return out


def _tool_docker_images(args: dict) -> str:
    filter_ = args.get("filter", "")
    cmd = ["docker", "images", "--format", "table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"]
    if filter_:
        cmd.append(filter_)
    rc, out = _docker_run(cmd)
    if rc == -2:
        return "Error: Docker no disponible."
    return out or "No hay imágenes locales."


def _tool_docker_stop(args: dict) -> str:
    container = args.get("container", "")
    if not container:
        return "Error: 'container' requerido."
    rc, out = _docker_run(["docker", "stop", container], timeout=30)
    return out or ("Contenedor detenido." if rc == 0 else f"Error (rc={rc})")


def _tool_docker_rm(args: dict) -> str:
    container = args.get("container", "")
    force     = args.get("force", False)
    if not container:
        return "Error: 'container' requerido."
    cmd = ["docker", "rm"]
    if force:
        cmd.append("-f")
    cmd.append(container)
    rc, out = _docker_run(cmd, timeout=15)
    return out or ("Contenedor eliminado." if rc == 0 else f"Error (rc={rc})")


def _tool_docker_cp(args: dict) -> str:
    """Copia ficheros entre el host y un contenedor Docker."""
    src = args.get("src", "")
    dst = args.get("dst", "")
    if not src or not dst:
        return "Error: 'src' y 'dst' requeridos. Ej: src='./file.txt', dst='container:/path/file.txt'"
    rc, out = _docker_run(["docker", "cp", src, dst], timeout=60)
    if rc == 0:
        return out or f"Copiado: {src} → {dst}"
    return f"Error copiando (rc={rc}): {out}"


def _tool_compose_version(args: dict) -> str:
    rc, out = _docker_run(["docker", "compose", "version"])
    if rc == 0:
        return out.split("\n")[0]
    rc2, out2 = _docker_run(["docker-compose", "version"])
    if rc2 == 0:
        return out2.split("\n")[0] + " (v1)"
    return "docker compose no disponible"


def _tool_compose_services(args: dict) -> str:
    path = args.get("path", "")
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    rc, out = _docker_compose(["config", "--services"], cwd=cwd)
    if rc != 0:
        cf_path = _find_compose_dir(cwd)
        if cf_path:
            for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
                p = Path(cf_path) / name
                if p.exists():
                    try:
                        content = p.read_text()
                        services = re.findall(r'^  (\w[\w-]*):', content, re.MULTILINE)
                        return "Servicios:\n" + "\n".join(f"  · {s}" for s in services)
                    except Exception:
                        break
        return f"Error listando servicios: {out}"
    services = [s for s in out.splitlines() if s.strip()]
    return "Servicios definidos:\n" + "\n".join(f"  · {s}" for s in services)


def _tool_compose_status(args: dict) -> str:
    path = args.get("path", "")
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    rc, out = _docker_compose(["ps"], cwd=cwd)
    return out or "No hay servicios en ejecución."


def _tool_compose_up(args: dict) -> str:
    path    = args.get("path", "")
    service = args.get("service", "")
    detach  = args.get("detach", True)
    build   = args.get("build", False)
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["up"]
    if detach:
        cmd.append("-d")
    if build:
        cmd.append("--build")
    if service:
        cmd.append(service)
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=300)
    return _docker_trim(out) or ("Servicios levantados." if rc == 0 else f"Error (rc={rc})")


def _tool_compose_down(args: dict) -> str:
    path          = args.get("path", "")
    volumes       = args.get("volumes", False)
    remove_images = args.get("remove_images", "")
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["down"]
    if volumes:
        cmd.append("-v")
    if remove_images in ("all", "local"):
        cmd += ["--rmi", remove_images]
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=120)
    return _docker_trim(out) or ("Servicios detenidos." if rc == 0 else f"Error (rc={rc})")


def _tool_compose_stop(args: dict) -> str:
    path    = args.get("path", "")
    service = args.get("service", "")
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["stop"]
    if service:
        cmd.append(service)
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=60)
    return _docker_trim(out) or ("Detenido." if rc == 0 else f"Error (rc={rc})")


def _tool_compose_restart(args: dict) -> str:
    path    = args.get("path", "")
    service = args.get("service", "")
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["restart"]
    if service:
        cmd.append(service)
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=60)
    return _docker_trim(out) or ("Reiniciado." if rc == 0 else f"Error (rc={rc})")


def _tool_compose_build(args: dict) -> str:
    path     = args.get("path", "")
    service  = args.get("service", "")
    no_cache = args.get("no_cache", False)
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["build"]
    if no_cache:
        cmd.append("--no-cache")
    if service:
        cmd.append(service)
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=600)
    return _docker_trim(out) or ("Build completado." if rc == 0 else f"Error (rc={rc})")


def _tool_compose_pull(args: dict) -> str:
    path    = args.get("path", "")
    service = args.get("service", "")
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["pull"]
    if service:
        cmd.append(service)
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=300)
    return _docker_trim(out) or ("Pull completado." if rc == 0 else f"Error (rc={rc})")


def _tool_compose_logs(args: dict) -> str:
    path    = args.get("path", "")
    service = args.get("service", "")
    lines   = int(args.get("lines", 50))
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["logs", "--tail", str(lines), "--no-color"]
    if service:
        cmd.append(service)
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=30)
    return _docker_trim(out) or "(Sin logs)"


def _tool_compose_exec(args: dict) -> str:
    import shlex
    path    = args.get("path", "")
    service = args.get("service", "")
    command = args.get("command", "sh")
    if not service:
        return "Error: 'service' requerido."
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd_parts = shlex.split(command) if command != "sh" else ["sh"]
    cmd = ["exec", "-T", service] + cmd_parts
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=30)
    return _docker_trim(out) or f"(Sin salida del servicio '{service}')"


def _tool_compose_run(args: dict) -> str:
    import shlex
    path    = args.get("path", "")
    service = args.get("service", "")
    command = args.get("command", "")
    remove  = args.get("remove", True)
    if not service or not command:
        return "Error: 'service' y 'command' requeridos."
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["run", "--no-deps"]
    if remove:
        cmd.append("--rm")
    cmd.append(service)
    cmd += shlex.split(command)
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=120)
    return _docker_trim(out) or "(Sin salida)"


def _tool_compose_config(args: dict) -> str:
    path  = args.get("path", "")
    quiet = args.get("quiet", False)
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["config"]
    if quiet:
        cmd.append("-q")
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=15)
    if rc != 0:
        return f"Configuración inválida:\n{out}"
    return "Configuración válida." if quiet else _docker_trim(out)


def _tool_compose_images(args: dict) -> str:
    path = args.get("path", "")
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    rc, out = _docker_compose(["images"], cwd=cwd, timeout=15)
    return out or "No hay imágenes para los servicios de este compose."


def _tool_compose_top(args: dict) -> str:
    path    = args.get("path", "")
    service = args.get("service", "")
    cwd, err = _require_compose(path)
    if err:
        return f"Error: {err}"
    cmd = ["top"]
    if service:
        cmd.append(service)
    rc, out = _docker_compose(cmd, cwd=cwd, timeout=15)
    return _docker_trim(out) or "Sin procesos activos."


# ── Ctags tools ───────────────────────────────────────────────────────────────

_CTAGS_FILE = ".oocode_tags"
_CTAGS_KINDS: dict[str, str] = {
    "c": "clase", "f": "función", "m": "método", "v": "variable",
    "i": "interfaz", "s": "struct", "e": "enum", "t": "tipo",
    "d": "define", "n": "namespace", "p": "prototipo",
}


def _ctags_bin() -> str:
    import shutil as _sh
    return _sh.which("ctags") or _sh.which("universal-ctags") or "ctags"


def _ctags_build_index(root: str) -> str:
    import shutil as _sh
    if not (_sh.which("ctags") or _sh.which("universal-ctags")):
        return "ctags no instalado (apt install universal-ctags)"
    tags = Path(root) / _CTAGS_FILE
    try:
        proc = subprocess.Popen(
            [_ctags_bin(), "-R", "--fields=+n", "--extras=+q",
             "--tag-relative=yes", "--output-format=u-ctags", "-f", str(tags), "."],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=root,
            start_new_session=True,
        )
        _, err = proc.communicate(timeout=60)
        if proc.returncode != 0 and err:
            return err.strip()
        return ""
    except subprocess.TimeoutExpired:
        try:
            import signal as _sig
            os.killpg(os.getpgid(proc.pid), _sig.SIGKILL)
        except Exception:
            proc.kill()
        proc.communicate()
        return "Timeout al generar índice."
    except Exception as e:
        return str(e)


def _ctags_read_tags(root: str) -> list[dict]:
    tags_path = Path(root) / _CTAGS_FILE
    if not tags_path.exists():
        return []
    results = []
    try:
        for line in tags_path.read_text(errors="replace").splitlines():
            if line.startswith("!"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            name, fpath, kind, lno = parts[0], parts[1], "", "?"
            for field in parts[3:]:
                if field.startswith("line:"):
                    lno = field[5:]
                elif len(field) == 1 and field.isalpha():
                    kind = field
            results.append({"name": name, "path": fpath, "line": lno, "kind": kind})
    except Exception:
        pass
    return results


def _tool_build_symbol_index(args: dict) -> str:
    path = args.get("path", "") or os.getcwd()
    root = str(Path(path).resolve())
    if not Path(root).is_dir():
        return f"Error: directorio no encontrado: {root}"
    err = _ctags_build_index(root)
    if err:
        return f"Error generando índice: {err}"
    count = len(_ctags_read_tags(root))
    return f"Índice generado en {root} — {count} símbolos."


def _tool_find_symbol(args: dict) -> str:
    name = args.get("name", "")
    kind = args.get("kind", "")
    path = args.get("path", "") or os.getcwd()
    if not name:
        return "Error: 'name' requerido."
    root = str(Path(path).resolve())
    tags = _ctags_read_tags(root)
    if not tags:
        err = _ctags_build_index(root)
        if err:
            return f"Sin índice y falló la generación: {err}"
        tags = _ctags_read_tags(root)
    if not tags:
        return "No hay símbolos en el índice."
    lower_name = name.lower()
    kind_key   = kind.lower()[:1] if kind else ""
    matches = [
        t for t in tags
        if lower_name in t["name"].lower()
        and (not kind_key or t["kind"] == kind_key
             or kind_key in _CTAGS_KINDS.get(t["kind"], ""))
    ]
    if not matches:
        return f"Símbolo '{name}' no encontrado."
    lines = [f"Símbolo: «{name}»  ({len(matches)} resultado(s))\n"]
    for m in matches[:30]:
        k = _CTAGS_KINDS.get(m["kind"], m["kind"])
        lines.append(f"  {m['path']}:{m['line']}  [{k}]  {m['name']}")
    if len(matches) > 30:
        lines.append(f"  … y {len(matches)-30} más.")
    return "\n".join(lines)


def _tool_list_symbols(args: dict) -> str:
    path  = args.get("path", "")
    kinds = args.get("kinds", "")
    if not path:
        return "Error: 'path' requerido."
    p = Path(path)
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"
    root = str(p.parent.resolve())
    tags = _ctags_read_tags(root)
    if not tags:
        _ctags_build_index(root)
        tags = _ctags_read_tags(root)
    rel = p.name
    kind_filter = set(k.strip()[:1] for k in kinds.split(",") if k.strip()) if kinds else set()
    symbols = sorted(
        [t for t in tags if Path(t["path"]).name == rel
         and (not kind_filter or t["kind"] in kind_filter)],
        key=lambda t: int(t["line"]) if t["line"].isdigit() else 0,
    )
    if not symbols:
        return f"Sin símbolos en '{p.name}'."
    lines = [f"Símbolos en {p.name}:\n"]
    for s in symbols:
        k = _CTAGS_KINDS.get(s["kind"], s["kind"])
        lines.append(f"  :{s['line']:<6} [{k:<10}]  {s['name']}")
    return "\n".join(lines)


# ── Linter tools ──────────────────────────────────────────────────────────────

_LINTERS: dict[str, list[list[str]]] = {
    ".py":  [
        ["ruff", "check", "--output-format=concise", "{file}"],
        ["mypy", "--no-error-summary", "--ignore-missing-imports", "{file}"],
    ],
    ".js":  [["eslint", "{file}"]],
    ".ts":  [["eslint", "{file}"]],
    ".jsx": [["eslint", "{file}"]],
    ".tsx": [["eslint", "{file}"]],
    ".sh":  [["shellcheck", "-S", "warning", "{file}"]],
    ".bash":[["shellcheck", "-S", "warning", "{file}"]],
    ".rs":  [["cargo", "check", "--message-format=short"]],
    ".go":  [["go", "vet", "{file}"]],
    # C/C++ — cppcheck para análisis estático, clang-tidy si disponible
    ".c":   [
        ["cppcheck", "--enable=warning,style,performance,portability",
         "--error-exitcode=1", "--quiet", "{file}"],
    ],
    ".h":   [
        ["cppcheck", "--enable=warning,style,performance",
         "--error-exitcode=1", "--quiet", "{file}"],
    ],
    ".cpp": [
        ["cppcheck", "--enable=warning,style,performance,portability",
         "--language=c++", "--error-exitcode=1", "--quiet", "{file}"],
    ],
    ".cc":  [
        ["cppcheck", "--enable=warning,style,performance,portability",
         "--language=c++", "--error-exitcode=1", "--quiet", "{file}"],
    ],
    ".hpp": [
        ["cppcheck", "--enable=warning,style,performance",
         "--language=c++", "--error-exitcode=1", "--quiet", "{file}"],
    ],
    # PHP — syntax check nativo + PHP CodeSniffer (PSR-12) + PHPStan (análisis estático)
    ".php": [["php", "-l", "{file}"],
             ["phpcs", "--standard=PSR12", "--report=emacs", "{file}"],
             ["phpstan", "analyse", "--no-progress", "--level=5", "{file}"]],
}


def _linter_run(cmd: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=cwd or os.getcwd(),
            start_new_session=True,
        )
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                import signal as _sig
                os.killpg(os.getpgid(proc.pid), _sig.SIGKILL)
            except Exception:
                proc.kill()
            proc.communicate()
            return -1, f"Timeout ({timeout}s)"
        return proc.returncode, (out or "").strip()
    except FileNotFoundError:
        return -2, f"herramienta no instalada: {cmd[0]}"
    except Exception as e:
        return -3, str(e)


def _tool_lint_file(args: dict) -> str:
    path = args.get("path", "")
    if not path:
        return "Error: 'path' requerido."
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"
    ext     = p.suffix.lower()
    linters = _LINTERS.get(ext, [])
    if not linters:
        return f"Sin linter configurado para extensión '{ext}'."
    import shutil as _sh
    cwd     = str(p.parent)
    results = []
    for template in linters:
        cmd = [c.replace("{file}", str(p)) for c in template]
        if not _sh.which(cmd[0]):
            continue
        rc, out = _linter_run(cmd, cwd=cwd)
        if rc == -2:
            continue
        tool = cmd[0]
        if rc == 0:
            results.append(f"  ✓  {tool}: sin errores")
        else:
            out_trim = out[:4000]
            if len(out) > 4000:
                out_trim += "\n     … (recortado a 4000 chars)"
            results.append(f"  ✗  {tool} (rc={rc}):\n" + "\n".join(f"     {ln}" for ln in out_trim.splitlines()))
    if not results:
        return f"Ningún linter disponible para '{ext}' (instala ruff/mypy/eslint/shellcheck)."
    return f"Lint: {p.name}\n" + "\n".join(results)


def _tool_lint_project(args: dict) -> str:
    path = args.get("path", "") or os.getcwd()
    root = Path(path).resolve()
    if not root.is_dir():
        return f"Error: directorio no encontrado: {root}"
    import shutil as _sh
    results = []
    if _sh.which("ruff"):
        rc, out = _linter_run(["ruff", "check", "--output-format=concise", str(root)])
        if rc == 0:
            results.append("  ✓  ruff: sin errores")
        elif out:
            lines = out.splitlines()[:40]
            results.append("  ✗  ruff:\n" + "\n".join(f"    {ln}" for ln in lines))
    if _sh.which("mypy") and any(root.rglob("*.py")):
        rc, out = _linter_run(["mypy", "--no-error-summary", "--ignore-missing-imports", str(root)], cwd=str(root))
        if rc == 0:
            results.append("  ✓  mypy: sin errores de tipos")
        elif out:
            lines = out.splitlines()[:30]
            results.append("  ✗  mypy:\n" + "\n".join(f"    {ln}" for ln in lines))
    if _sh.which("shellcheck"):
        scripts = list(root.rglob("*.sh"))[:20]
        if scripts:
            rc, out = _linter_run(["shellcheck", "-S", "warning"] + [str(s) for s in scripts])
            if rc == 0:
                results.append(f"  ✓  shellcheck: {len(scripts)} scripts OK")
            elif out:
                lines = out.splitlines()[:20]
                results.append("  ✗  shellcheck:\n" + "\n".join(f"    {ln}" for ln in lines))
    if _sh.which("cppcheck"):
        c_files = list(root.rglob("*.c"))[:50] + list(root.rglob("*.cpp"))[:30]
        if c_files:
            rc, out = _linter_run(
                ["cppcheck", "--enable=warning,style,performance,portability",
                 "--error-exitcode=1", "--quiet"] + [str(f) for f in c_files],
                cwd=str(root),
            )
            if rc == 0:
                results.append(f"  ✓  cppcheck: {len(c_files)} ficheros C/C++ OK")
            elif out:
                lines = out.splitlines()[:30]
                results.append("  ✗  cppcheck:\n" + "\n".join(f"    {ln}" for ln in lines))
    if not results:
        return "Ningún linter disponible. Instala ruff, mypy, shellcheck o cppcheck."
    return f"Lint: {root.name}/\n" + "\n".join(results)


def _tool_url_encode(args: dict) -> str:
    """Codifica o decodifica URL percent-encoding y Base64."""
    import urllib.parse
    import base64

    text      = args.get("text", "")
    operation = args.get("operation", "encode")  # encode | decode | b64encode | b64decode
    encoding  = args.get("encoding", "utf-8")

    if not text:
        return "Error: 'text' requerido."

    try:
        if operation == "encode":
            result = urllib.parse.quote(text, safe="")
            return f"URL-encode ({encoding}):\n{result}"
        elif operation == "decode":
            result = urllib.parse.unquote(text, encoding=encoding)
            return f"URL-decode:\n{result}"
        elif operation == "b64encode":
            result = base64.b64encode(text.encode(encoding)).decode("ascii")
            return f"Base64-encode:\n{result}"
        elif operation == "b64decode":
            # Tolerar padding incorrecto
            padded = text + "=" * (-len(text) % 4)
            result = base64.b64decode(padded).decode(encoding, errors="replace")
            return f"Base64-decode:\n{result}"
        elif operation == "urlencode_form":
            # Codificación de formulario (+ para espacios)
            result = urllib.parse.quote_plus(text)
            return f"Form-encode:\n{result}"
        else:
            return f"Error: operación desconocida '{operation}'. Usa: encode, decode, b64encode, b64decode, urlencode_form."
    except Exception as exc:
        return f"Error en {operation}: {exc}"


def _tool_count_lines(args: dict) -> str:
    """Cuenta líneas de código por lenguaje. Usa cloc/tokei si están disponibles."""
    directory  = args.get("directory", ".")
    extensions = args.get("extensions", "")
    max_depth  = min(int(args.get("max_depth", 15)), 30)

    root = Path(directory).expanduser().resolve()
    if not root.exists():
        return f"Error: directorio no encontrado: {directory}"

    import shutil
    # ── Intentar cloc primero (más preciso para lenguajes) ────────────────────
    if shutil.which("cloc") and not extensions:
        try:
            r = subprocess.run(
                ["cloc", "--quiet", str(root)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and r.stdout.strip():
                return f"# cloc {root}\n\n" + r.stdout.strip()
        except Exception:
            pass

    # ── Intentar tokei (más rápido que cloc) ──────────────────────────────────
    if shutil.which("tokei") and not extensions:
        try:
            r = subprocess.run(
                ["tokei", str(root)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and r.stdout.strip():
                return f"# tokei {root}\n\n" + r.stdout.strip()
        except Exception:
            pass

    # Mapa extensión → lenguaje + patrón de comentario de línea
    _LANG_MAP: dict[str, tuple[str, str]] = {
        ".py":   ("Python",     "#"),
        ".js":   ("JavaScript", "//"),
        ".ts":   ("TypeScript", "//"),
        ".jsx":  ("JSX",        "//"),
        ".tsx":  ("TSX",        "//"),
        ".c":    ("C",          "//"),
        ".h":    ("C/Header",   "//"),
        ".cpp":  ("C++",        "//"),
        ".cc":   ("C++",        "//"),
        ".rs":   ("Rust",       "//"),
        ".go":   ("Go",         "//"),
        ".java": ("Java",       "//"),
        ".kt":   ("Kotlin",     "//"),
        ".rb":   ("Ruby",       "#"),
        ".sh":   ("Shell",      "#"),
        ".bash": ("Bash",       "#"),
        ".zsh":  ("Zsh",        "#"),
        ".lua":  ("Lua",        "--"),
        ".sql":  ("SQL",        "--"),
        ".md":   ("Markdown",   ""),
        ".toml": ("TOML",       "#"),
        ".yaml": ("YAML",       "#"),
        ".yml":  ("YAML",       "#"),
        ".json": ("JSON",       ""),
        ".html": ("HTML",       ""),
        ".css":  ("CSS",        ""),
    }

    if extensions:
        filter_exts = {"." + e.lstrip(".").lower() for e in extensions.split(",")}
    else:
        filter_exts = set(_LANG_MAP.keys())

    _IGNORE = {".git", "__pycache__", "node_modules", ".venv", "venv",
               ".mypy_cache", "dist", "build", "target"}

    stats: dict[str, dict[str, int]] = {}  # lang → {files, code, comment, blank, total}

    def _process(f: Path) -> None:
        ext  = f.suffix.lower()
        lang, comment_prefix = _LANG_MAP.get(ext, ("Other", ""))
        if lang not in stats:
            stats[lang] = {"files": 0, "code": 0, "comment": 0, "blank": 0, "total": 0}
        s = stats[lang]
        s["files"] += 1
        try:
            for line in f.read_text(errors="replace").splitlines():
                stripped = line.strip()
                s["total"] += 1
                if not stripped:
                    s["blank"] += 1
                elif comment_prefix and stripped.startswith(comment_prefix):
                    s["comment"] += 1
                else:
                    s["code"] += 1
        except Exception:
            pass

    def _walk(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            for entry in path.iterdir():
                if entry.name.startswith(".") or entry.name in _IGNORE:
                    continue
                if entry.is_dir():
                    _walk(entry, depth + 1)
                elif entry.is_file() and entry.suffix.lower() in filter_exts:
                    _process(entry)
        except PermissionError:
            pass

    _walk(root, 1)

    if not stats:
        return f"No se encontraron ficheros de código en {root}"

    # Ordenar por líneas totales descendente
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True)
    total_all = {"files": 0, "code": 0, "comment": 0, "blank": 0, "total": 0}
    for _, s in sorted_stats:
        for k in total_all:
            total_all[k] += s[k]

    lines = [f"Estadísticas de código en {root}\n"]
    lines.append(f"{'Lenguaje':<14} {'Files':>6} {'Código':>8} {'Coment':>8} {'Blancos':>8} {'Total':>8}")
    lines.append("-" * 56)
    for lang, s in sorted_stats:
        lines.append(
            f"{lang:<14} {s['files']:>6} {s['code']:>8} {s['comment']:>8} {s['blank']:>8} {s['total']:>8}"
        )
    lines.append("-" * 56)
    lines.append(
        f"{'TOTAL':<14} {total_all['files']:>6} {total_all['code']:>8} "
        f"{total_all['comment']:>8} {total_all['blank']:>8} {total_all['total']:>8}"
    )
    return "\n".join(lines)


def _tool_template_fill(args: dict) -> str:
    """Rellena una plantilla de texto con variables {{clave}} o {clave}."""
    template   = args.get("template", "")
    variables  = args.get("variables", {})   # dict str→str
    style      = args.get("style", "double") # double={{}} | single={} | dollar=${}

    if not template:
        return "Error: 'template' requerido."

    if not isinstance(variables, dict):
        return "Error: 'variables' debe ser un objeto JSON {clave: valor}."

    try:
        if style == "double":
            # Reemplazar {{clave}} con el valor
            result = template
            for k, v in variables.items():
                result = result.replace("{{" + k + "}}", str(v))
            # Detectar variables sin rellenar
            missing = re.findall(r'\{\{(\w+)\}\}', result)
        elif style == "single":
            result = template.format_map({k: str(v) for k, v in variables.items()})
            missing = []
        elif style == "dollar":
            result = template
            for k, v in variables.items():
                result = result.replace("${" + k + "}", str(v))
            missing = re.findall(r'\$\{(\w+)\}', result)
        else:
            return f"Error: estilo desconocido '{style}'. Usa: double, single, dollar."

        header = f"Plantilla rellenada ({len(variables)} variables)"
        if missing:
            header += f"\nADVERTENCIA: variables sin valor: {', '.join(set(missing))}"
        return f"{header}\n\n{result}"
    except KeyError as exc:
        return f"Error: variable {exc} no encontrada en 'variables'."
    except Exception as exc:
        return f"Error rellenando plantilla: {exc}"


# ── Filesystem tools ──────────────────────────────────────────────────────────

def _safe_path(raw: str, *, allow_root: bool = False) -> "tuple[Path, str]":
    """Resuelve y valida que la ruta esté dentro del home o cwd. Devuelve (Path, error_str)."""
    if not raw:
        return Path("."), "Error: 'path' requerido."
    p = Path(raw).expanduser().resolve()
    if not allow_root:
        home = Path.home().resolve()
        cwd  = Path.cwd().resolve()
        blocked = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/boot", "/proc", "/sys", "/dev")
        if any(str(p).startswith(b) for b in blocked):
            return p, f"Error: ruta bloqueada por seguridad: {p}"
        if not (str(p).startswith(str(home)) or str(p).startswith(str(cwd))):
            return p, f"Error: ruta fuera del home o directorio de trabajo: {p}"
    return p, ""


def _tool_ls_file(args: dict) -> str:
    """Información detallada (stat) de un fichero o directorio."""
    import stat as _stat
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    if not p.exists():
        return f"Error: no existe: {p}"
    try:
        import pwd
        import grp
        s = p.lstat()
        mode = _stat.filemode(s.st_mode)
        try:
            owner = pwd.getpwuid(s.st_uid).pw_name
        except Exception:
            owner = str(s.st_uid)
        try:
            group = grp.getgrgid(s.st_gid).gr_name
        except Exception:
            group = str(s.st_gid)
        mtime = datetime.datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        atime = datetime.datetime.fromtimestamp(s.st_atime).strftime("%Y-%m-%d %H:%M:%S")
        ctime = datetime.datetime.fromtimestamp(s.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        if _stat.S_ISLNK(s.st_mode):
            ftype = "enlace simbólico"
        elif _stat.S_ISDIR(s.st_mode):
            ftype = "directorio"
        elif _stat.S_ISREG(s.st_mode):
            ftype = "fichero"
        else:
            ftype = f"especial ({oct(s.st_mode)})"
        lines = [
            f"Ruta:        {p}",
            f"Tipo:        {ftype}",
            f"Permisos:    {mode}  ({oct(s.st_mode & 0o7777)})",
            f"Propietario: {owner}:{group}",
            f"Tamaño:      {s.st_size} bytes",
            f"Modificado:  {mtime}",
            f"Accedido:    {atime}",
            f"Cambiado:    {ctime}",
            f"Inodo:       {s.st_ino}  Nlinks: {s.st_nlink}",
        ]
        if _stat.S_ISLNK(s.st_mode):
            lines.append(f"Apunta a:    {os.readlink(p)}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error stat '{p}': {exc}"


def _tool_ls_dir(args: dict) -> str:
    """Lista el contenido de un directorio con permisos, propietario, tamaño y fecha (estilo ls -la)."""
    import stat as _stat
    p, err = _safe_path(args.get("path", "."))
    if err:
        return err
    if not p.exists():
        return f"Error: no existe: {p}"
    if not p.is_dir():
        return f"Error: '{p}' no es un directorio."
    hidden  = bool(args.get("hidden", False))
    sort_by = args.get("sort", "name")   # name | size | mtime
    try:
        import pwd
        import grp
        entries = list(p.iterdir())
        if not hidden:
            entries = [e for e in entries if not e.name.startswith(".")]
        def _sort_key(e: Path):
            try:
                s = e.lstat()
                if sort_by == "size":
                    return -s.st_size
                if sort_by == "mtime":
                    return -s.st_mtime
            except Exception:
                pass
            return e.name.lower()
        entries.sort(key=_sort_key)
        lines = [f"{p}/\n"]
        total_blocks = 0
        rows = []
        for entry in entries:
            try:
                s = entry.lstat()
                total_blocks += s.st_blocks if hasattr(s, "st_blocks") else 0
                mode = _stat.filemode(s.st_mode)
                try:
                    owner = pwd.getpwuid(s.st_uid).pw_name
                except Exception:
                    owner = str(s.st_uid)
                try:
                    grp_name = grp.getgrgid(s.st_gid).gr_name
                except Exception:
                    grp_name = str(s.st_gid)
                mtime = datetime.datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M")
                name = entry.name + ("/" if entry.is_dir() else "")
                if entry.is_symlink():
                    name += f" -> {os.readlink(entry)}"
                rows.append(f"{mode}  {s.st_nlink:>3}  {owner:<10} {grp_name:<10} {s.st_size:>10}  {mtime}  {name}")
            except Exception:
                rows.append(f"?---------    ?  ?          ?          {entry.name}")
        lines.append(f"total {total_blocks // 2}")
        lines.extend(rows)
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listando '{p}': {exc}"


def _tool_find_file(args: dict) -> str:
    """Busca ficheros que coincidan con un patrón glob en un directorio."""
    p, err = _safe_path(args.get("path", "."))
    if err:
        return err
    if not p.is_dir():
        return f"Error: '{p}' no es un directorio."
    pattern  = args.get("pattern", "*")
    maxdepth = int(args.get("maxdepth", 10))
    max_res  = min(int(args.get("limit", 100)), 500)
    try:
        results = []
        def _walk(d: Path, depth: int):
            if depth > maxdepth or len(results) >= max_res:
                return
            for entry in sorted(d.iterdir()):
                if entry.is_file() and entry.match(pattern):
                    results.append(str(entry))
                if entry.is_dir() and not entry.name.startswith("."):
                    _walk(entry, depth + 1)
        _walk(p, 0)
        if not results:
            return f"Sin resultados para '{pattern}' en {p}"
        header = f"Ficheros '{pattern}' en {p}/ ({len(results)} encontrados):"
        return header + "\n" + "\n".join(results[:max_res])
    except Exception as exc:
        return f"Error buscando '{pattern}': {exc}"


def _tool_find_dir(args: dict) -> str:
    """Busca directorios que coincidan con un patrón glob."""
    p, err = _safe_path(args.get("path", "."))
    if err:
        return err
    if not p.is_dir():
        return f"Error: '{p}' no es un directorio."
    pattern  = args.get("pattern", "*")
    maxdepth = int(args.get("maxdepth", 8))
    max_res  = min(int(args.get("limit", 100)), 500)
    try:
        results = []
        def _walk(d: Path, depth: int):
            if depth > maxdepth or len(results) >= max_res:
                return
            for entry in sorted(d.iterdir()):
                if entry.is_dir():
                    if entry.match(pattern):
                        results.append(str(entry) + "/")
                    if not entry.name.startswith("."):
                        _walk(entry, depth + 1)
        _walk(p, 0)
        if not results:
            return f"Sin resultados para '{pattern}' en {p}"
        return f"Directorios '{pattern}' en {p}/ ({len(results)}):\n" + "\n".join(results[:max_res])
    except Exception as exc:
        return f"Error buscando directorios: {exc}"


def _tool_grep_file(args: dict) -> str:
    """Busca un patrón regex en un fichero con números de línea y contexto."""
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    if not p.exists():
        return f"Error: no existe: {p}"
    if not p.is_file():
        return f"Error: '{p}' no es un fichero."
    pattern     = args.get("pattern", "")
    if not pattern:
        return "Error: 'pattern' requerido."
    context     = max(0, int(args.get("context", 0)))
    ignore_case = bool(args.get("ignore_case", False))
    max_matches = min(int(args.get("limit", 50)), 200)
    try:
        flags = re.IGNORECASE if ignore_case else 0
        rx    = re.compile(pattern, flags)
        lines = p.read_text(errors="replace").splitlines()
        matches: list[int] = [i for i, ln in enumerate(lines) if rx.search(ln)]
        if not matches:
            return f"Sin coincidencias para '{pattern}' en {p.name}"
        shown_lines: set[int] = set()
        for m in matches[:max_matches]:
            for j in range(max(0, m - context), min(len(lines), m + context + 1)):
                shown_lines.add(j)
        output = [f"'{pattern}' en {p.name} ({len(matches)} coincidencias):"]
        prev = -1
        for ln_idx in sorted(shown_lines):
            if prev >= 0 and ln_idx > prev + 1:
                output.append("  ---")
            marker = "→" if ln_idx in set(matches) else " "
            output.append(f"  {marker} {ln_idx + 1:5d}  {lines[ln_idx]}")
            prev = ln_idx
        if len(matches) > max_matches:
            output.append(f"  ... ({len(matches) - max_matches} coincidencias más)")
        return "\n".join(output)
    except re.error as exc:
        return f"Error en patrón regex: {exc}"
    except Exception as exc:
        return f"Error leyendo '{p}': {exc}"


def _tool_chmod_file(args: dict) -> str:
    """Cambia los permisos de un fichero (chmod)."""
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    mode_str = args.get("mode", "")
    if not mode_str:
        return "Error: 'mode' requerido (ej. '644', '755', '600')."
    if not p.exists():
        return f"Error: no existe: {p}"
    try:
        mode = int(mode_str, 8)
    except ValueError:
        return f"Error: modo inválido '{mode_str}'. Usa octal: '644', '755', etc."
    try:
        import stat as _stat
        old_mode = oct(_stat.S_IMODE(p.lstat().st_mode))
        os.chmod(p, mode)
        new_mode = oct(_stat.S_IMODE(p.lstat().st_mode))
        return f"chmod {mode_str}: {p}\n{old_mode} → {new_mode}"
    except Exception as exc:
        return f"Error chmod '{p}': {exc}"


def _tool_chmod_dir(args: dict) -> str:
    """Cambia los permisos de un directorio y opcionalmente su contenido (chmod [-R])."""
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    mode_str  = args.get("mode", "")
    recursive = bool(args.get("recursive", False))
    if not mode_str:
        return "Error: 'mode' requerido (ej. '755', '750')."
    if not p.exists():
        return f"Error: no existe: {p}"
    if not p.is_dir():
        return f"Error: '{p}' no es un directorio."
    try:
        mode = int(mode_str, 8)
    except ValueError:
        return f"Error: modo inválido '{mode_str}'."
    try:
        count = 0
        targets = [p]
        if recursive:
            targets += list(p.rglob("*"))
        for t in targets:
            os.chmod(t, mode)
            count += 1
        suffix = f" (recursivo, {count} entradas)" if recursive else ""
        return f"chmod {mode_str}: {p}{suffix}"
    except Exception as exc:
        return f"Error chmod '{p}': {exc}"


def _tool_chown_file(args: dict) -> str:
    """Cambia el propietario de un fichero (chown user[:group])."""
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    owner = args.get("owner", "")
    if not owner:
        return "Error: 'owner' requerido (ej. 'usuario', 'usuario:grupo')."
    if not p.exists():
        return f"Error: no existe: {p}"
    try:
        import pwd
        import grp
        if ":" in owner:
            u_str, g_str = owner.split(":", 1)
        else:
            u_str, g_str = owner, ""
        uid = pwd.getpwnam(u_str).pw_uid if u_str else -1
        gid = grp.getgrnam(g_str).gr_gid if g_str else -1
        os.chown(p, uid, gid)
        return f"chown {owner}: {p}"
    except KeyError as exc:
        return f"Error: usuario/grupo no encontrado: {exc}"
    except Exception as exc:
        return f"Error chown '{p}': {exc}"


def _tool_chown_dir(args: dict) -> str:
    """Cambia el propietario de un directorio y opcionalmente su contenido (chown [-R])."""
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    owner     = args.get("owner", "")
    recursive = bool(args.get("recursive", False))
    if not owner:
        return "Error: 'owner' requerido."
    if not p.exists():
        return f"Error: no existe: {p}"
    if not p.is_dir():
        return f"Error: '{p}' no es un directorio."
    try:
        import pwd
        import grp
        if ":" in owner:
            u_str, g_str = owner.split(":", 1)
        else:
            u_str, g_str = owner, ""
        uid = pwd.getpwnam(u_str).pw_uid if u_str else -1
        gid = grp.getgrnam(g_str).gr_gid if g_str else -1
        count = 0
        targets = [p]
        if recursive:
            targets += list(p.rglob("*"))
        for t in targets:
            os.chown(t, uid, gid)
            count += 1
        suffix = f" (recursivo, {count} entradas)" if recursive else ""
        return f"chown {owner}: {p}{suffix}"
    except KeyError as exc:
        return f"Error: usuario/grupo no encontrado: {exc}"
    except Exception as exc:
        return f"Error chown '{p}': {exc}"


def _tool_mv_file(args: dict) -> str:
    """Mueve o renombra un fichero o directorio."""
    import shutil
    src_str = args.get("src", "") or args.get("source", "")
    dst_str = args.get("dst", "") or args.get("destination", "")
    if not src_str or not dst_str:
        return "Error: 'src' y 'dst' requeridos."
    src, err = _safe_path(src_str)
    if err:
        return err
    dst, err = _safe_path(dst_str)
    if err:
        return err
    if not src.exists():
        return f"Error: origen no existe: {src}"
    try:
        shutil.move(str(src), str(dst))
        return f"Movido: {src} → {dst}"
    except Exception as exc:
        return f"Error moviendo '{src}': {exc}"


def _tool_cp_file(args: dict) -> str:
    """Copia un fichero o directorio."""
    import shutil
    src_str = args.get("src", "") or args.get("source", "")
    dst_str = args.get("dst", "") or args.get("destination", "")
    if not src_str or not dst_str:
        return "Error: 'src' y 'dst' requeridos."
    src, err = _safe_path(src_str)
    if err:
        return err
    dst, err = _safe_path(dst_str)
    if err:
        return err
    if not src.exists():
        return f"Error: origen no existe: {src}"
    try:
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
            return f"Directorio copiado: {src} → {dst}"
        else:
            dst_resolved = dst
            if dst.is_dir():
                dst_resolved = dst / src.name
            shutil.copy2(str(src), str(dst_resolved))
            return f"Fichero copiado: {src} → {dst_resolved}"
    except Exception as exc:
        return f"Error copiando '{src}': {exc}"


def _tool_rm_file(args: dict) -> str:
    """Elimina un fichero."""
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    if not p.exists() and not p.is_symlink():
        return f"Error: no existe: {p}"
    if p.is_dir():
        return f"Error: '{p}' es un directorio. Usa rm_dir."
    try:
        p.unlink()
        return f"Eliminado: {p}"
    except Exception as exc:
        return f"Error eliminando '{p}': {exc}"


def _tool_rm_dir(args: dict) -> str:
    """Elimina un directorio vacío, o recursivamente si recursive=true."""
    import shutil
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    if not p.exists():
        return f"Error: no existe: {p}"
    if not p.is_dir():
        return f"Error: '{p}' no es un directorio. Usa rm_file."
    recursive = bool(args.get("recursive", False))
    try:
        if recursive:
            shutil.rmtree(str(p))
            return f"Directorio eliminado (recursivo): {p}"
        else:
            p.rmdir()
            return f"Directorio vacío eliminado: {p}"
    except OSError as exc:
        hint = " (¿no está vacío? Usa recursive=true)" if "not empty" in str(exc).lower() else ""
        return f"Error eliminando '{p}': {exc}{hint}"
    except Exception as exc:
        return f"Error eliminando '{p}': {exc}"


def _tool_mkdir_dir(args: dict) -> str:
    """Crea un directorio (y los padres necesarios, como mkdir -p)."""
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    mode_str = args.get("mode", "755")
    try:
        mode = int(mode_str, 8)
    except ValueError:
        return f"Error: modo inválido '{mode_str}'."
    try:
        p.mkdir(parents=True, exist_ok=True, mode=mode)
        return f"Directorio creado: {p}  (modo {mode_str})"
    except Exception as exc:
        return f"Error creando '{p}': {exc}"


def _tool_touch_file(args: dict) -> str:
    """Crea un fichero vacío o actualiza su fecha de modificación (touch)."""
    p, err = _safe_path(args.get("path", ""))
    if err:
        return err
    try:
        existed = p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        action = "Actualizado" if existed else "Creado"
        return f"{action}: {p}"
    except Exception as exc:
        return f"Error touch '{p}': {exc}"


# ── Debug de procesos ────────────────────────────────────────────────────────

def _run_debug(cmd: list[str], timeout: int, cwd: str | None = None) -> str:
    """Helper compartido: ejecuta comando de debug y devuelve stdout+stderr limitados."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=cwd or os.getcwd(),
            start_new_session=True,
        )
        out = (r.stdout or "") + (r.stderr or "")
        lines = out.splitlines()
        if len(lines) > 600:
            lines = lines[:600] + [f"… ({len(lines)-600} líneas más omitidas)"]
        header = f"[exit {r.returncode}]  {' '.join(cmd[:3])}\n"
        return header + "\n".join(lines)
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s) ejecutando: {' '.join(cmd[:3])}"
    except FileNotFoundError:
        return f"Comando no encontrado: {cmd[0]}. Instálalo primero."
    except Exception as exc:
        return f"Error: {exc}"


def _tool_strace_run(args: dict) -> str:
    """Traza syscalls de un comando o de un PID existente con strace."""
    command   = args.get("command", "")       # ej. "ls /tmp"
    pid       = args.get("pid", "")           # PID para attach
    syscalls  = args.get("syscalls", "")      # filtro: "open,read,write"
    timeout   = min(int(args.get("timeout", 15)), 60)
    count     = args.get("count", False)      # -c: summary estadístico

    if not command and not pid:
        return "Error: proporciona 'command' (ej. 'ls /tmp') o 'pid' (PID del proceso)."

    cmd = ["strace"]
    if count:
        cmd.append("-c")
    if syscalls:
        cmd += ["-e", f"trace={syscalls}"]
    cmd += ["-f", "-s", "256"]

    if pid:
        cmd += ["-p", str(pid)]
        # strace -p no ejecuta nada, necesita SIGINT para parar -> timeout forzado
        cmd = ["timeout", str(timeout)] + cmd
        return _run_debug(cmd, timeout + 5)
    else:
        parts = command.split()
        cmd += parts
        return _run_debug(cmd, timeout)


def _tool_gdb_run(args: dict) -> str:
    """Ejecuta GDB en modo batch sobre un binario con comandos GDB."""
    binary   = args.get("binary", "")     # ruta al binario
    core     = args.get("core", "")       # fichero core dump (opcional)
    commands = args.get("commands", "")   # comandos GDB separados por \n
    args_bin = args.get("args", "")       # argumentos para el binario
    timeout  = min(int(args.get("timeout", 30)), 120)
    cwd      = args.get("directory", os.getcwd())

    if not binary:
        return "Error: proporciona 'binary' con la ruta al ejecutable."

    # Construir fichero de comandos temporal
    default_cmds = "info registers\nbacktrace full\nquit"
    gdb_cmds = commands if commands else default_cmds

    with _tempfile.NamedTemporaryFile(mode="w", suffix=".gdb", delete=False,
                                          dir=_get_tmp_dir()) as f:
        f.write(gdb_cmds + "\n")
        cmd_file = f.name

    try:
        cmd = ["gdb", "--batch", "--command", cmd_file, binary]
        if core:
            cmd.append(core)
        elif args_bin:
            cmd += ["--args"] + args_bin.split()
        return _run_debug(cmd, timeout, cwd=cwd)
    finally:
        try:
            os.unlink(cmd_file)
        except OSError:
            pass


def _tool_pdb_run(args: dict) -> str:
    """Ejecuta un script Python bajo pdb con comandos (no interactivo)."""
    script   = args.get("script", "")    # ruta al script
    commands = args.get("commands", "")  # comandos pdb: "b 10\nr\np var\nq"
    env_vars = args.get("env", {})       # variables de entorno adicionales
    timeout  = min(int(args.get("timeout", 30)), 120)

    if not script:
        return "Error: proporciona 'script' con la ruta al script Python."
    if not Path(script).exists():
        return f"Error: el script '{script}' no existe."

    default_cmds = "l\nbt\nq"
    pdb_input = (commands if commands else default_cmds).replace("\\n", "\n")

    env = {**os.environ, **(env_vars or {})}

    with _tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                          dir=_get_tmp_dir()) as f:
        f.write(pdb_input + "\n")
        input_file = f.name

    try:
        with open(input_file) as stdin_f:
            r = subprocess.run(
                [sys.executable, "-m", "pdb", script],
                stdin=stdin_f, capture_output=True, text=True,
                timeout=timeout, env=env, cwd=str(Path(script).parent),
            )
        out = (r.stdout or "") + (r.stderr or "")
        lines = out.splitlines()
        if len(lines) > 300:
            lines = lines[:300] + ["… (recortado)"]
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s) ejecutando pdb sobre '{script}'."
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        try:
            os.unlink(input_file)
        except OSError:
            pass


def _tool_valgrind_run(args: dict) -> str:
    """Analiza memoria de un binario con Valgrind memcheck."""
    binary   = args.get("binary", "")    # ruta al binario
    bin_args = args.get("args", "")      # argumentos del binario
    tool     = args.get("tool", "memcheck")  # memcheck, callgrind, helgrind, massif
    timeout  = min(int(args.get("timeout", 60)), 300)
    cwd      = args.get("directory", os.getcwd())

    if not binary:
        return "Error: proporciona 'binary' con la ruta al ejecutable."

    cmd = [
        "valgrind",
        f"--tool={tool}",
        "--error-exitcode=1",
        "--leak-check=full" if tool == "memcheck" else "",
        "--show-leak-kinds=all" if tool == "memcheck" else "",
        binary,
    ]
    cmd = [c for c in cmd if c]  # eliminar cadenas vacías
    if bin_args:
        cmd += bin_args.split()

    return _run_debug(cmd, timeout, cwd=cwd)


# ── Build y ejecución ─────────────────────────────────────────────────────────

def _tool_make_run(args: dict) -> str:
    """Ejecuta un target de Makefile con salida completa."""
    target    = args.get("target", "")    # target Make (vacío = target por defecto)
    directory = args.get("directory", os.getcwd())
    jobs      = args.get("jobs", 0)       # -j N (0 = no flag)
    timeout   = min(int(args.get("timeout", 120)), 600)
    extra     = args.get("vars", "")      # ej. "DEBUG=1 PREFIX=/usr/local"

    if not Path(directory).is_dir():
        return f"Error: directorio '{directory}' no existe."
    makefile_exists = any(
        (Path(directory) / f).exists()
        for f in ("Makefile", "makefile", "GNUmakefile")
    )
    if not makefile_exists:
        return f"No se encontró Makefile en '{directory}'."

    cmd = ["make"]
    if jobs:
        cmd += [f"-j{int(jobs)}"]
    if target:
        cmd.append(target)
    if extra:
        cmd += extra.split()

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=directory,
        )
        out = (r.stdout or "") + (r.stderr or "")
        lines = out.splitlines()
        if len(lines) > 500:
            lines = lines[:500] + [f"… ({len(lines)-500} líneas más)"]
        status = "OK" if r.returncode == 0 else f"FALLO (exit {r.returncode})"
        return f"[make {target or '(default)'}]  {status}\n\n" + "\n".join(lines)
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s) ejecutando make."
    except Exception as exc:
        return f"Error: {exc}"


def _tool_run_script(args: dict) -> str:
    """Ejecuta un script (Python, bash, sh, node, ruby) con timeout."""
    script      = args.get("script", "")    # ruta al script
    script_args = args.get("args", "")      # argumentos del script
    interpreter = args.get("interpreter", "")  # forzar: python3, bash, node...
    directory   = args.get("directory", "")
    env_extra   = args.get("env", {})       # vars de entorno adicionales
    timeout     = min(int(args.get("timeout", 60)), 300)

    if not script:
        return "Error: proporciona 'script' con la ruta al script."

    p = Path(script)
    if not p.exists():
        return f"Error: el script '{script}' no existe."

    cwd = directory if directory and Path(directory).is_dir() else str(p.parent)

    # Auto-detectar intérprete
    if not interpreter:
        ext = p.suffix.lower()
        interp_map = {
            ".py": sys.executable,
            ".sh": "bash", ".bash": "bash",
            ".js": "node", ".mjs": "node",
            ".rb": "ruby", ".pl": "perl",
            ".php": "php",
        }
        interpreter = interp_map.get(ext, "bash")

    cmd = [interpreter, str(p)]
    if script_args:
        cmd += script_args.split()

    env = {**os.environ, **(env_extra or {})}

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=cwd, env=env,
        )
        out = r.stdout or ""
        err = r.stderr or ""
        parts = []
        if out.strip():
            lines = out.splitlines()
            if len(lines) > 400:
                lines = lines[:400] + ["… (recortado)"]
            parts.append("STDOUT:\n" + "\n".join(lines))
        if err.strip():
            elines = err.splitlines()
            if len(elines) > 200:
                elines = elines[:200] + ["… (recortado)"]
            parts.append("STDERR:\n" + "\n".join(elines))
        status = "OK" if r.returncode == 0 else f"FALLO (exit {r.returncode})"
        return f"[{interpreter} {p.name}]  {status}\n\n" + "\n\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s) ejecutando '{script}'."
    except FileNotFoundError:
        return f"Intérprete no encontrado: {interpreter}"
    except Exception as exc:
        return f"Error: {exc}"


def _tool_format_code(args: dict) -> str:
    """Formatea código con black/prettier/gofmt/rustfmt/isort/clang-format."""
    path    = args.get("path", "")     # fichero o directorio
    tool    = args.get("tool", "auto") # auto | black | isort | prettier | gofmt | rustfmt | clang-format
    check   = args.get("check", False) # solo verificar, no modificar
    timeout = 60

    if not path:
        return "Error: proporciona 'path' al fichero o directorio."
    p = Path(path)
    if not p.exists():
        return f"Error: '{path}' no existe."

    ext = p.suffix.lower() if p.is_file() else ""

    # Auto-detectar herramienta
    if tool == "auto":
        if ext in (".py",):
            tool = "black"
        elif ext in (".js", ".ts", ".jsx", ".tsx", ".json", ".css", ".html", ".md"):
            tool = "prettier"
        elif ext == ".go":
            tool = "gofmt"
        elif ext == ".rs":
            tool = "rustfmt"
        elif ext in (".c", ".cpp", ".h", ".cc", ".cxx"):
            tool = "clang-format"
        elif ext == ".php":
            tool = "php-cs-fixer"
        else:
            return f"No se pudo auto-detectar formateador para '{ext}'. Especifica 'tool'."

    if tool == "black":
        cmd = [sys.executable, "-m", "black"]
        if check:
            cmd.append("--check")
        cmd.append(str(p))
    elif tool == "isort":
        cmd = [sys.executable, "-m", "isort"]
        if check:
            cmd.append("--check")
        cmd.append(str(p))
    elif tool == "prettier":
        cmd = ["prettier", "--write" if not check else "--check", str(p)]
    elif tool == "gofmt":
        if check:
            cmd = ["gofmt", "-l", str(p)]
        else:
            cmd = ["gofmt", "-w", str(p)]
    elif tool == "rustfmt":
        cmd = ["rustfmt"]
        if check:
            cmd.append("--check")
        cmd.append(str(p))
    elif tool == "clang-format":
        cmd = ["clang-format", "-i" if not check else "--dry-run", str(p)]
    elif tool == "php-cs-fixer":
        cmd = ["php-cs-fixer", "fix", "--using-cache=no",
               "--rules=@PSR12" if not check else "--dry-run",
               str(p)]
        if check:
            cmd = ["php-cs-fixer", "fix", "--dry-run", "--using-cache=no",
                   "--rules=@PSR12", str(p)]
    else:
        return f"Herramienta desconocida: {tool}"

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            action = "verificado" if check else "formateado"
            return f"OK: {path} {action} con {tool}.\n{out.strip()}"
        else:
            return f"Error {tool} (exit {r.returncode}):\n{out.strip()}"
    except FileNotFoundError:
        return f"'{tool}' no está instalado. Instálalo con pip install {tool} o similar."
    except subprocess.TimeoutExpired:
        return f"Timeout ejecutando {tool}."
    except Exception as exc:
        return f"Error: {exc}"


def _tool_mypy_check(args: dict) -> str:
    """Comprueba tipos con mypy sobre un fichero o directorio."""
    path    = args.get("path", ".")
    strict  = args.get("strict", False)
    ignore_missing = args.get("ignore_missing_imports", True)
    timeout = 120

    cmd = [sys.executable, "-m", "mypy", str(path)]
    if strict:
        cmd.append("--strict")
    if ignore_missing:
        cmd.append("--ignore-missing-imports")
    cmd += ["--pretty", "--show-error-codes"]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        lines = out.splitlines()
        if len(lines) > 300:
            lines = lines[:300] + [f"… ({len(lines)-300} líneas más)"]
        status = "Sin errores de tipos" if r.returncode == 0 else f"Errores encontrados (exit {r.returncode})"
        return f"mypy {path}  —  {status}\n\n" + "\n".join(lines)
    except FileNotFoundError:
        return "mypy no está instalado. Instálalo con: pip install mypy"
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s) ejecutando mypy."
    except Exception as exc:
        return f"Error: {exc}"


# ── Python tools ──────────────────────────────────────────────────────────────

def _tool_python_exec(args: dict) -> str:
    """Ejecuta un fragmento de código Python y captura stdout/stderr."""
    code      = args.get("code", "")
    timeout   = min(int(args.get("timeout", 15)), 60)
    env_extra = args.get("env") or {}
    workdir   = args.get("workdir") or None

    if not code:
        return "Error: proporciona 'code' con el código Python a ejecutar."

    if workdir:
        workdir = str(Path(workdir).expanduser())
        if not Path(workdir).is_dir():
            return f"Error: workdir '{workdir}' no existe o no es un directorio."
    cwd = workdir or os.getcwd()

    env = {**os.environ, **env_extra} if env_extra else None

    with _tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False,
                                          dir=_get_tmp_dir()) as f:
        f.write(code)
        tmp = f.name

    try:
        r = subprocess.run(
            [sys.executable, tmp],
            capture_output=True, text=True, timeout=timeout,
            cwd=cwd, env=env,
        )
        out = r.stdout or ""
        err = r.stderr or ""
        parts = []
        if out.strip():
            parts.append("STDOUT:\n" + out.strip()[:4000])
        if err.strip():
            parts.append("STDERR:\n" + err.strip()[:2000])
        if not parts:
            parts.append("(sin salida)")
        status = "OK" if r.returncode == 0 else f"exit {r.returncode}"
        return f"[python_exec]  {status}\n\n" + "\n\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s) ejecutando el snippet Python."
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _tool_pip_tool(args: dict) -> str:
    """Gestión de paquetes pip: list/show/install/freeze/check/outdated."""
    action   = args.get("action", "list")    # list | show | install | freeze | check | outdated
    packages = args.get("packages", "")      # nombres de paquetes separados por espacios
    timeout  = 120

    valid_actions = {"list", "show", "install", "freeze", "check", "outdated"}
    if action not in valid_actions:
        return f"Acción desconocida: {action}. Válidas: {', '.join(sorted(valid_actions))}"

    if action == "list":
        cmd = [sys.executable, "-m", "pip", "list", "--format=columns"]
    elif action == "show":
        if not packages:
            return "Error: 'packages' es obligatorio para 'show'."
        cmd = [sys.executable, "-m", "pip", "show"] + packages.split()
    elif action == "install":
        if not packages:
            return "Error: 'packages' es obligatorio para 'install'."
        cmd = [sys.executable, "-m", "pip", "install"] + packages.split()
    elif action == "freeze":
        cmd = [sys.executable, "-m", "pip", "freeze"]
    elif action == "check":
        cmd = [sys.executable, "-m", "pip", "check"]
    elif action == "outdated":
        cmd = [sys.executable, "-m", "pip", "list", "--outdated", "--format=columns"]
    else:
        cmd = [sys.executable, "-m", "pip", action]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        lines = out.splitlines()
        if len(lines) > 300:
            lines = lines[:300] + ["… (recortado)"]
        status = "OK" if r.returncode == 0 else f"exit {r.returncode}"
        return f"[pip {action}]  {status}\n\n" + "\n".join(lines)
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s) ejecutando pip {action}."
    except Exception as exc:
        return f"Error: {exc}"


# ── Node.js tools ─────────────────────────────────────────────────────────────

def _tool_npm_tool(args: dict) -> str:
    """Gestión de paquetes npm: list/run/info/install/audit/outdated."""
    action    = args.get("action", "list")   # list | run | info | install | audit | outdated
    packages  = args.get("packages", "")     # paquetes o nombre del script
    directory = args.get("directory", os.getcwd())
    timeout   = 120

    valid_actions = {"list", "run", "info", "install", "audit", "outdated", "ci"}
    if action not in valid_actions:
        return f"Acción desconocida: {action}. Válidas: {', '.join(sorted(valid_actions))}"

    if not Path(directory).is_dir():
        return f"Error: directorio '{directory}' no existe."

    if action == "list":
        cmd = ["npm", "list", "--depth=1"]
    elif action == "run":
        if not packages:
            cmd = ["npm", "run"]
        else:
            cmd = ["npm", "run"] + packages.split()
    elif action == "info":
        if not packages:
            return "Error: 'packages' es obligatorio para 'info'."
        cmd = ["npm", "info"] + packages.split()
    elif action == "install":
        if packages:
            cmd = ["npm", "install"] + packages.split()
        else:
            cmd = ["npm", "install"]
    elif action == "audit":
        cmd = ["npm", "audit"]
    elif action == "outdated":
        cmd = ["npm", "outdated"]
    elif action == "ci":
        cmd = ["npm", "ci"]
    else:
        cmd = ["npm", action]

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=directory,
        )
        out = (r.stdout or "") + (r.stderr or "")
        lines = out.splitlines()
        if len(lines) > 300:
            lines = lines[:300] + ["… (recortado)"]
        status = "OK" if r.returncode == 0 else f"exit {r.returncode}"
        return f"[npm {action}]  {status}\n\n" + "\n".join(lines)
    except FileNotFoundError:
        return "npm no está instalado."
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s) ejecutando npm {action}."
    except Exception as exc:
        return f"Error: {exc}"


# ── Archive tools ─────────────────────────────────────────────────────────────

def _tool_archive_extract(args: dict) -> str:
    """Extrae tar, zip, tar.gz, tar.bz2, tar.xz."""
    archive = args.get("archive", "")
    dest    = args.get("destination", "")
    strip   = int(args.get("strip_components", 0))

    if not archive:
        return "Error: proporciona 'archive' con la ruta al archivo."
    p = Path(archive)
    if not p.exists():
        return f"Error: '{archive}' no existe."

    dest_path = Path(dest) if dest else p.parent
    dest_path.mkdir(parents=True, exist_ok=True)

    name = p.name.lower()
    try:
        if name.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(p) as zf:
                members = zf.namelist()
                zf.extractall(dest_path)
            return f"Extraídos {len(members)} ficheros en '{dest_path}'."
        elif any(name.endswith(s) for s in (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")):
            cmd = ["tar", "xf", str(p), "-C", str(dest_path)]
            if strip:
                cmd += [f"--strip-components={strip}"]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                return f"Error tar: {r.stderr.strip()}"
            return f"Extraído '{p.name}' en '{dest_path}'."
        elif name.endswith(".gz"):
            import gzip
            out_path = dest_path / p.stem
            with gzip.open(p) as fin, open(out_path, "wb") as fout:
                fout.write(fin.read())
            return f"Descomprimido '{p.name}' → '{out_path}'."
        elif name.endswith((".bz2", ".xz")):
            cmd = ["tar", "xf", str(p), "-C", str(dest_path)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                return f"Error: {r.stderr.strip()}"
            return f"Extraído '{p.name}' en '{dest_path}'."
        else:
            return f"Formato de archivo no reconocido: {p.suffix}. Soportados: .zip, .tar.gz, .tgz, .tar.bz2, .tar.xz, .tar, .gz"
    except Exception as exc:
        return f"Error al extraer '{archive}': {exc}"


def _tool_archive_create(args: dict) -> str:
    """Crea archivos tar.gz, tar.bz2, tar.xz o zip."""
    archive  = args.get("archive", "")     # ruta de salida, ej. "project.tar.gz"
    sources  = args.get("sources", "")     # ficheros/dirs separados por espacios
    compress = args.get("compress", "gz")  # gz | bz2 | xz | zip | none
    timeout  = 120

    if not archive:
        return "Error: proporciona 'archive' con la ruta de salida."
    if not sources:
        return "Error: proporciona 'sources' con ficheros/directorios a comprimir."

    src_list = sources.split()
    missing  = [s for s in src_list if not Path(s).exists()]
    if missing:
        return f"Error: no existen: {', '.join(missing)}"

    out = Path(archive)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        if compress == "zip":
            import zipfile
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                for src in src_list:
                    sp = Path(src)
                    if sp.is_dir():
                        for fp in sp.rglob("*"):
                            if fp.is_file():
                                zf.write(fp, fp.relative_to(sp.parent))
                    else:
                        zf.write(sp, sp.name)
            return f"Creado '{archive}'."
        else:
            flag_map = {"gz": "z", "bz2": "j", "xz": "J", "none": ""}
            flag = flag_map.get(compress, "z")
            cmd = ["tar", f"-c{flag}f", str(out)] + src_list
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode != 0:
                return f"Error tar: {r.stderr.strip()}"
            size = out.stat().st_size
            return f"Creado '{archive}' ({size // 1024} KB)."
    except Exception as exc:
        return f"Error creando '{archive}': {exc}"


def _tool_archive_list(args: dict) -> str:
    """Lista el contenido de un archivo comprimido."""
    archive  = args.get("archive", "")
    max_lines = min(int(args.get("max_lines", 200)), 1000)

    if not archive:
        return "Error: proporciona 'archive'."
    p = Path(archive)
    if not p.exists():
        return f"Error: '{archive}' no existe."

    name = p.name.lower()
    try:
        if name.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(p) as zf:
                entries = zf.infolist()
            lines = []
            for e in entries[:max_lines]:
                size = f"{e.file_size:>10,}" if e.file_size else ""
                lines.append(f"{size}  {e.filename}")
            if len(entries) > max_lines:
                lines.append(f"… ({len(entries) - max_lines} más)")
            return f"{len(entries)} entradas en '{p.name}':\n" + "\n".join(lines)
        elif any(name.endswith(s) for s in (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")):
            r = subprocess.run(
                ["tar", "tvf", str(p)],
                capture_output=True, text=True, timeout=30,
            )
            lines = r.stdout.splitlines()
            total = len(lines)
            if total > max_lines:
                lines = lines[:max_lines] + [f"… ({total - max_lines} más)"]
            return f"{total} entradas en '{p.name}':\n" + "\n".join(lines)
        else:
            return f"Formato no soportado para listar: {p.suffix}"
    except Exception as exc:
        return f"Error: {exc}"


# ── Metadatos de ficheros ─────────────────────────────────────────────────────

def _tool_file_stat(args: dict) -> str:
    """Metadatos completos de un fichero: permisos, propietario, tiempos, inode."""
    import grp
    import pwd
    import stat as stat_mod

    path = args.get("path", "")
    if not path:
        return "Error: proporciona 'path'."

    p = Path(path)
    if not p.exists() and not p.is_symlink():
        return f"Error: '{path}' no existe."

    try:
        st = p.lstat()  # lstat para no seguir symlinks
        mode      = st.st_mode
        perms     = stat_mod.filemode(mode)
        ftype     = "symlink" if p.is_symlink() else ("dir" if p.is_dir() else "file")
        size      = st.st_size
        inode     = st.st_ino
        nlinks    = st.st_nlink
        uid, gid  = st.st_uid, st.st_gid
        try:
            owner = pwd.getpwuid(uid).pw_name
        except KeyError:
            owner = str(uid)
        try:
            group = grp.getgrgid(gid).gr_name
        except KeyError:
            group = str(gid)

        import datetime as dt
        atime = dt.datetime.fromtimestamp(st.st_atime).strftime("%Y-%m-%d %H:%M:%S")
        mtime = dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        ctime = dt.datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"Ruta:        {p.resolve() if not p.is_symlink() else p}",
            f"Tipo:        {ftype}",
            f"Permisos:    {perms}  ({oct(mode & 0o7777)})",
            f"Propietario: {owner} ({uid})  /  {group} ({gid})",
            f"Tamaño:      {size:,} bytes",
            f"Inodo:       {inode}",
            f"Nlinks:      {nlinks}",
            f"Modificado:  {mtime}",
            f"Accedido:    {atime}",
            f"Cambiado:    {ctime}",
        ]
        # Contar líneas para ficheros de texto (alternativa a wc -l)
        if ftype == "file" and size > 0 and size < 50 * 1024 * 1024:
            try:
                with open(p, "rb") as fh:
                    nlines = sum(1 for _ in fh)
                lines.append(f"Líneas:      {nlines:,}")
            except OSError:
                pass
        if p.is_symlink():
            target = os.readlink(p)
            resolved = p.resolve()
            lines.append(f"Destino:     {target}")
            lines.append(f"Resuelto:    {resolved}")

        return "\n".join(lines)
    except Exception as exc:
        return f"Error stat '{path}': {exc}"


def _tool_symlink_create(args: dict) -> str:
    """Crea un enlace simbólico (ln -s target link_path)."""
    target    = args.get("target", "")
    link_path = args.get("link_path", "")
    force     = args.get("force", False)

    if not target or not link_path:
        return "Error: proporciona 'target' y 'link_path'."

    lp = Path(link_path)
    if lp.exists() or lp.is_symlink():
        if not force:
            return f"Error: '{link_path}' ya existe. Usa force=true para reemplazar."
        lp.unlink()

    try:
        lp.symlink_to(target)
        return f"Enlace simbólico creado: {link_path} → {target}"
    except Exception as exc:
        return f"Error creando symlink: {exc}"


def _tool_readlink(args: dict) -> str:
    """Resuelve el destino de un enlace simbólico."""
    path     = args.get("path", "")
    resolve  = args.get("resolve", True)  # True = ruta absoluta final

    if not path:
        return "Error: proporciona 'path'."

    p = Path(path)
    if not p.is_symlink():
        if p.exists():
            return f"'{path}' no es un enlace simbólico (es {('directorio' if p.is_dir() else 'fichero')})."
        return f"'{path}' no existe."

    try:
        direct = os.readlink(p)
        lines  = [f"Enlace:  {path}", f"Destino: {direct}"]
        if resolve:
            resolved = p.resolve()
            lines.append(f"Resuelto: {resolved}")
            lines.append(f"Existe:   {resolved.exists()}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error readlink '{path}': {exc}"


# ── Parches ───────────────────────────────────────────────────────────────────

def _tool_patch_apply(args: dict) -> str:
    """Aplica un diff unificado a ficheros del proyecto."""
    patch_text = args.get("patch", "")        # contenido del diff unificado
    patch_file = args.get("patch_file", "")   # o ruta a un fichero .patch
    directory  = args.get("directory", os.getcwd())
    dry_run    = args.get("dry_run", False)
    strip      = int(args.get("strip", 1))    # -p nivel (1 = quita el a/ b/)

    if not patch_text and not patch_file:
        return "Error: proporciona 'patch' (texto) o 'patch_file' (ruta al fichero)."
    if not Path(directory).is_dir():
        return f"Error: directorio '{directory}' no existe."

    tmp_patch = None

    try:
        if patch_text:
            with _tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False,
                                                  dir=_get_tmp_dir()) as f:
                f.write(patch_text)
                tmp_patch = f.name
            patch_src = tmp_patch
        else:
            patch_src = patch_file

        cmd = ["patch", f"-p{strip}", "--input", patch_src]
        if dry_run:
            cmd.append("--dry-run")

        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=60, cwd=directory,
        )
        out = (r.stdout or "") + (r.stderr or "")
        action = "[dry-run]" if dry_run else "[aplicado]"
        status = "OK" if r.returncode == 0 else f"FALLO (exit {r.returncode})"
        return f"patch {action}  {status}\n\n{out.strip()}"
    except FileNotFoundError:
        return "El comando 'patch' no está instalado."
    except subprocess.TimeoutExpired:
        return "Timeout aplicando el patch."
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        if tmp_patch:
            try:
                os.unlink(tmp_patch)
            except OSError:
                pass


def _tool_regex_replace(args: dict) -> str:
    """Reemplaza un patrón regex en un fichero con re.sub(). Muestra diff."""
    file_path   = args.get("file", "").strip()
    pattern     = args.get("pattern", "")
    replacement = args.get("replacement", "")
    flags_str   = args.get("flags", "")
    count       = int(args.get("count", 0))
    dry_run     = bool(args.get("dry_run", False))
    backup      = bool(args.get("backup", False))

    if not file_path or not pattern:
        return "Error: 'file' y 'pattern' son obligatorios."

    path = Path(file_path)
    if not path.exists():
        return f"Error: '{file_path}' no existe."
    if not path.is_file():
        return f"Error: '{file_path}' no es un fichero."

    # Parsear flags
    flags = 0
    for f in flags_str.upper().replace("|", ",").split(","):
        f = f.strip()
        if f in ("MULTILINE", "M"):
            flags |= re.MULTILINE
        elif f in ("IGNORECASE", "I"):
            flags |= re.IGNORECASE
        elif f in ("DOTALL", "S"):
            flags |= re.DOTALL

    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error leyendo '{file_path}': {e}"

    try:
        if count:
            new_content, n = re.subn(pattern, replacement, original, count=count, flags=flags)
        else:
            new_content, n = re.subn(pattern, replacement, original, flags=flags)
    except re.error as e:
        return f"Error en regex '{pattern}': {e}"

    if n == 0:
        return f"No se encontraron coincidencias de '{pattern}' en '{path.name}'."

    # Diff compacto para mostrar los cambios
    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
        n=3,
    ))
    diff_str = "".join(diff_lines)
    if len(diff_str) > 4000:
        diff_str = diff_str[:4000] + "\n... (diff truncado)"

    if dry_run:
        return f"[dry-run] {n} reemplazos en '{path.name}':\n\n{diff_str}"

    if backup:
        bak = path.with_suffix(path.suffix + ".bak")
        bak.write_text(original, encoding="utf-8")

    try:
        path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return f"Error escribiendo '{file_path}': {e}"

    bak_note = f"  (backup: {path.with_suffix(path.suffix + '.bak')})" if backup else ""
    return f"OK — {n} reemplazos en '{path.name}'{bak_note}\n\n{diff_str}"


def _tool_tree(args: dict) -> str:
    """Muestra la estructura jerárquica de un directorio (estilo tree)."""
    import shutil as _sh
    directory    = args.get("directory", ".") or "."
    depth        = min(int(args.get("depth", 3)), 10)
    show_hidden  = bool(args.get("show_hidden", False))
    dirs_only    = bool(args.get("dirs_only", False))
    max_entries  = min(int(args.get("max_entries", 300)), 1000)

    root = Path(directory).expanduser().resolve()
    if not root.exists():
        return f"Error: '{directory}' no existe."
    if not root.is_dir():
        return f"Error: '{directory}' no es un directorio."

    # Intentar tree nativo primero
    if _sh.which("tree"):
        cmd = ["tree", "-L", str(depth), "--noreport", "-F"]
        if show_hidden:
            cmd.append("-a")
        if dirs_only:
            cmd.append("-d")
        cmd.append(str(root))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                out = r.stdout
                if len(out) > 8000:
                    out = out[:8000] + "\n… (truncado)"
                return out
        except Exception:
            pass

    # Fallback Python
    lines: list[str] = [str(root) + "/"]
    count = [0]

    def _walk(path: Path, prefix: str, cur_depth: int) -> None:
        if cur_depth > depth or count[0] >= max_entries:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return
        if not show_hidden:
            entries = [e for e in entries if not e.name.startswith(".")]
        if dirs_only:
            entries = [e for e in entries if e.is_dir()]
        for i, entry in enumerate(entries):
            if count[0] >= max_entries:
                lines.append(prefix + "└── … (truncado)")
                return
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            suffix = "/" if entry.is_dir() else ""
            if entry.is_symlink():
                try:
                    suffix += f" -> {os.readlink(entry)}"
                except OSError:
                    pass
            lines.append(prefix + connector + entry.name + suffix)
            count[0] += 1
            if entry.is_dir() and cur_depth < depth:
                ext = "    " if is_last else "│   "
                _walk(entry, prefix + ext, cur_depth + 1)

    _walk(root, "", 1)
    if count[0] >= max_entries:
        lines.append(f"\n… ({max_entries}+ entradas — aumenta max_entries o reduce depth)")
    return "\n".join(lines)


def _tool_analyze_codebase(args: dict) -> str:
    """Análisis estructurado de una sección del proyecto antes de empezar a trabajar.

    Combina: estructura de directorios + conteo de ficheros por lenguaje + ficheros
    recientes + búsqueda de patrones clave. Diseñado para dar al agente un mapa
    completo antes de hacer cambios, sin necesidad de usar bash.
    """
    directory  = args.get("directory", ".") or "."
    pattern    = args.get("pattern", "")          # búsqueda opcional de patrón
    extensions = args.get("extensions", "")       # "c,h,cpp" → filtrar extensiones
    max_files  = min(int(args.get("max_files", 10)), 50)
    depth      = min(int(args.get("depth", 2)), 5)

    root = Path(directory).expanduser().resolve()
    if not root.exists():
        return f"Error: directorio '{directory}' no existe."
    if not root.is_dir():
        return f"Error: '{directory}' no es un directorio."

    sections: list[str] = [f"# Análisis: {root}\n"]

    # ── 1. Conteo de ficheros por extensión ──────────────────────────────────
    _SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache",
             "dist", "build", ".eggs", "target", ".cache"}
    ext_counts: dict[str, int] = {}
    total_files = 0
    for f in root.rglob("*"):
        if any(p in f.parts for p in _SKIP):
            continue
        if f.is_file():
            total_files += 1
            ext = f.suffix.lower() or "(sin ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

    top_exts = sorted(ext_counts.items(), key=lambda x: -x[1])[:12]
    sections.append(f"## Ficheros ({total_files} total)\n")
    for ext, n in top_exts:
        bar = "█" * min(n * 20 // max(top_exts[0][1], 1), 20)
        sections.append(f"  {ext:10s}  {n:5d}  {bar}")

    # ── 2. Estructura de directorios (depth limitado) ────────────────────────
    sections.append(f"\n\n## Estructura (depth={depth})\n")
    lines: list[str] = [str(root) + "/"]
    _count = [0]

    def _walk(path: Path, prefix: str, cur_depth: int) -> None:
        if cur_depth > depth or _count[0] >= 60:
            return
        try:
            entries = sorted(
                [e for e in path.iterdir() if not e.name.startswith(".")
                 and e.name not in _SKIP],
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            if _count[0] >= 60:
                lines.append(f"{prefix}… (+más)")
                break
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            _count[0] += 1
            if entry.is_dir():
                child_prefix = prefix + ("    " if is_last else "│   ")
                _walk(entry, child_prefix, cur_depth + 1)

    _walk(root, "", 1)
    sections.append("\n".join(lines))

    # ── 3. Ficheros recientes (últimos modificados) ──────────────────────────
    sections.append(f"\n\n## Ficheros recientes (últimos {max_files})\n")
    try:
        ext_filter = {("." + e.lstrip(".").lower()) for e in extensions.split(",") if e.strip()} if extensions else set()
        all_files = sorted(
            (f for f in root.rglob("*")
             if f.is_file()
             and not any(p in f.parts for p in _SKIP)
             and (not ext_filter or f.suffix.lower() in ext_filter)),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:max_files]
        import datetime as _dt
        now_ts = _dt.datetime.now().timestamp()
        for f in all_files:
            age_s = now_ts - f.stat().st_mtime
            age = (f"{int(age_s//60)}m" if age_s < 3600
                   else f"{int(age_s//3600)}h" if age_s < 86400
                   else f"{int(age_s//86400)}d")
            rel = f.relative_to(root) if f.is_relative_to(root) else f
            sections.append(f"  {age:>5}  {rel}")
    except Exception as exc:
        sections.append(f"  (error listando ficheros: {exc})")

    # ── 4. Búsqueda de patrón (si se proporcionó) ────────────────────────────
    if pattern:
        sections.append(f"\n\n## Búsqueda: '{pattern}'\n")
        try:
            import subprocess as _sp
            ext_args = []
            if extensions:
                for ext in extensions.split(","):
                    e = ext.strip().lstrip(".")
                    if e:
                        ext_args += ["--include", f"*.{e}"]
            cmd = ["grep", "-rn", "--color=never"] + ext_args + [pattern, str(root)]
            result = _sp.run(cmd, capture_output=True, text=True, timeout=15)
            lines_out = result.stdout.splitlines()
            if lines_out:
                sections.append(f"  {len(lines_out)} coincidencias:\n")
                for ln in lines_out[:40]:
                    try:
                        rel_ln = ln.replace(str(root) + "/", "")
                    except Exception:
                        rel_ln = ln
                    sections.append(f"  {rel_ln[:120]}")
                if len(lines_out) > 40:
                    sections.append(f"  … +{len(lines_out)-40} más (usa grep_code para más detalle)")
            else:
                sections.append(f"  Sin coincidencias de '{pattern}' en {root}")
        except Exception as exc:
            sections.append(f"  (error en búsqueda: {exc})")

    # ── 5. Consejo de uso ────────────────────────────────────────────────────
    sections.append(
        "\n\n## Próximos pasos recomendados\n"
        "  1. grep_code(pattern, directory, extensions=[...]) — búsqueda de texto en código\n"
        "  2. find_files(name='*.c', directory) — localizar ficheros específicos\n"
        "  3. read_file(path, offset=N, limit=M) — leer secciones de ficheros grandes\n"
        "  4. lsp_symbols(path) — ver funciones/clases definidas (si hay servidor LSP)\n"
        "  5. context_before_edit(path, pattern) — contexto exacto antes de editar\n"
        "NUNCA uses bash grep/find/sed — usa las tools especializadas de arriba."
    )

    return "\n".join(sections)


def _tool_bulk_replace(args: dict) -> str:
    """Aplica un reemplazo regex a todos los ficheros que coincidan con un glob en un directorio."""
    directory   = args.get("directory", ".") or "."
    pattern     = args.get("pattern", "")
    replacement = args.get("replacement", "")
    glob_pat    = args.get("glob", "**/*")
    extensions  = args.get("extensions", "")   # "c,h" → filtra por extensión
    flags_str   = args.get("flags", "")
    dry_run     = bool(args.get("dry_run", False))
    max_files   = min(int(args.get("max_files", 50)), 200)

    if not pattern:
        return "Error: 'pattern' requerido."

    root = Path(directory).expanduser().resolve()
    if not root.exists():
        return f"Error: directorio '{directory}' no existe."

    # Flags
    flags = 0
    for f in flags_str.upper().replace("|", ",").split(","):
        f = f.strip()
        if f in ("MULTILINE", "M"):   flags |= re.MULTILINE
        elif f in ("IGNORECASE", "I"): flags |= re.IGNORECASE
        elif f in ("DOTALL", "S"):     flags |= re.DOTALL

    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return f"Error en regex '{pattern}': {e}"

    # Recopilar ficheros
    exts = {e.strip().lstrip(".") for e in extensions.split(",") if e.strip()} if extensions else set()
    try:
        candidates = list(root.glob(glob_pat))
    except Exception as e:
        return f"Error con glob '{glob_pat}': {e}"

    files = []
    for p in candidates:
        if not p.is_file():
            continue
        if exts and p.suffix.lstrip(".") not in exts:
            continue
        if p.name.startswith("."):
            continue
        files.append(p)
        if len(files) >= max_files:
            break

    if not files:
        return f"No se encontraron ficheros con glob='{glob_pat}'" + (f" ext={extensions}" if extensions else "")

    results: list[str] = []
    total_replaced = 0
    files_modified = 0

    for fp in sorted(files):
        try:
            original = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            results.append(f"  ✗  {fp.name}: error leyendo — {e}")
            continue

        new_content, n = compiled.subn(replacement, original)
        if n == 0:
            continue

        rel = fp.relative_to(root) if fp.is_relative_to(root) else fp
        if dry_run:
            results.append(f"  ~ {rel}  ({n} reemplazos)")
        else:
            try:
                fp.write_text(new_content, encoding="utf-8")
                # Incluir diff visual para los primeros 5 ficheros modificados
                diff_block = ""
                if files_modified < 5:
                    diff_lines = list(difflib.unified_diff(
                        original.splitlines(keepends=True),
                        new_content.splitlines(keepends=True),
                        fromfile=f"a/{fp.name}",
                        tofile=f"b/{fp.name}",
                        n=3,
                    ))
                    diff_str = "".join(diff_lines[:80])
                    if diff_str:
                        diff_block = f"\n###FILE:{fp}\n```diff\n{diff_str}```"
                results.append(f"  ✓  {rel}  ({n} reemplazos){diff_block}")
                files_modified += 1
            except Exception as e:
                results.append(f"  ✗  {rel}: error escribiendo — {e}")
        total_replaced += n

    if not results:
        return f"No se encontraron coincidencias de '{pattern}' en {len(files)} fichero(s)."

    action = "[dry-run]" if dry_run else "[aplicado]"
    header = f"bulk_replace {action}  {total_replaced} reemplazos en {files_modified if not dry_run else len(results)} fichero(s):\n"
    return header + "\n".join(results)


# ── Tools compuestas — razonamiento + edición segura ─────────────────────────

def _tool_smart_replace(args: dict) -> str:
    """Verifica que el patrón existe antes de reemplazar; muestra contexto si no lo encuentra.

    Flujo: grep → si 0 coincidencias muestra primeras líneas del fichero para corregir
    el patrón; si hay coincidencias aplica el reemplazo y muestra el diff.
    """
    file_path   = args.get("file", "").strip()
    pattern     = args.get("pattern", "")
    replacement = args.get("replacement", "")
    flags_str   = args.get("flags", "")
    dry_run     = bool(args.get("dry_run", False))
    context_n   = int(args.get("context_lines", 3))

    if not file_path or not pattern:
        return "Error: 'file' y 'pattern' son obligatorios."

    path = Path(file_path)
    if not path.exists():
        return f"Error: '{file_path}' no existe. Verifica la ruta con ls_dir."
    if not path.is_file():
        return f"Error: '{file_path}' no es un fichero."

    # Parse flags
    flags = 0
    for f in flags_str.upper().replace("|", ",").split(","):
        f = f.strip()
        if f in ("MULTILINE", "M"):    flags |= re.MULTILINE
        elif f in ("IGNORECASE", "I"): flags |= re.IGNORECASE
        elif f in ("DOTALL", "S"):     flags |= re.DOTALL

    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error leyendo '{file_path}': {e}"

    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return (
            f"Error en regex '{pattern}': {e}\n"
            "Verifica la sintaxis. Tip: los paréntesis, puntos y barras deben escaparse con \\"
        )

    matches = list(compiled.finditer(original))

    if not matches:
        # Mostrar contexto del fichero para corregir el patrón
        lines = original.splitlines()
        total = len(lines)
        preview_n = min(40, total)
        preview = "\n".join(f"{i+1:5d}: {lines[i]}" for i in range(preview_n))
        suffix = f"\n... ({total - preview_n} líneas más)" if total > preview_n else ""
        return (
            f"⚠ smart_replace: patrón '{pattern}' NO encontrado en '{path.name}' ({total} líneas).\n\n"
            f"Primeras {preview_n} líneas del fichero:\n{preview}{suffix}\n\n"
            "💡 Próximo paso recomendado:\n"
            "  • Localiza el texto exacto a cambiar en las líneas de arriba\n"
            "  • Usa edit_file(old_string='texto exacto copiado', new_string='...')\n"
            "  • O ajusta el patrón regex y vuelve a llamar smart_replace"
        )

    # Aplicar reemplazo
    new_content, n = compiled.subn(replacement, original)

    if dry_run:
        diff_lines = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            n=context_n,
        ))
        diff_str = "".join(diff_lines[:120])
        if len(diff_lines) > 120:
            diff_str += f"\n... ({len(diff_lines) - 120} líneas de diff más)"
        return f"[dry-run] smart_replace: {n} coincidencias en '{path.name}':\n\n{diff_str}"

    try:
        path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return f"Error escribiendo '{file_path}': {e}"

    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
        n=context_n,
    ))
    diff_str = "".join(diff_lines[:100])
    if len(diff_lines) > 100:
        diff_str += f"\n... ({len(diff_lines) - 100} líneas más)"

    return f"✓ smart_replace: {n} reemplazos aplicados en '{path.name}'.\n\n{diff_str}"


def _tool_context_before_edit(args: dict) -> str:
    """Muestra el contexto alrededor de un patrón o texto en un fichero.

    Úsalo ANTES de edit_file o regex_replace para ver el texto exacto que rodea
    el área a editar — evita errores de old_string no coincidente.
    """
    file_path = args.get("file", "").strip()
    pattern   = args.get("pattern", "")
    context_n = int(args.get("context_lines", 8))
    max_hits  = int(args.get("max_hits", 5))

    if not file_path:
        return "Error: 'file' requerido."

    path = Path(file_path)
    if not path.exists():
        return f"Error: '{file_path}' no existe."

    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error leyendo '{file_path}': {e}"

    lines = original.splitlines()
    total = len(lines)

    if not pattern:
        # Sin patrón: muestra estructura general del fichero
        preview_n = min(50, total)
        preview   = "\n".join(f"{i+1:5d}: {lines[i]}" for i in range(preview_n))
        return (
            f"'{path.name}' — {total} líneas:\n{preview}"
            + (f"\n... ({total - preview_n} líneas más — usa offset en read_file)" if total > preview_n else "")
        )

    # Buscar patrón (regex primero, fallback literal)
    try:
        compiled = re.compile(pattern, re.MULTILINE | re.IGNORECASE)
        match_lines = [i for i, ln in enumerate(lines) if compiled.search(ln)]
    except re.error:
        match_lines = [i for i, ln in enumerate(lines) if pattern in ln]

    if not match_lines:
        # Búsqueda literal más flexible: busca subcadenas con casefold
        pat_lower = pattern.casefold()
        match_lines = [i for i, ln in enumerate(lines) if pat_lower in ln.casefold()]

    if not match_lines:
        preview_n = min(30, total)
        preview   = "\n".join(f"{i+1:5d}: {lines[i]}" for i in range(preview_n))
        return (
            f"Patrón '{pattern}' no encontrado en '{path.name}' ({total} líneas).\n\n"
            f"Primeras {preview_n} líneas:\n{preview}"
            + (f"\n... ({total - preview_n} más)" if total > preview_n else "")
        )

    parts = []
    for line_idx in match_lines[:max_hits]:
        start = max(0, line_idx - context_n)
        end   = min(total, line_idx + context_n + 1)
        ctx   = "\n".join(
            f"{'→' if i == line_idx else ' '} {i+1:5d}: {lines[i]}"
            for i in range(start, end)
        )
        parts.append(f"Línea {line_idx + 1}:\n{ctx}")

    header = f"'{pattern}' en '{path.name}' — {len(match_lines)} coincidencia(s)"
    if len(match_lines) > max_hits:
        header += f" (mostrando {max_hits})"
    return header + ":\n\n" + "\n\n---\n\n".join(parts)


def _tool_pre_edit_check(args: dict) -> str:
    """Analiza un fichero antes de editarlo: muestra estructura, imports, funciones clave y
    el texto exacto alrededor del área de interés. Evita ediciones ciegas.

    Combina en una sola llamada: file_stat + resumen de secciones + contexto del patrón.
    """
    file_path = args.get("file", "").strip()
    focus     = args.get("focus", "").strip()   # palabra clave o línea de interés
    offset    = int(args.get("offset", 0))
    limit     = int(args.get("limit", 60))

    if not file_path:
        return "Error: 'file' requerido."

    path = Path(file_path)
    if not path.exists():
        return f"Error: '{file_path}' no existe. Usa ls_dir o find_file para localizar el fichero."

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error leyendo '{file_path}': {e}"

    lines = text.splitlines()
    total = len(lines)

    parts = [f"── pre_edit_check: '{path.name}' — {total} líneas, {len(text)} chars ──"]

    # Sección del fichero solicitada (offset/limit)
    start = max(0, offset)
    end   = min(total, start + limit)
    section_lines = "\n".join(f"{i+1:5d}: {lines[i]}" for i in range(start, end))
    remaining = total - end
    parts.append(
        f"\nLíneas {start+1}–{end}:\n{section_lines}"
        + (f"\n... ({remaining} líneas más — incrementa offset)" if remaining > 0 else "")
    )

    # Contexto alrededor del focus (si se da)
    if focus:
        try:
            compiled = re.compile(focus, re.MULTILINE | re.IGNORECASE)
            hits = [i for i, ln in enumerate(lines) if compiled.search(ln)]
        except re.error:
            hits = [i for i, ln in enumerate(lines) if focus.casefold() in ln.casefold()]

        if hits:
            hit_idx = hits[0]
            ctx_start = max(0, hit_idx - 5)
            ctx_end   = min(total, hit_idx + 6)
            ctx = "\n".join(
                f"{'→' if i == hit_idx else ' '} {i+1:5d}: {lines[i]}"
                for i in range(ctx_start, ctx_end)
            )
            parts.append(f"\nContexto de '{focus}' (línea {hit_idx+1}):\n{ctx}")
            if len(hits) > 1:
                parts.append(f"  ('{focus}' aparece además en líneas: {[i+1 for i in hits[1:6]]})")
        else:
            parts.append(f"\n'{focus}' no encontrado en el fichero.")

    return "\n".join(parts)


# ── Recursos ──────────────────────────────────────────────────────────────────

def _resource_project_context() -> str:
    parts = []
    for filename in ("OOCODE.md", "README.md", "pyproject.toml", "package.json"):
        for search_dir in (Path.cwd(), Path.home()):
            p = search_dir / filename
            if p.exists():
                text = p.read_text(errors="replace")[:3000]
                parts.append(f"## {p}\n\n{text}")
                break
    return "\n\n---\n\n".join(parts) if parts else "(no se encontraron ficheros de contexto)"


def _resource_project_structure() -> str:
    root   = Path.cwd()
    lines  = [str(root), ""]
    ignore = {".git", "__pycache__", "node_modules", ".venv", "venv",
              "dist", "build", ".mypy_cache", "target"}

    def _walk(path: Path, prefix: str, depth: int) -> None:
        if depth > 2:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except PermissionError:
            return
        entries = [e for e in entries if e.name not in ignore and not e.name.startswith(".")]
        for i, entry in enumerate(entries[:40]):
            connector = "└── " if i == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir() and depth < 2:
                extension = "    " if i == len(entries) - 1 else "│   "
                _walk(entry, prefix + extension, depth + 1)

    _walk(root, "", 1)
    return "\n".join(lines)


def _resource_git_status() -> str:
    """git status + últimos 10 commits + diff stats del directorio actual."""
    parts = []
    cwd   = str(Path.cwd())

    def _run(cmd: list[str]) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, cwd=cwd)
            return r.stdout.strip()
        except Exception:
            return ""

    status = _run(["git", "status", "--short"])
    if not status and not _run(["git", "rev-parse", "--git-dir"]):
        return "(no es un repositorio git)"

    parts.append("## Estado actual (git status --short)")
    parts.append(status or "(sin cambios)")

    log = _run(["git", "log", "--oneline", "-10"])
    if log:
        parts.append("\n## Últimos 10 commits")
        parts.append(log)

    stat = _run(["git", "diff", "--stat", "HEAD"])
    if stat:
        parts.append("\n## Cambios respecto a HEAD (diff --stat)")
        parts.append(stat)

    branch = _run(["git", "branch", "--show-current"])
    if branch:
        parts.insert(0, f"## Rama actual: {branch}\n")

    return "\n".join(parts)


def _resource_project_deps() -> str:
    """Dependencias del proyecto (pyproject.toml, requirements.txt, package.json)."""
    parts  = []
    search = [Path.cwd()] + list(Path.cwd().parents)[:2]

    for base in search:
        # Python — pyproject.toml
        pp = base / "pyproject.toml"
        if pp.exists():
            text = pp.read_text(errors="replace")
            # Extraer solo secciones de dependencias
            in_deps = False
            dep_lines = []
            for line in text.splitlines():
                if re.match(r'\[.*dependencies.*\]', line, re.I):
                    in_deps = True
                    dep_lines.append(line)
                elif in_deps and line.startswith("[") and not line.startswith("[["):
                    in_deps = False
                elif in_deps:
                    dep_lines.append(line)
            if dep_lines:
                parts.append(f"## {pp}\n\n" + "\n".join(dep_lines[:60]))
            break

        # Python — requirements.txt
        req = base / "requirements.txt"
        if req.exists():
            text = req.read_text(errors="replace")[:2000]
            parts.append(f"## {req}\n\n{text}")
            break

    for base in search:
        # Node — package.json
        pkg = base / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(errors="replace"))
                deps    = data.get("dependencies", {})
                devdeps = data.get("devDependencies", {})
                lines   = [f"## {pkg}"]
                if deps:
                    lines.append("\ndependencies:")
                    for k, v in list(deps.items())[:30]:
                        lines.append(f"  {k}: {v}")
                if devdeps:
                    lines.append("\ndevDependencies:")
                    for k, v in list(devdeps.items())[:20]:
                        lines.append(f"  {k}: {v}")
                parts.append("\n".join(lines))
            except Exception:
                pass
            break

    if not parts:
        return "(no se encontraron ficheros de dependencias en el directorio actual)"
    return "\n\n---\n\n".join(parts)


def _resource_project_tests() -> str:
    """Tests encontrados en el proyecto con su ruta relativa."""
    root   = Path.cwd()
    _IGNORE = {".git", "__pycache__", "node_modules", ".venv", "venv",
               "dist", "build", ".mypy_cache", "target"}

    test_files: list[Path] = []
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        if any(p in f.parts for p in _IGNORE):
            continue
        name = f.name.lower()
        # Python: test_*.py o *_test.py
        # JS/TS: *.test.js, *.spec.ts, __tests__/
        if (
            (f.suffix == ".py" and (name.startswith("test_") or name.endswith("_test.py")))
            or (f.suffix in {".js", ".ts", ".jsx", ".tsx"} and (".test." in name or ".spec." in name))
            or ("__tests__" in f.parts or "tests" in f.parts or "test" in f.parts)
            and f.suffix in {".py", ".js", ".ts", ".jsx", ".tsx"}
        ):
            test_files.append(f)

    if not test_files:
        return f"No se encontraron ficheros de test en {root}"

    test_files.sort(key=lambda f: f.relative_to(root))

    lines = [f"## Tests encontrados en {root} ({len(test_files)} ficheros)\n"]
    by_dir: dict[str, list[str]] = {}
    for f in test_files:
        rel  = f.relative_to(root)
        dname = str(rel.parent)
        by_dir.setdefault(dname, []).append(rel.name)

    for dname, names in sorted(by_dir.items()):
        lines.append(f"\n{dname}/")
        for name in names:
            lines.append(f"  {name}")

    # Intentar ejecutar rápido para ver si hay tests fallando
    try:
        r = subprocess.run(
            ["python", "-m", "pytest", "--collect-only", "-q", "--no-header"],
            capture_output=True, text=True, timeout=15, cwd=str(root),
        )
        out = (r.stdout or "").strip()
        if out:
            lines.append(f"\n## Recopilación pytest (--collect-only)\n\n{out[:1500]}")
    except Exception:
        pass

    return "\n".join(lines)


def _resource_project_env() -> str:
    """Variables de entorno de desarrollo relevantes (sin secretos)."""
    _SECRET_PATTERNS = re.compile(
        r'(password|passwd|secret|token|key|api_key|auth|credential|private|'
        r'access_key|client_secret|oauth|bearer|jwt)',
        re.IGNORECASE,
    )
    _DEV_PREFIXES = (
        "PATH", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_", "POETRY_",
        "NODE_", "NPM_", "HOME", "USER", "SHELL", "LANG", "TERM",
        "GIT_", "CARGO_", "GOPATH", "GOROOT", "JAVA_HOME",
        "OLLAMA_", "OOCODE_", "DOCKER_", "COMPOSE_",
        "DATABASE_URL", "REDIS_URL", "PORT", "HOST", "DEBUG",
        "LOG_LEVEL", "ENV", "APP_ENV", "NODE_ENV",
    )
    lines = ["## Variables de entorno de desarrollo\n"]
    for k, v in sorted(os.environ.items()):
        if not any(k.upper().startswith(p) for p in _DEV_PREFIXES):
            continue
        if _SECRET_PATTERNS.search(k):
            lines.append(f"  {k} = *** (oculto)")
        else:
            display = v if len(v) <= 100 else v[:97] + "..."
            lines.append(f"  {k} = {display}")
    return "\n".join(lines)


def _resource_project_errors() -> str:
    """Últimas entradas de error del sistema vía journalctl o /var/log/syslog."""
    parts = []

    # journalctl — últimos errores del sistema
    try:
        r = subprocess.run(
            ["journalctl", "-p", "err", "-n", "50", "--no-pager", "--output=short"],
            capture_output=True, text=True, timeout=8,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts.append("## journalctl (últimos 50 errores del sistema)\n\n" + r.stdout.strip()[:3000])
    except Exception:
        pass

    # Si no hay journalctl, intentar /var/log/syslog o /var/log/messages
    if not parts:
        for log_file in ("/var/log/syslog", "/var/log/messages"):
            p = Path(log_file)
            if p.exists():
                try:
                    lines = p.read_text(errors="replace").splitlines()
                    errors = [ln for ln in lines if re.search(r'\b(error|err|crit|alert|emerg)\b', ln, re.I)][-50:]
                    if errors:
                        parts.append(f"## {log_file} (últimas 50 líneas de error)\n\n" + "\n".join(errors))
                        break
                except Exception:
                    pass

    # Últimas entradas del log de la aplicación si existe
    for log_candidate in ("logs/app.log", "app.log", "server.log", ".log"):
        p = Path.cwd() / log_candidate
        if p.exists() and p.is_file():
            try:
                lines = p.read_text(errors="replace").splitlines()
                errors = [ln for ln in lines if re.search(r'\b(error|exception|traceback|critical)\b', ln, re.I)][-30:]
                if errors:
                    parts.append(f"## {p} (últimos 30 errores)\n\n" + "\n".join(errors))
            except Exception:
                pass
            break

    if not parts:
        return "(no se pudieron obtener logs de error del sistema)"
    return "\n\n---\n\n".join(parts)


def _resource_project_metrics() -> str:
    """Métricas de código por extensión: ficheros, líneas, tamaño total."""
    root   = Path.cwd()
    _IGNORE = {".git", "__pycache__", "node_modules", ".venv", "venv",
               ".mypy_cache", "dist", "build", "target"}
    _KNOWN  = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".jsx": "JSX", ".tsx": "TSX", ".c": "C", ".h": "C Header",
        ".cpp": "C++", ".rs": "Rust", ".go": "Go", ".java": "Java",
        ".rb": "Ruby", ".sh": "Shell", ".sql": "SQL", ".md": "Markdown",
        ".toml": "TOML", ".yaml": "YAML", ".yml": "YAML", ".json": "JSON",
        ".html": "HTML", ".css": "CSS", ".lua": "Lua",
    }

    by_ext: dict[str, dict] = {}
    total_size = 0
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        if any(p in f.parts for p in _IGNORE):
            continue
        if f.name.startswith("."):
            continue
        ext  = f.suffix.lower() or ".?"
        try:
            sz   = f.stat().st_size
            text = f.read_text(errors="replace")
            nlines = text.count("\n") + 1
        except Exception:
            continue
        total_size += sz
        if ext not in by_ext:
            by_ext[ext] = {"lang": _KNOWN.get(ext, ext or "sin-ext"), "files": 0, "lines": 0, "size": 0}
        by_ext[ext]["files"]  += 1
        by_ext[ext]["lines"]  += nlines
        by_ext[ext]["size"]   += sz

    if not by_ext:
        return f"No se encontraron ficheros en {root}"

    sorted_exts = sorted(by_ext.items(), key=lambda x: x[1]["lines"], reverse=True)
    lines = [f"## Métricas de código en {root}\n"]
    lines.append(f"{'Extensión':<10} {'Lenguaje':<14} {'Ficheros':>8} {'Líneas':>8} {'Tamaño':>10}")
    lines.append("-" * 56)
    total_f = total_l = 0
    for ext, d in sorted_exts[:25]:
        sz_str = f"{d['size']//1024}KB" if d['size'] > 1024 else f"{d['size']}B"
        lines.append(f"{ext:<10} {d['lang']:<14} {d['files']:>8} {d['lines']:>8} {sz_str:>10}")
        total_f += d["files"]
        total_l += d["lines"]
    lines.append("-" * 56)
    total_sz = f"{total_size//1024**2}MB" if total_size > 1024**2 else f"{total_size//1024}KB"
    lines.append(f"{'TOTAL':<24} {total_f:>8} {total_l:>8} {total_sz:>10}")
    if len(sorted_exts) > 25:
        lines.append(f"\n(+{len(sorted_exts)-25} extensiones adicionales omitidas)")
    return "\n".join(lines)


def _resource_project_changelog() -> str:
    """CHANGELOG.md, CHANGES.rst o HISTORY.md del proyecto."""
    candidates = [
        "CHANGELOG.md", "CHANGELOG.rst", "CHANGELOG.txt",
        "CHANGES.md", "CHANGES.rst", "HISTORY.md", "RELEASES.md",
    ]
    for base in (Path.cwd(),) + tuple(Path.cwd().parents)[:2]:
        for name in candidates:
            p = base / name
            if p.exists():
                text = p.read_text(errors="replace")
                truncated = len(text) > 6000
                if truncated:
                    text = text[:6000]
                suffix = f"\n\n... [truncado — {p.stat().st_size//1024}KB total]" if truncated else ""
                return f"## {p}\n\n{text}{suffix}"
    return "(no se encontró CHANGELOG en el directorio actual ni en los 2 niveles superiores)"


def _resource_project_docker() -> str:
    """Estado Docker: contenedores activos, imágenes recientes y volúmenes."""
    def _run(cmd: list[str]) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            return (r.stdout + r.stderr).strip()
        except FileNotFoundError:
            return "(docker no disponible)"
        except Exception as exc:
            return str(exc)

    parts = []

    ps = _run(["docker", "ps", "--format",
               "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"])
    parts.append("## Contenedores activos\n\n" + (ps or "(ninguno)"))

    stopped = _run(["docker", "ps", "-a", "--filter", "status=exited",
                    "--format", "table {{.Names}}\t{{.Image}}\t{{.Status}}"])
    if stopped and "NAME" not in stopped.splitlines()[0] or (stopped and len(stopped.splitlines()) > 1):
        parts.append("## Contenedores detenidos\n\n" + stopped)

    imgs = _run(["docker", "images", "--format",
                 "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"])
    parts.append("## Imágenes\n\n" + (imgs or "(ninguna)"))

    nets = _run(["docker", "network", "ls", "--format",
                 "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"])
    if nets:
        parts.append("## Redes\n\n" + nets)

    vols = _run(["docker", "volume", "ls", "--format", "table {{.Name}}\t{{.Driver}}"])
    if vols and len(vols.splitlines()) > 1:
        parts.append("## Volúmenes\n\n" + vols)

    compose = _run(["docker", "compose", "ps"])
    if compose and "NAME" in compose:
        parts.append("## docker compose ps\n\n" + compose)

    return "\n\n---\n\n".join(parts)


def _resource_project_coverage() -> str:
    """Informe de cobertura de tests más reciente (.coverage, coverage.xml, htmlcov)."""
    root  = Path.cwd()
    parts = []

    # coverage.xml (formato Cobertura — más legible en texto)
    for xml_path in (root / "coverage.xml", root / ".coverage.xml"):
        if xml_path.exists():
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(xml_path)
                cov  = tree.getroot()
                line_rate = float(cov.attrib.get("line-rate", 0)) * 100
                branch_rate = float(cov.attrib.get("branch-rate", 0)) * 100
                lines_valid = cov.attrib.get("lines-valid", "?")
                timestamp = cov.attrib.get("timestamp", "")
                parts.append(
                    f"## coverage.xml\n\n"
                    f"  Cobertura de líneas:  {line_rate:.1f}%\n"
                    f"  Cobertura de ramas:   {branch_rate:.1f}%\n"
                    f"  Líneas analizadas:    {lines_valid}\n"
                    + (f"  Generado:             {datetime.datetime.fromtimestamp(float(timestamp)).isoformat()[:16]}\n" if timestamp else "")
                )
                # Top 10 módulos con menor cobertura
                packages = cov.findall(".//package") or []
                module_covs = []
                for pkg in packages:
                    for cls in pkg.findall("classes/class"):
                        name = cls.attrib.get("filename", "?")
                        lr   = float(cls.attrib.get("line-rate", 1))
                        module_covs.append((lr, name))
                module_covs.sort()
                if module_covs:
                    parts[-1] += "\nMódulos con menor cobertura:\n"
                    for lr, name in module_covs[:10]:
                        parts[-1] += f"  {lr*100:5.1f}%  {name}\n"
            except Exception as exc:
                parts.append(f"## coverage.xml\n\n(error parseando: {exc})")
            break

    # Intentar ejecutar coverage report si hay .coverage
    cov_db = root / ".coverage"
    if cov_db.exists() and not parts:
        try:
            r = subprocess.run(
                ["python", "-m", "coverage", "report", "--skip-empty"],
                capture_output=True, text=True, timeout=15, cwd=str(root),
            )
            out = (r.stdout or "").strip()
            if out:
                parts.append("## coverage report\n\n" + out[:3000])
        except Exception:
            pass

    if not parts:
        # Buscar htmlcov/index.html y extraer el porcentaje
        htmlcov = root / "htmlcov" / "index.html"
        if htmlcov.exists():
            try:
                html = htmlcov.read_text(errors="replace")
                m = re.search(r'(\d+)\s*%', html)
                pct = m.group(0) if m else "?"
                parts.append(f"## htmlcov/index.html\n\nCobertura total: {pct}\n(abre htmlcov/index.html para el informe completo)")
            except Exception:
                pass

    if not parts:
        return "(no se encontró informe de cobertura — ejecuta 'pytest --cov .' para generarlo)"
    return "\n\n---\n\n".join(parts)


# ── Prompts ───────────────────────────────────────────────────────────────────

_PROMPTS = {
    "code_review": {
        "description": "Revisión de código estructurada — analiza calidad, bugs y mejoras",
        "arguments": [
            {"name": "code",     "description": "Código a revisar",                                          "required": True},
            {"name": "language", "description": "Lenguaje de programación",                                  "required": False},
            {"name": "focus",    "description": "Área de foco: security, performance, readability, all",     "required": False},
        ],
    },
    "debug_session": {
        "description": "Inicio de sesión de debugging estructurada",
        "arguments": [
            {"name": "error",   "description": "Mensaje de error o descripción del problema", "required": True},
            {"name": "context", "description": "Contexto adicional (código, logs, etc.)",     "required": False},
        ],
    },
    "commit_message": {
        "description": "Genera un mensaje de commit convencional a partir de un diff",
        "arguments": [
            {"name": "diff",  "description": "Salida de git diff",                              "required": True},
            {"name": "style", "description": "Estilo: conventional, simple, detailed",          "required": False},
        ],
    },
    "test_cases": {
        "description": "Genera casos de test completos (pytest) para una función o clase",
        "arguments": [
            {"name": "code",      "description": "Función o clase a testear",                        "required": True},
            {"name": "language",  "description": "Lenguaje: python (default), js, ts",               "required": False},
            {"name": "framework", "description": "Framework: pytest (default), unittest, jest, vitest", "required": False},
            {"name": "focus",     "description": "Foco adicional: edge_cases, performance, security", "required": False},
        ],
    },
    "sql_query": {
        "description": "Genera queries PostgreSQL a partir de una descripción en lenguaje natural",
        "arguments": [
            {"name": "description", "description": "Qué debe hacer la query",                     "required": True},
            {"name": "schema",      "description": "Esquema de las tablas relevantes (CREATE TABLE)", "required": False},
            {"name": "dialect",     "description": "Dialecto SQL: postgresql (default), sqlite, mysql", "required": False},
        ],
    },
    "explain_code": {
        "description": "Explicación profunda de código: qué hace, complejidad, invariantes y edge cases",
        "arguments": [
            {"name": "code",     "description": "Código a explicar",            "required": True},
            {"name": "language", "description": "Lenguaje de programación",     "required": False},
            {"name": "depth",    "description": "Nivel: overview, detailed, deep (default: detailed)", "required": False},
        ],
    },
    "refactor_code": {
        "description": "Refactoriza código para mejor legibilidad, mantenibilidad o rendimiento",
        "arguments": [
            {"name": "code",     "description": "Código a refactorizar",         "required": True},
            {"name": "language", "description": "Lenguaje de programación",      "required": False},
            {"name": "goal",     "description": "Objetivo: readability, performance, testability, all (default: readability)", "required": False},
            {"name": "preserve", "description": "Restricciones a respetar (ej. 'mantener la API pública')", "required": False},
        ],
    },
    "api_design": {
        "description": "Diseña una API REST o interfaz Python a partir de una descripción funcional",
        "arguments": [
            {"name": "description", "description": "Qué debe hacer la API",                                  "required": True},
            {"name": "style",       "description": "Estilo: rest, graphql, python_class, python_protocol",   "required": False},
            {"name": "language",    "description": "Lenguaje de implementación (default: python)",            "required": False},
            {"name": "constraints", "description": "Restricciones: autenticación, paginación, versioning, etc.", "required": False},
        ],
    },
    "documentation": {
        "description": "Genera docstrings, comentarios de módulo o sección de README para código dado",
        "arguments": [
            {"name": "code",     "description": "Código a documentar",                                       "required": True},
            {"name": "language", "description": "Lenguaje de programación",                                   "required": False},
            {"name": "style",    "description": "Estilo: google, numpy, sphinx, jsdoc, markdown_readme",      "required": False},
            {"name": "audience", "description": "Audiencia: developer, user, both (default: developer)",      "required": False},
        ],
    },
    "security_audit": {
        "description": "Auditoría de seguridad del código con OWASP Top 10 y vulnerabilidades comunes",
        "arguments": [
            {"name": "code",     "description": "Código a auditar",              "required": True},
            {"name": "language", "description": "Lenguaje de programación",      "required": False},
            {"name": "context",  "description": "Contexto: web_api, cli, library, database (default: web_api)", "required": False},
        ],
    },
    "architecture_review": {
        "description": "Revisión de arquitectura de un sistema o módulo: acoplamiento, cohesión, escalabilidad",
        "arguments": [
            {"name": "description", "description": "Descripción del sistema o módulo a revisar",                    "required": True},
            {"name": "code",        "description": "Código representativo (interfaces, clases clave, configuración)", "required": False},
            {"name": "concerns",    "description": "Preocupaciones específicas: scalability, coupling, testability, performance", "required": False},
        ],
    },
    "pr_description": {
        "description": "Genera una descripción de Pull Request a partir de commits y diff",
        "arguments": [
            {"name": "commits",      "description": "Lista de commits (git log --oneline)",           "required": True},
            {"name": "diff",         "description": "Diff del PR (git diff main...HEAD)",              "required": False},
            {"name": "ticket",       "description": "Número o URL del ticket relacionado",             "required": False},
            {"name": "reviewers",    "description": "Contexto para los revisores (área de impacto)",   "required": False},
        ],
    },
    "error_analysis": {
        "description": "Analiza un stack trace o error completo y propone soluciones concretas",
        "arguments": [
            {"name": "error",    "description": "Stack trace o mensaje de error completo",              "required": True},
            {"name": "code",     "description": "Código donde ocurre el error (si está disponible)",   "required": False},
            {"name": "language", "description": "Lenguaje o framework",                                "required": False},
            {"name": "context",  "description": "Qué se estaba haciendo cuando ocurrió el error",      "required": False},
        ],
    },
    "data_model": {
        "description": "Diseña un modelo de datos (tablas SQL, dataclasses Python, o schema Pydantic)",
        "arguments": [
            {"name": "description", "description": "Descripción del dominio o entidades a modelar",     "required": True},
            {"name": "style",       "description": "Estilo: sql, dataclass, pydantic, sqlalchemy, django_orm", "required": False},
            {"name": "constraints", "description": "Restricciones: relaciones, índices, validaciones",  "required": False},
            {"name": "example_data","description": "Ejemplo de datos reales para inferir tipos",        "required": False},
        ],
    },
    "code_migration": {
        "description": "Plan de migración de código entre versiones, lenguajes o frameworks",
        "arguments": [
            {"name": "code",       "description": "Código o fragmento a migrar",                        "required": True},
            {"name": "from_stack", "description": "Stack/versión origen, ej. 'Python 2.7', 'Flask 1.x'", "required": True},
            {"name": "to_stack",   "description": "Stack/versión destino, ej. 'Python 3.12', 'FastAPI'", "required": True},
            {"name": "scope",      "description": "Alcance: snippet (default), module, full_project",    "required": False},
        ],
    },
    "fix_lint": {
        "description": "Corrige errores de linting — recibe el output del linter y el código",
        "arguments": [
            {"name": "lint_output", "description": "Salida del linter (ruff, mypy, eslint, cppcheck)", "required": True},
            {"name": "code",        "description": "Código fuente con los errores",                    "required": False},
            {"name": "language",    "description": "Lenguaje de programación",                          "required": False},
        ],
    },
    "debug_c": {
        "description": "Sesión de debug C/C++ — analiza crashes, errores de compilación y comportamientos inesperados",
        "arguments": [
            {"name": "error",    "description": "Error del compilador, output de valgrind, gdb backtrace o descripción del problema", "required": True},
            {"name": "code",     "description": "Código C/C++ relevante",                                                             "required": False},
            {"name": "compiler", "description": "Compilador: gcc (default), clang, g++",                                              "required": False},
        ],
    },
    "write_tests": {
        "description": "TDD — genera tests antes de implementar la funcionalidad",
        "arguments": [
            {"name": "spec",      "description": "Descripción de la funcionalidad a implementar",        "required": True},
            {"name": "language",  "description": "Lenguaje: python (default), js, ts, go, rust",         "required": False},
            {"name": "framework", "description": "Framework de testing: pytest, jest, vitest, go test",  "required": False},
            {"name": "style",     "description": "Estilo: unit (default), integration, e2e, property",   "required": False},
        ],
    },
    "optimize_query": {
        "description": "Optimiza queries SQL o consultas a base de datos",
        "arguments": [
            {"name": "query",    "description": "Query SQL o código de acceso a datos a optimizar",             "required": True},
            {"name": "schema",   "description": "Esquema de tablas relevantes (CREATE TABLE e índices)",         "required": False},
            {"name": "problem",  "description": "Descripción del problema: lentitud, N+1, locks, etc.",         "required": False},
            {"name": "dialect",  "description": "Dialecto SQL: postgresql (default), sqlite, mysql, mongodb",   "required": False},
        ],
    },
    "log_analysis": {
        "description": "Analiza logs de error o sistema para identificar patrones y causas raíz",
        "arguments": [
            {"name": "logs",    "description": "Contenido de los logs a analizar",                          "required": True},
            {"name": "context", "description": "Qué estaba ocurriendo cuando se generaron estos logs",      "required": False},
            {"name": "focus",   "description": "Área: errors (default), performance, security, patterns",   "required": False},
        ],
    },
    "generate_code": {
        "description": "Genera código desde una especificación o descripción en lenguaje natural",
        "arguments": [
            {"name": "spec",      "description": "Especificación detallada de lo que hay que implementar",       "required": True},
            {"name": "language",  "description": "Lenguaje de programación (python por defecto)",                "required": False},
            {"name": "style",     "description": "Estilo: clean_code, functional, oop, procedural",              "required": False},
            {"name": "context",   "description": "Código existente con el que debe integrarse",                  "required": False},
        ],
    },
    "benchmark": {
        "description": "Compara implementaciones en términos de rendimiento y sugiere la más eficiente",
        "arguments": [
            {"name": "implementations", "description": "Dos o más implementaciones del mismo problema a comparar", "required": True},
            {"name": "language",        "description": "Lenguaje de programación",                                  "required": False},
            {"name": "context",         "description": "Restricciones de entorno (memoria, CPU, I/O, etc.)",        "required": False},
        ],
    },
    # ── Generación por lenguaje ───────────────────────────────────────────────
    "generate_c_code": {
        "description": "Genera código C17 con gestión de memoria, structs, headers y Makefile",
        "arguments": [
            {"name": "spec",      "description": "Descripción de lo que hay que implementar",                "required": True},
            {"name": "style",     "description": "procedural (default) | oop_c | embedded | posix",         "required": False},
            {"name": "context",   "description": "Código existente o restricciones del entorno",            "required": False},
        ],
    },
    "generate_cpp_code": {
        "description": "Genera código C++17/20 con clases, RAII, smart pointers y CMakeLists",
        "arguments": [
            {"name": "spec",      "description": "Descripción de lo que hay que implementar",                "required": True},
            {"name": "style",     "description": "oop (default) | template | stl | embedded",               "required": False},
            {"name": "context",   "description": "Código existente o restricciones del entorno",            "required": False},
        ],
    },
    "generate_sh_script": {
        "description": "Genera script Bash/POSIX con shebang, manejo de errores, usage() y shellcheck",
        "arguments": [
            {"name": "spec",      "description": "Descripción de lo que hace el script",                    "required": True},
            {"name": "shell",     "description": "bash (default) | sh | zsh",                               "required": False},
            {"name": "context",   "description": "Entorno o herramientas disponibles",                      "required": False},
        ],
    },
    "generate_python_code": {
        "description": "Genera código Python 3.12+ con type hints, dataclasses y tests pytest",
        "arguments": [
            {"name": "spec",      "description": "Descripción de lo que hay que implementar",                "required": True},
            {"name": "style",     "description": "clean (default) | async | oop | functional | script",     "required": False},
            {"name": "context",   "description": "Código existente o dependencias del proyecto",            "required": False},
        ],
    },
    "generate_perl_script": {
        "description": "Genera script Perl moderno con strict/warnings, POD y manejo de errores",
        "arguments": [
            {"name": "spec",      "description": "Descripción de lo que hace el script",                    "required": True},
            {"name": "style",     "description": "script (default) | module | oo | moose",                  "required": False},
            {"name": "context",   "description": "Módulos disponibles o restricciones de versión",          "required": False},
        ],
    },
    "generate_yaml_config": {
        "description": "Genera configuración YAML bien estructurada con comentarios y validación",
        "arguments": [
            {"name": "spec",      "description": "Qué configura el fichero YAML",                           "required": True},
            {"name": "schema",    "description": "json-schema | kubernetes | docker-compose | github-actions | ansible | custom", "required": False},
            {"name": "context",   "description": "Valores de ejemplo o restricciones de entorno",           "required": False},
        ],
    },
    "generate_js_code": {
        "description": "Genera código JavaScript/TypeScript moderno con ESM, async/await y JSDoc",
        "arguments": [
            {"name": "spec",      "description": "Descripción de lo que hay que implementar",                "required": True},
            {"name": "style",     "description": "esm (default) | cjs | typescript | node | browser | react", "required": False},
            {"name": "context",   "description": "Código existente o dependencias del proyecto",            "required": False},
        ],
    },
    "generate_sql_schema": {
        "description": "Genera DDL SQL con tablas, índices, FK, triggers y stored procedures",
        "arguments": [
            {"name": "spec",      "description": "Descripción del modelo de datos o consultas requeridas",   "required": True},
            {"name": "dialect",   "description": "postgresql (default) | mysql | sqlite | mssql | oracle",   "required": False},
            {"name": "context",   "description": "Esquema existente o datos de ejemplo",                    "required": False},
        ],
    },
    "generate_ruby_code": {
        "description": "Genera código Ruby 3.x idiomático con RSpec, Bundler y convenciones Ruby",
        "arguments": [
            {"name": "spec",      "description": "Descripción de lo que hay que implementar",                "required": True},
            {"name": "style",     "description": "script (default) | gem | rails | sinatra | oo",           "required": False},
            {"name": "context",   "description": "Código existente o gems disponibles",                     "required": False},
        ],
    },
    "generate_java_code": {
        "description": "Genera código Java 21+ con clases, interfaces, records y Maven/Gradle",
        "arguments": [
            {"name": "spec",      "description": "Descripción de lo que hay que implementar",                "required": True},
            {"name": "style",     "description": "oop (default) | functional | spring | jakarta | record",   "required": False},
            {"name": "context",   "description": "Código existente o dependencias Maven/Gradle",            "required": False},
        ],
    },
    # ── Razonamiento profundo ─────────────────────────────────────────────────
    "plan_code_changes": {
        "description": "Planifica cambios de código de forma razonada: lista ficheros, tools y pasos ANTES de ejecutar",
        "arguments": [
            {"name": "task",    "description": "Tarea o cambio a realizar",                                 "required": True},
            {"name": "context", "description": "Código o contexto actual relevante",                        "required": False},
            {"name": "scope",   "description": "Alcance: snippet | file | module | project",                "required": False},
        ],
    },
    "debug_failing_edits": {
        "description": "Diagnostica por qué regex_replace/edit_file falla — muestra texto exacto del fichero y sugiere corrección",
        "arguments": [
            {"name": "file",    "description": "Ruta del fichero en el que falla la edición",               "required": True},
            {"name": "pattern", "description": "Patrón que no coincide (regex o old_string)",               "required": True},
            {"name": "error",   "description": "Mensaje de error o síntoma (ej: 'no coincidencias')",       "required": False},
        ],
    },
    "pre_implementation_check": {
        "description": "Checklist previo a implementar: verifica qué existe, qué falta y qué puede romperse",
        "arguments": [
            {"name": "task",     "description": "Funcionalidad o cambio a implementar",                     "required": True},
            {"name": "files",    "description": "Ficheros o módulos involucrados (separados por coma)",     "required": False},
            {"name": "language", "description": "Lenguaje de programación",                                  "required": False},
        ],
    },
    "pre_implementation_analysis": {
        "description": (
            "Análisis estructurado obligatorio ANTES de implementar cualquier cambio. "
            "Guía al agente a usar tools MCP para mapear el problema sistemáticamente: "
            "analyze_codebase → grep_code → read_file → lsp_symbols → plan → implementar. "
            "Evita que el agente use bash grep/find o cree scripts temporales."
        ),
        "arguments": [
            {"name": "task",      "description": "Tarea a implementar",                                     "required": True},
            {"name": "directory", "description": "Directorio del proyecto (ruta absoluta)",                 "required": False},
            {"name": "language",  "description": "Lenguaje principal: c, cpp, python, js, ts, sh, etc.",   "required": False},
            {"name": "scope",     "description": "Alcance: single_file | module | project (default: auto)", "required": False},
        ],
    },
    "batch_file_operations": {
        "description": (
            "Planifica operaciones que afectan a múltiples ficheros usando SOLO tools MCP — "
            "sin bash, sin scripts temporales, sin sed -i en bucle. "
            "Genera el plan: grep_code(files_with_matches) → bulk_replace / edit_files / regex_replace."
        ),
        "arguments": [
            {"name": "task",       "description": "Qué hay que cambiar (ej. 'añadir errno.h a todos los .c que no lo tienen')", "required": True},
            {"name": "directory",  "description": "Directorio raíz de los ficheros (ruta absoluta)",        "required": False},
            {"name": "extensions", "description": "Extensiones de fichero afectadas (ej. 'c,h,cpp')",      "required": False},
            {"name": "pattern",    "description": "Patrón a buscar (para identificar ficheros afectados)",  "required": False},
        ],
    },
    "c_cpp_workflow": {
        "description": (
            "Flujo de trabajo estructurado para C/C++ con LSP (clangd). "
            "Ordena el agente a usar: lsp_symbols → lsp_hover → lsp_call_hierarchy → "
            "context_before_edit → edit_file → lsp_diagnostics → make_run. "
            "Evita que use bash gcc/grep para verificar — usa LSP."
        ),
        "arguments": [
            {"name": "task",     "description": "Qué hay que hacer en el código C/C++",                    "required": True},
            {"name": "file",     "description": "Fichero .c/.h/.cpp a analizar (ruta absoluta)",           "required": False},
            {"name": "symbol",   "description": "Función, struct o macro principal a modificar",           "required": False},
            {"name": "project",  "description": "Directorio del proyecto (para make_run y lsp_workspace)", "required": False},
        ],
    },
    "php_workflow": {
        "description": (
            "Flujo de trabajo estructurado para PHP con LSP (intelephense). "
            "Ordena al agente: lsp_symbols → lsp_diagnostics → context_before_edit → "
            "edit_file → lsp_diagnostics → lint_file (phpcs/phpstan). "
            "Evita bash grep para buscar código — usa LSP y grep_code."
        ),
        "arguments": [
            {"name": "task",    "description": "Qué hay que hacer en el código PHP",                       "required": True},
            {"name": "file",    "description": "Fichero .php a analizar (ruta absoluta o relativa)",       "required": False},
            {"name": "class",   "description": "Clase o interfaz principal a modificar",                   "required": False},
            {"name": "project", "description": "Directorio raíz del proyecto PHP (para lint_project)",     "required": False},
        ],
    },
    "generate_report": {
        "description": (
            "Genera un informe estructurado en Markdown o XML sobre cualquier tema del proyecto. "
            "Recopila información con grep_code/git_log, redacta el informe y lo valida con "
            "render_markdown o xml_validate antes de entregarlo al usuario."
        ),
        "arguments": [
            {"name": "topic",    "description": "Tema del informe (ej: 'cambios de la semana', 'estado del proyecto')", "required": True},
            {"name": "sections", "description": "Secciones separadas por coma (default: Resumen,Detalles,Conclusiones)",  "required": False},
            {"name": "format",   "description": "Formato: markdown (default) | xml",                                      "required": False},
        ],
    },
    "summarize_session": {
        "description": (
            "Genera un resumen estructurado de la conversación o sesión de trabajo actual: "
            "qué se hizo, decisiones clave, problemas resueltos y próximos pasos. "
            "Formateado en Markdown con render_markdown."
        ),
        "arguments": [
            {"name": "scope", "description": "Alcance: conversación actual (default), sesión, tarea específica", "required": False},
        ],
    },
    "ansible_review": {
        "description": (
            "Revisa un playbook Ansible: ejecuta ansible-lint con el perfil indicado, "
            "resume los hallazgos por categoría (yaml, task, security, idempotency) "
            "y propone correcciones concretas para cada problema encontrado."
        ),
        "arguments": [
            {"name": "path",    "description": "Ruta al playbook .yml o directorio de roles",           "required": True},
            {"name": "profile", "description": "Perfil: min|basic|moderate|safety|shared|production",   "required": False},
        ],
    },
    "explore_codebase": {
        "description": (
            "Guía de exploración sistemática de un proyecto desconocido. "
            "Usa analyze_codebase, code_outline, grep_code y read_sections para entender "
            "arquitectura, patrones clave, puntos de entrada y dependencias antes de tocar código."
        ),
        "arguments": [
            {"name": "focus", "description": "Aspecto concreto a explorar: 'arquitectura' | 'tests' | 'api' | 'config' | 'todo' (default: arquitectura)", "required": False},
            {"name": "depth", "description": "Profundidad: 'quick' (solo raíz) | 'medium' (default) | 'deep' (completo)", "required": False},
        ],
    },
    "troubleshoot_error": {
        "description": (
            "Flujo guiado para resolver un error o fallo concreto: localiza la fuente, "
            "lee el contexto relevante, propone hipótesis y aplica la corrección verificando "
            "con run_tests que el problema está resuelto."
        ),
        "arguments": [
            {"name": "error",   "description": "Mensaje de error, traza o descripción del fallo",              "required": True},
            {"name": "context", "description": "Fichero, función o módulo donde ocurre (ayuda a localizar más rápido)", "required": False},
        ],
    },
    "write_commit_message": {
        "description": (
            "Genera un mensaje de commit bien formado a partir de los cambios staged. "
            "Lee git_diff (staged), git_status y git_log reciente para seguir el estilo "
            "del proyecto y propone un mensaje con asunto y cuerpo."
        ),
        "arguments": [
            {"name": "style",  "description": "Estilo: 'conventional' (feat/fix/chore…) | 'free' (default: free)", "required": False},
            {"name": "lang",   "description": "Idioma del mensaje: 'es' | 'en' (default: en)",                     "required": False},
        ],
    },
}


def _get_prompt(name: str, arguments: dict) -> list[dict]:
    if name == "code_review":
        code     = arguments.get("code", "")
        lang     = arguments.get("language", "")
        focus    = arguments.get("focus", "all")
        lang_str = f" ({lang})" if lang else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Revisa el siguiente código{lang_str}.\n\n"
            f"```\n{code}\n```\n\n"
            f"Analiza {'todos los aspectos' if focus == 'all' else focus}:\n"
            "1. **Bugs y errores potenciales** — incluyendo casos edge. Para cada hallazgo: muestra el fragmento problemático y la versión corregida.\n"
            "2. **Calidad y mantenibilidad** — nombres, estructura, duplicación. Indica exactamente qué renombrar o extraer.\n"
            "3. **Seguridad** — inyecciones, datos sin sanitizar, secretos. Severidad (CRÍTICA/ALTA/MEDIA/BAJA) y ejemplo de explotación.\n"
            "4. **Rendimiento** — cuellos de botella, complejidad algorítmica. Muestra la alternativa más eficiente.\n"
            "5. **Mejoras concretas** — código de ejemplo para cada mejora propuesta.\n\n"
            "Para cada hallazgo usa el formato:\n"
            "**[Categoría] — [Severidad]:** descripción\n"
            "```\n# Antes (problemático)\n...\n# Después (corregido)\n...\n```\n"
            "Sé específico. Si el código es correcto en algún aspecto, dilo explícitamente."
        )}}]

    elif name == "debug_session":
        error   = arguments.get("error", "")
        context = arguments.get("context", "")
        ctx_str = f"\n\nContexto adicional:\n```\n{context}\n```" if context else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Tengo el siguiente error o problema:\n\n```\n{error}\n```{ctx_str}\n\n"
            "Ayúdame a debuggear paso a paso:\n"
            "1. **Causa raíz** — ¿qué está causando exactamente este error? Si hay varias hipótesis, ordénalas por probabilidad.\n"
            "2. **Información a recopilar** — qué logs, variables o estados necesito inspeccionar, y cómo obtenerlos.\n"
            "3. **Estrategia de depuración** — pasos concretos con comandos exactos y fragmentos de código para diagnosticar:\n"
            "   ```\n   # ejemplo: añadir logging temporal\n   import logging; logging.debug('var=%r', var)\n   ```\n"
            "4. **Soluciones** — ordenadas por probabilidad, con el fragmento de código corregido para cada una.\n"
            "5. **Cómo verificar** — cómo confirmar que el fix resuelve el problema (tests o salida esperada)."
        )}}]

    elif name == "commit_message":
        diff      = arguments.get("diff", "")
        style     = arguments.get("style", "conventional")
        style_desc = {
            "conventional": "Conventional Commits (feat:, fix:, chore:, etc.)",
            "simple":       "una línea descriptiva en imperativo",
            "detailed":     "título + cuerpo detallado con contexto",
        }.get(style, "Conventional Commits")
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera un mensaje de commit en formato {style_desc} para este diff:\n\n"
            f"```diff\n{diff[:4000]}\n```\n\n"
            "Responde SOLO con el mensaje de commit, sin explicaciones adicionales."
        )}}]

    elif name == "test_cases":
        code      = arguments.get("code", "")
        language  = arguments.get("language", "python")
        framework = arguments.get("framework", "pytest" if language == "python" else "jest")
        focus     = arguments.get("focus", "")
        focus_str = f"\nPon especial énfasis en: {focus}." if focus else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera casos de test completos con {framework} para el siguiente código {language}:\n\n"
            f"```{language}\n{code}\n```\n\n"
            "Incluye:\n"
            "1. **Happy path** — flujo normal y correcto\n"
            "2. **Edge cases** — valores límite, listas vacías, None/null, strings vacíos\n"
            "3. **Error cases** — entradas inválidas, excepciones esperadas\n"
            "4. **Casos de regresión** — si el código hace algo no obvio, testéalo explícitamente\n\n"
            "Para cada test: nombre descriptivo, arrange/act/assert claro, sin dependencias entre tests."
            f"{focus_str}"
        )}}]

    elif name == "sql_query":
        description = arguments.get("description", "")
        schema      = arguments.get("schema", "")
        dialect     = arguments.get("dialect", "postgresql")
        schema_str  = f"\n\nEsquema de tablas:\n```sql\n{schema}\n```" if schema else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera una query {dialect.upper()} para: {description}{schema_str}\n\n"
            "Requisitos:\n"
            f"- Sintaxis válida para {dialect.upper()}\n"
            "- Incluir índices relevantes si la query lo requiere\n"
            "- Comentar partes no obvias\n"
            "- Si hay varias formas, mostrar la más eficiente\n"
            "- Incluir la query de creación de índice si mejora el rendimiento\n\n"
            "Responde con la query SQL y una breve explicación de la estrategia."
        )}}]

    elif name == "explain_code":
        code     = arguments.get("code", "")
        language = arguments.get("language", "")
        depth    = arguments.get("depth", "detailed")
        lang_str = f" {language}" if language else ""
        _depth_map = {
            "overview": "Explica qué hace en 3-5 frases, sin entrar en detalles de implementación.",
            "detailed": (
                "Explica:\n"
                "1. **Propósito** — qué problema resuelve\n"
                "2. **Funcionamiento** — cómo lo hace, paso a paso si es necesario\n"
                "3. **Complejidad** — tiempo y espacio (O-notation)\n"
                "4. **Invariantes** — qué asume el código como verdadero\n"
                "5. **Edge cases** — qué casos especiales maneja o ignora"
            ),
            "deep": (
                "Análisis profundo:\n"
                "1. **Propósito y contexto** — por qué existe este código\n"
                "2. **Algoritmo detallado** — cada paso, decisiones de diseño\n"
                "3. **Complejidad** — tiempo, espacio, casos mejor/peor/promedio\n"
                "4. **Invariantes y pre/postcondiciones** — qué garantiza el código\n"
                "5. **Edge cases y bugs potenciales** — incluyendo concurrencia si aplica\n"
                "6. **Dependencias y acoplamiento** — con qué otras partes del sistema interactúa\n"
                "7. **Alternativas** — cómo podría implementarse de otra forma y cuándo preferirla"
            ),
        }
        depth_instructions = _depth_map.get(depth, _depth_map["detailed"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Explica el siguiente código{lang_str}:\n\n"
            f"```{language}\n{code}\n```\n\n"
            f"{depth_instructions}"
        )}}]

    elif name == "refactor_code":
        code     = arguments.get("code", "")
        language = arguments.get("language", "")
        goal     = arguments.get("goal", "readability")
        preserve = arguments.get("preserve", "")
        lang_str = f" {language}" if language else ""
        goal_map = {
            "readability":   "legibilidad y mantenibilidad (nombres claros, funciones pequeñas, menos duplicación)",
            "performance":   "rendimiento (complejidad algorítmica, estructuras de datos, lazy evaluation, caching)",
            "testability":   "testabilidad (inyección de dependencias, funciones puras, separación de efectos)",
            "all":           "legibilidad, rendimiento y testabilidad",
        }
        goal_desc   = goal_map.get(goal, goal_map["readability"])
        preserve_str = f"\n\nRestricciones a respetar: {preserve}" if preserve else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Refactoriza el siguiente código{lang_str} para mejorar: {goal_desc}.{preserve_str}\n\n"
            f"```{language}\n{code}\n```\n\n"
            "Proporciona:\n"
            "1. **Código refactorizado** — completo, listo para usar\n"
            "2. **Cambios realizados** — lista concisa de qué cambiaste y por qué\n"
            "3. **Trade-offs** — si hay compromisos importantes, menciónelos\n\n"
            "No cambies la funcionalidad observable. Si detectas bugs en el original, señálalos pero no los corrijas a menos que sean triviales."
        )}}]

    elif name == "api_design":
        description = arguments.get("description", "")
        style       = arguments.get("style", "rest")
        language    = arguments.get("language", "python")
        constraints = arguments.get("constraints", "")
        style_map = {
            "rest":             "API REST (endpoints, métodos HTTP, códigos de estado, JSON request/response)",
            "graphql":          "API GraphQL (schema, queries, mutations, resolvers)",
            "python_class":     "interfaz Python con clases y métodos (con type hints completos)",
            "python_protocol":  "Protocol/ABC de Python (interfaz abstracta con type hints)",
        }
        style_desc    = style_map.get(style, style_map["rest"])
        constraints_str = f"\n\nRestricciones adicionales: {constraints}" if constraints else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Diseña una {style_desc} para: {description}{constraints_str}\n\n"
            "Incluye:\n"
            f"1. **Diseño completo** — {'endpoints con rutas, métodos y payloads de ejemplo' if style == 'rest' else 'schema/interfaces/clases completas'}\n"
            "2. **Casos de uso principales** — cómo se usa la API en los flujos más comunes\n"
            "3. **Manejo de errores** — qué errores puede devolver y cómo\n"
            "4. **Decisiones de diseño** — por qué se eligió esta estructura\n"
            f"5. **Ejemplo de implementación** en {language} — esqueleto funcional mínimo"
        )}}]

    elif name == "documentation":
        code     = arguments.get("code", "")
        language = arguments.get("language", "python")
        style    = arguments.get("style", "google")
        audience = arguments.get("audience", "developer")
        style_map = {
            "google":        "Google style docstrings",
            "numpy":         "NumPy style docstrings",
            "sphinx":        "Sphinx/reStructuredText docstrings",
            "jsdoc":         "JSDoc comments",
            "markdown_readme": "sección de README en Markdown",
        }
        style_desc   = style_map.get(style, style_map["google"])
        audience_map = {
            "developer": "desarrolladores que van a usar o mantener el código",
            "user":      "usuarios finales que no verán el código fuente",
            "both":      "tanto desarrolladores como usuarios finales",
        }
        audience_desc = audience_map.get(audience, audience_map["developer"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera documentación en formato {style_desc} para el siguiente código {language}.\n"
            f"Audiencia objetivo: {audience_desc}.\n\n"
            f"```{language}\n{code}\n```\n\n"
            "Incluye para cada función/clase/módulo:\n"
            "1. **Descripción** — qué hace y cuándo usarlo\n"
            "2. **Parámetros** — tipo, propósito y valores especiales\n"
            "3. **Return/Raises** — qué devuelve y qué excepciones puede lanzar\n"
            "4. **Ejemplo de uso** — mínimo un ejemplo real\n\n"
            "Devuelve el código con la documentación integrada, no solo los docstrings por separado."
        )}}]

    elif name == "security_audit":
        code     = arguments.get("code", "")
        language = arguments.get("language", "")
        context  = arguments.get("context", "web_api")
        lang_str = f" {language}" if language else ""
        context_map = {
            "web_api":  "API web (inyección SQL/NoSQL, XSS, CSRF, auth bypass, IDOR, exposición de datos)",
            "cli":      "herramienta CLI (inyección de comandos, path traversal, permisos de ficheros)",
            "library":  "librería (API pública segura, deserialización, dependencias, side effects)",
            "database": "acceso a base de datos (SQL injection, permisos, datos sensibles en texto plano)",
        }
        context_desc = context_map.get(context, context_map["web_api"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Realiza una auditoría de seguridad del siguiente código{lang_str} en contexto {context_desc}:\n\n"
            f"```{language}\n{code}\n```\n\n"
            "Analiza específicamente:\n"
            "1. **Vulnerabilidades críticas** — con severidad (CRÍTICA/ALTA/MEDIA/BAJA) y CVE si aplica\n"
            "2. **Vectores de ataque** — cómo podría explotarse cada vulnerabilidad\n"
            "3. **Datos sensibles** — secretos hardcodeados, logging de PII, almacenamiento inseguro\n"
            "4. **Validación de entrada** — falta de sanitización, parsing inseguro\n"
            "5. **Correcciones concretas** — código corregido para cada vulnerabilidad encontrada\n\n"
            "Si el código es seguro en un aspecto, dilo explícitamente. Sé específico, no genérico."
        )}}]

    elif name == "architecture_review":
        description = arguments.get("description", "")
        code        = arguments.get("code", "")
        concerns    = arguments.get("concerns", "")
        code_str    = f"\n\nCódigo representativo:\n```\n{code[:3000]}\n```" if code else ""
        concerns_str = f"\n\nPreocupaciones específicas a analizar: {concerns}" if concerns else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Revisa la arquitectura del siguiente sistema:{code_str}{concerns_str}\n\n"
            f"Descripción:\n{description}\n\n"
            "Analiza:\n"
            "1. **Estructura y responsabilidades** — ¿cada módulo tiene una sola razón para cambiar?\n"
            "2. **Acoplamiento** — ¿qué depende de qué? ¿hay dependencias circulares?\n"
            "3. **Cohesión** — ¿agrupan cosas que cambian juntas?\n"
            "4. **Escalabilidad** — ¿cuáles son los cuellos de botella bajo carga?\n"
            "5. **Testabilidad** — ¿es fácil testear cada parte en aislamiento?\n"
            "6. **Riesgos principales** — los 3 problemas más graves con su impacto\n"
            "7. **Mejoras concretas** — cambios priorizados con esfuerzo estimado (bajo/medio/alto) y pseudocódigo o snippet ilustrativo para cada uno"
        )}}]

    elif name == "pr_description":
        commits   = arguments.get("commits", "")
        diff      = arguments.get("diff", "")
        ticket    = arguments.get("ticket", "")
        reviewers = arguments.get("reviewers", "")
        diff_str      = f"\n\nDiff (extracto):\n```diff\n{diff[:3000]}\n```" if diff else ""
        ticket_str    = f"\nTicket/Issue: {ticket}" if ticket else ""
        reviewers_str = f"\nContexto para revisores: {reviewers}" if reviewers else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera una descripción de Pull Request clara y completa.\n\n"
            f"Commits incluidos:\n```\n{commits}\n```{diff_str}{ticket_str}{reviewers_str}\n\n"
            "La descripción debe incluir:\n"
            "1. **Título** — una línea concisa (<70 chars) que describe el cambio\n"
            "2. **Resumen** — 2-4 frases explicando QUÉ cambia y POR QUÉ\n"
            "3. **Cambios principales** — lista de bullets con los cambios más importantes\n"
            "4. **Impacto** — qué áreas del sistema se ven afectadas\n"
            "5. **Plan de pruebas** — cómo verificar que funciona correctamente\n"
            "6. **Notas para revisores** — qué deben revisar con más atención\n\n"
            "Formato Markdown. Sé específico, no genérico."
        )}}]

    elif name == "error_analysis":
        error    = arguments.get("error", "")
        code     = arguments.get("code", "")
        language = arguments.get("language", "")
        context  = arguments.get("context", "")
        code_str    = f"\n\nCódigo afectado:\n```{language}\n{code[:2000]}\n```" if code else ""
        context_str = f"\n\nContexto: {context}" if context else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Analiza el siguiente error{' en ' + language if language else ''}:{code_str}{context_str}\n\n"
            f"Error:\n```\n{error[:3000]}\n```\n\n"
            "Responde con:\n"
            "1. **Causa raíz** — exactamente qué está fallando y por qué\n"
            "2. **Línea exacta** — dónde ocurre el error en el stack trace (si aplica)\n"
            "3. **Soluciones ordenadas** — de más a menos probable, con código corregido\n"
            "4. **Cómo verificar** — comando o test para confirmar que está solucionado\n"
            "5. **Prevención** — cómo evitar este error en el futuro\n\n"
            "Si necesitas más información para diagnosticar, di exactamente qué información falta."
        )}}]

    elif name == "data_model":
        description  = arguments.get("description", "")
        style        = arguments.get("style", "sql")
        constraints  = arguments.get("constraints", "")
        example_data = arguments.get("example_data", "")
        style_map = {
            "sql":          "tablas SQL (PostgreSQL)",
            "dataclass":    "dataclasses Python con type hints completos",
            "pydantic":     "modelos Pydantic v2 con validaciones",
            "sqlalchemy":   "modelos SQLAlchemy 2.0 con relaciones",
            "django_orm":   "modelos Django ORM con Meta y relaciones",
        }
        style_desc    = style_map.get(style, style_map["sql"])
        constraints_str  = f"\n\nRestricciones: {constraints}" if constraints else ""
        example_str      = f"\n\nEjemplo de datos reales:\n```\n{example_data[:1000]}\n```" if example_data else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Diseña un modelo de datos en {style_desc} para:\n\n{description}{constraints_str}{example_str}\n\n"
            "Incluye:\n"
            "1. **Modelo completo** — todas las entidades, campos, tipos y relaciones\n"
            "2. **Índices** — qué campos indexar y por qué (consultas frecuentes)\n"
            "3. **Validaciones** — restricciones de integridad, rangos, formatos\n"
            "4. **Relaciones** — FK, M2M, cardinalidades con notación explícita\n"
            "5. **Decisiones de diseño** — por qué elegiste esta estructura\n"
            "6. **Consultas ejemplo** — las 3 queries más frecuentes sobre este modelo"
        )}}]

    elif name == "code_migration":
        code       = arguments.get("code", "")
        from_stack = arguments.get("from_stack", "")
        to_stack   = arguments.get("to_stack", "")
        scope      = arguments.get("scope", "snippet")
        scope_map = {
            "snippet":      "un fragmento de código",
            "module":       "un módulo completo",
            "full_project": "un proyecto entero",
        }
        scope_desc = scope_map.get(scope, scope_map["snippet"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Migra {scope_desc} de **{from_stack}** a **{to_stack}**.\n\n"
            f"Código original ({from_stack}):\n```\n{code[:3000]}\n```\n\n"
            "Proporciona:\n"
            "1. **Código migrado** — completo y listo para usar en {to_stack}\n"
            "2. **Cambios breaking** — APIs o comportamientos que cambian entre versiones\n"
            "3. **Equivalencias** — tabla de correspondencias (función/clase/patrón antiguo → nuevo)\n"
            "4. **Dependencias nuevas** — paquetes a instalar/actualizar\n"
            "5. **Pasos de migración** — orden recomendado si es un módulo o proyecto\n"
            "6. **Gotchas** — problemas comunes en esta migración y cómo evitarlos"
        )}}]

    elif name == "fix_lint":
        lint_out = arguments.get("lint_output", "")
        code     = arguments.get("code", "")
        lang     = arguments.get("language", "")
        lang_str = f" ({lang})" if lang else ""
        code_sec = f"\n\nCódigo fuente:\n```\n{code[:3000]}\n```" if code else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Corrige los siguientes errores de linting{lang_str}:\n\n"
            f"```\n{lint_out[:3000]}\n```{code_sec}\n\n"
            "Para cada error:\n"
            "1. **Descripción** — qué está mal y por qué es un problema\n"
            "2. **Corrección** — código corregido con el cambio mínimo necesario\n"
            "3. **Regla** — nombre de la regla del linter (si aplica)\n\n"
            "Prioriza errores sobre advertencias. Mantén el estilo del código existente."
        )}}]

    elif name == "debug_c":
        error    = arguments.get("error", "")
        code     = arguments.get("code", "")
        compiler = arguments.get("compiler", "gcc")
        code_sec = f"\n\nCódigo relevante:\n```c\n{code[:3000]}\n```" if code else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Tengo el siguiente problema en código C/C++ (compilador: {compiler}):\n\n"
            f"```\n{error[:3000]}\n```{code_sec}\n\n"
            "Analiza y proporciona:\n"
            "1. **Causa raíz** — qué está causando el error exactamente\n"
            "2. **Corrección** — código C/C++ corregido\n"
            "3. **Explicación** — por qué esto causa el problema (gestión de memoria, UB, etc.)\n"
            "4. **Prevención** — cómo evitar este tipo de error en el futuro\n"
            "5. **Herramientas** — si aplica: valgrind, sanitizers, gdb, cppcheck que ayudarían\n\n"
            "Si es un error de compilación, explica cada línea del diagnóstico."
        )}}]

    elif name == "write_tests":
        spec      = arguments.get("spec", "")
        lang      = arguments.get("language", "python")
        framework = arguments.get("framework", "pytest" if lang == "python" else "jest")
        style     = arguments.get("style", "unit")
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Aplica TDD: escribe los tests **antes** de implementar la funcionalidad.\n\n"
            f"**Especificación:**\n{spec}\n\n"
            f"**Lenguaje:** {lang}  |  **Framework:** {framework}  |  **Estilo:** {style}\n\n"
            "Genera tests que:\n"
            "1. **Fallen primero** — que fallen con una implementación vacía (red)\n"
            "2. **Cubran el contrato** — casos positivos, negativos y edge cases\n"
            "3. **Sean legibles** — nombre del test describe el comportamiento esperado\n"
            "4. **Sean independientes** — sin dependencias entre tests\n\n"
            "Tras los tests, proporciona el **esqueleto mínimo** de implementación que los haga pasar."
        )}}]

    elif name == "optimize_query":
        query   = arguments.get("query", "")
        schema  = arguments.get("schema", "")
        problem = arguments.get("problem", "")
        dialect = arguments.get("dialect", "postgresql")
        schema_sec  = f"\n\nEsquema:\n```sql\n{schema[:2000]}\n```" if schema else ""
        problem_sec = f"\n\nProblema específico: {problem}" if problem else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Optimiza la siguiente query {dialect}:{problem_sec}\n\n"
            f"```sql\n{query[:3000]}\n```{schema_sec}\n\n"
            "Analiza y proporciona:\n"
            "1. **Problemas detectados** — N+1, full scans, joins costosos, etc.\n"
            "2. **Query optimizada** — con los cambios aplicados\n"
            "3. **Índices recomendados** — CREATE INDEX necesarios\n"
            "4. **EXPLAIN ANALYZE** — qué buscar en el plan de ejecución\n"
            "5. **Alternativas** — si hay un enfoque radicalmente diferente más eficiente"
        )}}]

    elif name == "log_analysis":
        logs    = arguments.get("logs", "")
        context = arguments.get("context", "")
        focus   = arguments.get("focus", "errors")
        ctx_sec = f"\n\nContexto: {context}" if context else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Analiza estos logs (foco: {focus}):{ctx_sec}\n\n"
            f"```\n{logs[:4000]}\n```\n\n"
            "Proporciona:\n"
            "1. **Resumen** — qué está pasando en pocas palabras\n"
            "2. **Errores críticos** — los más graves con timestamp y contexto\n"
            "3. **Patrones** — repeticiones, correlaciones temporales, secuencias\n"
            "4. **Causa probable** — hipótesis más probable de la causa raíz\n"
            "5. **Próximos pasos** — qué investigar o qué acción tomar"
        )}}]

    elif name == "generate_code":
        spec    = arguments.get("spec", "")
        lang    = arguments.get("language", "python")
        style   = arguments.get("style", "clean_code")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nCódigo existente con el que debe integrarse:\n```\n{context[:2000]}\n```" if context else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera código {lang} siguiendo el estilo {style}.{ctx_sec}\n\n"
            f"**Especificación:**\n{spec}\n\n"
            "Requisitos:\n"
            "- Código completo y funcional, listo para usar\n"
            "- Nombres descriptivos en el idioma del proyecto\n"
            "- Manejo de errores apropiado\n"
            "- Tipos/anotaciones donde el lenguaje lo soporte\n"
            "- Tests básicos si la spec los requiere implícitamente\n\n"
            "Tras el código, explica brevemente las decisiones de diseño no obvias."
        )}}]

    elif name == "benchmark":
        impls   = arguments.get("implementations", "")
        lang    = arguments.get("language", "")
        context = arguments.get("context", "")
        lang_str = f" ({lang})" if lang else ""
        ctx_sec  = f"\n\nRestricciones de entorno: {context}" if context else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Compara el rendimiento de estas implementaciones{lang_str}:{ctx_sec}\n\n"
            f"```\n{impls[:4000]}\n```\n\n"
            "Analiza:\n"
            "1. **Complejidad algorítmica** — Big-O en tiempo y espacio de cada una\n"
            "2. **Rendimiento práctico** — qué factores dominan en casos reales\n"
            "3. **Benchmark code** — código de benchmark ejecutable para medir\n"
            "4. **Recomendación** — cuál usar y en qué casos\n"
            "5. **Mejoras** — si ninguna es óptima, propón una versión mejorada"
        )}}]

    # ── Generación por lenguaje ───────────────────────────────────────────────

    elif name == "generate_c_code":
        spec    = arguments.get("spec", "")
        style   = arguments.get("style", "procedural")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nCódigo/contexto existente:\n```c\n{context[:2000]}\n```" if context else ""
        style_map = {
            "procedural": "C17 procedural limpio (structs, punteros, sin UB)",
            "oop_c":      "OOP en C puro (structs con punteros a función, vtable manual)",
            "embedded":   "C para sistemas embebidos (sin heap dinámico, sin stdlib pesada, ISR-safe)",
            "posix":      "C POSIX (threads, sockets, señales, file I/O)",
        }
        style_desc = style_map.get(style, style_map["procedural"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera código {style_desc}.{ctx_sec}\n\n"
            f"**Especificación:**\n{spec}\n\n"
            "Requisitos obligatorios:\n"
            "- Estándar C17; compila sin warnings con `gcc -Wall -Wextra -Wpedantic`\n"
            "- Header guard `#ifndef MODULE_H / #define MODULE_H / #endif` en cada .h\n"
            "- Gestión de memoria explícita: cada malloc() tiene su free(), sin leaks\n"
            "- Manejo de errores: comprueba retorno de malloc/fopen/etc., nunca ignores errores\n"
            "- Tipos seguros: usa `stdint.h` (int32_t, uint8_t…) donde el tamaño importa\n"
            "- Makefile mínimo con targets `all`, `clean`, `debug` (CFLAGS con sanitizers)\n\n"
            "Entrega: fichero(s) .h + .c + Makefile. Explica las decisiones no obvias."
        )}}]

    elif name == "generate_cpp_code":
        spec    = arguments.get("spec", "")
        style   = arguments.get("style", "oop")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nCódigo/contexto existente:\n```cpp\n{context[:2000]}\n```" if context else ""
        style_map = {
            "oop":       "C++17 OOP (RAII, clases, herencia, polimorfismo)",
            "template":  "C++17 genérico (templates, concepts C++20, variadic)",
            "stl":       "C++17 STL-first (algorithms, ranges C++20, smart_ptr)",
            "embedded":  "C++ para embebidos (sin excepciones, sin RTTI, stack-only)",
        }
        style_desc = style_map.get(style, style_map["oop"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera código {style_desc}.{ctx_sec}\n\n"
            f"**Especificación:**\n{spec}\n\n"
            "Requisitos obligatorios:\n"
            "- Estándar C++17 (o C++20 si los features lo justifican)\n"
            "- RAII: recursos en constructores, liberación garantizada en destructores\n"
            "- Smart pointers: `unique_ptr`, `shared_ptr`; nunca `new`/`delete` raw\n"
            "- `noexcept` donde corresponda; `[[nodiscard]]` en funciones que devuelven errores\n"
            "- Headers con `#pragma once`; separación clara .hpp (interfaz) / .cpp (impl)\n"
            "- CMakeLists.txt mínimo con `target_compile_features(target PRIVATE cxx_std_17)`\n"
            "- Compila sin warnings con `-Wall -Wextra -Weffc++`\n\n"
            "Entrega: fichero(s) .hpp + .cpp + CMakeLists.txt. Justifica las decisiones de diseño."
        )}}]

    elif name == "generate_sh_script":
        spec    = arguments.get("spec", "")
        shell   = arguments.get("shell", "bash")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nContexto/herramientas disponibles:\n{context}" if context else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera un script {shell} que: {spec}{ctx_sec}\n\n"
            "Requisitos obligatorios:\n"
            f"- Shebang correcto: `#!/usr/{shell}` o `#!/usr/bin/env {shell}`\n"
            "- `set -euo pipefail` al inicio (falla rápido, variables no declaradas = error)\n"
            "- Función `usage()` con descripción, opciones y ejemplo de uso\n"
            "- Parseo de argumentos con `getopts` o manejo explícito de `$@`\n"
            "- Mensajes de log con `echo >&2` o función `log_error()`/`log_info()`\n"
            "- Limpieza con `trap 'cleanup' EXIT INT TERM` si crea ficheros temporales\n"
            "- Rutas absolutas o variables `DIR=$(cd \"$(dirname \"$0\")\" && pwd)`\n"
            "- Comprobaciones previas: `command -v tool || { echo 'necesita tool'; exit 1; }`\n"
            "- 0 warnings con `shellcheck -S warning script.sh`\n\n"
            "Entrega: script completo listo para ejecutar + comentario de uso."
        )}}]

    elif name == "generate_python_code":
        spec    = arguments.get("spec", "")
        style   = arguments.get("style", "clean")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nCódigo/contexto existente:\n```python\n{context[:2000]}\n```" if context else ""
        style_map = {
            "clean":      "Python 3.12 limpio (type hints, dataclasses, pathlib)",
            "async":      "Python asyncio (async/await, aiohttp, TaskGroup)",
            "oop":        "Python OOP (clases, herencia, ABCs, descriptors)",
            "functional": "Python funcional (functools, itertools, inmutabilidad)",
            "script":     "script CLI Python (argparse, logging, sys.exit)",
        }
        style_desc = style_map.get(style, style_map["clean"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera código {style_desc}.{ctx_sec}\n\n"
            f"**Especificación:**\n{spec}\n\n"
            "Requisitos obligatorios:\n"
            "- Python 3.12+; type hints completos en funciones públicas\n"
            "- `from __future__ import annotations` si hay forward refs\n"
            "- Docstrings solo cuando el 'por qué' no es obvio (no qué hace)\n"
            "- Manejo de errores con excepciones específicas, no `except Exception` genérico\n"
            "- Tests pytest básicos para la lógica principal\n"
            "- `ruff check` y `mypy` deben pasar sin errores\n\n"
            "Entrega: módulo .py completo + tests. Explica decisiones no obvias."
        )}}]

    elif name == "generate_perl_script":
        spec    = arguments.get("spec", "")
        style   = arguments.get("style", "script")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nContexto/módulos disponibles:\n{context}" if context else ""
        style_map = {
            "script": "script Perl moderno (strict, warnings, Getopt::Long)",
            "module": "módulo CPAN-style (.pm con Exporter o Moo)",
            "oo":     "OOP Perl clásico (bless, @ISA, AUTOLOAD)",
            "moose":  "OOP Perl moderno (Moose o Moo con roles y atributos tipados)",
        }
        style_desc = style_map.get(style, style_map["script"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera {style_desc} que: {spec}{ctx_sec}\n\n"
            "Requisitos obligatorios:\n"
            "- `use strict; use warnings; use utf8;` siempre al inicio\n"
            "- `use 5.020;` (o superior) para features modernas\n"
            "- Manejo de errores con `die` y `eval { ... } or die $@`\n"
            "- POD mínimo: `=head1 NAME`, `=head1 SYNOPSIS`, `=head1 DESCRIPTION`\n"
            "- Variables léxicas (`my`) siempre, nunca globales sin `our`\n"
            "- `perlcritic --severity 3` debe pasar sin errores\n"
            "- `perl -c script.pl` sin warnings de compilación\n\n"
            "Entrega: fichero .pl/.pm completo con POD. Explica las decisiones no obvias."
        )}}]

    elif name == "generate_yaml_config":
        spec    = arguments.get("spec", "")
        schema  = arguments.get("schema", "custom")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nValores de ejemplo o restricciones:\n{context}" if context else ""
        schema_map = {
            "kubernetes":     "Kubernetes manifests (apiVersion, kind, metadata, spec)",
            "docker-compose": "Docker Compose v3 (services, networks, volumes)",
            "github-actions": "GitHub Actions workflow (.github/workflows/)",
            "ansible":        "Ansible playbook (hosts, tasks, handlers, vars)",
            "json-schema":    "JSON Schema validable con ajv o pydantic",
            "custom":         "YAML de configuración personalizado bien estructurado",
        }
        schema_desc = schema_map.get(schema, schema_map["custom"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera {schema_desc} para: {spec}{ctx_sec}\n\n"
            "Requisitos obligatorios:\n"
            "- YAML válido (sin tabs, indentación consistente con 2 espacios)\n"
            "- Comentarios `#` explicando cada sección no obvia\n"
            "- Valores por defecto razonables donde aplique\n"
            "- Variables de entorno `${VAR:-default}` para secretos y configuración\n"
            "- `yamllint -d relaxed` debe pasar sin errores\n"
            "- Estructura jerárquica clara, sin repetición innecesaria\n\n"
            "Entrega: fichero YAML completo con comentarios. Explica la estructura."
        )}}]

    elif name == "generate_js_code":
        spec    = arguments.get("spec", "")
        style   = arguments.get("style", "esm")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nCódigo/contexto existente:\n```js\n{context[:2000]}\n```" if context else ""
        style_map = {
            "esm":        "JavaScript ESM moderno (import/export, top-level await)",
            "cjs":        "CommonJS Node.js (require/module.exports, callbacks legacy)",
            "typescript": "TypeScript estricto (strict mode, interfaces, generics)",
            "node":       "Node.js (fs/path/http/stream, manejo de errores async)",
            "browser":    "JavaScript para browser (DOM, Fetch, Web APIs, sin bundler)",
            "react":      "React 18 (hooks, componentes funcionales, TypeScript)",
        }
        style_desc = style_map.get(style, style_map["esm"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera código {style_desc}.{ctx_sec}\n\n"
            f"**Especificación:**\n{spec}\n\n"
            "Requisitos obligatorios:\n"
            "- ESLint (o TSC) sin errores ni warnings\n"
            "- async/await con manejo de errores try/catch explícito\n"
            "- JSDoc en funciones públicas con @param y @returns\n"
            "- Sin `var`; usa `const` por defecto, `let` solo si reasignas\n"
            "- Nombres en camelCase (variables/funciones) y PascalCase (clases/tipos)\n"
            "- Tests con Jest o Vitest para la lógica principal\n\n"
            "Entrega: fichero .js/.ts completo + tests. Explica decisiones no obvias."
        )}}]

    elif name == "generate_sql_schema":
        spec    = arguments.get("spec", "")
        dialect = arguments.get("dialect", "postgresql")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nEsquema existente o datos de ejemplo:\n```sql\n{context[:2000]}\n```" if context else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera DDL {dialect.upper()} para: {spec}{ctx_sec}\n\n"
            "Requisitos obligatorios:\n"
            f"- Sintaxis válida para {dialect.upper()}\n"
            "- `CREATE TABLE IF NOT EXISTS` con `DROP TABLE IF EXISTS` antes si hay recreación\n"
            "- Tipos apropiados: UUID para PKs, TIMESTAMPTZ para fechas, TEXT sobre VARCHAR\n"
            "- Constraints: NOT NULL, UNIQUE, CHECK donde aplique; FKs con ON DELETE\n"
            "- Índices: PK implícito + índices en FKs y columnas filtradas frecuentemente\n"
            "- Nombres en snake_case; tablas en plural; comentarios COMMENT ON donde no es obvio\n"
            "- Stored procedures/functions si la spec lo requiere\n"
            "- Transacciones BEGIN/COMMIT para DML de inserción de datos de prueba\n\n"
            "Entrega: DDL completo + datos de prueba mínimos + 3 queries ejemplo."
        )}}]

    elif name == "generate_ruby_code":
        spec    = arguments.get("spec", "")
        style   = arguments.get("style", "script")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nCódigo/contexto existente:\n```ruby\n{context[:2000]}\n```" if context else ""
        style_map = {
            "script":  "script Ruby idiomático (one-liner style, Enumerable, Comparable)",
            "gem":     "gema Ruby (estructura lib/gemspec/Rakefile/README)",
            "rails":   "Rails 7 (models, controllers, mailers, concerns, concerns)",
            "sinatra": "Sinatra lightweight (routes, helpers, Rack middleware)",
            "oo":      "Ruby OOP (módulos, mixins, duck typing, method_missing)",
        }
        style_desc = style_map.get(style, style_map["script"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera código {style_desc} que: {spec}{ctx_sec}\n\n"
            "Requisitos obligatorios:\n"
            "- Ruby 3.x; frozen_string_literal: true cuando aplique\n"
            "- Convenciones Ruby: snake_case, SCREAMING_SNAKE para constantes, CamelCase para clases\n"
            "- Manejo de errores con `rescue` específico; nunca `rescue Exception`\n"
            "- Tests RSpec con `describe`/`it`/`expect` para la lógica principal\n"
            "- Gemfile con versiones pinadas para dependencias\n"
            "- `rubocop --no-color` debe pasar sin ofensas (o explicar disable comentado)\n\n"
            "Entrega: fichero(s) .rb + spec/ + Gemfile. Explica decisiones no obvias."
        )}}]

    elif name == "generate_java_code":
        spec    = arguments.get("spec", "")
        style   = arguments.get("style", "oop")
        context = arguments.get("context", "")
        ctx_sec = f"\n\nCódigo/contexto existente:\n```java\n{context[:2000]}\n```" if context else ""
        style_map = {
            "oop":       "Java 21 OOP (clases, interfaces, herencia, generics)",
            "functional":"Java 21 funcional (streams, Optional, lambdas, method refs)",
            "spring":    "Spring Boot 3 (controllers, services, repositories, JPA)",
            "jakarta":   "Jakarta EE (CDI, JPA, JAX-RS, EJB)",
            "record":    "Java records + sealed classes + pattern matching (Java 17+)",
        }
        style_desc = style_map.get(style, style_map["oop"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera código {style_desc}.{ctx_sec}\n\n"
            f"**Especificación:**\n{spec}\n\n"
            "Requisitos obligatorios:\n"
            "- Java 21 LTS; usa `var` donde mejore la legibilidad\n"
            "- Javadoc en clases y métodos públicos con @param, @return, @throws\n"
            "- Convenciones: camelCase para métodos/variables, PascalCase para clases\n"
            "- Manejo de errores: excepciones comprobadas vs runtime bien separadas\n"
            "- Tests JUnit 5 con @Test, @BeforeEach, AssertJ para aserciones\n"
            "- pom.xml (Maven) o build.gradle (Gradle) mínimo con dependencias\n"
            "- Compila sin warnings con `javac -Xlint:all`\n\n"
            "Entrega: fichero(s) .java + tests + pom.xml/build.gradle. "
            "Explica las decisiones de diseño no obvias."
        )}}]

    elif name == "plan_code_changes":
        task    = arguments.get("task", "")
        context = arguments.get("context", "")
        scope   = arguments.get("scope", "file")
        ctx_sec = f"\n\nCódigo/contexto actual:\n```\n{context[:3000]}\n```" if context else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Planifica los cambios necesarios para: {task}{ctx_sec}\n\n"
            "ANTES de escribir cualquier código o llamar a tools de edición, razona en este orden:\n\n"
            "**1. Exploración inicial (OBLIGATORIA)**\n"
            "   - `lsp_symbols(path)` → ver estructura del fichero afectado\n"
            "   - `lsp_workspace_symbols(query, path)` → localizar el símbolo/función objetivo\n"
            "   - `lsp_call_hierarchy(path, line, 'incoming')` → quién usa lo que voy a cambiar\n"
            "   - `context_before_edit(path, pattern)` → ver texto exacto del área\n"
            "   - Si el fichero es desconocido: `pre_edit_check(path, focus)` primero\n\n"
            "**2. Análisis de impacto**\n"
            "   - ¿Qué ficheros hay que modificar? Lista con ruta absoluta\n"
            "   - ¿Qué puede romperse? (referencias via lsp_call_hierarchy)\n"
            "   - ¿Hay tests que actualizar? (grep_code en tests/)\n\n"
            "**3. Plan de edición ordenado**\n"
            "   - Lista de pasos: (fichero → línea aproximada → qué cambiar → tool a usar)\n"
            "   - Para C/C++: cada edit → lsp_diagnostics → make_run\n"
            "   - Para Python: cada edit → lsp_diagnostics → run_tests\n"
            "   - NUNCA: bash python3 << EOF, bash grep -rn, bash make para verificar\n\n"
            "**4. Verificación por lenguaje**\n"
            "   - C/C++: `lsp_diagnostics` + `make_run`\n"
            "   - Python: `lsp_diagnostics` + `mypy_check` + `run_tests`\n"
            "   - JS/TS: `lsp_diagnostics` + `npm_tool(action='test')`\n"
            "   - Shell: `lsp_diagnostics` + `lint_file`\n\n"
            f"Alcance: {scope}. Responde SÓLO con el plan. NO ejecutes nada todavía."
        )}}]

    elif name == "debug_failing_edits":
        file_path = arguments.get("file", "")
        pattern   = arguments.get("pattern", "")
        error     = arguments.get("error", "no coincidencias")
        return [{"role": "user", "content": {"type": "text", "text": (
            f"La edición de '{file_path}' falla: {error}\nPatrón que no coincide: `{pattern}`\n\n"
            "Diagnostica y corrige siguiendo estos pasos OBLIGATORIOS:\n\n"
            "**Paso 1 — Lee el fichero real**\n"
            f"Llama a `context_before_edit(file='{file_path}', pattern='{pattern[:50]}')` "
            "para ver el texto exacto alrededor del área. NO intentes editar sin leer primero.\n\n"
            "**Paso 2 — Compara patrón vs texto real**\n"
            "- ¿Tiene tabs en lugar de espacios?\n"
            "- ¿Los saltos de línea son \\n o \\r\\n?\n"
            "- ¿Hay caracteres especiales no escapados en el regex?\n"
            "- ¿El texto que buscas existe realmente con esa ortografía exacta?\n\n"
            "**Paso 3 — Elige la tool correcta**\n"
            "- Si el texto es literal (copiado del fichero): usa `edit_file(old_string=..., new_string=...)`\n"
            "- Si necesitas regex: usa `smart_replace` con el patrón corregido\n"
            "- NUNCA repitas el mismo patrón que ya falló\n\n"
            "Empieza por el Paso 1 ahora."
        )}}]

    elif name == "pre_implementation_check":
        task     = arguments.get("task", "")
        files    = arguments.get("files", "")
        language = arguments.get("language", "")
        files_sec = (
            f"\n\nFicheros/módulos involucrados: {files}\n"
            "Para cada uno: usa `pre_edit_check(file=<ruta>)` para ver su estructura actual."
        ) if files else ""
        lang_sec = f" en {language}" if language else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Checklist previo a implementar{lang_sec}: {task}{files_sec}\n\n"
            "Antes de escribir código, verifica sistemáticamente:\n\n"
            "**✓ ¿Qué ya existe?**\n"
            "- Busca con `grep_code` o `symbol_lookup` si ya hay algo similar implementado\n"
            "- Lee los ficheros relevantes con `pre_edit_check` o `context_before_edit`\n"
            "- Revisa tests existentes con `grep_code(pattern='test_', path='tests/')`\n\n"
            "**✓ ¿Qué falta?**\n"
            "- Lista las funciones/clases/configs que habrá que crear o modificar\n"
            "- ¿Hay imports que agregar? ¿Dependencias nuevas en requirements.txt?\n\n"
            "**✓ ¿Qué puede romperse?**\n"
            "- ¿Qué llama a lo que voy a cambiar? (usa `grep_code` para buscar referencias)\n"
            "- ¿Hay tests que pueden fallar? ¿Necesito actualizarlos?\n"
            "- ¿Hay ficheros de config que deba sincronizar?\n\n"
            "**✓ Orden de implementación**\n"
            "- Lista los pasos en orden de dependencia (qué primero, qué después)\n"
            "- Indica qué herramienta usarás en cada paso (edit_file, smart_replace, write_file)\n\n"
            "Responde con el checklist completado antes de implementar."
        )}}]

    elif name == "pre_implementation_analysis":
        task      = arguments.get("task", "")
        directory = arguments.get("directory", ".")
        language  = arguments.get("language", "")
        scope     = arguments.get("scope", "auto")
        lang_hint = {
            "c":      "clangd LSP (lsp_symbols, lsp_hover, lsp_call_hierarchy, lsp_diagnostics)",
            "cpp":    "clangd LSP (lsp_symbols, lsp_hover, lsp_call_hierarchy, lsp_diagnostics)",
            "python": "pylsp (lsp_diagnostics, lsp_references, lsp_definition)",
            "js":     "typescript-language-server (lsp_diagnostics, lsp_completion)",
            "ts":     "typescript-language-server (lsp_diagnostics, lsp_completion)",
        }.get(language.lower(), "lsp_diagnostics + lsp_symbols si hay servidor activo")
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Tarea: {task}\n"
            f"Directorio: {directory}\n"
            f"Lenguaje: {language or 'detectar automáticamente'}\n\n"
            "## ANÁLISIS PREVIO OBLIGATORIO — sigue este flujo ANTES de implementar:\n\n"
            "### Paso 1: Mapa del proyecto\n"
            f"```\nanalyze_codebase(directory='{directory}', extensions='{language or 'detectar'}')\n```\n"
            "→ Identifica la estructura, qué ficheros existen y cuáles fueron modificados recientemente.\n\n"
            "### Paso 2: Localizar el código relevante\n"
            "```\ngrep_code(pattern='<símbolo_clave>', directory='...', extensions=['c','h'])  # NO bash grep\n"
            "find_files(name='*.c', directory='...')  # NO bash find\n"
            "multi_grep(patterns=['pat1','pat2','pat3'], directory='...')  # N búsquedas en una\n```\n"
            "→ Lista EXACTAMENTE qué ficheros y líneas hay que modificar.\n\n"
            "### Paso 3: Análisis semántico (LSP)\n"
            f"Usa: {lang_hint}\n"
            "```\nlsp_symbols(path='file.c')           # ver funciones/structs del fichero\n"
            "lsp_hover(path, line, col)            # tipo de un símbolo\n"
            "lsp_call_hierarchy(path, line)        # quién llama a esta función\n```\n\n"
            "### Paso 4: Contexto exacto antes de editar\n"
            "```\ncontext_before_edit(file, pattern)  # texto real del área a cambiar\n"
            "read_file(path, offset=N, limit=50)  # leer sección específica\n```\n\n"
            "### Paso 5: Plan de cambios\n"
            "Enumera NUMERADO:\n"
            "1. Fichero:línea — qué cambiar y por qué\n"
            "2. Tool a usar (edit_file / regex_replace / bulk_replace / write_file)\n"
            "3. Verificación (lsp_diagnostics / lint_file / make_run / run_tests)\n\n"
            "### PROHIBIDO durante el análisis:\n"
            "❌ bash grep / bash find / bash sed — usa los tools MCP de arriba\n"
            "❌ Crear scripts Python temporales — usa python_exec(code=...) o bulk_replace\n"
            "❌ Editar sin leer — siempre context_before_edit antes de edit_file\n\n"
            "Comienza el análisis ahora."
        )}}]

    elif name == "batch_file_operations":
        task       = arguments.get("task", "")
        directory  = arguments.get("directory", ".")
        extensions = arguments.get("extensions", "")
        pattern    = arguments.get("pattern", "")
        ext_str    = f", extensions=['{extensions}']" if extensions else ""
        pat_hint   = f"\ngrep_code(pattern='{pattern}', files_with_matches=true{ext_str})" if pattern else \
                     f"\ngrep_code(pattern='<patrón_que_necesita_cambio>'{ext_str})"
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Operación batch: {task}\n"
            f"Directorio: {directory}\n"
            f"Extensiones: {extensions or 'todas'}\n\n"
            "## FLUJO OBLIGATORIO para operaciones en múltiples ficheros:\n\n"
            "### 1. Identificar ficheros afectados (UNA sola llamada)\n"
            f"```{pat_hint}  # → lista de ficheros con el patrón\n"
            f"grep_code(pattern='<ausente>', files_without_matches=true{ext_str})  # → ficheros SIN el patrón\n```\n"
            "❌ NUNCA: bash grep -l / bash grep -L / bash find\n\n"
            "### 2. Ver un ejemplo del cambio necesario\n"
            "```\nread_file(path='uno_de_los_ficheros', offset=0, limit=30)  # contexto real\n"
            "context_before_edit(file, pattern)  # texto exacto a cambiar\n```\n\n"
            "### 3. Aplicar el cambio en TODOS los ficheros a la vez\n"
            "```\n# Opción A: reemplazo regex en todos\n"
            f"bulk_replace(directory='{directory}', pattern='old', replacement='new'{ext_str}, dry_run=true)\n"
            "# → verifica con dry_run primero, luego sin dry_run\n\n"
            "# Opción B: edición atómica multi-fichero\n"
            "edit_files([{path: 'f1.c', old_string: '...', new_string: '...'}, ...])\n\n"
            "# Opción C: Python puntual (sin fichero temporal)\n"
            "python_exec(code='''\nfrom pathlib import Path\nfor f in Path(\"...\").glob(\"*.c\"):\n"
            "    t = f.read_text(); f.write_text(t.replace(\"old\", \"new\"))\n''', workdir='...')\n```\n"
            "❌ NUNCA: bash sed -i en bucle / scripts Python temporales / bash python3 << 'EOF'\n\n"
            "### 4. Verificar\n"
            "```\nlint_project(path='...')  # o lint_file para ficheros individuales\n"
            "make_run(directory='...')  # si hay Makefile\n"
            "run_tests(path='tests/')  # si hay tests\n```\n\n"
            "Describe exactamente qué ficheros necesitan cambio y aplica el plan."
        )}}]

    elif name == "c_cpp_workflow":
        task    = arguments.get("task", "")
        file    = arguments.get("file", "")
        symbol  = arguments.get("symbol", "")
        project = arguments.get("project", ".")
        file_hint  = f"lsp_symbols(path='{file}')" if file else "lsp_symbols(path='<fichero_principal.c>')"
        sym_hint   = f"lsp_hover(path='{file}', line=N, col=M)" if file else "lsp_hover(path, line, col)"
        hier_hint  = f"lsp_call_hierarchy(path='{file}', line=N, direction='incoming')" if file else "lsp_call_hierarchy(path, line)"
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Tarea C/C++: {task}\n"
            f"Fichero: {file or '(detectar con grep_code/find_files)'}\n"
            f"Símbolo: {symbol or '(identificar con lsp_symbols)'}\n"
            f"Proyecto: {project}\n\n"
            "## FLUJO OBLIGATORIO C/C++ con clangd LSP:\n\n"
            "### Paso 1: Mapear el fichero\n"
            f"```\n{file_hint}  # → lista funciones/structs/macros\n"
            "analyze_codebase(directory='src/', extensions='c,h')  # si necesitas ver el proyecto\n```\n\n"
            "### Paso 2: Entender el contexto semántico\n"
            f"```\n{sym_hint}   # → tipo y firma del símbolo\n"
            f"{hier_hint}  # → quién llama a esta función (NO bash grep -rn)\n"
            "lsp_definition(path, line, col)  # → donde está definido\n```\n\n"
            "### Paso 3: Leer el área exacta a editar\n"
            "```\ncontext_before_edit(file, pattern='<nombre_función>')  # texto real del área\n"
            "read_file(path, offset=N, limit=50)  # sección específica\n```\n\n"
            "### Paso 4: Aplicar el cambio\n"
            "```\nedit_file(path, old_string='...literal...', new_string='...')  # texto exacto copiado\n"
            "# Para múltiples ficheros:\n"
            "bulk_replace(directory='src/', pattern='...', replacement='...', extensions=['c','h'])\n```\n"
            "❌ NUNCA: bash sed -i / bash grep -rn para buscar / python script temporal\n\n"
            "### Paso 5: Verificar (OBLIGATORIO)\n"
            "```\nlsp_diagnostics(path='<fichero_editado>')  # errores en tiempo real (antes de compilar)\n"
            f"make_run(directory='{project}')  # compilar y verificar\n"
            "lint_file(path='<fichero>')  # cppcheck/análisis estático\n```\n\n"
            "### Reglas C/C++ críticas:\n"
            "- Verifica `free()` por cada `malloc()` — sin fugas\n"
            "- Nullcheck obligatorio tras malloc: `if (!ptr) { perror(\"malloc\"); return; }`\n"
            "- Usa `edit_file` con texto literal copiado del fichero — NO supongas el contenido\n"
            "- `lsp_diagnostics` equivale a `gcc -Wall` sin compilar — úsalo siempre\n\n"
            "Comienza con el análisis LSP del fichero."
        )}}]

    elif name == "php_workflow":
        task    = arguments.get("task", "")
        file    = arguments.get("file", "")
        cls     = arguments.get("class", "")
        project = arguments.get("project", ".")
        file_hint = f"lsp_symbols(path='{file}')" if file else "lsp_symbols(path='<fichero.php>')"
        diag_hint = f"lsp_diagnostics(path='{file}')" if file else "lsp_diagnostics(path='<fichero.php>')"
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Tarea PHP: {task}\n"
            f"Fichero: {file or '(detectar con grep_code o find_files)'}\n"
            f"Clase/Interfaz: {cls or '(identificar con lsp_symbols)'}\n"
            f"Proyecto: {project}\n\n"
            "## FLUJO OBLIGATORIO PHP con intelephense LSP:\n\n"
            "### Paso 1: Mapear el fichero\n"
            f"```\n{file_hint}  # → clases, métodos, propiedades, constantes\n"
            "analyze_codebase(directory='.', extensions='php')  # si necesitas ver el proyecto\n```\n\n"
            "### Paso 2: Entender el contexto semántico\n"
            f"```\n{diag_hint}  # → errores de tipos, undefined vars, syntax errors\n"
            "lsp_hover(path, line, col)    # → PHPDoc, firma del método/función\n"
            "lsp_references(path, line, col)  # → todos los usos (NO bash grep -rn)\n"
            "lsp_definition(path, line, col)  # → saltar a la definición\n```\n\n"
            "### Paso 3: Leer el área exacta a editar\n"
            "```\ncontext_before_edit(file, pattern='<nombreMétodo|nombreClase>')  # texto literal\n"
            "read_file(path, offset=N, limit=60)  # sección específica\n```\n\n"
            "### Paso 4: Aplicar el cambio\n"
            "```\nedit_file(path, old_string='...literal copiado...', new_string='...')\n"
            "# Para refactoring en múltiples ficheros:\n"
            "bulk_replace(directory='.', pattern='...', replacement='...', extensions=['php'])\n```\n"
            "❌ NUNCA: bash grep -rn / sed -i / scripts Python temporales\n\n"
            "### Paso 5: Verificar (OBLIGATORIO)\n"
            "```\nlsp_diagnostics(path='<fichero_editado>')  # errores LSP en tiempo real\n"
            "lint_file(path='<fichero>')  # php -l (syntax) + phpcs (PSR-12) + phpstan\n"
            f"lint_project(path='{project}')  # si el cambio afecta a varios ficheros\n```\n\n"
            "### Reglas PHP críticas:\n"
            "- Usa namespaces correctos — revisa `use` statements antes de añadir código\n"
            "- Escribe PHPDoc para métodos públicos: `@param`, `@return`, `@throws`\n"
            "- Usa `edit_file` con texto copiado literalmente — nunca supongas indentación\n"
            "- `lsp_diagnostics` detecta errores sin ejecutar PHP — úsalo siempre\n"
            "- Para interfaces: verifica que todas las clases implementadoras siguen la firma\n\n"
            "Comienza con el análisis LSP del fichero."
        )}}]

    elif name == "generate_report":
        topic    = arguments.get("topic", "")
        sections = arguments.get("sections", "Resumen,Detalles,Conclusiones")
        fmt      = arguments.get("format", "markdown")
        fmt_hint = "XML" if fmt == "xml" else "Markdown"
        tool_hint = "xml_format" if fmt == "xml" else "render_markdown"
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera un informe sobre: {topic}\n"
            f"Secciones solicitadas: {sections}\n"
            f"Formato: {fmt_hint}\n\n"
            f"## FLUJO PARA GENERAR EL INFORME:\n\n"
            "1. Recopila la información necesaria con grep_code, read_file, git_log, etc.\n"
            f"2. Redacta el informe en {fmt_hint} con las secciones indicadas\n"
            f"3. Usa `{tool_hint}` para renderizarlo y verificar el formato\n"
            "4. Si se pide guardar, usa write_file con la extensión correcta\n\n"
            "Estructura recomendada:\n"
            "```\n# Título\n## Resumen ejecutivo\n## Detalles\n## Conclusiones\n## Recomendaciones\n```"
        )}}]

    elif name == "summarize_session":
        scope = arguments.get("scope", "conversación actual")
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera un resumen estructurado de: {scope}\n\n"
            "## ESTRUCTURA DEL RESUMEN:\n\n"
            "1. **Qué se hizo** — lista de cambios con ficheros modificados\n"
            "2. **Decisiones clave** — opciones elegidas y por qué\n"
            "3. **Problemas encontrados y soluciones** — bugs, errores, workarounds\n"
            "4. **Estado actual** — tests pasando, pendientes, bloqueantes\n"
            "5. **Próximos pasos** — qué queda por hacer\n\n"
            "Usa render_markdown para formatear el resumen antes de mostrarlo al usuario."
        )}}]

    elif name == "ansible_review":
        path    = arguments.get("path", ".")
        profile = arguments.get("profile", "moderate")
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Revisa el playbook/rol Ansible en: {path}\n\n"
            f"Sigue este flujo:\n"
            f"1. Llama `ansible_lint` con path='{path}', profile='{profile}'\n"
            f"2. Agrupa los hallazgos por categoría: yaml, task, security, idempotency, best-practice\n"
            f"3. Para cada problema: muestra la línea exacta y propón la corrección\n"
            f"4. Si no hay problemas, confirma que el playbook cumple el perfil '{profile}'\n\n"
            f"Finaliza con un resumen: N avisos críticos, N advertencias, N informativos."
        )}}]

    elif name == "explore_codebase":
        focus = arguments.get("focus", "arquitectura")
        depth = arguments.get("depth", "medium")
        depth_hint = {
            "quick":  "solo lee el raíz del proyecto (tree depth=1, README, ficheros de config)",
            "medium": "explora raíz + módulos principales (tree depth=2, entry points, módulos clave)",
            "deep":   "exploración completa: tree depth=3, todos los módulos, tests, docs",
        }.get(depth, "explora raíz + módulos principales")
        focus_tools = {
            "arquitectura": "analyze_codebase (visión global), code_outline (estructuras), grep_code (patrones de diseño)",
            "tests":        "find_files (.test.* | test_*.py), code_outline de test_*.py, run_tests (smoke check)",
            "api":          "grep_code (routes|endpoints|@app|FastAPI|flask), code_outline de ficheros API",
            "config":       "find_files (*.json|*.toml|*.yaml|*.env), read_file de cada config encontrada",
            "todo":         "search_todos (TODO/FIXME/HACK), grep_code (raise NotImplementedError)",
        }.get(focus, "analyze_codebase, code_outline, grep_code")
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Explora el proyecto sistemáticamente. Foco: **{focus}**. Profundidad: **{depth}** ({depth_hint}).\n\n"
            f"Herramientas recomendadas: {focus_tools}.\n\n"
            "## PLAN DE EXPLORACIÓN:\n\n"
            "1. **Estructura global** — `analyze_codebase` o `tree` para ver organización de ficheros\n"
            "2. **Punto de entrada** — lee el fichero principal (main.py, index.js, cmd/…) con `read_sections`\n"
            "3. **Módulos clave** — `code_outline` de los 3-5 ficheros más importantes\n"
            "4. **Patrones** — `grep_code` para encontrar convenciones de nomenclatura, imports, patrones DI\n"
            "5. **Dependencias** — lee requirements.txt / package.json / Cargo.toml\n"
            "6. **Síntesis** — resume: arquitectura, tecnologías, puntos de entrada, dónde cambiar X\n\n"
            "Responde con secciones claras: Estructura, Tecnologías, Flujo principal, Dónde tocar qué."
        )}}]

    elif name == "troubleshoot_error":
        error   = arguments.get("error", "")
        context = arguments.get("context", "")
        ctx_str = f"\nContexto adicional: `{context}`" if context else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Error a resolver:\n```\n{error}\n```{ctx_str}\n\n"
            "## FLUJO DE RESOLUCIÓN:\n\n"
            "1. **Localizar** — `grep_code` para encontrar el símbolo/mensaje en el código\n"
            "2. **Leer contexto** — `read_sections` de la función/clase donde ocurre el error\n"
            "3. **Trazar causa raíz** — `affected_files` para ver qué otros módulos usan ese símbolo\n"
            "4. **Hipótesis** — enuncia 2-3 causas posibles ordenadas por probabilidad\n"
            "5. **Verificar** — lee las líneas relevantes para confirmar la hipótesis correcta\n"
            "6. **Corregir** — usa `edit_file` para el mínimo cambio necesario\n"
            "7. **Comprobar** — `run_tests` o ejecuta el caso de prueba específico\n\n"
            "Sé preciso: muestra el fragmento exacto del error y el fragmento exacto de la corrección. "
            "No modifiques código que no sea directamente responsable del error."
        )}}]

    elif name == "write_commit_message":
        style = arguments.get("style", "free")
        lang  = arguments.get("lang", "en")
        style_hint = (
            "Usa Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, `perf:`, `ci:`"
            if style == "conventional"
            else "Estilo libre: asunto en imperativo, ≤72 chars, sin punto final"
        )
        lang_hint = "Escribe el mensaje en español." if lang == "es" else "Write the message in English."
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera un mensaje de commit para los cambios actuales.\n\n"
            f"Estilo: {style_hint}. {lang_hint}\n\n"
            "## PASOS:\n\n"
            "1. `git_diff` con staged=true para ver exactamente qué está staged\n"
            "2. `git_status` para confirmar ficheros incluidos/excluidos\n"
            "3. `git_log` (últimos 5 commits) para seguir el estilo del proyecto\n"
            "4. Propón el mensaje: **asunto** (primera línea) + **cuerpo** opcional (si el cambio es complejo)\n\n"
            "Formato de respuesta:\n"
            "```\n<asunto>\n\n<cuerpo opcional: qué cambia y por qué, no el cómo>\n```\n\n"
            "Si hay cambios en múltiples áreas, usa el scope del componente principal. "
            "No incluyas números de issue salvo que el historial del proyecto lo haga siempre."
        )}}]

    return []


# ── Markdown y XML tools ──────────────────────────────────────────────────────

def _tool_render_markdown(args: dict) -> str:
    """Renderiza Markdown a texto plano estructurado (para mostrar al usuario o guardar como .md)."""
    text   = args.get("text", "").strip()
    output = args.get("output", "").strip()

    if not text:
        file_path = args.get("file", "").strip()
        if file_path:
            p = Path(file_path)
            if not p.exists():
                return f"Error: '{file_path}' no existe."
            text = p.read_text(encoding="utf-8", errors="replace")
        else:
            return "Error: 'text' o 'file' requerido."

    # Validate markdown structure
    lines = text.splitlines()
    headers   = [l for l in lines if l.startswith("#")]
    code_blocks = text.count("```")
    links     = text.count("[")
    tables    = sum(1 for l in lines if l.strip().startswith("|"))

    summary = (
        f"Markdown válido — {len(lines)} líneas, {len(headers)} cabeceras, "
        f"{code_blocks // 2} bloques de código, {links} enlaces, {tables} filas de tabla"
    )

    if output:
        try:
            Path(output).write_text(text, encoding="utf-8")
            return f"✓ {summary}\nGuardado en: {output}"
        except Exception as e:
            return f"Error al guardar: {e}"

    preview = text[:3000] + ("\n…(truncado)" if len(text) > 3000 else "")
    return f"✓ {summary}\n\n{preview}"


def _tool_xml_format(args: dict) -> str:
    """Formatea y pretty-prints XML con indentación correcta."""
    import xml.dom.minidom as _minidom

    text      = args.get("text", "").strip()
    file_path = args.get("file", "").strip()
    indent    = int(args.get("indent", 2))
    output    = args.get("output", "").strip()

    if not text and file_path:
        p = Path(file_path)
        if not p.exists():
            return f"Error: '{file_path}' no existe."
        text = p.read_text(encoding="utf-8", errors="replace")

    if not text:
        return "Error: 'text' o 'file' requerido."

    try:
        dom = _minidom.parseString(text.encode("utf-8"))
        pretty = dom.toprettyxml(indent=" " * indent, encoding=None)
        # Remove the <?xml version...?> declaration added by toprettyxml if not in original
        if not text.strip().startswith("<?xml"):
            pretty = "\n".join(pretty.splitlines()[1:])
        pretty = pretty.strip()
    except Exception as e:
        return f"Error de formato XML: {e}"

    if output:
        try:
            Path(output).write_text(pretty, encoding="utf-8")
            return f"✓ XML formateado y guardado en: {output}"
        except Exception as e:
            return f"Error al guardar: {e}"

    preview = pretty[:3000] + ("\n…(truncado)" if len(pretty) > 3000 else "")
    return f"✓ XML formateado ({len(pretty.splitlines())} líneas)\n\n{preview}"


def _tool_xml_validate(args: dict) -> str:
    """Valida XML contra un esquema XSD o comprueba que sea XML bien formado."""
    import xml.etree.ElementTree as _ET

    file_path  = args.get("file", "").strip()
    text       = args.get("text", "").strip()
    schema_xsd = args.get("schema", "").strip()

    if not text and file_path:
        p = Path(file_path)
        if not p.exists():
            return f"Error: '{file_path}' no existe."
        text = p.read_text(encoding="utf-8", errors="replace")

    if not text:
        return "Error: 'text' o 'file' requerido."

    # Well-formedness check via stdlib
    try:
        _ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
        wf_ok = True
        wf_msg = "XML bien formado ✓"
    except _ET.ParseError as e:
        return f"✗ XML mal formado: {e}"

    # XSD validation via lxml (optional)
    if schema_xsd:
        try:
            from lxml import etree as _lxml_et
            schema_doc = _lxml_et.parse(schema_xsd)
            schema_obj = _lxml_et.XMLSchema(schema_doc)
            doc = _lxml_et.fromstring(text.encode("utf-8"))
            if schema_obj.validate(doc):
                return f"✓ {wf_msg}\n✓ Válido contra esquema XSD: {schema_xsd}"
            else:
                errors = "\n".join(str(e) for e in schema_obj.error_log)
                return f"✓ {wf_msg}\n✗ No válido contra XSD:\n{errors}"
        except ImportError:
            return f"✓ {wf_msg}\n⚠ lxml no instalado — validación XSD no disponible (pip install lxml)"
        except Exception as e:
            return f"✓ {wf_msg}\n✗ Error validando XSD: {e}"

    return f"✓ {wf_msg}"


# ── Linters adicionales ───────────────────────────────────────────────────────

def _tool_gitlint_check(args: dict) -> str:
    """Comprueba el mensaje del commit más reciente (o N commits) con gitlint."""
    import shutil as _sh
    count   = max(1, int(args.get("count", 1)))
    commit  = args.get("commit", "HEAD").strip() or "HEAD"
    cwd     = args.get("directory", ".").strip() or "."

    if not _sh.which("gitlint"):
        return "Error: gitlint no instalado  (apt install gitlint)"

    results = []
    try:
        # Obtener mensajes de commit
        log_r = subprocess.run(
            ["git", "log", f"-{count}", "--format=%H %s"],
            capture_output=True, text=True, timeout=10, cwd=cwd
        )
        if log_r.returncode != 0:
            return f"Error git log: {log_r.stderr.strip() or 'no es un repo git'}"

        lines = [l for l in log_r.stdout.splitlines() if l.strip()]
        if not lines:
            return "(no hay commits)"

        for entry in lines:
            sha, _, subject = entry.partition(" ")
            # Obtener el mensaje completo del commit
            msg_r = subprocess.run(
                ["git", "log", "-1", "--format=%B", sha],
                capture_output=True, text=True, timeout=10, cwd=cwd
            )
            msg = msg_r.stdout.strip()
            lint_r = subprocess.run(
                ["gitlint", "--msg-filename", "-"],
                input=msg, capture_output=True, text=True, timeout=10, cwd=cwd
            )
            status = "✓" if lint_r.returncode == 0 else "✗"
            issues = lint_r.stdout.strip() or lint_r.stderr.strip()
            entry_out = f"{status} {sha[:8]}  {subject[:60]}"
            if issues:
                entry_out += f"\n   {issues.replace(chr(10), chr(10) + '   ')}"
            results.append(entry_out)

    except subprocess.TimeoutExpired:
        return "Error: timeout ejecutando gitlint"
    except Exception as e:
        return f"Error: {e}"

    header = f"gitlint — {len(results)} commit(s)\n"
    return header + "\n".join(results)


def _tool_ansible_lint(args: dict) -> str:
    """Ejecuta ansible-lint sobre un playbook o directorio de roles Ansible."""
    import shutil as _sh
    path    = args.get("path", ".").strip() or "."
    profile = args.get("profile", "moderate").strip() or "moderate"
    tags    = args.get("tags", "").strip()

    if not _sh.which("ansible-lint"):
        return "Error: ansible-lint no instalado  (apt install ansible-lint)"

    p = Path(path)
    if not p.exists():
        return f"Error: '{path}' no existe."

    cmd = ["ansible-lint", "--parseable", "--nocolor", f"--profile={profile}"]
    if tags:
        cmd += ["--tags", tags]
    cmd.append(str(p))

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(p.parent))
    except subprocess.TimeoutExpired:
        return "Error: timeout (60s) ejecutando ansible-lint"
    except Exception as e:
        return f"Error: {e}"

    out = (r.stdout + r.stderr).strip()
    if r.returncode == 0:
        return f"✓ ansible-lint: sin problemas en '{path}'"
    if not out:
        return f"✗ ansible-lint: exit code {r.returncode} (sin output)"
    lines = out.splitlines()
    summary = f"✗ ansible-lint — {len(lines)} aviso(s)  [profile={profile}]\n\n"
    return summary + "\n".join(lines[:80]) + ("\n…(truncado)" if len(lines) > 80 else "")


def _tool_efm_config_update(args: dict) -> str:
    """Regenera la config de efm-langserver en ~/.oocode/efm-langserver.yaml.
    Detecta automáticamente los linters instalados (xmllint, rpmlint, ansible-lint, etc.)
    y actualiza la config para que efm-langserver los use como backend LSP.
    """
    try:
        from agent.lsp_client import _ensure_efm_config, _EFM_CONFIG_PATH, _generate_efm_config
        _ensure_efm_config(force=True)
        config = _EFM_CONFIG_PATH.read_text()
        langs = [l.strip().rstrip(":") for l in config.splitlines() if l.startswith("  ") and l.strip().endswith(":") and not l.strip().startswith("-")]
        return (
            f"✓ Config efm-langserver actualizada: {_EFM_CONFIG_PATH}\n"
            f"Lenguajes configurados: {', '.join(langs) or '(ninguno instalado)'}\n\n"
            f"```yaml\n{config}\n```"
        )
    except Exception as e:
        return f"Error actualizando config efm-langserver: {e}"


# ── Definición de tools y resources ──────────────────────────────────────────

_TOOLS = [
    {
        "name": "get_datetime",
        "description": "Devuelve la fecha y hora actual en el formato solicitado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format":   {"type": "string", "description": "'iso' (default) | 'human' | 'unix' | 'date' | 'time'"},
                "timezone": {"type": "string", "description": "'local' (default) | 'utc'"},
            },
        },
    },
    {
        "name": "system_info",
        "description": "Información del sistema: OS, Python, CPU, RAM, disco, uptime.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_recent_files",
        "description": "Lista los ficheros modificados más recientemente en un directorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string",  "description": "Directorio raíz (default: '.')"},
                "count":     {"type": "integer", "description": "Número de ficheros (max 100, default 20)"},
                "extension": {"type": "string",  "description": "Filtrar por extensión, ej. 'py', 'ts'"},
            },
        },
    },
    {
        "name": "read_project_file",
        "description": "Lee un fichero del proyecto (OOCODE.md, README.md, pyproject.toml, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename":  {"type": "string",  "description": "Nombre del fichero (default: 'OOCODE.md')"},
                "directory": {"type": "string",  "description": "Directorio donde buscar (default: '.')"},
                "max_chars": {"type": "integer", "description": "Chars máximos a devolver (default: 4000)"},
            },
        },
    },
    {
        "name": "run_quick_check",
        "description": "Ejecuta un comando corto de verificación (lint, test rápido). Max 120s.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command":   {"type": "string",  "description": "Comando a ejecutar"},
                "directory": {"type": "string",  "description": "Directorio de trabajo (default: '.')"},
                "timeout":   {"type": "integer", "description": "Timeout en segundos (max 120, default 30)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_todos",
        "description": "Busca TODO/FIXME/HACK/NOTE/XXX en el código fuente con file:line. Útil para triage de deuda técnica.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory":   {"type": "string",  "description": "Directorio raíz (default: '.')"},
                "tags":        {"type": "string",  "description": "Tags a buscar separados por coma (default: 'TODO,FIXME,HACK,NOTE,XXX')"},
                "extensions":  {"type": "string",  "description": "Extensiones de fichero separadas por coma (default: 'py,js,ts,c,h,cpp,rs,go,java,rb,sh')"},
                "max_results": {"type": "integer", "description": "Número máximo de resultados (max 500, default 100)"},
            },
        },
    },
    {
        "name": "port_check",
        "description": "Verifica qué puertos TCP locales están en LISTEN. Útil para saber si servicios están activos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ports": {"type": "string", "description": "Puertos a verificar separados por coma, ej. '8080,5432,6379'. Si se omite, lista todos los puertos en LISTEN."},
            },
        },
    },
    {
        "name": "read_files",
        "description": "Lee varios ficheros en una sola llamada. Más eficiente que múltiples read_file cuando se necesita contexto de varios ficheros relacionados.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths":            {"type": "string",  "description": "Rutas de los ficheros separadas por coma, o JSON array de strings"},
                "max_chars_each":   {"type": "integer", "description": "Chars máximos por fichero (max 8000, default 3000)"},
                "show_line_numbers": {"type": "boolean", "description": "Mostrar números de línea (default: false)"},
            },
            "required": ["paths"],
        },
    },
    {
        "name": "http_get",
        "description": "Realiza GET a una URL local (APIs de desarrollo, health checks, llama.cpp, servicios internos). Solo permite URLs locales (localhost, 127.x, 192.168.x).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":     {"type": "string",  "description": "URL local a consultar, ej. 'http://localhost:8080/api/tags'"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (max 30, default 10)"},
                "headers": {"type": "object",  "description": "Headers HTTP adicionales como objeto JSON"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "calculate",
        "description": "Evalúa expresiones matemáticas de forma segura: +,-,*,/,%,**, sqrt, log, sin, cos, pi, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Expresión matemática, ej. 'sqrt(144) + pi * 2'"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "diff_files",
        "description": "Muestra el diff entre dos ficheros o entre dos bloques de texto inline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_a":        {"type": "string",  "description": "Ruta del primer fichero"},
                "file_b":        {"type": "string",  "description": "Ruta del segundo fichero"},
                "text_a":        {"type": "string",  "description": "Primer texto inline (alternativa a file_a)"},
                "text_b":        {"type": "string",  "description": "Segundo texto inline (alternativa a file_b)"},
                "context_lines": {"type": "integer", "description": "Líneas de contexto alrededor del cambio (default: 3)"},
                "unified":       {"type": "boolean", "description": "Formato unified (true, default) o context (false)"},
            },
        },
    },
    {
        "name": "code_compare",
        "description": (
            "Compara una función, macro o sección de código entre dos ficheros en una sola llamada. "
            "Usa esto cuando quieras comparar cómo está implementada una función en dos versiones — "
            "evita hacer grep_code + read_file × 2. "
            "Puede buscar el símbolo automáticamente o comparar rangos de líneas."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_a":        {"type": "string",  "description": "Ruta del primer fichero (obligatorio)"},
                "file_b":        {"type": "string",  "description": "Ruta del segundo fichero (si se omite, compara dentro del mismo fichero)"},
                "symbol":        {"type": "string",  "description": "Nombre del símbolo/función a localizar y comparar, ej. 'load_channels'"},
                "line_a":        {"type": "integer", "description": "Línea de inicio en file_a (alternativa a symbol)"},
                "line_b":        {"type": "integer", "description": "Línea de inicio en file_b (alternativa a symbol)"},
                "num_lines":     {"type": "integer", "description": "Número de líneas a comparar (default: 60, max 300)"},
                "context_lines": {"type": "integer", "description": "Líneas de contexto en el diff (default: 3)"},
            },
            "required": ["file_a"],
        },
    },
    {
        "name": "grep_code",
        "description": (
            "USA ESTO en lugar de 'bash grep'. Busca un patrón regex en el código fuente con líneas de contexto. "
            "Usa ripgrep (rg) si está disponible — mucho más rápido que grep. "
            "Pasa `directory` con ruta absoluta para buscar en un proyecto concreto. "
            "Usa `extensions` para filtrar por tipo: 'c,h' (C/C++), 'py' (Python), 'js,ts' (JS). "
            "Soporta: -rn, -A, -B, -l, -L — todo lo que harías con bash grep pero mejor."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern":       {"type": "string",  "description": "Expresión regular a buscar"},
                "directory":     {"type": "string",  "description": "Directorio raíz con ruta absoluta (default: directorio actual). Pasa la ruta del proyecto aquí en vez de usar cd."},
                "extensions":    {"type": "string",  "description": "Extensiones separadas por coma (default: py,js,ts,c,h,hpp,cpp,rs,go,java,rb,sh,md,json,yaml,toml,xml,sql,html,css,lua). Ej: 'c,h,hpp' para C/C++."},
                "context_lines":          {"type": "integer", "description": "Líneas de contexto antes y después (default: 2, max 20). Equivale a grep -A/-B."},
                "max_matches":            {"type": "integer", "description": "Máximo de resultados (default: 50, max 200)"},
                "ignore_case":            {"type": "boolean", "description": "Ignorar mayúsculas (default: true)"},
                "exclude_pattern":        {"type": "string",  "description": "Patrón regex a excluir de los resultados (como grep -v). Ej: 'STRFREE|imc_malloc' excluye esas líneas."},
                "count_only":             {"type": "boolean", "description": "Si true, devuelve solo el conteo de coincidencias por fichero (como grep -c). No muestra el texto."},
                "files_with_matches":     {"type": "boolean", "description": "Si true, devuelve solo los ficheros que contienen el patrón (como grep -l)."},
                "files_without_matches":  {"type": "boolean", "description": "Si true, devuelve solo los ficheros que NO contienen el patrón (como grep -L)."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "multi_grep",
        "description": (
            "Busca MÚLTIPLES patrones a la vez en el código fuente. "
            "Usa esto cuando necesitas buscar varias cosas seguidas — evita hacer N llamadas a grep_code. "
            "Equivale a N búsquedas grep_code en una sola llamada."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "patterns":         {"type": "array",   "items": {"type": "string"}, "description": "Lista de patrones regex a buscar, ej. ['malloc', 'calloc', 'free']"},
                "directory":        {"type": "string",  "description": "Directorio raíz con ruta absoluta"},
                "extensions":       {"type": "string",  "description": "Extensiones separadas por coma (ej. 'c,h' para C/C++). Default: py,js,ts,c,h,cpp…"},
                "context_lines":    {"type": "integer", "description": "Líneas de contexto por coincidencia (default: 2)"},
                "max_per_pattern":  {"type": "integer", "description": "Máximo de resultados por patrón (default: 20)"},
                "ignore_case":      {"type": "boolean", "description": "Ignorar mayúsculas (default: true)"},
            },
            "required": ["patterns"],
        },
    },
    {
        "name": "code_outline",
        "description": (
            "Devuelve la estructura de un fichero de código: clases, métodos y funciones con sus números de línea. "
            "FUNDAMENTAL para navegar ficheros grandes (>200 líneas) sin necesitar read_file con múltiples offsets. "
            "Para .py usa ast.parse (preciso, sin dependencias). Para otros lenguajes usa ctags con fallback a regex. "
            "Úsalo antes de editar cualquier fichero grande para localizar el método o clase correcta sin leer el fichero entero."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":           {"type": "string",  "description": "Ruta al fichero de código"},
                "min_lines":      {"type": "integer", "description": "Solo genera outline si el fichero supera este número de líneas (0 = siempre, default: 0)"},
                "with_docstrings": {"type": "boolean", "description": "Añade la primera línea del docstring a cada clase/método/función (default: false)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_sections",
        "description": (
            "Lee secciones específicas (funciones, clases, métodos) de un fichero por nombre, sin leer el fichero entero. "
            "ÚSALO en lugar de múltiples read_file(offset=N) cuando necesitas el código de 2+ funciones no contiguas. "
            "Para .py usa ast.parse (extrae la sección exacta incluyendo decoradores). "
            "Para otros lenguajes usa ctags. "
            "Ejemplo: read_sections('src/engine.py', ['Engine.run', '_process', 'handle_event'])"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":     {"type": "string", "description": "Ruta al fichero de código"},
                "sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Lista de nombres a extraer. Para métodos de clase usa 'Clase.metodo'. "
                        "Para funciones de módulo o clases usa solo el nombre, ej. ['run', 'AgentLoop', 'AgentLoop.run']."
                    ),
                },
            },
            "required": ["path", "sections"],
        },
    },
    {
        "name": "affected_files",
        "description": (
            "Encuentra todos los ficheros que referencian un símbolo: función, clase, variable, macro, tipo. "
            "USA ESTO antes de renombrar o cambiar la firma de una función para saber qué ficheros hay que actualizar. "
            "Agrupa los resultados por fichero con conteo de referencias — mucho más claro que grep_code para impacto de cambios."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol":        {"type": "string",  "description": "Nombre del símbolo a buscar, ej. 'ch_ret', 'AgentLoop', 'invalidate_file'"},
                "directory":     {"type": "string",  "description": "Directorio raíz con ruta absoluta (default: directorio actual)"},
                "extensions":    {"type": "string",  "description": "Extensiones separadas por coma (ej. 'c,h' para C/C++, 'py' para Python). Default: todos los tipos de código."},
                "exclude_tests": {"type": "boolean", "description": "Excluir ficheros de test (test_*.py, *.test.ts, tests/). Default: false."},
                "whole_word":    {"type": "boolean", "description": "Buscar solo palabra completa (default: true). Pon false para encontrar prefijos/sufijos."},
                "max_files":     {"type": "integer", "description": "Máximo de ficheros a mostrar (default: 40, max: 100)"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "symbol_lookup",
        "description": (
            "USA ESTO cuando grep_code devuelve 'Sin resultados' 2+ veces o no encuentras una definición. "
            "Busca la definición de un símbolo (función, macro #define, typedef, variable, clase) "
            "probando automáticamente múltiples estrategias al nivel del agente Python — "
            "sin gastar tokens del LLM en cada intento fallido. "
            "Ideal para: '#define args', 'typedef CHAR_DATA', 'imc_malloc', cualquier símbolo difícil de encontrar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol":        {"type": "string",  "description": "Nombre del símbolo a buscar, ej. 'args', 'CHAR_DATA', 'imc_malloc'"},
                "directory":     {"type": "string",  "description": "Directorio raíz con ruta absoluta"},
                "extensions":    {"type": "string",  "description": "Extensiones separadas por coma (ej. 'c,h'). Si se omite, se detecta automáticamente."},
                "context_lines": {"type": "integer", "description": "Líneas de contexto (default: 3)"},
                "max_matches":   {"type": "integer", "description": "Máximo resultados por estrategia (default: 10)"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "env_check",
        "description": "Muestra variables de entorno relevantes para desarrollo, ocultando secretos automáticamente.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prefix":   {"type": "string",  "description": "Filtrar por prefijo, ej. 'PYTHON' o 'OLLAMA'"},
                "show_all": {"type": "boolean", "description": "Mostrar todas las variables (no solo las de desarrollo). Default: false"},
            },
        },
    },
    {
        "name": "json_format",
        "description": "Valida y formatea JSON. Permite extraer sub-objetos con path punteado (ej. 'data.items.0.name').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text":    {"type": "string",  "description": "Contenido JSON a procesar"},
                "path":    {"type": "string",  "description": "Path punteado para extraer un sub-objeto, ej. 'results.0.name'"},
                "compact": {"type": "boolean", "description": "Salida compacta sin espacios (default: false)"},
                "indent":  {"type": "integer", "description": "Nivel de indentación (default: 2)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "hash_text",
        "description": "Calcula hashes MD5/SHA1/SHA256/SHA512 de texto o de un fichero.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text":      {"type": "string", "description": "Texto a hashear"},
                "file_path": {"type": "string", "description": "Ruta de fichero a hashear (alternativa a text)"},
                "algorithm": {"type": "string", "description": "Algoritmo: md5, sha1, sha256, sha512, all (default: sha256)"},
            },
        },
    },
    {
        "name": "write_file",
        "description": "Escribe o sobreescribe un fichero. Incluye diff unificado en la respuesta para visualizar cambios. Soporta append y creación automática de directorios.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string",  "description": "Ruta del fichero a escribir"},
                "content":   {"type": "string",  "description": "Contenido a escribir"},
                "append":    {"type": "boolean", "description": "Si true, añade al final en vez de sobreescribir (default: false)"},
                "mkdir":     {"type": "boolean", "description": "Crear directorios intermedios si no existen (default: true)"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "find_files",
        "description": "USA ESTO en lugar de 'bash find'. Búsqueda avanzada de ficheros por nombre glob, extensión, tamaño y antigüedad. Pasa `directory` con ruta absoluta. Más potente que bash find.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory":      {"type": "string",  "description": "Directorio raíz (default: '.')"},
                "name":           {"type": "string",  "description": "Patrón glob para el nombre, ej. '*.py', 'test_*'"},
                "extension":      {"type": "string",  "description": "Extensión sin punto, ej. 'py', 'ts'"},
                "min_size_kb":    {"type": "integer", "description": "Tamaño mínimo en KB"},
                "max_size_kb":    {"type": "integer", "description": "Tamaño máximo en KB"},
                "max_age_days":   {"type": "integer", "description": "Modificado hace menos de N días"},
                "min_age_days":   {"type": "integer", "description": "Modificado hace más de N días"},
                "max_depth":      {"type": "integer", "description": "Profundidad máxima de búsqueda (default: 10)"},
                "max_results":    {"type": "integer", "description": "Máximo de resultados (default: 50)"},
                "include_hidden": {"type": "boolean", "description": "Incluir ficheros ocultos (default: false)"},
            },
        },
    },
    {
        "name": "process_list",
        "description": "Lista procesos activos del sistema, filtrados por nombre. Muestra PID, CPU, MEM y puertos asociados.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter":      {"type": "string",  "description": "Filtrar por nombre de proceso, ej. 'python', 'node', 'uvicorn'"},
                "show_ports":  {"type": "boolean", "description": "Mostrar puertos asociados a cada proceso (default: true)"},
                "max_results": {"type": "integer", "description": "Máximo de procesos a mostrar (default: 30)"},
            },
        },
    },
    {
        "name": "git_status",
        "description": "Estado del repositorio: rama actual, archivos modificados, staged, untracked y commits ahead/behind.",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Ruta al repositorio (vacío = directorio actual)"},
        }},
    },
    {
        "name": "git_diff",
        "description": "Diferencias del repositorio: unstaged, staged (staged=true) o respecto a un commit/rama (ref='HEAD~1').",
        "inputSchema": {"type": "object", "properties": {
            "path":   {"type": "string",  "description": "Ruta al repositorio (vacío = actual)"},
            "staged": {"type": "boolean", "description": "true = cambios en staging area"},
            "ref":    {"type": "string",  "description": "Comparar con commit/rama, ej. 'HEAD~1', 'main'"},
            "files":  {"type": "string",  "description": "Rutas específicas separadas por espacios"},
        }},
    },
    {
        "name": "git_log",
        "description": "Historial de commits con gráfico de ramas. Admite filtro por fichero y muestra diff del último commit si show_diff=true.",
        "inputSchema": {"type": "object", "properties": {
            "path":      {"type": "string",  "description": "Ruta al repositorio (vacío = actual)"},
            "n":         {"type": "integer", "description": "Número de commits (max 100, default 15)"},
            "format":    {"type": "string",  "description": "'oneline', 'short' o 'medium' (default)"},
            "since":     {"type": "string",  "description": "Fecha de inicio, ej. '2024-01-01' o '1 week ago'"},
            "file_path": {"type": "string",  "description": "Filtrar historial por fichero específico"},
            "show_diff": {"type": "boolean", "description": "Mostrar diff del último commit del fichero (default: false)"},
        }},
    },
    {
        "name": "git_add",
        "description": "Añade archivos al área de staging para el próximo commit.",
        "inputSchema": {"type": "object", "properties": {
            "files": {"type": "string", "description": "Rutas separadas por espacios, o '.' para todo"},
            "path":  {"type": "string", "description": "Ruta al repositorio (vacío = actual)"},
        }, "required": ["files"]},
    },
    {
        "name": "git_commit",
        "description": "Crea un commit con los cambios staged. Usa mensajes descriptivos en imperativo.",
        "inputSchema": {"type": "object", "properties": {
            "message": {"type": "string",  "description": "Mensaje del commit"},
            "path":    {"type": "string",  "description": "Ruta al repositorio (vacío = actual)"},
            "all":     {"type": "boolean", "description": "true = incluir todos los tracked modificados (-a)"},
        }, "required": ["message"]},
    },
    {
        "name": "git_push",
        "description": "Sube commits al repositorio remoto.",
        "inputSchema": {"type": "object", "properties": {
            "remote": {"type": "string",  "description": "Nombre del remoto (default 'origin')"},
            "branch": {"type": "string",  "description": "Rama destino (vacío = rama actual)"},
            "path":   {"type": "string",  "description": "Ruta al repositorio (vacío = actual)"},
            "force":  {"type": "boolean", "description": "true = --force-with-lease (push forzado seguro)"},
        }},
    },
    {
        "name": "git_pull",
        "description": "Descarga y fusiona commits del repositorio remoto.",
        "inputSchema": {"type": "object", "properties": {
            "remote": {"type": "string", "description": "Nombre del remoto (default 'origin')"},
            "branch": {"type": "string", "description": "Rama a descargar (vacío = rama actual)"},
            "path":   {"type": "string", "description": "Ruta al repositorio (vacío = actual)"},
        }},
    },
    {
        "name": "git_branch",
        "description": "Gestiona ramas: listar, crear, cambiar, eliminar o renombrar.",
        "inputSchema": {"type": "object", "properties": {
            "action": {"type": "string", "description": "'list' | 'create' | 'checkout' | 'delete' | 'rename'"},
            "name":   {"type": "string", "description": "Nombre de la rama. Para rename: 'antiguo nuevo'"},
            "path":   {"type": "string", "description": "Ruta al repositorio (vacío = actual)"},
        }},
    },
    {
        "name": "git_stash",
        "description": "Gestiona el stash: push, pop, list (con diff opcional de un índice), drop.",
        "inputSchema": {"type": "object", "properties": {
            "action":     {"type": "string",  "description": "'push' | 'pop' | 'list' | 'drop'"},
            "name":       {"type": "string",  "description": "Mensaje (push) o referencia (drop, ej. 'stash@{0}')"},
            "path":       {"type": "string",  "description": "Ruta al repositorio (vacío = actual)"},
            "diff_index": {"type": "integer", "description": "Índice del stash cuyo diff mostrar al listar (-1 = ninguno, default)"},
        }},
    },
    {
        "name": "git_patch",
        "description": "Crea o aplica parches. create=diff actual, format=.patch del último commit, apply=aplicar parche.",
        "inputSchema": {"type": "object", "properties": {
            "action":        {"type": "string", "description": "'create' | 'format' | 'apply'"},
            "files":         {"type": "string", "description": "Rutas para create (vacío = todo)"},
            "patch_content": {"type": "string", "description": "Contenido del parche para apply"},
            "since_commit":  {"type": "string", "description": "Commit base para format (default 'HEAD~1')"},
            "path":          {"type": "string", "description": "Ruta al repositorio (vacío = actual)"},
        }},
    },
    {
        "name": "git_clone",
        "description": "Clona un repositorio remoto en local.",
        "inputSchema": {"type": "object", "properties": {
            "url":    {"type": "string",  "description": "URL del repositorio (https o ssh)"},
            "target": {"type": "string",  "description": "Directorio destino (vacío = nombre del repo)"},
            "depth":  {"type": "integer", "description": "Shallow clone: número de commits (0 = historial completo)"},
            "branch": {"type": "string",  "description": "Rama específica a clonar"},
        }, "required": ["url"]},
    },
    {
        "name": "git_worktree",
        "description": "Gestiona git worktrees: listar, crear, eliminar, podar, bloquear/desbloquear.",
        "inputSchema": {"type": "object", "properties": {
            "action": {"type": "string",  "description": "'list' | 'add' | 'remove' | 'prune' | 'lock' | 'unlock'"},
            "path":   {"type": "string",  "description": "Directorio del worktree (requerido para add/remove/lock/unlock)"},
            "branch": {"type": "string",  "description": "Rama para el nuevo worktree (add)"},
            "force":  {"type": "boolean", "description": "Forzar operación (add --force, remove --force)"},
            "repo":   {"type": "string",  "description": "Directorio del repositorio (vacío = actual)"},
        }},
    },
    {
        "name": "git_blame",
        "description": "Muestra el autor, fecha y commit de cada línea del fichero (git blame).",
        "inputSchema": {"type": "object", "properties": {
            "path":       {"type": "string",  "description": "Ruta al fichero"},
            "start_line": {"type": "integer", "description": "Línea de inicio (opcional)"},
            "end_line":   {"type": "integer", "description": "Línea de fin (opcional)"},
            "repo":       {"type": "string",  "description": "Directorio del repositorio (vacío = actual)"},
        }, "required": ["path"]},
    },
    {
        "name": "git_rebase",
        "description": "Rebase de commits. action: 'start' (rebase sobre branch), 'continue', 'abort', 'skip'.",
        "inputSchema": {"type": "object", "properties": {
            "action": {"type": "string",  "description": "'start' | 'continue' | 'abort' | 'skip'"},
            "branch": {"type": "string",  "description": "Rama base para el rebase (requerida en start)"},
            "onto":   {"type": "string",  "description": "Rama --onto (opcional)"},
            "repo":   {"type": "string",  "description": "Directorio del repositorio (vacío = actual)"},
        }},
    },
    {
        "name": "git_tag",
        "description": "Gestiona tags de git: listar, crear (ligero o anotado), eliminar, enviar al remoto.",
        "inputSchema": {"type": "object", "properties": {
            "action":  {"type": "string", "description": "'list' | 'create' | 'delete' | 'push'"},
            "name":    {"type": "string", "description": "Nombre del tag"},
            "message": {"type": "string", "description": "Mensaje del tag anotado (create)"},
            "target":  {"type": "string", "description": "Commit/ref objetivo (default: HEAD)"},
            "remote":  {"type": "string", "description": "Remoto para push (default: origin)"},
            "repo":    {"type": "string", "description": "Directorio del repositorio (vacío = actual)"},
        }},
    },
    {
        "name": "git_cherry_pick",
        "description": "Cherry-pick de un commit. action: 'pick', 'continue', 'abort'.",
        "inputSchema": {"type": "object", "properties": {
            "commit":    {"type": "string",  "description": "Hash o ref del commit a cherry-pick"},
            "action":    {"type": "string",  "description": "'pick' | 'continue' | 'abort'"},
            "no_commit": {"type": "boolean", "description": "No hacer commit automáticamente (-n)"},
            "repo":      {"type": "string",  "description": "Directorio del repositorio (vacío = actual)"},
        }},
    },
    {
        "name": "json_validate",
        "description": "Valida que un texto o fichero sea JSON válido e informa de su estructura.",
        "inputSchema": {"type": "object", "properties": {
            "content": {"type": "string", "description": "Texto JSON a validar"},
            "path":    {"type": "string", "description": "Ruta al fichero JSON (alternativa a content)"},
        }},
    },
    {
        "name": "yaml_validate",
        "description": "Valida que un texto o fichero sea YAML válido (requiere PyYAML).",
        "inputSchema": {"type": "object", "properties": {
            "content": {"type": "string", "description": "Texto YAML a validar"},
            "path":    {"type": "string", "description": "Ruta al fichero YAML (alternativa a content)"},
        }},
    },
    {
        "name": "jq_query",
        "description": "Ejecuta una query jq sobre JSON. Requiere jq instalado (apt install jq).",
        "inputSchema": {"type": "object", "properties": {
            "query":   {"type": "string",  "description": "Expresión jq (ej. '.[] | .name', '.key')"},
            "content": {"type": "string",  "description": "Texto JSON de entrada"},
            "path":    {"type": "string",  "description": "Ruta al fichero JSON (alternativa a content)"},
            "compact": {"type": "boolean", "description": "Salida compacta (-c)"},
        }, "required": ["query"]},
    },
    {
        "name": "docker_ps",
        "description": "Lista contenedores Docker en ejecución o todos (all=true).",
        "inputSchema": {"type": "object", "properties": {
            "all": {"type": "boolean", "description": "Incluir contenedores detenidos"},
        }},
    },
    {
        "name": "docker_logs",
        "description": "Muestra los logs recientes de un contenedor.",
        "inputSchema": {"type": "object", "properties": {
            "container": {"type": "string",  "description": "Nombre o ID del contenedor"},
            "lines":     {"type": "integer", "description": "Número de líneas (default: 50)"},
            "follow":    {"type": "boolean", "description": "Seguir logs en tiempo real (timeout 10s)"},
        }, "required": ["container"]},
    },
    {
        "name": "docker_exec",
        "description": "Ejecuta un comando en un contenedor en ejecución (vía sh -c).",
        "inputSchema": {"type": "object", "properties": {
            "container": {"type": "string", "description": "Nombre o ID del contenedor"},
            "command":   {"type": "string", "description": "Comando a ejecutar"},
        }, "required": ["container", "command"]},
    },
    {
        "name": "docker_inspect",
        "description": "Detalles de un contenedor: imagen, estado, IP, puertos, variables de entorno.",
        "inputSchema": {"type": "object", "properties": {
            "container": {"type": "string", "description": "Nombre o ID del contenedor"},
        }, "required": ["container"]},
    },
    {
        "name": "docker_images",
        "description": "Lista las imágenes Docker disponibles localmente.",
        "inputSchema": {"type": "object", "properties": {
            "filter": {"type": "string", "description": "Filtrar por nombre o tag"},
        }},
    },
    {
        "name": "docker_stop",
        "description": "Detiene un contenedor en ejecución.",
        "inputSchema": {"type": "object", "properties": {
            "container": {"type": "string", "description": "Nombre o ID del contenedor"},
        }, "required": ["container"]},
    },
    {
        "name": "docker_rm",
        "description": "Elimina un contenedor detenido.",
        "inputSchema": {"type": "object", "properties": {
            "container": {"type": "string",  "description": "Nombre o ID del contenedor"},
            "force":     {"type": "boolean", "description": "Forzar eliminación aunque esté corriendo"},
        }, "required": ["container"]},
    },
    {
        "name": "docker_cp",
        "description": "Copia ficheros/directorios entre el host y un contenedor. Usar en lugar de 'bash docker cp'.",
        "inputSchema": {"type": "object", "properties": {
            "src": {"type": "string", "description": "Origen: ruta local o CONTAINER:/ruta"},
            "dst": {"type": "string", "description": "Destino: ruta local o CONTAINER:/ruta"},
        }, "required": ["src", "dst"]},
    },
    {
        "name": "compose_version",
        "description": "Muestra la versión de Docker Compose y el binario detectado (v1 o v2).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "compose_services",
        "description": "Lista los servicios definidos en el fichero docker-compose.",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Directorio con el fichero compose (vacío = búsqueda automática)"},
        }},
    },
    {
        "name": "compose_status",
        "description": "Muestra el estado de los servicios de Docker Compose (docker compose ps).",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Directorio con el fichero compose (vacío = búsqueda automática)"},
        }},
    },
    {
        "name": "compose_up",
        "description": "Levanta los servicios de Docker Compose.",
        "inputSchema": {"type": "object", "properties": {
            "path":    {"type": "string",  "description": "Directorio con el fichero compose"},
            "service": {"type": "string",  "description": "Servicio específico (vacío = todos)"},
            "detach":  {"type": "boolean", "description": "Ejecutar en segundo plano (default: true)"},
            "build":   {"type": "boolean", "description": "Reconstruir imágenes antes de levantar"},
        }},
    },
    {
        "name": "compose_down",
        "description": "Detiene y elimina contenedores de Compose.",
        "inputSchema": {"type": "object", "properties": {
            "path":          {"type": "string",  "description": "Directorio con el fichero compose"},
            "volumes":       {"type": "boolean", "description": "Eliminar volúmenes nombrados (¡destructivo!)"},
            "remove_images": {"type": "string",  "description": "'all' o 'local' para eliminar imágenes"},
        }},
    },
    {
        "name": "compose_stop",
        "description": "Detiene servicios de Compose sin eliminar los contenedores.",
        "inputSchema": {"type": "object", "properties": {
            "path":    {"type": "string", "description": "Directorio con el fichero compose"},
            "service": {"type": "string", "description": "Servicio específico (vacío = todos)"},
        }},
    },
    {
        "name": "compose_restart",
        "description": "Reinicia servicios de Docker Compose.",
        "inputSchema": {"type": "object", "properties": {
            "path":    {"type": "string", "description": "Directorio con el fichero compose"},
            "service": {"type": "string", "description": "Servicio específico (vacío = todos)"},
        }},
    },
    {
        "name": "compose_build",
        "description": "Construye o reconstruye las imágenes de Docker Compose.",
        "inputSchema": {"type": "object", "properties": {
            "path":     {"type": "string",  "description": "Directorio con el fichero compose"},
            "service":  {"type": "string",  "description": "Servicio específico (vacío = todos)"},
            "no_cache": {"type": "boolean", "description": "Construir sin caché de capas"},
        }},
    },
    {
        "name": "compose_pull",
        "description": "Descarga las últimas versiones de las imágenes de Compose.",
        "inputSchema": {"type": "object", "properties": {
            "path":    {"type": "string", "description": "Directorio con el fichero compose"},
            "service": {"type": "string", "description": "Servicio específico (vacío = todos)"},
        }},
    },
    {
        "name": "compose_logs",
        "description": "Muestra los logs de los servicios de Docker Compose.",
        "inputSchema": {"type": "object", "properties": {
            "path":    {"type": "string",  "description": "Directorio con el fichero compose"},
            "service": {"type": "string",  "description": "Servicio específico (vacío = todos)"},
            "lines":   {"type": "integer", "description": "Número de líneas (default: 50)"},
        }},
    },
    {
        "name": "compose_exec",
        "description": "Ejecuta un comando en un servicio en ejecución de Compose.",
        "inputSchema": {"type": "object", "properties": {
            "path":    {"type": "string", "description": "Directorio con el fichero compose"},
            "service": {"type": "string", "description": "Nombre del servicio"},
            "command": {"type": "string", "description": "Comando a ejecutar (default: sh)"},
        }, "required": ["service"]},
    },
    {
        "name": "compose_run",
        "description": "Ejecuta un comando puntual en un nuevo contenedor del servicio (one-off).",
        "inputSchema": {"type": "object", "properties": {
            "path":    {"type": "string",  "description": "Directorio con el fichero compose"},
            "service": {"type": "string",  "description": "Servicio base"},
            "command": {"type": "string",  "description": "Comando a ejecutar"},
            "remove":  {"type": "boolean", "description": "Eliminar contenedor al acabar (default: true)"},
        }, "required": ["service", "command"]},
    },
    {
        "name": "compose_config",
        "description": "Valida y muestra la configuración efectiva de Compose con variables resueltas.",
        "inputSchema": {"type": "object", "properties": {
            "path":  {"type": "string",  "description": "Directorio con el fichero compose"},
            "quiet": {"type": "boolean", "description": "Solo validar, sin mostrar el YAML"},
        }},
    },
    {
        "name": "compose_images",
        "description": "Lista las imágenes usadas por los servicios de Compose.",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Directorio con el fichero compose"},
        }},
    },
    {
        "name": "compose_top",
        "description": "Muestra los procesos corriendo dentro de los contenedores de Compose.",
        "inputSchema": {"type": "object", "properties": {
            "path":    {"type": "string", "description": "Directorio con el fichero compose"},
            "service": {"type": "string", "description": "Servicio específico (vacío = todos)"},
        }},
    },
    {
        "name": "build_symbol_index",
        "description": "Genera o actualiza el índice de símbolos del proyecto con ctags. Llama antes de find_symbol si el proyecto no está indexado.",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Directorio a indexar (vacío = directorio actual)"},
        }},
    },
    {
        "name": "find_symbol",
        "description": "Busca dónde está definida una función, clase o variable en el proyecto. Devuelve fichero y número de línea.",
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Nombre del símbolo a buscar (parcial o completo)"},
            "kind": {"type": "string", "description": "Tipo: función, clase, método, variable, tipo, struct, enum…"},
            "path": {"type": "string", "description": "Directorio donde buscar (vacío = actual)"},
        }, "required": ["name"]},
    },
    {
        "name": "list_symbols",
        "description": "Lista todas las funciones, clases y métodos definidos en un fichero.",
        "inputSchema": {"type": "object", "properties": {
            "path":  {"type": "string", "description": "Ruta al fichero"},
            "kinds": {"type": "string", "description": "Tipos a listar: función,clase,método,variable (vacío = todos)"},
        }, "required": ["path"]},
    },
    {
        "name": "lint_file",
        "description": "Ejecuta linters sobre un fichero y devuelve diagnósticos: ruff/mypy (Python), eslint (JS/TS), shellcheck (bash), cppcheck (C/C++). PREFERIDO sobre `bash cppcheck` para analizar código C.",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Ruta al fichero a analizar"},
        }, "required": ["path"]},
    },
    {
        "name": "lint_project",
        "description": "Ejecuta linters sobre todo el proyecto de forma resumida (ruff, mypy, shellcheck).",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Directorio a analizar (vacío = directorio actual)"},
        }},
    },
    {
        "name": "url_encode",
        "description": "Codifica o decodifica texto: URL percent-encoding, form-encoding y Base64.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text":      {"type": "string", "description": "Texto a codificar/decodificar"},
                "operation": {"type": "string", "description": "Operación: encode (URL), decode, b64encode, b64decode, urlencode_form (default: encode)"},
                "encoding":  {"type": "string", "description": "Codificación de caracteres (default: utf-8)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "count_lines",
        "description": "Cuenta líneas de código, comentarios y líneas en blanco por lenguaje en un directorio (estilo cloc).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory":  {"type": "string", "description": "Directorio raíz (default: '.')"},
                "extensions": {"type": "string", "description": "Extensiones a contar separadas por coma, ej. 'py,js'. Si se omite, cuenta todas las conocidas."},
                "max_depth":  {"type": "integer","description": "Profundidad máxima (default: 15)"},
            },
        },
    },
    {
        "name": "template_fill",
        "description": "Rellena una plantilla de texto con variables. Soporta {{clave}}, {clave} y ${clave}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template":  {"type": "string", "description": "Texto de la plantilla con variables"},
                "variables": {"type": "object", "description": "Objeto JSON con los valores {clave: valor}"},
                "style":     {"type": "string", "description": "Estilo de variable: double={{clave}} (default), single={clave}, dollar=${clave}"},
            },
            "required": ["template", "variables"],
        },
    },
    # ── Filesystem tools ──────────────────────────────────────────────────────
    {
        "name": "ls_file",
        "description": "Información detallada (stat) de un fichero o directorio: permisos, propietario, tamaño, fechas, inodo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero o directorio"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "ls_dir",
        "description": "USA ESTO en lugar de 'bash ls -la'. Lista el contenido de un directorio con permisos, propietario, tamaño y fecha. Para ver la estructura completa de un proyecto usa `tree`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":   {"type": "string",  "description": "Directorio a listar (ruta absoluta, default: '.')"},
                "hidden": {"type": "boolean", "description": "Mostrar ficheros ocultos (default: false)"},
                "sort":   {"type": "string",  "description": "Ordenar por: 'name' (default) | 'size' | 'mtime'"},
            },
        },
    },
    {
        "name": "find_file",
        "description": "USA ESTO en lugar de 'bash find -name' o 'bash find -type f'. Busca ficheros por patrón glob en un directorio. Pasa ruta absoluta en `path`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":     {"type": "string",  "description": "Directorio de búsqueda (default: '.')"},
                "pattern":  {"type": "string",  "description": "Patrón glob, ej. '*.py', 'test_*' (default: '*')"},
                "maxdepth": {"type": "integer", "description": "Profundidad máxima (default: 10)"},
                "limit":    {"type": "integer", "description": "Resultados máximos (default: 100, max 500)"},
            },
        },
    },
    {
        "name": "find_dir",
        "description": "USA ESTO en lugar de 'bash find -type d'. Busca directorios por patrón glob.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":     {"type": "string",  "description": "Directorio de búsqueda (default: '.')"},
                "pattern":  {"type": "string",  "description": "Patrón glob, ej. '__pycache__', 'test*' (default: '*')"},
                "maxdepth": {"type": "integer", "description": "Profundidad máxima (default: 8)"},
                "limit":    {"type": "integer", "description": "Resultados máximos (default: 100, max 500)"},
            },
        },
    },
    {
        "name": "grep_file",
        "description": "Busca un patrón regex en un fichero con números de línea y contexto opcional.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string",  "description": "Ruta del fichero a buscar"},
                "pattern":     {"type": "string",  "description": "Expresión regular a buscar"},
                "context":     {"type": "integer", "description": "Líneas de contexto antes y después (default: 0)"},
                "ignore_case": {"type": "boolean", "description": "Ignorar mayúsculas (default: false)"},
                "limit":       {"type": "integer", "description": "Número máximo de coincidencias (default: 50, max 200)"},
            },
            "required": ["path", "pattern"],
        },
    },
    {
        "name": "chmod_file",
        "description": "Cambia los permisos de un fichero (chmod).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero"},
                "mode": {"type": "string", "description": "Permisos en octal: '644', '755', '600', etc."},
            },
            "required": ["path", "mode"],
        },
    },
    {
        "name": "chmod_dir",
        "description": "Cambia los permisos de un directorio, opcionalmente de forma recursiva.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":      {"type": "string",  "description": "Ruta del directorio"},
                "mode":      {"type": "string",  "description": "Permisos en octal: '755', '750', '700', etc."},
                "recursive": {"type": "boolean", "description": "Aplicar recursivamente a todo el contenido (default: false)"},
            },
            "required": ["path", "mode"],
        },
    },
    {
        "name": "chown_file",
        "description": "Cambia el propietario (y opcionalmente el grupo) de un fichero.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Ruta del fichero"},
                "owner": {"type": "string", "description": "Usuario o 'usuario:grupo', ej. 'root', 'www-data:www-data'"},
            },
            "required": ["path", "owner"],
        },
    },
    {
        "name": "chown_dir",
        "description": "Cambia el propietario de un directorio, opcionalmente de forma recursiva.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":      {"type": "string",  "description": "Ruta del directorio"},
                "owner":     {"type": "string",  "description": "Usuario o 'usuario:grupo'"},
                "recursive": {"type": "boolean", "description": "Aplicar recursivamente (default: false)"},
            },
            "required": ["path", "owner"],
        },
    },
    {
        "name": "mv_file",
        "description": "Mueve o renombra un fichero o directorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Ruta de origen"},
                "dst": {"type": "string", "description": "Ruta de destino"},
            },
            "required": ["src", "dst"],
        },
    },
    {
        "name": "cp_file",
        "description": "Copia un fichero o directorio (copytree para directorios).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Ruta de origen"},
                "dst": {"type": "string", "description": "Ruta de destino"},
            },
            "required": ["src", "dst"],
        },
    },
    {
        "name": "rm_file",
        "description": "Elimina un fichero.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero a eliminar"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "rm_dir",
        "description": "Elimina un directorio (vacío por defecto, o recursivamente con recursive=true).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":      {"type": "string",  "description": "Ruta del directorio a eliminar"},
                "recursive": {"type": "boolean", "description": "Eliminar contenido recursivamente (default: false)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "mkdir_dir",
        "description": "Crea un directorio y los directorios padre necesarios (mkdir -p).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del directorio a crear"},
                "mode": {"type": "string", "description": "Permisos en octal (default: '755')"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "touch_file",
        "description": "Crea un fichero vacío o actualiza su fecha de modificación.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero"},
            },
            "required": ["path"],
        },
    },
    # ── Debug de procesos ────────────────────────────────────────────────────
    {
        "name": "strace_run",
        "description": "Traza syscalls de un comando (ej. 'ls /tmp') o de un proceso PID existente con strace. Útil para depurar llamadas al sistema, ficheros abiertos, red.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command":  {"type": "string",  "description": "Comando a ejecutar con strace, ej. 'python3 script.py'"},
                "pid":      {"type": "integer", "description": "PID del proceso al que hacer attach (alternativa a command)"},
                "syscalls": {"type": "string",  "description": "Filtro de syscalls, ej. 'open,read,write,connect'"},
                "timeout":  {"type": "integer", "description": "Timeout en segundos (max 60, default 15)"},
                "count":    {"type": "boolean", "description": "Mostrar estadística de llamadas (-c) en lugar del trace"},
            },
        },
    },
    {
        "name": "gdb_run",
        "description": "Ejecuta GDB en modo batch sobre un binario o core dump con comandos GDB. Para depurar crashes, inspeccionar estado, analizar cores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary":    {"type": "string", "description": "Ruta al binario ejecutable", "required": True},
                "core":      {"type": "string", "description": "Fichero core dump (opcional)"},
                "commands":  {"type": "string", "description": "Comandos GDB separados por \\n (default: info registers + backtrace + quit)"},
                "args":      {"type": "string", "description": "Argumentos del binario"},
                "directory": {"type": "string", "description": "Directorio de trabajo (default: cwd)"},
                "timeout":   {"type": "integer","description": "Timeout en segundos (max 120, default 30)"},
            },
            "required": ["binary"],
        },
    },
    {
        "name": "pdb_run",
        "description": "Ejecuta un script Python bajo pdb de forma no interactiva. Acepta comandos pdb (b, r, n, p, bt, q). Útil para inspeccionar estado en un punto concreto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script":   {"type": "string", "description": "Ruta al script Python", "required": True},
                "commands": {"type": "string", "description": "Comandos pdb separados por \\n, ej. 'b 42\\nr\\np variable\\nbt\\nq'"},
                "env":      {"type": "object", "description": "Variables de entorno adicionales {CLAVE: VALOR}"},
                "timeout":  {"type": "integer","description": "Timeout en segundos (max 120, default 30)"},
            },
            "required": ["script"],
        },
    },
    {
        "name": "valgrind_run",
        "description": "Analiza memoria de un binario C/C++ con Valgrind. Detecta memory leaks, use-after-free, buffer overflows.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "binary":    {"type": "string", "description": "Ruta al binario ejecutable", "required": True},
                "args":      {"type": "string", "description": "Argumentos del binario"},
                "tool":      {"type": "string", "description": "memcheck (default) | callgrind | helgrind | massif"},
                "directory": {"type": "string", "description": "Directorio de trabajo (default: cwd)"},
                "timeout":   {"type": "integer","description": "Timeout en segundos (max 300, default 60)"},
            },
            "required": ["binary"],
        },
    },
    # ── Build y ejecución ────────────────────────────────────────────────────
    {
        "name": "make_run",
        "description": "Ejecuta un target de Makefile con salida completa. Detecta automáticamente el Makefile en el directorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target":    {"type": "string",  "description": "Target Make (vacío = target por defecto)"},
                "directory": {"type": "string",  "description": "Directorio con el Makefile (default: cwd)"},
                "jobs":      {"type": "integer", "description": "Paralelismo: -j N (0 = sin flag)"},
                "timeout":   {"type": "integer", "description": "Timeout en segundos (max 600, default 120)"},
                "vars":      {"type": "string",  "description": "Variables Make adicionales, ej. 'DEBUG=1 PREFIX=/usr'"},
            },
        },
    },
    {
        "name": "run_script",
        "description": "Ejecuta un script (Python, bash, sh, node, ruby, php) con timeout y captura de stdout/stderr por separado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script":      {"type": "string", "description": "Ruta al script a ejecutar", "required": True},
                "args":        {"type": "string", "description": "Argumentos del script separados por espacios"},
                "interpreter": {"type": "string", "description": "Forzar intérprete: python3, bash, node, ruby... (auto-detectado por extensión si no se especifica)"},
                "directory":   {"type": "string", "description": "Directorio de trabajo (default: directorio del script)"},
                "env":         {"type": "object", "description": "Variables de entorno adicionales {CLAVE: VALOR}"},
                "timeout":     {"type": "integer","description": "Timeout en segundos (max 300, default 60)"},
            },
            "required": ["script"],
        },
    },
    {
        "name": "format_code",
        "description": "Formatea código con la herramienta adecuada: black/isort (Python), prettier (JS/TS/JSON/CSS), gofmt (Go), rustfmt (Rust), clang-format (C/C++).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Ruta al fichero o directorio a formatear", "required": True},
                "tool":  {"type": "string", "description": "auto (default) | black | isort | prettier | gofmt | rustfmt | clang-format"},
                "check": {"type": "boolean","description": "Solo verificar sin modificar (default: false)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "mypy_check",
        "description": "Comprueba tipos con mypy sobre un fichero o directorio Python. Detecta errores de tipado estático.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":                  {"type": "string",  "description": "Fichero o directorio a analizar (default: '.')"},
                "strict":                {"type": "boolean", "description": "Modo estricto --strict (default: false)"},
                "ignore_missing_imports":{"type": "boolean", "description": "Ignorar imports sin stubs (default: true)"},
            },
        },
    },
    # ── Python tools ─────────────────────────────────────────────────────────
    {
        "name": "python_exec",
        "description": (
            "Ejecuta código Python inline y captura stdout/stderr. "
            "PREFERIDO sobre crear ficheros .py temporales Y sobre `bash python3 << 'EOF'` heredocs. "
            "Usa `workdir` para operar en un directorio concreto — así evitas `cd /ruta && python3`. "
            "Úsalo para transformaciones de datos, análisis de ficheros, cálculos, validaciones o cualquier lógica Python puntual."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code":    {"type": "string",  "description": "Código Python a ejecutar"},
                "workdir": {"type": "string",  "description": "Directorio de trabajo (ruta absoluta). Úsalo en vez de os.chdir() o 'cd /ruta && python3'."},
                "timeout": {"type": "integer", "description": "Timeout en segundos (max 60, default 15)"},
                "env":     {"type": "object",  "description": "Variables de entorno adicionales {CLAVE: VALOR}"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "pip_tool",
        "description": "Gestión de paquetes pip: list/show/install/freeze/check/outdated. Usa el Python del entorno activo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action":   {"type": "string", "description": "list | show | install | freeze | check | outdated (default: list)"},
                "packages": {"type": "string", "description": "Nombres de paquetes separados por espacios (obligatorio para show/install)"},
            },
        },
    },
    # ── Node.js tools ────────────────────────────────────────────────────────
    {
        "name": "npm_tool",
        "description": "Gestión de paquetes npm: list/run/info/install/audit/outdated. Opera en el directorio del proyecto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action":    {"type": "string", "description": "list | run | info | install | audit | outdated | ci (default: list)"},
                "packages":  {"type": "string", "description": "Paquetes a instalar/consultar, o nombre del script npm para 'run'"},
                "directory": {"type": "string", "description": "Directorio del proyecto Node.js (default: cwd)"},
            },
        },
    },
    # ── Archive tools ────────────────────────────────────────────────────────
    {
        "name": "archive_extract",
        "description": "Extrae archivos comprimidos: .zip, .tar.gz, .tgz, .tar.bz2, .tar.xz, .tar, .gz.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "archive":          {"type": "string",  "description": "Ruta al archivo a extraer", "required": True},
                "destination":      {"type": "string",  "description": "Directorio de destino (default: directorio del archivo)"},
                "strip_components": {"type": "integer", "description": "Número de niveles de directorio a eliminar (--strip-components)"},
            },
            "required": ["archive"],
        },
    },
    {
        "name": "archive_create",
        "description": "Crea archivos comprimidos: .tar.gz, .tar.bz2, .tar.xz o .zip a partir de ficheros/directorios.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "archive":  {"type": "string", "description": "Ruta del archivo de salida, ej. 'proyecto.tar.gz'", "required": True},
                "sources":  {"type": "string", "description": "Ficheros/directorios a comprimir separados por espacios", "required": True},
                "compress": {"type": "string", "description": "gz (default) | bz2 | xz | zip | none"},
            },
            "required": ["archive", "sources"],
        },
    },
    {
        "name": "archive_list",
        "description": "Lista el contenido de un archivo comprimido (.zip, .tar.gz, .tar.bz2, .tar.xz, .tar) sin extraerlo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "archive":   {"type": "string",  "description": "Ruta al archivo", "required": True},
                "max_lines": {"type": "integer", "description": "Máximo de entradas a mostrar (default: 200)"},
            },
            "required": ["archive"],
        },
    },
    # ── Metadatos de ficheros ────────────────────────────────────────────────
    {
        "name": "file_stat",
        "description": "USA ESTO en lugar de 'bash wc -l' o 'bash stat'. Muestra metadatos completos: permisos, propietario, tamaño, nº de líneas (para ficheros de texto), inode, tiempos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta al fichero, directorio o symlink", "required": True},
            },
            "required": ["path"],
        },
    },
    {
        "name": "symlink_create",
        "description": "Crea un enlace simbólico (equivalente a ln -s target link_path).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target":    {"type": "string",  "description": "Destino al que apuntará el enlace", "required": True},
                "link_path": {"type": "string",  "description": "Ruta del nuevo enlace simbólico", "required": True},
                "force":     {"type": "boolean", "description": "Reemplazar si ya existe (default: false)"},
            },
            "required": ["target", "link_path"],
        },
    },
    {
        "name": "readlink",
        "description": "Resuelve el destino de un enlace simbólico. Muestra el destino directo y la ruta absoluta resuelta.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string",  "description": "Ruta al enlace simbólico", "required": True},
                "resolve": {"type": "boolean", "description": "Resolver a ruta absoluta (default: true)"},
            },
            "required": ["path"],
        },
    },
    # ── Parches ──────────────────────────────────────────────────────────────
    {
        "name": "patch_apply",
        "description": "Aplica un diff unificado (unified diff) a ficheros del proyecto. Soporta dry-run para verificar sin modificar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patch":      {"type": "string",  "description": "Contenido del diff unificado (alternativa a patch_file)"},
                "patch_file": {"type": "string",  "description": "Ruta a un fichero .patch (alternativa a patch)"},
                "directory":  {"type": "string",  "description": "Directorio donde aplicar el patch (default: cwd)"},
                "dry_run":    {"type": "boolean", "description": "Solo verificar, no modificar (default: false)"},
                "strip":      {"type": "integer", "description": "Nivel de strip de prefijos de ruta (-p, default: 1)"},
            },
        },
    },
    # ── Visualización y exploración ──────────────────────────────────────────
    {
        "name": "analyze_codebase",
        "description": (
            "PRIMERA HERRAMIENTA a llamar antes de trabajar en un proyecto o directorio desconocido. "
            "Análisis estructurado completo: conteo de ficheros por lenguaje, árbol de directorios, "
            "ficheros más recientes y búsqueda de patrón opcional. Combina tree+count_lines+find+grep "
            "en UNA SOLA llamada. Úsala para mapear el problema ANTES de leer o editar ficheros. "
            "Mucho mejor que `bash ls -la && find -name && grep -rn`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory":  {"type": "string",  "description": "Directorio a analizar (ruta absoluta, default: '.')"},
                "pattern":    {"type": "string",  "description": "Patrón de búsqueda opcional en el código (se busca con grep_code internamente)"},
                "extensions": {"type": "string",  "description": "Filtrar ficheros por extensión, ej. 'c,h,cpp' para C/C++, 'py' para Python"},
                "max_files":  {"type": "integer", "description": "Máximo de ficheros recientes a mostrar (default: 10, max: 50)"},
                "depth":      {"type": "integer", "description": "Profundidad del árbol de directorios (default: 2, max: 5)"},
            },
        },
    },
    {
        "name": "tree",
        "description": (
            "Muestra la estructura jerárquica de un directorio (estilo `tree`). "
            "PREFERIDO sobre `bash find . | sort` o `bash ls -la` para explorar proyectos. "
            "Usa `depth` para controlar la profundidad y `dirs_only=true` para ver solo carpetas."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory":   {"type": "string",  "description": "Directorio raíz (ruta absoluta, default: directorio actual)"},
                "depth":       {"type": "integer", "description": "Profundidad máxima (default: 3, max: 10)"},
                "show_hidden": {"type": "boolean", "description": "Mostrar ficheros y directorios ocultos (default: false)"},
                "dirs_only":   {"type": "boolean", "description": "Mostrar solo directorios, no ficheros (default: false)"},
                "max_entries": {"type": "integer", "description": "Número máximo de entradas a mostrar (default: 300)"},
            },
        },
    },
    # ── Edición avanzada ─────────────────────────────────────────────────────
    {
        "name": "bulk_replace",
        "description": (
            "Aplica un reemplazo regex (Python re.sub) a todos los ficheros que coincidan con un glob. "
            "PREFERIDO sobre `bash python3 << 'EOF'` o scripts Python para modificar múltiples ficheros a la vez. "
            "Usa `dry_run=true` para verificar qué ficheros se modificarían antes de aplicar. "
            "Ejemplo: reemplazar patrones de error handling en todos los .c de un proyecto."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory":   {"type": "string",  "description": "Directorio raíz donde buscar (ruta absoluta)"},
                "pattern":     {"type": "string",  "description": "Patrón regex Python (re.sub)"},
                "replacement": {"type": "string",  "description": "Texto de reemplazo (puede usar grupos \\1, \\2)"},
                "glob":        {"type": "string",  "description": "Patrón glob para seleccionar ficheros (default: '**/*'). Ej: '**/*.c', 'src/**/*.py'"},
                "extensions":  {"type": "string",  "description": "Filtro adicional por extensiones separadas por coma. Ej: 'c,h' para C, 'py' para Python"},
                "flags":       {"type": "string",  "description": "Flags: MULTILINE (M), IGNORECASE (I), DOTALL (S)"},
                "dry_run":     {"type": "boolean", "description": "Solo mostrar qué ficheros se modificarían, sin cambiar nada (default: false)"},
                "max_files":   {"type": "integer", "description": "Máximo de ficheros a procesar (default: 50, max: 200)"},
            },
            "required": ["pattern", "replacement"],
        },
    },
    {
        "name": "regex_replace",
        "description": (
            "Reemplaza un patrón regex (Python re.sub) en un fichero y muestra el diff. "
            "PREFERIDO sobre `bash sed -i`, `bash python3 << 'EOF'` o scripts Python inline "
            "para modificar ficheros con patrones regex. Usa `dry_run=true` para verificar antes. "
            "Soporta grupos de captura (\\1, \\2) en el reemplazo."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file":        {"type": "string",  "description": "Ruta absoluta del fichero a modificar"},
                "pattern":     {"type": "string",  "description": "Patrón regex Python (re.sub). Ej: r'if \\(fp == NULL\\)' o r'fopen\\(([^,]+),\\s*\"r\"\\)'"},
                "replacement": {"type": "string",  "description": "Texto de reemplazo. Puede usar grupos \\1, \\2. Ej: 'if (fp == NULL) { perror(\"fopen\"); }'"},
                "flags":       {"type": "string",  "description": "Flags separadas por coma: MULTILINE (M), IGNORECASE (I), DOTALL (S). Ej: 'MULTILINE,DOTALL'"},
                "count":       {"type": "integer", "description": "Máximo de reemplazos (0 = todos, default: 0)"},
                "dry_run":     {"type": "boolean", "description": "Solo mostrar diff sin modificar el fichero (default: false)"},
                "backup":      {"type": "boolean", "description": "Crear fichero .bak antes de modificar (default: false)"},
            },
            "required": ["file", "pattern", "replacement"],
        },
    },
    # ── Edición segura compuesta ──────────────────────────────────────────────
    {
        "name": "smart_replace",
        "description": (
            "Reemplaza un patrón regex en un fichero CON VERIFICACIÓN PREVIA: si el patrón no existe "
            "muestra las primeras líneas del fichero para corregir el patrón. Si existe aplica el "
            "reemplazo y muestra el diff. PREFERIDO sobre regex_replace/bulk_replace cuando no estás "
            "seguro de que el patrón coincide — evita el bucle de reintentos fallidos."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file":          {"type": "string",  "description": "Ruta absoluta del fichero a modificar"},
                "pattern":       {"type": "string",  "description": "Patrón regex Python"},
                "replacement":   {"type": "string",  "description": "Texto de reemplazo (soporta grupos \\1, \\2)"},
                "flags":         {"type": "string",  "description": "Flags: MULTILINE, IGNORECASE, DOTALL (separadas por coma)"},
                "dry_run":       {"type": "boolean", "description": "Solo mostrar diff sin guardar (default: false)"},
                "context_lines": {"type": "integer", "description": "Líneas de contexto en el diff (default: 3)"},
            },
            "required": ["file", "pattern", "replacement"],
        },
    },
    {
        "name": "context_before_edit",
        "description": (
            "Muestra el contexto exacto (líneas numeradas con →) alrededor del patrón a editar. "
            "Úsalo ANTES de edit_file o regex_replace cuando no estás seguro del texto exacto — "
            "evita errores de 'old_string no encontrado'. Busca con regex; si falla usa literal casefold."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file":          {"type": "string",  "description": "Ruta absoluta del fichero"},
                "pattern":       {"type": "string",  "description": "Patrón a buscar (regex o texto literal)"},
                "context_lines": {"type": "integer", "description": "Líneas de contexto arriba/abajo de cada coincidencia (default: 8)"},
                "max_hits":      {"type": "integer", "description": "Máximo de coincidencias a mostrar (default: 5)"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "pre_edit_check",
        "description": (
            "Análisis previo a una edición: muestra estructura del fichero (tamaño, líneas totales) "
            "más un rango de líneas y el contexto alrededor del área de interés. "
            "Combina file_stat + read_file(offset) + context_before_edit en una sola llamada."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file":   {"type": "string",  "description": "Ruta absoluta del fichero"},
                "focus":  {"type": "string",  "description": "Palabra clave o patrón para localizar el área de interés"},
                "offset": {"type": "integer", "description": "Línea desde la que empezar a mostrar (default: 0)"},
                "limit":  {"type": "integer", "description": "Número de líneas a mostrar (default: 60)"},
            },
            "required": ["file"],
        },
    },
    # ── Markdown y XML ───────────────────────────────────────────────────────
    {
        "name": "render_markdown",
        "description": (
            "Valida y previsualiza Markdown: cuenta cabeceras, bloques de código, tablas y enlaces. "
            "Opcionalmente guarda el resultado en un fichero. Útil para generar informes .md y "
            "verificar estructura antes de entregarlos al usuario."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text":   {"type": "string", "description": "Texto Markdown a renderizar"},
                "file":   {"type": "string", "description": "Ruta de fichero .md a leer (alternativa a text)"},
                "output": {"type": "string", "description": "Ruta donde guardar el Markdown (opcional)"},
            },
        },
    },
    {
        "name": "xml_format",
        "description": (
            "Formatea y pretty-prints XML con indentación correcta. "
            "Acepta texto XML o ruta de fichero. Opcionalmente guarda el XML formateado."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text":   {"type": "string",  "description": "Texto XML a formatear"},
                "file":   {"type": "string",  "description": "Ruta de fichero .xml a formatear"},
                "indent": {"type": "integer", "description": "Espacios de indentación (default: 2)"},
                "output": {"type": "string",  "description": "Ruta donde guardar el XML formateado (opcional)"},
            },
        },
    },
    {
        "name": "xml_validate",
        "description": (
            "Valida que un documento XML esté bien formado (siempre). "
            "Si se pasa 'schema', valida también contra el esquema XSD (requiere lxml)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text":   {"type": "string", "description": "Texto XML a validar"},
                "file":   {"type": "string", "description": "Ruta de fichero .xml a validar"},
                "schema": {"type": "string", "description": "Ruta del esquema XSD (opcional)"},
            },
        },
    },
    # ── Linters especializados ───────────────────────────────────────────────────
    {
        "name": "gitlint_check",
        "description": (
            "Comprueba el mensaje de uno o varios commits con gitlint. "
            "Detecta problemas de formato: asunto muy largo, falta de línea en blanco, "
            "tipo de commit inválido (Conventional Commits), etc."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "count":     {"type": "integer", "description": "Número de commits a comprobar desde HEAD (default: 1)"},
                "commit":    {"type": "string",  "description": "SHA o referencia específica de commit (default: HEAD)"},
                "directory": {"type": "string",  "description": "Directorio del repositorio git (default: '.')"},
            },
        },
    },
    {
        "name": "ansible_lint",
        "description": (
            "Ejecuta ansible-lint sobre un playbook o directorio de roles Ansible. "
            "Detecta problemas de estilo, seguridad y buenas prácticas. "
            "Usa perfiles: min, basic, moderate (default), safety, shared, production."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Ruta al playbook .yml o directorio de roles (default: '.')"},
                "profile": {"type": "string", "description": "'min' | 'basic' | 'moderate' | 'safety' | 'shared' | 'production' (default: 'moderate')"},
                "tags":    {"type": "string", "description": "Tags de reglas a ejecutar (ej. 'yaml,formatting', opcional)"},
            },
        },
    },
    {
        "name": "efm_config_update",
        "description": (
            "Regenera la config de efm-langserver en ~/.oocode/efm-langserver.yaml. "
            "Detecta automáticamente los linters instalados (xmllint, rpmlint, ansible-lint, "
            "gitlint, jsonlint, markdownlint) y configura cada uno como backend LSP. "
            "Llamar cuando se instale un nuevo linter o LSP relacionado."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]

def _resource_project_templates() -> str:
    """Plantillas de código por lenguaje para generación rápida."""
    return """\
# Plantillas de código — OOCode

## C (C17)
```c
// module.h
#ifndef MODULE_H
#define MODULE_H
#include <stdint.h>
#include <stdbool.h>
typedef struct { int32_t value; } ModuleCtx;
bool module_init(ModuleCtx *ctx);
void module_free(ModuleCtx *ctx);
#endif

// module.c
#include "module.h"
#include <stdlib.h>
bool module_init(ModuleCtx *ctx) { ctx->value = 0; return true; }
void module_free(ModuleCtx *ctx) { (void)ctx; }
```

## C++ (C++17)
```cpp
// widget.hpp
#pragma once
#include <memory>
#include <string>
class Widget {
public:
    explicit Widget(std::string name);
    ~Widget() = default;
    Widget(const Widget&) = delete;
    Widget& operator=(const Widget&) = delete;
    void render() const;
private:
    struct Impl; std::unique_ptr<Impl> pimpl_;
};
```

## Bash
```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
usage() { echo "Usage: $0 [-v] <arg>"; exit 1; }
log() { echo "[$(date +%T)] $*" >&2; }
main() {
  local verbose=false
  while getopts "vh" opt; do
    case $opt in v) verbose=true ;; *) usage ;; esac
  done
  shift $((OPTIND-1))
  [[ $# -eq 0 ]] && usage
  log "Processing $1"
}
main "$@"
```

## Python (3.12+)
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class Config:
    path: Path
    verbose: bool = False

def process(config: Config) -> Optional[str]:
    if not config.path.exists():
        raise FileNotFoundError(config.path)
    return config.path.read_text()
```

## Perl (modern)
```perl
#!/usr/bin/env perl
use strict; use warnings; use utf8; use 5.020;
use Getopt::Long qw(GetOptions);
use Pod::Usage qw(pod2usage);

my %opts = (verbose => 0);
GetOptions(\\%opts, 'verbose|v', 'help|h') or pod2usage(2);
pod2usage(1) if $opts{help};

=head1 NAME script - description
=head1 SYNOPSIS script [--verbose] <arg>
=cut
```

## JavaScript/TypeScript (ESM)
```typescript
// module.ts
export interface Config { name: string; debug?: boolean; }
export async function process(config: Config): Promise<string> {
  const { name, debug = false } = config;
  if (!name) throw new Error('name required');
  if (debug) console.debug('[process]', name);
  return `processed:${name}`;
}
```

## SQL (PostgreSQL)
```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS items (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT        NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata    JSONB
);
CREATE INDEX idx_items_created_at ON items(created_at DESC);
COMMENT ON TABLE items IS 'Main items table';
```

## Ruby (3.x)
```ruby
# frozen_string_literal: true
require 'pathname'
class Processor
  def initialize(path)
    @path = Pathname.new(path)
  end

  def call
    raise ArgumentError, "not found: #{@path}" unless @path.exist?
    @path.read
  end
end
```

## Java (21)
```java
// Processor.java
package com.example;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

public record Processor(Path path) {
    public String call() throws IOException {
        if (!Files.exists(path)) throw new IllegalArgumentException("not found: " + path);
        return Files.readString(path);
    }
}
```

## YAML (config)
```yaml
# config.yaml
app:
  name: myapp
  version: "1.0"
  debug: ${APP_DEBUG:-false}

database:
  host: ${DB_HOST:-localhost}
  port: ${DB_PORT:-5432}
  name: ${DB_NAME:-mydb}

logging:
  level: ${LOG_LEVEL:-INFO}
  format: json
```
"""


def _resource_report_template_md() -> str:
    """Plantilla estándar de informe en Markdown."""
    return """\
# [Título del informe]

**Fecha:** [YYYY-MM-DD]
**Autor:** [OOCode / nombre del agente]
**Versión:** 1.0

---

## Resumen ejecutivo

[Descripción breve — 2-3 frases — del propósito y resultado principal del informe.]

## Detalles técnicos

### [Subtema 1]

[Contenido detallado con contexto técnico.]

```
[Código, logs o datos relevantes]
```

### [Subtema 2]

[Contenido adicional.]

## Hallazgos

| # | Hallazgo | Severidad | Estado |
|---|----------|-----------|--------|
| 1 | [descripción] | Alta / Media / Baja | Abierto / Resuelto |
| 2 | [descripción] | Media | Abierto |

## Conclusiones

- [Conclusión 1]
- [Conclusión 2]
- [Conclusión 3]

## Recomendaciones

1. **[Recomendación 1]** — [justificación breve]
2. **[Recomendación 2]** — [justificación breve]

---

_Generado con OOCode — [fecha]_
"""


def _resource_report_template_xml() -> str:
    """Plantilla estándar de informe en XML bien formado."""
    return """\
<?xml version="1.0" encoding="UTF-8"?>
<report>
  <metadata>
    <title>Título del informe</title>
    <date>YYYY-MM-DD</date>
    <author>OOCode</author>
    <version>1.0</version>
  </metadata>

  <summary>
    Descripción breve del propósito y resultado principal del informe.
  </summary>

  <details>
    <section id="1">
      <title>Subtema 1</title>
      <content>Contenido detallado con contexto técnico.</content>
      <code language="python"><![CDATA[
# Ejemplo de código
print("hola")
      ]]></code>
    </section>
    <section id="2">
      <title>Subtema 2</title>
      <content>Contenido adicional.</content>
    </section>
  </details>

  <findings>
    <finding id="1" severity="high" status="open">
      <description>Descripción del hallazgo</description>
    </finding>
    <finding id="2" severity="medium" status="resolved">
      <description>Descripción del hallazgo resuelto</description>
    </finding>
  </findings>

  <conclusions>
    <item>Conclusión 1</item>
    <item>Conclusión 2</item>
  </conclusions>

  <recommendations>
    <item priority="1">Recomendación 1 — justificación</item>
    <item priority="2">Recomendación 2 — justificación</item>
  </recommendations>
</report>
"""


_RESOURCES = [
    {
        "uri":         "project://context",
        "name":        "Contexto del proyecto",
        "description": "OOCODE.md + README.md + pyproject.toml del directorio actual",
        "mimeType":    "text/markdown",
    },
    {
        "uri":         "project://structure",
        "name":        "Estructura del proyecto",
        "description": "Árbol de directorios (2 niveles) del directorio actual",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://git",
        "name":        "Estado git",
        "description": "git status + últimos 10 commits + diff stats del directorio actual",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://deps",
        "name":        "Dependencias del proyecto",
        "description": "pyproject.toml / requirements.txt / package.json — dependencias parseadas",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://tests",
        "name":        "Tests del proyecto",
        "description": "Ficheros de test encontrados en el proyecto y recopilación pytest",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://env",
        "name":        "Variables de entorno",
        "description": "Variables de entorno de desarrollo relevantes (secretos ocultos)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://errors",
        "name":        "Logs de error del sistema",
        "description": "Últimas entradas de error del sistema vía journalctl o /var/log/syslog",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://metrics",
        "name":        "Métricas de código",
        "description": "Líneas de código, ficheros y tamaño por extensión/lenguaje",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://changelog",
        "name":        "Changelog del proyecto",
        "description": "CHANGELOG.md / CHANGES.rst / HISTORY.md del proyecto o directorio raíz",
        "mimeType":    "text/markdown",
    },
    {
        "uri":         "project://docker",
        "name":        "Estado Docker",
        "description": "Contenedores activos, imágenes, redes y volúmenes Docker",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://coverage",
        "name":        "Cobertura de tests",
        "description": "Informe de cobertura más reciente (coverage.xml, .coverage, htmlcov)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://makefile",
        "name":        "Targets del Makefile",
        "description": "Targets disponibles en el Makefile del proyecto con sus recetas",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://ci",
        "name":        "Configuración CI/CD",
        "description": "Workflows de GitHub Actions, GitLab CI, Jenkinsfile o similar",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://lint",
        "name":        "Estado de linting",
        "description": "Resultado actual de ruff/mypy/eslint/cppcheck sobre el proyecto",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://openapi",
        "name":        "Esquema OpenAPI / Swagger",
        "description": "openapi.yaml / openapi.json / swagger.yaml del directorio actual",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://todos",
        "name":        "TODOs y FIXMEs del proyecto",
        "description": "Lista de TODO/FIXME/HACK/XXX encontrados en el código fuente",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://processes",
        "name":        "Procesos del sistema",
        "description": "Procesos activos relevantes: servidores, workers, compiladores",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://templates",
        "name":        "Plantillas de código por lenguaje",
        "description": "Templates de C, C++, Bash, Python, Perl, JS/TS, SQL, Ruby, Java y YAML",
        "mimeType":    "text/markdown",
    },
    {
        "uri":         "project://reasoning",
        "name":        "Guía de razonamiento del agente",
        "description": "Reglas y flujos de trabajo para razonar antes de editar — anti-bucle, edición segura, checklist de implementación",
        "mimeType":    "text/markdown",
    },
    {
        "uri":         "project://lsp",
        "name":        "Estado LSP y guía de uso por lenguaje",
        "description": "Servidores LSP activos/instalados + flujo de trabajo por lenguaje (C/C++, Python, JS/TS, Perl, Shell, SQL, YAML, Ruby, Java)",
        "mimeType":    "text/markdown",
    },
    {
        "uri":         "project://interface_contracts",
        "name":        "Interfaces estables del proyecto",
        "description": (
            "Lista de funciones y clases públicas usadas en ≥3 ficheros del proyecto. "
            "Leer ANTES de cualquier refactor para identificar qué interfaces tienen mayor impacto. "
            "Generado con ast.parse + ripgrep — no requiere LLM."
        ),
        "mimeType":    "text/plain",
    },
    {
        "uri":         "report://template_md",
        "name":        "Plantilla de informe Markdown",
        "description": (
            "Plantilla estándar de informe en Markdown con secciones: Resumen ejecutivo, "
            "Detalles técnicos, Hallazgos, Conclusiones y Recomendaciones. "
            "Usar con el prompt generate_report y la tool render_markdown."
        ),
        "mimeType":    "text/markdown",
    },
    {
        "uri":         "report://template_xml",
        "name":        "Plantilla de informe XML",
        "description": (
            "Plantilla estándar de informe en XML bien formado con elementos: summary, details, "
            "findings, conclusions. Usar con el prompt generate_report y la tool xml_validate."
        ),
        "mimeType":    "text/xml",
    },
    {
        "uri":         "project://hooks",
        "name":        "Estado de hooks activos",
        "description": (
            "Lista de hooks builtin activos y disponibles en OOCode, leída de ~/.oocode/oocode.json. "
            "Incluye tipo (pre/post), descripción y cómo togglear con /hooks builtin <nombre>."
        ),
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://active_tools",
        "name":        "Herramientas disponibles por categoría",
        "description": (
            "Inventario completo de todas las herramientas disponibles agrupadas por categoría: "
            "búsqueda, edición, git, docker, tests, build, sistema, memoria. "
            "Usar antes de decidir qué tool llamar para elegir la más apropiada."
        ),
        "mimeType":    "text/plain",
    },
]

_TOOL_FNS = {
    "get_datetime":      _tool_get_datetime,
    "system_info":       _tool_system_info,
    "list_recent_files": _tool_list_recent_files,
    "read_project_file": _tool_read_project_file,
    "run_quick_check":   _tool_run_quick_check,
    "search_todos":      _tool_search_todos,
    "port_check":        _tool_port_check,
    "read_files":        _tool_read_files,
    "http_get":          _tool_http_get,
    "calculate":         _tool_calculate,
    "diff_files":        _tool_diff_files,
    "code_compare":      _tool_code_compare,
    "grep_code":         _tool_grep_code,
    "multi_grep":        _tool_multi_grep,
    "code_outline":      _tool_code_outline,
    "read_sections":     _tool_read_sections,
    "affected_files":    _tool_affected_files,
    "symbol_lookup":     _tool_symbol_lookup,
    "env_check":         _tool_env_check,
    "json_format":       _tool_json_format,
    "hash_text":         _tool_hash_text,
    "write_file":        _tool_write_file,
    "find_files":        _tool_find_files,
    "process_list":      _tool_process_list,
    "url_encode":        _tool_url_encode,
    "count_lines":       _tool_count_lines,
    "template_fill":     _tool_template_fill,
    # Git
    "git_status":        _tool_git_status,
    "git_diff":          _tool_git_diff,
    "git_log":           _tool_git_log,
    "git_add":           _tool_git_add,
    "git_commit":        _tool_git_commit,
    "git_push":          _tool_git_push,
    "git_pull":          _tool_git_pull,
    "git_branch":        _tool_git_branch,
    "git_stash":         _tool_git_stash,
    "git_patch":         _tool_git_patch,
    "git_clone":         _tool_git_clone,
    "git_worktree":      _tool_git_worktree,
    "git_blame":         _tool_git_blame,
    "git_rebase":        _tool_git_rebase,
    "git_tag":           _tool_git_tag,
    "git_cherry_pick":   _tool_git_cherry_pick,
    "json_validate":     _tool_json_validate,
    "yaml_validate":     _tool_yaml_validate,
    "jq_query":          _tool_jq_query,
    # Docker
    "docker_ps":         _tool_docker_ps,
    "docker_logs":       _tool_docker_logs,
    "docker_exec":       _tool_docker_exec,
    "docker_inspect":    _tool_docker_inspect,
    "docker_images":     _tool_docker_images,
    "docker_stop":       _tool_docker_stop,
    "docker_rm":         _tool_docker_rm,
    "docker_cp":         _tool_docker_cp,
    "compose_version":   _tool_compose_version,
    "compose_services":  _tool_compose_services,
    "compose_status":    _tool_compose_status,
    "compose_up":        _tool_compose_up,
    "compose_down":      _tool_compose_down,
    "compose_stop":      _tool_compose_stop,
    "compose_restart":   _tool_compose_restart,
    "compose_build":     _tool_compose_build,
    "compose_pull":      _tool_compose_pull,
    "compose_logs":      _tool_compose_logs,
    "compose_exec":      _tool_compose_exec,
    "compose_run":       _tool_compose_run,
    "compose_config":    _tool_compose_config,
    "compose_images":    _tool_compose_images,
    "compose_top":       _tool_compose_top,
    # Ctags
    "build_symbol_index": _tool_build_symbol_index,
    "find_symbol":         _tool_find_symbol,
    "list_symbols":        _tool_list_symbols,
    # Linter
    "lint_file":           _tool_lint_file,
    "lint_project":        _tool_lint_project,
    # Filesystem
    "ls_file":             _tool_ls_file,
    "ls_dir":              _tool_ls_dir,
    "find_file":           _tool_find_file,
    "find_dir":            _tool_find_dir,
    "grep_file":           _tool_grep_file,
    "chmod_file":          _tool_chmod_file,
    "chmod_dir":           _tool_chmod_dir,
    "chown_file":          _tool_chown_file,
    "chown_dir":           _tool_chown_dir,
    "mv_file":             _tool_mv_file,
    "cp_file":             _tool_cp_file,
    "rm_file":             _tool_rm_file,
    "rm_dir":              _tool_rm_dir,
    "mkdir_dir":           _tool_mkdir_dir,
    "touch_file":          _tool_touch_file,
    # Debug de procesos
    "strace_run":          _tool_strace_run,
    "gdb_run":             _tool_gdb_run,
    "pdb_run":             _tool_pdb_run,
    "valgrind_run":        _tool_valgrind_run,
    # Build y ejecución
    "make_run":            _tool_make_run,
    "run_script":          _tool_run_script,
    "format_code":         _tool_format_code,
    "mypy_check":          _tool_mypy_check,
    # Python
    "python_exec":         _tool_python_exec,
    "pip_tool":            _tool_pip_tool,
    # Node.js
    "npm_tool":            _tool_npm_tool,
    # Archive
    "archive_extract":     _tool_archive_extract,
    "archive_create":      _tool_archive_create,
    "archive_list":        _tool_archive_list,
    # Metadatos de ficheros
    "file_stat":           _tool_file_stat,
    "symlink_create":      _tool_symlink_create,
    "readlink":            _tool_readlink,
    # Parches y edición avanzada
    "patch_apply":         _tool_patch_apply,
    "regex_replace":       _tool_regex_replace,
    "bulk_replace":        _tool_bulk_replace,
    # Edición segura compuesta
    "smart_replace":       _tool_smart_replace,
    "context_before_edit": _tool_context_before_edit,
    "pre_edit_check":      _tool_pre_edit_check,
    # Visualización
    "tree":                _tool_tree,
    # Análisis de proyecto (meta-tool — combina tree+count+grep)
    "analyze_codebase":    _tool_analyze_codebase,
    # Markdown y XML
    "render_markdown":     _tool_render_markdown,
    "xml_format":          _tool_xml_format,
    "xml_validate":        _tool_xml_validate,
    # Linters especializados
    "gitlint_check":       _tool_gitlint_check,
    "ansible_lint":        _tool_ansible_lint,
    "efm_config_update":   _tool_efm_config_update,
}

def _resource_project_makefile() -> str:
    """Targets disponibles en el Makefile del proyecto."""
    root = Path.cwd()
    makefile = None
    for name in ("Makefile", "makefile", "GNUmakefile"):
        p = root / name
        if p.exists():
            makefile = p
            break
    if makefile is None:
        return "(no se encontró Makefile en el directorio actual)"

    content = makefile.read_text(errors="replace")
    lines   = content.splitlines()
    targets = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        # Detecta comentario de ayuda antes del target
        comment = ""
        if i > 0 and lines[i - 1].startswith("##"):
            comment = lines[i - 1][2:].strip()
        # Target: no empieza con tab ni .PHONY ni es variable
        if ln and not ln.startswith("\t") and not ln.startswith("#") and "=" not in ln.split(":")[0]:
            if ":" in ln:
                tgt = ln.split(":")[0].strip()
                recipe_lines = []
                j = i + 1
                while j < len(lines) and lines[j].startswith("\t"):
                    recipe_lines.append(lines[j].strip())
                    j += 1
                recipe = " ; ".join(recipe_lines[:3])
                if len(recipe_lines) > 3:
                    recipe += " …"
                targets.append((tgt, comment, recipe))
        i += 1

    if not targets:
        return f"Makefile encontrado ({makefile.name}) pero sin targets detectados.\n\n" + content[:2000]

    lines_out = [f"## {makefile.name}  ({len(targets)} targets)\n"]
    for tgt, doc, recipe in targets:
        doc_str    = f"  — {doc}" if doc else ""
        recipe_str = f"\n    $ {recipe}" if recipe else ""
        lines_out.append(f"  **{tgt}**{doc_str}{recipe_str}")
    return "\n".join(lines_out)


def _resource_project_ci() -> str:
    """Configuración CI/CD del proyecto."""
    root  = Path.cwd()
    parts = []

    # GitHub Actions
    gh_dir = root / ".github" / "workflows"
    if gh_dir.is_dir():
        workflows = sorted(gh_dir.glob("*.yml")) + sorted(gh_dir.glob("*.yaml"))
        if workflows:
            parts.append("## GitHub Actions workflows\n")
            for wf in workflows[:5]:
                content = wf.read_text(errors="replace")[:1500]
                parts.append(f"### {wf.name}\n```yaml\n{content}\n```")

    # GitLab CI
    gitlab_ci = root / ".gitlab-ci.yml"
    if gitlab_ci.exists():
        content = gitlab_ci.read_text(errors="replace")[:2000]
        parts.append(f"## .gitlab-ci.yml\n```yaml\n{content}\n```")

    # Jenkins
    jenkinsfile = root / "Jenkinsfile"
    if jenkinsfile.exists():
        content = jenkinsfile.read_text(errors="replace")[:2000]
        parts.append(f"## Jenkinsfile\n```groovy\n{content}\n```")

    # CircleCI
    circle = root / ".circleci" / "config.yml"
    if circle.exists():
        content = circle.read_text(errors="replace")[:1500]
        parts.append(f"## .circleci/config.yml\n```yaml\n{content}\n```")

    # Travis
    travis = root / ".travis.yml"
    if travis.exists():
        content = travis.read_text(errors="replace")[:1500]
        parts.append(f"## .travis.yml\n```yaml\n{content}\n```")

    if not parts:
        return "(no se encontró configuración CI/CD: .github/workflows/, .gitlab-ci.yml, Jenkinsfile, etc.)"
    return "\n\n".join(parts)


def _resource_project_lint() -> str:
    """Resultado del linting rápido del proyecto."""
    root   = Path.cwd()
    parts  = []

    def _run(cmd: list[str]) -> tuple[int, str]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, cwd=str(root))
            return r.returncode, (r.stdout + r.stderr).strip()
        except FileNotFoundError:
            return -2, ""
        except Exception as exc:
            return -3, str(exc)

    import shutil
    if shutil.which("ruff"):
        rc, out = _run(["ruff", "check", "--output-format=concise", str(root)])
        label = "✓ sin errores" if rc == 0 else f"✗ rc={rc}"
        snippet = "\n".join(out.splitlines()[:30]) if out else ""
        parts.append(f"## ruff  ({label})\n{snippet}" if snippet else f"## ruff  ({label})")

    if shutil.which("mypy"):
        py_files = list(root.rglob("*.py"))
        if py_files:
            rc, out = _run(["mypy", "--no-error-summary", "--ignore-missing-imports", str(root)])
            label = "✓ sin errores de tipos" if rc == 0 else f"✗ rc={rc}"
            snippet = "\n".join(out.splitlines()[:20]) if out else ""
            parts.append(f"## mypy  ({label})\n{snippet}" if snippet else f"## mypy  ({label})")

    if shutil.which("eslint"):
        js_files = list(root.rglob("*.js")) + list(root.rglob("*.ts"))
        if js_files:
            rc, out = _run(["eslint", "--max-warnings=0", str(root)])
            label = "✓ sin errores" if rc == 0 else f"✗ rc={rc}"
            snippet = "\n".join(out.splitlines()[:20]) if out else ""
            parts.append(f"## eslint  ({label})\n{snippet}" if snippet else f"## eslint  ({label})")

    if shutil.which("cppcheck"):
        c_files = list(root.rglob("*.c")) + list(root.rglob("*.cpp"))
        if c_files:
            rc, out = _run(["cppcheck", "--enable=warning,style", "--quiet", str(root)])
            label = "✓ sin errores" if rc == 0 else f"✗ rc={rc}"
            snippet = "\n".join(out.splitlines()[:20]) if out else ""
            parts.append(f"## cppcheck  ({label})\n{snippet}" if snippet else f"## cppcheck  ({label})")

    if not parts:
        return "(no hay linters disponibles: instala ruff, mypy, eslint o cppcheck)"
    return "\n\n---\n\n".join(parts)


def _resource_project_openapi() -> str:
    """Esquema OpenAPI / Swagger del proyecto."""
    root = Path.cwd()
    candidates = [
        "openapi.yaml", "openapi.yml", "openapi.json",
        "swagger.yaml", "swagger.yml", "swagger.json",
        "api/openapi.yaml", "api/swagger.yaml",
        "docs/openapi.yaml", "docs/swagger.yaml",
    ]
    for name in candidates:
        p = root / name
        if p.exists():
            content = p.read_text(errors="replace")
            return f"## {p.relative_to(root)}\n\n```yaml\n{content[:4000]}\n```"

    # Buscar en subdirectorios un nivel
    for p in sorted(root.glob("**/openapi.yaml"))[:3]:
        content = p.read_text(errors="replace")
        return f"## {p.relative_to(root)}\n\n```yaml\n{content[:4000]}\n```"

    return "(no se encontró openapi.yaml / swagger.yaml en el proyecto)"


def _resource_project_todos() -> str:
    """TODOs, FIXMEs y HACKs encontrados en el código fuente."""
    root    = Path.cwd()
    pattern = re.compile(r'(?i)(TODO|FIXME|HACK|XXX|NOTE|WARN)[\s:!]+(.*)')
    exts    = {".py", ".c", ".h", ".cpp", ".hpp", ".js", ".ts", ".go", ".rs",
               ".sh", ".java", ".rb", ".php", ".cs", ".md"}
    hits: list[tuple[str, int, str, str]] = []

    for fpath in sorted(root.rglob("*"))[:2000]:
        if not fpath.is_file() or fpath.suffix.lower() not in exts:
            continue
        if any(p in fpath.parts for p in (".git", "node_modules", "__pycache__", ".venv", "venv")):
            continue
        try:
            for i, line in enumerate(fpath.read_text(errors="replace").splitlines(), 1):
                m = pattern.search(line)
                if m:
                    hits.append((str(fpath.relative_to(root)), i, m.group(1).upper(), m.group(2).strip()))
                if len(hits) >= 200:
                    break
        except Exception:
            continue
        if len(hits) >= 200:
            break

    if not hits:
        return "(no se encontraron TODO/FIXME/HACK en el código fuente)"

    by_kind: dict[str, list] = {}
    for path, line, kind, text in hits:
        by_kind.setdefault(kind, []).append((path, line, text))

    lines_out = [f"## {len(hits)} comentarios pendientes\n"]
    for kind in ("FIXME", "TODO", "HACK", "XXX", "WARN", "NOTE"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        lines_out.append(f"### {kind}  ({len(items)})")
        for path, lno, text in items[:30]:
            lines_out.append(f"  {path}:{lno}  {text}")
        if len(items) > 30:
            lines_out.append(f"  … ({len(items) - 30} más)")
    return "\n".join(lines_out)


def _resource_project_processes() -> str:
    """Procesos activos relevantes: servidores, workers, compiladores."""
    try:
        r = subprocess.run(
            ["ps", "aux", "--sort=-%cpu"],
            capture_output=True, text=True, timeout=5,
        )
        lines = r.stdout.splitlines()
        # Filtrar procesos del sistema irrelevantes
        _skip = {"ps", "grep", "bash", "sh", "awk", "sed", "sort", "tail", "head"}
        _keep_kw = {
            "python", "node", "npm", "cargo", "make", "gcc", "g++", "clang",
            "docker", "postgres", "redis", "nginx", "gunicorn", "uvicorn",
            "flask", "django", "fastapi", "ollama", "llama", "celery",
            "pytest", "ruff", "mypy", "eslint", "webpack", "vite",
        }
        header = lines[0] if lines else ""
        relevant = []
        for ln in lines[1:]:
            cmd_col = ln.split(None, 10)[-1].lower() if ln else ""
            if any(kw in cmd_col for kw in _keep_kw) and \
               not any(sk in cmd_col.split()[0] for sk in _skip):
                relevant.append(ln)
        if not relevant:
            return "No se detectaron procesos de desarrollo activos."
        out = header + "\n" + "\n".join(relevant[:30])
        return "## Procesos relevantes\n\n```\n" + out + "\n```"
    except Exception as exc:
        return f"Error al obtener procesos: {exc}"


def _resource_lsp_guide() -> str:
    """Estado LSP y guía de uso por lenguaje."""
    import shutil
    _LSP_SERVERS = {
        "clangd":  {"exts": [".c", ".cpp", ".cc", ".h", ".hpp"], "lang": "C/C++",
                    "install": "apt install clangd  /  brew install llvm"},
        "pylsp":   {"exts": [".py"], "lang": "Python",
                    "install": "pip install python-lsp-server"},
        "typescript-language-server": {"exts": [".js", ".ts", ".jsx", ".tsx"], "lang": "JS/TS",
                    "install": "npm i -g typescript-language-server"},
        "bash-language-server": {"exts": [".sh", ".mk"], "lang": "Bash/Makefile",
                    "install": "npm i -g bash-language-server"},
        "perl-language-server": {"exts": [".pl", ".pm"], "lang": "Perl",
                    "install": "cpanm PLS"},
        "ruby-lsp": {"exts": [".rb"], "lang": "Ruby",
                    "install": "gem install ruby-lsp"},
        "jdtls":   {"exts": [".java"], "lang": "Java",
                    "install": "apt install jdtls  /  brew install jdtls"},
        "gopls":   {"exts": [".go"], "lang": "Go",
                    "install": "go install golang.org/x/tools/gopls@latest"},
        "rust-analyzer": {"exts": [".rs"], "lang": "Rust",
                    "install": "rustup component add rust-analyzer"},
        "sqls":    {"exts": [".sql"], "lang": "SQL",
                    "install": "go install github.com/sqls-server/sqls@latest"},
        "yaml-language-server": {"exts": [".yaml", ".yml"], "lang": "YAML",
                    "install": "npm i -g yaml-language-server"},
        "vscode-css-language-server": {"exts": [".css", ".scss", ".less"], "lang": "CSS/SCSS",
                    "install": "npm i -g vscode-langservers-extracted"},
        "vscode-html-language-server": {"exts": [".html"], "lang": "HTML",
                    "install": "npm i -g vscode-langservers-extracted"},
        "vscode-json-language-server": {"exts": [".json"], "lang": "JSON",
                    "install": "npm i -g vscode-langservers-extracted"},
        "cmake-language-server": {"exts": [".cmake"], "lang": "CMake",
                    "install": "pip install cmake-language-server"},
        "taplo":   {"exts": [".toml"], "lang": "TOML",
                    "install": "cargo install taplo-cli"},
        "intelephense": {"exts": [".php"], "lang": "PHP",
                    "install": "npm i -g intelephense"},
    }
    lines = ["# Estado LSP — Servidores de lenguaje disponibles\n"]
    installed = []
    missing   = []
    for srv, info in _LSP_SERVERS.items():
        ok = bool(shutil.which(srv))
        row = f"{'✓' if ok else '✗'}  {srv:38s} {info['lang']:12s} ({', '.join(info['exts'])})"
        if ok:
            installed.append(row)
        else:
            missing.append(f"{row}\n   → instalar: {info['install']}")
    lines.append(f"## Instalados ({len(installed)})")
    lines.extend(installed or ["  (ninguno instalado)"])
    lines.append(f"\n## No instalados ({len(missing)})")
    lines.extend(missing[:10])  # limitar lista
    lines.append("""
## Flujo de trabajo por lenguaje

### C / C++ (clangd)
```
lsp_symbols(path)                          → estructura del fichero (funciones, structs, macros)
lsp_call_hierarchy(path, line, "incoming") → quién llama a esta función
lsp_call_hierarchy(path, line, "outgoing") → qué llama esta función
lsp_hover(path, line, col)                 → tipo/firma del símbolo
lsp_diagnostics(path)                      → errores (equivale a gcc -Wall sin compilar)
lsp_workspace_symbols("nombre", path)      → buscar cualquier símbolo en el proyecto
lsp_rename(path, line, col, "nuevo", apply=true) → renombrar en todos los ficheros
```
SIEMPRE: lsp_diagnostics DESPUÉS de editar .c/.cpp/.h → luego make_run para compilar.

### Python (pylsp)
```
lsp_diagnostics(path)    → errores de tipos, imports no usados, syntax errors
lsp_references(path, line, col)  → todos los usos antes de renombrar/borrar
lsp_symbols(path)        → clases y funciones del módulo
```

### JS / TS (typescript-language-server)
```
lsp_diagnostics(path)    → errores TypeScript de tipos
lsp_completion(path, line, col) → autocompletado de APIs/métodos
lsp_rename(path, line, col, "nuevo", apply=true) → refactoring seguro
```

### Shell / Makefile (bash-language-server)
```
lsp_diagnostics(path)    → errores de sintaxis bash
lsp_symbols(path)        → funciones del script
```

### Perl (perl-language-server)
```
lsp_diagnostics(path)    → errores Perl (-c check)
lsp_definition(path, line, col) → saltar a sub
```

### SQL (sqls)
```
lsp_diagnostics(path)    → errores SQL
lsp_completion(path, line, col) → autocompletado de tablas/columnas
```

### PHP (intelephense)
```
lsp_symbols(path)                               → clases, métodos, propiedades, constantes
lsp_diagnostics(path)                           → undefined vars, type errors, syntax errors
lsp_hover(path, line, col)                      → PHPDoc, firma de función/método
lsp_completion(path, line, col)                 → autocompletado de métodos/propiedades
lsp_references(path, line, col)                 → todos los usos antes de renombrar/borrar
lsp_definition(path, line, col)                 → saltar a la definición del símbolo
lsp_rename(path, line, col, "nuevo", apply=true) → renombrar en todos los ficheros
```
Flujo PHP recomendado: lsp_symbols → lsp_diagnostics → context_before_edit → edit_file → lsp_diagnostics → lint_file

### YAML (yaml-language-server)
```
lsp_diagnostics(path)    → validación de schema
```

## Antipatrones a evitar (el agente bloqueará estos)
- `bash grep -rn "función"` → usa lsp_workspace_symbols o lsp_call_hierarchy
- `bash make` solo para ver errores → usa lsp_diagnostics primero
- `bash python3 << 'EOF'` → usa python_exec(code=...)
- `bash gcc file.c` solo para verificar → usa lsp_diagnostics
""")
    return "\n".join(lines)


def _resource_agent_reasoning() -> str:
    """Guía de razonamiento: reglas anti-bucle y flujos de trabajo para edición segura."""
    return """\
# Guía de razonamiento del agente OOCode

## Regla de oro: LEE ANTES DE EDITAR

Antes de llamar a cualquier tool de edición (`edit_file`, `regex_replace`, `bulk_replace`,
`smart_replace`), debes conocer el texto **exacto** que vas a modificar.

```
FLUJO CORRECTO:
  1. context_before_edit(file, pattern)   → ver texto exacto alrededor del área
  2. [si el texto no es claro] pre_edit_check(file, focus)  → estructura + contexto
  3. edit_file(old_string=TEXTO_COPIADO_LITERALMENTE, new_string=...)
       ─ o ─
     smart_replace(file, pattern, replacement)  → auto-verifica antes de aplicar

FLUJO INCORRECTO (causa bucles):
  ✗ regex_replace → "no coincidencias" → regex_replace (mismo patrón) → bucle
  ✗ bulk_replace → falla → bulk_replace (mismo patrón) → 9 reintentos fallidos
```

## Anti-bucle: reglas de parada obligatorias

| Situación | Acción requerida |
|-----------|-----------------|
| regex_replace/bulk_replace → "no coincidencias" (1ª vez) | Lee el fichero con `context_before_edit` |
| regex_replace/bulk_replace → "no coincidencias" (2ª vez con mismo patrón) | **PARA**. Cambia estrategia. Usa `edit_file` con texto literal |
| grep_code / symbol_lookup → 0 resultados | Prueba patrón alternativo o busca en otro directorio |
| Misma tool con mismos args 2 veces seguidas | **PARA**. Reporta el bloqueo al usuario |

## Herramientas compuestas (uso preferido)

### `smart_replace(file, pattern, replacement)`
- Verifica que el patrón existe ANTES de reemplazar
- Si no existe: muestra las primeras líneas del fichero para corregir
- Si existe: aplica y muestra diff
- **Cuándo usar**: siempre que no estés 100% seguro de que el patrón coincide

### `context_before_edit(file, pattern)`
- Muestra líneas numeradas con `→` en la línea coincidente
- Búsqueda: regex → literal → casefold (tres niveles de fallback)
- **Cuándo usar**: antes de edit_file cuando old_string puede no coincidir exactamente

### `pre_edit_check(file, focus, offset, limit)`
- Stat del fichero + rango de líneas + contexto del focus en una llamada
- **Cuándo usar**: al empezar a trabajar en un fichero que no conoces

## Flujo de implementación (checklist)

```
1. EXPLORAR   → grep_code / symbol_lookup / pre_edit_check
2. PLANIFICAR → list_recent_files / read_project_file / context_before_edit
3. EDITAR     → edit_file (literal) | smart_replace (regex)
4. VERIFICAR  → grep_code (confirma cambio) | lint_file | run_quick_check
```

## Selección de tool de edición

| Situación | Tool recomendada |
|-----------|-----------------|
| Texto exacto conocido (≤ 20 líneas) | `edit_file(old_string=..., new_string=...)` |
| Patrón regex simple, texto verificado | `regex_replace` |
| Patrón regex incierto | `smart_replace` (auto-verifica) |
| Reemplazar mismo patrón en múltiples ficheros | `bulk_replace` (solo si grep_code confirmó) |
| No sé qué hay en el fichero | `pre_edit_check` primero, luego editar |
| old_string falló → "no encontrado" | `context_before_edit` → corregir → `edit_file` |

## Reglas de razonamiento profundo

1. **Nunca asumas el contenido de un fichero** — léelo siempre que vayas a editarlo
2. **Un fallo = cambio de estrategia** — no repitas lo mismo esperando distinto resultado
3. **grep antes de regex** — si no sabes si el patrón existe, usa grep_code primero
4. **Literal es más seguro que regex** — cuando puedas copiar el texto exacto, usa edit_file
5. **Divide y verifica** — ediciones grandes → verifica cada bloque antes de continuar
"""


def _resource_interface_contracts() -> str:
    """Lista las interfaces públicas del proyecto usadas en ≥3 ficheros.
    Útil para identificar qué funciones/clases son "estables" antes de refactorizar.
    """
    import ast as _ast, subprocess as _sp, shutil as _sh
    from pathlib import Path as _P

    MIN_FILES = 3    # usadas en al menos este número de ficheros
    MAX_SYMS  = 60   # límite de símbolos para no hacer demasiadas llamadas rg

    cwd = _P.cwd()

    if not _sh.which("rg") and not _sh.which("grep"):
        return "ripgrep/grep no disponible — necesario para contar referencias."

    # ── 1. Recopilar símbolos públicos top-level de todos los .py del proyecto ──
    def _compact_sig(node) -> str:
        if isinstance(node, _ast.ClassDef):
            bases = ", ".join(_ast.unparse(b) for b in node.bases) if node.bases else ""
            return f"class {node.name}({bases})" if bases else f"class {node.name}"
        prefix = "async def" if isinstance(node, _ast.AsyncFunctionDef) else "def"
        try:
            args_s = _ast.unparse(node.args)
            ret    = f" -> {_ast.unparse(node.returns)}" if node.returns else ""
            return f"{prefix} {node.name}({args_s}){ret}"
        except Exception:
            return f"{prefix} {node.name}(...)"

    # symbol_name → (relative_path, display_sig)
    collected: dict[str, tuple[str, str]] = {}
    py_files = sorted(cwd.rglob("*.py"))[:400]

    for py_file in py_files:
        try:
            text = py_file.read_text(errors="replace")
            tree = _ast.parse(text)
        except Exception:
            continue
        try:
            rel = str(py_file.relative_to(cwd))
        except ValueError:
            rel = str(py_file)
        for node in tree.body:
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                continue
            name = node.name
            if name.startswith("_"):
                continue  # saltar privados
            if name not in collected:
                collected[name] = (rel, _compact_sig(node))

    if not collected:
        return "Sin símbolos públicos encontrados en el directorio actual."

    # ── 2. Para cada símbolo contar ficheros que lo referencian (word-boundary) ─
    # Procesar en lotes para no lanzar 200 rg individuales innecesariamente
    results: list[tuple[int, str, str, str]] = []  # (n_files, name, path, sig)

    for name, (fpath, sig) in list(collected.items())[:MAX_SYMS]:
        try:
            if _sh.which("rg"):
                proc = _sp.run(
                    ["rg", "-l", "--word-regexp", "--color=never", "--", name, str(cwd)],
                    capture_output=True, text=True, timeout=4,
                )
            else:
                proc = _sp.run(
                    ["grep", "-rl", "--word-regexp", name, str(cwd)],
                    capture_output=True, text=True, timeout=4,
                )
            files = [l for l in (proc.stdout or "").splitlines() if l.strip()]
            n_files = len(files)
        except Exception:
            continue

        if n_files >= MIN_FILES:
            results.append((n_files, name, fpath, sig))

    if not results:
        return (
            f"Sin interfaces públicas usadas en ≥{MIN_FILES} ficheros.\n"
            f"(Símbolos analizados: {len(collected)})"
        )

    results.sort(reverse=True, key=lambda x: x[0])

    lines = [
        f"# Interfaces estables del proyecto  (usadas en ≥{MIN_FILES} ficheros)",
        f"# Directorio: {cwd}",
        f"# Total encontradas: {len(results)} de {len(collected)} símbolos públicos analizados",
        "",
    ]

    for n_files, name, fpath, sig in results:
        lines.append(f"{'─'*60}")
        lines.append(f"  {sig}")
        lines.append(f"  Definida en: {fpath}   Usada en: {n_files} ficheros")

    return "\n".join(lines)


def _resource_active_hooks() -> str:
    """Estado actual de los hooks en OOCode: activos, disponibles y cómo togglearlos."""
    import json
    config_file = Path.home() / ".oocode" / "oocode.json"
    enabled_hooks: list[str] = []
    try:
        raw = json.loads(config_file.read_text()) if config_file.exists() else {}
        enabled_hooks = raw.get("hooks", {}).get("builtins", [
            "diff_after_write", "ctags_after_write", "lint_after_write",
            "quick_syntax_after_write", "verify_after_edit", "test_suite_delta",
            "config_syntax_after_write",
        ])
        hooks_enabled = raw.get("hooks", {}).get("enabled", True)
    except Exception:
        hooks_enabled = True

    ALL_HOOKS = {
        "diff_after_write":           ("post", "✓ def",  "Muestra diff visual (before/after) tras cada escritura"),
        "ctags_after_write":          ("post", "✓ def",  "Reconstruye índice ctags de símbolos"),
        "lint_after_write":           ("post", "✓ def",  "Ejecuta linter del lenguaje (ruff/eslint/clangd…)"),
        "quick_syntax_after_write":   ("post", "✓ def",  "Chequeo de sintaxis Python instantáneo (ast.parse)"),
        "config_syntax_after_write":  ("post", "✓ def",  "Valida .json/.toml/.ini/.cfg tras escritura"),
        "verify_after_edit":          ("post", "✓ def",  "Re-lee sección editada con marcadores ▶ para verificar"),
        "test_suite_delta":           ("pre+post", "✓ def", "Baseline de tests antes + delta de regresiones después"),
        "lsp_after_write":            ("post", "opt",    "Diagnósticos LSP automáticos (.py/.c/.cpp/.ts…)"),
        "autoformat_after_write":     ("post", "opt",    "Autoformato via LSP (black/prettier/gofmt…)"),
        "backup_before_write":        ("pre",  "opt",    "Crea copia .bak antes de sobreescribir"),
        "check_secrets":              ("pre",  "opt",    "Bloquea escritura si detecta credenciales reales"),
        "log_tool_calls":             ("post", "opt",    "Guarda todo tool call en ~/.oocode/logs/tool_calls.jsonl"),
        "todo_scan_after_write":      ("post", "opt",    "Muestra TODO/FIXME/HACK encontrados en código modificado"),
        "test_after_write":           ("post", "opt",    "Ejecuta pytest en el test asociado tras editar .py"),
        "size_check_after_write":     ("post", "opt",    "Avisa si el fichero supera 300 líneas o 15 KB"),
        "interface_change_detector":  ("pre+post", "opt", "Detecta cambios de firma/interfaz pública y busca callers"),
        "git_push_guard":             ("pre",  "opt",    "Pre-push: muestra rama+commits, avisa en ramas protegidas"),
        "security_audit_log":         ("post", "opt",    "Guarda log de auditoria de Security MCP en archivo"),
    }

    lines = ["# Hooks de OOCode", f"# Sistema de hooks: {'ACTIVO' if hooks_enabled else 'DESACTIVADO'}  (toggle: /hooks on|off)", ""]
    lines.append("## Activos ahora")
    for h in enabled_hooks:
        info = ALL_HOOKS.get(h, ("?", "?", ""))
        lines.append(f"  ✓ {h:40s}  [{info[0]}]  {info[2]}")

    lines.append("\n## Disponibles (desactivados)")
    for h, (typ, state, desc) in ALL_HOOKS.items():
        if h not in enabled_hooks:
            lines.append(f"  ○ {h:40s}  [{typ}]  {desc}")

    lines.append("\n## Cómo togglear")
    lines.append("  /hooks builtin <nombre>   — activa/desactiva un hook builtin")
    lines.append("  /hooks on | /hooks off    — habilita/deshabilita el sistema completo")
    lines.append("  /hooks list               — lista todos los hooks registrados")
    return "\n".join(lines)


def _resource_active_tools() -> str:
    """Lista de todas las herramientas disponibles agrupadas por categoría."""
    categories = {
        "Lectura y búsqueda": [
            "grep_code", "multi_grep", "code_outline", "read_sections", "affected_files",
            "symbol_lookup", "read_files", "read_project_file", "list_recent_files",
        ],
        "Sistema de ficheros": [
            "ls_dir", "ls_file", "find_file", "find_files", "find_dir", "file_stat",
            "tree", "count_lines",
        ],
        "Edición de código": [
            "write_file", "edit_file", "edit_files", "regex_replace", "bulk_replace",
            "smart_replace", "patch_apply", "context_before_edit", "pre_edit_check",
        ],
        "Git": [
            "git_status", "git_diff", "git_log", "git_add", "git_commit", "git_push",
            "git_pull", "git_branch", "git_stash", "git_patch", "git_clone",
            "git_worktree", "git_blame", "git_rebase", "git_tag", "git_cherry_pick",
        ],
        "Docker / Compose": [
            "docker_ps", "docker_logs", "docker_exec", "docker_inspect", "docker_images",
            "docker_stop", "docker_rm", "docker_cp",
            "compose_version", "compose_services", "compose_status", "compose_up",
            "compose_down", "compose_stop", "compose_restart", "compose_build",
            "compose_pull", "compose_logs", "compose_exec", "compose_run",
            "compose_config", "compose_images", "compose_top",
        ],
        "Tests y linting": [
            "lint_file", "lint_project", "mypy_check", "json_validate", "yaml_validate",
            "xml_validate", "xml_format", "render_markdown", "gitlint_check", "ansible_lint",
            "efm_config_update",
        ],
        "Build y ejecución": [
            "make_run", "run_script", "format_code", "python_exec", "pip_tool", "npm_tool",
            "bash", "run_tests", "test_file",
        ],
        "Debug": [
            "strace_run", "gdb_run", "pdb_run", "valgrind_run",
        ],
        "Análisis de proyecto": [
            "analyze_codebase", "code_compare", "diff_files",
            "build_symbol_index", "find_symbol", "list_symbols",
        ],
        "Operaciones de ficheros": [
            "chmod_file", "chmod_dir", "chown_file", "chown_dir",
            "mv_file", "cp_file", "rm_file", "rm_dir", "mkdir_dir", "touch_file",
            "symlink_create", "readlink", "grep_file",
            "archive_extract", "archive_create", "archive_list",
        ],
        "Datos y utilidades": [
            "json_format", "jq_query", "hash_text", "url_encode", "template_fill",
            "calculate", "http_get", "web_search", "web_fetch",
        ],
        "Sistema": [
            "system_info", "env_check", "process_list", "port_check", "get_datetime",
        ],
        "Memoria y contexto": [
            "mem_save", "plan_create", "task_done",
        ],
    }

    lines = [
        "# Herramientas disponibles en OOCode",
        "# Usa una herramienta en lugar de bash siempre que sea posible",
        "",
    ]
    for cat, tools in categories.items():
        lines.append(f"## {cat}")
        lines.append("  " + "  ·  ".join(tools))
        lines.append("")

    lines.append("## Prompts disponibles (invoca via MCP prompts)")
    lines.append("  code_review, debug_session, commit_message, test_cases, sql_query,")
    lines.append("  explain_code, refactor_code, api_design, documentation, security_audit,")
    lines.append("  architecture_review, pr_description, error_analysis, explore_codebase,")
    lines.append("  troubleshoot_error, write_commit_message, generate_report, summarize_session,")
    lines.append("  ansible_review, … (42 prompts en total)")
    return "\n".join(lines)


_RESOURCE_FNS = {
    "project://context":   _resource_project_context,
    "project://structure": _resource_project_structure,
    "project://git":       _resource_git_status,
    "project://deps":      _resource_project_deps,
    "project://tests":     _resource_project_tests,
    "project://env":       _resource_project_env,
    "project://errors":    _resource_project_errors,
    "project://metrics":   _resource_project_metrics,
    "project://changelog": _resource_project_changelog,
    "project://docker":    _resource_project_docker,
    "project://coverage":  _resource_project_coverage,
    "project://makefile":  _resource_project_makefile,
    "project://ci":        _resource_project_ci,
    "project://lint":      _resource_project_lint,
    "project://openapi":   _resource_project_openapi,
    "project://todos":     _resource_project_todos,
    "project://processes": _resource_project_processes,
    "project://templates": _resource_project_templates,
    "project://reasoning":           _resource_agent_reasoning,
    "project://lsp":                 _resource_lsp_guide,
    "project://interface_contracts": _resource_interface_contracts,
    "report://template_md":          _resource_report_template_md,
    "report://template_xml":         _resource_report_template_xml,
    "project://hooks":               _resource_active_hooks,
    "project://active_tools":        _resource_active_tools,
}


# ── Bucle principal ───────────────────────────────────────────────────────────

class MCPOptionalError(Exception):
    """Error opcional para MCP — no rompe el flujo."""
    pass


def _handle(req: dict) -> None:
    method  = req.get("method", "")
    req_id  = req.get("id")
    params  = req.get("params", {})

    # Añadir versión a los argumentos (API versioning)
    arguments = params.get("arguments", {})
    if arguments:
        arguments["_version"] = "1.0.0"
        arguments["_api_version"] = "2024-11-05"

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "oocode-assistant", "version": "5.0.0"},
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
            # Manejo unificado de errores MCP
            result = fn(arguments)
            _ok(req_id, {"content": [{"type": "text", "text": result}], "isError": False})
        except MCPOptionalError as e:
            _ok(req_id, {"content": [{"type": "text", "text": str(e)}], "isError": True})
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
    sys.stderr.write("[oocode-assistant] MCP server v4.0 iniciado\n")
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
            sys.stderr.write(f"[oocode-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
