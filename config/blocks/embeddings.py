# Generado desde el antiguo config.py — bloque 'embeddings' de DEFAULT_CONFIG.
DEFAULTS = {
    "model":               "nomic-embed-text-v2-moe:latest",
    "maxInputChars":       8000,  # chars máximos de texto a embedar
    "similarityThreshold": 0.30,  # score mínimo para devolver un resultado
    "snippetChars":        400,   # chars del snippet por resultado
    "topK":                3,     # resultados máximos por búsqueda
    "memoryEmbedEnabled":  True,  # usar embeddings para búsqueda semántica en memorias
    "diskCacheEnabled":    True,  # persistir caché de embeddings a disco
    "diskCacheDir":        "~/.oocode/cache",  # directorio de caché en disco
    "diskCacheMaxEntries": 2000,  # máx. entradas en caché de disco
    "ramCacheMax":         256,   # vectores máximos en caché LRU en RAM
}
