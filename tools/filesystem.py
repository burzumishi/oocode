from pathlib import Path
from typing import Optional


# ── Matcher flexible para ediciones literales ────────────────────────────────
# edit_file/edit_files reciben `old_string` literal del modelo, que a menudo difiere
# del fichero solo en whitespace (espacios finales, tabs vs espacios, CRLF, o toda la
# indentación desplazada). El match EXACTO falla por esas diferencias triviales. Este
# matcher escala la tolerancia y SIEMPRE exige coincidencia ÚNICA (si es ambigua, no
# adivina). Devuelve el span real del fichero para reemplazarlo conservando su formato.

def _leading_ws(s: str) -> str:
    return s[: len(s) - len(s.lstrip())]


def _line_offsets(content_lines: list[str]) -> list[int]:
    """Offset de inicio de cada línea en el texto unido por '\\n'."""
    offsets, pos = [], 0
    for ln in content_lines:
        offsets.append(pos)
        pos += len(ln) + 1   # +1 por el '\n' separador
    return offsets


def find_unique_span(content: str, old: str):
    """Localiza el span [start, end) de `content` que corresponde a `old`.

    Escala la tolerancia y solo acepta coincidencia ÚNICA:
      1. Exacto.
      2. Por línea, ignorando whitespace final (rstrip) → cubre espacios finales/CRLF.
      3. Por línea, ignorando indentación (strip) → cubre indentación desplazada.
      4. Por línea, colapsando TODO run de whitespace a un espacio (norm) → cubre
         tabs interiores vs espacios (p.ej. C estilo GNU con tabs de alineación que
         el modelo no puede ver en el output numerado de read_file).

    Devuelve (start, end, level) donde level ∈ {'exact','rstrip','strip','norm'}, o
    (None, None, reason) con reason ∈ {'ambiguo','no-encontrado','vacio'}.
    """
    if old == "":
        return None, None, "vacio"
    # ── Nivel 1: exacto ──
    n = content.count(old)
    if n == 1:
        i = content.find(old)
        return i, i + len(old), "exact"
    if n > 1:
        return None, None, "ambiguo"

    # ── Niveles por línea ──
    content_lines = content.split("\n")
    old_lines = old.split("\n")
    if old_lines and old_lines[-1] == "":
        old_lines = old_lines[:-1]   # `old` terminaba en '\n': trabajar por líneas
    L = len(old_lines)
    if L == 0:
        return None, None, "vacio"
    if L > len(content_lines):
        return None, None, "no-encontrado"

    offsets = _line_offsets(content_lines)

    def span_at(i: int):
        start = offsets[i]
        last = i + L - 1
        end = offsets[last] + len(content_lines[last])
        return start, end

    def _norm_ws(s: str) -> str:
        return " ".join(s.split())

    for level, key in (("rstrip", str.rstrip), ("strip", str.strip), ("norm", _norm_ws)):
        hits = [
            i for i in range(len(content_lines) - L + 1)
            if all(key(content_lines[i + k]) == key(old_lines[k]) for k in range(L))
        ]
        if len(hits) == 1:
            s, e = span_at(hits[0])
            return s, e, level
        if len(hits) > 1:
            return None, None, "ambiguo"

    return None, None, "no-encontrado"


def _reindent(new: str, old: str, matched: str) -> str:
    """Ajusta la indentación de `new` cuando el match fue por `strip` (la indentación
    del fichero difiere de la de `old`). Desplaza cada línea de `new` por la diferencia
    de indentación de la primera línea (old → matched). Conservador: si `new` no usa la
    indentación de `old` como prefijo, deja la línea tal cual."""
    old0 = old.split("\n")[0]
    mat0 = matched.split("\n")[0]
    old_ind, mat_ind = _leading_ws(old0), _leading_ws(mat0)
    if old_ind == mat_ind:
        return new
    out = []
    for ln in new.split("\n"):
        if ln.startswith(old_ind):
            out.append(mat_ind + ln[len(old_ind):])
        elif ln.strip() == "":
            out.append(ln)
        else:
            out.append(mat_ind + ln.lstrip()) if mat_ind and not _leading_ws(ln) else out.append(ln)
    return "\n".join(out)


# Directivas de preprocesador C que NO son comentarios (no colapsar como banner).
_C_PREPROC_PREFIXES = (
    "#include", "#define", "#undef", "#if", "#ifdef", "#ifndef",
    "#else", "#elif", "#endif", "#pragma", "#error", "#import", "#line",
)
# Familias por sintaxis de comentario (clave = extensión sin punto, en minúsculas).
_C_FAMILY = {"c", "h", "cpp", "cxx", "cc", "hpp", "hh", "hxx", "java", "js", "jsx",
             "ts", "tsx", "mjs", "cjs", "go", "rs", "swift", "kt", "kts", "scala",
             "cs", "dart", "zig", "d", "groovy", "css", "scss", "less", "proto",
             "glsl", "hlsl", "vala", "json5"}
