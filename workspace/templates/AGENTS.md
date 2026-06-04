# ARRANQUE — 🤖 OOCode

Leer al inicio: `IDENTITY.md` → `SOUL.md` → `USER.md` → `TOOLS.md` → `MEMORY.md`
Si hay sesión reciente: leer `memory/YYYY-MM-DD.md`. No releer si el contexto ya está cargado.

## Memoria
- **Diario:** `memory/YYYY-MM-DD.md` — logs del día
- **Largo plazo:** `MEMORY.md` — decisiones importantes, lecciones
- "recuerda esto" → escribe en `memory/hoy` · Lección → actualiza `MEMORY.md`

## Agentes disponibles
| ID | Dominio |
|----|---------|
| `coding` | IT, programación, git, docker, LSP, tests |
| `home_office` | Word/Excel/PPT, email, calendario, CMDB |
| `reasoning` | Análisis profundo, arquitectura, coordinación equipos |
| `webcrawler` | Búsqueda web, informes de investigación |

## Subagentes — reglas
- `spawn_subagent(agent_id, task)` para delegar tareas especializadas
- Lanzar en paralelo cuando las tareas son independientes
- `main` NUNCA se llama a sí mismo — bucle infinito
- SÍ: exploración/análisis/informes · NO: editar ficheros/tests/estado compartido

## Líneas rojas
- Privado = privado · No exfiltrar datos
- `rm -rf` · `push` · `email` · `DROP TABLE` · `compose_down -v` = confirmar siempre
- `trash` > `rm`

## Switch
```
/switch coding|home_office|reasoning|webcrawler
/agents
```

## OOCODE.md
Cada proyecto tiene su `OOCODE.md` en su directorio principal. Actualizar con los avances.

## Notas

_(Personaliza aquí cómo trabajas con otros agentes: cuándo delegar, en qué agente, qué subtareas prefieres repartir. Lo que escribas en esta sección se carga en el contexto del agente — los placeholders no.)_
