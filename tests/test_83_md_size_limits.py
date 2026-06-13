"""Tests para los límites de tamaño de OOCODE.md y MEMORY.md.

OOCODE.md se inyecta entero en el system prompt cada turno → aviso blando + techo
duro con marcador visible. MEMORY.md ya se recorta en mini (N bullets); en /ctx full
se aplica un tope de chars con marcador. Sin LLM ni proceso externo.
"""
import os
import tempfile
import unittest
from pathlib import Path


class TestOocodeMdLimits(unittest.TestCase):
    def setUp(self):
        from config import OOConfig
        self.d = Path(tempfile.mkdtemp())
        self.cfg = OOConfig()
        # workspace inexistente → load_oocode_md cae a project_dir; chdir al temp
        # para que el candidato cwd de _resolve_oocode_md sea también el temp (aislado).
        self.cfg.workspace = str(self.d / "ws_inexistente")
        self.cfg.project_dir = str(self.d)
        self.md = self.d / "OOCODE.md"
        self._cwd0 = os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self._cwd0)

    def test_defaults_present(self):
        self.assertEqual(self.cfg.ws_oocode_md_warn_kb, 8)
        self.assertEqual(self.cfg.ws_oocode_md_max_kb, 24)
        self.assertEqual(self.cfg.ws_memory_full_max_chars, 8000)

    def test_no_warning_under_threshold(self):
        self.md.write_text("X" * (2 * 1024))   # 2 KB < 8 KB
        self.assertIsNone(self.cfg.oocode_md_warning())

    def test_no_warning_when_missing(self):
        self.assertIsNone(self.cfg.oocode_md_warning())

    def test_warning_over_soft_threshold(self):
        self.md.write_text("X" * (10 * 1024))  # 10 KB > 8 KB
        w = self.cfg.oocode_md_warning()
        self.assertIsNotNone(w)
        self.assertIn("OOCODE.md", w)
        self.assertIn("10.0 KB", w)

    def test_loads_whole_under_hard_ceiling(self):
        # 10 KB: avisa pero NO trunca (carga entero)
        self.md.write_text("X" * (10 * 1024))
        txt = self.cfg.load_oocode_md()
        self.assertNotIn("truncado", txt)
        self.assertEqual(len(txt), 10 * 1024)

    def test_truncates_over_hard_ceiling(self):
        # 30 KB > techo 24 KB → trunca con marcador visible
        self.md.write_text("Y" * (30 * 1024))
        txt = self.cfg.load_oocode_md()
        self.assertIn("truncado", txt.lower())
        # No supera el techo + un pequeño margen del marcador
        self.assertLess(len(txt.encode("utf-8")), 24 * 1024 + 200)

    def test_warn_kb_zero_disables_warning(self):
        self.cfg.ws_oocode_md_warn_kb = 0
        self.md.write_text("X" * (50 * 1024))
        self.assertIsNone(self.cfg.oocode_md_warning())

    def test_max_kb_zero_disables_truncation(self):
        self.cfg.ws_oocode_md_max_kb = 0
        self.md.write_text("Z" * (50 * 1024))
        txt = self.cfg.load_oocode_md()
        self.assertNotIn("truncado", txt)
        self.assertEqual(len(txt), 50 * 1024)

    def test_round_trip_persists_new_keys(self):
        import json
        import config as _cfg_mod
        from config import OOConfig
        tmp = Path(tempfile.mktemp(suffix=".json"))
        orig = _cfg_mod.CONFIG_FILE
        try:
            _cfg_mod.CONFIG_FILE = tmp
            c = OOConfig()
            c.ws_oocode_md_warn_kb = 5
            c.ws_oocode_md_max_kb = 20
            c.ws_memory_full_max_chars = 1234
            c.save()
            raw = json.loads(tmp.read_text())
            self.assertEqual(raw["workspace"]["oocodeMdWarnKb"], 5)
            self.assertEqual(raw["workspace"]["oocodeMdMaxKb"], 20)
            self.assertEqual(raw["workspace"]["memoryFullMaxChars"], 1234)
            c2 = OOConfig.load()
            self.assertEqual(c2.ws_oocode_md_warn_kb, 5)
            self.assertEqual(c2.ws_oocode_md_max_kb, 20)
            self.assertEqual(c2.ws_memory_full_max_chars, 1234)
        finally:
            _cfg_mod.CONFIG_FILE = orig
            tmp.unlink(missing_ok=True)


class TestMemoryMdFullCap(unittest.TestCase):
    def _wm(self, cap):
        from workspace.manager import WorkspaceManager
        d = Path(tempfile.mkdtemp())
        (d / "IDENTITY.md").write_text("## Rol\nTest\n")
        (d / "MEMORY.md").write_text("# MEMORY\n" + ("- recuerdo largo\n" * 2000))
        return WorkspaceManager(str(d), memory_full_max_chars=cap), d

    def test_full_caps_large_memory(self):
        wm, _ = self._wm(8000)
        full = wm.load_full_context()
        self.assertIn("MEMORY.md truncado", full)

    def test_full_zero_cap_no_truncation(self):
        wm, _ = self._wm(0)
        full = wm.load_full_context()
        self.assertNotIn("MEMORY.md truncado", full)

    def test_full_small_memory_untouched(self):
        from workspace.manager import WorkspaceManager
        d = Path(tempfile.mkdtemp())
        (d / "IDENTITY.md").write_text("## Rol\nTest\n")
        (d / "MEMORY.md").write_text("# MEMORY\n- un solo recuerdo\n")
        wm = WorkspaceManager(str(d), memory_full_max_chars=8000)
        full = wm.load_full_context()
        self.assertNotIn("truncado", full)


if __name__ == "__main__":
    unittest.main()
