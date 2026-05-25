#!/usr/bin/env python3
"""
iot_assistant.py — MCP server para dispositivos IoT del hogar.
24 tools: TAPO (luces WiFi), Blink (cámaras/timbre), Alexa (Echo),
          Tuya/Smart Life, Home Assistant, MQTT, ESPHome, descubrimiento.

Protocolo: stdio JSON-RPC 2.0 newline-delimited.
Config:    ~/.oocode/iot_assistant.json
Activar:   ~/.oocode/oocode.json → mcp.iotAssistant.enabled = true

Dependencias opcionales:
  pip install python-kasa       # TAPO luces/enchufes TP-Link (Debian: python3-kasa)
  pip install blinkpy aiohttp   # Cámaras Blink/Amazon Ring  (Debian: python3-blinkpy)
  pip install tinytuya          # Dispositivos Tuya/Smart Life
  pip install paho-mqtt         # Broker MQTT               (Debian: python3-paho-mqtt)
  # Alexa y Home Assistant no necesitan librerías externas
  # ESPHome no necesita librerías externas
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


# ── Config ────────────────────────────────────────────────────────────────────

_CONFIG_PATH = Path("~/.oocode/iot_assistant.json").expanduser()

_DEFAULT_CONFIG: dict = {
    "tapo": {
        "email": "",
        "password": "",
        "devices": [
            # {"name": "salon", "ip": "192.168.1.100", "model": "L510"}
        ],
    },
    "blink": {
        "email":      "",
        "password":   "",
        "auth_token": "",
        "account_id": "",
        "client_id":  "",
        "region":     "prod",
    },
    "alexa": {
        # Implementado a través de Home Assistant Alexa Media Player
        # HACS: https://github.com/custom-components/alexa_media_player
        "ha_entity_prefix": "media_player.",
    },
    "tuya": {
        "access_id":  "",
        "access_key": "",
        "api_region": "eu",
        "devices": [
            # {"name": "luz_cocina", "device_id": "...", "ip": "192.168.1.x", "local_key": "..."}
        ],
    },
    "mqtt": {
        "host":      "localhost",
        "port":      1883,
        "username":  "",
        "password":  "",
        "client_id": "oocode-iot",
    },
    "home_assistant": {
        "url":   "http://homeassistant.local:8123",
        "token": "",
    },
    "esphome": {
        "devices": [
            # {"name": "lampara_escritorio", "host": "192.168.1.x", "password": ""}
        ],
    },
}


def _load_cfg() -> dict:
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH) as f:
                data = json.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    def _merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = _merge(result[k], v)
            else:
                result[k] = v
        return result

    cfg = _merge(_DEFAULT_CONFIG, data)
    if not _CONFIG_PATH.exists():
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_PATH, "w") as f:
            json.dump(_DEFAULT_CONFIG, f, indent=2)
    return cfg


def _save_cfg(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ── Helpers stdio ─────────────────────────────────────────────────────────────

def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _recv() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line.strip())


def _ok(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, msg: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _http(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    data: dict | bytes | None = None,
    timeout: int = 15,
) -> tuple[int, dict | str]:
    """Devuelve (status_code, parsed_json_or_text)."""
    body: bytes | None = None
    if isinstance(data, dict):
        body = json.dumps(data).encode()
        headers = {**(headers or {}), "Content-Type": "application/json"}
    elif isinstance(data, bytes):
        body = data

    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, raw.decode("utf-8", errors="replace")
    except Exception as exc:
        return -1, str(exc)


# ══════════════════════════════════════════════════════════════════════════════
# TAPO — Luces y enchufes WiFi TP-Link
# ══════════════════════════════════════════════════════════════════════════════

def _tapo_cfg() -> dict | None:
    cfg = _load_cfg()["tapo"]
    if not cfg.get("email") or not cfg.get("password"):
        return None
    return cfg


def _tool_tapo_list(args: dict) -> str:
    cfg = _tapo_cfg()
    if not cfg:
        return (
            "TAPO no configurado. Editar ~/.oocode/iot_assistant.json:\n"
            '  "tapo": {"email": "tu@email.com", "password": "contraseña",\n'
            '           "devices": [{"name": "salon", "ip": "192.168.1.x", "model": "L510"}]}'
        )
    devices = cfg.get("devices", [])
    if not devices:
        return "No hay dispositivos TAPO configurados en ~/.oocode/iot_assistant.json"
    lines = [f"Dispositivos TAPO configurados ({len(devices)}):"]
    for d in devices:
        lines.append(f"  {d.get('name', '?'):20s}  IP: {d.get('ip', '?'):16s}  Modelo: {d.get('model', '?')}")
    return "\n".join(lines)


def _tool_tapo_status(args: dict) -> str:
    name = args.get("name", "").strip()
    cfg  = _tapo_cfg()
    if not cfg:
        return _tool_tapo_list({})

    devices = cfg.get("devices", [])
    if name:
        devices = [d for d in devices if d.get("name") == name]
    if not devices:
        return f"Dispositivo '{name}' no encontrado en la configuración"

    try:
        import asyncio
        from kasa import Credentials, DeviceConfig
        from kasa.iot import IotBulb, IotPlug
    except ImportError:
        return "Instalar: pip install python-kasa  (Debian: sudo apt install python3-kasa)\nLuego reinicia OOCode."

    results = []
    for dev in devices:
        ip = dev.get("ip", "")
        async def _get(ip=ip):
            creds   = Credentials(cfg["email"], cfg["password"])
            dev_cfg = DeviceConfig(host=ip, credentials=creds)
            for DevCls in (IotBulb, IotPlug):
                try:
                    device = DevCls(host=ip, config=dev_cfg)
                    await device.update()
                    info: dict = {
                        "encendido": device.is_on,
                        "alias":     device.alias,
                        "modelo":    device.model,
                    }
                    if hasattr(device, "brightness"):
                        info["brillo"] = device.brightness
                    if hasattr(device, "color_temp"):
                        info["temp_color"] = device.color_temp
                    return info
                except Exception:
                    continue
            return None

        try:
            info = asyncio.run(_get())
            if info:
                estado = "🟢 encendido" if info.get("encendido") else "🔴 apagado"
                extra  = ""
                if "brillo" in info:
                    extra += f"  brillo:{info['brillo']}%"
                if "temp_color" in info:
                    extra += f"  color:{info['temp_color']}K"
                results.append(f"  {dev['name']}: {estado}  [{info.get('modelo','?')}]{extra}")
            else:
                results.append(f"  {dev['name']}: No se pudo conectar a {ip}")
        except Exception as exc:
            results.append(f"  {dev['name']}: Error — {exc}")

    return "\n".join(results) if results else "Sin resultados"


def _tool_tapo_on_off(args: dict) -> str:
    name   = args.get("name", "").strip()
    action = args.get("action", "").lower()
    if not name or action not in ("on", "off", "toggle"):
        return "Parámetros requeridos: name, action (on/off/toggle)"

    cfg = _tapo_cfg()
    if not cfg:
        return _tool_tapo_list({})

    device_cfg = next((d for d in cfg.get("devices", []) if d.get("name") == name), None)
    if not device_cfg:
        return f"Dispositivo '{name}' no encontrado. Usa tapo_list para ver los disponibles."

    try:
        import asyncio
        from kasa import Credentials, DeviceConfig
        from kasa.iot import IotBulb, IotPlug
    except ImportError:
        return "Instalar: pip install python-kasa  (Debian: sudo apt install python3-kasa)"

    ip = device_cfg.get("ip", "")

    async def _do():
        creds   = Credentials(cfg["email"], cfg["password"])
        dev_cfg = DeviceConfig(host=ip, credentials=creds)
        for DevCls in (IotBulb, IotPlug):
            try:
                device = DevCls(host=ip, config=dev_cfg)
                await device.update()
                if action == "on":
                    await device.turn_on()
                elif action == "off":
                    await device.turn_off()
                else:  # toggle
                    if device.is_on:
                        await device.turn_off()
                    else:
                        await device.turn_on()
                return "OK"
            except Exception:
                continue
        return "Error: no se pudo controlar el dispositivo"

    try:
        result = asyncio.run(_do())
        return f"{name} → {action.upper()}: {result}"
    except Exception as exc:
        return f"Error: {exc}"


def _tool_tapo_set(args: dict) -> str:
    name       = args.get("name", "").strip()
    brightness = args.get("brightness")
    color_temp = args.get("color_temp")
    hue        = args.get("hue")
    saturation = args.get("saturation")
    if not name:
        return "Parámetro requerido: name"

    cfg = _tapo_cfg()
    if not cfg:
        return _tool_tapo_list({})

    device_cfg = next((d for d in cfg.get("devices", []) if d.get("name") == name), None)
    if not device_cfg:
        return f"Dispositivo '{name}' no encontrado."

    try:
        import asyncio
        from kasa import Credentials, DeviceConfig
        from kasa.iot import IotBulb, IotPlug
    except ImportError:
        return "Instalar: pip install python-kasa  (Debian: sudo apt install python3-kasa)"

    ip = device_cfg.get("ip", "")

    async def _do():
        creds   = Credentials(cfg["email"], cfg["password"])
        dev_cfg = DeviceConfig(host=ip, credentials=creds)
        for DevCls in (IotBulb, IotPlug):
            try:
                device = DevCls(host=ip, config=dev_cfg)
                await device.update()
                changes = []
                if brightness is not None and hasattr(device, "set_brightness"):
                    await device.set_brightness(int(brightness))
                    changes.append(f"brillo={brightness}%")
                if color_temp is not None and hasattr(device, "set_color_temp"):
                    await device.set_color_temp(int(color_temp))
                    changes.append(f"temp_color={color_temp}K")
                if hue is not None and saturation is not None and hasattr(device, "set_hsv"):
                    await device.set_hsv(int(hue), int(saturation))
                    changes.append(f"color=({hue}°, {saturation}%)")
                return " → ".join(changes) if changes else "Sin cambios"
            except Exception:
                continue
        return "Error: dispositivo no compatible con ajustes de luz"

    try:
        result = asyncio.run(_do())
        return f"{name}: {result}"
    except Exception as exc:
        return f"Error: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# BLINK — Cámaras y timbre Amazon Blink
# ══════════════════════════════════════════════════════════════════════════════

_BLINK_BASE = "https://rest-{region}.immedia-semi.com"


def _blink_headers(token: str) -> dict:
    return {
        "TOKEN_AUTH":    token,
        "Content-Type":  "application/json",
        "User-Agent":    "Blink/3.5.4 (iPhone; iOS 14.0; Scale/3.00)",
        "APP-BUILD":     "IOS_3.5.4",
        "LOCALE":        "en_US",
    }


def _blink_login(cfg: dict) -> tuple[str | None, str | None]:
    """Devuelve (token, error). Guarda token en config si OK."""
    email    = cfg.get("email", "")
    password = cfg.get("password", "")
    region   = cfg.get("region", "prod")
    if not email or not password:
        return None, (
            "Blink no configurado. Editar ~/.oocode/iot_assistant.json:\n"
            '  "blink": {"email": "tu@email.com", "password": "contraseña"}'
        )

    url = f"{_BLINK_BASE.format(region=region)}/api/v5/account/login"
    status, data = _http(url, method="POST", data={
        "email":    email,
        "password": password,
        "unique_id": "oocode-blink-client",
        "client_name": "OOCode IoT Assistant",
        "client_type": "ios",
        "reauth": True,
    })

    if not isinstance(data, dict):
        return None, f"Error de login Blink (HTTP {status}): {data}"

    if "client" in data and data["client"].get("verification_required"):
        # 2FA requerido — guardar account_id y client_id para blink_verify
        cfg_full = _load_cfg()
        cfg_full["blink"]["account_id"] = str(data.get("account", {}).get("account_id", ""))
        cfg_full["blink"]["client_id"]  = str(data.get("client", {}).get("id", ""))
        _save_cfg(cfg_full)
        return None, (
            f"Blink requiere verificación 2FA. Se ha enviado un PIN a {email}.\n"
            "Llama blink_verify con el PIN recibido: blink_verify(pin='123456')"
        )

    token = data.get("auth", {}).get("token", "")
    if not token:
        return None, f"Login Blink fallido: {data}"

    # Guardar token y IDs
    cfg_full = _load_cfg()
    cfg_full["blink"]["auth_token"] = token
    cfg_full["blink"]["account_id"] = str(data.get("account", {}).get("account_id", ""))
    cfg_full["blink"]["client_id"]  = str(data.get("client", {}).get("id", ""))
    _save_cfg(cfg_full)
    return token, None


def _blink_get_token() -> tuple[str | None, str | None]:
    cfg = _load_cfg()["blink"]
    token = cfg.get("auth_token", "")
    if token:
        return token, None
    return _blink_login(cfg)


def _tool_blink_status(args: dict) -> str:
    token, err = _blink_get_token()
    if not token:
        return err or "Error de autenticación Blink"

    cfg    = _load_cfg()["blink"]
    region = cfg.get("region", "prod")
    acct   = cfg.get("account_id", "")
    base   = _BLINK_BASE.format(region=region)
    hdrs   = _blink_headers(token)

    # Obtener networks
    status, data = _http(f"{base}/api/v3/accounts/{acct}/networks", headers=hdrs)
    if status == 401:
        # Token expirado — relanzar login
        cfg_full = _load_cfg()
        cfg_full["blink"]["auth_token"] = ""
        _save_cfg(cfg_full)
        return "Sesión Blink expirada. Vuelve a llamar blink_status para re-autenticarte."

    if not isinstance(data, dict):
        return f"Error al obtener redes Blink (HTTP {status})"

    lines = ["Estado Blink:"]
    networks = data.get("networks", [])
    for net in networks:
        armed = "🔴 ARMADO" if net.get("armed") else "🟢 desarmado"
        lines.append(f"\nRed: {net.get('name', '?')} ({armed})")
        lines.append(f"  ID:    {net.get('id', '?')}")
        lines.append(f"  Tipo:  {net.get('network_origin', '?')}")

    # Obtener cámaras de cada red
    for net in networks:
        net_id = net.get("id")
        s2, cams = _http(f"{base}/network/{net_id}/cameras", headers=hdrs)
        if isinstance(cams, dict):
            for cam in cams.get("cameras", []):
                batt   = cam.get("battery", "?")
                signal = cam.get("wifi_strength", "?")
                lines.append(
                    f"  📷 {cam.get('name', '?'):20s}  "
                    f"batería:{batt}  señal:{signal}  "
                    f"activa:{'sí' if cam.get('enabled') else 'no'}"
                )

    return "\n".join(lines)


def _tool_blink_arm(args: dict) -> str:
    action     = args.get("action", "").lower()
    network_id = args.get("network_id", "")
    if action not in ("arm", "disarm"):
        return "Parámetro requerido: action (arm/disarm)"

    token, err = _blink_get_token()
    if not token:
        return err or "Error de autenticación"

    cfg    = _load_cfg()["blink"]
    region = cfg.get("region", "prod")
    base   = _BLINK_BASE.format(region=region)
    hdrs   = _blink_headers(token)

    if not network_id:
        # Obtener primera red
        acct = cfg.get("account_id", "")
        s, data = _http(f"{base}/api/v3/accounts/{acct}/networks", headers=hdrs)
        if isinstance(data, dict) and data.get("networks"):
            network_id = str(data["networks"][0]["id"])
        else:
            return "No se encontró ninguna red Blink. Especifica network_id."

    url = f"{base}/api/v1/network/{network_id}/{action}"
    status, resp = _http(url, method="POST", headers=hdrs, data={})
    if status in (200, 201):
        return f"Sistema Blink → {action.upper()} ✔ (red {network_id})"
    return f"Error al {action} Blink (HTTP {status}): {resp}"


def _tool_blink_snapshot(args: dict) -> str:
    camera_id  = args.get("camera_id", "")
    network_id = args.get("network_id", "")
    save_path  = args.get("save_path", "").strip()

    token, err = _blink_get_token()
    if not token:
        return err or "Error de autenticación"

    cfg    = _load_cfg()["blink"]
    region = cfg.get("region", "prod")
    base   = _BLINK_BASE.format(region=region)
    hdrs   = _blink_headers(token)

    # Si no hay camera_id, obtener primera cámara
    if not camera_id or not network_id:
        acct = cfg.get("account_id", "")
        s, nets = _http(f"{base}/api/v3/accounts/{acct}/networks", headers=hdrs)
        if isinstance(nets, dict) and nets.get("networks"):
            network_id = str(nets["networks"][0]["id"])
            s2, cams = _http(f"{base}/network/{network_id}/cameras", headers=hdrs)
            if isinstance(cams, dict) and cams.get("cameras"):
                camera_id = str(cams["cameras"][0]["id"])

    if not camera_id:
        return "No se encontró ninguna cámara. Especifica camera_id."

    # Disparar snapshot
    url    = f"{base}/network/{network_id}/camera/{camera_id}/thumbnail"
    status, resp = _http(url, method="POST", headers=hdrs, data={})
    if status not in (200, 201, 202):
        return f"Error al tomar snapshot (HTTP {status}): {resp}"

    # Obtener URL de la miniatura
    thumb_url = resp.get("media", "") if isinstance(resp, dict) else ""
    if thumb_url and save_path:
        try:
            req = urllib.request.Request(
                f"https://rest-{region}.immedia-semi.com{thumb_url}",
                headers={"TOKEN_AUTH": token},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                Path(save_path).write_bytes(r.read())
            return f"Snapshot guardado en: {save_path}"
        except Exception as exc:
            return f"Snapshot tomado pero error al guardar: {exc}"

    return f"Snapshot disparado. URL: {thumb_url or '(pendiente — espera unos segundos)'}"


def _tool_blink_clips(args: dict) -> str:
    limit = int(args.get("limit", 10))

    token, err = _blink_get_token()
    if not token:
        return err or "Error de autenticación"

    cfg    = _load_cfg()["blink"]
    region = cfg.get("region", "prod")
    acct   = cfg.get("account_id", "")
    base   = _BLINK_BASE.format(region=region)
    hdrs   = _blink_headers(token)

    status, data = _http(
        f"{base}/api/v1/accounts/{acct}/media/changed?page=1&per_page={limit}",
        headers=hdrs,
    )
    if not isinstance(data, dict):
        return f"Error obteniendo clips (HTTP {status})"

    clips = data.get("media", [])
    if not clips:
        return "Sin clips de movimiento recientes"

    lines = [f"Clips Blink recientes ({len(clips)}):"]
    for clip in clips:
        ts     = clip.get("created_at", "?")
        camera = clip.get("device_name", "?")
        thumb  = clip.get("thumbnail", "?")
        url    = clip.get("media", "?")
        lines.append(f"  {ts}  📷 {camera}")
        lines.append(f"    Clip:  https://rest-{region}.immedia-semi.com{url}")
        lines.append(f"    Thumb: https://rest-{region}.immedia-semi.com{thumb}")
    return "\n".join(lines)


def _tool_blink_verify(args: dict) -> str:
    """Verificación 2FA de Blink — llama después de recibir el PIN por email/SMS."""
    pin = str(args.get("pin", "")).strip()
    if not pin:
        return "Parámetro requerido: pin (el código recibido por email/SMS)"

    cfg    = _load_cfg()["blink"]
    region = cfg.get("region", "prod")
    acct   = cfg.get("account_id", "")
    client = cfg.get("client_id", "")
    base   = _BLINK_BASE.format(region=region)

    if not acct or not client:
        return "Primero llama blink_status para iniciar el proceso de login"

    status, data = _http(
        f"{base}/api/v4/account/{acct}/client/{client}/pin/verify",
        method="POST",
        data={"pin": pin},
    )
    if status in (200, 201) and isinstance(data, dict):
        token = data.get("auth", {}).get("token", "")
        if token:
            cfg_full = _load_cfg()
            cfg_full["blink"]["auth_token"] = token
            _save_cfg(cfg_full)
            return "✔ Verificación 2FA completada. Token guardado en ~/.oocode/iot_assistant.json"
    return f"Error en verificación (HTTP {status}): {data}"


# ══════════════════════════════════════════════════════════════════════════════
# ALEXA — Vía Home Assistant Alexa Media Player
# ══════════════════════════════════════════════════════════════════════════════

def _ha_headers() -> dict | None:
    cfg   = _load_cfg()["home_assistant"]
    token = cfg.get("token", "")
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _ha_url(path: str) -> str:
    base = _load_cfg()["home_assistant"].get("url", "http://homeassistant.local:8123").rstrip("/")
    return f"{base}/api/{path}"


def _no_ha_config() -> str:
    return (
        "Home Assistant no configurado. Editar ~/.oocode/iot_assistant.json:\n"
        '  "home_assistant": {\n'
        '    "url": "http://192.168.1.x:8123",\n'
        '    "token": "<Long-Lived Access Token desde HA → Perfil → Seguridad>"\n'
        "  }\n\n"
        "Para Alexa: instala la integración 'Alexa Media Player' desde HACS en HA.\n"
        "https://github.com/custom-components/alexa_media_player"
    )


def _tool_alexa_devices(args: dict) -> str:
    hdrs = _ha_headers()
    if not hdrs:
        return _no_ha_config()

    status, data = _http(_ha_url("states"), headers=hdrs)
    if status != 200:
        return f"Error HA (HTTP {status}): {data}"
    if not isinstance(data, list):
        return "Respuesta inesperada de HA"

    # Buscar entidades Alexa (media_player con "alexa" o "echo" en el nombre/atributos)
    prefix    = _load_cfg()["alexa"].get("ha_entity_prefix", "media_player.")
    devices   = [
        e for e in data
        if e.get("entity_id", "").startswith(prefix) and
        ("alexa" in e.get("entity_id", "").lower() or
         "echo"  in e.get("entity_id", "").lower() or
         "alexa" in str(e.get("attributes", {}).get("friendly_name", "")).lower() or
         "amazon" in str(e.get("attributes", {}).get("source_list", [])).lower() or
         "alexa" in str(e.get("attributes", {})).lower())
    ]

    if not devices:
        return (
            "No se encontraron dispositivos Alexa en HA.\n"
            "Asegúrate de tener instalada la integración 'Alexa Media Player' (HACS).\n"
            f"Entidades media_player disponibles: {[e['entity_id'] for e in data if e['entity_id'].startswith('media_player.')][:10]}"
        )

    lines = [f"Dispositivos Alexa en HA ({len(devices)}):"]
    for dev in devices:
        attrs = dev.get("attributes", {})
        lines.append(
            f"  {dev['entity_id']:40s}  "
            f"estado:{dev.get('state','?'):10s}  "
            f"nombre:{attrs.get('friendly_name','?')}"
        )
    return "\n".join(lines)


def _tool_alexa_speak(args: dict) -> str:
    message   = args.get("message", "").strip()
    entity_id = args.get("entity_id", "").strip()
    if not message:
        return "Parámetro requerido: message"
    if not entity_id:
        return "Parámetro requerido: entity_id (usa alexa_devices para ver el ID)"

    hdrs = _ha_headers()
    if not hdrs:
        return _no_ha_config()

    # Intentar con notify.alexa_media primero
    notify_service = "notify.alexa_media_" + entity_id.replace("media_player.", "").replace(".", "_")
    status, resp = _http(
        _ha_url("services/notify/" + notify_service.replace("notify.", "")),
        method="POST",
        headers=hdrs,
        data={"message": message, "data": {"type": "announce"}},
    )
    if status in (200, 201):
        return f"✔ Alexa dice: '{message}' → {entity_id}"

    # Fallback: TTS con media_player.play_media
    status2, resp2 = _http(
        _ha_url("services/tts/cloud_say"),
        method="POST",
        headers=hdrs,
        data={"entity_id": entity_id, "message": message},
    )
    if status2 in (200, 201):
        return f"✔ TTS enviado: '{message}' → {entity_id}"

    return f"Error al enviar TTS (HTTP {status}/{status2}). Respuesta: {resp}"


def _tool_alexa_command(args: dict) -> str:
    command   = args.get("command", "").strip()
    entity_id = args.get("entity_id", "").strip()
    if not command or not entity_id:
        return "Parámetros requeridos: command, entity_id"

    hdrs = _ha_headers()
    if not hdrs:
        return _no_ha_config()

    # Comandos de reproductor multimedia
    cmd_map = {
        "play":   ("media_player", "media_play"),
        "pause":  ("media_player", "media_pause"),
        "stop":   ("media_player", "media_stop"),
        "next":   ("media_player", "media_next_track"),
        "prev":   ("media_player", "media_previous_track"),
        "mute":   ("media_player", "volume_mute"),
    }

    if command.lower() in cmd_map:
        domain, service = cmd_map[command.lower()]
        data = {"entity_id": entity_id}
        if command.lower() == "mute":
            data["is_volume_muted"] = True
    else:
        # Enviar como command a Alexa Media Player
        domain, service = "media_player", "play_media"
        data = {
            "entity_id": entity_id,
            "media_content_id": command,
            "media_content_type": "custom",
        }

    status, resp = _http(
        _ha_url(f"services/{domain}/{service}"),
        method="POST",
        headers=hdrs,
        data=data,
    )
    if status in (200, 201):
        return f"✔ Comando '{command}' enviado → {entity_id}"
    return f"Error (HTTP {status}): {resp}"


def _tool_alexa_volume(args: dict) -> str:
    entity_id = args.get("entity_id", "").strip()
    volume    = args.get("volume")
    if not entity_id or volume is None:
        return "Parámetros requeridos: entity_id, volume (0-100)"

    hdrs = _ha_headers()
    if not hdrs:
        return _no_ha_config()

    vol_float = float(volume) / 100.0
    status, resp = _http(
        _ha_url("services/media_player/volume_set"),
        method="POST",
        headers=hdrs,
        data={"entity_id": entity_id, "volume_level": vol_float},
    )
    if status in (200, 201):
        return f"✔ Volumen → {volume}% en {entity_id}"
    return f"Error (HTTP {status}): {resp}"


# ══════════════════════════════════════════════════════════════════════════════
# TUYA / SMART LIFE
# ══════════════════════════════════════════════════════════════════════════════

def _tool_tuya_list(args: dict) -> str:
    cfg = _load_cfg()["tuya"]
    devices = cfg.get("devices", [])
    if not devices:
        return (
            "No hay dispositivos Tuya configurados. Editar ~/.oocode/iot_assistant.json:\n"
            '  "tuya": {\n'
            '    "access_id": "...",\n'
            '    "access_key": "...",\n'
            '    "api_region": "eu",\n'
            '    "devices": [{"name": "luz_salon", "device_id": "...", "ip": "192.168.1.x", "local_key": "..."}]\n'
            "  }\n\n"
            "Para obtener device_id y local_key: https://iot.tuya.com → Cloud → Devices\n"
            "Instalar: pip install tinytuya"
        )
    lines = [f"Dispositivos Tuya configurados ({len(devices)}):"]
    for d in devices:
        lines.append(f"  {d.get('name', '?'):25s}  ID: {d.get('device_id', '?')[:20]}  IP: {d.get('ip', '?')}")
    return "\n".join(lines)


def _tool_tuya_status(args: dict) -> str:
    name = args.get("name", "").strip()
    cfg  = _load_cfg()["tuya"]

    devices = cfg.get("devices", [])
    if name:
        devices = [d for d in devices if d.get("name") == name]
    if not devices:
        return _tool_tuya_list({})

    try:
        import tinytuya
    except ImportError:
        return "Instalar: pip install tinytuya\nLuego reinicia OOCode."

    results = []
    for dev in devices:
        try:
            d = tinytuya.Device(
                dev_id   = dev.get("device_id", ""),
                address  = dev.get("ip", ""),
                local_key = dev.get("local_key", ""),
                version  = dev.get("protocol_version", "3.3"),
            )
            d.set_socketRetryLimit(2)
            data = d.status()
            results.append(f"{dev['name']}: {json.dumps(data, ensure_ascii=False)}")
        except Exception as exc:
            results.append(f"{dev['name']}: Error — {exc}")

    return "\n".join(results)


def _tool_tuya_control(args: dict) -> str:
    name   = args.get("name", "").strip()
    action = args.get("action", "").lower()
    dp     = int(args.get("dp", 1))   # Data Point (1=on/off, 2=modo, 3=brillo...)
    value  = args.get("value")

    if not name:
        return "Parámetro requerido: name"

    cfg = _load_cfg()["tuya"]
    dev_cfg = next((d for d in cfg.get("devices", []) if d.get("name") == name), None)
    if not dev_cfg:
        return f"Dispositivo '{name}' no encontrado. Usa tuya_list."

    try:
        import tinytuya
    except ImportError:
        return "Instalar: pip install tinytuya"

    try:
        d = tinytuya.Device(
            dev_id    = dev_cfg.get("device_id", ""),
            address   = dev_cfg.get("ip", ""),
            local_key = dev_cfg.get("local_key", ""),
            version   = dev_cfg.get("protocol_version", "3.3"),
        )
        d.set_socketRetryLimit(2)

        if action in ("on", "off"):
            d.set_status(action == "on", switch=dp)
            return f"{name} → {action.upper()} ✔"
        elif action == "set" and value is not None:
            d.set_value(dp, value)
            return f"{name} → DP{dp}={value} ✔"
        elif action == "toggle":
            status = d.status()
            current = status.get("dps", {}).get(str(dp), False)
            d.set_status(not current, switch=dp)
            return f"{name} → {'OFF' if current else 'ON'} (toggle) ✔"
        else:
            return "action debe ser: on, off, toggle, set (con value)"
    except Exception as exc:
        return f"Error controlando {name}: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# HOME ASSISTANT — REST API
# ══════════════════════════════════════════════════════════════════════════════

def _tool_ha_entities(args: dict) -> str:
    domain  = args.get("domain", "").strip()
    search  = args.get("search", "").strip().lower()
    limit   = int(args.get("limit", 30))

    hdrs = _ha_headers()
    if not hdrs:
        return _no_ha_config()

    status, data = _http(_ha_url("states"), headers=hdrs)
    if status != 200:
        return f"Error HA (HTTP {status}): {data}"
    if not isinstance(data, list):
        return "Respuesta inesperada de HA"

    entities = data
    if domain:
        entities = [e for e in entities if e.get("entity_id", "").startswith(domain + ".")]
    if search:
        entities = [e for e in entities if search in e.get("entity_id", "").lower() or
                    search in str(e.get("attributes", {}).get("friendly_name", "")).lower()]

    entities = entities[:limit]
    if not entities:
        return f"Sin entidades{'para dominio ' + domain if domain else ''}"

    lines = [f"Entidades HA ({len(entities)}{'/' + str(len(data)) if not domain and not search else ''}):"]
    for e in entities:
        attrs = e.get("attributes", {})
        name  = attrs.get("friendly_name", "")
        lines.append(f"  {e['entity_id']:45s}  {e.get('state','?'):12s}  {name}")
    return "\n".join(lines)


def _tool_ha_state(args: dict) -> str:
    entity_id = args.get("entity_id", "").strip()
    if not entity_id:
        return "Parámetro requerido: entity_id"

    hdrs = _ha_headers()
    if not hdrs:
        return _no_ha_config()

    status, data = _http(_ha_url(f"states/{entity_id}"), headers=hdrs)
    if status == 404:
        return f"Entidad no encontrada: {entity_id}"
    if status != 200:
        return f"Error HA (HTTP {status})"
    if not isinstance(data, dict):
        return str(data)

    attrs = data.get("attributes", {})
    lines = [
        f"Estado: {entity_id}",
        f"  Valor:      {data.get('state', '?')}",
        f"  Actualizado:{data.get('last_updated', '?')}",
        f"  Cambiado:   {data.get('last_changed', '?')}",
        f"\nAtributos:",
    ]
    for k, v in sorted(attrs.items()):
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _tool_ha_control(args: dict) -> str:
    entity_id  = args.get("entity_id", "").strip()
    service    = args.get("service", "").strip()
    extra_data = args.get("data", {})
    if not entity_id or not service:
        return "Parámetros requeridos: entity_id, service (ej. light.turn_on, switch.toggle)"

    hdrs = _ha_headers()
    if not hdrs:
        return _no_ha_config()

    # service puede ser "turn_on", "light.turn_on", "media_player.volume_set"...
    if "." in service:
        domain, svc = service.split(".", 1)
    else:
        domain = entity_id.split(".")[0]
        svc    = service

    body = {"entity_id": entity_id}
    if isinstance(extra_data, dict):
        body.update(extra_data)

    status, resp = _http(
        _ha_url(f"services/{domain}/{svc}"),
        method="POST",
        headers=hdrs,
        data=body,
    )
    if status in (200, 201):
        changed = resp if isinstance(resp, list) else []
        return (
            f"✔ Servicio {domain}.{svc} → {entity_id}\n"
            + (f"  Entidades afectadas: {[e.get('entity_id') for e in changed]}" if changed else "")
        )
    return f"Error HA (HTTP {status}): {resp}"


def _tool_ha_automation(args: dict) -> str:
    action    = args.get("action", "list").lower()
    entity_id = args.get("entity_id", "").strip()

    hdrs = _ha_headers()
    if not hdrs:
        return _no_ha_config()

    if action == "list":
        status, data = _http(_ha_url("states"), headers=hdrs)
        if not isinstance(data, list):
            return f"Error HA (HTTP {status})"
        autos = [e for e in data if e.get("entity_id", "").startswith("automation.")]
        search = args.get("search", "").lower()
        if search:
            autos = [a for a in autos if search in a["entity_id"].lower() or
                     search in str(a.get("attributes", {}).get("friendly_name", "")).lower()]
        lines = [f"Automatizaciones HA ({len(autos)}):"]
        for a in autos:
            state = a.get("state", "?")
            name  = a.get("attributes", {}).get("friendly_name", "")
            icon  = "✔" if state == "on" else "✘"
            lines.append(f"  {icon} {a['entity_id']:45s}  {name}")
        return "\n".join(lines)

    elif action == "trigger":
        if not entity_id:
            return "Parámetro requerido: entity_id para trigger"
        status, resp = _http(
            _ha_url("services/automation/trigger"),
            method="POST",
            headers=hdrs,
            data={"entity_id": entity_id},
        )
        if status in (200, 201):
            return f"✔ Automatización disparada: {entity_id}"
        return f"Error (HTTP {status}): {resp}"

    elif action in ("on", "off"):
        if not entity_id:
            return f"Parámetro requerido: entity_id para {action}"
        svc = "turn_on" if action == "on" else "turn_off"
        status, resp = _http(
            _ha_url(f"services/automation/{svc}"),
            method="POST",
            headers=hdrs,
            data={"entity_id": entity_id},
        )
        if status in (200, 201):
            return f"✔ Automatización {entity_id} → {action.upper()}"
        return f"Error (HTTP {status}): {resp}"

    return f"action debe ser: list, trigger, on, off"


# ══════════════════════════════════════════════════════════════════════════════
# MQTT
# ══════════════════════════════════════════════════════════════════════════════

def _tool_mqtt_publish(args: dict) -> str:
    topic   = args.get("topic", "").strip()
    payload = args.get("payload", "")
    if not topic:
        return "Parámetro requerido: topic"

    cfg = _load_cfg()["mqtt"]
    try:
        import paho.mqtt.client as mqtt
        import paho.mqtt.publish as publish
    except ImportError:
        return "Instalar: pip install paho-mqtt\nLuego reinicia OOCode."

    qos      = int(args.get("qos", 0))
    retain   = bool(args.get("retain", False))
    host     = cfg.get("host", "localhost")
    port     = int(cfg.get("port", 1883))
    username = cfg.get("username", "")
    password = cfg.get("password", "")

    auth = {"username": username, "password": password} if username else None

    payload_str = payload if isinstance(payload, str) else json.dumps(payload)

    try:
        publish.single(
            topic,
            payload  = payload_str,
            qos      = qos,
            retain   = retain,
            hostname = host,
            port     = port,
            auth     = auth,
        )
        return f"✔ MQTT publicado → {topic}\n  Payload: {payload_str[:200]}"
    except Exception as exc:
        return f"Error MQTT: {exc}\n\nConfig actual: {host}:{port}\nVerifica que el broker esté activo."


def _tool_mqtt_subscribe(args: dict) -> str:
    topic   = args.get("topic", "#").strip()
    timeout = float(args.get("timeout", 5))
    limit   = int(args.get("limit", 20))

    cfg = _load_cfg()["mqtt"]
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return "Instalar: pip install paho-mqtt"

    host     = cfg.get("host", "localhost")
    port     = int(cfg.get("port", 1883))
    username = cfg.get("username", "")
    password = cfg.get("password", "")

    messages: list[dict] = []

    def on_message(client, userdata, msg):
        if len(messages) < limit:
            try:
                payload = msg.payload.decode("utf-8", errors="replace")
            except Exception:
                payload = repr(msg.payload)
            messages.append({
                "topic":   msg.topic,
                "payload": payload,
                "qos":     msg.qos,
            })

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(topic)

    client = mqtt.Client(client_id=cfg.get("client_id", "oocode-sub"))
    if username:
        client.username_pw_set(username, password)
    client.on_message = on_message
    client.on_connect = on_connect

    try:
        client.connect(host, port, keepalive=5)
        client.loop_start()
        time.sleep(timeout)
        client.loop_stop()
        client.disconnect()
    except Exception as exc:
        return f"Error MQTT: {exc}\n\nVerifica broker en {host}:{port}"

    if not messages:
        return f"Sin mensajes en '{topic}' durante {timeout}s (broker: {host}:{port})"

    lines = [f"Mensajes MQTT '{topic}' ({len(messages)}):"]
    for m in messages:
        lines.append(f"  [{m['qos']}] {m['topic']}: {m['payload'][:200]}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# ESPHOME — Dispositivos ESP8266/ESP32 con web_server
# ══════════════════════════════════════════════════════════════════════════════

def _esphome_devices() -> list[dict]:
    return _load_cfg().get("esphome", {}).get("devices", [])


def _tool_esphome_list(args: dict) -> str:
    devices = _esphome_devices()
    if not devices:
        return (
            "No hay dispositivos ESPHome configurados. Editar ~/.oocode/iot_assistant.json:\n"
            '  "esphome": {\n'
            '    "devices": [{"name": "lampara_escritorio", "host": "192.168.1.x", "password": ""}]\n'
            "  }\n\n"
            "Requiere el componente 'web_server' en la config de ESPHome:\n"
            "  web_server:\n"
            "    port: 80"
        )

    lines = [f"Dispositivos ESPHome ({len(devices)}):"]
    for dev in devices:
        host = dev.get("host", "")
        name = dev.get("name", host)
        # Intentar ping básico
        try:
            sock = socket.create_connection((host, 80), timeout=2)
            sock.close()
            status = "✔ online"
        except (socket.timeout, OSError):
            status = "✘ offline"
        lines.append(f"  {name:25s}  {host:20s}  {status}")
    return "\n".join(lines)


def _tool_esphome_control(args: dict) -> str:
    name      = args.get("name", "").strip()
    entity    = args.get("entity", "").strip()
    action    = args.get("action", "toggle").lower()
    extra     = args.get("params", {})
    if not name or not entity:
        return "Parámetros requeridos: name, entity (ej. light/luz_salon)"

    devices = _esphome_devices()
    dev_cfg = next((d for d in devices if d.get("name") == name), None)
    if not dev_cfg:
        return f"Dispositivo '{name}' no encontrado. Usa esphome_list."

    host     = dev_cfg.get("host", "")
    password = dev_cfg.get("password", "")

    # entity puede ser "light/led" o "switch/relay" o "fan/ventilador"
    url = f"http://{host}/{entity}/{action}"

    params = {}
    if isinstance(extra, dict):
        params.update(extra)

    if password:
        params["api_key"] = password

    if params:
        url += "?" + urllib.parse.urlencode(params)

    status, resp = _http(url, method="POST", timeout=10)
    if status in (200, 204):
        return f"✔ ESPHome {name} → {entity}/{action}"
    return f"Error ESPHome (HTTP {status}): {resp}\n\nURL: {url}"


# ══════════════════════════════════════════════════════════════════════════════
# IoT DISCOVER — Descubrimiento de dispositivos en la red
# ══════════════════════════════════════════════════════════════════════════════

def _tool_iot_discover(args: dict) -> str:
    subnet  = args.get("subnet", "").strip()
    timeout = float(args.get("timeout", 1))

    lines = ["Descubrimiento de dispositivos IoT:"]

    # 1. mDNS / Avahi (descubrimiento de servicio)
    mdns_services = [
        "_http._tcp",
        "_hap._tcp",     # HomeKit
        "_esphomelib._tcp",
        "_home-assistant._tcp",
        "_mqtt._tcp",
        "_googlecast._tcp",  # Chromecast/Google Home
        "_alexa._tcp",
        "_tapo._tcp",
    ]

    if subprocess.run(["which", "avahi-browse"], capture_output=True).returncode == 0:
        lines.append("\n--- mDNS (avahi-browse) ---")
        for svc in mdns_services:
            rc = subprocess.run(
                ["avahi-browse", "-t", "-r", "-p", svc],
                capture_output=True, text=True, timeout=5
            )
            if rc.stdout.strip():
                for l in rc.stdout.splitlines():
                    if l.startswith("="):
                        lines.append(f"  {l}")
    elif subprocess.run(["which", "dns-sd"], capture_output=True).returncode == 0:
        lines.append("\n--- mDNS (dns-sd) ---")
        lines.append("  Ejecuta manualmente: dns-sd -B _http._tcp .")
    else:
        lines.append("\n(mDNS no disponible — instala avahi-daemon: sudo apt install avahi-daemon)")

    # 2. Escaneo de puertos comunes en subnet local
    if subnet:
        lines.append(f"\n--- Scan de subnet {subnet} (puertos IoT) ---")
        iot_ports = {
            80:    "HTTP/ESPHome/HA",
            443:   "HTTPS",
            1883:  "MQTT",
            8123:  "Home Assistant",
            8554:  "RTSP (cámara)",
            9123:  "Blink",
            9443:  "Tuya local",
        }
        # Determinar rango de IPs
        try:
            import ipaddress
            network = ipaddress.ip_network(subnet, strict=False)
            hosts   = list(network.hosts())[:254]
        except ValueError:
            return f"Subnet inválida: {subnet}. Formato: 192.168.1.0/24"

        found: list[str] = []
        for ip in hosts:
            ip_str = str(ip)
            for port, label in iot_ports.items():
                try:
                    sock = socket.create_connection((ip_str, port), timeout=timeout)
                    sock.close()
                    found.append(f"  {ip_str:16s}:{port:5d}  {label}")
                    break
                except (socket.timeout, ConnectionRefusedError, OSError):
                    pass

        if found:
            lines.extend(found)
        else:
            lines.append(f"  Sin dispositivos IoT encontrados en {subnet}")
    else:
        lines.append("\nPara escanear la red local: iot_discover(subnet='192.168.1.0/24')")

    # 3. Verificar dispositivos configurados
    cfg = _load_cfg()
    configured = []
    for section, key in [
        ("tapo", "devices"), ("esphome", "devices"), ("tuya", "devices")
    ]:
        for d in cfg.get(section, {}).get(key, []):
            configured.append(f"  [{section:8s}] {d.get('name', '?'):25s}  {d.get('ip') or d.get('host', '?')}")
    if configured:
        lines.append(f"\n--- Dispositivos configurados ({len(configured)}) ---")
        lines.extend(configured)

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMAS — 25 tools (incluyendo blink_verify)
# ══════════════════════════════════════════════════════════════════════════════

_TOOLS = [
    # ── TAPO ──────────────────────────────────────────────────────────────
    {
        "name":        "tapo_list",
        "description": "Lista los dispositivos TAPO (luces, enchufes TP-Link) configurados.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name":        "tapo_status",
        "description": "Obtiene el estado actual de uno o todos los dispositivos TAPO.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre del dispositivo (omitir = todos)"},
            },
        },
    },
    {
        "name":        "tapo_on_off",
        "description": "Enciende, apaga o alterna el estado de un dispositivo TAPO.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name":   {"type": "string", "description": "Nombre del dispositivo"},
                "action": {"type": "string", "description": "on / off / toggle"},
            },
            "required": ["name", "action"],
        },
    },
    {
        "name":        "tapo_set",
        "description": "Configura brillo, temperatura de color o tono/saturación de una bombilla TAPO.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name":        {"type": "string",  "description": "Nombre del dispositivo"},
                "brightness":  {"type": "integer", "description": "Brillo 1-100"},
                "color_temp":  {"type": "integer", "description": "Temperatura Kelvin (2500-6500)"},
                "hue":         {"type": "integer", "description": "Tono 0-360"},
                "saturation":  {"type": "integer", "description": "Saturación 0-100"},
            },
            "required": ["name"],
        },
    },
    # ── BLINK ─────────────────────────────────────────────────────────────
    {
        "name":        "blink_status",
        "description": "Estado del sistema Blink: cámaras, batería, armado/desarmado. Inicia sesión si es necesario.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name":        "blink_arm",
        "description": "Activa o desactiva la monitorización del sistema Blink.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action":     {"type": "string",  "description": "arm o disarm"},
                "network_id": {"type": "string",  "description": "ID de red Blink (opcional, usa la primera por defecto)"},
            },
            "required": ["action"],
        },
    },
    {
        "name":        "blink_snapshot",
        "description": "Toma una foto con la cámara Blink especificada (o la primera disponible).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "camera_id":  {"type": "string", "description": "ID de cámara (opcional)"},
                "network_id": {"type": "string", "description": "ID de red (opcional)"},
                "save_path":  {"type": "string", "description": "Ruta local donde guardar la imagen (opcional)"},
            },
        },
    },
    {
        "name":        "blink_clips",
        "description": "Lista los clips de movimiento recientes de las cámaras Blink.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Máximo de clips a mostrar (default 10)"},
            },
        },
    },
    {
        "name":        "blink_verify",
        "description": "Completa la verificación 2FA de Blink con el PIN recibido por email/SMS.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pin": {"type": "string", "description": "PIN de verificación recibido"},
            },
            "required": ["pin"],
        },
    },
    # ── ALEXA ─────────────────────────────────────────────────────────────
    {
        "name":        "alexa_devices",
        "description": "Lista los dispositivos Amazon Echo registrados en Home Assistant (Alexa Media Player).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name":        "alexa_speak",
        "description": "Envía un mensaje de texto a un Echo para que lo anuncie por voz (TTS).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "ID de entidad HA (ej. media_player.echo_salon)"},
                "message":   {"type": "string", "description": "Texto a reproducir"},
            },
            "required": ["entity_id", "message"],
        },
    },
    {
        "name":        "alexa_command",
        "description": "Envía un comando multimedia a un Echo (play, pause, stop, next, prev, mute).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "ID de entidad HA"},
                "command":   {"type": "string", "description": "play / pause / stop / next / prev / mute"},
            },
            "required": ["entity_id", "command"],
        },
    },
    {
        "name":        "alexa_volume",
        "description": "Ajusta el volumen de un Amazon Echo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "ID de entidad HA"},
                "volume":    {"type": "integer", "description": "Volumen 0-100"},
            },
            "required": ["entity_id", "volume"],
        },
    },
    # ── TUYA ──────────────────────────────────────────────────────────────
    {
        "name":        "tuya_list",
        "description": "Lista los dispositivos Tuya/Smart Life configurados.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name":        "tuya_status",
        "description": "Obtiene el estado actual de un dispositivo Tuya (por protocolo local).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre del dispositivo (omitir = todos)"},
            },
        },
    },
    {
        "name":        "tuya_control",
        "description": "Controla un dispositivo Tuya: encender, apagar, alternar o configurar un Data Point.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name":   {"type": "string",  "description": "Nombre del dispositivo"},
                "action": {"type": "string",  "description": "on / off / toggle / set"},
                "dp":     {"type": "integer", "description": "Data Point (1=on/off por defecto)"},
                "value":  {"description":    "Valor para action=set (boolean, int o string)"},
            },
            "required": ["name", "action"],
        },
    },
    # ── HOME ASSISTANT ────────────────────────────────────────────────────
    {
        "name":        "ha_entities",
        "description": "Lista entidades de Home Assistant. Filtra por dominio o búsqueda de texto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string",  "description": "Dominio: light, switch, sensor, media_player..."},
                "search": {"type": "string",  "description": "Texto a buscar en entity_id o nombre"},
                "limit":  {"type": "integer", "description": "Máximo de resultados (default 30)"},
            },
        },
    },
    {
        "name":        "ha_state",
        "description": "Obtiene el estado completo de una entidad de Home Assistant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "ID de entidad (ej. light.salon)"},
            },
            "required": ["entity_id"],
        },
    },
    {
        "name":        "ha_control",
        "description": "Llama un servicio de Home Assistant para controlar dispositivos (turn_on, toggle, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "ID de entidad objetivo"},
                "service":   {"type": "string", "description": "Servicio: turn_on, turn_off, toggle, light.turn_on..."},
                "data":      {"type": "object", "description": "Parámetros adicionales del servicio (brightness, color_temp, etc.)"},
            },
            "required": ["entity_id", "service"],
        },
    },
    {
        "name":        "ha_automation",
        "description": "Lista, activa o habilita/deshabilita automatizaciones de Home Assistant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action":    {"type": "string", "description": "list / trigger / on / off"},
                "entity_id": {"type": "string", "description": "ID de la automatización (para trigger/on/off)"},
                "search":    {"type": "string", "description": "Filtro de búsqueda (para list)"},
            },
        },
    },
    # ── MQTT ──────────────────────────────────────────────────────────────
    {
        "name":        "mqtt_publish",
        "description": "Publica un mensaje en un topic MQTT. Útil para controlar dispositivos Zigbee2MQTT, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic":   {"type": "string",  "description": "Topic MQTT (ej. zigbee2mqtt/luz_salon/set)"},
                "payload": {"description":     "Contenido del mensaje (string o objeto JSON)"},
                "qos":     {"type": "integer", "description": "QoS 0/1/2 (default 0)"},
                "retain":  {"type": "boolean", "description": "Marcar como retenido (default false)"},
            },
            "required": ["topic", "payload"],
        },
    },
    {
        "name":        "mqtt_subscribe",
        "description": "Escucha mensajes de un topic MQTT durante un tiempo determinado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic":   {"type": "string",  "description": "Topic a escuchar (soporta wildcards # y +)"},
                "timeout": {"type": "number",  "description": "Segundos de escucha (default 5)"},
                "limit":   {"type": "integer", "description": "Máximo de mensajes (default 20)"},
            },
        },
    },
    # ── ESPHOME ───────────────────────────────────────────────────────────
    {
        "name":        "esphome_list",
        "description": "Lista y verifica conectividad de dispositivos ESPHome configurados.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name":        "esphome_control",
        "description": "Controla una entidad de un dispositivo ESPHome (light, switch, fan, button).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name":   {"type": "string", "description": "Nombre del dispositivo ESPHome"},
                "entity": {"type": "string", "description": "Entidad: light/salon, switch/relay, fan/ventilador"},
                "action": {"type": "string", "description": "turn_on / turn_off / toggle (default toggle)"},
                "params": {"type": "object", "description": "Parámetros extra (brightness, effect, speed, etc.)"},
            },
            "required": ["name", "entity"],
        },
    },
    # ── DESCUBRIMIENTO ────────────────────────────────────────────────────
    {
        "name":        "iot_discover",
        "description": "Descubre dispositivos IoT en la red local usando mDNS y escaneo de puertos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subnet":  {"type": "string", "description": "Subnet a escanear (ej. 192.168.1.0/24) — opcional"},
                "timeout": {"type": "number", "description": "Timeout en segundos por host (default 1)"},
            },
        },
    },
]

_TOOL_FNS = {
    "tapo_list":       _tool_tapo_list,
    "tapo_status":     _tool_tapo_status,
    "tapo_on_off":     _tool_tapo_on_off,
    "tapo_set":        _tool_tapo_set,
    "blink_status":    _tool_blink_status,
    "blink_arm":       _tool_blink_arm,
    "blink_snapshot":  _tool_blink_snapshot,
    "blink_clips":     _tool_blink_clips,
    "blink_verify":    _tool_blink_verify,
    "alexa_devices":   _tool_alexa_devices,
    "alexa_speak":     _tool_alexa_speak,
    "alexa_command":   _tool_alexa_command,
    "alexa_volume":    _tool_alexa_volume,
    "tuya_list":       _tool_tuya_list,
    "tuya_status":     _tool_tuya_status,
    "tuya_control":    _tool_tuya_control,
    "ha_entities":     _tool_ha_entities,
    "ha_state":        _tool_ha_state,
    "ha_control":      _tool_ha_control,
    "ha_automation":   _tool_ha_automation,
    "mqtt_publish":    _tool_mqtt_publish,
    "mqtt_subscribe":  _tool_mqtt_subscribe,
    "esphome_list":    _tool_esphome_list,
    "esphome_control": _tool_esphome_control,
    "iot_discover":    _tool_iot_discover,
}

# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS — 4
# ══════════════════════════════════════════════════════════════════════════════

_PROMPTS = [
    {
        "name":        "home_scene",
        "description": "Configura una escena de iluminación y ambiente para el hogar.",
        "arguments": [
            {"name": "scene",   "description": "Escena: cine, lectura, cena, amanecer, fiesta, relax", "required": True},
            {"name": "rooms",   "description": "Habitaciones afectadas", "required": False},
            {"name": "devices", "description": "Dispositivos disponibles (TAPO, Tuya, HA lights...)", "required": False},
        ],
    },
    {
        "name":        "device_schedule",
        "description": "Crea un horario o automatización para dispositivos IoT.",
        "arguments": [
            {"name": "device",    "description": "Dispositivo o grupo de dispositivos", "required": True},
            {"name": "schedule",  "description": "Horario deseado (ej. 'encender a las 7am, apagar a las 11pm')", "required": True},
            {"name": "platform",  "description": "Plataforma: HA, TAPO, Tuya, ESPHome", "required": False},
        ],
    },
    {
        "name":        "security_home",
        "description": "Revisa el estado de seguridad del hogar: cámaras Blink, puertas, sensores.",
        "arguments": [
            {"name": "systems", "description": "Sistemas a revisar: blink, ha_sensors, alexa", "required": False},
            {"name": "report_format", "description": "Formato: resumen, detallado", "required": False},
        ],
    },
    {
        "name":        "energy_report",
        "description": "Genera un informe de consumo energético de los dispositivos monitorizados.",
        "arguments": [
            {"name": "period",  "description": "Período: hoy, semana, mes", "required": False},
            {"name": "devices", "description": "Dispositivos con monitorización de energía (TAPO P110, HA sensors)", "required": False},
        ],
    },
]


def _get_prompt(name: str, args: dict) -> list[dict]:
    if name == "home_scene":
        scene   = args.get("scene", "relax")
        rooms   = args.get("rooms", "toda la casa")
        devices = args.get("devices", "TAPO, Tuya, Home Assistant")
        text = (
            f"Configura la escena de iluminación '{scene}' para {rooms}.\n\n"
            f"Dispositivos disponibles: {devices}\n\n"
            "Para cada dispositivo relevante, proporciona:\n"
            "1. Estado (encendido/apagado)\n"
            "2. Brillo recomendado (si es regulable)\n"
            "3. Color o temperatura de color (si es compatible)\n"
            "4. Comandos exactos a ejecutar (tapo_set, ha_control, tuya_control)\n\n"
            "Escenas de referencia:\n"
            "  cine: luz muy tenue (10-20%), tono cálido (2700K)\n"
            "  lectura: luz media (60-70%), tono neutro (4000K)\n"
            "  cena: luz romántica (30-40%), tono muy cálido (2500K)\n"
            "  amanecer: sube gradualmente del 1% al 80% en 30 min, 2700→4000K\n"
            "  fiesta: colores vivos, alta saturación, ciclo de colores\n"
            "  relax: luz suave (40-50%), tono cálido (3000K)"
        )
    elif name == "device_schedule":
        device   = args.get("device", "todos los dispositivos")
        schedule = args.get("schedule", "")
        platform = args.get("platform", "Home Assistant")
        text = (
            f"Crea una automatización/horario para: {device}\n"
            f"Horario deseado: {schedule}\n"
            f"Plataforma: {platform}\n\n"
            "Proporciona:\n"
            "1. Automatización en formato YAML para HA (si platform=HA)\n"
            "2. Comandos exactos para configurar el horario\n"
            "3. Consideraciones: días de la semana, excepciones, condiciones\n"
            "4. Alternativas más simples si es posible"
        )
    elif name == "security_home":
        systems = args.get("systems", "blink, ha_sensors")
        fmt     = args.get("report_format", "resumen")
        text = (
            f"Revisa el estado de seguridad del hogar.\n"
            f"Sistemas: {systems}\n"
            f"Formato: {fmt}\n\n"
            "Verifica:\n"
            "1. Estado de cámaras Blink (armado/desarmado, batería, conectividad)\n"
            "2. Sensores de movimiento/puertas en HA\n"
            "3. Alertas pendientes\n"
            "4. Últimas detecciones de movimiento\n"
            "5. Recomendaciones de seguridad\n\n"
            "Usa blink_status, ha_entities(domain=binary_sensor), ha_entities(domain=alarm_control_panel)"
        )
    elif name == "energy_report":
        period  = args.get("period", "hoy")
        devices = args.get("devices", "TAPO P110, sensores HA")
        text = (
            f"Genera un informe de consumo energético ({period}).\n"
            f"Dispositivos: {devices}\n\n"
            "Incluye:\n"
            "1. Consumo por dispositivo (kWh)\n"
            "2. Coste estimado (usa 0.15€/kWh si no se conoce la tarifa)\n"
            "3. Comparativa con período anterior\n"
            "4. Dispositivos más consumidores\n"
            "5. Recomendaciones de ahorro\n\n"
            "Usa ha_entities(domain=sensor, search=energy) y tapo_status para enchufes P110"
        )
    else:
        text = f"Prompt desconocido: {name}"

    return [{"role": "user", "content": {"type": "text", "text": text}}]


# ══════════════════════════════════════════════════════════════════════════════
# RESOURCES — 3
# ══════════════════════════════════════════════════════════════════════════════

_RESOURCES = [
    {
        "uri":         "iot://devices_all",
        "name":        "Todos los dispositivos",
        "description": "Lista de todos los dispositivos IoT configurados (TAPO, Blink, Tuya, ESPHome)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "iot://status_dashboard",
        "name":        "Dashboard de estado",
        "description": "Estado actual de los subsistemas configurados (conectividad y config)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "iot://setup_guide",
        "name":        "Guía de configuración",
        "description": "Instrucciones para configurar cada subsistema IoT",
        "mimeType":    "text/plain",
    },
]


def _resource_devices_all() -> str:
    cfg = _load_cfg()
    lines = ["Dispositivos IoT configurados:"]

    tapo_devs = cfg["tapo"].get("devices", [])
    lines.append(f"\nTAPO ({len(tapo_devs)} dispositivos):")
    for d in tapo_devs:
        lines.append(f"  {d.get('name','?'):25s}  {d.get('ip','?')}  {d.get('model','?')}")

    esphome_devs = cfg["esphome"].get("devices", [])
    lines.append(f"\nESPHome ({len(esphome_devs)} dispositivos):")
    for d in esphome_devs:
        lines.append(f"  {d.get('name','?'):25s}  {d.get('host','?')}")

    tuya_devs = cfg["tuya"].get("devices", [])
    lines.append(f"\nTuya ({len(tuya_devs)} dispositivos):")
    for d in tuya_devs:
        lines.append(f"  {d.get('name','?'):25s}  {d.get('ip','?')}")

    blink_cfg = cfg["blink"]
    lines.append(f"\nBlink: {'configurado' if blink_cfg.get('email') else 'no configurado'}")

    ha_cfg = cfg["home_assistant"]
    lines.append(f"\nHome Assistant: {ha_cfg.get('url','?')} — {'token OK' if ha_cfg.get('token') else 'sin token'}")

    mqtt_cfg = cfg["mqtt"]
    lines.append(f"\nMQTT: {mqtt_cfg.get('host','?')}:{mqtt_cfg.get('port',1883)}")

    return "\n".join(lines)


def _resource_status_dashboard() -> str:
    cfg   = _load_cfg()
    lines = ["Dashboard de estado IoT:"]

    def _check_http(url: str, timeout: int = 3) -> str:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return f"✔ online (HTTP {r.status})"
        except Exception as exc:
            return f"✘ offline ({exc})"

    # HA
    ha_url = cfg["home_assistant"].get("url", "")
    if ha_url:
        lines.append(f"\nHome Assistant ({ha_url}): {_check_http(ha_url + '/api/')}")
    else:
        lines.append("\nHome Assistant: no configurado")

    # MQTT
    mqtt_h = cfg["mqtt"].get("host", "localhost")
    mqtt_p = int(cfg["mqtt"].get("port", 1883))
    try:
        s = socket.create_connection((mqtt_h, mqtt_p), timeout=2)
        s.close()
        lines.append(f"\nMQTT broker ({mqtt_h}:{mqtt_p}): ✔ online")
    except Exception as exc:
        lines.append(f"\nMQTT broker ({mqtt_h}:{mqtt_p}): ✘ {exc}")

    # TAPO devices
    for dev in cfg["tapo"].get("devices", []):
        ip = dev.get("ip", "")
        try:
            s = socket.create_connection((ip, 80), timeout=2)
            s.close()
            lines.append(f"\nTAPO {dev.get('name','?')} ({ip}): ✔ alcanzable")
        except Exception:
            lines.append(f"\nTAPO {dev.get('name','?')} ({ip}): ✘ no alcanzable")

    # ESPHome
    for dev in cfg["esphome"].get("devices", []):
        host = dev.get("host", "")
        try:
            s = socket.create_connection((host, 80), timeout=2)
            s.close()
            lines.append(f"\nESPHome {dev.get('name','?')} ({host}): ✔ online")
        except Exception:
            lines.append(f"\nESPHome {dev.get('name','?')} ({host}): ✘ offline")

    # Blink
    blink_token = cfg["blink"].get("auth_token", "")
    if blink_token:
        lines.append("\nBlink: ✔ autenticado (token almacenado)")
    elif cfg["blink"].get("email"):
        lines.append("\nBlink: ⚠ credenciales configuradas, sin token activo (llama blink_status)")
    else:
        lines.append("\nBlink: no configurado")

    return "\n".join(lines)


def _resource_setup_guide() -> str:
    return """Guía de configuración — IoT Assistant

