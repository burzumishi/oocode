# 22 — Servidores MCP

OOCode incluye 12 servidores MCP bundled que se ejecutan como procesos independientes y se comunican via stdio con JSON-RPC 2.0 (protocolo MCP 2024-11-05).

| Servidor | Tools | Por defecto |
|----------|-------|-------------|
| `oocode-assistant` | 54 | activo |
| `devops-assistant` | 66 | activo |
| `system-assistant` | ~40 | activo |
| `database-assistant` | 20 | desactivado |
| `word-assistant` | 29 | desactivado |
| `excel-assistant` | 16 | desactivado |
| `pptx-assistant` | 7 | desactivado |
| `mail-assistant` | 11 | desactivado |
| `cmdb-assistant` | 3 | desactivado |
| `security-assistant` | 24 | desactivado |
| `iot-assistant` | 25 | desactivado |
| `http-client-assistant` | 17 | desactivado |

## Activación

Cada servidor se activa con su flag en `~/.oocode/oocode.json`:

```json
{
  "mcp": {
    "oocodeAssistant":    { "enabled": true  },
    "devopsAssistant":    { "enabled": true  },
    "systemAssistant":    { "enabled": true  },
    "databaseAssistant":  { "enabled": false },
    "wordAssistant":      { "enabled": false },
    "excelAssistant":     { "enabled": false },
    "pptxAssistant":      { "enabled": false },
    "mailAssistant":      { "enabled": false },
    "cmdbAssistant":      { "enabled": false },
    "securityAssistant":  { "enabled": false },
    "iotAssistant":       { "enabled": false },
    "httpClientAssistant":{ "enabled": false },
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
**Descripción:** 54 herramientas de análisis de código, edición, utilidades y linting. Git, Docker y fs-mutations se movieron a `devops-assistant`.

### Tools (categorías)

**Filesystem y lectura:**

| Tool | Descripción |
|------|-------------|
| `read_files` | Leer múltiples ficheros en un batch |
| `write_file` | Crear o sobreescribir un fichero |
| `ls_file` / `ls_dir` | Listar fichero/directorio con permisos |
| `find_files` / `find_file` / `find_dir` | Buscar ficheros y directorios |
| `list_recent_files` | Ficheros modificados recientemente |
| `read_project_file` | Leer fichero relativo al directorio del proyecto |
| `file_stat` | Metadatos de un fichero (permisos, tamaño, fechas) |

**Búsqueda de código:**

| Tool | Descripción |
|------|-------------|
| `grep_code` | Buscar patrón regex en código fuente |
| `multi_grep` | Múltiples patrones en una sola búsqueda |
| `code_outline` | Estructura del código: funciones, clases, métodos (ast.parse + ctags) |
| `read_sections` | Extraer funciones/clases por nombre sin leer el fichero entero |
| `symbol_lookup` | Buscar símbolo en el proyecto con ripgrep |
| `affected_files` | Ficheros que usan un símbolo dado |
| `find_symbol` / `list_symbols` | Buscar/listar símbolos con ctags |
| `analyze_codebase` | Resumen estructural del proyecto |
| `code_compare` | Comparar implementaciones de funciones entre ficheros |

**Edición avanzada:**

| Tool | Descripción |
|------|-------------|
| `bulk_replace` | Reemplazos múltiples en un fichero |
| `regex_replace` | Reemplazo con regex en fichero |
| `smart_replace` | Reemplazo inteligente con contexto |
| `patch_apply` | Aplicar un parche diff |
| `pre_edit_check` | Verificación antes de editar (busca old_string) |
| `context_before_edit` | Leer contexto antes de modificar |

**Análisis y utilidades:**

| Tool | Descripción |
|------|-------------|
| `get_datetime` | Fecha y hora actuales |
| `system_info` | Información del sistema |
| `run_quick_check` | Verificación rápida (sintaxis, linters) |
| `search_todos` | Buscar TODOs/FIXMEs en el proyecto |
| `port_check` | Verificar si un puerto está en uso |
| `http_get` | Petición HTTP GET |
| `calculate` | Evaluar expresión matemática |
| `diff_files` | Diff entre dos ficheros |
| `env_check` | Verificar variables de entorno |
| `json_format` / `json_validate` | Formatear y validar JSON |
| `yaml_validate` | Validar YAML |
| `jq_query` | Ejecutar consulta jq |
| `xml_format` / `xml_validate` | Formatear y validar XML |
| `render_markdown` | Renderizar markdown a HTML |
| `hash_text` | Calcular hash de un texto |
| `url_encode` | Codificar URL |
| `process_list` | Lista de procesos activos |

**Linting:**

| Tool | Descripción |
|------|-------------|
| `lint_file` / `lint_project` | Linting de fichero/proyecto |
| `gitlint_check` | Validar formato de mensajes git |
| `ansible_lint` | Linting de playbooks Ansible |
| `efm_config_update` | Actualizar configuración efm-langserver |

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

## 2. devops-assistant

**Fichero:** `mcp_servers/devops_assistant.py`  
**Flag:** `devopsAssistant.enabled` (activo por defecto)  
**Descripción:** 66 herramientas para flujos DevOps: git, Docker/Compose, build, debug, archive y mutaciones del sistema de ficheros.

### Tools (categorías)

**Git (16):**

| Tool | Descripción |
|------|-------------|
| `git_status` / `git_diff` / `git_log` | Estado, diff e historial |
| `git_add` / `git_commit` / `git_push` / `git_pull` | Operaciones básicas |
| `git_branch` / `git_stash` / `git_tag` | Gestión de ramas, stash y tags |
| `git_clone` / `git_worktree` | Clonar y gestionar worktrees |
| `git_blame` / `git_rebase` / `git_cherry_pick` / `git_patch` | Historial avanzado |

**Docker / Compose (23):**

| Tool | Descripción |
|------|-------------|
| `docker_ps` / `docker_logs` / `docker_exec` | Operaciones de contenedor |
| `docker_inspect` / `docker_images` / `docker_stop` / `docker_rm` / `docker_cp` | Gestión de contenedores |
| `compose_up` / `compose_down` / `compose_stop` / `compose_restart` | Ciclo de vida |
| `compose_logs` / `compose_build` / `compose_pull` / `compose_exec` / `compose_run` | Operaciones compose |
| `compose_version` / `compose_services` / `compose_status` / `compose_config` / `compose_images` / `compose_top` | Info compose |

**Debug (4):**

| Tool | Descripción |
|------|-------------|
| `strace_run` | Ejecutar con strace |
| `gdb_run` | Depurar con GDB |
| `pdb_run` | Depurar Python con pdb |
| `valgrind_run` | Análisis de memoria con valgrind |

**Build (7):**

| Tool | Descripción |
|------|-------------|
| `make_run` | Ejecutar target de Makefile |
| `run_script` | Ejecutar script (bash/python/node/ruby) |
| `format_code` | Formatear código (ruff/black/gofmt/…) |
| `mypy_check` | Chequeo de tipos Python |
| `python_exec` | Ejecutar fragmento Python |
| `pip_tool` | Gestión de paquetes pip |
| `npm_tool` | Gestión de paquetes npm |

**Archive (3):**

| Tool | Descripción |
|------|-------------|
| `archive_create` | Crear archivo tar.gz/zip |
| `archive_list` | Listar contenido del archivo |
| `archive_extract` | Extraer archivo |

**Filesystem mutations (13):**

| Tool | Descripción |
|------|-------------|
| `chmod_file` / `chmod_dir` | Cambiar permisos |
| `chown_file` / `chown_dir` | Cambiar propietario |
| `mv_file` / `cp_file` | Mover/copiar ficheros |
| `rm_file` / `rm_dir` | Eliminar ficheros/directorios |
| `mkdir_dir` / `touch_file` | Crear directorio/fichero |
| `symlink_create` / `readlink` | Enlace simbólico |
| `file_stat` | Metadatos de fichero |

---

## 3. database-assistant

**Fichero:** `mcp_servers/database_assistant.py`  
**Flag:** `databaseAssistant.enabled` (desactivado por defecto)  
**Descripción:** 20 herramientas de bases de datos. SQLite con stdlib Python (sin deps). PostgreSQL y MySQL opcionales.

### Tools

**SQLite (stdlib, siempre disponible):**

| Tool | Descripción |
|------|-------------|
| `sqlite_query` | Ejecutar SELECT (resultado como tabla ASCII) |
| `sqlite_schema` | Mostrar CREATE TABLE de todas las tablas |
| `sqlite_tables` | Listar tablas con conteo de filas |
| `sqlite_insert` / `sqlite_update` / `sqlite_delete` | Escritura |
| `sqlite_create_table` | Crear tabla con DDL |
| `sqlite_export` | Exportar tabla a CSV o JSON |
| `sqlite_to_csv` | Exportar tabla a fichero CSV |
| `sqlite_vacuum` | VACUUM + ANALYZE |
| `sqlite_indices` | Listar índices |
| `sqlite_explain` | EXPLAIN QUERY PLAN |
| `csv_to_sqlite` | Importar CSV a una tabla SQLite |

**PostgreSQL (requiere `pip install psycopg2`):**

| Tool | Descripción |
|------|-------------|
| `pg_query` | SELECT con salida tabla ASCII |
| `pg_schema` | Lista tablas + columnas |
| `pg_explain` | EXPLAIN ANALYZE |

**MySQL (requiere `pip install pymysql`):**

| Tool | Descripción |
|------|-------------|
| `mysql_query` | SELECT con salida tabla ASCII |
| `mysql_schema` | Lista tablas + columnas |

**Utilidades:**

| Tool | Descripción |
|------|-------------|
| `db_stats` | Estadísticas: tamaño, nº tablas, nº filas |
| `sql_format` | Formatear SQL con indentación |

---

## 4. system-assistant

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

## 5. word-assistant

**Fichero:** `mcp_servers/word_assistant.py`  
**Flag:** `wordAssistant.enabled` (desactivado por defecto)  
**Descripción:** 29 herramientas para documentos Word (.docx) O365 **nativos** + núcleo
ofimático transversal: la tool unificada `doc_create` (genera .docx/.xlsx/.pptx según
extensión), gráficas OOXML, plantillas docxtpl, OCR, PDF, conversión y gestión de proyecto.
Genera solo contenido O365 nativo (sin conversión markdown→documento ni gráficas PNG).

> **Nota (v0.4.4):** `word-assistant`, `excel-assistant` (5b) y `pptx-assistant` (5c)
> nacen de la subdivisión por formato del antiguo `office-assistant`, que a su vez salió de
> dividir `home-office-assistant` junto a `mail-assistant` (5d) y `cmdb-assistant` (5e).
> word lee `~/.oocode/office.json` con fallback al legacy `~/.oocode/home_office.json`.

**Requisito:** `pip install python-docx python-pptx openpyxl pillow docxtpl`

### Tools (categorías)

**Documentos Word + núcleo:**

| Tool | Descripción |
|------|-------------|
| `doc_create` | Crear documento Word con content_blocks (title/heading/paragraph/table/chart/image/toc…) |
| `doc_fill_template` | Rellenar plantilla DOCX con Jinja2/docxtpl |
| `doc_read` | Leer contenido de un documento Word |
| `doc_read_template_fields` | Listar campos de una plantilla |
| `doc_list_templates` | Listar plantillas disponibles |
| `insert_chart` | Insertar gráfica OOXML **nativa** en Word (bar/column/line/area/pie/doughnut/scatter/stacked/radar) — objeto editable de Word |
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

**OCR y procesamiento:**

| Tool | Descripción |
|------|-------------|
| `image_to_text` | OCR: extraer texto de imagen |
| `pdf_extract_text` | Extraer texto de PDF |

**Gestión de proyectos:**

| Tool | Descripción |
|------|-------------|
| `project_context_read` | Leer contexto del proyecto Office |
| `project_init_office` | Inicializar proyecto Office (estructura de carpetas) |

### Prompts (13)

Incluye `executive_summary`, `business_case`, `project_status_report`, `weekly_report`,
`datacenter_migration_report`, `rfc_change_request`, `server_migration_plan`,
`it_incident_report`, `infrastructure_change_plan`, `summarize_document`,
`create_technical_doc`, `generate_report_with_charts`, `create_word_document`.
(Los prompts de Excel/PPT viven en sus respectivos servidores.)

### Resources

`office://templates_available`, `office://rfc_pending`, `office://project_context`,
`office://style_gallery`, `office://style_presets`, `office://theme_colors`,
`office://font_combinations`, `office://chart_types`.

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

