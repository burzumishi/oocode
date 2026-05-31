from pathlib import Path
from typing import Optional


def read_file(
    path: str,
    offset: int = 0,
    limit: int = 150,
    _warn_large: int = 500,
) -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"
    if not p.is_file():
        return f"Error: '{path}' no es un fichero."
    try:
        lines = p.read_text(errors="replace").splitlines()
        total = len(lines)
        chunk = lines[offset : offset + limit]
        numbered = [f"{offset + i + 1}\t{line}" for i, line in enumerate(chunk)]
        result = "\n".join(numbered)
        remaining = total - (offset + limit)
        if remaining > 0:
            result += f"\n... ({remaining} líneas más — usa offset={offset + limit} para continuar)"
        if total > _warn_large and offset == 0:
            result = f"[fichero grande: {total} líneas — mostrando {offset+1}-{offset+len(chunk)}]\n" + result
        return result
    except Exception as e:
        return f"Error leyendo '{path}': {e}"


def list_dir(path: str, max_entries: int = 60) -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: directorio no encontrado: {path}"
    if not p.is_dir():
        return f"Error: '{path}' no es un directorio."
    try:
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines = []
        for entry in entries[:max_entries]:
            if entry.is_dir():
                lines.append(f"  📁  {entry.name}/")
            else:
                size = entry.stat().st_size
                size_str = f"{size // 1024}K" if size >= 1024 else f"{size}B"
                lines.append(f"  📄  {entry.name:<40} {size_str:>8}")
        if len(entries) > max_entries:
            lines.append(f"  ... ({len(entries) - max_entries} entradas más)")
        return f"{path}/\n" + "\n".join(lines)
    except Exception as e:
        return f"Error listando '{path}': {e}"


def write_file(path: str, content: str) -> str:
    import difflib
    p = Path(path)
    old_content = ""
    if p.exists():
        try:
            old_content = p.read_text(errors="replace")
        except Exception:
            pass
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        msg = f"Fichero escrito: {path} ({len(content)} caracteres)"
        # Embed unified diff so the diff_after_write hook can render it visually
        old_lines = old_content.splitlines(keepends=True)
        new_lines = content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{p.name}", tofile=f"b/{p.name}",
            lineterm="", n=2,
        ))
        if diff_lines:
            diff_text = "\n".join(ln.rstrip("\n") for ln in diff_lines)
            return f"{msg}\n\n```diff\n{diff_text}\n```"
        return msg
    except Exception as e:
        return f"Error escribiendo '{path}': {e}"


def edit_file(path: str, old_string: str, new_string: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"
    try:
        content = p.read_text()
        count = content.count(old_string)
        if count == 0:
            return f"Error: cadena no encontrada en '{path}'."
        if count > 1:
            return f"Error: la cadena aparece {count} veces en '{path}'. Proporciona más contexto para hacerla única."
        p.write_text(content.replace(old_string, new_string, 1))
        return f"Edición aplicada en '{path}'."
    except Exception as e:
        return f"Error editando '{path}': {e}"


def _unified_diff_snippet(original: str, new_content: str, path: str,
                           context: int = 3, max_lines: int = 40) -> str:
    """Genera un diff unificado compacto entre dos strings."""
    import difflib
    orig_lines = original.splitlines(keepends=True)
    new_lines  = new_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines, new_lines,
        fromfile=f"a/{path}", tofile=f"b/{path}",
        n=context,
    ))
    if not diff:
        return ""
    if len(diff) > max_lines:
        diff = diff[:max_lines]
        diff.append(f"... ({len(diff)} líneas más)\n")
    return "".join(diff)


