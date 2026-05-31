"""Plugin: vault
Vault de credenciales cifrado con AES-Fernet (PBKDF2-SHA256 · 200 000 iter).
Almacena contraseñas SSH, tokens Git, claves API y credenciales de bases de datos
para que el agente pueda acceder a sistemas remotos durante tareas de mantenimiento.

Fichero vault:  ~/.oocode/vault.enc   (permisos 600, propietario únicamente)
"""
import base64
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

NAME        = "vault"
DESCRIPTION = "Vault cifrado de credenciales: SSH, Git, DB, APIs y secretos genéricos"
VERSION     = "1.0.0"

_VAULT_FILE = Path.home() / ".oocode" / "vault.enc"

# Estado en memoria: nunca se persiste la clave ni los datos descifrados
_state: dict[str, Any] = {
    "key":        None,   # bytes (Fernet URL-safe base64) | None
    "data":       None,   # dict{"credentials": [...]}    | None
    "salt":       None,   # bytes | None  (leído del fichero al desbloquear)
    "agent_loop": None,   # referencia al AgentLoop para usar request_input del TUI
}

# Campos por tipo de credencial (campo → (label, es_secreto))
_TYPE_FIELDS: dict[str, list[tuple[str, str, bool]]] = {
    "ssh":     [("host",     "Host/IP",          False),
                ("port",     "Puerto (22)",       False),
                ("user",     "Usuario",           False),
                ("password", "Contraseña",        True),
                ("key_path", "Ruta clave SSH",    False),
                ("notes",    "Notas",             False)],
    "git":     [("host",     "Host (github.com)", False),
                ("user",     "Usuario",            False),
                ("email",    "Email",              False),
                ("token",    "Token/Contraseña",   True),
                ("notes",    "Notas",              False)],
    "db":      [("engine",   "Motor (postgres/mysql/sqlite)", False),
                ("host",     "Host",              False),
                ("port",     "Puerto",            False),
                ("user",     "Usuario",           False),
                ("password", "Contraseña",        True),
                ("database", "Base de datos",     False),
                ("notes",    "Notas",             False)],
    "api":     [("service",  "Servicio/Nombre",   False),
                ("url",      "URL base",          False),
                ("key",      "API key",           True),
                ("secret",   "API secret",        True),
                ("notes",    "Notas",             False)],
    "server":  [("host",     "Host/IP",           False),
                ("port",     "Puerto",            False),
                ("user",     "Usuario",           False),
                ("password", "Contraseña",        True),
                ("notes",    "Notas",             False)],
    "generic": [("value",    "Valor secreto",     True),
                ("notes",    "Notas",             False)],
}

_CRED_TYPES = tuple(_TYPE_FIELDS)


# ── Criptografía ──────────────────────────────────────────────────────────────

def _require_crypto() -> bool:
    try:
        import cryptography  # noqa: F401
        return True
    except ImportError:
        return False


def _derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
    raw = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def _encrypt(key: bytes, data: dict) -> bytes:
    from cryptography.fernet import Fernet
    return Fernet(key).encrypt(json.dumps(data, ensure_ascii=False).encode())


def _decrypt(key: bytes, token: bytes) -> dict:
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return json.loads(Fernet(key).decrypt(token).decode())
    except InvalidToken:
        raise ValueError("Contraseña maestra incorrecta o vault corrupto.")


def _read_vault_file() -> tuple[bytes, bytes] | None:
    """Devuelve (salt, ciphertext) o None si el vault no existe."""
    if not _VAULT_FILE.exists():
        return None
    raw = json.loads(_VAULT_FILE.read_bytes())
    return base64.b64decode(raw["salt"]), base64.b64decode(raw["token"])


def _write_vault_file(salt: bytes, ciphertext: bytes) -> None:
    _VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _VAULT_FILE.write_text(json.dumps({
        "salt":  base64.b64encode(salt).decode(),
        "token": base64.b64encode(ciphertext).decode(),
    }, indent=2))
    _VAULT_FILE.chmod(0o600)