Fichero de config: ~/.oocode/iot_assistant.json

━━━ TAPO (luces y enchufes TP-Link) ━━━━━━━━━━━━━━━━━━━━━━━━━━
  pip install tapo
  Config: email, password de tu cuenta TP-Link/Tapo
  Añadir cada dispositivo con su IP local

━━━ BLINK (cámaras y timbre Amazon) ━━━━━━━━━━━━━━━━━━━━━━━━━━
  Sin dependencias externas — API HTTP directa
  Config: email y password de tu cuenta Blink
  Primera llamada a blink_status hace el login
  Si hay 2FA: llama blink_verify(pin='123456')

━━━ ALEXA (Amazon Echo) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Requiere Home Assistant + integración HACS:
  1. Instala HACS en HA: https://hacs.xyz
  2. Instala "Alexa Media Player" desde HACS
  3. Configura con tus credenciales de Amazon
  4. Añade el token de HA en iot_assistant.json
  Los dispositivos aparecerán como media_player.echo_*

━━━ TUYA / SMART LIFE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  pip install tinytuya
  1. Crea cuenta en https://iot.tuya.com
  2. Crea proyecto, añade tus dispositivos desde la app Smart Life
  3. Obtén device_id y local_key de cada dispositivo
  Config: access_id, access_key del proyecto Tuya IoT