## 5b. excel-assistant

**Fichero:** `mcp_servers/excel_assistant.py`  
**Flag:** `excelAssistant.enabled` (desactivado por defecto)  
**Descripción:** 16 herramientas para hojas de cálculo `.xlsx` nativas (openpyxl) y CSV.

**Requisito:** `pip install openpyxl`

### Tools

| Tool | Descripción |
|------|-------------|
| `xlsx_read` | Leer celdas/rango de un .xlsx o CSV |
| `xlsx_write` | Escribir una celda |
| `xlsx_fill_range` | Escribir múltiples celdas a la vez |
| `xlsx_append_row` | Añadir fila al final de una hoja |
| `xlsx_create_report` | Crear informe Excel formateado con estilos |
| `xlsx_create_table` | Crear tabla nativa con estilo O365 |
| `xlsx_insert_chart` | Insertar gráfico (bar/line/pie/area/scatter) |
| `xlsx_apply_conditional_format` | Formato condicional (color scale/data bar/icon set…) |
| `apply_cell_formatting` | Formato avanzado de celdas (font/fill/border) |
| `xlsx_freeze_panes` | Congelar filas/columnas |
| `xlsx_set_column_width` | Ajustar ancho de columnas (auto) |
| `xlsx_merge_cells` | Combinar celdas |
| `xlsx_add_sheet` | Añadir hoja |
| `xlsx_protect_sheet` | Proteger hoja con contraseña |
| `xlsx_add_data_validation` | Validación de datos (lista/fecha/número) |
| `csv_analyze` | Análisis de CSV: cabeceras, filas, estadísticas |