def edit_files(edits: list, dry_run: bool = False) -> str:
    """Edición atómica multi-fichero: aplica todos o ninguno.

    Cada edición es un dict con keys: path, old_string, new_string.
    Opcionalmente, 'operation': 'edit' (default) | 'create' | 'delete'.
    Si alguna edición falla en la validación, no se escribe ningún fichero.
    Si falla al escribir un fichero, se hace rollback de los ya escritos.

    Con dry_run=True valida y muestra el diff pero no escribe nada.
    """
    if not edits:
        return "Error: la lista de ediciones está vacía."

    # ── Fase 1: validación (sin escribir nada) ─────────────────────────────
    # Tupla: (path, orig_content_or_None, old_string, new_string, replace_all, op)
    originals: list[tuple[Path, Optional[str], Optional[str], Optional[str], bool, str]] = []
    errors: list[str] = []

    for i, edit in enumerate(edits):
        if not isinstance(edit, dict):
            errors.append(f"Edición {i+1}: debe ser un objeto con path y campos requeridos.")
            continue
        path_str    = edit.get("path", "")
        old_string  = edit.get("old_string", "")
        new_string  = edit.get("new_string", "")
        replace_all = bool(edit.get("replace_all", False))
        op          = edit.get("operation", "edit").lower()

        if not path_str:
            errors.append(f"Edición {i+1}: falta 'path'.")
            continue

        p = Path(path_str)

        if op == "create":
            if p.exists():
                errors.append(f"Edición {i+1} ({path_str}): el fichero ya existe (operation='create').")
                continue
            originals.append((p, None, None, new_string, False, "create"))

        elif op == "delete":
            if not p.exists():
                errors.append(f"Edición {i+1}: fichero no encontrado: {path_str}")
                continue
            try:
                content = p.read_text()
            except Exception as exc:
                errors.append(f"Edición {i+1} ({path_str}): error leyendo: {exc}")
                continue
            originals.append((p, content, None, None, False, "delete"))

        else:  # "edit" (default)
            if not old_string:
                errors.append(f"Edición {i+1} ({path_str}): falta 'old_string'.")
                continue
            if not p.exists():
                errors.append(f"Edición {i+1}: fichero no encontrado: {path_str}")
                continue
            try:
                content = p.read_text()
            except Exception as exc:
                errors.append(f"Edición {i+1} ({path_str}): error leyendo: {exc}")
                continue

            count = content.count(old_string)
            if count == 0:
                errors.append(f"Edición {i+1} ({path_str}): cadena no encontrada.")
                continue
            if count > 1 and not replace_all:
                errors.append(
                    f"Edición {i+1} ({path_str}): la cadena aparece {count} veces "
                    "(usa replace_all=true para reemplazar todas las ocurrencias)."
                )
                continue
            originals.append((p, content, old_string, new_string, replace_all, "edit"))

    if errors:
        return "Validación fallida — no se escribió ningún fichero:\n" + "\n".join(errors)

    # ── Dry-run: mostrar diff sin escribir ────────────────────────────────
    if dry_run:
        parts = [f"[DRY-RUN] Se aplicarían {len(originals)} edición(es):\n"]
        for p, original, old_s, new_s, repl_all, op in originals:
            if op == "create":
                parts.append(f"--- {p} [CREATE] ---\n{new_s or ''}\n")
            elif op == "delete":
                parts.append(f"--- {p} [DELETE] ---\n(se eliminará el fichero)\n")
            else:
                _orig = original or ""
                _old = old_s or ""
                _new = new_s or ""
                new_content = _orig.replace(_old, _new) if repl_all else _orig.replace(_old, _new, 1)
                diff = _unified_diff_snippet(_orig, new_content, str(p))
                note = f" [replace_all={_orig.count(_old)}]" if repl_all else ""
                parts.append(f"--- {p}{note} ---\n{diff or '(sin cambios)'}\n")
        return "\n".join(parts)

    # ── Fase 2: escritura con rollback ─────────────────────────────────────
    written: list[tuple[Path, Optional[str], str]] = []   # (path, orig_or_None, op)
    write_errors: list[str] = []
    diffs: list[str] = []

    for p, original, old_s, new_s, repl_all, op in originals:
        try:
            if op == "create":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(new_s or "")
                diffs.append(f"+++ {p} (creado)")
            elif op == "delete":
                p.unlink()
                diffs.append(f"--- {p} (eliminado)")
            else:
                _orig = original or ""
                _old = old_s or ""
                _new = new_s or ""
                new_content = _orig.replace(_old, _new) if repl_all else _orig.replace(_old, _new, 1)
                diffs.append(_unified_diff_snippet(_orig, new_content, str(p)))
                p.write_text(new_content)
            written.append((p, original, op))
        except Exception as exc:
            write_errors.append(f"{p}: {exc}")
            break

    if write_errors:
        # Rollback de los ficheros ya escritos
        for p, original, op in written:
            try:
                if op == "create":
                    p.unlink(missing_ok=True)
                elif op == "delete":
                    if original is not None:
                        p.write_text(original)
                else:
                    if original is not None:
                        p.write_text(original)
            except Exception:
                pass
        return (
            "Error al escribir (rollback aplicado):\n"
            + "\n".join(write_errors)
        )

    lines = [f"  ✓ {p} [{op}]" for p, _, _, _, _, op in originals]
    result = f"Edición atómica aplicada ({len(originals)} operaciones):\n" + "\n".join(lines)
    diff_text = "\n".join(d for d in diffs if d)
    if diff_text:
        result += f"\n\n{diff_text}"
    return result


