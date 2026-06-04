# Generado desde el antiguo config.py — bloque 'api' de DEFAULT_CONFIG.
DEFAULTS = {
    "type":             "ollama",     # "ollama" | "openai" | "anthropic"
    "key":              "",           # API key (OpenAI / Anthropic; vacío para Ollama)
    "host":             "http://localhost:11434",  # URL del servidor (Ollama host / OpenAI baseUrl)
    "extraHosts":       [],           # hosts adicionales para subagentes (round-robin, solo Ollama)
    "embedHost":        "",           # host dedicado para embeddings (vacío = usar host principal)
    "subagentRouting":  "round-robin", # "round-robin" | "primary-only" (solo Ollama)
    "ollamaRetryCount": 2,            # reintentos automáticos en timeout de Ollama (0 = sin retry)
    "ollamaRetryDelay": 3.0           # segundos de espera base entre reintentos (se duplica con backoff)
}
