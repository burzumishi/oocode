#!/usr/bin/env python3
"""OOCode System Assistant MCP Server — administración del sistema operativo.

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 newline-delimited).

Detecta automáticamente la familia del SO al arrancar:
  - Debian/Ubuntu: expone tools apt_*
  - RedHat/Fedora/RHEL: expone tools dnf_* y rpm_*
  - Ambas familias: systemctl, journalctl, ufw/firewalld, usuarios, red, disco

Tools de servicios (systemd):
  systemctl_status   — estado de uno o varios servicios
  systemctl_action   — start / stop / restart / enable / disable / reload
  journalctl         — logs del sistema o de un servicio (últimas N líneas)

Tools de paquetes — Debian/Ubuntu:
  apt_update         — actualiza la lista de paquetes (apt update)
  apt_upgrade        — muestra paquetes actualizables (--dry-run por defecto)
  apt_install        — instala paquetes
  apt_remove         — elimina paquetes
  apt_search         — busca paquetes por nombre o descripción
  apt_info           — información detallada de un paquete
  apt_list_installed — lista paquetes instalados con versión

Tools de paquetes — RedHat/Fedora/RHEL:
  dnf_update         — actualiza la lista y muestra actualizaciones disponibles
  dnf_install        — instala paquetes
  dnf_remove         — elimina paquetes
  dnf_search         — busca paquetes
  dnf_info           — información de un paquete
  rpm_query          — consulta la base de datos RPM (ficheros, versión, changelog)

Tools de red:
  net_interfaces     — lista interfaces de red con IP, MAC y estado
  net_connections    — conexiones activas (ss -tulpn)
  net_ping           — ping a un host (count limitado)
  net_dns            — resolución DNS con dig/host

Tools de disco y sistema de ficheros:
  disk_usage         — uso de disco por partición (df -h)
  disk_inodes        — uso de inodos por partición
  dir_size           — tamaño de un directorio (du -sh)
  lsblk_info         — dispositivos de bloque y particiones

Tools de usuarios y grupos:
  user_list          — lista usuarios del sistema
  user_info          — información de un usuario (grupos, shell, home)
  group_list         — lista grupos del sistema
  who_logged         — usuarios con sesión activa (who / w)

Tools de procesos y recursos:
  ps_list            — procesos activos con CPU/RAM filtrable
  top_snapshot       — snapshot instantáneo de CPU y memoria (sin interactividad)
  kill_process       — enviar señal a un proceso (TERM por defecto)

Tools de firewall:
  fw_status          — estado del firewall (ufw o firewalld según SO)
  fw_rules           — reglas activas del firewall
  fw_allow           — añadir regla de entrada
  fw_deny            — bloquear regla de entrada

Tools de sistema:
  sys_info           — resumen del sistema: SO, kernel, RAM, CPU, uptime
  sys_updates        — paquetes con actualizaciones de seguridad disponibles
  sys_logs           — últimas líneas de logs del sistema (journalctl / syslog)
  env_vars           — variables de entorno del sistema (filtradas, sin secretos)
  cron_list          — crontabs del usuario actual y del sistema
"""
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


# ── Detección de SO ───────────────────────────────────────────────────────────

def _detect_os() -> dict[str, str]:
    """Detecta la familia y versión del sistema operativo."""
    info: dict[str, str] = {
        "family":  "unknown",
        "distro":  platform.system(),
        "version": platform.release(),
        "pkg_mgr": "none",
    }
    try:
        os_release = Path("/etc/os-release").read_text()
        fields = dict(
            line.split("=", 1)
            for line in os_release.splitlines()
            if "=" in line
        )
        name = fields.get("ID", "").strip('"').lower()
        name_like = fields.get("ID_LIKE", "").strip('"').lower()
        info["distro"]  = fields.get("PRETTY_NAME", name).strip('"')
        info["version"] = fields.get("VERSION_ID", "").strip('"')
        if "debian" in name or "ubuntu" in name or "debian" in name_like:
            info["family"]  = "debian"
            info["pkg_mgr"] = "apt"
        elif any(k in name or k in name_like for k in ("fedora", "rhel", "centos", "rocky", "almalinux")):
            info["family"]  = "redhat"
            info["pkg_mgr"] = "dnf" if _which("dnf") else "yum"
        elif "arch" in name or "arch" in name_like:
            info["family"]  = "arch"
            info["pkg_mgr"] = "pacman"
    except Exception:
        pass
    return info


_OS = _detect_os()
_PKG = _OS["pkg_mgr"]


def _which(cmd: str) -> bool:
    import shutil
    return bool(shutil.which(cmd))


# ── Protocolo MCP (stdio, newline JSON) ───────────────────────────────────────

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


# ── Helper de ejecución de comandos ──────────────────────────────────────────