_HASH_FAMILY = {"py", "pyi", "sh", "bash", "zsh", "fish", "rb", "pl", "pm", "raku",
                "yaml", "yml", "toml", "ini", "cfg", "conf", "r", "jl", "tcl", "nim",
                "ex", "exs", "cr", "coffee", "ps1", "dockerfile", "makefile", "mk",
                "gitignore", "env", "properties", "awk", "sed", "gd"}
_DASH_FAMILY = {"sql", "lua", "hs", "lhs", "adb", "ads", "elm", "purs", "sql"}
_SEMI_FAMILY = {"lisp", "el", "clj", "cljs", "cljc", "scm", "rkt", "asm", "s", "nasm",
                "ahk", "ini2"}
_BANG_FAMILY = {"f", "f90", "f95", "f03", "f08", "for", "fortran"}
_PCT_FAMILY  = {"tex", "latex", "sty", "cls", "erl", "hrl", "matlab", "mat"}
_XML_FAMILY  = {"html", "htm", "xml", "svg", "xhtml", "vue", "xsl", "xslt", "md", "markdown", "rst"}


def _comment_syntax(ext: str):
    """Devuelve (line_prefixes, block_pairs, is_c_family) según la extensión del fichero.
    Cubre las familias de lenguajes más comunes; para extensiones desconocidas usa un
    conjunto amplio y conservador."""
    ext = (ext or "").lstrip(".").lower()
    if ext in _C_FAMILY:
        return (("//",), [("/*", "*/")], True)
    if ext == "php":
        return (("//", "#"), [("/*", "*/")], False)
    if ext in _HASH_FAMILY:
        # Python: además docstrings de módulo (""" / ''') como "banner".
        blocks = [('"""', '"""'), ("'''", "'''")] if ext in ("py", "pyi") else []
        return (("#",), blocks, False)
    if ext in _DASH_FAMILY:
        blocks = [("--[[", "]]")] if ext == "lua" else [("/*", "*/")]
        return (("--",), blocks, False)
    if ext in _SEMI_FAMILY:
        return ((";",), [], False)
    if ext in _BANG_FAMILY:
        return (("!",), [], False)
    if ext in _PCT_FAMILY:
        return (("%",), [], False)
    if ext in _XML_FAMILY:
        return ((), [("<!--", "-->")], False)
    if ext == "vim":
        return (('"',), [], False)
    if ext in ("ml", "mli", "fs", "fsi"):
        return ((), [("(*", "*)")], False)
    if ext in ("pas", "pp", "dpr"):
        return ((), [("{", "}"), ("(*", "*)")], False)
    # Desconocido: conjunto amplio (line) + bloques comunes. Conservador.
    return (("//", "#", "--", ";", "%"), [("/*", "*/"), ("<!--", "-->")], False)


def _leading_comment_banner_len(lines: list[str], path: str = "") -> int:
    """Nº de líneas iniciales que forman una cabecera de comentario/licencia (logos,
    listas de autores…), AGNÓSTICO al lenguaje (según la extensión del fichero). Reconoce
    bloques `/* */`, `<!-- -->`, `(* *)`, docstrings Python… y comentarios de línea por
    familia. En C-family, las directivas de preprocesador (`#include`/`#define`…) NO se
    tratan como comentario. Para en la primera línea de código real."""
    import os as _os
    ext = _os.path.splitext(path)[1] if path else ""
    line_prefixes, block_pairs, is_c = _comment_syntax(ext)
    in_block_close = None   # cierre esperado si estamos dentro de un bloque
    n = 0
    for ln in lines:
        s = ln.strip()
        if in_block_close is not None:
            n += 1
            if in_block_close in s:
                in_block_close = None
            continue
        if s == "":
            n += 1
            continue
        # ¿Abre un bloque de comentario?
        _opened = False
        for _open, _close in block_pairs:
            if s.startswith(_open):
                n += 1
                # cierra en la misma línea? (cuidado con """x""" de una línea)
                rest = s[len(_open):]
                if _close not in rest:
                    in_block_close = _close
                _opened = True
                break
        if _opened:
            continue
        # ¿Directiva de preprocesador C? → NO es comentario, es código.
        if is_c and s.startswith("#"):
            break
        # ¿Comentario de línea de esta familia?
        if line_prefixes and s.startswith(line_prefixes):
            n += 1
            continue
        # Líneas de continuación de banner tipo ` * ...` (dentro de algunos estilos).
        if s.startswith("*") and n > 0:
            n += 1
            continue
        break   # primera línea de código real
    return n