### Prompts (3)

`create_excel_report`, `create_dashboard`, `data_visualization`.

---

## 5c. pptx-assistant

**Fichero:** `mcp_servers/pptx_assistant.py`  
**Flag:** `pptxAssistant.enabled` (desactivado por defecto)  
**Descripción:** 7 herramientas para presentaciones PowerPoint `.pptx` nativas (python-pptx).

**Requisito:** `pip install python-pptx`

### Tools

| Tool | Descripción |
|------|-------------|
| `pptx_create` | Crear presentación PPTX (con slides) |
| `pptx_create_from_template` | Crear desde plantilla .pptx/.potx |
| `pptx_add_slide` | Añadir diapositiva |
| `pptx_insert_chart` | Insertar gráfico en diapositiva |
| `pptx_read` | Leer contenido de la presentación |
| `pptx_add_notes` | Añadir notas del orador |
| `pptx_set_background` | Fondo/tema de diapositiva |

### Prompts (1)

`create_presentation`.

---

## 5d. mail-assistant

**Fichero:** `mcp_servers/mail_assistant.py`  
**Flag:** `mailAssistant.enabled` (desactivado por defecto)  
**Descripción:** 11 herramientas de comunicación y agenda (PIM): email IMAP/SMTP, calendario `.ics` local, notas markdown y contactos vCard.