def _run(
    cmd: list[str],
    timeout: int = 30,
    cwd: str | None = None,
    env: dict | None = None,
    input_text: str | None = None,
) -> tuple[int, str]:
    """Ejecuta un comando y devuelve (returncode, stdout+stderr combinado)."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if input_text else subprocess.DEVNULL,
            text=True,
            cwd=cwd or os.getcwd(),
            env=env,
            start_new_session=True,
        )
        try:
            out, _ = proc.communicate(input=input_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            proc.communicate()
            return -1, f"Timeout ({timeout}s)"
        return proc.returncode, (out or "").strip()
    except FileNotFoundError:
        return -2, f"Comando no encontrado: {cmd[0]}"
    except Exception as exc:
        return -3, str(exc)


def _require(cmd: str) -> str | None:
    """Devuelve error string si el comando no está disponible."""
    if not _which(cmd):
        return f"Error: '{cmd}' no está instalado en este sistema."
    return None


# ── Tools de servicios (systemd) ──────────────────────────────────────────────

def _tool_systemctl_status(args: dict) -> str:
    services = args.get("services", args.get("service", ""))
    if not services:
        return "Error: 'services' requerido (nombre o lista separada por comas)."
    if err := _require("systemctl"):
        return err
    svc_list = [s.strip() for s in services.split(",") if s.strip()]
    parts = []
    for svc in svc_list[:10]:
        rc, out = _run(["systemctl", "status", "--no-pager", "-l", svc])
        parts.append(f"### {svc}\n{out or '(sin salida)'}")
    return "\n\n".join(parts)


def _tool_systemctl_action(args: dict) -> str:
    service = args.get("service", "")
    action  = args.get("action", "status").lower()
    valid   = ("start", "stop", "restart", "reload", "enable", "disable",
               "mask", "unmask", "is-active", "is-enabled")
    if not service:
        return "Error: 'service' requerido."
    if action not in valid:
        return f"Error: acción inválida '{action}'. Válidas: {', '.join(valid)}"
    if err := _require("systemctl"):
        return err
    rc, out = _run(["systemctl", "--no-pager", action, service])
    status = "OK" if rc == 0 else f"rc={rc}"
    return f"systemctl {action} {service}: {status}\n{out}".strip()


def _tool_journalctl(args: dict) -> str:
    service = args.get("service", "")
    lines   = min(int(args.get("lines", 50)), 500)
    since   = args.get("since", "")       # ej. "1 hour ago", "2024-01-01"
    level   = args.get("level", "")       # err, warning, info, debug
    if err := _require("journalctl"):
        return err
    cmd = ["journalctl", "--no-pager", f"-n{lines}"]
    if service:
        cmd += ["-u", service]
    if since:
        cmd += ["--since", since]
    if level:
        cmd += [f"-p{level}"]
    rc, out = _run(cmd, timeout=15)
    prefix = f"journalctl {'-u ' + service if service else ''} (últimas {lines} líneas):\n"
    return prefix + (out or "(sin logs)")


# ── Tools APT (Debian/Ubuntu) ─────────────────────────────────────────────────

def _tool_apt_update(args: dict) -> str:
    if err := _require("apt-get"):
        return err
    rc, out = _run(["apt-get", "update", "-q"], timeout=120)
    return f"apt update: {'OK' if rc == 0 else 'ERROR rc=' + str(rc)}\n{out[:3000]}"


def _tool_apt_upgrade(args: dict) -> str:
    dry_run = bool(args.get("dry_run", True))
    if err := _require("apt-get"):
        return err
    cmd = ["apt-get", "upgrade", "-y", "--dry-run"] if dry_run else ["apt-get", "upgrade", "-y"]
    rc, out = _run(cmd, timeout=120)
    suffix = " (simulación)" if dry_run else ""
    return f"apt upgrade{suffix}: {'OK' if rc == 0 else 'rc=' + str(rc)}\n{out[:4000]}"


def _tool_apt_install(args: dict) -> str:
    packages = args.get("packages", "")
    if not packages:
        return "Error: 'packages' requerido (nombre o lista separada por espacios)."
    if err := _require("apt-get"):
        return err
    pkgs = packages.split()
    rc, out = _run(["apt-get", "install", "-y"] + pkgs, timeout=180)
    return f"apt install {packages}: {'OK' if rc == 0 else 'ERROR rc=' + str(rc)}\n{out[:4000]}"


def _tool_apt_remove(args: dict) -> str:
    packages = args.get("packages", "")
    if not packages:
        return "Error: 'packages' requerido."
    purge = bool(args.get("purge", False))
    if err := _require("apt-get"):
        return err
    action = "purge" if purge else "remove"
    rc, out = _run(["apt-get", action, "-y"] + packages.split(), timeout=120)
    return f"apt {action} {packages}: {'OK' if rc == 0 else 'ERROR rc=' + str(rc)}\n{out[:3000]}"


def _tool_apt_search(args: dict) -> str:
    query = args.get("query", "")
    if not query:
        return "Error: 'query' requerido."
    if err := _require("apt-cache"):
        return err
    rc, out = _run(["apt-cache", "search", query])
    lines = out.splitlines()[:60]
    return f"apt search '{query}' ({len(out.splitlines())} resultados, mostrando 60):\n" + "\n".join(lines)


def _tool_apt_info(args: dict) -> str:
    package = args.get("package", "")
    if not package:
        return "Error: 'package' requerido."
    if err := _require("apt-cache"):
        return err
    rc, out = _run(["apt-cache", "show", package])
    return out[:3000] if out else f"Paquete '{package}' no encontrado."


def _tool_apt_list_installed(args: dict) -> str:
    filter_str = args.get("filter", "")
    if err := _require("dpkg"):
        return err
    rc, out = _run(["dpkg", "-l"])
    lines = [ln for ln in out.splitlines() if ln.startswith("ii")]
    if filter_str:
        lines = [ln for ln in lines if filter_str.lower() in ln.lower()]
    result = "\n".join(lines[:200])
    total = len(lines)
    return f"Paquetes instalados ({total}{' filtrados' if filter_str else ''}):\n{result}"


# ── Tools DNF/RPM (RedHat/Fedora) ────────────────────────────────────────────

def _tool_dnf_update(args: dict) -> str:
    bin_ = "dnf" if _which("dnf") else "yum"
    if not _which(bin_):
        return "Error: ni dnf ni yum disponibles."
    rc, out = _run([bin_, "check-update"], timeout=60)
    # check-update devuelve 100 cuando hay actualizaciones — no es error
    return f"{bin_} check-update:\n{out[:4000]}"


def _tool_dnf_install(args: dict) -> str:
    packages = args.get("packages", "")
    if not packages:
        return "Error: 'packages' requerido."
    bin_ = "dnf" if _which("dnf") else "yum"
    rc, out = _run([bin_, "install", "-y"] + packages.split(), timeout=180)
    return f"{bin_} install {packages}: {'OK' if rc == 0 else 'ERROR rc=' + str(rc)}\n{out[:4000]}"


def _tool_dnf_remove(args: dict) -> str:
    packages = args.get("packages", "")
    if not packages:
        return "Error: 'packages' requerido."
    bin_ = "dnf" if _which("dnf") else "yum"
    rc, out = _run([bin_, "remove", "-y"] + packages.split(), timeout=120)
    return f"{bin_} remove {packages}: {'OK' if rc == 0 else 'ERROR rc=' + str(rc)}\n{out[:3000]}"


def _tool_dnf_search(args: dict) -> str:
    query = args.get("query", "")
    if not query:
        return "Error: 'query' requerido."
    bin_ = "dnf" if _which("dnf") else "yum"
    rc, out = _run([bin_, "search", query])
    return out[:3000] or f"Sin resultados para '{query}'."


def _tool_dnf_info(args: dict) -> str:
    package = args.get("package", "")
    if not package:
        return "Error: 'package' requerido."
    bin_ = "dnf" if _which("dnf") else "yum"
    rc, out = _run([bin_, "info", package])
    return out[:3000] or f"Paquete '{package}' no encontrado."


def _tool_rpm_query(args: dict) -> str:
    package = args.get("package", "")
    query   = args.get("query", "info")  # info | files | changelog | requires | provides
    if not package:
        return "Error: 'package' requerido."
    if err := _require("rpm"):
        return err
    flags = {
        "info":      ["-qi"],
        "files":     ["-ql"],
        "changelog": ["--changelog"],
        "requires":  ["-qR"],
        "provides":  ["-q", "--provides"],
    }.get(query, ["-qi"])
    rc, out = _run(["rpm"] + flags + [package])
    return out[:3000] or f"Paquete '{package}' no encontrado."


# ── Tools de red ──────────────────────────────────────────────────────────────

def _tool_net_interfaces(args: dict) -> str:
    if _which("ip"):
        rc, out = _run(["ip", "-brief", "address"])
        if rc == 0:
            return f"Interfaces de red:\n{out}"
    if _which("ifconfig"):
        rc, out = _run(["ifconfig", "-a"])
        return f"Interfaces de red:\n{out[:3000]}"
    return "Error: ni 'ip' ni 'ifconfig' disponibles."


def _tool_net_connections(args: dict) -> str:
    filter_str = args.get("filter", "")
    if not _which("ss"):
        if not _which("netstat"):
            return "Error: ni 'ss' ni 'netstat' disponibles."
        rc, out = _run(["netstat", "-tulpn"])
    else:
        rc, out = _run(["ss", "-tulpn"])
    if filter_str:
        lines = [ln for ln in out.splitlines() if filter_str in ln or ln.startswith("State")]
        out = "\n".join(lines)
    return f"Conexiones activas:\n{out[:3000]}"


def _tool_net_ping(args: dict) -> str:
    host  = args.get("host", "")
    count = min(int(args.get("count", 4)), 10)
    if not host:
        return "Error: 'host' requerido."
    if err := _require("ping"):
        return err
    rc, out = _run(["ping", "-c", str(count), host], timeout=20)
    return out[:2000]


def _tool_net_dns(args: dict) -> str:
    host    = args.get("host", "")
    record  = args.get("record", "A")
    if not host:
        return "Error: 'host' requerido."
    if _which("dig"):
        rc, out = _run(["dig", "+short", host, record])
        return f"DNS {record} para {host}:\n{out or '(sin respuesta)'}"
    if _which("host"):
        rc, out = _run(["host", host])
        return out[:1000]
    return "Error: ni 'dig' ni 'host' disponibles."


# ── Tools de disco ────────────────────────────────────────────────────────────

def _tool_disk_usage(args: dict) -> str:
    path = args.get("path", "")
    cmd = ["df", "-h"]
    if path:
        cmd.append(path)
    rc, out = _run(cmd)
    return out[:2000]


def _tool_disk_inodes(args: dict) -> str:
    rc, out = _run(["df", "-i"])
    return out[:2000]


def _tool_dir_size(args: dict) -> str:
    path = args.get("path", ".")
    depth = min(int(args.get("depth", 1)), 5)
    if err := _require("du"):
        return err
    rc, out = _run(["du", "-sh", f"--max-depth={depth}", path], timeout=30)
    return out[:2000]


def _tool_lsblk_info(args: dict) -> str:
    if err := _require("lsblk"):
        return err
    rc, out = _run(["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,LABEL,UUID"])
    return out[:2000]


# ── Tools de usuarios ─────────────────────────────────────────────────────────

def _tool_user_list(args: dict) -> str:
    try:
        lines = Path("/etc/passwd").read_text().splitlines()
        users = []
        for ln in lines:
            parts = ln.split(":")
            if len(parts) >= 7:
                uid = int(parts[2])
                if uid >= 1000 or args.get("all", False):
                    users.append(f"  {parts[0]:<20} uid={uid:<6} home={parts[5]}  shell={parts[6]}")
        return "Usuarios del sistema:\n" + "\n".join(users)
    except Exception as exc:
        return f"Error leyendo /etc/passwd: {exc}"


def _tool_user_info(args: dict) -> str:
    username = args.get("username", "")
    if not username:
        return "Error: 'username' requerido."
    rc, out = _run(["id", username])
    if rc != 0:
        return f"Usuario '{username}' no encontrado."
    lines = [f"id: {out}"]
    # grupos
    rc2, groups = _run(["groups", username])
    if rc2 == 0:
        lines.append(f"grupos: {groups}")
    # entrada passwd
    try:
        for ln in Path("/etc/passwd").read_text().splitlines():
            if ln.startswith(username + ":"):
                parts = ln.split(":")
                lines.append(f"home: {parts[5]}  shell: {parts[6]}")
                break
    except Exception:
        pass
    return "\n".join(lines)


def _tool_group_list(args: dict) -> str:
    try:
        lines = Path("/etc/group").read_text().splitlines()
        groups = []
        for ln in lines:
            parts = ln.split(":")
            if len(parts) >= 4:
                groups.append(f"  {parts[0]:<25} gid={parts[2]:<6} miembros={parts[3]}")
        return "Grupos del sistema:\n" + "\n".join(groups[:80])
    except Exception as exc:
        return f"Error leyendo /etc/group: {exc}"


def _tool_who_logged(args: dict) -> str:
    rc, out = _run(["w"])
    if rc != 0:
        rc, out = _run(["who"])
    return f"Usuarios con sesión activa:\n{out}"


# ── Tools de procesos ─────────────────────────────────────────────────────────

def _tool_ps_list(args: dict) -> str:
    filter_str = args.get("filter", "")
    sort_by    = args.get("sort", "cpu")   # cpu | mem | pid | name
    limit      = min(int(args.get("limit", 30)), 100)
    sort_flag  = {
        "cpu":  "-%cpu",
        "mem":  "-%mem",
        "pid":  "pid",
        "name": "comm",
    }.get(sort_by, "-%cpu")
    rc, out = _run(["ps", "axo", "pid,user,%cpu,%mem,vsz,rss,stat,start,comm", f"--sort={sort_flag}"])
    lines = out.splitlines()
    if filter_str:
        header = lines[0] if lines else ""
        lines  = [header] + [ln for ln in lines[1:] if filter_str.lower() in ln.lower()]
    return "\n".join(lines[:limit + 1])


def _tool_top_snapshot(args: dict) -> str:
    if _which("top"):
        rc, out = _run(["top", "-b", "-n1", "-o", "%CPU"])
        lines = out.splitlines()[:30]
        return "\n".join(lines)
    rc, out = _run(["ps", "axo", "pid,user,%cpu,%mem,comm", "--sort=-%cpu"])
    return out.splitlines()[0] + "\n" + "\n".join(out.splitlines()[1:16])


def _tool_kill_process(args: dict) -> str:
    pid    = args.get("pid", "")
    signal = args.get("signal", "TERM").upper().lstrip("-")
    if not pid:
        return "Error: 'pid' requerido."
    try:
        pid_int = int(pid)
    except ValueError:
        return f"Error: PID inválido '{pid}'."
    if pid_int <= 1:
        return "Error: PID demasiado bajo — operación bloqueada por seguridad."
    if err := _require("kill"):
        return err
    rc, out = _run(["kill", f"-{signal}", str(pid_int)])
    return f"kill -{signal} {pid_int}: {'OK' if rc == 0 else 'ERROR rc=' + str(rc)}\n{out}"


# ── Tools de firewall ─────────────────────────────────────────────────────────

def _fw_backend() -> str:
    if _which("ufw"):
        return "ufw"
    if _which("firewall-cmd"):
        return "firewalld"
    return "none"


def _tool_fw_status(args: dict) -> str:
    backend = _fw_backend()
    if backend == "ufw":
        rc, out = _run(["ufw", "status", "verbose"])
    elif backend == "firewalld":
        rc, out = _run(["firewall-cmd", "--state"])
        if rc == 0:
            rc2, out2 = _run(["firewall-cmd", "--list-all"])
            out = out + "\n" + out2
    else:
        return "Error: ni ufw ni firewalld disponibles."
    return out[:3000]


def _tool_fw_rules(args: dict) -> str:
    backend = _fw_backend()
    if backend == "ufw":
        rc, out = _run(["ufw", "status", "numbered"])
    elif backend == "firewalld":
        rc, out = _run(["firewall-cmd", "--list-all-zones"])
    else:
        return "Error: ni ufw ni firewalld disponibles."
    return out[:3000]


def _tool_fw_allow(args: dict) -> str:
    port    = args.get("port", "")
    proto   = args.get("proto", "tcp").lower()
    from_ip = args.get("from", "any")
    if not port:
        return "Error: 'port' requerido."
    backend = _fw_backend()
    if backend == "ufw":
        rule = f"{port}/{proto}" if from_ip == "any" else f"from {from_ip} to any port {port} proto {proto}"
        rc, out = _run(["ufw", "allow"] + rule.split())
    elif backend == "firewalld":
        rc, out = _run(["firewall-cmd", "--permanent", f"--add-port={port}/{proto}"])
        if rc == 0:
            _run(["firewall-cmd", "--reload"])
    else:
        return "Error: ni ufw ni firewalld disponibles."
    return f"Regla allow {port}/{proto}: {'OK' if rc == 0 else 'ERROR rc=' + str(rc)}\n{out}"


def _tool_fw_deny(args: dict) -> str:
    port  = args.get("port", "")
    proto = args.get("proto", "tcp").lower()
    if not port:
        return "Error: 'port' requerido."
    backend = _fw_backend()
    if backend == "ufw":
        rc, out = _run(["ufw", "deny", f"{port}/{proto}"])
    elif backend == "firewalld":
        rc, out = _run(["firewall-cmd", "--permanent", f"--remove-port={port}/{proto}"])
        if rc == 0:
            _run(["firewall-cmd", "--reload"])
    else:
        return "Error: ni ufw ni firewalld disponibles."
    return f"Regla deny {port}/{proto}: {'OK' if rc == 0 else 'ERROR rc=' + str(rc)}\n{out}"


# ── Tools de sistema ──────────────────────────────────────────────────────────

def _tool_sys_info(args: dict) -> str:
    lines = [
        f"SO:      {_OS['distro']}",
        f"Kernel:  {platform.release()}  ({platform.machine()})",
        f"Host:    {platform.node()}",
        f"Python:  {platform.python_version()}",
    ]
    try:
        import psutil
        cpu  = psutil.cpu_percent(interval=0.5)
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        lines += [
            f"CPU:     {cpu:.1f}%  ({psutil.cpu_count(logical=False)} físicos / {psutil.cpu_count()} lógicos)",
            f"RAM:     {mem.used // 1024**2} MB / {mem.total // 1024**2} MB  ({mem.percent:.1f}%)",
            f"Disco (/): {disk.used // 1024**3} GB / {disk.total // 1024**3} GB  ({disk.percent:.1f}%)",
        ]
    except ImportError:
        rc, out = _run(["free", "-h"])
        if rc == 0:
            lines.append(f"RAM:\n{out}")
    try:
        uptime_s = float(Path("/proc/uptime").read_text().split()[0])
        h, rem = divmod(int(uptime_s), 3600)
        m, s   = divmod(rem, 60)
        lines.append(f"Uptime:  {h}h {m}m {s}s")
    except Exception:
        pass
    return "\n".join(lines)


def _tool_sys_updates(args: dict) -> str:
    if _PKG == "apt":
        if not _which("apt-get"):
            return "Error: apt-get no disponible."
        rc, out = _run(["apt-get", "--just-print", "upgrade"], timeout=60)
        lines = [ln for ln in out.splitlines() if "Inst " in ln]
        security = [ln for ln in lines if "security" in ln.lower()]
        return (
            f"Paquetes con actualizaciones: {len(lines)}\n"
            f"De seguridad: {len(security)}\n\n"
            + "\n".join(security[:30] or lines[:30])
        )
    if _PKG in ("dnf", "yum"):
        bin_ = _PKG
        rc, out = _run([bin_, "check-update", "--security"], timeout=60)
        return out[:3000] or "Sin actualizaciones de seguridad."
    return f"Sistema de paquetes '{_PKG}' no soportado para este check."


def _tool_sys_logs(args: dict) -> str:
    lines   = min(int(args.get("lines", 50)), 300)
    level   = args.get("level", "warning")   # emerg,alert,crit,err,warning,notice,info,debug
    since   = args.get("since", "24h")
    if _which("journalctl"):
        cmd = ["journalctl", "--no-pager", f"-n{lines}", f"-p{level}", f"--since=-{since}"]
        rc, out = _run(cmd, timeout=15)
        return out or "(sin logs en el período)"
    for log_file in ("/var/log/syslog", "/var/log/messages"):
        p = Path(log_file)
        if p.exists():
            try:
                log_lines = p.read_text(errors="replace").splitlines()[-lines:]
                return "\n".join(log_lines)
            except Exception:
                pass
    return "Error: ni journalctl ni logs de syslog disponibles."


def _tool_env_vars(args: dict) -> str:
    prefix = args.get("prefix", "").upper()
    secret_patterns = re.compile(
        r"(?i)(password|passwd|secret|token|key|api_key|private|credential)",
    )
    lines = []
    for k, v in sorted(os.environ.items()):
        if prefix and not k.startswith(prefix):
            continue
        if secret_patterns.search(k):
            v = "***"
        lines.append(f"  {k}={v}")
    return f"Variables de entorno ({len(lines)} encontradas):\n" + "\n".join(lines[:100])


def _tool_cron_list(args: dict) -> str:
    user = args.get("user", os.getenv("USER", ""))
    parts = []
    # crontab del usuario
    if _which("crontab"):
        rc, out = _run(["crontab", "-l", "-u", user] if user else ["crontab", "-l"])
        if rc == 0 and out:
            parts.append(f"## crontab de {user or 'usuario actual'}\n{out}")
    # cron.d del sistema
    for cron_dir in ("/etc/cron.d", "/etc/cron.daily", "/etc/cron.weekly", "/etc/cron.monthly"):
        p = Path(cron_dir)
        if p.is_dir():
            entries = sorted(p.iterdir())
            if entries:
                names = ", ".join(e.name for e in entries)
                parts.append(f"## {cron_dir}/\n{names}")
    return "\n\n".join(parts) if parts else "No se encontraron crontabs."


# ── Resources ────────────────────────────────────────────────────────────────

_RESOURCES = [
    {
        "uri":         "system://info",
        "name":        "System Info",
        "description": "Resumen del sistema: SO, kernel, CPU, RAM, disco y uptime.",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "system://services/active",
        "name":        "Active Services",
        "description": "Lista de servicios systemd activos (running).",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "system://processes/top",
        "name":        "Top Processes",
        "description": "Top 20 procesos por uso de CPU en este momento.",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "system://disk",
        "name":        "Disk Usage",
        "description": "Uso de disco por partición (df -h).",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "system://network/interfaces",
        "name":        "Network Interfaces",
        "description": "Interfaces de red con IP y estado.",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "system://logs/recent",
        "name":        "Recent Logs",
        "description": "Últimas 50 entradas de warning o superior del log del sistema.",
        "mimeType":    "text/plain",
    },
]


def _read_resource(uri: str) -> str:
    """Devuelve el contenido de un resource por URI."""
    if uri == "system://info":
        return _tool_sys_info({})
    if uri == "system://services/active":
        if not _which("systemctl"):
            return "systemctl no disponible."
        rc, out = _run(["systemctl", "list-units", "--type=service",
                        "--state=running", "--no-pager", "--no-legend"])
        lines = out.splitlines()[:60]
        return f"Servicios activos ({len(lines)}):\n" + "\n".join(lines)
    if uri == "system://processes/top":
        return _tool_ps_list({"limit": 20, "sort": "cpu"})
    if uri == "system://disk":
        return _tool_disk_usage({})
    if uri == "system://network/interfaces":
        return _tool_net_interfaces({})
    if uri == "system://logs/recent":
        return _tool_sys_logs({"lines": 50, "level": "warning", "since": "24h"})
    return f"Resource desconocido: {uri}"


# ── Prompts ───────────────────────────────────────────────────────────────────

_PROMPTS = [
    {
        "name":        "diagnose_service",
        "description": "Diagnóstico completo de un servicio systemd: estado, logs recientes y dependencias.",
        "arguments": [
            {"name": "service", "description": "Nombre del servicio (ej. nginx, postgresql)", "required": True},
        ],
    },
    {
        "name":        "audit_system",
        "description": "Auditoría de seguridad básica: usuarios, puertos abiertos, servicios, firewall y actualizaciones.",
        "arguments": [],
    },
    {
        "name":        "investigate_disk",
        "description": "Investigación de uso de disco: particiones llenas, directorios grandes y ficheros recientes.",
        "arguments": [
            {"name": "path", "description": "Ruta a investigar (default: /)", "required": False},
        ],
    },
    {
        "name":        "debug_network",
        "description": "Diagnóstico de red: interfaces, conexiones activas, DNS y conectividad básica.",
        "arguments": [
            {"name": "host", "description": "Host a probar (opcional)", "required": False},
        ],
    },
    {
        "name":        "performance_snapshot",
        "description": "Snapshot de rendimiento: CPU, memoria, procesos pesados y carga del sistema.",
        "arguments": [],
    },
]


def _get_prompt(name: str, arguments: dict) -> dict:
    """Devuelve el contenido expandido de un prompt."""
    if name == "diagnose_service":
        service = arguments.get("service", "<servicio>")
        text = (
            f"Realiza un diagnóstico completo del servicio **{service}** en este sistema.\n\n"
            f"Pasos a seguir:\n"
            f"1. Comprueba el estado con `systemctl_status` para `{service}`\n"
            f"2. Revisa los últimos logs con `journalctl` (service={service}, lines=100, level=warning)\n"
            f"3. Verifica si está habilitado (`is-enabled`) y en auto-arranque\n"
            f"4. Si hay errores, analiza la causa raíz en los logs\n"
            f"5. Propón acciones correctivas concretas\n\n"
            f"Informa sobre: estado actual, errores encontrados, causa probable y solución recomendada."
        )
        return {
            "description": f"Diagnóstico completo del servicio {service}",
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }
    if name == "audit_system":
        text = (
            "Realiza una auditoría de seguridad básica de este sistema.\n\n"
            "Revisa en este orden:\n"
            "1. **Usuarios**: `user_list` (usuarios con UID ≥ 1000), busca cuentas sospechosas\n"
            "2. **Sesiones activas**: `who_logged` — ¿hay sesiones inesperadas?\n"
            "3. **Puertos abiertos**: `net_connections` — verifica qué servicios escuchan en qué puertos\n"
            "4. **Firewall**: `fw_status` y `fw_rules` — ¿está activo? ¿las reglas son correctas?\n"
            "5. **Actualizaciones de seguridad**: `sys_updates` — ¿hay parches críticos pendientes?\n"
            "6. **Servicios activos**: lee el resource `system://services/active`\n"
            "7. **Cron jobs**: `cron_list` — ¿hay tareas programadas sospechosas?\n\n"
            "Clasifica los hallazgos por severidad: crítico, advertencia, informativo."
        )
        return {
            "description": "Auditoría de seguridad básica del sistema",
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }
    if name == "investigate_disk":
        path = arguments.get("path", "/")
        text = (
            f"Investiga el uso de disco en `{path}` y encuentra qué está consumiendo espacio.\n\n"
            f"Pasos:\n"
            f"1. Uso global: `disk_usage` para ver el estado de todas las particiones\n"
            f"2. Inodos: `disk_inodes` — ¿alguna partición tiene inodos agotados?\n"
            f"3. Dispositivos: `lsblk_info` — muestra la estructura de discos y particiones\n"
            f"4. Directorio más grande: `dir_size` con path={path} y depth=2 para desglose\n"
            f"5. Si hay espacio crítico (>90%), identifica los directorios más grandes recursivamente\n\n"
            f"Informa sobre: partición más llena, directorio(s) responsables y recomendación de limpieza."
        )
        return {
            "description": f"Investigación de uso de disco en {path}",
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }
    if name == "debug_network":
        host = arguments.get("host", "")
        host_step = (f"5. Conectividad: `net_ping` hacia `{host}` y `net_dns` para resolver su IP\n"
                     if host else "")
        text = (
            "Diagnostica el estado de la red en este sistema.\n\n"
            "Pasos:\n"
            "1. Interfaces: `net_interfaces` — verifica qué interfaces están UP y sus IPs\n"
            "2. Conexiones activas: `net_connections` — lista puertos en escucha y conexiones establecidas\n"
            "3. DNS: `net_dns` con host=google.com para verificar resolución DNS básica\n"
            "4. Conectividad externa: `net_ping` con host=8.8.8.8 para verificar routing\n"
            + host_step +
            "5. Firewall: `fw_status` — ¿podría estar bloqueando conexiones?\n\n"
            "Informa sobre: interfaces activas, servicios escuchando, conectividad y posibles bloqueos."
        )
        return {
            "description": "Diagnóstico de red del sistema",
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }
    if name == "performance_snapshot":
        text = (
            "Analiza el rendimiento actual del sistema y detecta posibles cuellos de botella.\n\n"
            "Pasos:\n"
            "1. Resumen general: lee el resource `system://info` (CPU, RAM, uptime)\n"
            "2. Procesos pesados: `ps_list` ordenado por CPU (sort=cpu, limit=15)\n"
            "3. Procesos por memoria: `ps_list` ordenado por memoria (sort=mem, limit=10)\n"
            "4. Snapshot instantáneo: `top_snapshot` para ver la carga en este momento\n"
            "5. Disco: `disk_usage` — ¿alguna partición al límite?\n"
            "6. Logs recientes: lee `system://logs/recent` buscando errores de OOM o I/O\n\n"
            "Informa sobre: proceso(s) dominante(s), uso de memoria, carga de disco y recomendaciones."
        )
        return {
            "description": "Snapshot de rendimiento del sistema",
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }
    return {}


# ── Registro de tools ─────────────────────────────────────────────────────────

# Tools que solo se exponen si el gestor de paquetes está disponible
_TOOLS_DEBIAN = [
    {
        "name": "apt_update",
        "description": "Actualiza la lista de paquetes disponibles (apt update).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "apt_upgrade",
        "description": "Muestra paquetes actualizables. Con dry_run=false ejecuta el upgrade real.",
        "inputSchema": {"type": "object", "properties": {
            "dry_run": {"type": "boolean", "description": "Simular sin instalar (default: true)"},
        }},
    },
    {
        "name": "apt_install",
        "description": "Instala uno o varios paquetes con apt-get install.",
        "inputSchema": {"type": "object", "properties": {
            "packages": {"type": "string", "description": "Nombres de paquetes separados por espacios"},
        }, "required": ["packages"]},
    },
    {
        "name": "apt_remove",
        "description": "Elimina paquetes (remove o purge).",
        "inputSchema": {"type": "object", "properties": {
            "packages": {"type": "string", "description": "Nombres separados por espacios"},
            "purge":    {"type": "boolean", "description": "Eliminar también ficheros de configuración (default: false)"},
        }, "required": ["packages"]},
    },
    {
        "name": "apt_search",
        "description": "Busca paquetes por nombre o descripción (apt-cache search).",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Términos de búsqueda"},
        }, "required": ["query"]},
    },
    {
        "name": "apt_info",
        "description": "Información detallada de un paquete (apt-cache show).",
        "inputSchema": {"type": "object", "properties": {
            "package": {"type": "string", "description": "Nombre del paquete"},
        }, "required": ["package"]},
    },
    {
        "name": "apt_list_installed",
        "description": "Lista todos los paquetes instalados con versión.",
        "inputSchema": {"type": "object", "properties": {
            "filter": {"type": "string", "description": "Filtrar por nombre (opcional)"},
        }},
    },
]

_TOOLS_REDHAT = [
    {
        "name": "dnf_update",
        "description": "Muestra actualizaciones disponibles (dnf/yum check-update).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dnf_install",
        "description": "Instala paquetes con dnf/yum.",
        "inputSchema": {"type": "object", "properties": {
            "packages": {"type": "string", "description": "Nombres de paquetes"},
        }, "required": ["packages"]},
    },
    {
        "name": "dnf_remove",
        "description": "Elimina paquetes con dnf/yum.",
        "inputSchema": {"type": "object", "properties": {
            "packages": {"type": "string", "description": "Nombres de paquetes"},
        }, "required": ["packages"]},
    },
    {
        "name": "dnf_search",
        "description": "Busca paquetes por nombre (dnf/yum search).",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Términos de búsqueda"},
        }, "required": ["query"]},
    },
    {
        "name": "dnf_info",
        "description": "Información detallada de un paquete (dnf/yum info).",
        "inputSchema": {"type": "object", "properties": {
            "package": {"type": "string", "description": "Nombre del paquete"},
        }, "required": ["package"]},
    },
    {
        "name": "rpm_query",
        "description": "Consulta la base de datos RPM: ficheros, versión, changelog, dependencias.",
        "inputSchema": {"type": "object", "properties": {
            "package": {"type": "string", "description": "Nombre del paquete"},
            "query":   {"type": "string", "description": "'info' (default) | 'files' | 'changelog' | 'requires' | 'provides'"},
        }, "required": ["package"]},
    },
]

_TOOLS_COMMON = [
    # Servicios
    {
        "name": "systemctl_status",
        "description": "Estado de uno o varios servicios systemd.",
        "inputSchema": {"type": "object", "properties": {
            "services": {"type": "string", "description": "Nombre o lista separada por comas (ej. 'nginx,postgresql')"},
        }, "required": ["services"]},
    },
    {
        "name": "systemctl_action",
        "description": "Controla un servicio systemd: start, stop, restart, enable, disable, reload, is-active…",
        "inputSchema": {"type": "object", "properties": {
            "service": {"type": "string", "description": "Nombre del servicio"},
            "action":  {"type": "string", "description": "start | stop | restart | reload | enable | disable | mask | unmask | is-active | is-enabled"},
        }, "required": ["service", "action"]},
    },
    {
        "name": "journalctl",
        "description": "Logs del sistema o de un servicio (journalctl).",
        "inputSchema": {"type": "object", "properties": {
            "service": {"type": "string", "description": "Filtrar por servicio (vacío = logs del sistema)"},
            "lines":   {"type": "integer","description": "Número de líneas (default: 50, max 500)"},
            "since":   {"type": "string", "description": "Desde cuándo: '1 hour ago', '2024-01-01', etc."},
            "level":   {"type": "string", "description": "Nivel mínimo: err | warning | info | debug"},
        }},
    },
    # Red
    {
        "name": "net_interfaces",
        "description": "Lista interfaces de red con IP, MAC y estado.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "net_connections",
        "description": "Conexiones y puertos TCP/UDP activos (ss -tulpn).",
        "inputSchema": {"type": "object", "properties": {
            "filter": {"type": "string", "description": "Filtrar por puerto, IP o proceso"},
        }},
    },
    {
        "name": "net_ping",
        "description": "Ping a un host (máximo 10 paquetes).",
        "inputSchema": {"type": "object", "properties": {
            "host":  {"type": "string",  "description": "IP o nombre de host"},
            "count": {"type": "integer", "description": "Número de paquetes (default: 4, max 10)"},
        }, "required": ["host"]},
    },
    {
        "name": "net_dns",
        "description": "Resolución DNS con dig o host.",
        "inputSchema": {"type": "object", "properties": {
            "host":   {"type": "string", "description": "Nombre de host o dominio"},
            "record": {"type": "string", "description": "Tipo de registro: A (default), AAAA, MX, NS, TXT, CNAME"},
        }, "required": ["host"]},
    },
    # Disco
    {
        "name": "disk_usage",
        "description": "Uso del disco por partición (df -h).",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Ruta específica (vacío = todas las particiones)"},
        }},
    },
    {
        "name": "disk_inodes",
        "description": "Uso de inodos por partición (df -i).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dir_size",
        "description": "Tamaño de un directorio (du -sh).",
        "inputSchema": {"type": "object", "properties": {
            "path":  {"type": "string",  "description": "Ruta del directorio (default: '.')"},
            "depth": {"type": "integer", "description": "Profundidad de desglose (default: 1, max 5)"},
        }},
    },
    {
        "name": "lsblk_info",
        "description": "Dispositivos de bloque, particiones y sistema de ficheros (lsblk).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # Usuarios
    {
        "name": "user_list",
        "description": "Lista usuarios del sistema (por defecto solo UID ≥ 1000).",
        "inputSchema": {"type": "object", "properties": {
            "all": {"type": "boolean", "description": "Incluir usuarios del sistema (UID < 1000) (default: false)"},
        }},
    },
    {
        "name": "user_info",
        "description": "Información de un usuario: UID, grupos, home, shell.",
        "inputSchema": {"type": "object", "properties": {
            "username": {"type": "string", "description": "Nombre del usuario"},
        }, "required": ["username"]},
    },
    {
        "name": "group_list",
        "description": "Lista grupos del sistema con miembros.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "who_logged",
        "description": "Usuarios con sesión activa en el sistema (who / w).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # Procesos
    {
        "name": "ps_list",
        "description": "Lista procesos activos con CPU, RAM y estado, ordenados y filtrables.",
        "inputSchema": {"type": "object", "properties": {
            "filter": {"type": "string",  "description": "Filtrar por nombre de proceso o usuario"},
            "sort":   {"type": "string",  "description": "Ordenar por: cpu (default) | mem | pid | name"},
            "limit":  {"type": "integer", "description": "Número máximo de procesos (default: 30, max 100)"},
        }},
    },
    {
        "name": "top_snapshot",
        "description": "Snapshot instantáneo de CPU y memoria (top -bn1 o ps).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "kill_process",
        "description": "Envía una señal a un proceso por PID. Usa TERM por defecto (SIGKILL si el proceso no responde).",
        "inputSchema": {"type": "object", "properties": {
            "pid":    {"type": "integer", "description": "PID del proceso"},
            "signal": {"type": "string",  "description": "Señal: TERM (default) | KILL | HUP | USR1 | USR2"},
        }, "required": ["pid"]},
    },
    # Firewall
    {
        "name": "fw_status",
        "description": "Estado del firewall (ufw en Debian/Ubuntu, firewalld en RedHat).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "fw_rules",
        "description": "Lista las reglas activas del firewall.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "fw_allow",
        "description": "Añade una regla de entrada al firewall.",
        "inputSchema": {"type": "object", "properties": {
            "port":  {"type": "string", "description": "Puerto o rango (ej. '80', '443', '8000:8010')"},
            "proto": {"type": "string", "description": "Protocolo: tcp (default) | udp"},
            "from":  {"type": "string", "description": "IP origen (default: 'any')"},
        }, "required": ["port"]},
    },
    {
        "name": "fw_deny",
        "description": "Bloquea un puerto en el firewall.",
        "inputSchema": {"type": "object", "properties": {
            "port":  {"type": "string", "description": "Puerto o rango"},
            "proto": {"type": "string", "description": "tcp (default) | udp"},
        }, "required": ["port"]},
    },
    # Sistema
    {
        "name": "sys_info",
        "description": "Resumen del sistema: SO, kernel, CPU, RAM, disco y uptime.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "sys_updates",
        "description": "Paquetes con actualizaciones disponibles, destacando las de seguridad.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "sys_logs",
        "description": "Últimas entradas del log del sistema (journalctl o syslog).",
        "inputSchema": {"type": "object", "properties": {
            "lines": {"type": "integer", "description": "Número de líneas (default: 50, max 300)"},
            "level": {"type": "string",  "description": "Nivel mínimo: warning (default) | err | crit | info | debug"},
            "since": {"type": "string",  "description": "Período: '24h' (default), '1h', '7d', etc."},
        }},
    },
    {
        "name": "env_vars",
        "description": "Variables de entorno del sistema, ocultando secretos automáticamente.",
        "inputSchema": {"type": "object", "properties": {
            "prefix": {"type": "string", "description": "Filtrar por prefijo (ej. 'PATH', 'PYTHON')"},
        }},
    },
    {
        "name": "cron_list",
        "description": "Lista los crontabs del usuario actual y entradas del sistema (/etc/cron.d).",
        "inputSchema": {"type": "object", "properties": {
            "user": {"type": "string", "description": "Usuario cuyo crontab listar (vacío = usuario actual)"},
        }},
    },
]

# Selección de tools según SO detectado
def _build_tools() -> list[dict]:
    tools = list(_TOOLS_COMMON)
    if _PKG == "apt":
        tools.extend(_TOOLS_DEBIAN)
    elif _PKG in ("dnf", "yum"):
        tools.extend(_TOOLS_REDHAT)
    return tools


_TOOLS = _build_tools()

_TOOL_FNS: dict[str, Any] = {
    # Servicios
    "systemctl_status":  _tool_systemctl_status,
    "systemctl_action":  _tool_systemctl_action,
    "journalctl":        _tool_journalctl,
    # Red
    "net_interfaces":    _tool_net_interfaces,
    "net_connections":   _tool_net_connections,
    "net_ping":          _tool_net_ping,
    "net_dns":           _tool_net_dns,
    # Disco
    "disk_usage":        _tool_disk_usage,
    "disk_inodes":       _tool_disk_inodes,
    "dir_size":          _tool_dir_size,
    "lsblk_info":        _tool_lsblk_info,
    # Usuarios
    "user_list":         _tool_user_list,
    "user_info":         _tool_user_info,
    "group_list":        _tool_group_list,
    "who_logged":        _tool_who_logged,
    # Procesos
    "ps_list":           _tool_ps_list,
    "top_snapshot":      _tool_top_snapshot,
    "kill_process":      _tool_kill_process,
    # Firewall
    "fw_status":         _tool_fw_status,
    "fw_rules":          _tool_fw_rules,
    "fw_allow":          _tool_fw_allow,
    "fw_deny":           _tool_fw_deny,
    # Sistema
    "sys_info":          _tool_sys_info,
    "sys_updates":       _tool_sys_updates,
    "sys_logs":          _tool_sys_logs,
    "env_vars":          _tool_env_vars,
    "cron_list":         _tool_cron_list,
    # APT
    "apt_update":        _tool_apt_update,
    "apt_upgrade":       _tool_apt_upgrade,
    "apt_install":       _tool_apt_install,
    "apt_remove":        _tool_apt_remove,
    "apt_search":        _tool_apt_search,
    "apt_info":          _tool_apt_info,
    "apt_list_installed": _tool_apt_list_installed,
    # DNF/RPM
    "dnf_update":        _tool_dnf_update,
    "dnf_install":       _tool_dnf_install,
    "dnf_remove":        _tool_dnf_remove,
    "dnf_search":        _tool_dnf_search,
    "dnf_info":          _tool_dnf_info,
    "rpm_query":         _tool_rpm_query,
}


# ── Dispatcher MCP ────────────────────────────────────────────────────────────

def _handle(req: dict) -> None:
    method   = req.get("method", "")
    params   = req.get("params", {})
    req_id   = req.get("id")

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name":    "system-assistant",
                "version": "1.1.0",
            },
            "capabilities": {
                "tools":     {},
                "resources": {"subscribe": False, "listChanged": False},
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
        try:
            text = _read_resource(uri)
            _ok(req_id, {
                "contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]
            })
        except Exception as exc:
            _err(req_id, -32603, f"Error leyendo resource '{uri}': {exc}")

    elif method == "prompts/list":
        _ok(req_id, {"prompts": _PROMPTS})

    elif method == "prompts/get":
        name      = params.get("name", "")
        arguments = params.get("arguments", {}) or {}
        result    = _get_prompt(name, arguments)
        if not result:
            _err(req_id, -32601, f"Prompt desconocido: {name}")
            return
        _ok(req_id, result)

    elif req_id is not None:
        _err(req_id, -32601, f"Método desconocido: {method}")


def main() -> None:
    sys.stderr.write(
        f"[system-assistant] MCP server v1.1 iniciado  "
        f"SO: {_OS['distro']}  pkg: {_PKG}  "
        f"tools: {len(_TOOLS)}  resources: {len(_RESOURCES)}  prompts: {len(_PROMPTS)}\n"
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
            sys.stderr.write(f"[system-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