def _save() -> None:
    """Re-cifra y persiste el estado actual."""
    if not _is_unlocked():
        raise RuntimeError("El vault está bloqueado.")
    _write_vault_file(_state["salt"], _encrypt(_state["key"], _state["data"]))


# ── Estado ────────────────────────────────────────────────────────────────────

def _is_unlocked() -> bool:
    return _state["key"] is not None and _state["data"] is not None


def _vault_exists() -> bool:
    return _VAULT_FILE.exists()


# ── Entrada segura a través del TUI ──────────────────────────────────────────

def _ask(prompt_text: str, secret: bool = False) -> str:
    """Solicita entrada al usuario usando el mecanismo del TUI (request_input).
    Si el TUI no está disponible, cae a getpass / input estándar.
    Lanza KeyboardInterrupt si el usuario cancela (Ctrl+C).
    """
    al = _state.get("agent_loop")
    if al is not None:
        fn = getattr(al, "_request_input", None)
        if callable(fn):
            result = fn(prompt_text, secret)
            if result == "" and secret:
                # Ctrl+C en el TUI devuelve cadena vacía — propagar como cancelación
                raise KeyboardInterrupt
            return result
    # Fallback cuando se usa vault fuera del TUI (tests, CLI directo)
    import getpass as _gp
    if secret:
        return _gp.getpass(f"  {prompt_text}: ")
    sys.stdout.write(f"  {prompt_text}: ")
    sys.stdout.flush()
    return sys.stdin.readline().rstrip("\n")


# ── Operaciones sobre credenciales ────────────────────────────────────────────

def _find(name: str) -> dict | None:
    """Busca credencial por nombre (case-insensitive) o por UUID parcial."""
    creds = _state["data"]["credentials"]
    nl = name.lower()
    for c in creds:
        if c["name"].lower() == nl or c["id"].startswith(name):
            return c
    return None


def _mask(value: str) -> str:
    if not value:
        return "(vacío)"
    if len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


# ── Herramientas para el agente ───────────────────────────────────────────────

def vault_list() -> str:
    """Lista todas las credenciales almacenadas (sin mostrar secretos)."""
    if not _require_crypto():
        return "Error: instala el paquete 'cryptography' (pip install cryptography)."
    if not _vault_exists():
        return "El vault no existe. Usa /vault init para crearlo."
    if not _is_unlocked():
        return "El vault está bloqueado. Usa /vault unlock para desbloquearlo."
    creds = _state["data"].get("credentials", [])
    if not creds:
        return "El vault está vacío."
    lines = ["Credenciales disponibles:\n"]
    for c in creds:
        tipo  = c.get("type", "?")
        name  = c["name"]
        host  = c.get("host") or c.get("service") or ""
        user  = c.get("user") or ""
        notes = c.get("notes") or ""
        line  = f"  [{tipo:8s}]  {name}"
        if host:
            line += f"  →  {host}"
        if user:
            line += f"  ({user})"
        if notes:
            line += f"  # {notes[:60]}"
        lines.append(line)
    return "\n".join(lines)


def vault_get(name: str) -> str:
    """
    Obtiene una credencial completa por nombre, incluyendo contraseña/token.
    Úsala antes de conectarte a un sistema remoto.
    """
    if not _require_crypto():
        return "Error: instala el paquete 'cryptography' (pip install cryptography)."
    if not _vault_exists():
        return "El vault no existe. Usa /vault init para crearlo."
    if not _is_unlocked():
        return "El vault está bloqueado. Usa /vault unlock para desbloquearlo."
    cred = _find(name)
    if cred is None:
        available = [c["name"] for c in _state["data"].get("credentials", [])]
        return f"Credencial '{name}' no encontrada. Disponibles: {', '.join(available) or '(ninguna)'}."
    lines = [f"Credencial: {cred['name']}  [{cred.get('type', '?')}]"]
    skip = {"id", "name", "type"}
    for k, v in cred.items():
        if k in skip or not v:
            continue
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


