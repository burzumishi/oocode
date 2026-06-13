# Generado desde el antiguo config.py — bloque 'mcp' de DEFAULT_CONFIG.
DEFAULTS = {
    "servers":        [],    # lista de {name, cmd, env?, cwd?} — servidores MCP a arrancar al inicio
    "requestTimeout": 15.0,  # segundos máximos esperando respuesta MCP
    "oocodeAssistant": {
        "enabled": True      # arrancar el MCP server bundled oocode_assistant.py
    },
    "systemAssistant": {
        "enabled": True      # arrancar el MCP server bundled system_assistant.py
    },
    "devopsAssistant": {
        "enabled": True      # arrancar el MCP server bundled devops_assistant.py
    },
    "databaseAssistant": {
        "enabled": False     # arrancar el MCP server bundled database_assistant.py
    },
    "wordAssistant": {
        "enabled": False     # arrancar el MCP server bundled word_assistant.py (Word/PDF + núcleo O365)
    },
    "excelAssistant": {
        "enabled": False     # arrancar el MCP server bundled excel_assistant.py (hojas .xlsx/CSV)
    },
    "pptxAssistant": {
        "enabled": False     # arrancar el MCP server bundled pptx_assistant.py (presentaciones .pptx)
    },
    "mailAssistant": {
        "enabled": False     # arrancar el MCP server bundled mail_assistant.py (email/cal/notas)
    },
    "cmdbAssistant": {
        "enabled": False     # arrancar el MCP server bundled cmdb_assistant.py (inventario IT)
    },
    "securityAssistant": {
        "enabled": False     # arrancar el MCP server bundled security_assistant.py
    },
    "iotAssistant": {
        "enabled": False     # arrancar el MCP server bundled iot_assistant.py
    },
    "httpClientAssistant": {
        "enabled": False     # arrancar el MCP server bundled http_client_assistant.py
    },
}
