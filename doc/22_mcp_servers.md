# 22 — Servidores MCP

OOCode incluye 5 servidores MCP bundled que se ejecutan como procesos independientes y se comunican via stdio con JSON-RPC 2.0 (protocolo MCP 2024-11-05).

## Activación

Cada servidor se activa con su flag en `~/.oocode/oocode.json`:

```json
{
  "mcp": {
    "oocodeAssistant":    { "enabled": true  },
    "systemAssistant":    { "enabled": true  },
    "homeOfficeAssistant":{ "enabled": false },
    "securityAssistant":  { "enabled": false },
    "iotAssistant":       { "enabled": false },
    "requestTimeout": 30.0
  }
}
```

Estado en el REPL:
```
/mcp                     # estado de todos los servidores
/mcp reload <nombre>     # recargar servidor
```

---

## 1. oocode-assistant

**Fichero:** `mcp_servers/oocode_assistant.py`  
**Flag:** `oocodeAssistant.enabled` (activo por defecto)  
**Descripción:** Herramientas de desarrollo: git, docker, filesystem, búsqueda de código, símbolos, utilidades

### Tools (categorías)

**Filesystem y lectura:**

| Tool | Descripción |
|------|-------------|
| `read_files` | Leer múltiples ficheros en un batch |
| `write_file` | Crear o sobreescribir un fichero |
| `find_files` | Buscar ficheros por patrón glob |
| `list_recent_files` | Ficheros modificados recientemente |
| `read_project_file` | Leer fichero relativo al directorio del proyecto |

**Búsqueda de código:**

| Tool | Descripción |
|------|-------------|
| `grep_code` | Buscar patrón regex en código fuente |
| `multi_grep` | Múltiples patrones en una sola búsqueda |
| `code_outline` | Estructura del código: funciones, clases, métodos (ast.parse + ctags) |
| `read_sections` | Extraer funciones/clases por nombre sin leer el fichero entero |
| `symbol_lookup` | Buscar símbolo en el proyecto con ripgrep |
| `affected_files` | Ficheros que usan un símbolo dado |

**Análisis y utilidades:**

| Tool | Descripción |
|------|-------------|
| `get_datetime` | Fecha y hora actuales |
| `system_info` | Información del sistema |
| `run_quick_check` | Verificación rápida de un fichero (sintaxis, linters) |
| `search_todos` | Buscar TODOs/FIXMEs en el proyecto |
| `port_check` | Verificar si un puerto está en uso |
| `http_get` | Petición HTTP GET |
| `calculate` | Evaluar expresión matemática |
| `diff_files` | Diff entre dos ficheros |
| `code_compare` | Comparar implementaciones de funciones |
| `env_check` | Verificar variables de entorno |
| `json_format` | Formatear JSON |
| `json_validate` | Validar JSON |
| `yaml_validate` | Validar YAML |
| `jq_query` | Ejecutar consulta jq sobre JSON |
| `hash_text` | Calcular hash de un texto |
| `process_list` | Lista de procesos activos |

**Git:**

| Tool | Descripción |
|------|-------------|
| `git_status` | Estado del repositorio |
| `git_diff` | Diff de cambios |
| `git_log` | Historial de commits |
| `git_add` | Stage ficheros |
| `git_commit` | Crear commit |
| `git_push` | Push al remoto |
| `git_pull` | Pull del remoto |
| `git_branch` | Gestión de ramas |
| `git_stash` | Stash de cambios |
| `git_patch` | Aplicar/crear parches |
| `git_clone` | Clonar repositorio |
| `git_worktree` | Gestión de git worktrees |
| `git_blame` | Ver autoría por línea |
| `git_rebase` | Rebase interactivo |
| `git_tag` | Gestión de tags |
| `git_cherry_pick` | Cherry-pick de commits |

**Docker:**

| Tool | Descripción |
|------|-------------|
| `docker_ps` | Lista de contenedores |
| `docker_logs` | Logs de un contenedor |
| `docker_exec` | Ejecutar comando en contenedor |
| `docker_inspect` | Inspeccionar contenedor |
| `docker_images` | Lista de imágenes |
| `docker_stop` | Parar contenedor |
| `docker_rm` | Eliminar contenedor |
| `docker_cp` | Copiar ficheros entre host y contenedor |
| `compose_version` | Versión de docker compose |
| `compose_services` | Servicios del compose |
| `compose_status` | Estado de servicios |
| `compose_up` | Levantar servicios |
| `compose_down` | Parar y eliminar servicios |
| `compose_logs` | Logs de servicios compose |
| `compose_build` | Construir imágenes |
| `compose_pull` | Pull de imágenes |
| `compose_exec` | Ejecutar en servicio |
| `compose_run` | Ejecutar comando one-off |