TOOLS: list = [
    ("vault_list", vault_list, {
        "name":        "vault_list",
        "description": "Lista las credenciales del vault (sin revelar secretos). Llama antes de vault_get para saber qué nombres hay.",
        "parameters":  {"type": "object", "properties": {}},
    }),
    ("vault_get", vault_get, {
        "name":        "vault_get",
        "description": "Obtiene una credencial completa por nombre, incluyendo contraseña/token. Necesaria para conectarse a sistemas remotos.",
        "parameters":  {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre de la credencial (tal como aparece en vault_list)."},
            },
            "required": ["name"],
        },
    }),
]


# ── Comando /vault ─────────────────────────────────────────────────────────────

_VAULT_HELP = """\
  /vault init               Crea un nuevo vault (establece contraseña maestra)
  /vault unlock             Desbloquea el vault con la contraseña maestra
  /vault lock               Bloquea el vault (elimina la clave de memoria)
  /vault list               Lista todas las credenciales (sin secretos)
  /vault show <nombre>      Muestra una credencial (secretos enmascarados)
  /vault reveal <nombre>    Muestra una credencial con secretos visibles
  /vault add <tipo> <nombre> [campo=valor ...]
                            Añade una credencial (se pedirá el secreto)
                              tipos: ssh  git  db  api  server  generic
  /vault edit <nombre>      Edita campos de una credencial existente
  /vault rm <nombre>        Elimina una credencial del vault
  /vault passwd             Cambia la contraseña maestra
"""


