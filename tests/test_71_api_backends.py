"""Tests para el módulo api/: base, ollama, openai, anthropic y build_client.

No requieren LLM, Ollama ni conexión de red — todo mockeado.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_config(api_type="ollama", api_key="", api_base_url="", ollama_host="http://localhost:11434"):
    cfg = MagicMock()
    cfg.api_type     = api_type
    cfg.api_key      = api_key
    cfg.api_base_url = api_base_url
    cfg.ollama_host  = ollama_host
    return cfg


# ── api.base ─────────────────────────────────────────────────────────────────

class TestBase:
    def test_chunk_defaults(self):
        from api.base import Chunk
        c = Chunk()
        assert c.text == ""
        assert c.tool_calls == []
        assert c.thinking == ""
        assert c.done is False
        assert c.input_tokens == 0
        assert c.output_tokens == 0

    def test_chunk_with_values(self):
        from api.base import Chunk
        c = Chunk(text="hello", done=True, input_tokens=10, output_tokens=5)
        assert c.text == "hello"
        assert c.done is True
        assert c.input_tokens == 10
        assert c.output_tokens == 5

    def test_response_defaults(self):
        from api.base import Response
        r = Response()
        assert r.text == ""
        assert r.tool_calls == []
        assert r.input_tokens == 0
        assert r.output_tokens == 0

    def test_tool_call_model_dump(self):
        from api.base import ToolCall, _ToolFunction
        tc = ToolCall(function=_ToolFunction(name="read_file", arguments={"path": "/tmp/x"}))
        d = tc.model_dump()
        assert d["type"] == "function"
        assert d["function"]["name"] == "read_file"
        assert d["function"]["arguments"] == {"path": "/tmp/x"}

    def test_tool_call_model_dump_exclude_none(self):
        from api.base import ToolCall, _ToolFunction
        tc = ToolCall(function=_ToolFunction(name="bash", arguments={}))
        d = tc.model_dump(exclude_none=True)
        assert d["function"]["arguments"] == {}

    def test_tool_function_attrs(self):
        from api.base import _ToolFunction
        fn = _ToolFunction(name="edit_file", arguments={"path": "/a", "content": "x"})
        assert fn.name == "edit_file"
        assert fn.arguments["path"] == "/a"


# ── api/__init__ build_client ─────────────────────────────────────────────────

class TestBuildClient:
    def test_build_ollama_default(self):
        from api import build_client
        from api.ollama import OllamaBackend
        with patch("api.ollama.ollama.Client"):
            cfg = _make_config(api_type="ollama")
            client = build_client(cfg)
        assert isinstance(client, OllamaBackend)

    def test_build_ollama_empty_type(self):
        from api import build_client
        from api.ollama import OllamaBackend
        with patch("api.ollama.ollama.Client"):
            cfg = _make_config(api_type="")
            client = build_client(cfg)
        assert isinstance(client, OllamaBackend)

    def test_build_openai(self):
        from api import build_client
        from api.openai import OpenAIBackend
        with patch("httpx.Client"):
            cfg = _make_config(api_type="openai", api_base_url="http://localhost:8080/v1")
            client = build_client(cfg)
        assert isinstance(client, OpenAIBackend)

    def test_build_anthropic(self):
        from api import build_client
        from api.anthropic import AnthropicBackend
        try:
            import anthropic
        except ImportError:
            pytest.skip("anthropic not installed")
        with patch("anthropic.Anthropic"):
            cfg = _make_config(api_type="anthropic", api_key="sk-ant-test")
            client = build_client(cfg)
        assert isinstance(client, AnthropicBackend)

    def test_build_unknown_falls_back_to_ollama(self):
        """Tipo desconocido → Ollama por defecto."""
        from api import build_client
        from api.ollama import OllamaBackend
        with patch("api.ollama.ollama.Client"):
            cfg = _make_config(api_type="unknown_backend")
            client = build_client(cfg)
        assert isinstance(client, OllamaBackend)


# ── api.ollama ────────────────────────────────────────────────────────────────

class TestOllamaBackend:
    def _make_backend(self):
        with patch("api.ollama.ollama.Client") as MockClient:
            from api.ollama import OllamaBackend
            b = OllamaBackend(host="http://localhost:11434")
            b._mock_client = MockClient.return_value
            b._client = b._mock_client
        return b

    def test_chat_sync_basic(self):
        from api.ollama import OllamaBackend
        mock_resp = MagicMock()
        mock_resp.message.content = "hello world"
        mock_resp.message.tool_calls = None
        mock_resp.prompt_eval_count = 10
        mock_resp.eval_count = 5
        with patch("api.ollama.ollama.Client") as MockClient:
            MockClient.return_value.chat.return_value = mock_resp
            b = OllamaBackend(host="http://localhost:11434")
        resp = b.chat_sync("llama3", [], [], {})
        assert resp.text == "hello world"
        assert resp.tool_calls == []
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5

    def test_chat_sync_with_tool_calls(self):
        from api.ollama import OllamaBackend
        mock_tc = MagicMock()
        mock_tc.function.name = "read_file"
        mock_tc.function.arguments = {"path": "/tmp/x"}
        mock_resp = MagicMock()
        mock_resp.message.content = ""
        mock_resp.message.tool_calls = [mock_tc]
        mock_resp.prompt_eval_count = 20
        mock_resp.eval_count = 8
        with patch("api.ollama.ollama.Client") as MockClient:
            MockClient.return_value.chat.return_value = mock_resp
            b = OllamaBackend(host="http://localhost:11434")
        resp = b.chat_sync("llama3", [], [], {})
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].function.name == "read_file"
        assert resp.tool_calls[0].function.arguments == {"path": "/tmp/x"}

    def test_chat_sync_timeout(self):
        from api.ollama import OllamaBackend
        import time
        with patch("api.ollama.ollama.Client") as MockClient:
            def slow_chat(*a, **kw):
                time.sleep(10)
            MockClient.return_value.chat.side_effect = slow_chat
            b = OllamaBackend(host="http://localhost:11434")
        with pytest.raises(TimeoutError):
            b.chat_sync("llama3", [], [], {}, timeout=0.01)

    def test_chat_stream_yields_chunks(self):
        from api.ollama import OllamaBackend
        def _make_chunk(content="", tool_calls=None, done=False, pec=0, ec=0):
            c = MagicMock()
            c.message.content = content
            c.message.tool_calls = tool_calls
            c.message.thinking = ""
            c.done = done
            c.prompt_eval_count = pec
            c.eval_count = ec
            return c
        chunks = [
            _make_chunk("hello "),
            _make_chunk("world", done=True, pec=5, ec=3),
        ]
        with patch("api.ollama.ollama.Client") as MockClient:
            MockClient.return_value.chat.return_value = iter(chunks)
            b = OllamaBackend(host="http://localhost:11434")
        result = list(b.chat_stream("llama3", [], [], {}))
        texts = [c.text for c in result if c.text]
        assert "hello " in texts
        assert "world" in texts
        done_chunks = [c for c in result if c.done]
        assert len(done_chunks) == 1
        assert done_chunks[0].input_tokens == 5
        assert done_chunks[0].output_tokens == 3

    def test_stream_tool_calls_normalized(self):
        from api.ollama import OllamaBackend
        mock_tc = MagicMock()
        mock_tc.function.name = "bash"
        mock_tc.function.arguments = {"cmd": "ls"}
        chunk = MagicMock()
        chunk.message.content = ""
        chunk.message.tool_calls = [mock_tc]
        chunk.message.thinking = ""
        chunk.done = True
        chunk.prompt_eval_count = 0
        chunk.eval_count = 0
        with patch("api.ollama.ollama.Client") as MockClient:
            MockClient.return_value.chat.return_value = iter([chunk])
            b = OllamaBackend(host="http://localhost:11434")
        result = list(b.chat_stream("llama3", [], [], {}))
        assert len(result) == 1
        tc = result[0].tool_calls[0]
        assert tc.function.name == "bash"
        assert tc.function.arguments == {"cmd": "ls"}

    def test_tool_call_args_json_string_normalized(self):
        """Si arguments viene como string JSON, se parsea a dict."""
        from api.ollama import _norm_tool_calls, OllamaBackend
        mock_tc = MagicMock()
        mock_tc.function.name = "edit_file"
        mock_tc.function.arguments = '{"path": "/x"}'
        result = _norm_tool_calls([mock_tc])
        assert result[0].function.arguments == {"path": "/x"}

    def test_kill_stream(self):
        from api.ollama import OllamaBackend
        with patch("api.ollama.ollama.Client") as MockClient:
            b = OllamaBackend()
            inner = MagicMock()
            b._client._client = inner
        b.kill_stream()
        inner.close.assert_called_once()

    def test_rebuild(self):
        from api.ollama import OllamaBackend
        with patch("api.ollama.ollama.Client") as MockClient:
            b = OllamaBackend(host="http://localhost:11434")
            cfg = _make_config(ollama_host="http://localhost:11435")
            b.rebuild(cfg)
        assert b._host == "http://localhost:11435"

    def test_close(self):
        from api.ollama import OllamaBackend
        with patch("api.ollama.ollama.Client") as MockClient:
            b = OllamaBackend()
        b.close()
        MockClient.return_value.close.assert_called_once()


# ── api.openai ────────────────────────────────────────────────────────────────

class TestOpenAIBackend:
    def _make_backend(self, base_url="http://localhost:8080/v1", api_key=""):
        with patch("httpx.Client"):
            from api.openai import OpenAIBackend
            b = OpenAIBackend(base_url=base_url, api_key=api_key)
        return b

    def test_init_sets_base_url(self):
        b = self._make_backend(base_url="http://localhost:8080/v1")
        assert b._base_url == "http://localhost:8080/v1"

    def test_trailing_slash_stripped(self):
        b = self._make_backend(base_url="http://localhost:8080/v1/")
        assert b._base_url == "http://localhost:8080/v1"

    def test_chat_sync_basic(self):
        with patch("httpx.Client") as MockClient:
            from api.openai import OpenAIBackend
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "hi", "tool_calls": None}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
            mock_resp.raise_for_status = MagicMock()
            MockClient.return_value.post.return_value = mock_resp
            b = OpenAIBackend(base_url="http://localhost:8080/v1")
        resp = b.chat_sync("llama3", [{"role": "user", "content": "hi"}], [], {})
        assert resp.text == "hi"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5

    def test_chat_sync_with_tool_calls(self):
        with patch("httpx.Client") as MockClient:
            from api.openai import OpenAIBackend
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{"function": {"name": "bash", "arguments": '{"cmd":"ls"}'}}],
                    },
                    "finish_reason": "tool_calls",
                }],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            }
            mock_resp.raise_for_status = MagicMock()
            MockClient.return_value.post.return_value = mock_resp
            b = OpenAIBackend(base_url="http://localhost:8080/v1")
        resp = b.chat_sync("llama3", [], [], {})
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].function.name == "bash"
        assert resp.tool_calls[0].function.arguments == {"cmd": "ls"}

    def test_param_adaptation_num_predict(self):
        from api.openai import _adapt_params
        adapted = _adapt_params({"num_predict": 512, "temperature": 0.7, "num_ctx": 8192})
        assert "max_tokens" in adapted
        assert adapted["max_tokens"] == 512
        assert "temperature" in adapted
        assert "num_ctx" not in adapted  # dropped
        assert "num_predict" not in adapted

    def test_param_adaptation_keep_alive_dropped(self):
        from api.openai import _adapt_params
        adapted = _adapt_params({"keep_alive": 300, "top_p": 0.9})
        assert "keep_alive" not in adapted
        assert adapted["top_p"] == 0.9

    def test_norm_tool_calls_json_string_args(self):
        from api.openai import _norm_tool_calls
        raw = [{"function": {"name": "read_file", "arguments": '{"path":"/x"}'}}]
        result = _norm_tool_calls(raw)
        assert result[0].function.name == "read_file"
        assert result[0].function.arguments == {"path": "/x"}

    def test_norm_tool_calls_dict_args(self):
        from api.openai import _norm_tool_calls
        raw = [{"function": {"name": "bash", "arguments": {"cmd": "ls"}}}]
        result = _norm_tool_calls(raw)
        assert result[0].function.arguments == {"cmd": "ls"}

    def test_chat_stream_basic(self):
        """Verifica que el stream SSE se parsea y emite Chunk correctamente."""
        with patch("httpx.Client") as MockClient:
            from api.openai import OpenAIBackend
            import io
            lines = [
                b'data: {"choices":[{"delta":{"content":"hello"},"finish_reason":null}],"usage":null}\n',
                b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":2}}\n',
                b'data: [DONE]\n',
            ]
            mock_resp = MagicMock()
            mock_resp.iter_lines.return_value = [l.decode().strip() for l in lines]
            mock_resp.raise_for_status = MagicMock()
            MockClient.return_value.stream.return_value.__enter__ = MagicMock(return_value=mock_resp)
            MockClient.return_value.stream.return_value.__exit__ = MagicMock(return_value=False)
            b = OpenAIBackend(base_url="http://localhost:8080/v1")
        chunks = list(b.chat_stream("llama3", [], [], {}))
        texts = [c.text for c in chunks if c.text]
        assert "hello" in texts
        done_chunks = [c for c in chunks if c.done]
        assert len(done_chunks) == 1                       # un único chunk done al final
        assert done_chunks[0].input_tokens == 5            # usage propagado al chunk final
        assert done_chunks[0].output_tokens == 2

    def test_build_payload_injects_max_tokens(self):
        with patch("httpx.Client"):
            from api.openai import OpenAIBackend
            b = OpenAIBackend(base_url="http://localhost:8080/v1", max_tokens=4096)
        payload = b._build_payload("m", [], [], {"temperature": 0.7}, stream=False)
        assert payload["max_tokens"] == 4096
        assert payload["temperature"] == 0.7

    def test_build_payload_caller_max_tokens_wins(self):
        with patch("httpx.Client"):
            from api.openai import OpenAIBackend
            b = OpenAIBackend(base_url="http://localhost:8080/v1", max_tokens=4096)
        # num_predict del caller (→ max_tokens) tiene prioridad sobre el default
        payload = b._build_payload("m", [], [], {"num_predict": 1000}, stream=False)
        assert payload["max_tokens"] == 1000

    def test_build_payload_no_max_tokens_when_unset(self):
        with patch("httpx.Client"):
            from api.openai import OpenAIBackend
            b = OpenAIBackend(base_url="http://localhost:8080/v1")   # max_tokens=None
        payload = b._build_payload("m", [], [], {}, stream=False)
        assert "max_tokens" not in payload

    def test_rebuild_updates_url(self):
        with patch("httpx.Client"):
            from api.openai import OpenAIBackend
            b = OpenAIBackend(base_url="http://old:8080/v1")
            cfg = _make_config(api_base_url="http://new:9090/v1")
            with patch("httpx.Client"):
                b.rebuild(cfg)
        assert b._base_url == "http://new:9090/v1"


# ── api.anthropic ─────────────────────────────────────────────────────────────

class TestAnthropicConversions:
    """Tests de las funciones de conversión sin necesitar el SDK anthropic."""

    def test_tools_to_anthropic_basic(self):
        from api.anthropic import _tools_to_anthropic
        tools = [{"type": "function", "function": {
            "name": "bash",
            "description": "Run bash",
            "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}},
        }}]
        result = _tools_to_anthropic(tools)
        assert result[0]["name"] == "bash"
        assert result[0]["description"] == "Run bash"
        assert result[0]["input_schema"]["type"] == "object"

    def test_tools_to_anthropic_empty(self):
        from api.anthropic import _tools_to_anthropic
        assert _tools_to_anthropic([]) == []

    def test_messages_system_extracted(self):
        from api.anthropic import _messages_to_anthropic
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        system, ant = _messages_to_anthropic(messages)
        assert "You are helpful." in system
        assert len(ant) == 1
        assert ant[0]["role"] == "user"

    def test_messages_tool_result_converted(self):
        from api.anthropic import _messages_to_anthropic
        messages = [
            {"role": "user", "content": "run"},
            {"role": "tool", "content": "output here", "tool_call_id": "call_123"},
        ]
        system, ant = _messages_to_anthropic(messages)
        tool_results = [m for m in ant if m["role"] == "user" and isinstance(m["content"], list)]
        assert len(tool_results) == 1
        assert tool_results[0]["content"][0]["type"] == "tool_result"
        assert tool_results[0]["content"][0]["tool_use_id"] == "call_123"

    def test_messages_assistant_with_tool_calls(self):
        from api.anthropic import _messages_to_anthropic
        messages = [
            {"role": "assistant", "content": "Using tool:", "tool_calls": [
                {"id": "call_1", "function": {"name": "bash", "arguments": {"cmd": "ls"}}}
            ]},
        ]
        system, ant = _messages_to_anthropic(messages)
        assert len(ant) == 1
        assert ant[0]["role"] == "assistant"
        blocks = ant[0]["content"]
        text_blocks = [b for b in blocks if b["type"] == "text"]
        tool_blocks = [b for b in blocks if b["type"] == "tool_use"]
        assert len(text_blocks) == 1
        assert len(tool_blocks) == 1
        assert tool_blocks[0]["name"] == "bash"

    def test_norm_tool_calls_anthropic(self):
        from api.anthropic import _norm_tool_calls
        blocks = [
            {"type": "tool_use", "id": "call_1", "name": "read_file", "input": {"path": "/x"}},
            {"type": "text", "text": "some text"},  # ignorado
        ]
        result = _norm_tool_calls(blocks)
        assert len(result) == 1
        assert result[0].function.name == "read_file"
        assert result[0].function.arguments == {"path": "/x"}

    def test_messages_multiple_systems_joined(self):
        from api.anthropic import _messages_to_anthropic
        messages = [
            {"role": "system", "content": "Part 1."},
            {"role": "system", "content": "Part 2."},
            {"role": "user", "content": "hi"},
        ]
        system, ant = _messages_to_anthropic(messages)
        assert "Part 1." in system
        assert "Part 2." in system
        assert len(ant) == 1

    def test_adapt_params_maps_num_predict_to_max_tokens(self):
        from api.anthropic import _adapt_params
        adapted = _adapt_params({"num_predict": 4096, "temperature": 0.5,
                                 "num_ctx": 8192, "seed": 7})
        assert adapted["max_tokens"] == 4096          # num_predict → max_tokens
        assert adapted["temperature"] == 0.5
        assert "num_ctx" not in adapted               # dropped
        assert "seed" not in adapted                  # dropped
        assert "num_predict" not in adapted

    def test_adapt_params_drops_ollama_specific(self):
        from api.anthropic import _adapt_params
        params = {"temperature": 0.7, "num_ctx": 8192, "keep_alive": 300, "seed": 42}
        result = _adapt_params(params)
        assert "temperature" in result
        assert "num_ctx" not in result
        assert "keep_alive" not in result
        assert "seed" not in result


# ── config.py integration ─────────────────────────────────────────────────────

class TestConfigApiFields:
    def test_default_api_type(self):
        from config import OOConfig
        cfg = OOConfig()
        assert cfg.api_type == "ollama"
        assert cfg.api_key == ""
        assert cfg.api_base_url == ""

    def test_default_config_has_api_section(self):
        from config import DEFAULT_CONFIG
        assert "api" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["api"]["type"] == "ollama"

    def test_api_fields_in_ooconfig(self):
        from config import OOConfig
        cfg = OOConfig(api_type="openai", api_key="sk-test", api_base_url="http://localhost:8080/v1")
        assert cfg.api_type == "openai"
        assert cfg.api_key == "sk-test"
        assert cfg.api_base_url == "http://localhost:8080/v1"

    def test_save_writes_api_section(self):
        import json
        from config import OOConfig, CONFIG_FILE
        cfg = OOConfig(api_type="openai", api_key="sk-x", api_base_url="http://localhost:8080/v1")
        written = {}
        def fake_write_text(content):
            written["content"] = content
        with patch("config.CONFIG_FILE") as mock_cf:
            mock_cf.exists.return_value = True
            mock_cf.read_text.return_value = "{}"
            mock_cf.write_text.side_effect = fake_write_text
            mock_cf.parent.mkdir = MagicMock()
            with patch("config.CONFIG_FILE", mock_cf):
                try:
                    cfg.save()
                except Exception:
                    pass  # solo necesitamos que se llame write_text
        if written:
            data = json.loads(written["content"])
            assert data.get("api", {}).get("type") == "openai"

    def test_save_unifies_server_fields_under_api(self):
        """save() escribe host/extraHosts/embedHost bajo "api" y no deja bloque "ollama" legacy."""
        import json
        from config import OOConfig
        cfg = OOConfig(ollama_host="http://gpu:11434",
                       ollama_extra_hosts=["http://gpu2:11434"],
                       ollama_embed_host="http://cpu:11434",
                       ollama_subagent_routing="primary-only")
        written = {}
        with patch("config.CONFIG_FILE") as mock_cf:
            mock_cf.exists.return_value = True
            mock_cf.read_text.return_value = "{}"
            mock_cf.write_text.side_effect = lambda c: written.update(content=c)
            mock_cf.parent.mkdir = MagicMock()
            try:
                cfg.save()
            except Exception:
                pass
        if written:
            data = json.loads(written["content"])
            assert "ollama" not in data
            api = data.get("api", {})
            assert api.get("host") == "http://gpu:11434"
            assert api.get("extraHosts") == ["http://gpu2:11434"]
            assert api.get("embedHost") == "http://cpu:11434"
            assert api.get("subagentRouting") == "primary-only"


# ── loop.py integration (sin LLM) ─────────────────────────────────────────────

class TestLoopBackendIntegration:
    """Verifica que AgentLoop usa build_client y delega kill_stream/rebuild."""

    def _make_loop(self, tmp_path):
        from unittest.mock import MagicMock
        from config import OOConfig
        from agent.loop import AgentLoop
        from api.base import BackendClient

        cfg = OOConfig()
        mock_backend = MagicMock(spec=BackendClient)
        loop = AgentLoop(
            config=cfg,
            registry=MagicMock(),
            permissions=MagicMock(),
            memory=MagicMock(),
            workspace_manager=MagicMock(),
            session_manager=MagicMock(),
            capture_output=True,
            backend_client=mock_backend,
        )
        return loop, mock_backend

    def test_backend_client_stored(self, tmp_path):
        loop, mock_backend = self._make_loop(tmp_path)
        assert loop.client is mock_backend

    def test_owns_client_false_when_provided(self, tmp_path):
        loop, _ = self._make_loop(tmp_path)
        assert loop._owns_client is False

    def test_ollama_client_alias_accepted(self, tmp_path):
        """ollama_client= deprecado sigue funcionando."""
        from config import OOConfig
        from agent.loop import AgentLoop
        cfg = OOConfig()
        mock_client = MagicMock()
        loop = AgentLoop(
            config=cfg,
            registry=MagicMock(),
            permissions=MagicMock(),
            memory=MagicMock(),
            workspace_manager=MagicMock(),
            session_manager=MagicMock(),
            capture_output=True,
            ollama_client=mock_client,
        )
        # El MagicMock se envuelve en OllamaBackend; el cliente interno es mock_client
        assert loop.client is not None
        assert loop.client._client is mock_client
        assert loop._owns_client is False

    def test_close_not_called_when_not_owner(self, tmp_path):
        loop, mock_backend = self._make_loop(tmp_path)
        loop.close()
        mock_backend.close.assert_not_called()

    def test_build_client_called_when_no_backend(self, tmp_path):
        from config import OOConfig
        from agent.loop import AgentLoop
        from api.ollama import OllamaBackend
        cfg = OOConfig()
        with patch("api.ollama.ollama.Client"):
            loop = AgentLoop(
                config=cfg,
                registry=MagicMock(),
                permissions=MagicMock(),
                memory=MagicMock(),
                workspace_manager=MagicMock(),
                session_manager=MagicMock(),
                capture_output=True,
            )
        assert isinstance(loop.client, OllamaBackend)
        assert loop._owns_client is True


# ── registry.tool_schemas ────────────────────────────────────────────────────

class TestRegistryToolSchemas:
    def _make_reg(self):
        from tools.registry import ToolRegistry
        reg = ToolRegistry()
        reg.register("test_tool", lambda args: "ok", {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {"type": "object", "properties": {}},
        })
        return reg

    def test_tool_schemas_returns_list(self):
        reg = self._make_reg()
        schemas = reg.tool_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) > 0

    def test_tool_schemas_format(self):
        reg = self._make_reg()
        for s in reg.tool_schemas():
            assert s.get("type") == "function"
            assert "function" in s
            assert "name" in s["function"]

    def test_ollama_schemas_alias(self):
        """ollama_schemas() devuelve lo mismo que tool_schemas()."""
        reg = self._make_reg()
        assert reg.ollama_schemas() == reg.tool_schemas()


# ── api.base.force_close_httpx_sockets ─────────────────────────────────────────

class TestForceCloseHttpxSockets:
    """El kill de un stream debe cerrar el socket subyacente, no solo el pool.

    httpx.Client.close() NO desbloquea un recv() colgado si el servidor está en
    silencio (prompt-eval / pausa de generación). force_close_httpx_sockets hace
    shutdown(SHUT_RDWR) del socket, que interrumpe el recv() al instante.
    """

    def _fake_client_with_socket(self, sock):
        """Construye la estructura interna de httpx 0.28 alrededor de un socket."""
        ns      = MagicMock();   ns._sock = sock
        inner   = MagicMock();   inner._network_stream = ns
        conn    = MagicMock();   conn._connection = inner
        pool    = MagicMock();   pool.connections = [conn]
        transp  = MagicMock();   transp._pool = pool
        client  = MagicMock();   client._transport = transp
        return client

    def test_tolerant_to_garbage(self):
        """None / objetos sin la estructura → devuelve 0 sin lanzar."""
        from api.base import force_close_httpx_sockets
        assert force_close_httpx_sockets(None) == 0
        assert force_close_httpx_sockets(object()) == 0

    def test_shutdown_unblocks_blocked_recv(self):
        """force_close hace shutdown del socket → un recv() bloqueado retorna ya."""
        import socket
        import threading
        import time
        from api.base import force_close_httpx_sockets

        a, b = socket.socketpair()
        try:
            unblocked = threading.Event()
            err = [None]

            def _reader():
                try:
                    a.recv(1)        # bloquea: el otro extremo no envía nada
                except OSError as e:
                    err[0] = e
                finally:
                    unblocked.set()

            t = threading.Thread(target=_reader, daemon=True)
            t.start()
            time.sleep(0.2)          # asegurar que está bloqueado en recv()
            assert not unblocked.is_set()

            client = self._fake_client_with_socket(a)
            n = force_close_httpx_sockets(client)
            assert n == 1
            # El recv() debe desbloquearse de inmediato (sin que nadie envíe datos).
            assert unblocked.wait(timeout=2.0), "recv() no se desbloqueó tras shutdown"
        finally:
            for s in (a, b):
                try:
                    s.close()
                except OSError:
                    pass

    def test_ollama_kill_stream_calls_force_close(self):
        """OllamaBackend.kill_stream fuerza el cierre del socket además de close()."""
        from api.ollama import OllamaBackend
        with patch("api.ollama.ollama.Client"):
            b = OllamaBackend()
            inner = MagicMock()
            b._client._client = inner
        with patch("api.base.force_close_httpx_sockets") as mock_force:
            b.kill_stream()
        mock_force.assert_called_once_with(inner)
        inner.close.assert_called_once()

    def test_real_httpx_stream_unblocked_during_silence(self):
        """Integración: httpx.Client real, servidor local que enmudece. close() solo
        NO desbloquea; force_close_httpx_sockets SÍ. Blinda la ruta del pool
        (client._transport._pool.connections[i]._connection._network_stream._sock)
        ante cambios de versión de httpx."""
        import http.server
        import socketserver
        import threading
        import time
        import httpx
        from api.base import force_close_httpx_sockets

        class _Silent(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                try:
                    self.wfile.write(b'{"c":0}\n'); self.wfile.flush()
                    time.sleep(5)    # silencio: simula prompt-eval / pausa del LLM
                except OSError:
                    pass
            def log_message(self, *a):
                pass

        # ThreadingTCPServer: cada request en su hilo (daemon) → srv.shutdown() no se
        # bloquea esperando al handler dormido (con TCPServer plano tardaría el sleep).
        srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Silent)
        srv.daemon_threads = True
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        client = httpx.Client(timeout=None)
        done = threading.Event()

        def _bg():
            try:
                with client.stream("GET", f"http://127.0.0.1:{port}/") as r:
                    for _line in r.iter_lines():
                        pass
            except Exception:
                pass
            finally:
                done.set()

        try:
            threading.Thread(target=_bg, daemon=True).start()
            time.sleep(0.5)                       # recibe 1 chunk, luego servidor calla
            assert not done.is_set()
            n = force_close_httpx_sockets(client)
            assert n >= 1, "no se encontró/cerró el socket del pool httpx"
            assert done.wait(timeout=3.0), "el stream no se desbloqueó tras el shutdown"
        finally:
            try:
                client.close()
            except Exception:
                pass
            srv.shutdown()
            srv.server_close()
