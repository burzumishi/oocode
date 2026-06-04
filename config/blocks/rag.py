# Generado desde el antiguo config.py — bloque 'rag' de DEFAULT_CONFIG.
DEFAULTS = {
    "enabled":             True,   # inyectar código relevante del workspace en el system prompt
    "topK":                5,      # top_k base (queries cortas/simples)
    "similarityThreshold": 0.40,   # threshold base
    "maxSnippetChars":     4000,   # chars totales máximos del bloque inyectado
    "indexInterval":       300,    # segundos entre re-indexaciones en background
    "topKComplex":         10,     # top_k para queries largas/autoedición (>complexMinChars)
    "thresholdComplex":    0.35,   # threshold más permisivo para queries complejas
    "complexMinChars":     150,    # longitud mínima del mensaje para activar boost
    "maxFileChars":        6000,   # chars por fichero antes de chunking
    "chunkChars":          512,    # chars por chunk de indexación
    "chunkOverlap":        64,     # solapamiento entre chunks consecutivos
    "maxFiles":            2000,   # ficheros máximos a indexar en el workspace
    "minSlotChars":        200     # mínimo de chars por fragmento en la respuesta RAG
}
