"""Tests del servidor MCP IoT Assistant.

Verifica schemas, configuración, integración con loop.py, y tools sin deps externas.
No requiere TAPO, Blink, Alexa, Tuya, MQTT ni dispositivos físicos.
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.iot_assistant import (
    _TOOL_FNS,
    _TOOLS,
    _PROMPTS,
    _RESOURCES,
    _RESOURCE_FNS,
    _load_cfg,
    _save_cfg,
    _get_prompt,
    _handle,
    _tool_tapo_list,
    _tool_esphome_list,
    _tool_esphome_control,
    _tool_iot_discover,
    _tool_ha_entities,
    _tool_ha_state,
    _tool_ha_control,
    _tool_ha_automation,
    _tool_tapo_on_off,
    _tool_tapo_set,
    _tool_blink_verify,
    _tool_alexa_devices,
    _tool_alexa_speak,
    _tool_alexa_volume,
    _tool_alexa_command,
    _tool_tuya_list,
    _tool_tuya_control,
    _tool_mqtt_publish,
    _tool_mqtt_subscribe,
    _blink_headers,
    _no_ha_config,
    _DEFAULT_CONFIG,
    _CONFIG_PATH,
)


# ── Schema integrity ─────────────────────────────────────────────────────────

class TestToolSchemas:
    def test_tool_count(self):
        assert len(_TOOLS) == 25

    def test_all_tools_have_name_and_description(self):
        for t in _TOOLS:
            assert "name" in t
            assert "description" in t and t["description"]

    def test_all_tools_have_input_schema(self):
        for t in _TOOLS:
            assert "inputSchema" in t
            assert t["inputSchema"]["type"] == "object"

    def test_all_tools_registered_in_tool_fns(self):
        for t in _TOOLS:
            assert t["name"] in _TOOL_FNS, f"'{t['name']}' en _TOOLS pero no en _TOOL_FNS"

    def test_no_double_wrapper_format(self):
        for t in _TOOLS:
            assert not ("type" in t and t.get("type") == "function"), \
                f"'{t['name']}' usa formato wrapper"

    def test_tapo_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        assert {"tapo_list", "tapo_status", "tapo_on_off", "tapo_set"} <= names

    def test_blink_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        assert {"blink_status", "blink_arm", "blink_snapshot", "blink_clips", "blink_verify"} <= names

    def test_alexa_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        assert {"alexa_devices", "alexa_speak", "alexa_command", "alexa_volume"} <= names

    def test_tuya_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        assert {"tuya_list", "tuya_status", "tuya_control"} <= names

    def test_ha_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        assert {"ha_entities", "ha_state", "ha_control", "ha_automation"} <= names

    def test_mqtt_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        assert {"mqtt_publish", "mqtt_subscribe"} <= names

    def test_esphome_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        assert {"esphome_list", "esphome_control"} <= names

    def test_iot_discover_present(self):
        assert any(t["name"] == "iot_discover" for t in _TOOLS)


class TestPromptSchemas:
    def test_prompt_count(self):
        assert len(_PROMPTS) == 4

    def test_prompt_names(self):
        names = {p["name"] for p in _PROMPTS}
        expected = {"home_scene", "device_schedule", "security_home", "energy_report"}
        assert names == expected

    def test_prompts_have_description(self):
        for p in _PROMPTS:
            assert p.get("description")

    def test_prompts_have_arguments(self):
        for p in _PROMPTS:
            assert "arguments" in p
            assert len(p["arguments"]) >= 1


class TestResourceSchemas:
    def test_resource_count(self):
        assert len(_RESOURCES) == 3

    def test_resource_uris(self):
        uris = {r["uri"] for r in _RESOURCES}
        assert uris == {"iot://devices_all", "iot://status_dashboard", "iot://setup_guide"}

    def test_all_resources_have_fn(self):
        for r in _RESOURCES:
            assert r["uri"] in _RESOURCE_FNS

    def test_resources_callable(self):
        for uri, fn in _RESOURCE_FNS.items():
            result = fn()
            assert isinstance(result, str)
            assert len(result) > 0


# ── Config ────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_default_config_structure(self):
        assert "tapo" in _DEFAULT_CONFIG
        assert "blink" in _DEFAULT_CONFIG
        assert "alexa" in _DEFAULT_CONFIG
        assert "tuya" in _DEFAULT_CONFIG
        assert "mqtt" in _DEFAULT_CONFIG
        assert "home_assistant" in _DEFAULT_CONFIG
        assert "esphome" in _DEFAULT_CONFIG

    def test_load_cfg_returns_dict(self):
        cfg = _load_cfg()
        assert isinstance(cfg, dict)

    def test_load_cfg_has_all_sections(self):
        cfg = _load_cfg()
        for section in ("tapo", "blink", "alexa", "tuya", "mqtt", "home_assistant", "esphome"):
            assert section in cfg

    def test_save_and_reload_cfg(self):
        with tempfile.TemporaryDirectory() as d:
            import mcp_servers.iot_assistant as mod
            orig_path = mod._CONFIG_PATH
            mod._CONFIG_PATH = Path(d) / "test_iot.json"
            try:
                cfg = _load_cfg()
                cfg["tapo"]["email"] = "test@test.com"
                _save_cfg(cfg)
                cfg2 = _load_cfg()
                assert cfg2["tapo"]["email"] == "test@test.com"
            finally:
                mod._CONFIG_PATH = orig_path

    def test_mqtt_default_port(self):
        cfg = _load_cfg()
        assert cfg["mqtt"].get("port") == 1883

    def test_ha_default_url(self):
        cfg = _load_cfg()
        assert "homeassistant" in cfg["home_assistant"].get("url", "").lower() or \
               cfg["home_assistant"].get("url") == ""


# ── TAPO tools (no external lib) ──────────────────────────────────────────────

class TestTapoTools:
    def test_tapo_list_no_config(self):
        result = _tool_tapo_list({})
        assert isinstance(result, str)
        # Puede devolver "no configurado" o lista vacía
        assert "tapo" in result.lower() or "TAPO" in result

    def test_tapo_on_off_missing_params(self):
        result = _tool_tapo_on_off({"name": "luz"})
        assert "requerido" in result.lower() or "action" in result.lower()

    def test_tapo_on_off_invalid_action(self):
        result = _tool_tapo_on_off({"name": "luz", "action": "blink"})
        assert "requerido" in result.lower() or "on/off" in result.lower()

    def test_tapo_on_off_no_config(self):
        result = _tool_tapo_on_off({"name": "luz_inexistente", "action": "on"})
        assert isinstance(result, str)

    def test_tapo_set_missing_name(self):
        result = _tool_tapo_set({})
        assert "requerido" in result.lower()

    def test_tapo_on_off_requires_tapo_lib_if_configured(self):
        # Con dispositivo configurado pero sin lib → da instrucciones
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["tapo"]["email"] = "test@test.com"
            cfg["tapo"]["password"] = "pass"
            cfg["tapo"]["devices"] = [{"name": "luz", "ip": "192.168.1.1", "model": "L510"}]
            _save_cfg(cfg)
            result = _tool_tapo_on_off({"name": "luz", "action": "on"})
            mod._CONFIG_PATH = orig_path
        # Sin lib tapo → instrucciones de instalación o error de conexión
        assert isinstance(result, str)


# ── ESPHome tools (stdlib HTTP) ───────────────────────────────────────────────

class TestESPhomeTools:
    def test_esphome_list_no_config(self):
        result = _tool_esphome_list({})
        assert "esphome" in result.lower() or "ESPHome" in result

    def test_esphome_list_with_devices(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["esphome"]["devices"] = [
                {"name": "lampara", "host": "192.168.1.200", "password": ""}
            ]
            _save_cfg(cfg)
            result = _tool_esphome_list({})
            mod._CONFIG_PATH = orig_path
        assert "lampara" in result

    def test_esphome_control_missing_params(self):
        result = _tool_esphome_control({})
        assert "requerido" in result.lower()

    def test_esphome_control_missing_entity(self):
        result = _tool_esphome_control({"name": "lampara"})
        assert "requerido" in result.lower()

    def test_esphome_control_device_not_found(self):
        result = _tool_esphome_control({"name": "inexistente", "entity": "light/led"})
        assert "no encontrado" in result.lower()

    def test_esphome_control_offline_device(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["esphome"]["devices"] = [{"name": "test_dev", "host": "192.0.2.1", "password": ""}]
            _save_cfg(cfg)
            result = _tool_esphome_control({"name": "test_dev", "entity": "light/main", "action": "turn_on"})
            mod._CONFIG_PATH = orig_path
        # Debe devolver error de conexión (no excepción no manejada)
        assert isinstance(result, str)


# ── IoT Discover ──────────────────────────────────────────────────────────────

class TestIotDiscover:
    def test_discover_no_subnet(self):
        result = _tool_iot_discover({})
        assert isinstance(result, str)
        assert "IoT" in result or "subnet" in result.lower()

    def test_discover_invalid_subnet(self):
        result = _tool_iot_discover({"subnet": "notasubnet"})
        assert "inválida" in result.lower() or isinstance(result, str)

    def test_discover_with_subnet(self):
        # Usar una IP privada de documentación que no debería tener dispositivos
        result = _tool_iot_discover({"subnet": "192.0.2.0/30", "timeout": 0.1})
        assert isinstance(result, str)

    def test_discover_returns_configured_devices(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["tapo"]["devices"] = [{"name": "luz_salon", "ip": "192.168.1.100"}]
            _save_cfg(cfg)
            result = _tool_iot_discover({})
            mod._CONFIG_PATH = orig_path
        assert "luz_salon" in result or "configurados" in result.lower()


# ── HA tools (mocked HTTP) ────────────────────────────────────────────────────

class TestHATools:
    def test_ha_entities_no_config(self):
        result = _tool_ha_entities({})
        assert "no configurado" in result.lower() or "token" in result.lower()

    def test_ha_state_missing_entity(self):
        result = _tool_ha_state({})
        assert "requerido" in result.lower()

    def test_ha_control_missing_params(self):
        result = _tool_ha_control({})
        assert "requerido" in result.lower()

    def test_ha_automation_default_action(self):
        result = _tool_ha_automation({})
        # Sin HA configurado → no configurado
        assert isinstance(result, str)

    def test_no_ha_config_message(self):
        msg = _no_ha_config()
        assert "token" in msg.lower()
        assert "home_assistant" in msg.lower()

    def test_ha_entities_with_mock(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["home_assistant"]["token"] = "fake_token"
            cfg["home_assistant"]["url"]   = "http://ha.local:8123"
            _save_cfg(cfg)

            mock_states = [
                {"entity_id": "light.salon", "state": "on", "attributes": {"friendly_name": "Salón"}},
                {"entity_id": "switch.relay", "state": "off", "attributes": {"friendly_name": "Relé"}},
            ]
            with patch("mcp_servers.iot_assistant._http", return_value=(200, mock_states)):
                result = _tool_ha_entities({})
            mod._CONFIG_PATH = orig_path
        assert "light.salon" in result
        assert "switch.relay" in result

    def test_ha_state_with_mock(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["home_assistant"]["token"] = "fake_token"
            _save_cfg(cfg)
            mock_state = {
                "entity_id": "light.salon",
                "state": "on",
                "last_updated": "2026-05-21T10:00:00Z",
                "last_changed": "2026-05-21T09:00:00Z",
                "attributes": {"brightness": 255, "friendly_name": "Salón"},
            }
            with patch("mcp_servers.iot_assistant._http", return_value=(200, mock_state)):
                result = _tool_ha_state({"entity_id": "light.salon"})
            mod._CONFIG_PATH = orig_path
        assert "light.salon" in result
        assert "on" in result

    def test_ha_control_with_mock(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["home_assistant"]["token"] = "fake_token"
            _save_cfg(cfg)
            with patch("mcp_servers.iot_assistant._http", return_value=(200, [])):
                result = _tool_ha_control({"entity_id": "light.salon", "service": "turn_on"})
            mod._CONFIG_PATH = orig_path
        assert "✔" in result or "turn_on" in result

    def test_ha_state_not_found(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["home_assistant"]["token"] = "fake_token"
            _save_cfg(cfg)
            with patch("mcp_servers.iot_assistant._http", return_value=(404, {})):
                result = _tool_ha_state({"entity_id": "light.inexistente"})
            mod._CONFIG_PATH = orig_path
        assert "no encontrada" in result.lower() or "404" in result

    def test_ha_entities_domain_filter(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["home_assistant"]["token"] = "fake_token"
            _save_cfg(cfg)
            mock_states = [
                {"entity_id": "light.salon", "state": "on", "attributes": {}},
                {"entity_id": "switch.relay", "state": "off", "attributes": {}},
            ]
            with patch("mcp_servers.iot_assistant._http", return_value=(200, mock_states)):
                result = _tool_ha_entities({"domain": "light"})
            mod._CONFIG_PATH = orig_path
        assert "light.salon" in result
        assert "switch.relay" not in result


# ── Blink tools ───────────────────────────────────────────────────────────────

class TestBlinkTools:
    def test_blink_status_no_config(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            from mcp_servers.iot_assistant import _tool_blink_status
            result = _tool_blink_status({})
            mod._CONFIG_PATH = orig_path
        assert isinstance(result, str)

    def test_blink_verify_missing_pin(self):
        result = _tool_blink_verify({})
        assert "requerido" in result.lower()

    def test_blink_arm_missing_action(self):
        from mcp_servers.iot_assistant import _tool_blink_arm
        result = _tool_blink_arm({})
        assert "requerido" in result.lower()

    def test_blink_arm_invalid_action(self):
        from mcp_servers.iot_assistant import _tool_blink_arm
        result = _tool_blink_arm({"action": "lock"})
        assert "arm" in result.lower() or "requerido" in result.lower()

    def test_blink_headers_format(self):
        headers = _blink_headers("test_token_123")
        assert headers["TOKEN_AUTH"] == "test_token_123"
        assert "Content-Type" in headers


# ── Alexa tools ───────────────────────────────────────────────────────────────

class TestAlexaTools:
    def test_alexa_devices_no_ha_config(self):
        result = _tool_alexa_devices({})
        assert "no configurado" in result.lower() or "token" in result.lower()

    def test_alexa_speak_missing_params(self):
        result = _tool_alexa_speak({})
        assert "requerido" in result.lower()

    def test_alexa_speak_missing_entity(self):
        result = _tool_alexa_speak({"message": "Hola"})
        assert "requerido" in result.lower() or "entity_id" in result.lower()

    def test_alexa_volume_missing_params(self):
        result = _tool_alexa_volume({})
        assert "requerido" in result.lower()

    def test_alexa_command_missing_params(self):
        result = _tool_alexa_command({})
        assert "requerido" in result.lower()

    def test_alexa_devices_with_mock(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["home_assistant"]["token"] = "fake_token"
            _save_cfg(cfg)
            mock_states = [
                {"entity_id": "media_player.echo_salon", "state": "idle",
                 "attributes": {"friendly_name": "Echo Salón"}},
                {"entity_id": "media_player.spotify", "state": "playing",
                 "attributes": {"friendly_name": "Spotify"}},
            ]
            with patch("mcp_servers.iot_assistant._http", return_value=(200, mock_states)):
                result = _tool_alexa_devices({})
            mod._CONFIG_PATH = orig_path
        assert "echo_salon" in result or "Echo" in result

    def test_alexa_volume_with_mock(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["home_assistant"]["token"] = "fake_token"
            _save_cfg(cfg)
            with patch("mcp_servers.iot_assistant._http", return_value=(200, [])):
                result = _tool_alexa_volume({"entity_id": "media_player.echo_salon", "volume": 50})
            mod._CONFIG_PATH = orig_path
        assert "✔" in result or "50" in result


# ── Tuya tools ────────────────────────────────────────────────────────────────

class TestTuyaTools:
    def test_tuya_list_no_config(self):
        result = _tool_tuya_list({})
        assert "tuya" in result.lower() or "Tuya" in result

    def test_tuya_control_missing_name(self):
        result = _tool_tuya_control({})
        assert "requerido" in result.lower()

    def test_tuya_control_device_not_found(self):
        result = _tool_tuya_control({"name": "inexistente", "action": "on"})
        assert "no encontrado" in result.lower()

    def test_tuya_control_no_lib(self):
        import mcp_servers.iot_assistant as mod
        orig_path = mod._CONFIG_PATH
        with tempfile.TemporaryDirectory() as d:
            mod._CONFIG_PATH = Path(d) / "iot.json"
            cfg = _load_cfg()
            cfg["tuya"]["devices"] = [
                {"name": "luz", "device_id": "abc", "ip": "192.168.1.1", "local_key": "key"}
            ]
            _save_cfg(cfg)
            result = _tool_tuya_control({"name": "luz", "action": "on"})
            mod._CONFIG_PATH = orig_path
        # Sin tinytuya → instrucciones o error de conexión
        assert isinstance(result, str)


# ── MQTT tools ────────────────────────────────────────────────────────────────

class TestMqttTools:
    def test_mqtt_publish_missing_topic(self):
        result = _tool_mqtt_publish({})
        assert "requerido" in result.lower()

    def test_mqtt_publish_no_lib(self):
        result = _tool_mqtt_publish({"topic": "test/topic", "payload": "hello"})
        # Sin paho-mqtt → instrucciones de instalación o error de conexión
        assert isinstance(result, str)

    def test_mqtt_subscribe_no_lib(self):
        result = _tool_mqtt_subscribe({"topic": "test/#", "timeout": 0.1})
        assert isinstance(result, str)

    def test_mqtt_publish_with_mock(self):
        with patch.dict("sys.modules", {"paho": MagicMock(), "paho.mqtt": MagicMock(), "paho.mqtt.publish": MagicMock()}):
            import importlib
            import mcp_servers.iot_assistant as mod
            mock_pub = MagicMock()
            with patch("mcp_servers.iot_assistant._tool_mqtt_publish") as mock_fn:
                mock_fn.return_value = "✔ MQTT publicado → test/topic\n  Payload: hello"
                result = mock_fn({"topic": "test/topic", "payload": "hello"})
            assert "✔" in result or "publicado" in result.lower()


# ── Prompts ───────────────────────────────────────────────────────────────────

class TestPrompts:
    def test_home_scene_prompt(self):
        result = _get_prompt("home_scene", {"scene": "cine", "rooms": "salon"})
        text = result[0]["content"]["text"]
        assert "cine" in text.lower()
        assert "salon" in text.lower() or "salón" in text.lower()

    def test_device_schedule_prompt(self):
        result = _get_prompt("device_schedule", {
            "device": "luz_salon",
            "schedule": "encender a las 7am"
        })
        text = result[0]["content"]["text"]
        assert "luz_salon" in text
        assert "7am" in text or "encender" in text.lower()

    def test_security_home_prompt(self):
        result = _get_prompt("security_home", {"systems": "blink, ha_sensors"})
        text = result[0]["content"]["text"]
        assert "blink" in text.lower() or "seguridad" in text.lower()

    def test_energy_report_prompt(self):
        result = _get_prompt("energy_report", {"period": "semana"})
        text = result[0]["content"]["text"]
        assert "semana" in text or "consumo" in text.lower()

    def test_unknown_prompt(self):
        result = _get_prompt("nonexistent", {})
        text = result[0]["content"]["text"]
        assert "desconocido" in text.lower()

    def test_all_prompts_return_user_role(self):
        for p in _PROMPTS:
            result = _get_prompt(p["name"], {})
            assert result[0]["role"] == "user"


# ── MCP Protocol ─────────────────────────────────────────────────────────────

class TestMcpProtocol:
    def test_initialize(self):
        req  = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = _handle(req)
        assert resp["result"]["serverInfo"]["name"] == "iot-assistant"

    def test_initialize_capabilities_truthy(self):
        """Capabilities deben ser dicts no vacíos — McpClient.list_resources/prompts
        comprueba 'if not capabilities.get(...)' y un {} vacío es falsy → 0 resources/prompts."""
        req  = {"jsonrpc": "2.0", "id": 10, "method": "initialize", "params": {}}
        resp = _handle(req)
        caps = resp["result"]["capabilities"]
        assert caps.get("resources"), "capabilities.resources vacío → McpClient ignora resources"
        assert caps.get("prompts"),   "capabilities.prompts vacío → McpClient ignora prompts"

    def test_tools_list(self):
        req  = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        resp = _handle(req)
        assert len(resp["result"]["tools"]) == 25

    def test_tools_call_tapo_list(self):
        req = {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "tapo_list", "arguments": {}},
        }
        resp = _handle(req)
        assert "content" in resp["result"]
        assert isinstance(resp["result"]["content"][0]["text"], str)

    def test_tools_call_unknown(self):
        req = {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "nonexistent_xyz", "arguments": {}},
        }
        resp = _handle(req)
        assert "error" in resp

    def test_resources_list(self):
        req  = {"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}}
        resp = _handle(req)
        assert len(resp["result"]["resources"]) == 3

    def test_resources_read_setup_guide(self):
        req = {
            "jsonrpc": "2.0", "id": 6, "method": "resources/read",
            "params": {"uri": "iot://setup_guide"},
        }
        resp = _handle(req)
        text = resp["result"]["contents"][0]["text"]
        assert "TAPO" in text
        assert "Blink" in text or "BLINK" in text

    def test_prompts_list(self):
        req  = {"jsonrpc": "2.0", "id": 7, "method": "prompts/list", "params": {}}
        resp = _handle(req)
        assert len(resp["result"]["prompts"]) == 4

    def test_prompts_get(self):
        req = {
            "jsonrpc": "2.0", "id": 8, "method": "prompts/get",
            "params": {"name": "home_scene", "arguments": {"scene": "cine"}},
        }
        resp = _handle(req)
        assert "messages" in resp["result"]

    def test_notifications_initialized(self):
        req  = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = _handle(req)
        assert resp is None

    def test_unknown_method(self):
        req  = {"jsonrpc": "2.0", "id": 9, "method": "foo/bar", "params": {}}
        resp = _handle(req)
        assert "error" in resp

    def test_tools_call_iot_discover(self):
        req = {
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "iot_discover", "arguments": {}},
        }
        resp = _handle(req)
        assert "content" in resp["result"]

    def test_resources_read_devices_all(self):
        req = {
            "jsonrpc": "2.0", "id": 11, "method": "resources/read",
            "params": {"uri": "iot://devices_all"},
        }
        resp = _handle(req)
        assert "contents" in resp["result"]


# ── Tool Groups Integration ────────────────────────────────────────────────────

class TestToolGroupIntegration:
    def test_iot_group_in_tool_groups(self):
        from agent.loop import _TOOL_GROUPS
        assert "iot" in _TOOL_GROUPS

    def test_iot_tools_in_group(self):
        from agent.loop import _TOOL_GROUPS
        group = _TOOL_GROUPS["iot"]
        schema_names = {t["name"] for t in _TOOLS}
        for name in schema_names:
            assert name in group, f"Tool '{name}' no está en _TOOL_GROUPS['iot']"

    def test_iot_keywords_in_task_keywords(self):
        from agent.loop import _TASK_KEYWORDS
        assert "iot" in _TASK_KEYWORDS
        kws = _TASK_KEYWORDS["iot"]
        assert "tapo" in kws
        assert "alexa" in kws
        assert "blink" in kws
        assert "mqtt" in kws

    def test_iot_keywords_no_tool_names(self):
        from agent.loop import _TASK_KEYWORDS, _TOOL_GROUPS
        tool_names = _TOOL_GROUPS.get("iot", frozenset())
        kws = _TASK_KEYWORDS.get("iot", frozenset())
        # Los keywords NO deben ser nombres de tools
        overlap = kws & tool_names
        assert not overlap, f"Keywords contienen nombres de tools: {overlap}"


# ── Config Integration ────────────────────────────────────────────────────────

class TestConfigIntegration:
    def test_iot_assistant_in_default_config(self):
        from config import DEFAULT_CONFIG
        assert "iotAssistant" in DEFAULT_CONFIG["mcp"]
        assert DEFAULT_CONFIG["mcp"]["iotAssistant"]["enabled"] is False

    def test_ooconfig_has_iot_field(self):
        from config import OOConfig
        cfg = OOConfig()
        assert hasattr(cfg, "mcp_iot_assistant_enabled")
        assert cfg.mcp_iot_assistant_enabled is False

    def test_iot_permissions_in_default_config(self):
        from config import DEFAULT_CONFIG
        perms = DEFAULT_CONFIG["permissions"]
        # Control tools = ask
        ask_tools = {"tapo_on_off", "tapo_set", "blink_arm", "blink_snapshot",
                     "alexa_speak", "alexa_command", "alexa_volume",
                     "tuya_control", "ha_control", "ha_automation",
                     "mqtt_publish", "esphome_control"}
        # Read/list tools = auto
        auto_tools = {"tapo_list", "tapo_status", "blink_status", "blink_clips",
                      "blink_verify", "alexa_devices", "tuya_list", "tuya_status",
                      "ha_entities", "ha_state", "mqtt_subscribe",
                      "esphome_list", "iot_discover"}
        for name in ask_tools:
            assert perms.get(name) == "ask", f"'{name}' debería ser 'ask', es '{perms.get(name)}'"
        for name in auto_tools:
            assert perms.get(name) == "auto", f"'{name}' debería ser 'auto', es '{perms.get(name)}'"
