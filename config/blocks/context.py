# Generado desde el antiguo config.py — bloque 'context' de DEFAULT_CONFIG.
DEFAULTS = {
    "minKeep":              6,      # mensajes mínimos a conservar tras compactar
    "compactThreshold":     0.80,   # fracción del límite que dispara auto-compactación
    "maxSummaryChars":      2100,   # chars máximos del resumen acumulado (~600 tok)
    "maxToolResultTokens":  800,    # tokens máximos de un resultado de tool en contexto
    "autoContinueMax":      8,      # auto-continuaciones máx. por turno (0 = desactivado)
    "highWater":            0.70,   # fracción para truncar tool results en 2ª pasada
    "toolMaxChars":         3000,   # chars máximos por tool result tras 2ª pasada de compactación
    "ctxMode":              "mini"  # contexto del workspace al arrancar: "mini" | "full" (equivale a /ctx)
}
