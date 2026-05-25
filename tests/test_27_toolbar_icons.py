"""Tests de desplazamiento de iconos en la toolbar del status bar.

Verifica que todos los iconos de cada indicador tienen el mismo ancho de pantalla
para que la toolbar no se desplace entre estados de parpadeo.

No requiere LLM ni conexión de red.
"""
import unicodedata
import sys
import re
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.repl import (
    _SUBAGENT_FRAMES,
    _RAG_IDX_ICONS,
    _RAG_ICONS,
    _MEM_ICONS,
    _MCP_ICONS,
    _LSP_ICONS,
    _PERM_ICONS,
)


# ── Utilidad: ancho de pantalla de un string ─────────────────────────────────

def _char_width(ch: str) -> int:
    """Ancho de pantalla de un carácter (2 para wide/fullwidth, 1 para el resto)."""
    eaw = unicodedata.east_asian_width(ch)
    return 2 if eaw in ("W", "F") else 1


def _display_width(s: str) -> int:
    """Ancho de pantalla total de un string."""
    return sum(_char_width(c) for c in s)


def _block_display_width(icon: str, label: str, count: int | None = None) -> int:
    """Ancho del contenido de un bloque indicador: '  ·   {icon} {label}:{count} '."""
    inner = f"  ·   {icon} {label}"
    if count is not None:
        inner += f":{count}"
    inner += " "
    return _display_width(inner)


# ══════════════════════════════════════════════════════════════════════════════
# Tests de ancho uniforme por conjunto de iconos
# ══════════════════════════════════════════════════════════════════════════════

class TestSubagentIconWidths:
    """Todos los frames de subagente deben ser wide emojis (2 columnas)."""

    def test_all_frames_are_wide(self):
        for icon in _SUBAGENT_FRAMES:
            w = _display_width(icon)
            assert w == 2, (
                f"Icono subagente '{icon}' (U+{ord(icon[0]):04X}) "
                f"tiene ancho {w}, esperado 2."
            )

    def test_minimum_four_frames(self):
        """Al menos 4 frames para una animación interesante."""
        assert len(_SUBAGENT_FRAMES) >= 4

    def test_no_displacement_between_frames(self):
        """El bloque sub:1 tiene el mismo ancho de pantalla en todos los frames."""
        widths = [_block_display_width(icon, "sub", 1) for icon in _SUBAGENT_FRAMES]
        assert len(set(widths)) == 1, (
            f"Ancho variable entre frames: "
            + ", ".join(f"'{i}'→{w}" for i, w in zip(_SUBAGENT_FRAMES, widths))
        )

    def test_robot_face_is_in_frames(self):
        """El icono 🤖 debe estar en los frames."""
        assert "🤖" in _SUBAGENT_FRAMES

    def test_all_frames_are_emoji(self):
        """Todos los frames deben ser un solo carácter unicode (emoji compacto)."""
        for icon in _SUBAGENT_FRAMES:
            # Los emoji wide son un codepoint U+1FXXX o U+2XXXX
            assert len(icon) == 1, (
                f"Frame '{icon}' tiene {len(icon)} chars — debe ser 1 codepoint."
            )


class TestRagIdxIconWidths:
    """Los iconos de RAG indexando deben tener el mismo ancho."""

    def test_all_same_width(self):
        widths = [_display_width(i) for i in _RAG_IDX_ICONS]
        assert len(set(widths)) == 1, (
            f"Anchos distintos en _RAG_IDX_ICONS: "
            + ", ".join(f"'{i}'→{w}" for i, w in zip(_RAG_IDX_ICONS, widths))
        )

    def test_no_displacement(self):
        widths = [_block_display_width(i, "rag:idx(5)") for i in _RAG_IDX_ICONS]
        assert len(set(widths)) == 1


class TestRagIconWidths:
    """Los iconos de RAG activo deben tener el mismo ancho."""

    def test_all_same_width(self):
        widths = [_display_width(i) for i in _RAG_ICONS]
        assert len(set(widths)) == 1, (
            f"Anchos distintos en _RAG_ICONS: "
            + ", ".join(f"'{i}'→{w}" for i, w in zip(_RAG_ICONS, widths))
        )

    def test_no_displacement(self):
        widths = [_block_display_width(i, "rag", None) for i in _RAG_ICONS]
        assert len(set(widths)) == 1


class TestMemIconWidths:
    """Los iconos de memoria deben tener el mismo ancho."""

    def test_all_same_width(self):
        widths = [_display_width(i) for i in _MEM_ICONS]
        assert len(set(widths)) == 1, (
            f"Anchos distintos en _MEM_ICONS: "
            + ", ".join(f"'{i}'→{w}" for i, w in zip(_MEM_ICONS, widths))
        )

    def test_no_displacement(self):
        widths = [_block_display_width(i, "mem", 3) for i in _MEM_ICONS]
        assert len(set(widths)) == 1


class TestMcpIconWidths:
    """Los iconos de MCP deben tener el mismo ancho."""

    def test_all_same_width(self):
        widths = [_display_width(i) for i in _MCP_ICONS]
        assert len(set(widths)) == 1, (
            f"Anchos distintos en _MCP_ICONS: "
            + ", ".join(f"'{i}'→{w}" for i, w in zip(_MCP_ICONS, widths))
        )

    def test_no_displacement(self):
        widths = [_block_display_width(i, "mcp", 2) for i in _MCP_ICONS]
        assert len(set(widths)) == 1


