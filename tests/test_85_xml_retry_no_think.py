"""Tests del helper _inject_no_think y su uso en los retries de tool calls XML.

Cuando un modelo (qwen3/qwen3.5 y similares) emite tool calls en su formato XML interno
y Ollama falla al parsearlo ("XML syntax error" / "tag incorrecto" / "unexpected EOF"),
_stream_response reintenta. El retry inyecta ` /no_think` en el último mensaje de usuario:
la generación sin thinking es más corta y determinística → menos probabilidad de volver a
malformar el XML. Estos tests cubren el helper de forma aislada (es @staticmethod).
"""
from agent.loop import AgentLoop


class TestInjectNoThink:
    def test_appends_to_last_user_message(self):
        msgs = [
            {"role": "system", "content": "reglas"},
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "respuesta"},
            {"role": "user", "content": "haz X"},
        ]
        out = AgentLoop._inject_no_think(msgs)
        # Solo el ÚLTIMO mensaje de usuario recibe el token
        assert out[-1]["content"] == "haz X /no_think"
        assert out[1]["content"] == "hola"   # el user anterior intacto
        assert out[0]["content"] == "reglas"

    def test_does_not_mutate_original(self):
        msgs = [{"role": "user", "content": "haz X"}]
        out = AgentLoop._inject_no_think(msgs)
        assert msgs[0]["content"] == "haz X", "no debe mutar la lista original"
        assert out[0]["content"] == "haz X /no_think"
        assert out is not msgs

    def test_no_user_message_is_noop(self):
        msgs = [
            {"role": "system", "content": "reglas"},
            {"role": "assistant", "content": "algo"},
        ]
        out = AgentLoop._inject_no_think(msgs)
        assert [m["content"] for m in out] == ["reglas", "algo"]

    def test_non_string_content_skipped_safely(self):
        # Mensajes con content multimodal (lista) no deben romper ni recibir el token
        msgs = [
            {"role": "user", "content": [{"type": "text", "text": "img"}]},
        ]
        out = AgentLoop._inject_no_think(msgs)
        assert out[0]["content"] == [{"type": "text", "text": "img"}]

    def test_only_last_user_when_multiple(self):
        msgs = [
            {"role": "user", "content": "primero"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "segundo"},
            {"role": "assistant", "content": "ok2"},
            {"role": "user", "content": "tercero"},
        ]
        out = AgentLoop._inject_no_think(msgs)
        assert out[0]["content"] == "primero"
        assert out[2]["content"] == "segundo"
        assert out[4]["content"] == "tercero /no_think"
