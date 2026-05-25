"""Tests para RAG top-K configurable por turno.

Cubre:
- _is_complex_query: False para mensajes cortos sin keywords
- _is_complex_query: True para mensajes largos (>= min_chars)
- _is_complex_query: True para mensajes con >= 2 keywords de autoedición
- _is_complex_query: False con solo 1 keyword (sin longitud suficiente)
- _rag_params_for_turn: devuelve base para queries cortas
- _rag_params_for_turn: devuelve boost para queries complejas
- _rag_params_for_turn: lee valores desde config
- WorkspaceRAG.query: top_k override por llamada (no modifica instancia)
- WorkspaceRAG.query: threshold override por llamada (no modifica instancia)
- WorkspaceRAG.context_snippet: acepta top_k y threshold por llamada
- DEFAULT_CONFIG: tiene topKComplex, thresholdComplex, complexMinChars
- OOConfig: campos rag_top_k_complex, rag_threshold_complex, rag_complex_min_chars
- OOConfig: serializa y deserializa los nuevos campos
"""
import sys, os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── _is_complex_query ─────────────────────────────────────────────────────────

class TestIsComplexQuery:
    def _fn(self, msg, min_chars=150):
        from agent.loop import _is_complex_query
        return _is_complex_query(msg, min_chars)

    def test_short_no_keywords_is_simple(self):
        assert self._fn("fix the bug", 150) is False

    def test_long_message_is_complex(self):
        assert self._fn("x" * 150, 150) is True

    def test_exactly_at_threshold_is_complex(self):
        assert self._fn("a" * 150, 150) is True

    def test_one_below_threshold_is_simple(self):
        assert self._fn("a" * 149, 150) is False

    def test_two_oocode_keywords_is_complex(self):
        assert self._fn("review the hook and tool configuration", 150) is True

    def test_one_keyword_short_is_simple(self):
        assert self._fn("update hook", 150) is False

    def test_oocode_specific_keywords(self):
        for pair in [
            ("hook", "tool"), ("loop", "agent"), ("mcp", "plugin"),
            ("registry", "config"), ("builtin", "oocode"),
            ("permission", "slash"),
        ]:
            msg = f"review the {pair[0]} and {pair[1]}"
            assert self._fn(msg, 150) is True, f"pair {pair} should be complex"

    def test_custom_min_chars(self):
        assert self._fn("short", 5) is True
        assert self._fn("short", 100) is False

    def test_empty_message_is_simple(self):
        assert self._fn("", 150) is False

    def test_whitespace_only_is_simple(self):
        assert self._fn("   ", 150) is False


# ── _rag_params_for_turn ──────────────────────────────────────────────────────

class TestRagParamsForTurn:
    def _make_loop(self, **cfg_overrides):
        """Crea un AgentLoop mínimo con config mock."""
        from unittest.mock import MagicMock
        loop = MagicMock()
        loop.config = MagicMock()
        loop.config.rag_top_k = cfg_overrides.get("rag_top_k", 5)
        loop.config.rag_similarity_threshold = cfg_overrides.get("rag_similarity_threshold", 0.40)
        loop.config.rag_top_k_complex = cfg_overrides.get("rag_top_k_complex", 10)
        loop.config.rag_threshold_complex = cfg_overrides.get("rag_threshold_complex", 0.35)
        loop.config.rag_complex_min_chars = cfg_overrides.get("rag_complex_min_chars", 150)
        return loop

    def _call(self, loop, msg):
        from agent.loop import AgentLoop
        return AgentLoop._rag_params_for_turn(loop, msg)

    def test_short_query_returns_base_params(self):
        loop = self._make_loop()
        top_k, thresh = self._call(loop, "fix bug")
        assert top_k == 5
        assert thresh == 0.40

    def test_long_query_returns_boost_params(self):
        loop = self._make_loop()
        top_k, thresh = self._call(loop, "a" * 200)
        assert top_k == 10
        assert abs(thresh - 0.35) < 0.001

    def test_oocode_keywords_returns_boost(self):
        loop = self._make_loop()
        top_k, thresh = self._call(loop, "update the hook and tool configuration")
        assert top_k == 10

    def test_reads_custom_config_values(self):
        loop = self._make_loop(
            rag_top_k=3, rag_similarity_threshold=0.50,
            rag_top_k_complex=15, rag_threshold_complex=0.25,
            rag_complex_min_chars=200,
        )
        # mensaje corto → base
        top_k, thresh = self._call(loop, "fix")
        assert top_k == 3
        assert abs(thresh - 0.50) < 0.001
        # mensaje largo → boost
        top_k2, thresh2 = self._call(loop, "x" * 200)
        assert top_k2 == 15
        assert abs(thresh2 - 0.25) < 0.001

    def test_no_config_uses_safe_defaults(self):
        loop = MagicMock()
        loop.config = None
        from agent.loop import AgentLoop
        top_k, thresh = AgentLoop._rag_params_for_turn(loop, "fix bug")
        assert top_k == 5
        assert abs(thresh - 0.40) < 0.001


# ── WorkspaceRAG per-call overrides ──────────────────────────────────────────

