#!/usr/bin/env python3
"""DevOps assistant MCP server — git, docker, build, debug, filesystem.

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 newline-delimited JSON).

Tools:
  git_status, git_diff, git_log, git_add, git_commit, git_push, git_pull,
  git_branch, git_stash, git_patch, git_clone, git_worktree, git_blame,
  git_rebase, git_tag, git_cherry_pick,
  docker_ps, docker_logs, docker_exec, docker_inspect, docker_images,
  docker_stop, docker_rm, docker_cp,
  compose_version, compose_services, compose_status, compose_up, compose_down,
  compose_stop, compose_restart, compose_build, compose_pull, compose_logs,
  compose_exec, compose_run, compose_config, compose_images, compose_top,
  chmod_file, chmod_dir, chown_file, chown_dir, mv_file, cp_file,
  rm_file, rm_dir, mkdir_dir, touch_file,
  strace_run, gdb_run, pdb_run, valgrind_run,
  make_run, run_script, format_code, mypy_check,
  python_exec, pip_tool, npm_tool,
  archive_extract, archive_create, archive_list,
  file_stat, symlink_create, readlink
"""
import json
import os
import re
import sys
import subprocess
import tempfile as _tempfile
from pathlib import Path

# Límite de truncado de salida (configurable: tools.mcpMaxOutputChars en oocode.json)
def _mcp_max_output(default: int = 4000) -> int:
    try:
        from pathlib import Path as _P
        import json as _j
        _f = _P.home() / ".oocode" / "oocode.json"
        if _f.exists():
            return int(_j.loads(_f.read_text()).get("tools", {}).get("mcpMaxOutputChars", default))
    except Exception:
        pass
    return default


_MAX_OUTPUT = _mcp_max_output()
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
            parts.append("STDOUT:\n" + out.strip()[:_MAX_OUTPUT])
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



_TOOLS = [
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
]


_TOOL_FNS = {
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
    # Filesystem mutations
    "chmod_file":        _tool_chmod_file,
    "chmod_dir":         _tool_chmod_dir,
    "chown_file":        _tool_chown_file,
    "chown_dir":         _tool_chown_dir,
    "mv_file":           _tool_mv_file,
    "cp_file":           _tool_cp_file,
    "rm_file":           _tool_rm_file,
    "rm_dir":            _tool_rm_dir,
    "mkdir_dir":         _tool_mkdir_dir,
    "touch_file":        _tool_touch_file,
    # Debug
    "strace_run":        _tool_strace_run,
    "gdb_run":           _tool_gdb_run,
    "pdb_run":           _tool_pdb_run,
    "valgrind_run":      _tool_valgrind_run,
    # Build
    "make_run":          _tool_make_run,
    "run_script":        _tool_run_script,
    "format_code":       _tool_format_code,
    "mypy_check":        _tool_mypy_check,
    # Python
    "python_exec":       _tool_python_exec,
    "pip_tool":          _tool_pip_tool,
    # Node.js
    "npm_tool":          _tool_npm_tool,
    # Archive
    "archive_extract":   _tool_archive_extract,
    "archive_create":    _tool_archive_create,
    "archive_list":      _tool_archive_list,
    # File metadata
    "file_stat":         _tool_file_stat,
    "symlink_create":    _tool_symlink_create,
    "readlink":          _tool_readlink,
}


# ── Recursos ─────────────────────────────────────────────────────────────────

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
        comment = ""
        if i > 0 and lines[i - 1].startswith("##"):
            comment = lines[i - 1][2:].strip()
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

    gh_dir = root / ".github" / "workflows"
    if gh_dir.is_dir():
        workflows = sorted(gh_dir.glob("*.yml")) + sorted(gh_dir.glob("*.yaml"))
        if workflows:
            parts.append("## GitHub Actions workflows\n")
            for wf in workflows[:5]:
                content = wf.read_text(errors="replace")[:1500]
                parts.append(f"### {wf.name}\n```yaml\n{content}\n```")

    gitlab_ci = root / ".gitlab-ci.yml"
    if gitlab_ci.exists():
        content = gitlab_ci.read_text(errors="replace")[:2000]
        parts.append(f"## .gitlab-ci.yml\n```yaml\n{content}\n```")

    jenkinsfile = root / "Jenkinsfile"
    if jenkinsfile.exists():
        content = jenkinsfile.read_text(errors="replace")[:2000]
        parts.append(f"## Jenkinsfile\n```groovy\n{content}\n```")

    circle = root / ".circleci" / "config.yml"
    if circle.exists():
        content = circle.read_text(errors="replace")[:1500]
        parts.append(f"## .circleci/config.yml\n```yaml\n{content}\n```")

    travis = root / ".travis.yml"
    if travis.exists():
        content = travis.read_text(errors="replace")[:1500]
        parts.append(f"## .travis.yml\n```yaml\n{content}\n```")

    if not parts:
        return "(no se encontró configuración CI/CD: .github/workflows/, .gitlab-ci.yml, Jenkinsfile, etc.)"
    return "\n\n".join(parts)


