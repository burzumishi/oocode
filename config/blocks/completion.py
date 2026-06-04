# Bloque 'completion' de DEFAULT_CONFIG — ajuste INTERNO/AVANZADO, no de usuario.
#
# Es un mecanismo de control del bucle del agente, NO una personalización de las
# respuestas del agente: la frase canónica de "tarea completada" (a) se inyecta en
# el system prompt como instrucción al LLM y (b) se reconoce en la detección de fin
# de turno para parar el auto-continue. NO confundir con las frases preflight
# (_pick_preflight_phrase en loop_helpers.py), que son las respuestas inmediatas al
# usuario antes de llamar al LLM.
#
# Por eso NO se materializa en ~/.oocode/oocode.json (save() no lo escribe) ni se
# muestra en /config. Solo es un "escape hatch" multi-idioma: un agente cuya identidad
# está en otro idioma puede añadir el bloque `completion` a mano en oocode.json para
# que la detección de fin de turno funcione en ese idioma; load() lo respeta.
DEFAULTS = {
    # Frase canónica de "tarea completada" (default ES). Override manual solo si el
    # agente opera en otro idioma distinto de ES/EN (los regex internos cubren ES/EN).
    "phrase":       "He completado todas las tareas.",
    "extraPhrases": []       # frases adicionales reconocidas como señal de completado global
}