**Config:** `~/.oocode/mail.json` (fallback legacy `~/.oocode/home_office.json`):

```json
{
  "email": {"imap_host": "imap.gmail.com", "imap_port": 993,
            "smtp_host": "smtp.gmail.com", "smtp_port": 587,
            "user": "tu@email.com", "password": "contraseña-de-aplicación"},
  "notes_dir": "~/Documents/notes",
  "calendar_file": "~/Documents/calendar.ics",
  "contacts_dir": "~/Documents/contacts"
}
```

### Tools

| Tool | Descripción |
|------|-------------|
| `email_list` | Listar emails de la bandeja de entrada (IMAP) |
| `email_read` | Leer un email por UID/índice |
| `email_send` | Enviar email (SMTP) |
| `email_search` | Buscar emails (IMAP SEARCH) |
| `cal_list` | Listar eventos del calendario |
| `cal_add` | Añadir evento VEVENT |
| `cal_search` | Buscar eventos por texto o rango |
| `notes_list` | Listar notas markdown |
| `notes_search` | Buscar texto en notas (ripgrep/grep) |
| `notes_save` | Guardar/actualizar nota con front matter |
| `contact_search` | Buscar en ficheros vCard (.vcf) |

### Prompts (2)

| Nombre | Descripción |
|--------|-------------|
| `draft_email` | Borrador de email profesional con tono configurable |
| `meeting_notes` | Acta de reunión estructurada (genera .docx vía office) |

### Resources

`mail://emails_recent`, `mail://calendar_today`, `mail://notes_recent`, `mail://tasks_today`.

---

## 5e. cmdb-assistant

**Fichero:** `mcp_servers/cmdb_assistant.py`  
**Flag:** `cmdbAssistant.enabled` (desactivado por defecto)  
**Descripción:** 3 herramientas de inventario IT / CMDB sobre CSV/XLSX/JSON. La CMDB se autodetecta en el cwd (`cmdb.csv`, `inventario.csv`, `servers.csv`…) o en `~/Documents/`.

### Tools

| Tool | Descripción |
|------|-------------|
| `cmdb_search` | Buscar en CMDB (CSV/XLSX/JSON); `*` lista todo |
| `cmdb_update` | Actualizar registro CMDB (CSV) por campo clave |
| `asset_register_add` | Añadir activo al registro CSV (lo crea si no existe) |

### Resources

`cmdb://server_inventory` — listado completo de activos de la CMDB del proyecto.

---

## 6. security-assistant

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

## 7. iot-assistant

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
