"""Tests del refactor D: helpers compartidos de listado de modelos (api/ollama) y
factories del stack de agente (agent/services).

Verifican que la consolidación no cambia el comportamiento y, sobre todo, que
build_embedding_client usa SIEMPRE effective_embed_host (regresión del bug de /switch
que creaba el EmbeddingClient con ollama_host crudo, rompiendo backends no-Ollama).
"""
from unittest.mock import patch, MagicMock

import api.ollama as ollama_mod
from agent.services import (
    build_workspace_manager, build_embedding_client, build_memory_system,
)
from config import OOConfig


# ── Stand-ins para el formato "objeto" del SDK de Ollama ───────────────────────

class _Det:
    def __init__(self, d):
        self._d = d

    def model_dump(self):
        return self._d


class _ModelObj:
    def __init__(self, model, size, details):
        self.model = model
        self.size = size
        self.details = details


class _ListObj:
    def __init__(self, models):
        self.models = models


# ── api/ollama: ollama_model_names ─────────────────────────────────────────────

class TestOllamaModelNames:
    def test_dict_format(self):
        fake = MagicMock()
        fake.list.return_value = {"models": [{"name": "m1"}, {"name": "m2"}]}
        with patch.object(ollama_mod.ollama, "Client", return_value=fake):
            assert ollama_mod.ollama_model_names("http://h") == ["m1", "m2"]

    def test_object_format(self):
        fake = MagicMock()
        fake.list.return_value = _ListObj([
            _ModelObj("qwen3", 100, _Det({"family": "qwen"})),
            _ModelObj("llama3", 200, _Det({"family": "llama"})),
        ])
        with patch.object(ollama_mod.ollama, "Client", return_value=fake):
            assert ollama_mod.ollama_model_names("http://h") == ["qwen3", "llama3"]

    def test_empty(self):
        fake = MagicMock()
        fake.list.return_value = {"models": []}
        with patch.object(ollama_mod.ollama, "Client", return_value=fake):
            assert ollama_mod.ollama_model_names("http://h") == []

    def test_passes_host(self):
        fake = MagicMock()
        fake.list.return_value = {"models": []}
        with patch.object(ollama_mod.ollama, "Client", return_value=fake) as MockClient:
            ollama_mod.ollama_model_names("http://myhost:11434")
        MockClient.assert_called_once_with(host="http://myhost:11434")


# ── api/ollama: list_ollama_models ─────────────────────────────────────────────

class TestListOllamaModels:
    def test_dict_format_rich(self):
        fake = MagicMock()
        fake.list.return_value = {"models": [
            {"name": "m1", "size": 5_000_000, "details": {"family": "qwen"}},
            {"name": "m2"},  # sin size/details
        ]}
        with patch.object(ollama_mod.ollama, "Client", return_value=fake):
            out = ollama_mod.list_ollama_models("http://h")
        assert out[0] == {"name": "m1", "size": 5_000_000, "details": {"family": "qwen"}}
        assert out[1] == {"name": "m2", "size": 0, "details": {}}

    def test_object_format_rich(self):
        fake = MagicMock()
        fake.list.return_value = _ListObj([
            _ModelObj("qwen3", 9_000_000, _Det({"family": "qwen", "quantization_level": "Q4"})),
        ])
        with patch.object(ollama_mod.ollama, "Client", return_value=fake):
            out = ollama_mod.list_ollama_models("http://h")
        assert out == [{"name": "qwen3", "size": 9_000_000,
                        "details": {"family": "qwen", "quantization_level": "Q4"}}]

    def test_object_without_details(self):
        m = _ModelObj("x", 1, None)
        fake = MagicMock()
        fake.list.return_value = _ListObj([m])
        with patch.object(ollama_mod.ollama, "Client", return_value=fake):
            out = ollama_mod.list_ollama_models("http://h")
        assert out == [{"name": "x", "size": 1, "details": {}}]


# ── agent/services: build_workspace_manager ────────────────────────────────────

def _ws_cfg(**over):
    base = dict(
        workspace="/tmp/ws", agent_name="Test", agent_emoji="🤖",
        ollama_host="http://h:11434", permissions={"bash": "ask"},
        ws_max_memory_lines=12, ws_max_daily_chars=400,
    )
    base.update(over)
    return OOConfig.model_construct(**base)