### Prompts (9)

| Nombre | Descripción |
|--------|-------------|
| `code_review` | Revisión de código con sugerencias |
| `debug_session` | Sesión de debugging guiado |
| `commit_message` | Generar mensaje de commit desde un diff |
| `test_cases` | Generar casos de test para una función |
| `sql_query` | Generar/optimizar consultas SQL |
| `explain_code` | Explicar código en lenguaje natural |
| `refactor_code` | Refactorizar código con justificación |
| `design_api` | Diseñar estructura de API REST |
| `document_code` | Generar documentación/docstrings |

### Resources

El servidor expone recursos estáticos como referencia contextual para el LLM.

---

## 2. system-assistant

**Fichero:** `mcp_servers/system_assistant.py`  
**Flag:** `systemAssistant.enabled` (activo por defecto)  
**Descripción:** Administración del sistema: servicios, paquetes, red, disco, usuarios, procesos, firewall

### Tools (categorías)

**Servicios systemd:**

| Tool | Descripción |
|------|-------------|
| `systemctl_status` | Estado de un servicio |
| `systemctl_action` | start/stop/restart/enable/disable |
| `journalctl` | Logs del sistema/servicio |

**Gestión de paquetes:**

| Tool | Descripción |
|------|-------------|
| `apt_update/upgrade/install/remove/search/info/list_installed` | APT (Debian/Ubuntu) |
| `dnf_update/install/remove/search/info` | DNF (Fedora/RHEL) |
| `rpm_query` | Consultar paquetes RPM |

**Red:**

| Tool | Descripción |
|------|-------------|
| `net_interfaces` | Interfaces de red |
| `net_connections` | Conexiones activas |
| `net_ping` | Ping a un host |
| `net_dns` | Resolución DNS |

**Disco y almacenamiento:**

| Tool | Descripción |
|------|-------------|
| `disk_usage` | Uso de disco por partición |
| `disk_inodes` | Inodos disponibles |
| `dir_size` | Tamaño de un directorio |
| `lsblk_info` | Dispositivos de bloque |

**Usuarios y sesiones:**

| Tool | Descripción |
|------|-------------|
| `user_list` | Lista de usuarios del sistema |
| `user_info` | Información de un usuario |
| `group_list` | Grupos del sistema |
| `who_logged` | Usuarios conectados |

**Procesos:**

| Tool | Descripción |
|------|-------------|
| `ps_list` | Lista de procesos |
| `top_snapshot` | Snapshot de uso de CPU/RAM |
| `kill_process` | Enviar señal a un proceso |

**Firewall:**

| Tool | Descripción |
|------|-------------|
| `fw_status` | Estado del firewall (ufw/firewalld) |
| `fw_rules` | Reglas activas |
| `fw_allow/deny` | Añadir reglas |

**Sistema:**

| Tool | Descripción |
|------|-------------|
| `sys_info` | Información general del sistema |
| `sys_updates` | Actualizaciones disponibles |
| `sys_logs` | Logs del sistema |
| `env_vars` | Variables de entorno |
| `cron_list` | Lista de tareas cron |

### Prompts (5)

| Nombre | Descripción |
|--------|-------------|
| `system_audit` | Auditoría de seguridad del sistema |
| `service_debug` | Debug de un servicio systemd |
| `network_troubleshoot` | Diagnóstico de problemas de red |
| `disk_cleanup` | Plan de limpieza de disco |
| `user_management` | Gestión de usuarios y permisos |

---

## 3. home-office-assistant

**Fichero:** `mcp_servers/home_office_assistant.py`  
**Flag:** `homeOfficeAssistant.enabled` (desactivado por defecto)  
**Descripción:** 77+ herramientas para documentación corporativa O365, email, calendario, notas, OCR, CMDB

**Requisito:** `pip install python-docx python-pptx openpyxl matplotlib pillow docxtpl`

### Tools (categorías)

**Documentos Word:**