def build_filesystem_schemas(
    read_lines_default: int = 150,
    read_lines_warn_large: int = 500,
) -> list[tuple]:
    """
    Devuelve los schemas de filesystem con los defaults inyectados desde config.
    Crea closures que capturan los valores de configuración.
    """

    def _read_file(path: str, offset: int = 0, limit: int = read_lines_default) -> str:
        return read_file(path, offset, limit, _warn_large=read_lines_warn_large)

    return [
        (
            "read_file",
            _read_file,
            {
                "name": "read_file",
                "description": (
                    f"Lee un fichero con números de línea. "
                    f"Por defecto lee {read_lines_default} líneas. "
                    f"Para ficheros grandes usa offset para leer en trozos "
                    f"(ej: offset={read_lines_default} para las siguientes {read_lines_default} líneas)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":   {"type": "string",  "description": "Ruta absoluta o relativa al fichero."},
                        "offset": {"type": "integer", "description": f"Primera línea a leer (0-indexada, por defecto 0)."},
                        "limit":  {"type": "integer", "description": f"Líneas a leer (por defecto {read_lines_default})."},
                    },
                    "required": ["path"],
                },
            },
        ),
        (
            "list_dir",
            list_dir,
            {
                "name": "list_dir",
                "description": "Lista el contenido de un directorio con nombres y tamaños.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":        {"type": "string",  "description": "Ruta del directorio a listar."},
                        "max_entries": {"type": "integer", "description": "Máximo de entradas a mostrar (default: 60)."},
                    },
                    "required": ["path"],
                },
            },
        ),
        (
            "write_file",
            write_file,
            {
                "name": "write_file",
                "description": "Escribe o sobreescribe un fichero completo con el contenido indicado.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":    {"type": "string", "description": "Ruta del fichero a escribir."},
                        "content": {"type": "string", "description": "Contenido completo del fichero."},
                    },
                    "required": ["path", "content"],
                },
            },
        ),
        (
            "edit_file",
            edit_file,
            {
                "name": "edit_file",
                "description": "Reemplaza una cadena exacta y única en un fichero. Falla si aparece 0 o más de 1 vez.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":       {"type": "string", "description": "Ruta del fichero a editar."},
                        "old_string": {"type": "string", "description": "Cadena exacta a reemplazar (debe ser única)."},
                        "new_string": {"type": "string", "description": "Cadena sustituta."},
                    },
                    "required": ["path", "old_string", "new_string"],
                },
            },
        ),
        (
            "edit_files",
            edit_files,
            {
                "name": "edit_files",
                "description": (
                    "Edición atómica de múltiples ficheros: valida todas las ediciones primero "
                    "y solo escribe si todas son válidas. Si alguna escritura falla hace rollback "
                    "completo. Úsalo cuando necesitas editar varios ficheros de forma coherente "
                    "(refactoring, renombrado de símbolo en múltiples ficheros, etc.)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "edits": {
                            "type": "array",
                            "description": "Lista de ediciones a aplicar atómicamente.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path":        {"type": "string",  "description": "Ruta del fichero"},
                                    "operation":   {"type": "string",  "description": "'edit' (default) | 'create' (crear nuevo fichero, new_string=contenido) | 'delete' (eliminar fichero)", "default": "edit"},
                                    "old_string":  {"type": "string",  "description": "Cadena exacta a reemplazar (requerida para 'edit')"},
                                    "new_string":  {"type": "string",  "description": "Cadena sustituta (o contenido del fichero para 'create')"},
                                    "replace_all": {"type": "boolean", "description": "Si True, reemplaza TODAS las ocurrencias (default False)", "default": False},
                                },
                                "required": ["path"],
                            },
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Si True, valida y muestra el diff pero no escribe nada.",
                            "default": False,
                        },
                    },
                    "required": ["edits"],
                },
            },
        ),
    ]


# Compatibilidad: schemas con defaults hardcodeados para uso sin config
FILESYSTEM_SCHEMAS = build_filesystem_schemas()
