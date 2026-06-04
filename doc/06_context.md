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

OOCode estima los tokens por tipo de mensaje para mayor precisión, sin depender de un tokenizer externo:

| Tipo de mensaje | Chars/token | Motivo |
|----------------|-------------|--------|
| Tool results (`tool`) | 2.5 | JSON/código denso |
| Tool calls del asistente | 2.5 | JSON de llamadas |
| Thinking blocks | 4.0 | Lenguaje natural prolijo |
| Texto usuario/asistente | 3.5 | Lenguaje natural |
| System prompt | 3.0 | Mezcla |

## Compactación automática

Cuando el contexto supera `compactThreshold` × `maxTokens` (defecto: **80%**), se activa la compactación automática:

1. Se conservan los últimos `minKeep` mensajes (defecto: 6)
2. **min_keep adaptativo (A):** si hay un plan activo, `minKeep` se eleva automáticamente para incluir todos los mensajes desde que se activó la tarea actual (+2 de margen), garantizando que el LLM nunca pierde visibilidad del trabajo en curso
3. El punto de corte se alinea hacia atrás en hasta **12 mensajes** para coincidir con una frontera `user` (evita partir pares tool-call/result)
4. **Segunda pasada con ventana de recencia (B):** si el contexto sigue por encima del 70% (`highWater`) tras el corte, trunca los tool results largos conservando los 4 más recientes intactos
5. El primer mensaje del usuario de los eliminados se ancla en el resumen como `**Tarea original:** …`
6. **Serialización por turnos (F):** los mensajes eliminados se serializan en bloques `[Turno N] Usuario: … Asistente: … → [tools] ↳ tool: preview` antes de pasarse al LLM — mejor estructura causa-efecto para el resumen
7. El resumen se guarda en `context.summary` y se inyecta como **mensaje `system` separado (D)** — mejor salience en Qwen/DeepSeek que concatenado en las SYSTEM_RULES
8. **Meta-header (G):** el summary empieza con `[Compactación #N — conservados X/Y msgs — YYYY-MM-DD HH:MM]`
9. Si el resumen acumulado supera `maxSummaryChars`, se llama al LLM para condensarlo (re-condensación) antes de truncar

Los resúmenes son acumulativos: cada compactación añade al resumen existente hasta `maxSummaryChars` caracteres.

### Calibración dinámica CPT (E)

OOCode calibra automáticamente los ratios chars/token usando `prompt_eval_count` de Ollama (tokens reales). Al final de cada turno LLM ajusta el factor multiplicativo con smoothing α=0.15:

```
factor_nuevo = 0.85 × factor_anterior + 0.15 × (tokens_reales / tokens_estimados)
```

Outliers fuera del rango (0.4, 2.5) se ignoran. Esto permite que OOCode se adapte al vocabulario del modelo y proyecto.

### Pre-compactación en idle (I)

Cuando el contexto está entre `highWater` (70%) y `compact_threshold` (80%), al finalizar cada turno OOCode lanza la compactación en un hilo background daemon. El siguiente turno espera si la compactación no ha terminado. Esto elimina la pausa visible al alcanzar el 80%.

### Progreso visual durante la compactación

Durante la compactación, OOCode muestra una barra de progreso por fases directamente en el área de conversación (sin cursor-up ANSI, compatible con la TUI de prompt_toolkit):

```
  ↻  Compactando contexto  243 msgs · ~6,820 tokens · 85%
  ░░░░░░░░░░░░░░░░░░░░░░░░░░    0%  analizando mensajes…
  █████████████░░░░░░░░░░░░░   50%  resumiendo 237 msgs con el modelo…
  ██████████████████████████  100%  ✓  237 eliminados · ~5,140 tok liberados · 9% · resumen ✓
```

Cada fase imprime una nueva línea con la barra avanzando. No se modifica el output anterior.

### Recuperación del último mensaje tras compactar (v0.4.3, solo TUI)

La compactación limpia el área visible del TUI y muestra un banner + la lista de ficheros leídos/editados. Si la compactación salta **justo después de que el agente termina** (p.ej. al finalizar un turno con un resumen que pregunta «¿continúo con el siguiente paso?»), ese último mensaje se re-muestra tras el banner:

```
  ✻ Conversación compactada  (ctrl+o para ver historial)
  ↻ resumen LLM preservado en contexto
  ⎿ Updated robot/learning.py
  ● último mensaje del agente (antes de compactar):
    Resumen del sprint completado. ¿Continúo con el siguiente sprint?
```

Así el usuario nunca responde a ciegas: el texto sigue vivo en el contexto del LLM (la compactación no lo borra) y OOCode lo vuelve a renderizar como referencia. El WebUI no lo necesita porque conserva la conversación completa en el navegador.

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

El workspace proporciona contexto persistente del agente. Modo configurable con `/ctx` (por defecto `mini`):

| Modo | Tokens aprox. | Contenido del workspace inyectado |
|------|--------------|-----------|
| `mini` | ~150 | Resumen: `IDENTITY.md` (Rol/Vibe) + `SOUL.md` (principios) + `USER.md` (nombre/idioma) + índice de `MEMORY.md` (12 líneas) + log diario (400 chars) + sección `## Notas` de `TOOLS.md`/`AGENTS.md` si la personalizas |
| `full` | ~800 | Todos los ficheros del workspace completos + memoria diaria reciente |

El modo `mini` es suficiente para la mayoría de los casos y consume muchos menos tokens. En `mini` NO se cargan `AGENTS.md`/`HEARTBEAT.md`/`TOOLS.md` completos (solo su sección `## Notas`); son ficheros de referencia que el agente consulta bajo demanda o en `full`.

`OOCODE.md` (instrucciones del proyecto) se carga **aparte y siempre**, sea cual sea el modo. Ver doc 16 para el detalle de los ficheros del workspace y la capa de personalización `## Notas`.

## Configuración

```json
"context": {
  "minKeep":             6,
  "compactThreshold":    0.80,
  "maxSummaryChars":     2100,
  "maxToolResultTokens": 800,
  "autoContinueMax":     8
}
```

`maxToolResultTokens`: los resultados de herramientas se truncan a este número de tokens antes de añadirlos al contexto. Evita que una salida de `bash` muy larga sature el historial.

`compactThreshold`: fracción del límite de tokens que dispara la compactación automática. Con 0.80 hay más margen antes de llegar al límite que con el valor anterior de 0.85.