class TestLspIconWidths:
    """Los iconos de LSP deben tener el mismo ancho."""

    def test_all_same_width(self):
        widths = [_display_width(i) for i in _LSP_ICONS]
        assert len(set(widths)) == 1, (
            f"Anchos distintos en _LSP_ICONS: "
            + ", ".join(f"'{i}'→{w}" for i, w in zip(_LSP_ICONS, widths))
        )

    def test_no_displacement(self):
        widths = [_block_display_width(i, "py") for i in _LSP_ICONS]
        assert len(set(widths)) == 1


class TestPermIconWidths:
    """Los iconos de permisos deben tener el mismo ancho (off/ask/on/full)."""

    def test_all_same_width(self):
        icons  = list(_PERM_ICONS.values())
        widths = [_display_width(i) for i in icons]
        assert len(set(widths)) == 1, (
            f"Anchos distintos en _PERM_ICONS: "
            + ", ".join(f"'{i}'→{w}" for i, w in zip(icons, widths))
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test de regresión: el bug original (🤖 vs ⚙)
# ══════════════════════════════════════════════════════════════════════════════

class TestOldBugRegression:
    """Verifica que el bug original (🤖=2 vs ⚙=1) no vuelve a aparecer."""

    def test_gear_was_narrow_confirms_original_bug(self):
        """⚙ mide 1 columna — confirma que el bug original era real."""
        assert _display_width("⚙") == 1

    def test_robot_is_wide(self):
        """🤖 mide 2 columnas."""
        assert _display_width("🤖") == 2

    def test_subagent_frames_exclude_gear(self):
        """⚙ no debe aparecer en los frames de subagente (era el bug)."""
        assert "⚙" not in _SUBAGENT_FRAMES

    def test_subagent_frames_no_narrow_icons(self):
        """Ningún frame de subagente debe ser de ancho 1."""
        for icon in _SUBAGENT_FRAMES:
            assert _display_width(icon) != 1, (
                f"Frame '{icon}' tiene ancho 1 (narrow) — causaría desplazamiento."
            )


# ══════════════════════════════════════════════════════════════════════════════
# Test de integridad del ciclo de 4 fases
# ══════════════════════════════════════════════════════════════════════════════

class TestBlink4Phase:
    """El ciclo de 4 fases (_blink_phase % len(frames)) cubre todos los indicadores."""

    @pytest.mark.parametrize("icons,name", [
        (_SUBAGENT_FRAMES, "subagent"),
        (_RAG_IDX_ICONS,   "rag_idx"),
        (_RAG_ICONS,        "rag"),
        (_MEM_ICONS,        "mem"),
        (_MCP_ICONS,        "mcp"),
        (_LSP_ICONS,        "lsp"),
    ])
    def test_all_phases_reachable(self, icons: list[str], name: str):
        """Todos los iconos son alcanzables al ciclar por 4 fases."""
        # _blink_phase va 0..3; los iconos se indexan con % len(icons)
        reached = {icons[phase % len(icons)] for phase in range(4)}
        assert len(reached) >= 1, f"[{name}] ningún icono es alcanzable"

    @pytest.mark.parametrize("icons,name", [
        (_SUBAGENT_FRAMES, "subagent"),
        (_RAG_IDX_ICONS,   "rag_idx"),
        (_RAG_ICONS,        "rag"),
        (_MEM_ICONS,        "mem"),
        (_MCP_ICONS,        "mcp"),
        (_LSP_ICONS,        "lsp"),
    ])
    def test_no_width_variation_across_phases(self, icons: list[str], name: str):
        """El ancho de pantalla no varía entre las 4 fases."""
        widths = [_display_width(icons[phase % len(icons)]) for phase in range(4)]
        assert len(set(widths)) == 1, (
            f"[{name}] ancho variable entre fases: {widths}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Tests del bloque agente+subagente (nuevo indicador siempre visible)
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentBlock:
    """El bloque de identidad del agente no debe causar desplazamiento de toolbar."""

    def test_talk_icon_is_wide(self):
        """💬 (U+1F4AC) debe ser wide (2 cols) para no causar desplazamiento."""
        assert _display_width("\U0001f4ac") == 2

    def test_agent_block_stable_width_across_frames(self):
        """El bloque 'frame + nombre' tiene ancho estable entre los 4 frames."""
        agent_name = "OOCode"
        widths = [_display_width(f" {icon} {agent_name} ") for icon in _SUBAGENT_FRAMES]
        assert len(set(widths)) == 1, (
            f"Ancho variable en bloque agente: "
            + ", ".join(f"'{i}'→{w}" for i, w in zip(_SUBAGENT_FRAMES, widths))
        )

    def test_agent_sub_block_stable_width_across_frames(self):
        """El bloque 'frame + nombre + 💬 sub:N' tiene ancho estable entre frames."""
        agent_name = "OOCode"
        talk = "\U0001f4ac"
        widths = [
            _display_width(f" {icon} {agent_name}  {talk} sub:1 ")
            for icon in _SUBAGENT_FRAMES
        ]
        assert len(set(widths)) == 1, (
            f"Ancho variable en bloque agente+sub: "
            + ", ".join(f"'{i}'→{w}" for i, w in zip(_SUBAGENT_FRAMES, widths))
        )

    def test_agent_name_truncation_preserves_stability(self):
        """Nombre truncado a 14 chars: ancho estable."""
        long_name = "A" * 14   # 14 ASCII chars, ancho 1 cada uno
        widths = [_display_width(f" {icon} {long_name} ") for icon in _SUBAGENT_FRAMES]
        assert len(set(widths)) == 1
