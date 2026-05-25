"""Gestión de permisos por herramienta con soporte de ask_fn personalizado.

En modo App (full-screen), _ask_fn se sustituye por una función que usa
run_in_terminal para pedir permiso sin romper el event loop de prompt_toolkit.

Resolución de permisos para MCP tools:
  Los tools MCP se registran como "mcp_{server}_{base}" (ej. mcp_oocode_assistant_write_file).
  La config solo tiene nombres bare ("write_file"). _resolve_mode() hace el fallback
  buscando el sufijo más corto que exista en _perms, de forma que:
    - mcp_oocode_assistant_write_file → "write_file" → hereda su permiso
    - /elevated afecta los nombres bare → MCP tools lo heredan automáticamente
"""
from ui.console import console


class PermissionManager:
    def __init__(self, permissions: dict[str, str]):
        self._perms = permissions.copy()
        self._session_auto: set[str] = set()
        # Callable(tool, description) -> str  ["s","n","siempre"]
        # Se inyecta desde OOCodeApp para usar run_in_terminal.
        self._ask_fn = None
        # Callable(tool_bare: str) -> None — persiste "siempre" en oocode.json.
        # Inyectado por OOCodeApp; None → no se persiste (modo REPL clásico).
        self._on_siempre = None
        # Nivel de elevated actual: "ask" | "on" | "full" | "off"
        # Se fija vía set_elevated() desde loop.py cuando cambia rt.elevated.
        self._elevated: str = "ask"
        # Cuando True: los tools con permiso "ask" se auto-aprueban en lugar de
        # pedir input(). Se usa en subagentes sin terminal interactiva disponible.
        self._non_interactive: bool = False

    def set_elevated(self, level: str) -> None:
        """Aplica el nivel de elevated. Se refleja inmediatamente en resolve_mode()
        para TODAS las tools, incluso las no registradas en _perms."""
        self._elevated = level

    # ── Resolución de nombres MCP ─────────────────────────────────────────────

    def _bare_name(self, tool: str) -> str | None:
        """Devuelve el nombre bare de un MCP tool, o None si no es MCP o no hay match.

        mcp_oocode_assistant_write_file → prueba sufijos desde el más corto:
          "file" → "write_file" ← match en _perms → devuelve "write_file"
        """
        if not tool.startswith("mcp_"):
            return None
        subparts = tool[4:].split("_")   # quita "mcp_" y parte el resto
        for i in range(1, len(subparts)):
            candidate = "_".join(subparts[i:])
            if candidate in self._perms:
                return candidate
        return None

    def resolve_mode(self, tool: str) -> str:
        """Devuelve el modo de permiso efectivo, con fallback para MCP tools.

        El nivel elevated se aplica aquí, por lo que funciona para CUALQUIER tool
        aunque no esté registrada en _perms (fixes /elevated full con tools MCP nuevas).

        Orden de resolución (de mayor a menor prioridad):
          1. elevated="full" → "auto" siempre (anula incluso "deny")
          2. _perms[tool]    → modo explícito para este tool
          3. _bare_name(tool)→ hereda del nombre bare (MCP tools)
          4. "ask"           → conservador para tools desconocidas
          5. elevated="on"   → convierte "ask" → "auto" (respeta "deny")
          6. elevated="off"  → convierte "ask" → "deny"
        """
        # ── full: todo auto, anula incluso "deny" ─────────────────────────────
        if self._elevated == "full":
            return "auto"

        # ── Resolver modo base desde _perms ───────────────────────────────────
        mode = self._perms.get(tool)
        if mode is None:
            bare = self._bare_name(tool)
            if bare:
                mode = self._perms.get(bare, "ask")
            else:
                mode = "ask"   # tool desconocida: conservador

        # ── on: auto-aprueba "ask" pero respeta "deny" ────────────────────────
        if self._elevated == "on" and mode == "ask":
            return "auto"

        # ── off: convierte "ask" en "deny" ────────────────────────────────────
        if self._elevated == "off" and mode == "ask":
            return "deny"

        return mode

    # ── API pública ───────────────────────────────────────────────────────────

    def check(self, tool: str, description: str) -> bool:
        """Devuelve True si se puede ejecutar la herramienta."""
        if tool in self._session_auto:
            return True
        # Para MCP tools: verificar también si el nombre bare tiene sesión auto
        bare = self._bare_name(tool)
        if bare and bare in self._session_auto:
            return True

        mode = self.resolve_mode(tool)

        if mode == "auto":
            return True
        if mode == "deny":
            console.print(f"[red]Denegado:[/red] '{tool}' está bloqueado por configuración.")
            return False

        # mode == "ask" — usar ask_fn personalizado o input() estándar
        if self._ask_fn is not None:
            choice = self._ask_fn(tool, description)
        elif self._non_interactive:
            # Subagente sin terminal interactiva: auto-aprobar para no bloquear
            self._session_auto.add(tool)
            return True
        else:
            console.print(f"\n[yellow]Permiso requerido:[/yellow] {description}")
            choice = _ask_default(tool)

        if choice == "siempre":
            self._session_auto.add(tool)
            if self._on_siempre is not None:
                try:
                    self._on_siempre(tool)
                except Exception:
                    pass
            return True
        return choice == "s"

    def set_permission(self, tool: str, mode: str) -> None:
        if mode not in ("auto", "ask", "deny"):
            raise ValueError(f"Modo inválido: {mode}. Usa: auto, ask, deny")
        self._perms[tool] = mode

    def get_all(self) -> dict[str, str]:
        return self._perms.copy()


def _ask_default(tool: str) -> str:
    """Pregunta por consola estándar (modo clásico sin prompt_toolkit activo)."""
    while True:
        try:
            raw = input(f"  Permitir {tool}? [s/n/siempre] (s): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "n"
        if raw in ("s", "n", "siempre"):
            return raw
        if raw == "":
            return "s"
