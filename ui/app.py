"""OOCode TUI full-screen — 5 filas fijas al fondo, output scrollable arriba.

Layout (de arriba abajo):
  ┌─────────────────────────────────────────┐  ← salida del agente (scrollable)
  │ texto del agente, herramientas, etc.    │
  ├─────────────────────────────────────────┤  ← spinner / plan-tasks / tip (3 líneas)
  ├─────────────────────────────────────────┤  ← separador superior ──────── (1 línea)
  │  oocode  main · proj  ❯ _               │  ← input del usuario (1 línea)
  ├─────────────────────────────────────────┤  ← separador inferior ──────── (1 línea)
  │ ⏵⏵ subagentes · main ● · ◯ id tarea    │  ← panel subagentes (dinámico, 0 si vacío)
  │ · 🤖 main · ◎ ask · mcp:N · ctx · mod  │  ← toolbar línea 1: indicadores
  │ · ✐ py js ts go cpp sh ...             │  ← toolbar línea 2: LSP
  │ · F1 keys · F2 status · F3 compact ·   │  ← toolbar línea 3: keybindings
  └─────────────────────────────────────────┘

Permisos: cuando el agente necesita permiso, el input area cambia de modo
y el usuario responde [s/n/siempre] en la misma barra de entrada.
El agente bloquea su hilo hasta recibir la respuesta.
"""
import html
import io
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from rich.markup import escape as markup_escape

from prompt_toolkit import Application
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory, ConditionalAutoSuggest
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import ANSI, FormattedText, to_formatted_text
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, Float, FloatContainer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.processors import BeforeInput, ConditionalProcessor, PasswordProcessor
from prompt_toolkit.filters import Condition
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

from ui.console import console
from agent.keybindings import KeybindingManager

_RICH_TAG_RE  = re.compile(r'\[/?[^\]]+\]')        # strip markup Rich para status
_DEC_PRIV_RE  = re.compile(r'\x1b\[\?[0-9;]*[a-zA-Z]')  # \x1b[?25l, ?25h, etc.

# Marcadores de estilo inline: \x01STYLE\x02TEXT\x03
# Emitidos por agent/loop.py via _sfmt(); parsed aquí para colores en el status window.
_STYLED_SEG_RE = re.compile(r'\x01([^\x02]*)\x02([^\x03]*)\x03')


def _parse_status_line(text: str, default_cls: str) -> list[tuple[str, str]]:
    """Divide texto con marcadores \\x01STYLE\\x02TEXT\\x03 en tuplas (clase, texto).

    Los segmentos fuera de marcadores usan `default_cls`. Segmentos con estilo vacío
    (\\x01\\x02TEXT\\x03) también usan `default_cls`.
    """
    result: list[tuple[str, str]] = []
    pos = 0
    for m in _STYLED_SEG_RE.finditer(text):
        before = text[pos:m.start()]
        if before:
            result.append((default_cls, before))
        style_name = m.group(1)
        content    = m.group(2)
        if content:
            cls = f"class:{style_name}" if style_name else default_cls
            result.append((cls, content))
        pos = m.end()
    tail = text[pos:]
    if tail:
        result.append((default_cls, tail))
    return result

# Paleta de colores para el ● pulsante durante ejecución de tools
_LIVE_PULSE_COLORS = [
    "\x1b[1;32m",   # bold green
    "\x1b[1;36m",   # bold cyan
    "\x1b[1;96m",   # bold bright cyan
    "\x1b[1;36m",   # bold cyan (repeat → transición suave)
    "\x1b[1;32m",   # bold green
    "\x1b[0;32m",   # normal green (dim-down)
    "\x1b[1;32m",   # bold green (dim-up)
    "\x1b[1;36m",   # bold cyan
]
_LIVE_RESET = "\x1b[0m"

# Paleta para el ◐ pulsante en la línea ⎿ (amarillo → blanco)
_CIRC_PULSE_COLORS = [
    "\x1b[1;33m",   # bold yellow
    "\x1b[1;93m",   # bold bright yellow
    "\x1b[1;37m",   # bold white
    "\x1b[0;37m",   # white
]

# Extensiones de imagen soportadas para input multimodal
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
# Regex para detectar rutas de imagen en el texto del usuario
# Soporta: /ruta/abs, ~/ruta, ./ruta, ruta/relativa y nombre.ext
_IMG_PATH_RE = re.compile(
    r'(?:^|\s)((?:~?/|\.{0,2}/|\w)[^\s]*\.(?:png|jpg|jpeg|gif|webp|bmp|tiff|tif))',
    re.IGNORECASE,
)

_PERM_CYCLE  = ["ask", "on", "full"]
_PERM_ICONS  = {"off": "○", "ask": "◎", "on": "◉", "full": "●"}
_PERM_LABELS = {"off": "solo lectura", "ask": "normal", "on": "elevado", "full": "sin restricciones"}

_SLASH_CMDS = sorted([
    '/abort', '/activation', '/add-dir', '/agent', '/agents', '/steer',
    '/branch', '/btw', '/checkpoint', '/clear', '/color', '/commands',
    '/compact', '/config', '/context', '/copy', '/ctx', '/doctor',
    '/elevated', '/elev', '/exit', '/fast', '/gateway-status', '/help',
    '/init', '/keybindings', '/kill', '/logs', '/lsp', '/mcp', '/mem', '/model',
    '/models', '/new', '/plugins', '/q', '/quit', '/rag', '/reasoning',
    '/reset', '/resume', '/review', '/schedule', '/session', '/sessions',
    '/settings', '/skills', '/spawn', '/splash', '/status', '/subagents', '/tasks',
    '/think', '/tip', '/trace', '/usage', '/verbose', '/workspace',
])


# ── Completado ────────────────────────────────────────────────────────────────

# Regex: captura el último token que parece una ruta (~ o /, sin espacios)
_PATH_RE = re.compile(r'(?:(?<=\s)|^)(~?/\S*)')


def _common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while prefix and not s.startswith(prefix):
            prefix = prefix[:-1]
        if not prefix:
            return ""
    return prefix


class _OOCompleter(Completer):
    """Slash commands al inicio de línea y paths en cualquier posición del texto."""

    def get_completions(self, document, complete_event):
        text     = document.text_before_cursor
        stripped = text.lstrip()

        # Slash command: solo si la línea entera es "/cmd" sin espacio Y coincide con algún cmd real
        if (stripped.startswith('/') and ' ' not in stripped
                and any(cmd.startswith(stripped) for cmd in _SLASH_CMDS)):
            for cmd in _SLASH_CMDS:
                if cmd.startswith(stripped):
                    yield Completion(cmd[len(stripped):], display=cmd)
            return

        # Path: busca el último token de ruta en el texto (~ o /)
        # Tomamos el último match porque el cursor siempre está al final del texto.
        matches = _PATH_RE.findall(text)
        if not matches:
            return
        token = matches[-1]
        expanded = os.path.expanduser(token)

        if expanded.endswith('/'):
            dir_part, file_part = expanded, ''
        else:
            dir_part  = os.path.dirname(expanded) or '/'
            file_part = os.path.basename(expanded)

        try:
            entries = sorted(os.scandir(dir_part), key=lambda e: e.name.lower())
        except OSError:
            return

        for entry in entries:
            # Ocultar dotfiles salvo que el usuario ya haya tecleado '.'
            if entry.name.startswith('.') and not file_part.startswith('.'):
                continue
            if not entry.name.startswith(file_part):
                continue
            is_dir    = entry.is_dir(follow_symlinks=True)
            suffix    = '/' if is_dir else ''
            full_comp = os.path.join(dir_part, entry.name) + suffix
            # Preservar '~' si el token original usaba '~'
            if token.startswith('~'):
                home = os.path.expanduser('~')
                if full_comp.startswith(home):
                    full_comp = '~' + full_comp[len(home):]
            yield Completion(full_comp, start_position=-len(token),
                             display=entry.name + suffix)


# ── Control de salida con scroll de ratón ────────────────────────────────────

class _ScrollableOutput(FormattedTextControl):
    """FormattedTextControl que intercepta la rueda del ratón para scroll en la salida."""

    def __init__(self, app: "OOCodeApp", **kwargs):
        super().__init__(**kwargs)
        self._ooapp = app

    def mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self._ooapp._do_scroll_up()
            return None   # evento manejado, no propagar al Window
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self._ooapp._do_scroll_down()
            return None
        return super().mouse_handler(mouse_event)


# ── Redirección de stdout ─────────────────────────────────────────────────────

class _AppWriter(io.RawIOBase):
    """Redirige sys.stdout al buffer de texto de OOCodeApp."""

    def __init__(self, target: "OOCodeApp"):
        self._target = target

    def write(self, data) -> int:
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        self._target._append_output(data)
        return len(data)

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def flush(self) -> None:
        pass

    @property
    def encoding(self) -> str:
        return "utf-8"

    def fileno(self) -> int:
        return sys.__stdout__.fileno()


# ── OOCodeApp ─────────────────────────────────────────────────────────────────

