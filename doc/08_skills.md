# 08 — Skills personalizados

Los skills son herramientas Python simples que añaden capacidades al agente sin el ciclo de vida completo de un plugin. Son el camino más rápido para extender OOCode.

## Diferencia con plugins

| | Skills | Plugins |
|-|--------|---------|
| Complejidad | Mínima | Media-alta |
| Herramientas | ✓ | ✓ |
| Comandos /slash | ✗ | ✓ |
| Hooks (on_start, etc.) | ✗ | ✓ |
| Inyección system prompt | ✗ | ✓ |
| Sobreescribir built-ins | ✗ | ✓ |

## Directorio

```
~/.oocode/skills/
├── enabled.json     # lista de skills activos
└── mi-skill.py      # ficheros de skill
```

## Gestión desde el CLI

```bash
# Ver skills disponibles
/skills list

# Crear plantilla
/skills create mi-skill

# Activar (añade herramientas al registry, guarda en oocode.json)
/skills enable mi-skill

# Desactivar (guarda en oocode.json)
/skills disable mi-skill
```

## Estructura de un skill

```python
"""Skill: Mi Skill

Descripción de lo que hace este skill.
Exporta TOOLS como lista de tuplas (nombre, función, schema_openai).
"""


def mi_funcion(param: str, opcional: int = 5) -> str:
    """Implementa la herramienta aquí."""
    return f"Resultado para {param!r} con {opcional} iteraciones"


TOOLS = [
    (
        "mi_herramienta",
        mi_funcion,
        {
            "name": "mi_herramienta",
            "description": "Hace algo específico y útil para el agente",
            "parameters": {
                "type": "object",
                "properties": {
                    "param": {
                        "type": "string",
                        "description": "El parámetro principal",
                    },
                    "opcional": {
                        "type": "integer",
                        "description": "Parámetro opcional (defecto: 5)",
                    },
                },
                "required": ["param"],
            },
        },
    )
]
```

## Ejemplos de skills útiles

### Skill: ejecutar tests

```python
"""Skill: Run Tests — ejecuta la suite de tests del proyecto actual."""
import subprocess

def run_tests(framework: str = "pytest", args: str = "") -> str:
    cmd = f"{framework} {args}".strip()
    result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=60)
    return result.stdout + result.stderr

TOOLS = [("run_tests", run_tests, {
    "name": "run_tests",
    "description": "Ejecuta los tests del proyecto (pytest, unittest, etc.)",
    "parameters": {
        "type": "object",
        "properties": {
            "framework": {"type": "string", "description": "pytest, unittest, cargo test, npm test..."},
            "args": {"type": "string", "description": "Argumentos adicionales"},
        },
        "required": [],
    },
})]
```

### Skill: calcular

```python
"""Skill: Calculator — evalúa expresiones matemáticas de forma segura."""
import math

def calculate(expression: str) -> str:
    allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    try:
        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(result)
    except Exception as e:
        return f"Error: {e}"

TOOLS = [("calculate", calculate, {
    "name": "calculate",
    "description": "Evalúa expresiones matemáticas. Soporta funciones de math.",
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Expresión matemática, ej: sqrt(2)*pi"}
        },
        "required": ["expression"],
    },
})]
```

## Registro de skills al arranque

```
OOCode.main()
  → SkillManager(enabled_override=config.skills_enabled)
  → load_tools()
      → para cada skill en _enabled:
          → importlib carga el módulo
          → lee TOOLS del módulo
          → (nombre, fn, schema) por cada entrada
  → registry.register(nombre, fn, schema)   ← solo si no existe ya
```

Los skills no sobreescriben herramientas existentes (a diferencia de los plugins).

## Notas de desarrollo

- La función de la herramienta debe devolver siempre un `str`
- Excepciones no capturadas se convierten automáticamente en mensajes de error
- Usa `timeout` en operaciones externas para evitar bloqueos
- El schema sigue el formato OpenAI/Ollama tool use
