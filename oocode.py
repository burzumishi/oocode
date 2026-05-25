#!/usr/bin/env python3
"""OOCode — Ollama Open Code. CLI de asistencia de programación 100% local."""

import os
import sys
import argparse
from pathlib import Path
from rich.prompt import IntPrompt
import ollama

from config import OOConfig, CONFIG_DIR, MEMORY_DIR
from agent.branches import BranchManager
from agent.embeddings import EmbeddingClient
import agent.logger as log
from agent.loop import AgentLoop
from agent.memory import MemorySystem
from agent.runtime import RuntimeSettings
from agent.scheduler import Scheduler
from agent.session import SessionManager
from agent.subagent import SubAgentRunner
from agent.tasks import TaskManager
from plugins.manager import PluginManager
from skills.manager import SkillManager
from tools.registry import ToolRegistry
from tools.permissions import PermissionManager
from tools.filesystem import build_filesystem_schemas
from tools.bash import build_bash_schema
from tools.search import build_search_schemas
from tools.code_search import build_code_search_schema
from workspace.manager import WorkspaceManager
from ui.console import console
from ui.renderer import print_banner, print_model_selector
from ui.repl import run_repl


def select_model_interactive(config: OOConfig) -> None:
    client = ollama.Client(host=config.ollama_host)
    try:
        data = client.list()
        models = data.get("models", []) if isinstance(data, dict) else list(data.models)
        if not models:
            console.print(f"  [red]No hay modelos en {config.ollama_host}[/red]")
            sys.exit(1)
        model_list = [
            {
                "name": m.model if hasattr(m, "model") else m["name"],
                "size": m.size if hasattr(m, "size") else m.get("size", 0),
                "details": m.details.model_dump() if hasattr(m, "details") and m.details else {},
            }
            for m in models
        ]
        print_model_selector(model_list)
        idx = IntPrompt.ask(f"\n  Elige un modelo (1-{len(model_list)})", default=1)
        idx = max(1, min(idx, len(model_list)))
        config.model = model_list[idx - 1]["name"]
        config.save()
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"  [red]Error conectando con Ollama:[/red] {e}")
        sys.exit(1)
    #finally:
    #    return True
    #    client.close()


def _sync_plugins() -> None:
    """Copia plugins de la instalación a ~/.oocode/plugins/ si no existen o son más antiguos."""
    import shutil
    install_dir = Path(__file__).parent / "plugins"
    user_dir    = CONFIG_DIR / "plugins"
    user_dir.mkdir(parents=True, exist_ok=True)
    for src in install_dir.glob("*.py"):
        if src.name.startswith("_") or src.stem == "manager":
            continue
        dst = user_dir / src.name
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(src, dst)


def _load_oocode_md_hooks(hooks_manager, config) -> None:
    """Carga hooks definidos en la sección '## Hooks' del OOCODE.md. Delega a tools.hooks."""
    from tools.hooks import load_oocode_md_hooks as _lmh
    count = _lmh(hooks_manager, config)
    if count:
        import agent.logger as _log
        _log.info("oocode_md_hooks_loaded", count=count)


def _sync_skills() -> None:
    """Copia skills de ejemplo de la instalación a ~/.oocode/skills/ si no existen."""
    install_dir = Path(__file__).parent / "skills"
    user_dir    = CONFIG_DIR / "skills"
    user_dir.mkdir(parents=True, exist_ok=True)
    for src in install_dir.glob("*.py"):
        if src.name.startswith("_") or src.stem == "manager":
            continue
        dst = user_dir / src.name
        if not dst.exists():
            import shutil
            shutil.copy2(src, dst)


