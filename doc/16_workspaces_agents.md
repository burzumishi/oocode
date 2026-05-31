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

Estos ficheros se inyectan automáticamente en el system prompt de cada turno. El volumen de contenido inyectado se controla con:
- `/ctx mini` — ~150 tokens: OOCODE.md + índice de memoria + log diario reciente
- `/ctx full` — ~800 tokens: workspace completo

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
1. Carga la configuración del agente desde `oocode.json`
2. Verifica existencia de ficheros en `workspace/<agent_id>/`
3. Crea automáticamente los ficheros faltantes con valores por defecto
4. Detecta `OOCODE.md` en el directorio del proyecto (CWD)
5. Inyecta el contexto del workspace en el system prompt

## Comandos de gestión

```
/switch <id>     # cambiar de agente y cargar su workspace
/ctx mini        # modo compacto de contexto (~150 tokens)
/ctx full        # modo completo (~800 tokens)
/checkpoint      # guardar checkpoint manual en el log diario
```

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
