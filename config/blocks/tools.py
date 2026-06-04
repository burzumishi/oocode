# Generado desde el antiguo config.py — bloque 'tools' de DEFAULT_CONFIG.
DEFAULTS = {
    "readFileLinesDefault":  150,   # líneas por defecto en read_file
    "readFileLinesWarnLarge": 500,  # a partir de cuántas líneas avisar
    "webFetchMaxChars":      8000,  # chars máximos de web_fetch
    "webFetchTimeout":       15,    # timeout en segundos de web_fetch
    "webSearchMaxResults":   5,     # resultados por defecto de web_search
    "bashMaxOutputChars":    20000, # chars máximos de salida de bash
    "mcpMaxOutputChars":     4000,  # chars máximos por resultado de tool en los MCP bundled
    "codeSearchMaxResults":   50,   # resultados máximos de code_search
    "codeSearchContextLines": 2,    # líneas de contexto en code_search
    "codeSearchMaxFilesize":  "500K", # tamaño máximo de fichero en rg
    "toolCacheEnabled":       True,  # activar caché intra-turno de tools
    "toolCacheMaxSize":       200    # entradas máximas en la caché intra-turno
}