| Tool | Descripción |
|------|-------------|
| `doc_create` | Crear documento Word con content_blocks (title/heading/paragraph/table/chart/image/toc…) |
| `doc_fill_template` | Rellenar plantilla DOCX con Jinja2/docxtpl |
| `doc_read` | Leer contenido de un documento Word |
| `doc_read_template_fields` | Listar campos de una plantilla |
| `doc_list_templates` | Listar plantillas disponibles |
| `doc_insert_chart_native` | Insertar gráfico nativo OOXML en Word |
| `doc_insert_diagram` | Insertar diagrama (Mermaid/tabla de diagrama) |
| `doc_embed_image` | Incrustar imagen en documento |
| `doc_apply_style` | Aplicar estilo O365 (Calibri/Calibri Light) |
| `doc_set_table_style` | Aplicar estilo a tabla en Word |
| `doc_extract_metadata` | Extraer metadatos del documento |
| `doc_compare` | Comparar dos documentos |
| `doc_convert` | Convertir entre formatos (docx/pdf/html) |
| `doc_word_count` | Contar palabras/páginas |
| `doc_update_section` | Actualizar una sección por heading |
| `doc_version_bump` | Incrementar versión del documento |
| `doc_project_save` | Guardar documento con gestión de versiones |
| `doc_create_rfc` | Crear RFC técnico con estructura estándar |

**Excel / CSV:**

| Tool | Descripción |
|------|-------------|
| `xlsx_read` | Leer hoja de cálculo |
| `xlsx_write` | Escribir datos en Excel |
| `xlsx_insert_chart` | Insertar gráfico en Excel |
| `xlsx_apply_conditional_format` | Formato condicional |
| `csv_analyze` | Analizar fichero CSV |

**Presentaciones PowerPoint:**

| Tool | Descripción |
|------|-------------|
| `pptx_create` | Crear presentación PPTX |
| `pptx_add_slide` | Añadir diapositiva |
| `pptx_insert_chart` | Insertar gráfico en diapositiva |
| `pptx_read` | Leer contenido de presentación |

**Email:**

| Tool | Descripción |
|------|-------------|
| `email_list` | Listar emails de la bandeja de entrada |
| `email_read` | Leer un email |
| `email_send` | Enviar email |
| `email_search` | Buscar emails |

**Calendario:**

| Tool | Descripción |
|------|-------------|
| `cal_list` | Listar eventos del calendario |
| `cal_add` | Añadir evento |
| `cal_search` | Buscar eventos |

**Notas:**

| Tool | Descripción |
|------|-------------|
| `notes_list` | Listar notas |
| `notes_search` | Buscar notas |
| `notes_save` | Guardar nota |

**OCR y procesamiento:**

| Tool | Descripción |
|------|-------------|
| `image_to_text` | OCR: extraer texto de imagen |
| `pdf_extract_text` | Extraer texto de PDF |
| `markdown_to_html` | Convertir Markdown a HTML |
| `insert_chart` | Insertar gráfico dinámico (matplotlib) |

**Contactos y CMDB:**

| Tool | Descripción |
|------|-------------|
| `contact_search` | Buscar contacto |
| `cmdb_search` | Buscar en CMDB (Configuration Management DB) |
| `cmdb_update` | Actualizar registro CMDB |
| `asset_register_add` | Añadir activo al registro |

**Gestión de proyectos:**

| Tool | Descripción |
|------|-------------|
| `project_context_read` | Leer contexto del proyecto Office |
| `project_init_office` | Inicializar proyecto Office (estructura de carpetas) |

### Prompts (4)

| Nombre | Descripción |
|--------|-------------|
| `executive_summary` | Resumen ejecutivo de proyecto |
| `business_case` | Business case con ROI y análisis |
| `weekly_status` | Informe de estado semanal |
| `meeting_minutes` | Acta de reunión |

### Content blocks para doc_create

Los documentos Word se crean con `content_blocks`, una lista de bloques estructurados:

```json
{
  "content_blocks": [
    {"type": "title", "text": "Título del documento"},
    {"type": "heading", "text": "Sección 1", "level": 1},
    {"type": "paragraph", "text": "Texto del párrafo"},
    {"type": "bullet_list", "items": ["punto 1", "punto 2"]},
    {"type": "numbered_list", "items": ["paso 1", "paso 2"]},
    {"type": "checklist", "items": [{"text": "tarea", "checked": false}]},
    {"type": "table", "headers": ["Col1", "Col2"], "rows": [["a", "b"]]},
    {"type": "chart", "chart_type": "bar", "title": "Ventas", "data": {...}},
    {"type": "image", "path": "/ruta/imagen.png"},
    {"type": "code_block", "code": "print('hola')", "language": "python"},
    {"type": "callout", "text": "Nota importante", "style": "warning"},
    {"type": "toc"},
    {"type": "pagebreak"},
    {"type": "horizontal_rule"}
  ]
}
```

---

## 4. security-assistant

