# 16 — Gestión de Workspaces de Agentes

## Estructura del workspace

Cada agente tiene su propio workspace en `~/.oocode/workspace/<agent_id>/` con los siguientes ficheros:

```
~/.oocode/workspace/<agent_id>/
├── IDENTITY.md        # quién eres: nombre, emoji, rol, especialización, principios
├── SOUL.md            # cómo actúas: personalidad, valores, estilo de comunicación
├── USER.md            # a quién ayudas: usuario, idioma, proyectos, preferencias
├── AGENTS.md          # guía del workspace, instrucciones de arranque y memoria
├── HEARTBEAT.md       # tareas periódicas de mantenimiento del agente
├── TOOLS.md           # entorno local: servidor Ollama, herramientas, permisos
├── MEMORY.md          # memoria a largo plazo editable manualmente
└── memory/            # logs diarios del agente (YYYY-MM-DD.md)
```

El volumen de contenido inyectado en el system prompt se controla con el modo de contexto (`ctx_mode`, por defecto `mini`):

| Modo | Tokens aprox. | Qué carga |
|------|---------------|-----------|
| `mini` (default) | ~150 | **Resumen**: `IDENTITY.md` (Rol/Vibe), `SOUL.md` (principios → "## Comportamiento"), `USER.md` (nombre/idioma), `MEMORY.md` + `memory/` diario, y la sección `## Notas` de `TOOLS.md`/`AGENTS.md` si la personalizas. **No** carga `AGENTS.md`/`HEARTBEAT.md`/`TOOLS.md` completos. |
| `full` (`/ctx full`) | ~800 | **Todos** los ficheros del workspace completos + memoria diaria reciente. |

> `AGENTS.md`, `HEARTBEAT.md` y `TOOLS.md` son ficheros de referencia: el agente los consulta bajo demanda o en modo `full`. En `mini` solo entra su sección personalizable `## Notas` (ver abajo).

`OOCODE.md` (instrucciones del proyecto) se carga aparte y **siempre**, independiente del modo de contexto.

## Contenido de cada fichero

### IDENTITY.md

Identidad del agente: nombre, emoji, rol, área de especialización, herramientas principales y principios de trabajo.

Ejemplo:
```markdown
# Identidad: OOCode Coder (💻)

## Rol
Asistente de programación especializado en desarrollo Python, refactorización y arquitectura de software.

## Especialización
- Análisis y refactorización de código Python
- Diseño de APIs y arquitecturas
- Testing con pytest
- Herramientas LSP: diagnósticos, go-to-definition, rename

## Principios
- Código limpio y bien documentado
- Tests antes que implementación
- Cambios incrementales con verificación
```

### SOUL.md

Personalidad, valores, estilo de comunicación, reglas de oro y flujo de trabajo del agente.

Ejemplo:
```markdown
# Alma: OOCode Coder

## Core
- Directo y técnico: código antes que explicaciones largas
- Verifico antes de modificar: leo el fichero completo primero
- Propongo antes de actuar: anuncio qué voy a hacer

## Flujo de trabajo
1. Leer y entender el código existente
2. Proponer cambios con justificación
3. Implementar con verificación posterior
4. Comprobar tests tras cada cambio
```

### USER.md

Información sobre el usuario que asiste el agente: nombre, idioma, proyectos activos, preferencias de código y contexto de trabajo.

### AGENTS.md

Guía del workspace del agente: estructura de directorios, instrucciones de arranque, cómo usar la memoria, interacción con otros agentes.

### HEARTBEAT.md

Tareas de mantenimiento periódico: limpieza de ficheros, actualización de índices, verificaciones programadas.

### TOOLS.md

Entorno específico del agente: host Ollama, herramientas disponibles, permisos configurados, skills activos, configuración específica del agente.

### Capa de personalización — sección `## Notas` (sin tocar código)

`TOOLS.md` y `AGENTS.md` incluyen una sección **`## Notas`** pensada para que personalices el agente **sin editar código ni `SYSTEM_RULES`**:

- En **`TOOLS.md → ## Notas`**: preferencias de uso de herramientas (qué tool prefieres para cada tarea, alias, nombres de dispositivos, convenciones).
- En **`AGENTS.md → ## Notas`**: preferencias de delegación (cuándo delegar, en qué agente, qué subtareas repartir).

Lo que escribas en esas secciones **se carga en el contexto del agente** (también en modo `mini`). Los placeholders de la plantilla se filtran automáticamente, así que **no cuestan tokens hasta que escribes contenido real** (acotado a 1500 chars por sección). Es un modelo en capas: el código mantiene la disciplina/seguridad invariable; tus notas se añaden encima.

```markdown
## Notas
- Para tests usa run_tests, nunca bash pytest.
- Delega la búsqueda web en el agente webcrawler.
```

### MEMORY.md

Memoria a largo plazo editable. Se inyecta en el system prompt (hasta `workspace.maxMemoryLines` líneas). El agente puede actualizar este fichero directamente para persistir información entre sesiones.

Formato recomendado:
```markdown
# Memoria — OOCode Coder

## Decisiones técnicas
- 2026-05-27: Se usa pytest-asyncio para tests asíncronos

## Preferencias del usuario
- Prefiere docstrings en español
- Usa type hints en todas las funciones

## Contexto del proyecto
- Proyecto: OOCode
- Stack: Python 3.10+, Ollama, Rich, prompt_toolkit
```