_RESOURCES = [
    {
        "uri":         "project://git",
        "name":        "Estado git",
        "description": "git status + últimos 10 commits + diff stats del directorio actual",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "project://docker",
        "name":        "Estado Docker",
        "description": "Contenedores activos, imágenes, redes y volúmenes Docker",
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
]

_RESOURCE_FNS = {
    "project://git":      _resource_git_status,
    "project://docker":   _resource_project_docker,
    "project://makefile": _resource_project_makefile,
    "project://ci":       _resource_project_ci,
}


# ── Prompts ───────────────────────────────────────────────────────────────────

_PROMPTS = {
    "docker_compose_setup": {
        "description": "Genera un docker-compose.yml completo y listo para producción",
        "arguments": [
            {"name": "stack",       "description": "Descripción del stack: servicios, bases de datos, cachés, etc.",  "required": True},
            {"name": "environment", "description": "Entorno objetivo: development, staging, production (default: development)", "required": False},
            {"name": "extras",      "description": "Extras: healthchecks, volúmenes persistentes, redes custom, secrets", "required": False},
        ],
    },
    "git_workflow": {
        "description": "Define el flujo de trabajo git adecuado para un equipo o proyecto",
        "arguments": [
            {"name": "team_size",   "description": "Tamaño del equipo: solo, small (2-5), medium (5-15), large (15+)", "required": False},
            {"name": "project",     "description": "Descripción del proyecto o producto",                               "required": False},
            {"name": "constraints", "description": "Restricciones: releases regulares, hotfixes, monorepo, open-source", "required": False},
        ],
    },
    "ci_pipeline": {
        "description": "Genera un pipeline CI/CD completo para un proyecto",
        "arguments": [
            {"name": "project",   "description": "Descripción del proyecto: lenguaje, framework, tipo de despliegue", "required": True},
            {"name": "platform",  "description": "Plataforma CI: github_actions, gitlab_ci, jenkins, circleci (default: github_actions)", "required": False},
            {"name": "stages",    "description": "Etapas a incluir: lint, test, build, security, deploy, notify",      "required": False},
        ],
    },
}


def _prompt_get(name: str, arguments: dict) -> list[dict]:
    if name == "docker_compose_setup":
        stack       = arguments.get("stack", "")
        environment = arguments.get("environment", "development")
        extras      = arguments.get("extras", "")
        extras_str  = f"\n\nExtras requeridos: {extras}" if extras else ""
        env_notes = {
            "development": "modo desarrollo: volúmenes de código montados, hot-reload, puertos expuestos, sin TLS",
            "staging":     "entorno staging: similar a producción pero con acceso de debug, datos de prueba",
            "production":  "producción: recursos limitados, healthchecks, restart:always, secretos via env_file o secrets, sin puertos innecesarios expuestos",
        }.get(environment, "modo desarrollo")
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera un docker-compose.yml completo para el siguiente stack:\n\n{stack}{extras_str}\n\n"
            f"Entorno objetivo: **{environment}** ({env_notes})\n\n"
            "Incluye:\n"
            "1. **Servicios** — definición completa de cada contenedor con image/build, ports, environment, volumes\n"
            "2. **Dependencias** — `depends_on` con `condition: service_healthy` donde aplique\n"
            "3. **Healthchecks** — para bases de datos y servicios críticos\n"
            "4. **Redes** — red custom para comunicación entre servicios, sin exponer puertos innecesarios\n"
            "5. **Volúmenes** — persistencia de datos con nombres explícitos\n"
            "6. **Variables de entorno** — uso de .env o env_file con comentarios para cada variable\n\n"
            "Proporciona el YAML completo y listo para usar, con comentarios explicativos en las secciones no obvias."
        )}}]

    elif name == "git_workflow":
        team_size   = arguments.get("team_size", "small")
        project     = arguments.get("project", "")
        constraints = arguments.get("constraints", "")
        project_str     = f"\n\nProyecto: {project}" if project else ""
        constraints_str = f"\n\nRestricciones: {constraints}" if constraints else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Define el flujo de trabajo git más adecuado para un equipo de tamaño **{team_size}**.{project_str}{constraints_str}\n\n"
            "Describe:\n"
            "1. **Estrategia de branching** — qué ramas usar, sus propósitos y ciclo de vida\n"
            "2. **Flujo de trabajo diario** — pasos concretos para feature, bugfix y hotfix\n"
            "3. **Convenciones de commits** — formato, prefijos, ejemplos buenos y malos\n"
            "4. **Proceso de code review** — cuándo crear PR, criterios de aprobación, merge vs rebase\n"
            "5. **Releases** — cómo versionar y desplegar, tags, changelogs\n"
            "6. **Comandos git clave** — cheatsheet de los comandos más usados en este flujo\n\n"
            "Sé específico: incluye los nombres exactos de ramas, prefijos de commit y comandos git."
        )}}]

    elif name == "ci_pipeline":
        project  = arguments.get("project", "")
        platform = arguments.get("platform", "github_actions")
        stages   = arguments.get("stages", "lint, test, build, deploy")
        platform_map = {
            "github_actions": "GitHub Actions (.github/workflows/ci.yml)",
            "gitlab_ci":      "GitLab CI (.gitlab-ci.yml)",
            "jenkins":        "Jenkins (Jenkinsfile declarativo)",
            "circleci":       "CircleCI (.circleci/config.yml)",
        }
        platform_desc = platform_map.get(platform, platform_map["github_actions"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera un pipeline CI/CD completo en **{platform_desc}** para:\n\n{project}\n\n"
            f"Etapas a incluir: {stages}\n\n"
            "El pipeline debe:\n"
            "1. **Ser funcional y completo** — listo para copiar-pegar, no esquelético\n"
            "2. **Cachear dependencias** — para acelerar las ejecuciones\n"
            "3. **Fallar rápido** — las comprobaciones baratas primero\n"
            "4. **Separar etapas** — cada job con su propósito claro\n"
            "5. **Manejar secretos** — usar variables de entorno del CI para credenciales\n"
            "6. **Comentar lo no obvio** — especialmente triggers, condiciones y deploys\n\n"
            "Proporciona el fichero completo de configuración con comentarios inline."
        )}}]

    else:
        return [{"role": "user", "content": {"type": "text", "text":
            f"Ejecuta el prompt '{name}' con los argumentos: {json.dumps(arguments, ensure_ascii=False)}"
        }}]