**Fichero:** `mcp_servers/security_assistant.py`  
**Flag:** `securityAssistant.enabled` (desactivado por defecto)  
**Descripción:** 24 herramientas de ciberseguridad: reconocimiento, análisis web, criptografía, CTF, defensivas

**AVISO:** Las herramientas ofensivas tienen permiso `ask` por defecto. Úsalas solo en sistemas propios o con autorización explícita.

### Tools (categorías)

**Reconocimiento:**

| Tool | Descripción |
|------|-------------|
| `nmap_scan` | Escaneo de puertos con nmap |
| `port_scan` | Escaneo de puertos rápido |
| `ssl_check` | Verificar certificado SSL/TLS |
| `whois_lookup` | Consulta WHOIS |
| `dns_enum` | Enumeración DNS |
| `http_headers` | Inspeccionar headers HTTP |

**Análisis web:**

| Tool | Descripción |
|------|-------------|
| `nikto_scan` | Escaneo de vulnerabilidades web con nikto |
| `gobuster_run` | Enumeración de directorios/subdominios |
| `curl_request` | Petición HTTP personalizada |

**Criptografía y codificación:**

| Tool | Descripción |
|------|-------------|
| `encode_decode` | Codificar/decodificar (base64, hex, url, rot13…) |
| `hash_crack` | Identificar y crackear hashes |
| `jwt_decode` | Decodificar JWT y verificar firma |
| `cert_inspect` | Inspeccionar certificado X.509 |
| `xor_decode` | Decodificar XOR |
| `steganography_check` | Análisis básico de esteganografía |
| `base_convert` | Conversión entre bases numéricas |
| `hex_dump` | Volcado hexadecimal de fichero |

**CTF:**

| Tool | Descripción |
|------|-------------|
| `cve_lookup` | Buscar CVE en base de datos |
| `log_analyze` | Analizar logs en busca de anomalías |
| `secret_scan` | Buscar credenciales/secretos en código |

**Defensivas:**

| Tool | Descripción |
|------|-------------|
| `fw_audit` | Auditoría del firewall |
| `ssh_key_audit` | Auditoría de claves SSH |
| `sudoers_review` | Revisión de configuración sudo |
| `file_integrity_check` | Verificar integridad de ficheros |

### Prompts (4)

| Nombre | Descripción |
|--------|-------------|
| `pentest_report` | Plantilla de informe de pentesting |
| `vulnerability_assessment` | Evaluación de vulnerabilidades |
| `ctf_approach` | Metodología para CTF challenges |
| `security_hardening` | Guía de hardening del sistema |

---

## 5. iot-assistant

**Fichero:** `mcp_servers/iot_assistant.py`  
**Flag:** `iotAssistant.enabled` (desactivado por defecto)  
**Descripción:** 25 herramientas para IoT: TAPO, Blink, Alexa, Tuya, Home Assistant, MQTT, ESPHome

**AVISO:** Las herramientas de control tienen permiso `ask` por defecto.

### Tools (categorías)

**TAPO (TP-Link):**

| Tool | Descripción |
|------|-------------|
| `tapo_list` | Listar dispositivos TAPO |
| `tapo_status` | Estado de un dispositivo |
| `tapo_on_off` | Encender/apagar |
| `tapo_set` | Configurar parámetros (brillo, color) |

**Blink (cámaras):**

| Tool | Descripción |
|------|-------------|
| `blink_status` | Estado del sistema Blink |
| `blink_arm` | Armar/desarmar alarma |
| `blink_snapshot` | Capturar snapshot de cámara |
| `blink_clips` | Ver clips grabados |
| `blink_verify` | Verificar conectividad |

**Amazon Alexa:**

| Tool | Descripción |
|------|-------------|
| `alexa_devices` | Listar dispositivos Alexa |
| `alexa_speak` | Hacer hablar a Alexa |
| `alexa_command` | Enviar comando a Alexa |
| `alexa_volume` | Controlar volumen |

**Tuya:**

| Tool | Descripción |
|------|-------------|
| `tuya_list` | Listar dispositivos Tuya |
| `tuya_status` | Estado de dispositivo |
| `tuya_control` | Controlar dispositivo |

**Home Assistant:**

| Tool | Descripción |
|------|-------------|
| `ha_entities` | Listar entidades de HA |
| `ha_state` | Estado de una entidad |
| `ha_control` | Controlar entidad |
| `ha_automation` | Gestionar automatizaciones |

**MQTT:**