━━━ HOME ASSISTANT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Sin dependencias externas — REST API
  1. HA instalado en tu red local
  2. Crear Long-Lived Access Token: HA → Perfil → Seguridad
  Config: url de HA + token

━━━ MQTT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  pip install paho-mqtt
  Instalar broker: sudo apt install mosquitto
  Compatible con Zigbee2MQTT, Z-Wave JS UI, etc.

━━━ ESPHOME ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Sin dependencias externas — HTTP nativo
  Añadir a tu config .yaml de ESPHome:
    web_server:
      port: 80
  Config: host (IP o hostname.local)

━━━ ZIGBEE (vía MQTT) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Instala Zigbee2MQTT: https://www.zigbee2mqtt.io
  Controla con mqtt_publish:
    topic: "zigbee2mqtt/nombre_dispositivo/set"
    payload: {"state": "ON", "brightness": 128}
"""


_RESOURCE_FNS = {
    "iot://devices_all":      _resource_devices_all,
    "iot://status_dashboard": _resource_status_dashboard,
    "iot://setup_guide":      _resource_setup_guide,
}


# ══════════════════════════════════════════════════════════════════════════════
# MCP dispatcher
# ══════════════════════════════════════════════════════════════════════════════

def _handle(req: dict) -> dict | None:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools":     {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts":   {"listChanged": False},
            },
            "serverInfo": {"name": "iot-assistant", "version": "1.1.0"},
        })

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _ok(req_id, {"tools": _TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        fn = _TOOL_FNS.get(tool_name)
        if not fn:
            return _err(req_id, -32601, f"Tool desconocida: {tool_name}")
        try:
            result = fn(tool_args)
        except Exception as exc:
            result = f"Error interno: {exc}"
        return _ok(req_id, {
            "content": [{"type": "text", "text": str(result)}],
            "isError": False,
        })

    if method == "resources/list":
        return _ok(req_id, {"resources": _RESOURCES})

    if method == "resources/read":
        uri = params.get("uri", "")
        fn  = _RESOURCE_FNS.get(uri)
        if not fn:
            return _err(req_id, -32601, f"Resource desconocido: {uri}")
        try:
            content = fn()
        except Exception as exc:
            content = f"Error: {exc}"
        return _ok(req_id, {
            "contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]
        })

    if method == "prompts/list":
        return _ok(req_id, {"prompts": _PROMPTS})

    if method == "prompts/get":
        name  = params.get("name", "")
        pargs = params.get("arguments", {})
        found = next((p for p in _PROMPTS if p["name"] == name), None)
        if not found:
            return _err(req_id, -32601, f"Prompt desconocido: {name}")
        messages = _get_prompt(name, pargs)
        return _ok(req_id, {"description": found["description"], "messages": messages})

    if req_id is not None:
        return _err(req_id, -32601, f"Método desconocido: {method}")
    return None


def main() -> None:
    while True:
        req = _recv()
        if req is None:
            break
        resp = _handle(req)
        if resp is not None:
            _send(resp)


if __name__ == "__main__":
    main()