class TestWorkspaceRAGOverrides:
    def _make_rag(self, top_k=3, threshold=0.42):
        """Crea un WorkspaceRAG con embed_client mock."""
        from agent.workspace_rag import WorkspaceRAG
        import tempfile, pathlib
        tmpdir = tempfile.mkdtemp()
        ec = MagicMock()
        ec.is_available.return_value = True
        ec.embed.return_value = [0.1, 0.2, 0.3]
        # similarity siempre devuelve 0.50 para simplificar
        ec.similarity.return_value = 0.50
        rag = WorkspaceRAG(
            workspace=tmpdir,
            embed_client=ec,
            index_dir=pathlib.Path(tmpdir),
            top_k=top_k,
            similarity_threshold=threshold,
        )
        # Inyectamos 5 chunks de prueba directamente en el índice
        chunks = [
            {"path": f"{tmpdir}/f.py", "text": f"chunk {i}", "vec": [0.1, 0.2, 0.3], "line": i}
            for i in range(5)
        ]
        with rag._lock:
            rag._data["chunks"] = chunks
        return rag

    def test_query_respects_top_k_override(self):
        rag = self._make_rag(top_k=2, threshold=0.30)
        results = rag.query("test", top_k=4)
        assert len(results) == 4

    def test_query_instance_top_k_unchanged(self):
        rag = self._make_rag(top_k=2, threshold=0.30)
        rag.query("test", top_k=4)
        assert rag._top_k == 2  # instancia no modificada

    def test_query_threshold_override_filters(self):
        rag = self._make_rag(top_k=5, threshold=0.30)
        # similarity siempre 0.50 → todos pasan threshold=0.30
        results_low = rag.query("test", threshold=0.30)
        # con threshold=0.60 → ninguno pasa (similarity 0.50 < 0.60)
        results_high = rag.query("test", threshold=0.60)
        assert len(results_low) == 5
        assert len(results_high) == 0

    def test_query_instance_threshold_unchanged(self):
        rag = self._make_rag(top_k=5, threshold=0.30)
        rag.query("test", threshold=0.99)
        assert rag._threshold == 0.30  # instancia no modificada

    def test_context_snippet_top_k_override(self):
        rag = self._make_rag(top_k=2, threshold=0.30)
        snippet = rag.context_snippet("test", top_k=4)
        assert rag.last_hits == 4

    def test_context_snippet_threshold_override_excludes(self):
        rag = self._make_rag(top_k=5, threshold=0.30)
        # similarity=0.50 → excluidos con threshold=0.80
        snippet = rag.context_snippet("test", threshold=0.80)
        assert rag.last_hits == 0
        assert snippet == ""

    def test_context_snippet_no_override_uses_instance(self):
        rag = self._make_rag(top_k=3, threshold=0.30)
        rag.context_snippet("test")
        assert rag.last_hits == 3


# ── Config fields ─────────────────────────────────────────────────────────────

class TestRagConfigFields:
    def test_default_config_has_new_rag_keys(self):
        from config import DEFAULT_CONFIG
        rag = DEFAULT_CONFIG["rag"]
        assert "topKComplex" in rag
        assert "thresholdComplex" in rag
        assert "complexMinChars" in rag

    def test_default_values_match_spec(self):
        from config import DEFAULT_CONFIG
        rag = DEFAULT_CONFIG["rag"]
        assert rag["topKComplex"] >= 8       # al menos 8 (usuario pidió 8-10)
        assert rag["thresholdComplex"] <= 0.38  # más permisivo que el base
        assert rag["complexMinChars"] > 0

    def test_ooconfig_has_fields(self):
        from config import OOConfig
        cfg = OOConfig()
        assert hasattr(cfg, "rag_top_k_complex")
        assert hasattr(cfg, "rag_threshold_complex")
        assert hasattr(cfg, "rag_complex_min_chars")

    def test_ooconfig_defaults(self):
        from config import OOConfig
        cfg = OOConfig()
        assert cfg.rag_top_k_complex >= 8
        assert cfg.rag_threshold_complex <= 0.38
        assert cfg.rag_complex_min_chars > 0

    def test_ooconfig_serializes_new_fields(self):
        """save() escribe topKComplex/thresholdComplex/complexMinChars en la sección rag."""
        import tempfile, json, pathlib
        from unittest.mock import patch
        import config as _cfg_mod
        from config import OOConfig, DEFAULT_CONFIG

        tmp = pathlib.Path(tempfile.mkdtemp()) / "oocode.json"
        tmp.write_text(json.dumps(DEFAULT_CONFIG, indent=2))

        with patch.object(_cfg_mod, "CONFIG_FILE", tmp):
            cfg = OOConfig()
            cfg.rag_top_k_complex = 12
            cfg.rag_threshold_complex = 0.30
            cfg.rag_complex_min_chars = 200
            cfg.save()
            saved = json.loads(tmp.read_text())

        rag = saved.get("rag", {})
        assert rag.get("topKComplex") == 12
        assert abs(rag.get("thresholdComplex", 0) - 0.30) < 0.001
        assert rag.get("complexMinChars") == 200

    def test_ooconfig_deserializes_new_fields(self):
        """load() lee topKComplex/thresholdComplex/complexMinChars desde el JSON."""
        import tempfile, json, pathlib
        from unittest.mock import patch
        import config as _cfg_mod
        from config import OOConfig, DEFAULT_CONFIG

        data = dict(DEFAULT_CONFIG)
        data["rag"] = dict(DEFAULT_CONFIG["rag"])
        data["rag"].update({"topKComplex": 15, "thresholdComplex": 0.28, "complexMinChars": 100})

        tmp = pathlib.Path(tempfile.mkdtemp()) / "oocode.json"
        tmp.write_text(json.dumps(data))

        with patch.object(_cfg_mod, "CONFIG_FILE", tmp):
            cfg = OOConfig.load()

        assert cfg.rag_top_k_complex == 15
        assert abs(cfg.rag_threshold_complex - 0.28) < 0.001
        assert cfg.rag_complex_min_chars == 100
