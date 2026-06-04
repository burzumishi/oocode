# Generado desde el antiguo config.py — bloque 'subagents' de DEFAULT_CONFIG.
DEFAULTS = {
    "maxConcurrent":    4,              # subagentes simultáneos máximos
    "maxTeams":         3,              # equipos de agentes simultáneos máximos
    "maxTeamSize":      5,              # agentes máximos por equipo
    "recentTtl":        1800,           # segundos que permanecen los subagentes finalizados
    "defaultPriority":  0,              # prioridad por defecto de los subagentes
    "autoContMax":      16,             # auto-continues máx. para subagentes (0 = hereda del agente principal)
    "inferenceTimeout": 0,              # timeout de inferencia Ollama para subagentes en segundos (0 = hereda de fallback.timeoutSeconds)
    "defaultTimeout":   0              # timeout por PASO/petición al LLM (inactividad), no por tiempo total: mata el subagente si un paso no progresa en N s (0 = sin límite)
}
