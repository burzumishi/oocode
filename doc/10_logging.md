# 10 — Sistema de logs

OOCode registra su actividad en un fichero de log rotativo. Esto permite auditar qué herramientas se ejecutaron, qué errores ocurrieron y cuánto tiempo tardó cada sesión.

## Ubicación por defecto

```
~/.oocode/logs/oocode.log
~/.oocode/logs/oocode.log.1   ← rotado
~/.oocode/logs/oocode.log.2   ← rotado
```

## Configuración

```json
"logging": {
  "enabled":   true,
  "file":      "",
  "level":     "info",
  "maxSizeMb": 5,
  "maxFiles":  3
}
```

| Campo | Descripción |
|-------|-------------|
| `enabled` | `false` desactiva completamente la escritura en fichero |
| `file` | Ruta personalizada. Vacío = `~/.oocode/logs/oocode.log` |
| `level` | `debug` \| `info` \| `warn` \| `error` |
| `maxSizeMb` | El fichero rota cuando supera este tamaño |
| `maxFiles` | Número de ficheros rotados a conservar |

### Niveles de log

| Nivel | Se registra |
|-------|-------------|
| `error` | Solo errores críticos |
| `warn` | Errores + advertencias |
| `info` | + inicio de sesión, carga de plugins, herramientas |
| `debug` | + cada mensaje, cada tool call con args |

Para producción se recomienda `info`. Para depuración, `debug`.

## Editar configuración

```
/config edit  →  sección Logging
```

## Ver logs desde el REPL

```
/logs         # últimas 40 líneas
/logs 100     # últimas 100 líneas
/logs 500     # hasta 500 líneas
```

Las líneas se colorean automáticamente:
- **Rojo** — errores (`[ERROR]`)
- **Amarillo** — advertencias (`[WARN]`)
- **Gris** — debug (`[DEBUG]`)
- **Blanco apagado** — info (`[INFO]`)

## Formato del log

```
2026-05-14 23:15:42 [INFO ] session_start  agent='main'  model='qwen2.5-coder:14b'
2026-05-14 23:15:42 [INFO ] plugins_loaded  count=1  errors=0
2026-05-14 23:15:42 [INFO ] skills_loaded  count=0
2026-05-14 23:16:01 [DEBUG] user_message  chars=45
2026-05-14 23:16:08 [DEBUG] tool_call  tool='bash'  allowed=True  args='{"command": "ls -la"}'
2026-05-14 23:16:08 [DEBUG] assistant_reply  chars=312
2026-05-14 23:20:15 [ERROR] llm_error  model='qwen2.5-coder:14b'  error='Connection refused'
2026-05-14 23:25:00 [INFO ] plugin_enabled  name='searxng'
2026-05-14 23:30:00 [INFO ] session_end  agent='main'
```

## Eventos registrados

| Evento | Nivel | Cuándo |
|--------|-------|--------|
| `session_start` | info | Al arrancar OOCode |
| `session_end` | info | Al salir con `/exit` |
| `plugins_loaded` | info | Tras cargar plugins |
| `skills_loaded` | info | Tras cargar skills |
| `plugin_enabled` | info | `/plugins enable` |
| `plugin_disabled` | info | `/plugins disable` |
| `skill_enabled` | info | `/skills enable` |
| `skill_disabled` | info | `/skills disable` |
| `plugin_load_error` | error | Error al cargar un plugin |
| `user_message` | debug | Cada mensaje del usuario |
| `tool_call` | debug | Cada llamada a herramienta |
| `assistant_reply` | debug | Cada respuesta del asistente |
| `llm_error` | error | Error de conexión con Ollama |

## Análisis del log

```bash
# Ver todos los errores
grep ERROR ~/.oocode/logs/oocode.log

# Ver todas las herramientas ejecutadas
grep tool_call ~/.oocode/logs/oocode.log

# Estadísticas de sesiones de hoy
grep "2026-05-14.*session_start" ~/.oocode/logs/oocode.log | wc -l

# Herramientas más usadas
grep tool_call ~/.oocode/logs/oocode.log | grep -oP "tool='[^']+'" | sort | uniq -c | sort -rn
```

## Desactivar logs

```json
"logging": {
  "enabled": false
}
```

O desde el REPL: `/config edit` → sección Logging → `activado: false`.

## Módulo `agent/logger.py`

Para usar el logger desde un plugin o skill:

```python
import agent.logger as log

log.info("mi_evento", campo1="valor1", campo2=42)
log.debug("detalle", data="...")
log.warn("advertencia")
log.error("error_critico", error="mensaje de error")
```

Las funciones son no-operativas si el logging está desactivado.