| Tool | Descripción |
|------|-------------|
| `mqtt_publish` | Publicar mensaje MQTT |
| `mqtt_subscribe` | Suscribirse a topic MQTT |

**ESPHome:**

| Tool | Descripción |
|------|-------------|
| `esphome_list` | Listar dispositivos ESPHome |
| `esphome_control` | Controlar dispositivo ESPHome |

**Descubrimiento:**

| Tool | Descripción |
|------|-------------|
| `iot_discover` | Descubrir dispositivos IoT en la red |

### Prompts (4)

| Nombre | Descripción |
|--------|-------------|
| `home_automation` | Configurar automatizaciones del hogar |
| `energy_monitoring` | Monitorizar consumo energético |
| `security_setup` | Configurar sistema de seguridad IoT |
| `device_troubleshoot` | Diagnóstico de dispositivos IoT |

---

## Patrón interno de los MCP servers

Todos los servidores siguen el mismo patrón:

```python
_TOOLS = [
    {
        "name": "tool_name",
        "description": "Descripción de la herramienta",
        "inputSchema": {
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "..."}
            },
            "required": ["param"]
        }
    }
]

_TOOL_FNS = {
    "tool_name": _tool_function
}

_PROMPTS = [...]
_RESOURCES = [...]

def main():
    # Bucle JSON-RPC sobre stdio
    for line in sys.stdin:
        req = json.loads(line)
        method = req["method"]
        if method == "tools/list":
            respond({"tools": _TOOLS})
        elif method == "tools/call":
            result = _TOOL_FNS[req["params"]["name"]](req["params"]["arguments"])
            respond({"content": [{"type": "text", "text": result}]})
        elif method == "prompts/list":
            respond({"prompts": _PROMPTS})
        elif method == "resources/list":
            respond({"resources": _RESOURCES})
```

## Servidores MCP externos

OOCode soporta servidores MCP externos de dos formas: configuración manual en `oocode.json` y el gestor interactivo con catálogo integrado.

### Gestión con `/mcp` — catálogo y hot-add

El catálogo bundled (`mcp_servers/catalog.json`) contiene servidores MCP populares preconfigurados. No requiere conexión a internet — todo funciona offline.

```
/mcp catalog                          # lista el catálogo completo de servidores disponibles
/mcp catalog search filesystem        # buscar en el catálogo por nombre o descripción
/mcp check filesystem                 # verificar si los prerequisitos (npx, python…) están instalados
/mcp install filesystem /ruta/raíz   # añadir a oocode.json + activar en la sesión actual (hot-add)
/mcp add mi-srv python /ruta/srv.py  # añadir servidor personalizado
/mcp remove mi-servidor              # eliminar de oocode.json
/mcp enable mi-servidor              # activar servidor (sin reiniciar)
/mcp disable mi-servidor             # desactivar servidor (sin reiniciar)
/mcp reload mi-servidor              # recargar servidor (para un solo servidor)
/mcp restart                         # reiniciar todos los servidores MCP
```

El hot-add (`/mcp install`, `/mcp enable`) conecta el servidor a la sesión activa sin necesidad de reiniciar OOCode. Las herramientas del nuevo servidor quedan disponibles de inmediato.

**Entradas del catálogo (catalog.json):**

| Nombre | Descripción |
|--------|-------------|
| `filesystem` | Acceso a ficheros del sistema (npx @modelcontextprotocol/server-filesystem) |
| `memory` | Almacenamiento key-value persistente (npx @modelcontextprotocol/server-memory) |
| `brave-search` | Búsqueda web con Brave API |
| `github` | API de GitHub: repos, issues, PRs |
| `gitlab` | API de GitLab |
| `postgres` | Consultas a PostgreSQL |
| `sqlite` | Consultas a SQLite |
| `puppeteer` | Automatización de navegador web |

### Gestión del estado con `/mcp`

```
/mcp                         # estado de todos los servidores (bundled + externos)
/mcp status <nombre>         # estado detallado de un servidor
/mcp reload <nombre>         # reconectar un servidor concreto
/mcp restart                 # reiniciar todos los servidores MCP
```

### Configuración manual en `oocode.json`

Para añadir servidores sin usar el catálogo:

```json
{
  "mcp": {
    "servers": [
      {
        "name": "mi-servidor",
        "cmd":  ["npx", "@modelcontextprotocol/server-filesystem", "/ruta"],
        "env":  {"HOME": "/home/usuario"}
      },
      {
        "name": "servidor-python",
        "cmd":  ["python", "/ruta/a/servidor.py"],
        "env":  {}
      }
    ]
  }
}
```