def _cmd_vault(args: str, agent_loop=None, config=None) -> None:
    from ui.console import console

    # Registrar agent_loop para que _ask() pueda usar el mecanismo del TUI
    if agent_loop is not None:
        _state["agent_loop"] = agent_loop

    if not _require_crypto():
        console.print(
            "  [bold red]✗[/bold red]  El paquete [bold]cryptography[/bold] no está instalado.\n"
            "       Instálalo con:  [bold]pip install cryptography[/bold]"
        )
        return

    parts = args.strip().split(None, 2)
    sub   = parts[0].lower() if parts else "help"

    # ── help ──────────────────────────────────────────────────────────────────
    if sub in ("help", ""):
        console.print(f"\n  [bold cyan]Vault de credenciales[/bold cyan]\n{_VAULT_HELP}")
        _print_vault_status(console)
        return

    # ── init ──────────────────────────────────────────────────────────────────
    if sub == "init":
        if _vault_exists():
            console.print("  [yellow]⚠[/yellow]  Ya existe un vault en "
                          f"[dim]{_VAULT_FILE}[/dim]. Usa [bold]/vault unlock[/bold].")
            return
        console.print("\n  [bold cyan]Creando nuevo vault cifrado…[/bold cyan]")
        console.print(f"  [dim]Fichero: {_VAULT_FILE}[/dim]\n")
        try:
            pw1 = _ask("Contraseña maestra: ", secret=True)
            if not pw1:
                console.print("  [red]✗[/red]  La contraseña no puede estar vacía.")
                return
            pw2 = _ask("Confirmar contraseña: ", secret=True)
        except KeyboardInterrupt:
            console.print("\n  [dim]Cancelado.[/dim]")
            return
        if pw1 != pw2:
            console.print("  [red]✗[/red]  Las contraseñas no coinciden.")
            return
        salt = os.urandom(16)
        key  = _derive_key(pw1, salt)
        data = {"credentials": []}
        _write_vault_file(salt, _encrypt(key, data))
        _state["key"]  = key
        _state["salt"] = salt
        _state["data"] = data
        console.print("  [green]✓[/green]  Vault creado y desbloqueado.")
        console.print("  [dim]Añade credenciales con [bold]/vault add[/bold][/dim]")
        return

    # ── unlock ────────────────────────────────────────────────────────────────
    if sub == "unlock":
        if not _vault_exists():
            console.print("  [red]✗[/red]  No existe ningún vault. Usa [bold]/vault init[/bold].")
            return
        if _is_unlocked():
            console.print("  [green]✓[/green]  El vault ya está desbloqueado.")
            return
        try:
            pw = _ask("Contraseña maestra: ", secret=True)
        except KeyboardInterrupt:
            console.print("\n  [dim]Cancelado.[/dim]")
            return
        file_data = _read_vault_file()
        if file_data is None:
            console.print("  [red]✗[/red]  No se puede leer el vault.")
            return
        salt, ciphertext = file_data
        try:
            key  = _derive_key(pw, salt)
            data = _decrypt(key, ciphertext)
        except ValueError as e:
            console.print(f"  [red]✗[/red]  {e}")
            return
        _state["key"]  = key
        _state["salt"] = salt
        _state["data"] = data
        n = len(data.get("credentials", []))
        console.print(f"  [green]✓[/green]  Vault desbloqueado — {n} credencial(es).")
        return

    # ── lock ──────────────────────────────────────────────────────────────────
    if sub == "lock":
        _state["key"]  = None
        _state["data"] = None
        _state["salt"] = None
        console.print("  [green]✓[/green]  Vault bloqueado.")
        return

    # ── list ──────────────────────────────────────────────────────────────────
    if sub == "list":
        _need_unlocked(console)
        if not _is_unlocked():
            return
        creds = _state["data"].get("credentials", [])
        if not creds:
            console.print("  [dim]El vault está vacío.[/dim]")
            return
        console.print(f"\n  [bold cyan]Vault — {len(creds)} credencial(es)[/bold cyan]\n")
        for c in creds:
            tipo  = c.get("type", "?")
            name  = c["name"]
            host  = c.get("host") or c.get("service") or ""
            user  = c.get("user") or ""
            notes = c.get("notes") or ""
            line  = f"  [bold]{name}[/bold]  [dim][{tipo}][/dim]"
            if host:
                line += f"  [cyan]{host}[/cyan]"
            if user:
                line += f"  [dim]({user})[/dim]"
            if notes:
                line += f"  [dim]# {notes[:60]}[/dim]"
            console.print(line)
        console.print()
        return

    # ── show / reveal ─────────────────────────────────────────────────────────
    if sub in ("show", "reveal"):
        _need_unlocked(console)
        if not _is_unlocked():
            return
        if len(parts) < 2:
            console.print("  [dim]Uso: /vault show <nombre>[/dim]")
            return
        name = parts[1]
        cred = _find(name)
        if cred is None:
            console.print(f"  [red]✗[/red]  Credencial '[bold]{name}[/bold]' no encontrada.")
            return
        do_reveal = sub == "reveal"
        sensitive = {"password", "token", "key", "secret", "value"}
        console.print(f"\n  [bold cyan]{cred['name']}[/bold cyan]  [dim][{cred.get('type','?')}][/dim]\n")
        skip = {"id", "name", "type"}
        for k, v in cred.items():
            if k in skip or not v:
                continue
            if k in sensitive and not do_reveal:
                display = _mask(v)
                console.print(f"  [dim]{k:12s}[/dim]  {display}  [dim](usa /vault reveal para ver)[/dim]")
            else:
                console.print(f"  [dim]{k:12s}[/dim]  [bold]{v}[/bold]")
        console.print()
        return

    # ── add ───────────────────────────────────────────────────────────────────
    if sub == "add":
        _need_unlocked(console)
        if not _is_unlocked():
            return
        if len(parts) < 3:
            console.print(
                "  [dim]Uso: /vault add <tipo> <nombre> [campo=valor ...]\n"
                f"       Tipos disponibles: {', '.join(_CRED_TYPES)}[/dim]"
            )
            return
        rest_parts = parts[2].split(None, 1)
        tipo = parts[1].lower()
        if tipo not in _CRED_TYPES:
            console.print(f"  [red]✗[/red]  Tipo desconocido. Disponibles: {', '.join(_CRED_TYPES)}")
            return
        name = rest_parts[0]
        if _find(name) is not None:
            console.print(f"  [red]✗[/red]  Ya existe una credencial con el nombre '[bold]{name}[/bold]'.")
            return

        # Parsear campo=valor adicionales del resto del argumento
        inline: dict[str, str] = {}
        if len(rest_parts) > 1:
            for token in rest_parts[1].split():
                if "=" in token:
                    k, _, v = token.partition("=")
                    inline[k.strip()] = v.strip()

        cred: dict[str, str] = {"id": str(uuid.uuid4()), "name": name, "type": tipo}
        console.print(f"\n  [bold cyan]Añadir credencial[/bold cyan]  [{tipo}]  "
                      f"[bold]{name}[/bold]\n  [dim](Enter para dejar vacío)[/dim]\n")

        fields = _TYPE_FIELDS[tipo]
        try:
            for field, label, is_secret in fields:
                if field in inline:
                    cred[field] = inline[field]
                    console.print(f"  [dim]{label:25s}[/dim]  {inline[field]}")
                    continue
                if is_secret:
                    val = _ask(f"  {label}: ", secret=True)
                else:
                    val = _ask(f"  {label}: ", secret=False)
                if val:
                    cred[field] = val
        except KeyboardInterrupt:
            console.print("\n  [dim]Cancelado.[/dim]")
            return

        _state["data"]["credentials"].append(cred)
        try:
            _save()
            console.print(f"\n  [green]✓[/green]  Credencial '[bold]{name}[/bold]' guardada.")
        except Exception as e:
            # Revertir
            _state["data"]["credentials"].pop()
            console.print(f"  [red]✗[/red]  Error al guardar: {e}")
        return

    # ── edit ──────────────────────────────────────────────────────────────────
    if sub == "edit":
        _need_unlocked(console)
        if not _is_unlocked():
            return
        if len(parts) < 2:
            console.print("  [dim]Uso: /vault edit <nombre>[/dim]")
            return
        name = parts[1]
        cred = _find(name)
        if cred is None:
            console.print(f"  [red]✗[/red]  Credencial '[bold]{name}[/bold]' no encontrada.")
            return
        tipo   = cred.get("type", "generic")
        fields = _TYPE_FIELDS.get(tipo, [])
        console.print(f"\n  [bold cyan]Editar[/bold cyan]  [{tipo}]  [bold]{name}[/bold]\n"
                      "  [dim](Enter para mantener el valor actual)[/dim]\n")
        try:
            for field, label, is_secret in fields:
                current = cred.get(field, "")
                hint    = "****" if (is_secret and current) else (current or "(vacío)")
                prompt  = f"  {label} [{hint}]: "
                if is_secret:
                    val = _ask(prompt, secret=True)
                else:
                    val = _ask(prompt, secret=False)
                if val:
                    cred[field] = val
        except KeyboardInterrupt:
            console.print("\n  [dim]Cancelado — sin cambios.[/dim]")
            return
        try:
            _save()
            console.print(f"\n  [green]✓[/green]  Credencial '[bold]{name}[/bold]' actualizada.")
        except Exception as e:
            console.print(f"  [red]✗[/red]  Error al guardar: {e}")
        return

    # ── rm ────────────────────────────────────────────────────────────────────
    if sub == "rm":
        _need_unlocked(console)
        if not _is_unlocked():
            return
        if len(parts) < 2:
            console.print("  [dim]Uso: /vault rm <nombre>[/dim]")
            return
        name = parts[1]
        cred = _find(name)
        if cred is None:
            console.print(f"  [red]✗[/red]  Credencial '[bold]{name}[/bold]' no encontrada.")
            return
        try:
            confirm = _ask(f"  ¿Eliminar '{name}'? [s/N]: ", secret=False)
        except KeyboardInterrupt:
            console.print("\n  [dim]Cancelado.[/dim]")
            return
        if confirm.lower() not in ("s", "si", "sí", "y", "yes"):
            console.print("  [dim]Cancelado.[/dim]")
            return
        _state["data"]["credentials"] = [
            c for c in _state["data"]["credentials"] if c["id"] != cred["id"]
        ]
        try:
            _save()
            console.print(f"  [green]✓[/green]  Credencial '[bold]{name}[/bold]' eliminada.")
        except Exception as e:
            console.print(f"  [red]✗[/red]  Error al guardar: {e}")
        return

    # ── passwd ────────────────────────────────────────────────────────────────
    if sub == "passwd":
        _need_unlocked(console)
        if not _is_unlocked():
            return
        console.print("\n  [bold cyan]Cambiar contraseña maestra[/bold cyan]\n")
        try:
            pw1 = _ask("Nueva contraseña: ", secret=True)
            if not pw1:
                console.print("  [red]✗[/red]  La contraseña no puede estar vacía.")
                return
            pw2 = _ask("Confirmar contraseña: ", secret=True)
        except KeyboardInterrupt:
            console.print("\n  [dim]Cancelado.[/dim]")
            return
        if pw1 != pw2:
            console.print("  [red]✗[/red]  Las contraseñas no coinciden.")
            return
        salt    = os.urandom(16)
        new_key = _derive_key(pw1, salt)
        _state["key"]  = new_key
        _state["salt"] = salt
        try:
            _save()
            console.print("  [green]✓[/green]  Contraseña maestra actualizada.")
        except Exception as e:
            console.print(f"  [red]✗[/red]  Error al guardar: {e}")
        return

    # ── desconocido ───────────────────────────────────────────────────────────
    console.print(f"  [dim]Subcomando desconocido: '{sub}'. Usa [bold]/vault help[/bold][/dim]")


