# 06 — Gestión de contexto y sesiones

## Contexto de conversación

El contexto es el historial de mensajes que se envía al LLM en cada turno. Está limitado por la ventana de contexto del modelo (`context.maxTokens`).

### Estructura de un mensaje

```python
{"role": "user",      "content": "..."}
{"role": "assistant", "content": "..."}
{"role": "tool",      "name": "bash", "content": "...resultado..."}
```

El sistema prompt (rol `system`) se reconstruye en cada turno y contiene:
- Instrucciones del agente
- Contexto del workspace (OOCODE.md, memoria diaria)
- Memorias semánticas relevantes
- Inyecciones de plugins activos
- Instrucciones de razonamiento (`/think`)

### Estimación de tokens

OOCode usa una heurística de 4 chars/token para estimar el uso de contexto sin depender de un tokenizer específico. La estimación es conservadora.

## Compactación automática

Cuando el contexto supera `compactThreshold` × `maxTokens` (defecto: 85%), se activa la compactación automática:

1. Se conservan los últimos `minKeep` mensajes (defecto: 6)
2. Los mensajes eliminados se pasan al LLM para generar un resumen
3. El resumen se guarda en `context.summary` y se inyecta en el system prompt
4. El resumen también se escribe en el log diario del workspace como checkpoint

Los resúmenes son acumulativos: cada compactación añade al resumen existente hasta `maxSummaryChars` caracteres.

### Progreso visual durante la compactación

Durante la compactación, OOCode muestra una barra de progreso por fases directamente en el área de conversación (sin cursor-up ANSI, compatible con la TUI de prompt_toolkit):

```
  ↻  Compactando contexto  243 msgs · ~6,820 tokens · 85%
  ░░░░░░░░░░░░░░░░░░░░░░░░░░    0%  analizando mensajes…
  █████████████░░░░░░░░░░░░░   50%  resumiendo 237 msgs con el modelo…
  ██████████████████████████  100%  ✓  237 eliminados · ~5,140 tok liberados · 9% · resumen ✓
```

Cada fase imprime una nueva línea con la barra avanzando. No se modifica el output anterior.

### Compactación manual

```
/compact       # compacta con resumen LLM
/compact fast  # elimina sin generar resumen (instantáneo)
```

### Ver estado del contexto

```
/context       # tokens usados, resumen, estadísticas
/usage         # tokens por turno
/usage full    # tokens de sesión + contexto %
```

## Sesiones

Cada conversación es una sesión identificada por UUID. Las sesiones se guardan en `~/.oocode/sessions/<agent_id>/`.

Formato: JSONL, una entrada por evento:
- `session_start` — modelo, workspace, timestamp
- `message` — role + content
- `tool_call` — nombre, args, resultado
- `compaction` — número de mensajes eliminados
- `usage` — tokens entrada/salida

### Gestión de sesiones

```
/session           # muestra sesión activa
/session abc123    # restaura sesión por prefijo de ID
/sessions          # lista últimas sesiones
/new               # nueva sesión (guarda la actual)
/reset             # alias de /new
```

Al restaurar una sesión, los mensajes se cargan en el contexto actual.

## Ramas de conversación

Las ramas son snapshots del contexto que se pueden guardar y restaurar:

```
/branch save <nombre>   # captura estado actual
/branch load <nombre>   # restaura snapshot
/branch list            # lista ramas disponibles
/branch rm <nombre>     # elimina rama
```

Almacenadas en `~/.oocode/branches/<agent_id>/<nombre>.json`.

Casos de uso:
- Explorar una solución alternativa sin perder el contexto actual
- Guardar un punto de control antes de una operación arriesgada
- Compartir una conversación en un estado específico

## `/resume`

Resume la sesión completa con el LLM en 3-5 bullets, limpia el historial y usa el resumen como memoria de trabajo para el resto de la sesión. Útil para sesiones largas que han llegado al límite.

## `/btw`

Realiza una pregunta fuera del contexto actual sin interrumpirlo:

```
/btw ¿cuántos parámetros tiene qwen2.5-coder:14b?
```

Proceso:
1. Guarda el contexto actual
2. Crea un contexto temporal (máx 4000 tokens)
3. Envía la pregunta con el mismo system prompt
4. Muestra la respuesta
5. Restaura el contexto original

Ideal para consultas rápidas sin contaminar el historial.

## Workspace y contexto mini/full

El workspace proporciona contexto persistente del proyecto al agente. Modo configurable con `/ctx`:

| Modo | Tokens aprox. | Contenido |
|------|--------------|-----------|
| `mini` | ~150 | OOCODE.md + índice de memoria (12 líneas) + log diario (400 chars) |
| `full` | ~800 | OOCODE.md completo + todas las memorias + log completo |

El modo `mini` es suficiente para la mayoría de los casos y consume muchos menos tokens.

## Configuración

```json
"context": {
  "maxTokens":           8000,
  "minKeep":             6,
  "compactThreshold":    0.85,
  "maxSummaryChars":     2100,
  "maxToolResultTokens": 800
}
```

`maxToolResultTokens`: los resultados de herramientas se truncan a este número de tokens antes de añadirlos al contexto. Evita que una salida de `bash` muy larga sature el historial.