## OOCODE.md — instrucciones por proyecto

El fichero `OOCODE.md` es distinto de los ficheros de workspace: vive en el **directorio del proyecto** (no en el workspace del agente) y define el comportamiento del agente específicamente para ese proyecto.

```
directorio-del-proyecto/
└── OOCODE.md          # instrucciones específicas del proyecto
```

OOCode lo detecta automáticamente:
```bash
cd /mi/proyecto && oocode          # detecta OOCODE.md en CWD
oocode /mi/proyecto                # equivalente explícito
```

Genera una plantilla con `/init`. Puedes definir hooks personalizados en él:
```markdown
## Hooks
post write_file: ruff check {path} --fix
post edit_file:  mypy {path}
post bash:       echo "Comando ejecutado: {command}"
```

## Gestión automática al arrancar

Al arrancar OOCode:
1. **Selecciona el agente**: sin `--agent` se usa `main`; `--agent <id>` carga otro.
2. Carga la configuración del agente desde `oocode.json`.
3. Inicializa los workspaces de todos los agentes (crea los ficheros faltantes desde las plantillas).
4. Fija el **directorio del proyecto** = PWD (o el argumento `[dir]`), separado del workspace de identidad: `bash`/`python_exec`/`workspace_remember` se ejecutan ahí — también para los subagentes.
5. **Trust-check de `OOCODE.md`**: si no existe en el directorio del proyecto, pregunta si crearlo (`/init` analiza el proyecto y genera la plantilla).
6. Inyecta el contexto del workspace en el system prompt (modo `mini` por defecto).

### Dos sistemas de memoria (no confundir)

Ambos usan los nombres `memory/` y `MEMORY.md` pero son distintos:

| Sistema | Ubicación | Escritura | Uso |
|---------|-----------|-----------|-----|
| **Memoria del workspace** | `~/.oocode/workspace/<id>/memory/YYYY-MM-DD.md` + `MEMORY.md` | `workspace_remember`, automática | Continuidad del agente; se inyecta en `mini` |
| **Memoria semántica** | `~/.oocode/memory/<id>/*.md` + `MEMORY.md` + `.emb.json` | tool `mem_save` | Recuperación por embeddings (top-K por turno) |

## Comandos de gestión

```
/agent new <id> [nombre] [descripción]   # crear agente nuevo con workspace propio
/switch <id>     # cambiar de agente y cargar su workspace
/ctx mini        # modo compacto de contexto (~150 tokens)
/ctx full        # modo completo (~800 tokens)
/checkpoint      # guardar checkpoint manual en el log diario
```

## Crear un agente personalizado por dominio

Una instalación nueva arranca solo con el agente `main` (asistente de código). Puedes crear agentes de **cualquier dominio** con `/agent new`; OOCode adapta la persona del agente a su función — no asume que sea de programación.

```
/agent new oficina "Asistente de oficina" "informes Word/Excel y correo corporativo"
/agent new recon   "Recon"                "reconocimiento y análisis de seguridad autorizado"
/agent new noticias "Crawler"             "investigación web y resumen de noticias"
```

Al crear el agente, OOCode:

1. **Clasifica el dominio** a partir de la descripción/nombre (oficina, seguridad, web/investigación, datos, IoT, DevOps, código o general) y elige un emoji acorde.
2. **Personaliza el workspace con el LLM** (si hay uno disponible y diste descripción): el prompt es consciente del dominio, así que el `## Flujo de Trabajo` y las `## Reglas` de `SOUL.md` encajan con la función — sin reglas de tests/código/git si el agente no es de programación.
3. **Fallback sin LLM:** si no hay LLM disponible y el agente no es de código, escribe un `SOUL.md` adaptado al dominio en lugar de la plantilla de programación por defecto.

> El dominio solo afina la *persona* (los ficheros `.md`). Todos los agentes comparten el mismo repertorio de herramientas nativas; los servidores MCP activos sí varían por agente.

```bash
# Copiar workspace de un agente a otro
cp -r ~/.oocode/workspace/main/* ~/.oocode/workspace/mi_agente/

# Verificar ficheros de workspace
ls -la ~/.oocode/workspace/coding/
```

## Los 5 agentes y sus workspaces

| Agente | Workspace | Especialidad |
|--------|-----------|-------------|
| `main` (🤖) | `~/.oocode/workspace/main` | Asistente general, coordina otros agentes |
| `coding` (💻) | `~/.oocode/workspace/coding` | Programación, refactorización, LSP |
| `home_office` (📋) | `~/.oocode/workspace/home_office` | Documentación O365, email, calendario |
| `reasoning` (🧠) | `~/.oocode/workspace/reasoning` | Razonamiento, coordinación de equipos |
| `webcrawler` (🕷️) | `~/.oocode/workspace/webcrawler` | Búsqueda web con SearXNG, informes |

## Memoria diaria

El agente escribe automáticamente en `workspace/<agent_id>/memory/YYYY-MM-DD.md` las notas significativas de cada sesión. Los últimos `workspace.maxDailyChars` caracteres se inyectan en el system prompt.

```bash
# Ver log del día
cat ~/.oocode/workspace/main/memory/2026-05-27.md
```