class TestBuildWorkspaceManager:
    def test_passes_config_fields(self):
        cfg = _ws_cfg()
        with patch("agent.services.WorkspaceManager") as MockWM:
            build_workspace_manager(cfg)
        args, kwargs = MockWM.call_args
        assert args[0] == "/tmp/ws"
        assert args[1] == "Test"
        assert args[2] == "🤖"
        assert kwargs["ollama_host"] == "http://h:11434"
        assert kwargs["permissions"] == {"bash": "ask"}
        assert kwargs["max_memory_lines"] == 12
        assert kwargs["max_daily_chars"] == 400

    def test_does_not_init(self):
        """La factory construye pero NO inicializa (el llamador decide)."""
        cfg = _ws_cfg()
        mock_wm = MagicMock()
        with patch("agent.services.WorkspaceManager", return_value=mock_wm):
            ws = build_workspace_manager(cfg)
        mock_wm.init.assert_not_called()
        assert ws is mock_wm


# ── agent/services: build_embedding_client (regresión /switch) ─────────────────

def _embed_cfg(**over):
    base = dict(
        api_type="ollama", ollama_host="http://h:11434", ollama_embed_host="",
        ollama_subagent_routing="round-robin", embed_model="nomic",
        embed_max_input_chars=12000, embed_disk_cache_enabled=False,
        embed_disk_cache_dir="/tmp/c", embed_disk_cache_max=100, embed_ram_cache_max=50,
    )
    base.update(over)
    return OOConfig.model_construct(**base)


class TestBuildEmbeddingClient:
    def test_ollama_uses_host(self):
        cfg = _embed_cfg(api_type="ollama", ollama_host="http://h:11434")
        with patch("agent.services.EmbeddingClient") as MockEC:
            build_embedding_client(cfg)
        assert MockEC.call_args.kwargs["host"] == "http://h:11434"

    def test_non_ollama_falls_back_to_local_not_chat_host(self):
        """REGRESIÓN /switch: con backend no-Ollama y sin embedHost, el host debe ser
        el Ollama local, NO la URL del servidor de chat (api.host)."""
        cfg = _embed_cfg(api_type="openai", ollama_host="http://openai.srv:8000",
                         api_base_url="http://openai.srv:8000", ollama_embed_host="")
        with patch("agent.services.EmbeddingClient") as MockEC:
            build_embedding_client(cfg)
        assert MockEC.call_args.kwargs["host"] == "http://localhost:11434"

    def test_dedicated_embed_host_wins(self):
        cfg = _embed_cfg(api_type="anthropic", ollama_embed_host="http://embed:11434")
        with patch("agent.services.EmbeddingClient") as MockEC:
            build_embedding_client(cfg)
        assert MockEC.call_args.kwargs["host"] == "http://embed:11434"

    def test_passes_embed_params(self):
        cfg = _embed_cfg()
        with patch("agent.services.EmbeddingClient") as MockEC:
            build_embedding_client(cfg)
        kw = MockEC.call_args.kwargs
        assert kw["model"] == "nomic"
        assert kw["max_input_chars"] == 12000
        assert kw["ram_cache_max"] == 50


# ── agent/services: build_memory_system ────────────────────────────────────────

def _mem_cfg(tmp_path, **over):
    base = dict(
        agent_id="main", memory_embed_enabled=True,
        embed_similarity_threshold=0.3, embed_snippet_chars=800, embed_top_k=3,
    )
    base.update(over)
    return OOConfig.model_construct(**base)


class TestBuildMemorySystem:
    def test_embed_enabled_passes_client(self, tmp_path, monkeypatch):
        import agent.services as svc
        monkeypatch.setattr(svc, "MEMORY_DIR", tmp_path)
        cfg = _mem_cfg(tmp_path, memory_embed_enabled=True)
        sentinel = object()
        with patch("agent.services.MemorySystem") as MockMS:
            build_memory_system(cfg, sentinel)
        assert MockMS.call_args.kwargs["embed_client"] is sentinel

    def test_embed_disabled_passes_none(self, tmp_path, monkeypatch):
        import agent.services as svc
        monkeypatch.setattr(svc, "MEMORY_DIR", tmp_path)
        cfg = _mem_cfg(tmp_path, memory_embed_enabled=False)
        with patch("agent.services.MemorySystem") as MockMS:
            build_memory_system(cfg, object())
        assert MockMS.call_args.kwargs["embed_client"] is None

    def test_creates_agent_memory_dir(self, tmp_path, monkeypatch):
        import agent.services as svc
        monkeypatch.setattr(svc, "MEMORY_DIR", tmp_path)
        cfg = _mem_cfg(tmp_path, agent_id="coding")
        with patch("agent.services.MemorySystem") as MockMS:
            build_memory_system(cfg, None)
        assert (tmp_path / "coding").is_dir()
        assert MockMS.call_args.kwargs["memory_dir"] == tmp_path / "coding"