def _handle(req: dict) -> None:
    method   = req.get("method", "")
    params   = req.get("params") or {}
    req_id   = req.get("id")

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
            "serverInfo": {"name": "devops-assistant", "version": "1.1"},
        })

    elif method == "tools/list":
        _ok(req_id, {"tools": _TOOLS})

    elif method == "tools/call":
        name      = params.get("name", "")
        tool_args = params.get("arguments") or {}
        fn = _TOOL_FNS.get(name)
        if fn is None:
            _err(req_id, -32601, f"Tool desconocida: {name}")
            return
        try:
            result = fn(tool_args)
            _ok(req_id, {"content": [{"type": "text", "text": str(result)}]})
        except Exception as exc:
            _err(req_id, -32603, f"Error en tool '{name}': {exc}")

    elif method == "prompts/list":
        _ok(req_id, {"prompts": [
            {"name": k, "description": v["description"], "arguments": v.get("arguments", [])}
            for k, v in _PROMPTS.items()
        ]})

    elif method == "prompts/get":
        name      = params.get("name", "")
        arguments = params.get("arguments") or {}
        messages  = _prompt_get(name, arguments)
        _ok(req_id, {"description": _PROMPTS.get(name, {}).get("description", name), "messages": messages})

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
            _err(req_id, -32603, f"Error leyendo recurso '{uri}': {exc}")

    elif req_id is not None:
        _err(req_id, -32601, f"Método desconocido: {method}")


def main() -> None:
    sys.stderr.write(
        f"[devops-assistant] MCP server v1.1 iniciado  tools: {len(_TOOLS)}  prompts: {len(_PROMPTS)}  resources: {len(_RESOURCES)}\n"
    )
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
            sys.stderr.write(f"[devops-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
