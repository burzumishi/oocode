# System Assistant MCP Server

Servidor MCP independiente que expone herramientas de administración del sistema operativo. Se ejecuta como subproceso stdio por OOCode y expone sus tools al modelo igual que las tools internas.

## Activación

El servidor se registra en `~/.oocode/oocode.json` bajo `mcp.servers`:

```json
{
  "name": "system-assistant",
  "cmd": ["python", "~/oocode/mcp_servers/system_assistant.py"],
  "enabled": true,
  "description": "Administración del sistema: paquetes, servicios, red, disco, firewall"
}
```

Para desactivarlo sin borrar la configuración, cambiar `"enabled": false`.

## Detección automática del SO

Al arrancar, el servidor lee `/etc/os-release` y determina la familia del sistema:

| Familia | Gestor de paquetes | Tools expuestas |
|---------|-------------------|-----------------|
| Debian / Ubuntu | `apt` | `apt_*` (7 tools) |
| RedHat / Fedora / RHEL | `dnf` o `yum` | `dnf_*` + `rpm_query` (6 tools) |
| Ambas | — | systemd, red, disco, usuarios, procesos, firewall, sistema |

El número de tools expuestas aparece en el mensaje de arranque:
```
[system-assistant] MCP server v1.0 iniciado  SO: Debian GNU/Linux  pkg: apt  tools: 34
```

## Referencia de tools

### Servicios (systemd)

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `systemctl_status` | Estado de uno o varios servicios | auto |
| `systemctl_action` | start / stop / restart / enable / disable / reload | ask |
| `journalctl` | Logs del sistema o de un servicio (últimas N líneas) | auto |

```
# Ejemplos
systemctl_status  service="nginx"
systemctl_action  service="nginx"  action="restart"
journalctl        service="nginx"  lines=50
journalctl        lines=100        # logs del sistema
```

### Paquetes — Debian/Ubuntu (`apt_*`)

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `apt_update` | Actualiza lista de paquetes (`apt update`) | ask |
| `apt_upgrade` | Muestra paquetes actualizables (dry-run) | ask |
| `apt_install` | Instala paquetes | ask |
| `apt_remove` | Elimina paquetes | ask |
| `apt_search` | Busca paquetes por nombre/descripción | auto |
| `apt_info` | Información detallada de un paquete | auto |
| `apt_list_installed` | Lista paquetes instalados con versión | auto |

```
apt_search       query="vim"
apt_info         package="python3-httpx"
apt_install      packages="ripgrep fd-find"
apt_list_installed  filter="python3"
```

### Paquetes — RedHat/Fedora (`dnf_*`, `rpm_query`)

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `dnf_update` | Lista actualizaciones disponibles | auto |
| `dnf_install` | Instala paquetes | ask |
| `dnf_remove` | Elimina paquetes | ask |
| `dnf_search` | Busca paquetes | auto |
| `dnf_info` | Información de un paquete | auto |
| `rpm_query` | Consulta base RPM (ficheros, versión, changelog) | auto |

### Red

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `net_interfaces` | Interfaces de red con IP, MAC y estado | auto |
| `net_connections` | Conexiones activas (`ss -tulpn`) | auto |
| `net_ping` | Ping a un host (máx. 5 paquetes) | auto |
| `net_dns` | Resolución DNS con `dig`/`host` | auto |

```
net_ping  host="8.8.8.8"  count=3
net_dns   host="github.com"  type="A"
```

### Disco y sistema de ficheros

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `disk_usage` | Uso de disco por partición (`df -h`) | auto |
| `disk_inodes` | Uso de inodos por partición | auto |
| `dir_size` | Tamaño de un directorio (`du -sh`) | auto |
| `lsblk_info` | Dispositivos de bloque y particiones | auto |

```
dir_size  path="~/Documents"
```

### Usuarios y grupos

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `user_list` | Lista usuarios del sistema | auto |
| `user_info` | Info de un usuario (grupos, shell, home) | auto |
| `group_list` | Lista grupos del sistema | auto |
| `who_logged` | Usuarios con sesión activa (`who / w`) | auto |

```
user_info  username="user"
```

### Procesos y recursos

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `ps_list` | Procesos activos con CPU/RAM (filtrable) | auto |
| `top_snapshot` | Snapshot instantáneo de CPU y memoria | auto |
| `kill_process` | Enviar señal a un proceso (TERM por defecto) | ask |

```
ps_list        filter="python"
kill_process   pid=1234  signal="TERM"
```

### Firewall

Detecta automáticamente `ufw` (Debian/Ubuntu) o `firewalld` (RedHat). Si ninguno está disponible, las tools devuelven un mensaje informativo.

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `fw_status` | Estado del firewall | auto |
| `fw_rules` | Reglas activas | auto |
| `fw_allow` | Añadir regla de entrada | ask |
| `fw_deny` | Bloquear regla de entrada | ask |

```
fw_allow  rule="80/tcp"
fw_deny   rule="from 1.2.3.4"
```

### Sistema general

| Tool | Descripción | Permiso |
|------|-------------|---------|
| `sys_info` | Resumen: SO, kernel, RAM, CPU, uptime | auto |
| `sys_updates` | Paquetes con actualizaciones de seguridad | auto |
| `sys_logs` | Últimas líneas de logs del sistema | auto |
| `env_vars` | Variables de entorno (sin secretos) | auto |
| `cron_list` | Crontabs del usuario y del sistema | auto |

```
sys_logs   lines=50
env_vars   filter="PATH"
```

## Naming en OOCode

Las tools del servidor se registran con prefijo `mcp_system_assistant_`:

```
mcp_system_assistant_sys_info
mcp_system_assistant_apt_install
mcp_system_assistant_systemctl_action
```

Los permisos heredan automáticamente del bare name (`sys_info`, `apt_install`, etc.) via `PermissionManager.resolve_mode()`. El comando `/elevated` eleva todos los permisos incluyendo los de este servidor.

## Side-effects y caché

Las tools con side-effects están en `_NO_CACHE_BASE` de `tools/registry.py` y nunca se cachean intra-turno:

```
systemctl_action, kill_process, fw_allow, fw_deny
apt_update, apt_upgrade, apt_install, apt_remove
dnf_update, dnf_install, dnf_remove
```

Las tools de sólo lectura (`sys_info`, `disk_usage`, `net_interfaces`, etc.) sí se cachean si se llaman dos veces con los mismos argumentos en el mismo turno.

## Seguridad

- `kill_process` requiere permiso `ask` — el usuario confirma cada señal
- `systemctl_action` requiere `ask` — el usuario confirma start/stop/restart
- Las tools de firewall requieren `ask` — cambios de reglas son destructivos
- Las tools de paquetes (`apt_install`, `apt_remove`) requieren `ask`
- Las tools de solo lectura son `auto` — información del sistema no modifica nada

Para entornos de servidor o CI donde se quiere más control, configurar los permisos en `~/.oocode/oocode.json`:

```json
"systemctl_action": "deny",
"apt_install": "deny",
"fw_allow": "deny"
```