def _apply_flexible_edit(content: str, old: str, new: str):
    """Aplica una edición literal tolerante a whitespace. Devuelve (new_content, note)
    o (None, error_reason)."""
    start, end, level = find_unique_span(content, old)
    if start is None:
        return None, level
    matched = content[start:end]
    repl = new
    if level in ("strip", "norm"):
        repl = _reindent(new, old, matched)
    return content[:start] + repl + content[end:], level


def read_file(
    path: str,
    offset: int = 0,
    limit: int = 150,
    _warn_large: int = 500,
    skip_comment_banner: bool = False,
) -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"
    if not p.is_file():
        return f"Error: '{path}' no es un fichero."
    try:
        lines = p.read_text(errors="replace").splitlines()
        total = len(lines)
        # Saltar una cabecera de comentario/licencia larga (opt-in): se colapsa en un
        # marcador pero los NÚMEROS DE LÍNEA se conservan (offset avanza), así las
        # ediciones posteriores no se desalinean. Solo desde el inicio del fichero.
        banner_note = ""
        if skip_comment_banner and offset == 0:
            _bn = _leading_comment_banner_len(lines, path)
            if _bn >= 8:   # solo si es realmente larga
                banner_note = (f"[1-{_bn}: cabecera de comentario/licencia "
                               f"({_bn} líneas) omitida — read_file(offset=0) para verla]\n")
                offset = _bn
        chunk = lines[offset : offset + limit]
        numbered = [f"{offset + i + 1}\t{line}" for i, line in enumerate(chunk)]
        result = "\n".join(numbered)
        remaining = total - (offset + limit)
        if remaining > 0:
            result += f"\n... ({remaining} líneas más — usa offset={offset + limit} para continuar)"
        if total > _warn_large and offset == 0:
            result = f"[fichero grande: {total} líneas — mostrando {offset+1}-{offset+len(chunk)}]\n" + result
        return banner_note + result
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
    if old_string == "":
        return f"Error: 'old_string' vacío en '{path}'."
    try:
        content = p.read_text()
        new_content, level = _apply_flexible_edit(content, old_string, new_string)
        if new_content is None:
            if level == "ambiguo":
                return (f"Error: la cadena aparece varias veces en '{path}' (o coincide de forma "
                        "ambigua ignorando espacios). Proporciona más contexto para hacerla única.")
            return f"Error: cadena no encontrada en '{path}'."
        p.write_text(new_content)
        # Nota cuando hubo que tolerar whitespace: transparencia (el diff mostrado es la verdad).
        if level == "rstrip":
            return f"Edición aplicada en '{path}' (match tolerante a espacios finales)."
        if level == "strip":
            return f"Edición aplicada en '{path}' (match tolerante a indentación — revisa el diff)."
        if level == "norm":
            return (f"Edición aplicada en '{path}' (match tolerante a whitespace interior "
                    "— tabs/espacios normalizados; revisa el diff).")
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

            if replace_all:
                count = content.count(old_string)
                if count == 0:
                    errors.append(f"Edición {i+1} ({path_str}): cadena no encontrada.")
                    continue
            else:
                # Match flexible (tolerante a whitespace) y ÚNICO.
                _s, _e, _lvl = find_unique_span(content, old_string)
                if _s is None:
                    if _lvl == "ambiguo":
                        errors.append(
                            f"Edición {i+1} ({path_str}): la cadena coincide de forma ambigua "
                            "(varias veces, también ignorando espacios). Da más contexto o usa replace_all."
                        )
                    else:
                        errors.append(f"Edición {i+1} ({path_str}): cadena no encontrada.")
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
                if repl_all:
                    new_content = _orig.replace(_old, _new)
                else:
                    new_content, _ = _apply_flexible_edit(_orig, _old, _new)
                    new_content = new_content if new_content is not None else _orig
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
                if repl_all:
                    new_content = _orig.replace(_old, _new)
                else:
                    new_content, _ = _apply_flexible_edit(_orig, _old, _new)
                    new_content = new_content if new_content is not None else _orig
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

    def _read_file(path: str, offset: int = 0, limit: int = read_lines_default,
                   skip_comment_banner: bool = False) -> str:
        return read_file(path, offset, limit, _warn_large=read_lines_warn_large,
                         skip_comment_banner=skip_comment_banner)

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
                        "skip_comment_banner": {"type": "boolean", "description": "Si true, colapsa una cabecera de comentario/licencia larga al inicio (logos, listas de autores) conservando los números de línea — útil para no gastar contexto en banners."},
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
                "description": ("Reemplaza una cadena ÚNICA en un fichero. El match tolera diferencias "
                                "de whitespace (espacios finales, tabs vs espacios, CRLF, indentación) "
                                "siempre que la coincidencia sea única. Falla si aparece 0 veces o es ambigua."),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":       {"type": "string", "description": "Ruta del fichero a editar."},
                        "old_string": {"type": "string", "description": "Cadena a reemplazar (única). Copia el texto del fichero; pequeñas diferencias de espacios/indentación se toleran."},
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
