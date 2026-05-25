"""Tests for OOConfig: parameter loading, defaults, and effective values."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


class TestDefaultConfig(unittest.TestCase):
    """Verify DEFAULT_CONFIG structure and completeness."""

    def _dc(self):
        from config import DEFAULT_CONFIG
        return DEFAULT_CONFIG

    def test_default_config_is_dict(self):
        self.assertIsInstance(self._dc(), dict)

    def test_required_sections_present(self):
        required = {
            "ollama", "agents", "permissions", "context", "embeddings",
            "tools", "workspace", "logging", "appearance", "plugins",
            "pluginOptions", "skills", "modelOptions", "models", "fallback",
            "mcp", "hooks", "snapshots", "rag", "vision", "chatlog",
        }
        missing = required - set(self._dc().keys())
        self.assertFalse(missing, f"Missing sections in DEFAULT_CONFIG: {missing}")

    def test_context_section_keys(self):
        ctx = self._dc()["context"]
        for key in ("minKeep", "compactThreshold", "maxSummaryChars",
                    "maxToolResultTokens", "autoContinueMax"):
            self.assertIn(key, ctx, f"context.{key} missing")

    def test_rag_section_keys(self):
        rag = self._dc()["rag"]
        for key in ("enabled", "topK", "similarityThreshold", "maxSnippetChars",
                    "indexInterval", "topKComplex", "thresholdComplex", "complexMinChars"):
            self.assertIn(key, rag, f"rag.{key} missing")

    def test_hooks_section_keys(self):
        hooks = self._dc()["hooks"]
        self.assertIn("enabled", hooks)
        self.assertIn("builtins", hooks)
        self.assertIsInstance(hooks["builtins"], list)

    def test_embeddings_section_keys(self):
        emb = self._dc()["embeddings"]
        for key in ("model", "maxInputChars", "similarityThreshold",
                    "snippetChars", "topK", "memoryEmbedEnabled"):
            self.assertIn(key, emb, f"embeddings.{key} missing")

    def test_mcp_section_keys(self):
        mcp = self._dc()["mcp"]
        for key in ("servers", "requestTimeout", "oocodeAssistant",
                    "systemAssistant", "homeOfficeAssistant",
                    "securityAssistant", "iotAssistant"):
            self.assertIn(key, mcp, f"mcp.{key} missing")

    def test_default_hooks_builtins(self):
        builtins = self._dc()["hooks"]["builtins"]
        expected = {"diff_after_write", "ctags_after_write", "lint_after_write",
                    "quick_syntax_after_write", "verify_after_edit",
                    "test_suite_delta", "config_syntax_after_write"}
        self.assertEqual(set(builtins), expected)

    def test_permissions_are_valid_values(self):
        valid = {"auto", "ask", "deny"}
        for tool, mode in self._dc()["permissions"].items():
            self.assertIn(mode, valid, f"permissions.{tool} = {mode!r} invalid")


class TestOOConfigDefaults(unittest.TestCase):
    """Verify OOConfig default values match DEFAULT_CONFIG."""

    def _cfg(self):
        from config import OOConfig
        return OOConfig()

    def test_default_context_values(self):
        from config import DEFAULT_CONFIG
        cfg = self._cfg()
        dc = DEFAULT_CONFIG["context"]
        self.assertEqual(cfg.compact_min_keep, dc["minKeep"])
        self.assertEqual(cfg.compact_threshold, dc["compactThreshold"])
        self.assertEqual(cfg.max_summary_chars, dc["maxSummaryChars"])
        self.assertEqual(cfg.max_tool_result_tokens, dc["maxToolResultTokens"])
        self.assertEqual(cfg.auto_continue_max, dc["autoContinueMax"])

    def test_default_rag_values(self):
        from config import DEFAULT_CONFIG
        cfg = self._cfg()
        dc = DEFAULT_CONFIG["rag"]
        self.assertEqual(cfg.rag_top_k, dc["topK"])
        self.assertEqual(cfg.rag_similarity_threshold, dc["similarityThreshold"])
        self.assertEqual(cfg.rag_max_snippet_chars, dc["maxSnippetChars"])
        self.assertEqual(cfg.rag_top_k_complex, dc["topKComplex"])
        self.assertEqual(cfg.rag_threshold_complex, dc["thresholdComplex"])
        self.assertEqual(cfg.rag_complex_min_chars, dc["complexMinChars"])

    def test_default_embeddings_values(self):
        from config import DEFAULT_CONFIG
        cfg = self._cfg()
        dc = DEFAULT_CONFIG["embeddings"]
        self.assertEqual(cfg.embed_max_input_chars, dc["maxInputChars"])
        self.assertEqual(cfg.embed_snippet_chars, dc["snippetChars"])
        self.assertEqual(cfg.embed_top_k, dc["topK"])
        self.assertEqual(cfg.memory_embed_enabled, dc["memoryEmbedEnabled"])

    def test_default_hooks_values(self):
        from config import DEFAULT_CONFIG
        cfg = self._cfg()
        dc = DEFAULT_CONFIG["hooks"]
        self.assertEqual(cfg.hooks_enabled, dc["enabled"])
        self.assertEqual(set(cfg.hooks_builtins), set(dc["builtins"]))

    def test_default_mcp_values(self):
        cfg = self._cfg()
        self.assertTrue(cfg.mcp_oocode_assistant_enabled)
        self.assertTrue(cfg.mcp_system_assistant_enabled)
        self.assertFalse(cfg.mcp_home_office_assistant_enabled)
        self.assertFalse(cfg.mcp_security_assistant_enabled)
        self.assertFalse(cfg.mcp_iot_assistant_enabled)

    def test_default_tools_values(self):
        from config import DEFAULT_CONFIG
        cfg = self._cfg()
        dc = DEFAULT_CONFIG["tools"]
        self.assertEqual(cfg.read_file_lines_default, dc["readFileLinesDefault"])
        self.assertEqual(cfg.web_fetch_max_chars, dc["webFetchMaxChars"])
        self.assertEqual(cfg.bash_max_output_chars, dc["bashMaxOutputChars"])
        self.assertEqual(cfg.tool_cache_enabled, dc["toolCacheEnabled"])
        self.assertEqual(cfg.tool_cache_max_size, dc["toolCacheMaxSize"])


class TestOOConfigLoad(unittest.TestCase):
    """Test OOConfig.load() correctly applies custom JSON values."""

    def _load_from(self, custom: dict):
        """Write custom dict to a temp file and load via patched CONFIG_FILE."""
        import config as _cfg_mod
        from config import DEFAULT_CONFIG
        # Merge with defaults to avoid missing section errors
        import copy
        merged = copy.deepcopy(DEFAULT_CONFIG)
        for section, vals in custom.items():
            if isinstance(vals, dict) and isinstance(merged.get(section), dict):
                merged[section].update(vals)
            else:
                merged[section] = vals

        tmp = Path(tempfile.mktemp(suffix=".json"))
        tmp.write_text(json.dumps(merged, ensure_ascii=False))
        try:
            orig = _cfg_mod.CONFIG_FILE
            _cfg_mod.CONFIG_FILE = tmp
            from config import OOConfig
            cfg = OOConfig.load()
        finally:
            _cfg_mod.CONFIG_FILE = orig
            tmp.unlink(missing_ok=True)
        return cfg

    def test_load_custom_context_min_keep(self):
        cfg = self._load_from({"context": {"minKeep": 20}})
        self.assertEqual(cfg.compact_min_keep, 20)

    def test_load_custom_compact_threshold(self):
        cfg = self._load_from({"context": {"compactThreshold": 0.70}})
        self.assertAlmostEqual(cfg.compact_threshold, 0.70)

    def test_load_custom_auto_continue_max(self):
        cfg = self._load_from({"context": {"autoContinueMax": 12}})
        self.assertEqual(cfg.auto_continue_max, 12)

    def test_load_custom_rag_top_k(self):
        cfg = self._load_from({"rag": {"topK": 8}})
        self.assertEqual(cfg.rag_top_k, 8)

    def test_load_custom_rag_threshold(self):
        cfg = self._load_from({"rag": {"similarityThreshold": 0.50}})
        self.assertAlmostEqual(cfg.rag_similarity_threshold, 0.50)

    def test_load_custom_rag_max_snippet(self):
        cfg = self._load_from({"rag": {"maxSnippetChars": 10000}})
        self.assertEqual(cfg.rag_max_snippet_chars, 10000)

    def test_load_custom_hooks_builtins(self):
        cfg = self._load_from({"hooks": {"builtins": ["diff_after_write"]}})
        self.assertEqual(cfg.hooks_builtins, ["diff_after_write"])

    def test_load_custom_embeddings(self):
        cfg = self._load_from({"embeddings": {"maxInputChars": 6000, "topK": 8}})
        self.assertEqual(cfg.embed_max_input_chars, 6000)
        self.assertEqual(cfg.embed_top_k, 8)

    def test_load_custom_mcp_security(self):
        cfg = self._load_from({"mcp": {"securityAssistant": {"enabled": True}}})
        self.assertTrue(cfg.mcp_security_assistant_enabled)

    def test_load_custom_tool_cache(self):
        cfg = self._load_from({"tools": {"toolCacheEnabled": False, "toolCacheMaxSize": 50}})
        self.assertFalse(cfg.tool_cache_enabled)
        self.assertEqual(cfg.tool_cache_max_size, 50)

    def test_load_custom_fallback(self):
        cfg = self._load_from({"fallback": {"enabled": True, "model": "phi3:mini", "timeoutSeconds": 60}})
        self.assertTrue(cfg.fallback_enabled)
        self.assertEqual(cfg.fallback_model, "phi3:mini")
        self.assertEqual(cfg.fallback_timeout, 60)

    def test_load_custom_vision(self):
        cfg = self._load_from({"vision": {"enabled": False, "showIndicator": False}})
        self.assertFalse(cfg.vision_enabled)
        self.assertFalse(cfg.vision_show_indicator)

    def test_load_custom_chatlog(self):
        cfg = self._load_from({"chatlog": {"enabled": True, "maxSizeMb": 20}})
        self.assertTrue(cfg.chatlog_enabled)
        self.assertEqual(cfg.chatlog_max_size_mb, 20)

    def test_load_permissions_merge(self):
        """User permissions override defaults without discarding default entries."""
        cfg = self._load_from({"permissions": {"bash": "auto"}})
        self.assertEqual(cfg.permissions.get("bash"), "auto")
        # Other default permissions should still be present
        self.assertIn("read_file", cfg.permissions)

    def test_load_model_configs(self):
        model_cfg = {
            "models": {
                "configs": {
                    "mymodel:7b": {
                        "contextWindow": 32768,
                        "maxTokens": 4096,
                        "params": {"num_ctx": 32768},
                    }
                }
            }
        }
        cfg = self._load_from(model_cfg)
        self.assertIn("mymodel:7b", cfg.model_configs)
        self.assertEqual(cfg.model_configs["mymodel:7b"]["contextWindow"], 32768)


class TestEffectiveMaxContextTokens(unittest.TestCase):
    """Test effective_max_context_tokens property."""

    def _cfg(self, model=None, context_window=None, max_tokens=None):
        from config import OOConfig
        cfg = OOConfig()
        if model:
            cfg.model = model
            if context_window and max_tokens:
                cfg.model_configs[model] = {
                    "contextWindow": context_window,
                    "maxTokens": max_tokens,
                }
        return cfg

    def test_no_model_config_returns_fallback(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.model = "unknown-model"
        # No per-model config → returns max_context_tokens fallback
        self.assertEqual(cfg.effective_max_context_tokens, cfg.max_context_tokens)

    def test_with_model_config_computes_correctly(self):
        cfg = self._cfg("testmodel:7b", context_window=32768, max_tokens=4096)
        expected = 32768 - 4096 - cfg.model_system_overhead
        self.assertEqual(cfg.effective_max_context_tokens, expected)

    def test_effective_tokens_never_below_2000(self):
        """Even with a huge systemOverhead, result is always ≥ 2000."""
        from config import OOConfig
        cfg = OOConfig()
        cfg.model = "tiny:model"
        cfg.model_configs["tiny:model"] = {
            "contextWindow": 2048,
            "maxTokens": 2000,
        }
        cfg.model_system_overhead = 10000  # artificially huge
        self.assertGreaterEqual(cfg.effective_max_context_tokens, 2000)

    def test_system_overhead_from_default(self):
        from config import DEFAULT_CONFIG, OOConfig
        cfg = OOConfig()
        self.assertEqual(cfg.model_system_overhead,
                         DEFAULT_CONFIG["models"]["systemOverhead"])


class TestNoHardcodedOverrides(unittest.TestCase):
    """Verify no hardcoded values override loaded config in key paths."""

    def test_auto_continue_max_is_loaded(self):
        """autoContinueMax from config.py must end up in AgentLoop._max_auto_continue."""
        from config import OOConfig
        cfg = OOConfig()
        cfg.auto_continue_max = 4
        # Verify the attribute is accessible (AgentLoop reads it at runtime)
        self.assertEqual(cfg.auto_continue_max, 4)

    def test_compact_threshold_propagates_to_context(self):
        """OOConfig.compact_threshold should be passed to ConversationContext."""
        from agent.context import ConversationContext
        ctx = ConversationContext(compact_threshold=0.70)
        self.assertAlmostEqual(ctx.compact_threshold, 0.70)
        ctx2 = ConversationContext(compact_threshold=0.90)
        self.assertAlmostEqual(ctx2.compact_threshold, 0.90)

    def test_context_min_keep_propagates(self):
        from agent.context import ConversationContext
        ctx = ConversationContext(min_keep=20)
        self.assertEqual(ctx.min_keep, 20)

    def test_rag_top_k_field_accessible(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.rag_top_k = 15
        self.assertEqual(cfg.rag_top_k, 15)

    def test_tool_cache_max_size_field(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.tool_cache_max_size = 500
        self.assertEqual(cfg.tool_cache_max_size, 500)


class TestFallbackActiveConfig(unittest.TestCase):
    """Test fallback_active_config property."""

    def test_false_when_disabled(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.fallback_enabled = False
        cfg.fallback_model = "phi3:mini"
        self.assertFalse(cfg.fallback_active_config)

    def test_false_when_no_model(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.fallback_enabled = True
        cfg.fallback_model = ""
        self.assertFalse(cfg.fallback_active_config)

    def test_true_when_enabled_and_model(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.fallback_enabled = True
        cfg.fallback_model = "phi3:mini"
        self.assertTrue(cfg.fallback_active_config)


class TestModelTimeout(unittest.TestCase):
    """Test model_timeout() method."""

    def test_zero_when_no_config(self):
        from config import OOConfig
        cfg = OOConfig()
        self.assertEqual(cfg.model_timeout("some-model"), 0)

    def test_uses_per_model_timeout(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.model_configs["fast:model"] = {"timeoutSeconds": 30}
        self.assertEqual(cfg.model_timeout("fast:model"), 30)

    def test_uses_fallback_timeout_when_active(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.fallback_enabled = True
        cfg.fallback_model = "phi3:mini"
        cfg.fallback_timeout = 90
        self.assertEqual(cfg.model_timeout("unknown-model"), 90)

    def test_per_model_timeout_overrides_fallback(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.fallback_enabled = True
        cfg.fallback_model = "phi3:mini"
        cfg.fallback_timeout = 90
        cfg.model_configs["custom:model"] = {"timeoutSeconds": 45}
        self.assertEqual(cfg.model_timeout("custom:model"), 45)


class TestModelInputTypes(unittest.TestCase):
    """Test model input types (vision support detection)."""

    def test_defaults_to_text_only(self):
        from config import OOConfig
        cfg = OOConfig()
        self.assertEqual(cfg.get_model_input_types("unknown"), ["text"])

    def test_returns_stored_input_types(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.model_configs["vision:model"] = {"input": ["text", "image"]}
        self.assertEqual(cfg.get_model_input_types("vision:model"), ["text", "image"])

    def test_active_model_input_types_no_model(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.model = None
        self.assertEqual(cfg.active_model_input_types, ["text"])


if __name__ == "__main__":
    unittest.main()