class OOCodeApp:
    """Aplicación TUI full-screen con 4 filas fijas."""

    _MAX_OUTPUT_CHARS  = 80_000   # límite del buffer ANSI (prompt_toolkit recalcula word-wrap en cada render)
    _TRIM_TARGET_CHARS = 40_000   # objetivo tras recorte automático al finalizar un turno

    def __init__(self, agent_loop, config):
        self._agent_loop = agent_loop
        self._config = config
        self._lock = threading.Lock()
        self._output_parts: list[str] = []
        self._output_chars: int = 0
        self._agent_thread: Optional[threading.Thread] = None
        # Throttle de invalidate: evita re-renders innecesarios cuando el status no cambia
        self._last_status_text: str = ""
        self._last_invalidate_time: float = 0.0
        self._last_scroll_invalidate: float = 0.0   # throttle separado para scroll (50 ms)
        # Cache del texto ANSI renderizado: evita re-parsear 400KB en cada frame
        self._output_cache_key: int = 0      # versión del buffer (incrementa en cada append)
        self._output_cache_val = None        # FormattedText cacheado
        # Tip rotativo siempre visible en la fila 3 del status window.
        # Se inicializa aquí para que sea sticky desde el primer momento.
        from ui.renderer import _random_tip as _rt
        self._current_tip: str = _rt()
        # Cache del tip sin markup Rich (evita regex 7×/seg en _get_status_text)
        self._plain_tip_cache: str = _RICH_TAG_RE.sub('', self._current_tip)

        # Scroll: cursor-based → _auto_scroll=True pone cursor en la última línea real
        #         _auto_scroll=False usa cursor en _scroll_pos (posición manual)
        self._scroll_pos: int = 0
        self._auto_scroll: bool = True
        self._output_line_count: int = 0      # nº de \n en el buffer (para PageUp/Down)
        self._last_rendered_line_count: int = 0  # nº de \n del texto que se acaba de renderizar
        self._output_window: Optional[Window] = None

        # Estado de solicitud de permiso (accedido desde 2 hilos)
        self._perm_mode: bool = False
        self._perm_event: threading.Event = threading.Event()
        self._perm_result: list = ["s"]
        self._perm_tool: str = ""
        self._perm_description: str = ""  # descripción completa (tool + args)

        # Input genérico (vault, plugins) — similar al modo permiso
        self._input_mode: bool   = False
        self._input_secret: bool = False       # True → PasswordProcessor enmascara el texto
        self._input_prompt: str  = ""          # texto que aparece antes del cursor
        self._input_event: threading.Event = threading.Event()
        self._input_result: list[str] = [""]

        # Timer de parpadeo: invalida la toolbar cada 350ms para el ● pulsante
        self._blink_stop = threading.Event()

        # Live block — zona dinámica al final del output (● pulsante + ⎿ live)
        self._live_block_active: bool = False
        self._live_block_bullet: str = ""        # texto del agente tras ●
        self._live_block_action: str = ""        # acción de tool (sobreescribe ● mientras ejecuta)
        self._live_block_body: list[str] = []         # output acumulado (list para O(1) append)
        self._live_block_plan_header: list[str] = [] # plan creado en este turno — se renderiza ANTES del ●
        self._live_block_plan_mode: bool = False     # True mientras plan_create imprime sus líneas
        self._live_block_tool_n: int = 0         # contador de tools completadas
        self._live_block_current_tool: str = ""  # nombre de tool en '|  ◐ tool:'
        self._live_block_preview: list[str] = [] # args/contexto (1-4 líneas) visibles solo mientras corre
        self._live_block_completed_tools: list[str] = []  # historial de tools completadas (máx 4)
        self._live_pulse_idx: int = 0            # índice de color para animación

        # Caché partida: partes estáticas vs live block — evita re-parsear 80KB en cada blink
        self._output_static_key: int = 0          # se incrementa solo cuando _output_parts cambia
        self._static_ansi_cache: list = []        # fragmentos ANSI de la parte estática
        self._static_ansi_rendered_key: int = -1  # _output_static_key del último render

        # Keybinding manager
        self._kb_manager = KeybindingManager()
        agent_loop._kb_manager = self._kb_manager

        # Imágenes pendientes adjuntas (via Ctrl+P o /attach) para el próximo mensaje
        self._pending_images: list[str] = []
        agent_loop._pending_images = self._pending_images  # referencia compartida para toolbar

        # Status callback → hilo del agente actualiza el spinner en la fila 3
        agent_loop._status_text = ""
        agent_loop._status_cb   = self._set_status

        # Live block callbacks para el agente
        agent_loop._start_live_block_cb          = self._start_live_block
        agent_loop._update_live_tools_cb         = self._update_live_tools
        agent_loop._update_live_current_tool_cb  = self._update_live_current_tool
        agent_loop._update_live_preview_cb       = self._update_live_preview
        agent_loop._update_live_tool_start_cb    = self._update_live_tool_start
        agent_loop._update_live_bullet_cb        = self._update_live_bullet
        agent_loop._flush_live_block_cb          = self._flush_live_block
        agent_loop._set_plan_header_mode_cb      = self._set_plan_header_mode

        # Compact-reset callback → vacía el área de conversación antes del reset visual
        agent_loop._clear_output_cb = self._clear_output_for_compact

        # Hook de nueva sesión → limpia el historial de entrada en memoria
        agent_loop._on_new_session = self._reset_input_history

        # Permission callback
        self._setup_permissions()

        # Asegurar que el directorio de historial existe
        history_file = os.path.expanduser("~/.oocode/history")
        os.makedirs(os.path.dirname(history_file), exist_ok=True)

        # Buffer de entrada del usuario (multiline: Escape+Enter añade línea, Enter envía)
        self._completer = _OOCompleter()
        self._input_buf = Buffer(
            name="input",
            multiline=True,
            accept_handler=self._on_accept,
            history=FileHistory(history_file),
            completer=self._completer,
            # Deshabilitar auto-suggest en input_mode: evita interferencias al teclear contraseñas
            auto_suggest=ConditionalAutoSuggest(
                AutoSuggestFromHistory(),
                Condition(lambda: not self._input_mode),
            ),
            complete_while_typing=False,
        )

        self._app = self._build_app()

    # ── Buffer de salida ─────────────────────────────────────────────────────

    def _append_output(self, text: str) -> None:
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = _DEC_PRIV_RE.sub('', text)   # elimina \x1b[?25l y similares
        with self._lock:
            if self._live_block_active:
                # Durante live block: O(1) append en lista (evita O(n²) string concat)
                if self._live_block_plan_mode:
                    # plan_create imprimiendo: va al header (encima del ●)
                    self._live_block_plan_header.append(text)
                else:
                    self._live_block_body.append(text)
            else:
                self._output_parts.append(text)
                self._output_chars += len(text)
                self._output_line_count += text.count('\n')
                while self._output_chars > self._MAX_OUTPUT_CHARS and len(self._output_parts) > 1:
                    removed = self._output_parts.pop(0)
                    self._output_chars -= len(removed)
                    self._output_line_count -= removed.count('\n')
                self._output_line_count = max(0, self._output_line_count)
                self._output_static_key += 1   # invalida caché ANSI estático
            self._output_cache_key += 1        # invalida caché completo
        # El propio prompt_toolkit coalescia múltiples invalidate() en un solo render.
        try:
            self._app.invalidate()
        except Exception:
            pass

    def _clear_output_for_compact(self) -> None:
        """Vacía el buffer de conversación antes del reset visual de compactación."""
        with self._lock:
            self._output_parts.clear()
            self._output_chars = 0
            self._output_line_count = 0
            self._live_block_active = False
            self._live_block_bullet = ""
            self._live_block_body = []
            self._live_block_plan_header = []
            self._live_block_plan_mode = False
            self._live_block_tool_n = 0
            self._live_block_current_tool = ""
            self._live_block_preview = []
            self._live_block_completed_tools = []
            self._output_static_key += 1
            self._output_cache_key += 1
        try:
            self._app.invalidate()
        except Exception:
            pass

    def _set_plan_header_mode(self, active: bool) -> None:
        """Activa/desactiva la captura del plan en el header del live block."""
        with self._lock:
            self._live_block_plan_mode = active

    def _build_live_block_ansi(self) -> str:
        """Construye el ANSI del live block con ● pulsante y ⎿ actualizable."""
        pulse = self._live_pulse_idx
        color = _LIVE_PULSE_COLORS[pulse % len(_LIVE_PULSE_COLORS)]
        # Mostrar acción actual en ● si hay tool ejecutando, si no el texto del agente
        display_bullet = self._live_block_action if self._live_block_action else self._live_block_bullet
        lines: list[str] = [f"\n  {color}●{_LIVE_RESET} {display_bullet}"]
        body = "".join(self._live_block_body)
        if self._live_block_current_tool:
            lines.append(f"  \x1b[2m│\x1b[0m \x1b[2m◐ {self._live_block_current_tool}\x1b[0m")
            if body.strip():
                for _bl in body.rstrip('\n').splitlines()[:5]:
                    lines.append(f"  \x1b[2m│    {_bl}\x1b[0m")
            elif self._live_block_preview:
                for _pl in self._live_block_preview[:4]:
                    lines.append(f"  \x1b[2m│    {_pl}\x1b[0m")
        elif body.strip():
            lines.append(body.rstrip('\n'))
        n = self._live_block_tool_n
        if n > 0:
            unit = "tool" if n == 1 else "tools"
            lines.append(f"  \x1b[2m⎿ Used {n} {unit} (ctrl+o to expand)\x1b[0m")
        return "\n".join(lines) + "\n"

    def _get_output_text(self):
        # ── 1. Snapshot bajo lock (solo ops baratas — sin join ni scan) ───────
        with self._lock:
            full_key   = self._output_cache_key
            static_key = self._output_static_key

            # Fast path: nada cambió en absoluto
            if (self._output_cache_val is not None
                    and full_key == getattr(self, "_output_cache_rendered_key", -1)):
                self._last_rendered_line_count = self._output_cache_line_count
                return self._output_cache_val

            # Copia shallow de refs (O(n_parts), no copia strings)
            parts_snap        = list(self._output_parts)
            live_active       = self._live_block_active
            live_bullet       = self._live_block_bullet if live_active else ""
            live_action       = self._live_block_action if live_active else ""
            live_body         = "".join(self._live_block_body) if live_active else ""
            live_plan_hdr     = "".join(self._live_block_plan_header) if live_active else ""
            live_tool_n       = self._live_block_tool_n if live_active else 0
            live_current_tool      = self._live_block_current_tool if live_active else ""
            live_preview           = list(self._live_block_preview) if live_active else []
            live_completed_tools   = list(self._live_block_completed_tools) if live_active else []
            live_pulse             = self._live_pulse_idx
            out_lines         = self._output_line_count  # contador incremental

        # ── 2. Parte estática: re-parsear ANSI solo cuando cambia (no en cada blink) ──
        # _output_static_key solo sube cuando _output_parts cambia (flush/append).
        # El blink sube _output_cache_key pero NO _output_static_key → cache hit aquí.
        if static_key != getattr(self, "_static_ansi_rendered_key", -1):
            static_combined = "".join(parts_snap)
            if static_combined:
                try:
                    self._static_ansi_cache = list(to_formatted_text(ANSI(static_combined)))
                except Exception:
                    plain = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', static_combined)
                    self._static_ansi_cache = [("", plain)]
            else:
                self._static_ansi_cache = []
            self._static_ansi_rendered_key = static_key

        static_frags: list = getattr(self, "_static_ansi_cache", [])

        # ── 3. Live block: solo ~6 líneas, barato de re-parsear en cada blink ─
        if live_active:
            color = _LIVE_PULSE_COLORS[live_pulse % len(_LIVE_PULSE_COLORS)]
            # ● muestra siempre el mensaje original; live_action solo se usa si no hay
            # tool individual activa (caso paralelo: bullet pulsante como resumen).
            display_bullet = live_bullet if live_current_tool else (live_action or live_bullet)
            lb: list[str] = []
            if live_plan_hdr.strip():
                lb.append(live_plan_hdr.rstrip('\n'))
            lb.append(f"\n  {color}●{_LIVE_RESET} {display_bullet}")
            # Tools completadas anteriores (hasta 3, greyed)
            for _ct in live_completed_tools[-3:]:
                lb.append(f"  \x1b[2m│\x1b[0m \x1b[2m◐ {_ct}\x1b[0m")
            # Tool activa: live_action en la misma línea si está disponible, si no, preview aparte
            if live_current_tool:
                _tl = f"◐ {live_current_tool}"
                if live_action:
                    _tl += f" {live_action}"
                lb.append(f"  \x1b[2m│\x1b[0m \x1b[2m{_tl}\x1b[0m")
                if not live_action and live_preview:
                    for _pl in live_preview[:3]:
                        lb.append(f"  \x1b[2m│    {_pl}\x1b[0m")
            # live_body (texto del mensaje) NO se muestra en la zona live — se preserva
            # en _live_block_body para que aparezca correctamente tras el flush.
            if live_tool_n > 0:
                unit = "tool" if live_tool_n == 1 else "tools"
                lb.append(f"  \x1b[2m⎿ Used {live_tool_n} {unit} (ctrl+o to expand)\x1b[0m")
            live_text = "\n".join(lb) + "\n"
            line_count = out_lines + live_text.count('\n')
            try:
                live_frags = list(to_formatted_text(ANSI(live_text)))
            except Exception:
                plain = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', live_text)
                live_frags = [("", plain)]
            rendered = FormattedText(static_frags + live_frags)
        else:
            line_count = out_lines
            rendered   = FormattedText(static_frags) if static_frags else FormattedText([])

        if not static_frags and not live_active:
            rendered   = FormattedText([])
            line_count = 0

        # ── 4. Guardar caché bajo lock (solo stores baratos) ──────────────────
        with self._lock:
            self._output_cache_val          = rendered
            self._output_cache_rendered_key = full_key
            self._output_cache_line_count   = line_count
            self._last_rendered_line_count  = line_count
        return rendered

    def _get_output_cursor_pos(self) -> Point:
        """Posición del cursor para guiar el scroll en wrap_lines=True.

        _scroll_when_linewrapping no usa get_vertical_scroll; ajusta
        vertical_scroll para mantener cursor_position.y visible. Poniendo el
        cursor en la última línea renderizada, el scroll va al fondo.

        Usa _last_rendered_line_count (fijado en _get_output_text dentro del
        mismo create_content) para garantizar que el índice nunca supera el
        fragment_lines actual → sin race condition ni IndexError.
        """
        if self._auto_scroll:
            return Point(x=0, y=self._last_rendered_line_count)
        return Point(x=0, y=max(0, self._scroll_pos))

    # ── Live block (● pulsante + ⎿ actualizable) ────────────────────────────

    def _start_live_block(self, bullet: str) -> None:
        """Inicia el live block con el texto del ● como primer línea."""
        with self._lock:
            self._live_block_active = True
            self._live_block_bullet = bullet
            self._live_block_action = ""
            self._live_block_body = []
            self._live_block_plan_header = []
            self._live_block_plan_mode = False
            self._live_block_tool_n = 0
            self._live_block_current_tool = ""
            self._live_block_preview = []
            self._live_block_completed_tools = []
            self._output_cache_key += 1
        try:
            self._app.invalidate()
        except Exception:
            pass

    def _update_live_tools(self, count: int) -> None:
        """Actualiza el contador de tools en la línea ⎿."""
        with self._lock:
            if self._live_block_current_tool:
                self._live_block_completed_tools.append(self._live_block_current_tool)
                if len(self._live_block_completed_tools) > 4:
                    self._live_block_completed_tools.pop(0)
            self._live_block_tool_n = count
            self._live_block_current_tool = ""
            self._live_block_preview = []
            self._live_block_action = ""
            self._output_cache_key += 1
        # Sin invalidate() aquí — el blink timer de 350ms recoge el cambio.
        # Las invalidaciones inmediatas desde callbacks intermedios acumulan
        # repaints innecesarios en prompt_toolkit cuando corren múltiples tools.

    def _update_live_current_tool(self, tool_label: str) -> None:
        """Muestra el nombre de la tool ejecutando en '|  ◐ tool:' (sin preview). Prefer _update_live_tool_start."""
        with self._lock:
            self._live_block_current_tool = tool_label
            self._live_block_preview = []
            self._output_cache_key += 1

    def _update_live_preview(self, lines: list) -> None:
        """Establece las líneas de preview visibles bajo '|  ◐ tool:'. Prefer _update_live_tool_start."""
        with self._lock:
            self._live_block_preview = [str(l) for l in lines[:4]]
            self._output_cache_key += 1

    def _update_live_tool_start(self, tool_label: str, preview: list) -> None:
        """Actualiza herramienta actual + preview en una sola operación atómica (evita double-flash)."""
        with self._lock:
            self._live_block_current_tool = tool_label
            self._live_block_preview = [str(l) for l in preview[:4]]
            self._output_cache_key += 1

    def _update_live_bullet(self, action: str) -> None:
        """Actualiza el texto del ● con la acción actual (restaurado al completar)."""
        with self._lock:
            self._live_block_action = action
            self._output_cache_key += 1

    def _flush_live_block(self, summary: str = "") -> None:
        """Cierra el live block y lo mueve al buffer estático con ● de color fijo."""
        with self._lock:
            if not self._live_block_active:
                return
            # Determinar color final desde accent_color del agente
            try:
                from agent.runtime import COLOR_PRESETS
                _ac = getattr(self._agent_loop.rt, "accent_color", "cyan")
                _ANSI_ACCENT = {
                    "green": "\x1b[1;32m", "cyan": "\x1b[1;36m",
                    "blue": "\x1b[1;34m",  "magenta": "\x1b[1;35m",
                    "yellow": "\x1b[1;33m", "red": "\x1b[1;31m",
                }
                bullet_color = _ANSI_ACCENT.get(_ac, "\x1b[1;36m")
            except Exception:
                bullet_color = "\x1b[1;36m"

            # Construir bloque final (sin pulso) — plan header encima del ●
            plan_hdr_str = "".join(self._live_block_plan_header)
            body_str = "".join(self._live_block_body)
            lines: list[str] = []
            if plan_hdr_str.strip():
                lines.append(plan_hdr_str.rstrip('\n'))
            lines.append(f"\n  {bullet_color}●{_LIVE_RESET} {self._live_block_bullet}")
            if body_str.strip():
                lines.append(body_str.rstrip('\n'))
            if summary:
                lines.append(f"  \x1b[2m⎿ {summary}\x1b[0m")
            elif self._live_block_tool_n > 0:
                n = self._live_block_tool_n
                unit = "tool" if n == 1 else "tools"
                lines.append(f"  \x1b[2m⎿ Used {n} {unit} (ctrl+o to expand)\x1b[0m")
            # Trailing \n: el console.print() antes de ● ya fue eliminado del loop.
            # Separación: ⎿\n\n◈Plan (1 blank) y plan-end\n\next-●-leading-\n (1 blank).
            final = "\n".join(lines) + "\n"

            self._live_block_active = False
            self._live_block_bullet = ""
            self._live_block_action = ""
            self._live_block_body = []
            self._live_block_plan_header = []
            self._live_block_plan_mode = False
            self._live_block_tool_n = 0
            self._live_block_current_tool = ""
            self._live_block_preview = []
            self._output_parts.append(final)
            self._output_chars += len(final)
            self._output_line_count += final.count('\n')
            while self._output_chars > self._MAX_OUTPUT_CHARS and len(self._output_parts) > 1:
                removed = self._output_parts.pop(0)
                self._output_chars -= len(removed)
                self._output_line_count -= removed.count('\n')
            self._output_line_count = max(0, self._output_line_count)
            self._output_static_key += 1  # el bloque final pasa a partes estáticas
            self._output_cache_key += 1
        try:
            self._app.invalidate()
        except Exception:
            pass

    # ── Spinner / status ─────────────────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self._agent_loop._status_text = text
        # Throttle tiempo: máx 5 renders/s (200ms). Permite tokens en streaming.
        now = time.monotonic()
        if (now - self._last_invalidate_time) >= 0.2:
            self._last_invalidate_time = now
            try:
                self._app.invalidate()
            except Exception:
                pass

    def _status_window_height(self) -> int:
        """Altura dinámica del status window según si hay plan de tareas activo."""
        tasks = getattr(self._agent_loop, "_plan_tasks", [])
        if not tasks:
            return 3  # spinner(1) + tokens/bar(1) + tip(1)
        # spinner(1) + visible_tasks(max 5) + summary(1)
        visible = min(len(tasks), 5)
        return min(1 + visible + 1, 8)

    # ── Panel de subagentes ──────────────────────────────────────────────────

    def _subagent_panel_height(self) -> int:
        """Altura del panel de subagentes.

        Devuelve 0 cuando no hay subagentes activos, lo que elimina el panel del
        layout sin necesidad de un ConditionalContainer. El mínimo cuando hay
        subagentes es 2 (header + main agent) + N líneas de subagente (max 5).
        """
        try:
            from agent.subagent import list_running as _lr, list_recent as _lrec
            # Mostrar también subagentes recientes (terminados en los últimos 10s)
            subs = _lr()
            if not subs:
                subs = _lrec(ttl=10.0)[:3]   # máx 3 recientes brevemente
            n = len(subs)
            if n == 0:
                return 0
            # header(1) + N subagentes (máx 8 visibles)
            return 1 + min(n, 8)
        except Exception:
            return 0

    def _get_subagent_panel_text(self):
        """Contenido del panel de subagentes (estilo Claude Code).

        Formato cuando hay subagentes activos:
          ⏵⏵  subagentes activos · ^C interrumpir · /subagents gestionar   N% ctx
          ●  main (agent_name)                            ↑/↓ · /kill · /steer
          ◯  emoji id  tarea...                                    Ns · ↓ running
          ◯  emoji id  tarea...                                   Ns · ✓ done
        """
        try:
            from agent.subagent import list_running as _lr, list_recent as _lrec
            subs = _lr()
            if not subs:
                subs = _lrec(ttl=10.0)[:3]
            if not subs:
                return [("", "")]
        except Exception:
            return [("", "")]

        # Porcentaje de contexto para la línea de header
        try:
            cs      = self._agent_loop.context.stats()
            ctx_pct = int(cs["tokens_estimate"] / max(cs["max_tokens"], 1) * 100)
            ctx_str = f" · {ctx_pct}% ctx ·"
        except Exception:
            ctx_str = " ·"

        result: list[tuple[str, str]] = []

        # Nombre e icono del agente principal
        agent_name  = html.escape(
            (getattr(self._agent_loop.config, "agent_name", None) or "main")[:20]
        )
        agent_emoji = html.escape(
            getattr(self._agent_loop.config, "agent_emoji", "🤖") or "🤖"
        )

        # ── Línea header — todos los controles en una sola línea + ctx% · ───
        header_l = (
            "    ⏵⏵ Subagentes Activos"
            " · ^C interrumpir · /subagents gestionar"
            " · /kill · /steer"
        )
        result.append(("class:sub-header", header_l))
        result.append(("class:sub-dim", ctx_str))
        result.append(("class:sub-dim", "\n"))

        # ── Líneas de subagentes: ParentName [emoji id]: tarea ─────────────
        for sub in subs[:8]:
            secs = sub.elapsed()
            if secs < 60:
                elapsed_str = f"{int(secs)}s"
            else:
                m, s = divmod(int(secs), 60)
                elapsed_str = f"{m}m{s:02d}s"

            if sub.status == "running":
                icon_style = "class:sub-running"
                st_str     = f"  {elapsed_str} ↓"
                st_style   = "class:sub-dim"
            elif sub.status == "done":
                icon_style = "class:sub-done"
                st_str     = f"  {elapsed_str} ✓"
                st_style   = "class:sub-done"
            else:
                icon_style = "class:sub-dim"
                st_str     = f"  {elapsed_str} ✗"
                st_style   = "class:sub-dim"

            # ctx% del subagente (0 si no disponible)
            sub_ctx = f" · {sub.ctx_pct}% ctx" if sub.ctx_pct > 0 else ""

            sub_label  = html.escape(f"{sub.agent_emoji} {sub.agent_id[:12]}")
            task_short = html.escape(sub.task)

            result.append(("class:sub-dim",  "  "))
            result.append((icon_style,       f"{agent_emoji} "))
            result.append(("class:sub-name", f"{agent_name} 💬 {sub_label}: "))
            result.append(("class:sub-dim",  task_short))
            result.append(("class:sub-dim",  st_str + sub_ctx))
            result.append((st_style,         ""))
            result.append(("class:sub-dim",  "\n"))

        return result

    def _get_status_text(self):
        if self._perm_mode:
            desc = self._perm_description or self._perm_tool
            return [
                ("class:spinner", f"  ◈  {desc}"),
                ("", "\n"),
                ("class:dim",     "    s (sí)  ·  n (no)  ·  siempre (auto sesión)"),
                ("", "\n "),
            ]
        s         = self._agent_loop._status_text
        plain_tip = self._plain_tip_cache
        # Durante compactación suprimir task panel — muestra solo la animación de compactación
        _compacting = getattr(self._agent_loop, "_compacting_ctx", False)
        tasks     = [] if _compacting else getattr(self._agent_loop, "_plan_tasks", [])

        if not s and not tasks:
            # Sin status activo: mostrar solo el tip (3 líneas)
            if plain_tip:
                return [
                    ("", " \n"),
                    ("", " \n"),
                    ("class:dim", f"   ⎿  Tip: {plain_tip}"),
                ]
            return [("", " \n \n ")]

        result: list[tuple[str, str]] = []

        # ── Línea 1: spinner ──────────────────────────────────────────────────
        if s:
            parts = s.split("\n", 1)
            # Limpiar Rich tags pero preservar marcadores \x01..\x03 para colores
            line1_raw = _RICH_TAG_RE.sub('', parts[0])
            line2_raw = parts[1].rstrip("\n") if len(parts) > 1 else ""
            result += _parse_status_line(f"  {line1_raw}", "class:spinner")
            result.append(("", "\n"))
            if not tasks and line2_raw:
                # Sin plan activo: mostrar barra de ctx/tokens en línea 2 con colores
                result += _parse_status_line(f"   {line2_raw}", "class:dim")
                result.append(("", "\n"))
            elif not tasks:
                result.append(("", " \n"))
            # Con tasks: line2 vacía (el spinner ya incluye tokens inline)
        else:
            result.append(("", " \n"))

        # ── Task list estilo Claude Code ──────────────────────────────────────
        if tasks:
            done_count = active_count = pending_count = 0
            for _t in tasks:
                _s = _t["status"]
                if _s == "done":     done_count    += 1
                elif _s == "active": active_count  += 1
                else:                pending_count += 1
            max_show      = 5

            # Ventana deslizante: anclar en la primera tarea activa/pendiente,
            # mostrando como máximo 1 done antes de ella para dar contexto.
            first_live = next(
                (i for i, t in enumerate(tasks)
                 if t["status"] in ("active", "pending")),
                len(tasks),
            )
            win_start = max(0, first_live - 1)
            win_end   = min(len(tasks), win_start + max_show)
            # Si la ventana es más pequeña que max_show, estirar hacia atrás
            if win_end - win_start < max_show:
                win_start = max(0, win_end - max_show)
            visible_tasks = tasks[win_start:win_end]

            for i, task in enumerate(visible_tasks):
                status = task["status"]
                icon   = "✔" if status == "done" else "◼" if status == "active" else "◻"
                style  = ("class:task-done"   if status == "done"
                          else "class:task-active" if status == "active"
                          else "class:dim")
                label  = task["text"]
                if i == 0:
                    # Primera fila visible: ⎿ connector
                    result.append(("class:dim", "  ⎿  "))
                    result.append((style, f"{icon} {label}"))
                else:
                    result.append((style, f"     {icon} {label}"))
                result.append(("", "\n"))

            # Summary estilo Claude Code
            if active_count > 0 or pending_count > 0:
                summary = f"      … +{pending_count} pending, {done_count} completed"
            else:
                summary = f"      … {done_count} completed  ✓"
            result.append(("class:dim", summary))
        else:
            # Sin tasks: tip en última línea
            if plain_tip:
                result.append(("class:dim", f"   ⎿  Tip: {plain_tip}"))
            else:
                result.append(("", " "))
        return result

    # ── Permisos via modo especial en el input ───────────────────────────────

    def _setup_permissions(self) -> None:
        """El ask_fn activa _perm_mode: el input area cambia para pedir permiso."""
        app = self

        def _ask_fn(tool: str, description: str) -> str:
            app._perm_tool        = tool
            app._perm_description = description
            app._perm_result      = ["n"]  # default seguro: denegar si no hay respuesta
            app._perm_event.clear()
            app._perm_mode        = True
            try:
                app._app.invalidate()
            except Exception as _inv_exc:
                # Si la UI no puede renderizar el diálogo → denegar automáticamente
                # para evitar ejecutar tools sin confirmación del usuario
                app._perm_mode = False
                import sys as _sys
                print(f"\n[perm] Error al mostrar diálogo para '{tool}': {_inv_exc}", file=_sys.stderr)
                return "n"

            # Bloquear el hilo del agente hasta que el usuario responda
            timed_out = not app._perm_event.wait(timeout=300.0)

            app._perm_mode = False
            try:
                app._app.invalidate()
            except Exception:
                pass

            if timed_out:
                # Timeout sin respuesta: denegar por seguridad
                return "n"

            return app._perm_result[0]

        self._agent_loop.permissions._ask_fn = _ask_fn

        # Cuando el usuario responde "siempre", persistir como "auto" en oocode.json
        _config = self._config
        _perms  = self._agent_loop.permissions

        def _persist_siempre(tool: str) -> None:
            bare = _perms._bare_name(tool)
            key  = bare if bare else tool
            _config.permissions[key] = "auto"
            try:
                _config.save()
                console.print(f"  [dim]  ✓ permiso '{key}' guardado en oocode.json[/dim]")
            except Exception:
                pass

        self._agent_loop.permissions._on_siempre = _persist_siempre

        # Registrar el input genérico en el agent_loop para que los plugins lo usen
        self._agent_loop._request_input = self.request_input

    def request_input(self, prompt: str, secret: bool = False) -> str:
        """Solicita input al usuario desde el prompt del TUI.
        El prompt se muestra en la ventana de conversación; si secret=True los caracteres
        se enmascaran con PasswordProcessor. Bloquea el hilo llamante hasta Enter.
        """
        console.print(f"\n  [bold cyan]?[/bold cyan]  [bold]{markup_escape(prompt)}[/bold]")

        self._input_prompt  = prompt
        self._input_secret  = secret
        self._input_result  = [""]
        self._input_event.clear()
        # Limpiar el buffer antes de entrar en input_mode: evita residuos de comandos anteriores
        # y desactiva AutoSuggest (vía ConditionalAutoSuggest → Condition)
        try:
            self._input_buf.reset()
        except Exception:
            pass
        self._input_mode    = True
        try:
            self._app.invalidate()
        except Exception:
            pass

        self._input_event.wait(timeout=300.0)

        self._input_mode   = False
        self._input_secret = False
        self._input_prompt = ""
        try:
            self._app.invalidate()
        except Exception:
            pass

        return self._input_result[0]

    # ── Prompt, toolbar, separador ───────────────────────────────────────────

    def _get_prompt(self):
        if self._perm_mode:
            return [
                ("class:dim",   "  "),
                ("class:agent", "¿Permitir?"),
                ("class:dim",   "  "),
                ("class:sep",   "→"),
                ("class:dim",   " "),
            ]
        if self._input_mode:
            icon = "🔑" if self._input_secret else "›"
            return [
                ("class:dim",   "  "),
                ("class:agent", icon),
                ("class:dim",   " "),
            ]
        return [
            ("class:dim",   "  "),
            ("class:arrow", "❯"),
            ("class:dim",   " "),
        ]

    def _get_toolbar(self):
        from ui.repl import _build_toolbar
        return _build_toolbar(self._agent_loop)

    def _sep_label_str(self) -> str:
        agent_id  = self._config.agent_id
        proj_path = getattr(self._config, "project_dir", None) or self._config.workspace
        project   = Path(proj_path).name
        return f"[ oocode ❯ {agent_id} ❯ {project} ]──"

    def _make_sep(self) -> VSplit:
        """Separador full-width: dashes (stretch) + etiqueta (ancho exacto a la derecha)."""
        def _sep_frags():
            label = self._sep_label_str()
            # Separar el texto [ ... ] de los ── finales para colorearlos distinto
            if label.endswith("──") and label.startswith("["):
                inner = label[:-2]     # "[ oocode ❯ ... ]"
                tail  = "──"
                return [("class:sep-label", inner), ("class:sep", tail)]
            return [("class:sep-label", label)]

        return VSplit([
            Window(
                content=FormattedTextControl(lambda: [("class:sep", "─" * 500)]),
                wrap_lines=False,
            ),
            Window(
                content=FormattedTextControl(_sep_frags),
                width=lambda: len(self._sep_label_str()),
                wrap_lines=False,
            ),
        ], height=1)

    # ── Altura dinámica del input (wrap-aware) ───────────────────────────────

    def _input_height(self) -> int:
        """Cuenta filas visuales del input considerando el wrap del terminal."""
        if self._input_mode and self._input_secret:
            return 1  # contraseñas: una sola fila visible
        tw = shutil.get_terminal_size((80, 24)).columns

        if self._perm_mode:
            prompt_w = 16  # "  ¿Permitir?  → "
        elif self._input_mode:
            prompt_w = 5   # "  🔑 " o "  › "
        else:
            prompt_w = 4  # "  ❯ "

        rows = 0
        for i, line in enumerate(self._input_buf.text.split('\n')):
            avail = max(8, tw - (prompt_w if i == 0 else 0))
            rows += max(1, (len(line) + avail - 1) // avail)

        return max(1, min(80, rows))

    # ── Historial de entrada ─────────────────────────────────────────────────

    def _reset_input_history(self) -> None:
        """Limpia el historial de entrada en memoria al iniciar nueva sesión.
        El fichero ~/.oocode/history no se modifica — solo se descarta lo cargado.
        Al pulsar ↑ solo aparecerán los comandos escritos en esta sesión.
        """
        from collections import deque
        buf = self._input_buf
        buf._working_lines = deque([""])
        # __working_index usa name-mangling → _Buffer__working_index
        buf._Buffer__working_index = 0  # type: ignore[attr-defined]
        if getattr(buf, '_load_history_task', None) is not None:
            try:
                buf._load_history_task.cancel()
            except Exception:
                pass
            buf._load_history_task = None

    # ── Scroll programático compartido (teclado + ratón) ────────────────────

    def _ri_logical_range(self) -> tuple | None:
        """Devuelve (top_logical, bottom_logical, page_h, total) desde render_info.

        visible_line_to_row_col: dict[screen_row → (logical_lineno, horiz_scroll)]
        Extraemos los logical_lineno del valor de cada par.
        """
        ri = getattr(self._output_window, 'render_info', None)
        if ri is None or not ri.visible_line_to_row_col:
            return None
        logical_lines = {lineno for lineno, _ in ri.visible_line_to_row_col.values()}
        if not logical_lines:
            return None
        top   = min(logical_lines)
        bot   = max(logical_lines)
        total = ri.ui_content.line_count
        return top, bot, max(1, len(logical_lines)), total

    def _scroll_invalidate(self) -> None:
        """Invalida con throttle de 50 ms para evitar renders excesivos en scroll rápido."""
        now = time.monotonic()
        if now - self._last_scroll_invalidate >= 0.05:
            self._last_scroll_invalidate = now
            try:
                self._app.invalidate()
            except Exception:
                pass

    def _do_scroll_up(self, lines: int = 3) -> None:
        info = self._ri_logical_range()
        if info is not None:
            top_logical, _, _, _ = info
            self._scroll_pos = max(0, top_logical - lines)
        else:
            self._scroll_pos = max(0, self._scroll_pos - lines)
        self._auto_scroll = False
        self._scroll_invalidate()

    def _do_scroll_down(self, lines: int = 3) -> None:
        if self._auto_scroll:
            return
        info = self._ri_logical_range()
        if info is not None:
            _, bot_logical, _, total = info
            if bot_logical >= total - 1:
                self._auto_scroll = True
                self._scroll_pos  = 0
            else:
                self._scroll_pos = min(total - 1, bot_logical + lines)
        else:
            self._scroll_pos += lines
        self._scroll_invalidate()

    # ── Build Application ────────────────────────────────────────────────────

    def _build_app(self) -> Application:
        from ui.repl import _build_style

        self._output_window = Window(
            content=_ScrollableOutput(
                self,
                text=self._get_output_text,
                focusable=False,
                show_cursor=False,
                get_cursor_position=self._get_output_cursor_pos,
            ),
            wrap_lines=True,
        )
        output_window = self._output_window

        status_window = Window(
            content=FormattedTextControl(self._get_status_text),
            height=self._status_window_height,
        )

        sep_top = self._make_sep()
        sep_bot = self._make_sep()

        input_window = Window(
            content=BufferControl(
                buffer=self._input_buf,
                input_processors=[
                    BeforeInput(self._get_prompt),
                    # Enmascara caracteres cuando se solicita input secreto (contraseñas)
                    ConditionalProcessor(
                        PasswordProcessor(),
                        Condition(lambda: self._input_secret),
                    ),
                ],
                focusable=True,
            ),
            height=self._input_height,
            wrap_lines=True,
        )

        # Panel de subagentes: aparece entre el separador inferior y la toolbar
        # cuando hay subagentes o equipos activos. Altura dinámica (0 = invisible).
        subagent_panel_window = Window(
            content=FormattedTextControl(self._get_subagent_panel_text),
            height=self._subagent_panel_height,
            style="",
        )

        # Toolbar: ahora 3 líneas (indicadores / LSP / keybindings)
        toolbar_window = Window(
            content=FormattedTextControl(self._get_toolbar),
            height=3,
            style="class:bottom-toolbar",
        )

        layout = Layout(
            FloatContainer(
                content=HSplit([
                    output_window,
                    status_window,
                    sep_top,
                    input_window,
                    sep_bot,
                    subagent_panel_window,   # panel dinámico (0 height cuando vacío)
                    toolbar_window,
                ]),
                floats=[
                    Float(
                        xcursor=True,
                        ycursor=True,
                        content=CompletionsMenu(max_height=12, scroll_offset=1),
                    ),
                ],
            ),
            focused_element=self._input_buf,
        )

        # Crear output con CPR desactivado: evita el warning "terminal doesn't
        # support cursor position requests" y el "Press ENTER to continue"
        # que aparece en terminales que no implementan la secuencia \x1b[6n.
        from prompt_toolkit.output import create_output
        _out = create_output()
        if hasattr(_out, 'enable_cpr'):
            _out.enable_cpr = False

        return Application(
            layout=layout,
            key_bindings=self._build_keybindings(),
            style=_build_style(self._agent_loop.rt.accent_color),
            full_screen=True,
            mouse_support=True,
            output=_out,
        )

    # ── Keybindings ──────────────────────────────────────────────────────────

    def _build_keybindings(self) -> KeyBindings:
        from ui.renderer import (
            print_keybindings, print_expand_output,
            print_status, print_ctx_status, _random_tip,
        )
        kb = KeyBindings()
        km = self._kb_manager

        def _key(action: str) -> str:
            return km.get(action)

        def _out(text: str) -> None:
            sys.stdout.write(text)
            sys.stdout.flush()

        # ── Ctrl+C ───────────────────────────────────────────────────────────
        @kb.add("c-c")
        def _(event):
            if self._perm_mode:
                self._perm_result[0] = "n"
                self._perm_event.set()
                return
            if self._input_mode:
                self._input_result[0] = ""
                self._input_event.set()
                console.print("  [dim]Cancelado.[/dim]")
                return
            if self._agent_thread and self._agent_thread.is_alive():
                self._agent_loop._kill_requested = True
                self._set_status("")
                _out("\n  ↯  Kill enviado al agente.\n")
            else:
                _out("\n  (Ctrl+C — escribe /exit para salir)\n")

        # ── Ctrl+D ───────────────────────────────────────────────────────────
        @kb.add("c-d")
        def _(event):
            if self._perm_mode:
                return
            if not (self._agent_thread and self._agent_thread.is_alive()):
                _out("\n  Hasta pronto.\n\n")
                event.app.exit()

        # ── Up/Down — historial o movimiento cursor en multi-línea ─────────
        @kb.add("up")
        def _(event):
            if self._perm_mode:
                return
            # Agente activo: ↑ desplaza el output hacia arriba (scroll)
            if self._agent_thread and self._agent_thread.is_alive():
                self._do_scroll_up(lines=3)
                return
            buf = self._input_buf
            if buf.document.cursor_position_row == 0:
                buf.history_backward()
            else:
                delta = buf.document.get_cursor_up_position()
                if delta != 0:
                    buf.cursor_position += delta

        @kb.add("down")
        def _(event):
            if self._perm_mode:
                return
            # Agente activo: ↓ desplaza el output hacia abajo (scroll)
            if self._agent_thread and self._agent_thread.is_alive():
                self._do_scroll_down(lines=3)
                return
            buf = self._input_buf
            doc = buf.document
            if doc.cursor_position_row >= doc.line_count - 1:
                buf.history_forward()
            else:
                delta = doc.get_cursor_down_position()
                if delta != 0:
                    buf.cursor_position += delta

        # ── PageUp/PageDown — scroll ─────────────────────────────────────────
        # _scroll_pos es siempre un índice de LÍNEA LÓGICA (no filas de pantalla).
        # Poniendo el cursor en esa línea, _scroll_when_linewrapping de prompt_toolkit
        # ajusta vertical_scroll para hacerla visible.
        # Nunca asignamos vertical_scroll directamente (se sobreescribe en cada render).
        # La rueda del ratón usa los mismos métodos _do_scroll_up/_do_scroll_down.

        @kb.add("pageup")
        def _(event):
            info = self._ri_logical_range()
            if info is not None:
                top_logical, _, page_h, _ = info
                self._scroll_pos = max(0, top_logical - page_h)
            else:
                self._scroll_pos = max(0, self._scroll_pos - 20)
            self._auto_scroll = False
            self._scroll_invalidate()

        @kb.add("pagedown")
        def _(event):
            if self._auto_scroll:
                return
            info = self._ri_logical_range()
            if info is not None:
                _, bot_logical, page_h, total = info
                if bot_logical >= total - 1:
                    self._auto_scroll = True
                    self._scroll_pos = 0
                else:
                    self._scroll_pos = min(total - 1, bot_logical + page_h)
            else:
                self._scroll_pos += 20
            self._scroll_invalidate()

        # ── Tab — completado al estilo bash ──────────────────────────────────
        @kb.add("tab")
        def _(event):
            if self._perm_mode:
                return
            buf = self._input_buf

            # Si ya hay menú abierto, navegar por él
            if buf.complete_state:
                buf.complete_next()
                return

            # Obtener completions sin abrir menú
            from prompt_toolkit.completion import CompleteEvent
            completions = list(
                self._completer.get_completions(
                    buf.document, CompleteEvent(completion_requested=True)
                )
            )

            if not completions:
                return

            if len(completions) == 1:
                # Un solo match: aplicar directamente, sin menú
                buf.apply_completion(completions[0])
                return

            # Múltiples matches: calcular el prefijo común y extraer solo los
            # caracteres NUEVOS más allá de lo que ya está escrito.
            #
            # PathCompleter propio: c.text = ruta completa, start_position = -N (N=len(token))
            #   → already_typed = N, new_chars = common[N:]
            # SlashCompleter: c.text = sufijo puro, start_position = 0
            #   → already_typed = 0, new_chars = common
            texts        = [c.text for c in completions]
            common       = _common_prefix(texts)
            already_typed = abs(completions[0].start_position)
            new_chars    = common[already_typed:]

            if new_chars:
                buf.insert_text(new_chars)
            else:
                # No hay extensión posible: abrir menú para que el usuario elija
                buf.start_completion(select_first=False)

        # ── Ctrl+A/E/K/W — edición estilo emacs ──────────────────────────────
        @kb.add("c-a")
        def _(event):
            if not self._perm_mode:
                self._input_buf.cursor_position = 0

        @kb.add("c-e")
        def _(event):
            if not self._perm_mode:
                self._input_buf.cursor_position = len(self._input_buf.text)

        @kb.add("c-k")
        def _(event):
            if not self._perm_mode:
                buf = self._input_buf
                buf.delete(count=len(buf.text) - buf.cursor_position)

        @kb.add("c-w")
        def _(event):
            if not self._perm_mode:
                buf = self._input_buf
                pos = buf.document.find_previous_word_beginning()
                if pos is not None and pos < 0:
                    buf.delete_before_cursor(count=-pos)

        # ── Ctrl+O — Expandir / colapsar salida del último turno ────────────
        @kb.add(_key("expand_output"))
        def _(event):
            if self._input_buf.text.strip() or self._perm_mode:
                return
            _out("\n")
            loop = self._agent_loop
            # Mostrar lint completo si el último análisis tuvo errores (siempre)
            try:
                from tools.hooks import get_last_lint_output
                lint_out = get_last_lint_output()
                if lint_out and "✗" in lint_out:
                    _out("  ── lint (detalle completo) ────────────────────────────\n")
                    for _ln in lint_out.splitlines():
                        _out(f"  {_ln}\n")
                    _out("\n")
            except Exception:
                pass
            # Toggle: si ya está expandido → colapsar; si no → expandir
            if getattr(loop, "_turn_expanded", False):
                loop._turn_expanded = False
                _out("  \x1b[2m(comprimido — ctrl+o para expandir)\x1b[0m\n\n")
            else:
                loop._turn_expanded = True
                tool_calls = list(loop._last_tool_calls)
                last_resp  = loop._last_response
                print_expand_output(tool_calls, last_resp)

        # ── Shift+Tab — completado hacia atrás o cicla permisos ──────────────
        @kb.add(_key("cycle_perms"))
        def _(event):
            if self._perm_mode:
                return
            if self._input_buf.complete_state:
                self._input_buf.complete_previous()
                return
            rt = self._agent_loop.rt
            idx = _PERM_CYCLE.index(rt.elevated) if rt.elevated in _PERM_CYCLE else 0
            next_mode = _PERM_CYCLE[(idx + 1) % len(_PERM_CYCLE)]
            rt.elevated = next_mode
            icon  = _PERM_ICONS[next_mode]
            label = _PERM_LABELS[next_mode]
            _out(f"\n  {icon}  Permisos: {next_mode}  ({label})\n\n")

        # ── Ctrl+L — Limpia output ───────────────────────────────────────────
        @kb.add(_key("clear_screen"))
        def _(event):
            with self._lock:
                self._output_parts.clear()
                self._output_chars = 0
                self._output_line_count = 0
                self._output_static_key += 1
            self._last_rendered_line_count = 0
            self._scroll_pos = 0
            self._auto_scroll = True
            self._output_window.vertical_scroll = 0
            event.app.invalidate()

        # ── Ctrl+T — Tip aleatorio ───────────────────────────────────────────
        @kb.add(_key("random_tip"))
        def _(event):
            if self._input_buf.text.strip() or self._perm_mode:
                return
            tip = _random_tip()
            self._current_tip = tip
            self._plain_tip_cache = _RICH_TAG_RE.sub('', tip)
            console.print(f"\n  [dim]✦[/dim]  {tip}\n")

        # ── F2 — Estado ──────────────────────────────────────────────────────
        @kb.add(_key("show_status"))
        def _(event):
            console.print()
            print_status(
                self._config, self._agent_loop.session,
                self._agent_loop.rt, self._agent_loop.context,
            )

        # ── F3 — Compactar (+ limpia buffer de pantalla para liberar memoria) ─
        @kb.add(_key("compact"))
        def _(event):
            if self._input_buf.text.strip() or self._perm_mode:
                return
            # No compactar mientras el agente está procesando un turno — evita
            # race condition entre _do_compact_impl y el while-loop de run().
            if self._agent_thread and self._agent_thread.is_alive():
                return
            with self._lock:
                self._output_parts.clear()
                self._output_chars = 0
                self._output_line_count = 0
                self._output_static_key += 1
            self._last_rendered_line_count = 0
            self._scroll_pos = 0
            self._auto_scroll = True
            self._output_window.vertical_scroll = 0
            event.app.invalidate()
            threading.Thread(
                target=self._agent_loop._do_compact,
                kwargs={"with_summary": True},
                daemon=True,
                name="oocode-compact",
            ).start()

        # ── F1 — Keybindings ─────────────────────────────────────────────────
        @kb.add(_key("show_keybindings"))
        def _(event):
            effective = km.effective()
            console.print()
            print_keybindings(effective)

        # ── F4 — Contexto ────────────────────────────────────────────────────
        @kb.add(_key("show_context"))
        def _(event):
            console.print()
            print_ctx_status(
                self._agent_loop.context, self._config, self._agent_loop.rt,
            )

        # ── Ctrl+P — Pegar imagen del portapapeles ────────────────────────────
        @kb.add("c-p")
        def _(event):
            """Pegar imagen del portapapeles (requiere xclip o wl-paste)."""
            if self._perm_mode or self._input_mode:
                return
            if not (self._config.vision_enabled
                    and self._agent_loop._model_supports_images()):
                _out(
                    "\n  ⚠  Visión no disponible: el modelo activo no soporta imágenes.\n"
                    "  Cambia de modelo con /model o activa visión en oocode.json.\n\n"
                )
                return
            import subprocess, tempfile
            # ── X11: xclip ──────────────────────────────────────────────────
            for mime, ext in [("image/png", "png"), ("image/jpeg", "jpg")]:
                try:
                    res = subprocess.run(
                        ["xclip", "-selection", "clipboard", "-target", mime, "-o"],
                        capture_output=True, timeout=5,
                    )
                    if res.returncode == 0 and len(res.stdout) > 100:
                        tmp = tempfile.NamedTemporaryFile(
                            suffix=f".{ext}", delete=False, dir="/tmp"
                        )
                        tmp.write(res.stdout)
                        tmp.close()
                        self._pending_images.append(tmp.name)
                        _out(
                            f"\n  🖼  Imagen pegada del portapapeles ({ext.upper()})  →  {tmp.name}\n"
                            f"  Escribe tu mensaje y pulsa Enter para enviarla.\n\n"
                        )
                        return
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass
            # ── Wayland: wl-paste ───────────────────────────────────────────
            for mime, ext in [("image/png", "png"), ("image/jpeg", "jpg")]:
                try:
                    res = subprocess.run(
                        ["wl-paste", "--type", mime],
                        capture_output=True, timeout=5,
                    )
                    if res.returncode == 0 and len(res.stdout) > 100:
                        tmp = tempfile.NamedTemporaryFile(
                            suffix=f".{ext}", delete=False, dir="/tmp"
                        )
                        tmp.write(res.stdout)
                        tmp.close()
                        self._pending_images.append(tmp.name)
                        _out(
                            f"\n  🖼  Imagen pegada del portapapeles ({ext.upper()})  →  {tmp.name}\n"
                            f"  Escribe tu mensaje y pulsa Enter para enviarla.\n\n"
                        )
                        return
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass
            _out(
                "\n  No hay imagen en el portapapeles o la herramienta no está disponible.\n"
                "  Instala:  apt install xclip  (X11)  o  apt install wl-clipboard  (Wayland)\n"
                "  También puedes adjuntar con:  /attach /ruta/imagen.png\n\n"
            )

        # ── Ctrl+Y — Copiar ──────────────────────────────────────────────────
        @kb.add(_key("copy_last"))
        def _(event):
            last = self._agent_loop._last_response
            if not last:
                _out("\n  No hay respuesta que copiar.\n\n")
                return
            import subprocess
            for tool in (
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ):
                try:
                    proc = subprocess.Popen(
                        tool, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
                    )
                    proc.communicate(last.encode())
                    _out("\n  ✓  Respuesta copiada al portapapeles.\n\n")
                    return
                except FileNotFoundError:
                    continue
            _out("\n  xclip/xsel no disponible. Instala xclip.\n\n")

        # ── Enter — Enviar (override del insert-newline por defecto en multiline) ──
        @kb.add("enter")
        def _(event):
            if self._perm_mode or self._input_mode:
                # Perm mode y input_mode: siempre enviar con Enter (incluso vacío)
                self._input_buf.validate_and_handle()
            elif self._input_buf.complete_state:
                self._input_buf.complete_state = None
            else:
                self._input_buf.validate_and_handle()

        # ── Escape+Enter — Salto de línea (solo fuera de modos especiales) ───
        @kb.add("escape", "enter")
        def _(event):
            if not self._perm_mode and not self._input_mode:
                self._input_buf.insert_text("\n")

        # ── Alt+← / Alt+→ ────────────────────────────────────────────────────
        @kb.add("escape", "left")
        def _(event):
            if not self._perm_mode:
                pos = self._input_buf.document.find_previous_word_beginning()
                if pos is not None and pos < 0:
                    self._input_buf.cursor_left(count=-pos)

        @kb.add("escape", "right")
        def _(event):
            if not self._perm_mode:
                pos = self._input_buf.document.find_next_word_ending()
                if pos:
                    self._input_buf.cursor_right(count=pos)

        return kb

    # ── Input handler ────────────────────────────────────────────────────────

    def _on_accept(self, buffer: Buffer) -> None:
        text = buffer.text.strip()
        # append_to_history=True guarda el texto en FileHistory antes de limpiar
        # el buffer, para que ↑ recupere la orden en la misma sesión aunque
        # el fichero de historial se haya borrado entre sesiones.
        _save_to_history = not self._perm_mode and not self._input_mode and bool(text)
        _history_file    = os.path.expanduser("~/.oocode/history")
        _history_missing = _save_to_history and not os.path.exists(_history_file)
        buffer.reset(append_to_history=_save_to_history)
        if _history_missing:
            def _verify_history():
                time.sleep(0.3)
                if os.path.exists(_history_file):
                    sys.stdout.write("  \x1b[2m→ historial recreado en ~/.oocode/history\x1b[0m\n")
                    sys.stdout.flush()
            threading.Thread(target=_verify_history, daemon=True, name="oocode-hist-check").start()

        # ── Modo permiso: el usuario responde s/n/siempre ────────────────────
        if self._perm_mode:
            choice = text.lower()
            if choice not in ("s", "n", "siempre"):
                choice = "s"
            self._perm_result[0] = choice
            console.print(f"  [dim]→ {choice}[/dim]")
            self._perm_event.set()
            return

        # ── Input genérico (vault, plugins) ──────────────────────────────────
        if self._input_mode:
            self._input_result[0] = text
            if self._input_secret:
                console.print("  [dim]········[/dim]")
            else:
                from rich.markup import escape as _esc2
                console.print(f"  [dim]{_esc2(text)}[/dim]")
            self._input_event.set()
            return

        if not text:
            return

        from rich.markup import escape as _esc
        console.print()
        # ── Mostrar mensaje del usuario con ❯ y colores diferenciados ────────
        lines = text.split('\n')
        for i, _line in enumerate(lines):
            if i == 0:
                console.print(
                    f"  [bold #00ff88]❯[/bold #00ff88]"
                    f"  [bold #d0ffd0]{_esc(_line)}[/bold #d0ffd0]"
                )
            else:
                console.print(f"     [bold #d0ffd0]{_esc(_line)}[/bold #d0ffd0]")
        console.print()

        lower = text.lower()

        # /attach <ruta> — adjuntar imagen al siguiente mensaje
        if lower.startswith("/attach"):
            rest = text[7:].strip()
            if not rest:
                sys.stdout.write(
                    "  Uso: /attach <ruta>  — adjunta imagen al siguiente mensaje\n"
                    "  Ctrl+P                — pegar imagen del portapapeles\n\n"
                )
                sys.stdout.flush()
                return
            path = os.path.expanduser(rest)
            if not os.path.isfile(path):
                sys.stdout.write(f"  ✗  Archivo no encontrado: {path}\n\n")
                sys.stdout.flush()
                return
            _, ext = os.path.splitext(path.lower())
            if ext not in _IMG_EXTS:
                sys.stdout.write(
                    f"  ✗  Formato no soportado: {ext}\n"
                    f"  Formatos válidos: {', '.join(sorted(_IMG_EXTS))}\n\n"
                )
                sys.stdout.flush()
                return
            self._pending_images.append(path)
            sys.stdout.write(
                f"  🖼  Imagen adjunta: {path}\n"
                f"  Escribe tu mensaje y pulsa Enter para enviar.\n\n"
            )
            sys.stdout.flush()
            return

        # /kill — sin esperar al agente
        if lower in ("/kill", "/kill all"):
            if self._agent_thread and self._agent_thread.is_alive():
                self._agent_loop._kill_requested = True
                self._set_status("")
                if lower == "/kill all" and self._agent_loop.scheduler:
                    for job in self._agent_loop.scheduler.all_jobs():
                        if job.get("enabled", True):
                            self._agent_loop.scheduler.toggle(job["id"])
                sys.stdout.write("  ↯  Kill enviado.\n")
                sys.stdout.flush()
            else:
                sys.stdout.write("  No hay agente en ejecución.\n")
                sys.stdout.flush()
            return

        # /exit
        if lower in ("/exit", "/quit", "/q"):
            if self._agent_thread and self._agent_thread.is_alive():
                self._agent_loop._kill_requested = True
                self._agent_thread.join(timeout=3.0)
            self._app.exit()
            return

        # Slash commands → en hilo daemon
        if text.startswith("/"):
            def _run_slash():
                from ui.commands import handle_slash
                result = handle_slash(text, self._agent_loop, self._config)
                if not result:
                    self._app.exit()

            threading.Thread(
                target=_run_slash, daemon=True, name="oocode-slash"
            ).start()
            return

        # Mensaje al agente
        if self._agent_thread and self._agent_thread.is_alive():
            sys.stdout.write(
                "  El agente anterior sigue activo. "
                "Usa /kill para interrumpirlo.\n"
            )
            sys.stdout.flush()
            return

        self._agent_loop._kill_requested = False
        # Al enviar un mensaje siempre volvemos a auto-scroll para seguir la respuesta
        self._auto_scroll = True
        self._scroll_pos = 0

        # Detectar rutas de imagen en el mensaje si el modelo soporta visión
        images: list[str] = []
        clean_text = text
        if self._config.vision_enabled and self._agent_loop._model_supports_images():
            img_matches = _IMG_PATH_RE.findall(text)
            if img_matches:
                for m in img_matches:
                    p = m.strip()
                    if not os.path.isabs(p) and not p.startswith("~"):
                        p = os.path.join(self._agent_loop.config.workspace, p)
                    images.append(p)
                # Eliminar las rutas del texto del mensaje
                clean_text = _IMG_PATH_RE.sub("", text).strip()
                if not clean_text:
                    clean_text = "Analiza la imagen."
            # Incluir imágenes pendientes (adjuntadas con /attach o Ctrl+P)
            if self._pending_images:
                images.extend(self._pending_images)
                self._pending_images.clear()
            if images:
                console.print(
                    f"  [dim cyan]🖼[/dim cyan]  "
                    f"[dim]{len(images)} imagen(es) adjunta(s)[/dim]"
                )
        elif self._pending_images:
            # Modelo sin visión pero hay imágenes pendientes — limpiar y avisar
            self._pending_images.clear()
            sys.stdout.write("  ⚠  El modelo activo no soporta imágenes. Imágenes descartadas.\n")
            sys.stdout.flush()

        self._agent_thread = threading.Thread(
            target=self._run_agent,
            args=(clean_text, images),
            daemon=True,
            name="oocode-agent",
        )
        self._agent_thread.start()

    def _trim_output_buffer(self) -> None:
        """Recorta _output_parts hasta _TRIM_TARGET_CHARS tras finalizar un turno.

        prompt_toolkit recalcula el word-wrap de TODOS los segmentos en cada render.
        Con 200K chars de output con syntax highlighting el recálculo puede tardar
        2-5s bloqueando el event loop. Recortar a 40K mantiene historial suficiente
        y garantiza que el primer render post-turno sea inmediato.
        """
        with self._lock:
            if self._output_chars <= self._TRIM_TARGET_CHARS:
                return
            # Eliminar partes del principio hasta llegar al objetivo
            while self._output_chars > self._TRIM_TARGET_CHARS and len(self._output_parts) > 1:
                removed = self._output_parts.pop(0)
                self._output_chars -= len(removed)
                self._output_line_count -= removed.count('\n')
            self._output_line_count = max(0, self._output_line_count)
            self._output_static_key += 1  # fuerza re-parse ANSI del buffer reducido
            self._output_cache_key += 1

    def _run_agent(self, text: str, images: list[str] = None) -> None:
        """Ejecuta el agente en segundo plano."""
        from ui.renderer import _random_tip
        _t1 = _random_tip()
        self._current_tip = _t1
        self._plain_tip_cache = _RICH_TAG_RE.sub('', _t1)
        try:
            self._agent_loop.run(text, images=images or [])
        finally:
            # Asegurar que el live block queda cerrado aunque el agente falle
            self._flush_live_block()
            _t2 = _random_tip()
            self._current_tip = _t2
            self._plain_tip_cache = _RICH_TAG_RE.sub('', _t2)
            self._agent_loop._pending_usage_line = ""
            # Recortar el buffer para que el primer render post-turno sea rápido
            self._trim_output_buffer()

    # ── Timer de parpadeo ────────────────────────────────────────────────────

    def _start_blink_timer(self) -> None:
        """Hilo daemon que invalida la UI cada 350ms para el ● pulsante y elapsed."""
        stop = self._blink_stop
        app  = self

        def _loop():
            while not stop.wait(0.35):
                needs_redraw = False
                with app._lock:
                    if app._live_block_active:
                        app._live_pulse_idx += 1
                        app._output_cache_key += 1
                        needs_redraw = True
                # También invalidar cuando hay status activo (spinner del agente)
                if not needs_redraw:
                    needs_redraw = bool(getattr(app._agent_loop, "_status_text", ""))
                if needs_redraw:
                    try:
                        app._app.invalidate()
                    except Exception:
                        pass

        threading.Thread(target=_loop, daemon=True, name="oocode-blink").start()

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Redirige stdout, muestra banner y arranca la Application."""
        writer     = _AppWriter(self)
        old_stdout = sys.stdout
        sys.stdout = writer

        from ui.renderer import print_banner
        print_banner(self._config)
        console.print(
            "\n  [dim]Escribe tu mensaje o "
            "[bold cyan]/help[/bold cyan] para ver los comandos.[/dim]\n"
        )

        self._start_blink_timer()
        try:
            self._app.run()
        finally:
            self._blink_stop.set()
            sys.stdout = old_stdout
            self._agent_loop._status_cb  = None
            self._agent_loop._status_text = ""
            if hasattr(self._agent_loop.permissions, "_ask_fn"):
                self._agent_loop.permissions._ask_fn = None