def _need_unlocked(console) -> None:
    if not _vault_exists():
        console.print("  [red]✗[/red]  No existe ningún vault. Usa [bold]/vault init[/bold].")
        return
    if not _is_unlocked():
        console.print("  [yellow]⚠[/yellow]  El vault está bloqueado. Usa [bold]/vault unlock[/bold].")


def _print_vault_status(console) -> None:
    if not _vault_exists():
        console.print("  [dim]Estado: sin vault (usa /vault init)[/dim]")
    elif _is_unlocked():
        n = len(_state["data"].get("credentials", []))
        console.print(f"  [dim]Estado: [green]desbloqueado[/green] — {n} credencial(es)  "
                      f"· {_VAULT_FILE}[/dim]")
    else:
        console.print(f"  [dim]Estado: [yellow]bloqueado[/yellow]  · {_VAULT_FILE}[/dim]")


COMMANDS: dict = {"/vault": _cmd_vault}


# ── Hooks de ciclo de vida ────────────────────────────────────────────────────

def on_start(config) -> None:
    pass


def on_message(role: str, content: str) -> None:
    pass


def on_tool_result(name: str, args: dict, result: str) -> None:
    pass


def system_prompt_injection() -> str:
    if not _vault_exists():
        return ""
    if not _is_unlocked():
        return (
            "Hay un vault de credenciales disponible pero está bloqueado. "
            "Si necesitas acceder a sistemas remotos, pide al usuario que ejecute /vault unlock."
        )
    n = len(_state["data"].get("credentials", []))
    if n == 0:
        return ""
    return (
        f"Tienes acceso a un vault de credenciales con {n} entradas. "
        "Usa vault_list para ver qué credenciales hay y vault_get para obtener "
        "los detalles de una antes de conectarte a sistemas remotos o repositorios."
    )


def on_end() -> None:
    # Limpiar la clave de memoria al salir
    _state["key"]  = None
    _state["data"] = None
    _state["salt"] = None