def build_registry(workdir: str, config=None) -> ToolRegistry:
    registry = ToolRegistry()
    if config is not None:
        fs_schemas = build_filesystem_schemas(
            read_lines_default=config.read_file_lines_default,
            read_lines_warn_large=config.read_file_lines_warn_large,
        )
        search_schemas = build_search_schemas(
            web_fetch_max_chars=config.web_fetch_max_chars,
            web_fetch_timeout=config.web_fetch_timeout,
            web_search_max_results=config.web_search_max_results,
        )
        bash_name, bash_fn, bash_schema = build_bash_schema(
            max_output_chars=config.bash_max_output_chars,
        )
    else:
        fs_schemas = build_filesystem_schemas()
        search_schemas = build_search_schemas()
        bash_name, bash_fn, bash_schema = build_bash_schema()

    for name, fn, schema in fs_schemas:
        registry.register(name, fn, schema)

    # Envuelve bash para fijar el workdir del proyecto
    _bash_fn = bash_fn
    def bash_with_workdir(command: str, timeout: int = 120, workdir: str = workdir):
        return _bash_fn(command, timeout=timeout, workdir=workdir)
    registry.register("bash", bash_with_workdir, bash_schema)

    for name, fn, schema in search_schemas:
        registry.register(name, fn, schema)

    # code_search — usa rg si está disponible, grep como fallback
    if config is not None:
        cs_schemas = build_code_search_schema(
            max_results=config.code_search_max_results,
            context_lines=config.code_search_context_lines,
            max_filesize=config.code_search_max_filesize,
        )
    else:
        cs_schemas = build_code_search_schema()
    for name, fn, schema in cs_schemas:
        registry.register(name, fn, schema)

    # Tools de búsqueda y ejecución disponibles también en subagentes
    # (import diferido para no romper si el MCP server tiene deps opcionales)
    try:
        from mcp_servers.oocode_assistant import (
            _tool_grep_code       as _mcp_grep_code,
            _tool_multi_grep      as _mcp_multi_grep,
            _tool_affected_files  as _mcp_affected_files,
            _tool_code_outline    as _mcp_code_outline,
            _tool_read_sections   as _mcp_read_sections,
            _tool_python_exec     as _mcp_python_exec,
            _tool_ls_dir          as _mcp_ls_dir,
        )

        def grep_code(
            pattern: str, directory: str = ".",
            extensions: str = "py,js,ts,c,h,hpp,cpp,rs,go,java,rb,sh,md,json,yaml,toml",
            context_lines: int = 2, max_matches: int = 50, ignore_case: bool = True,
            exclude_pattern: str = "", count_only: bool = False,
            files_with_matches: bool = False, files_without_matches: bool = False,
        ) -> str:
            return _mcp_grep_code({
                "pattern": pattern, "directory": directory, "extensions": extensions,
                "context_lines": context_lines, "max_matches": max_matches,
                "ignore_case": ignore_case, "exclude_pattern": exclude_pattern,
                "count_only": count_only, "files_with_matches": files_with_matches,
                "files_without_matches": files_without_matches,
            })

        registry.register("grep_code", grep_code, {
            "name": "grep_code",
            "description": (
                "USA ESTO en lugar de 'bash grep'. Busca un patrón regex en el código fuente con líneas de contexto. "
                "Usa ripgrep (rg) si está disponible. Pasa `directory` con ruta absoluta para buscar en un proyecto concreto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern":              {"type": "string",  "description": "Expresión regular a buscar"},
                    "directory":            {"type": "string",  "description": "Directorio raíz (default: directorio actual)"},
                    "extensions":           {"type": "string",  "description": "Extensiones separadas por coma (ej. 'c,h' para C/C++)"},
                    "context_lines":        {"type": "integer", "description": "Líneas de contexto (default: 2, max 20)"},
                    "max_matches":          {"type": "integer", "description": "Máximo de resultados (default: 50, max 200)"},
                    "ignore_case":          {"type": "boolean", "description": "Ignorar mayúsculas (default: true)"},
                    "exclude_pattern":      {"type": "string",  "description": "Patrón regex a excluir (como grep -v)"},
                    "count_only":           {"type": "boolean", "description": "Si true, solo conteo por fichero (grep -c)"},
                    "files_with_matches":   {"type": "boolean", "description": "Si true, solo ficheros con coincidencias (grep -l)"},
                    "files_without_matches":{"type": "boolean", "description": "Si true, solo ficheros sin coincidencias (grep -L)"},
                },
                "required": ["pattern"],
            },
        })

        def multi_grep(
            patterns: list, directory: str = ".",
            extensions: str = "py,js,ts,c,h,hpp,cpp,rs,go,java,rb,sh,md,json,yaml,toml",
            context_lines: int = 2, max_per_pattern: int = 20, ignore_case: bool = True,
        ) -> str:
            return _mcp_multi_grep({
                "patterns": patterns, "directory": directory, "extensions": extensions,
                "context_lines": context_lines, "max_per_pattern": max_per_pattern,
                "ignore_case": ignore_case,
            })

        registry.register("multi_grep", multi_grep, {
            "name": "multi_grep",
            "description": (
                "Busca MÚLTIPLES patrones a la vez en el código fuente. "
                "Equivale a N búsquedas grep_code en una sola llamada — evita hacer N llamadas a grep_code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patterns":        {"type": "array", "items": {"type": "string"}, "description": "Lista de patrones regex"},
                    "directory":       {"type": "string",  "description": "Directorio raíz (ruta absoluta)"},
                    "extensions":      {"type": "string",  "description": "Extensiones separadas por coma"},
                    "context_lines":   {"type": "integer", "description": "Líneas de contexto por coincidencia (default: 2)"},
                    "max_per_pattern": {"type": "integer", "description": "Máximo resultados por patrón (default: 20)"},
                    "ignore_case":     {"type": "boolean", "description": "Ignorar mayúsculas (default: true)"},
                },
                "required": ["patterns"],
            },
        })

        def code_outline(path: str, min_lines: int = 0, with_docstrings: bool = False) -> str:
            return _mcp_code_outline({"path": path, "min_lines": min_lines,
                                      "with_docstrings": with_docstrings})

        registry.register("code_outline", code_outline, {
            "name": "code_outline",
            "description": (
                "Devuelve la estructura de un fichero: clases, métodos y funciones con sus números de línea. "
                "FUNDAMENTAL para navegar ficheros grandes (>200 líneas) sin read_file con múltiples offsets. "
                "Para .py usa ast.parse; para otros lenguajes usa ctags. "
                "Úsalo antes de editar loop.py, hooks.py u otros ficheros grandes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":           {"type": "string",  "description": "Ruta al fichero de código"},
                    "min_lines":      {"type": "integer", "description": "Solo genera outline si el fichero supera este número de líneas (0 = siempre)"},
                    "with_docstrings": {"type": "boolean", "description": "Añade la primera línea del docstring a cada clase/método/función (default: false)"},
                },
                "required": ["path"],
            },
        })

        def read_sections(path: str, sections: list) -> str:
            return _mcp_read_sections({"path": path, "sections": sections})

        registry.register("read_sections", read_sections, {
            "name": "read_sections",
            "description": (
                "Lee secciones específicas (funciones, clases, métodos) de un fichero por nombre, "
                "sin leer el fichero entero. "
                "ÚSALO en lugar de múltiples read_file(offset=N) para 2+ funciones no contiguas. "
                "Para .py usa ast.parse (extrae la sección exacta incluyendo decoradores). "
                "Para otros lenguajes usa ctags."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":     {"type": "string", "description": "Ruta al fichero de código"},
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de nombres: 'Clase.metodo' o 'funcion'. Ej. ['AgentLoop.run', '_detect_tasks']",
                    },
                },
                "required": ["path", "sections"],
            },
        })

        def affected_files(
            symbol: str, directory: str = ".",
            extensions: str = "",
            exclude_tests: bool = False,
            whole_word: bool = True,
            max_files: int = 40,
        ) -> str:
            return _mcp_affected_files({
                "symbol": symbol, "directory": directory,
                "extensions": extensions, "exclude_tests": exclude_tests,
                "whole_word": whole_word, "max_files": max_files,
            })

        registry.register("affected_files", affected_files, {
            "name": "affected_files",
            "description": (
                "Encuentra todos los ficheros que referencian un símbolo (función, clase, variable, macro). "
                "USA ESTO antes de renombrar o cambiar una interfaz para saber qué ficheros hay que actualizar. "
                "Agrupa los resultados por fichero con conteo de referencias."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol":        {"type": "string",  "description": "Nombre del símbolo, ej. 'ch_ret', 'AgentLoop', 'invalidate_file'"},
                    "directory":     {"type": "string",  "description": "Directorio raíz con ruta absoluta (default: directorio actual)"},
                    "extensions":    {"type": "string",  "description": "Extensiones separadas por coma (ej. 'c,h'). Default: todos los tipos de código."},
                    "exclude_tests": {"type": "boolean", "description": "Excluir ficheros de test. Default: false."},
                    "whole_word":    {"type": "boolean", "description": "Buscar solo palabra completa (default: true)."},
                    "max_files":     {"type": "integer", "description": "Máximo de ficheros a mostrar (default: 40)."},
                },
                "required": ["symbol"],
            },
        })

        def python_exec(code: str, timeout: int = 15, workdir: str = "") -> str:
            return _mcp_python_exec({
                "code": code, "timeout": timeout,
                "workdir": workdir if workdir else None,
            })

        registry.register("python_exec", python_exec, {
            "name": "python_exec",
            "description": (
                "Ejecuta un fragmento de código Python y captura stdout/stderr. "
                "Útil para cálculos, transformaciones de datos o validaciones rápidas. "
                "NO uses esto para escribir múltiples ficheros fuente — usa edit_file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code":    {"type": "string",  "description": "Código Python a ejecutar"},
                    "timeout": {"type": "integer", "description": "Timeout en segundos (default: 15, max: 60)"},
                    "workdir": {"type": "string",  "description": "Directorio de trabajo (default: workspace del agente)"},
                },
                "required": ["code"],
            },
        })

        def ls_dir(path: str = ".", hidden: bool = False, sort: str = "name") -> str:
            return _mcp_ls_dir({"path": path, "hidden": hidden, "sort": sort})

        registry.register("ls_dir", ls_dir, {
            "name": "ls_dir",
            "description": "Lista el contenido de un directorio con permisos, propietario, tamaño y fecha (estilo ls -la).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":   {"type": "string",  "description": "Ruta del directorio (default: directorio actual)"},
                    "hidden": {"type": "boolean", "description": "Mostrar ficheros ocultos (default: false)"},
                    "sort":   {"type": "string",  "description": "Ordenar por: name | size | mtime (default: name)"},
                },
                "required": [],
            },
        })

        from mcp_servers.oocode_assistant import (
            _tool_find_file  as _mcp_find_file,
            _tool_find_files as _mcp_find_files,
            _tool_find_dir   as _mcp_find_dir,
            _tool_file_stat  as _mcp_file_stat,
        )

        def find_file(path: str = ".", pattern: str = "*",
                      maxdepth: int = 10, limit: int = 100) -> str:
            return _mcp_find_file({"path": path, "pattern": pattern,
                                   "maxdepth": maxdepth, "limit": limit})

        registry.register("find_file", find_file, {
            "name": "find_file",
            "description": (
                "USA ESTO en lugar de 'bash find'. "
                "Busca ficheros que coincidan con un patrón glob en un directorio (recursivo). "
                "Excluye .git automáticamente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":     {"type": "string",  "description": "Directorio raíz (default: directorio actual)"},
                    "pattern":  {"type": "string",  "description": "Glob, ej: '*.py', 'test_*', 'Makefile'"},
                    "maxdepth": {"type": "integer", "description": "Profundidad máxima (default: 10)"},
                    "limit":    {"type": "integer", "description": "Máx resultados (default: 100)"},
                },
                "required": [],
            },
        })

        def find_files(directory: str = ".", name: str = "",
                       extension: str = "", max_depth: int = 10,
                       max_results: int = 50) -> str:
            return _mcp_find_files({"directory": directory, "name": name,
                                    "extension": extension, "max_depth": max_depth,
                                    "max_results": max_results})

        registry.register("find_files", find_files, {
            "name": "find_files",
            "description": (
                "Búsqueda avanzada de ficheros: por nombre glob, extensión, tamaño y edad. "
                "Excluye .git, __pycache__, node_modules automáticamente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory":   {"type": "string",  "description": "Directorio raíz (ruta absoluta preferida)"},
                    "name":        {"type": "string",  "description": "Patrón glob del nombre (ej: '*.py', 'test_*')"},
                    "extension":   {"type": "string",  "description": "Extensión sin punto (ej: 'py')"},
                    "max_depth":   {"type": "integer", "description": "Profundidad máxima (default: 10)"},
                    "max_results": {"type": "integer", "description": "Máx resultados (default: 50)"},
                },
                "required": [],
            },
        })

        def find_dir(path: str = ".", pattern: str = "*",
                     maxdepth: int = 8, limit: int = 100) -> str:
            return _mcp_find_dir({"path": path, "pattern": pattern,
                                  "maxdepth": maxdepth, "limit": limit})

        registry.register("find_dir", find_dir, {
            "name": "find_dir",
            "description": (
                "USA ESTO en lugar de 'bash find -type d'. "
                "Busca directorios que coincidan con un patrón glob."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":     {"type": "string",  "description": "Directorio raíz (default: directorio actual)"},
                    "pattern":  {"type": "string",  "description": "Glob, ej: 'src', 'test*'"},
                    "maxdepth": {"type": "integer", "description": "Profundidad máxima (default: 8)"},
                    "limit":    {"type": "integer", "description": "Máx resultados (default: 100)"},
                },
                "required": [],
            },
        })

        def file_stat(path: str) -> str:
            return _mcp_file_stat({"path": path})

        registry.register("file_stat", file_stat, {
            "name": "file_stat",
            "description": (
                "USA ESTO en lugar de 'bash stat/wc -l'. "
                "Metadatos de un fichero: permisos, propietario, tamaño, fechas, nº de líneas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del fichero o directorio"},
                },
                "required": ["path"],
            },
        })

    except ImportError:
        pass  # MCP server no disponible — las tools quedan sin registrar

    # workspace_remember — guarda instrucciones persistentes en OOCODE.md del proyecto
    def workspace_remember(note: str, section: str = "Notas del usuario") -> str:
        """Añade una nota/instrucción persistente al OOCODE.md del workspace."""
        import datetime as _dt
        oocode_md = Path(workdir) / "OOCODE.md"
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"- [{ts}] {note}\n"
        try:
            if oocode_md.exists():
                content = oocode_md.read_text()
                header = f"## {section}"
                if header in content:
                    content = content.replace(
                        header + "\n",
                        header + "\n" + entry,
                    )
                else:
                    content += f"\n{header}\n{entry}"
            else:
                content = f"# OOCODE.md\n\n## {section}\n{entry}"
            oocode_md.write_text(content)
            return f"Nota guardada en OOCODE.md: {note}"
        except Exception as exc:
            return f"Error guardando nota: {exc}"

    registry.register(
        "workspace_remember",
        workspace_remember,
        {
            "name": "workspace_remember",
            "description": (
                "Guarda una instrucción o nota persistente en OOCODE.md del proyecto. "
                "Úsala cuando el usuario pida 'recuerda que...', 'siempre haz X', "
                "o dé instrucciones que deben persistir entre sesiones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "note":    {"type": "string", "description": "Instrucción o nota a guardar"},
                    "section": {"type": "string", "description": "Sección en OOCODE.md (default: 'Notas del usuario')"},
                },
                "required": ["note"],
            },
        },
    )

    # Configurar caché intra-turno
    if config is not None:
        registry.cache_enabled  = config.tool_cache_enabled
        registry.cache_max_size = config.tool_cache_max_size

    return registry


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="oocode",
        description="OOCode — Asistente de programación local con Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  oocode                          Agente 'main' desde ~/.oocode/oocode.json\n"
            "  oocode --agent coding           Agente 'coding' con su propio workspace\n"
            "  oocode --model qwen3.5:9b       Sobreescribe el modelo para esta sesión\n"
            "  oocode /home/user/mi-proyecto   Workspace apuntando a un proyecto\n"
        ),
    )
    parser.add_argument("--agent", "-a", metavar="ID",
                        help="ID del agente (definido en ~/.oocode/oocode.json)")
    parser.add_argument("--model", "-m", metavar="MODELO",
                        help="Modelo Ollama (sobreescribe el del agente para esta sesión)")
    parser.add_argument("--host", metavar="URL",
                        help="URL del servidor Ollama (ej: http://192.168.1.33:11434)")
    parser.add_argument("--workspace", "-w", metavar="RUTA",
                        help="Workspace del agente (sobreescribe el de oocode.json)")
    parser.add_argument("dir", nargs="?",
                        help="Directorio de trabajo del proyecto (donde buscar OOCODE.md)")
    args = parser.parse_args()

    _sync_plugins()
    _sync_skills()
    config = OOConfig.load(agent_id=args.agent)

    if args.host:
        config.ollama_host = args.host
    if args.model:
        config.model = args.model
    if args.workspace:
        config.workspace = str(Path(args.workspace).expanduser().resolve())

    # Directorio de proyecto: separado del workspace de identidad (~/.oocode/workspace/main/)
    # args.dir indica el proyecto donde buscar OOCODE.md y ejecutar bash — no el workspace.
    if args.dir:
        os.chdir(str(Path(args.dir).expanduser().resolve()))
    project_dir = str(Path.cwd().resolve())
    config.project_dir = project_dir

    # Asegurar que el modelo activo tiene timeoutSeconds en su config al arrancar
    if config.model and config.model in config.model_configs:
        if "timeoutSeconds" not in config.model_configs[config.model]:
            config.model_configs[config.model]["timeoutSeconds"] = config.fallback_timeout
            config.save()

    # Inicializar sistema de logs
    log.init(
        enabled=config.log_enabled,
        log_file=config.log_file,
        level=config.log_level,
        max_size_mb=config.log_max_size,
        max_files=config.log_max_files,
    )
    log.info("session_start", agent=config.agent_id, model=config.model or "")

    # Runtime se crea aquí para que el banner use el color guardado
    runtime = RuntimeSettings(accent_color=config.accent_color)
    # Cargar preferencias de razonamiento guardadas para el modelo activo
    if config.model:
        _tl, _r = config.get_model_thinking(config.model)
        runtime.think_level = _tl
        runtime.reasoning   = _r

    print_banner(config)

    # Inicializar workspace si no existe
    ws_manager = WorkspaceManager(
        config.workspace,
        config.agent_name,
        config.agent_emoji,
        ollama_host=config.ollama_host,
        permissions=config.permissions,
        max_memory_lines=config.ws_max_memory_lines,
        max_daily_chars=config.ws_max_daily_chars,
    )
    if not ws_manager.exists():
        created = ws_manager.init()
        console.print(f"  [green]✓[/green]  Workspace inicializado: {', '.join(created)}")
        console.print()

    # OOCODE.md trust check — igual que Claude Code con CLAUDE.md
    _oocode_md_path = Path(project_dir) / "OOCODE.md"
    if not _oocode_md_path.exists() and project_dir != str(Path.home() / ".oocode"):
        from prompt_toolkit import prompt as _pt_prompt
        console.print(
            f"  [yellow]⚠[/yellow]  No se encontró [cyan]OOCODE.md[/cyan] en "
            f"[dim]{project_dir}[/dim]"
        )
        try:
            _trust = _pt_prompt("  ¿Crear OOCODE.md en este directorio? [s/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            _trust = "n"
        if _trust in ("s", "si", "sí", "y", "yes"):
            from ui.commands import _cmd_init
            _cmd_init(project_dir, config, None)
            console.print()

    if not config.model:
        select_model_interactive(config)
        # Auto-detectar contextWindow, maxTokens y params del modelo recién elegido
        if config.model and config.model not in config.model_configs:
            from ui.commands import _auto_detect_model_config
            _auto_detect_model_config(config, config.model)
        console.print()

    permissions = PermissionManager(config.permissions)
    embed_client = EmbeddingClient(
        host=config.ollama_host,
        model=config.embed_model,
        max_input_chars=config.embed_max_input_chars,
    )
    # Directorio de memoria por agente: evita mezcla de memorias entre agentes
    agent_memory_dir = MEMORY_DIR / config.agent_id
    agent_memory_dir.mkdir(parents=True, exist_ok=True)
    # Migración silenciosa: mover ficheros legacy de ~/.oocode/memory/ a la carpeta del agente
    if config.agent_id == "main":
        for _f in MEMORY_DIR.glob("*.md"):
            _dst = agent_memory_dir / _f.name
            if not _dst.exists():
                import shutil as _sh
                _sh.copy2(_f, _dst)
        for _f in MEMORY_DIR.glob("*.emb.json"):
            _dst = agent_memory_dir / _f.name
            if not _dst.exists():
                import shutil as _sh
                _sh.copy2(_f, _dst)

    memory = MemorySystem(
        embed_client=embed_client if config.memory_embed_enabled else None,
        similarity_threshold=config.embed_similarity_threshold,
        snippet_chars=config.embed_snippet_chars,
        top_k=config.embed_top_k,
        memory_dir=agent_memory_dir,
    )

    # WorkspaceRAG: auto-indexación semántica del proyecto en background
    _workspace_rag = None
    if config.rag_enabled:
        try:
            from agent.workspace_rag import WorkspaceRAG
            _workspace_rag = WorkspaceRAG(
                workspace=project_dir,
                embed_client=embed_client,
                index_dir=CONFIG_DIR / "search_index",
                top_k=config.rag_top_k,
                similarity_threshold=config.rag_similarity_threshold,
                max_snippet_chars=config.rag_max_snippet_chars,
                index_interval=config.rag_index_interval,
            )
            log.info("workspace_rag_init", workspace=config.workspace,
                     index_size=_workspace_rag.index_size)
        except Exception as _exc:
            log.error("workspace_rag_init_error", error=str(_exc))

    registry = build_registry(project_dir, config)

    # Subagent runner — inicialización anticipada para registrar la tool.
    # Los plugins/skills se inyectan después de cargarlos más abajo.
    subagent_runner = SubAgentRunner(config, permissions, build_registry,
                                     embed_client=embed_client)
    name, fn, schema = subagent_runner.as_tool_schema()
    registry.register(name, fn, schema)
    exp_name, exp_fn, exp_schema = subagent_runner.as_explore_schema()
    registry.register(exp_name, exp_fn, exp_schema)

    # mem_save — requiere la instancia de memory, no disponible en build_registry()
    _mem_ref = memory
    def _fn_mem_save(name: str, content: str, description: str = "") -> str:
        return _mem_ref.save(name, content, description)
    registry.register("mem_save", _fn_mem_save, {
        "name": "mem_save",
        "description": (
            "Guarda un recuerdo persistente en la memoria del agente (fichero .md con embedding). "
            "Úsalo para guardar hechos importantes del proyecto, decisiones de arquitectura, "
            "bugs conocidos, o preferencias del usuario que deben recordarse entre sesiones. "
            "Al terminar una tarea significativa, considera guardar los hallazgos clave. "
            "Busca memorias relacionadas antes de guardar para evitar duplicados."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre del recuerdo en snake_case (ej: 'database_schema', 'user_preferences')",
                },
                "content": {
                    "type": "string",
                    "description": "Contenido en markdown — puede incluir código, listas, decisiones",
                },
                "description": {
                    "type": "string",
                    "description": "Descripción de una línea para el índice MEMORY.md (opcional)",
                },
            },
            "required": ["name", "content"],
        },
    })

    # Sesión
    session = SessionManager(config.agent_id)
    session.start(config.model or "", project_dir)
    console.print(
        f"  [dim]Sesión:[/dim] [dim cyan]{session.session_id[:8]}…[/dim cyan]  "
        f"[dim]/sessions para historial[/dim]\n"
    )

    agent = AgentLoop(
        config=config,
        registry=registry,
        permissions=permissions,
        memory=memory,
        workspace_manager=ws_manager,
        session_manager=session,
        runtime=runtime,
        subagent_runner=subagent_runner,
    )

    agent._workspace_rag = _workspace_rag
    agent._embed_client  = embed_client

    # plan_create / task_done — requieren instancia del AgentLoop ya creada
    registry.register("plan_create", agent._execute_plan_create, {
        "name": "plan_create",
        "description": (
            "Crea un plan de tareas numerado para ejecutar de forma organizada. "
            "Úsalo cuando tengas ≥3 pasos distintos que realizar: llama plan_create(tasks=[...]) "
            "ANTES de ejecutar cualquier herramienta, muestra el plan al usuario y empieza por la tarea 1. "
            "Llama task_done() al completar cada tarea para avanzar al siguiente paso. "
            "Cuando todas las tareas estén completas, anuncia 'He completado todas las tareas.'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista ordenada de tareas a ejecutar (strings concisos, ej: 'Leer config.py y extraer permisos')",
                },
                "summary": {
                    "type": "string",
                    "description": "Descripción breve del plan completo (opcional, mostrada al usuario)",
                },
            },
            "required": ["tasks"],
        },
    })
    registry.register("task_done", agent._execute_task_done, {
        "name": "task_done",
        "description": (
            "Marca la tarea activa del plan como completada y activa la siguiente. "
            "Llama a esta herramienta cada vez que termines una tarea del plan para avanzar el marcador ✔/◼/◻. "
            "Si no hay plan activo, devuelve error — crea uno primero con plan_create()."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Mensaje opcional de resumen sobre lo que se completó en esta tarea",
                },
            },
        },
    })

    # Managers de sesión
    agent.branches  = BranchManager(config.agent_id)
    agent.tasks     = TaskManager()
    agent.scheduler = Scheduler()

    # Skills: carga herramientas habilitadas (fuente de verdad: oocode.json)
    agent.skills = SkillManager(enabled_override=config.skills_enabled or None)
    for skill_name, skill_fn, skill_schema in agent.skills.load_tools():
        if not registry.has(skill_name):
            registry.register(skill_name, skill_fn, skill_schema)
    log.info("skills_loaded", count=len(list(agent.skills._enabled)))

    # Plugins: fuente de verdad en oocode.json; los plugins pueden sobreescribir tools
    _has_lsp = "lsp" in (config.plugins_enabled or [])
    _lsp_autostart = []
    if _has_lsp:
        _lsp_opts = config.plugin_options.get("lsp", {})
        if isinstance(_lsp_opts, dict):
            _lsp_autostart = [e for e in _lsp_opts.get("autoStart", []) if e]
    if _lsp_autostart:
        console.print(
            f"  [dim]LSP:[/dim] [dim cyan]iniciando servidores: "
            f"{', '.join(_lsp_autostart)}…[/dim cyan]"
        )
    agent.plugins = PluginManager(enabled_override=config.plugins_enabled or None)
    plugin_errors = agent.plugins.load_all(config)
    for p_name, p_fn, p_schema in agent.plugins.get_tools():
        registry.register(p_name, p_fn, p_schema)
    log.info("plugins_loaded", count=len(agent.plugins._loaded), errors=len(plugin_errors))
    if plugin_errors:
        for err in plugin_errors:
            log.error("plugin_load_error", detail=err)
            console.print(f"  [yellow]⚠[/yellow]  Plugin error: {err}")

    # Inyectar plugins, skills y cliente Ollama en el subagent_runner.
    # Compartir el cliente evita que Ollama descargue/recargue el modelo entre
    # llamadas del agente principal y sus subagentes.
    subagent_runner._parent_plugins = agent.plugins
    subagent_runner._parent_skills  = agent.skills
    subagent_runner._parent_client  = agent.client
    subagent_runner._parent_rt      = agent.rt

    # Hooks built-in: registrar según config.hooks_builtins
    if config.hooks_enabled and config.hooks_builtins:
        registered = registry.hooks.register_builtins(config.hooks_builtins)
        if registered:
            log.info("hooks_builtins_registered", hooks=registered)

    # Ctags: configurar workspace e indexar símbolos si no existe índice
    try:
        from tools.ctags_index import set_workspace, ensure_initial_index
        set_workspace(config.workspace)
        ensure_initial_index()
    except Exception:
        pass

    # Hooks de OOCODE.md: cargar sección ## Hooks si existe
    if config.hooks_enabled:
        _load_oocode_md_hooks(registry.hooks, config)

    # MCP: arrancar servidores configurados y registrar sus tools
    _mcp_pool = None
    # Servidores del usuario (mcp.servers en oocode.json)
    _active_mcp_servers = [s for s in config.mcp_servers if s.get("enabled", True)]
    # Nombres ya presentes — los bundled solo se añaden si no están listados explícitamente
    _active_names = {s.get("name") for s in _active_mcp_servers}
    if config.mcp_oocode_assistant_enabled and "oocode-assistant" not in _active_names:
        _bundled_path = str(Path(__file__).parent / "mcp_servers" / "oocode_assistant.py")
        if Path(_bundled_path).exists():
            _active_mcp_servers = [
                {"name": "oocode-assistant", "cmd": [sys.executable, _bundled_path]}
            ] + _active_mcp_servers
            _active_names.add("oocode-assistant")
    if config.mcp_system_assistant_enabled and "system-assistant" not in _active_names:
        _sys_path = str(Path(__file__).parent / "mcp_servers" / "system_assistant.py")
        if Path(_sys_path).exists():
            _active_mcp_servers.append(
                {"name": "system-assistant", "cmd": [sys.executable, _sys_path]}
            )
            _active_names.add("system-assistant")
    if config.mcp_home_office_assistant_enabled and "home-office-assistant" not in _active_names:
        _ho_path = str(Path(__file__).parent / "mcp_servers" / "home_office_assistant.py")
        if Path(_ho_path).exists():
            _active_mcp_servers.append(
                {"name": "home-office-assistant", "cmd": [sys.executable, _ho_path]}
            )
            _active_names.add("home-office-assistant")
    if config.mcp_security_assistant_enabled and "security-assistant" not in _active_names:
        _sec_path = str(Path(__file__).parent / "mcp_servers" / "security_assistant.py")
        if Path(_sec_path).exists():
            _active_mcp_servers.append(
                {"name": "security-assistant", "cmd": [sys.executable, _sec_path]}
            )
            _active_names.add("security-assistant")
    if config.mcp_iot_assistant_enabled and "iot-assistant" not in _active_names:
        _iot_path = str(Path(__file__).parent / "mcp_servers" / "iot_assistant.py")
        if Path(_iot_path).exists():
            _active_mcp_servers.append(
                {"name": "iot-assistant", "cmd": [sys.executable, _iot_path]}
            )
    if _active_mcp_servers:
        _srv_names = [s.get("name", "mcp") for s in _active_mcp_servers]
        console.print(
            f"  [dim]MCP:[/dim] [dim cyan]iniciando servidores: "
            f"{', '.join(_srv_names)}…[/dim cyan]"
        )
        try:
            from agent.mcp_client import McpPool
            _mcp_pool = McpPool(request_timeout=config.mcp_request_timeout)
            for srv in _active_mcp_servers:
                _mcp_pool.start_server(
                    name=srv.get("name", "mcp"),
                    cmd=srv.get("cmd", []),
                    env=srv.get("env"),
                    cwd=srv.get("cwd"),
                    description=srv.get("description", ""),
                )
            for mcp_name, mcp_fn, mcp_schema in _mcp_pool.all_oocode_tools():
                if not registry.has(mcp_name):
                    registry.register(mcp_name, mcp_fn, mcp_schema)
            for res_name, res_fn, res_schema in _mcp_pool.resource_oocode_tools():
                if not registry.has(res_name):
                    registry.register(res_name, res_fn, res_schema)
            for prm_name, prm_fn, prm_schema in _mcp_pool.prompt_oocode_tools():
                if not registry.has(prm_name):
                    registry.register(prm_name, prm_fn, prm_schema)
            log.info("mcp_loaded", servers=_mcp_pool.client_count,
                     tools=_mcp_pool.tool_count)
            _errs = [c.error for c in _mcp_pool._clients.values() if c.error]
            if _errs:
                for _e in _errs:
                    console.print(f"  [yellow]⚠  MCP:[/yellow] {_e}")
            else:
                console.print(
                    f"  [dim]MCP:[/dim] [dim cyan]{_mcp_pool.client_count} servidores · "
                    f"{_mcp_pool.tool_count} tools[/dim cyan]\n"
                )
        except Exception as _exc:
            log.error("mcp_init_error", error=str(_exc))
            console.print(f"  [yellow]⚠  MCP error:[/yellow] {_exc}")

    # Exponer _mcp_pool en el agente para /mcp y /status
    agent._mcp_pool = _mcp_pool
    # Compartir el pool con los subagentes para que tengan acceso a los mismos tools MCP
    # (McpClient usa _send_lock + _id_lock → thread-safe para múltiples threads)
    subagent_runner._parent_mcp_pool = _mcp_pool

    # Adjuntar módulo LSP cargado (no el de sys.modules["plugins.lsp"] que es distinto)
    # El plugin manager usa _oocode_plugin_lsp como clave, no plugins.lsp.
    # La toolbar lee agent._lsp_mod._pool para obtener el pool actual.
    agent._lsp_mod = agent.plugins._loaded.get("lsp")

    run_repl(agent, config)

    if _mcp_pool is not None:
        _mcp_pool.stop_all()

    log.info("session_end", agent=config.agent_id)


if __name__ == "__main__":
    main()
