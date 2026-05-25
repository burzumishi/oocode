"""Gestión de skills personalizados: herramientas Python que OOCode carga dinámicamente."""
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from config import CONFIG_DIR

SKILLS_DIR         = CONFIG_DIR / "skills"          # ~/.oocode/skills/  (usuario)
INSTALL_SKILLS_DIR = Path(__file__).parent           # oocode/skills/     (repo)
ENABLED_FILE       = SKILLS_DIR / "enabled.json"

SKILL_TEMPLATE = '''\
"""Skill: {name}

{description}
Exporta TOOLS como lista de tuplas (nombre, función, schema_openai).
"""


def {slug}_fn(param: str) -> str:
    """Implementa tu herramienta aquí."""
    return f"Resultado: {{param}}"


TOOLS = [
    (
        "{slug}",
        {slug}_fn,
        {{
            "name": "{slug}",
            "description": "{description}",
            "parameters": {{
                "type": "object",
                "properties": {{
                    "param": {{"type": "string", "description": "Parámetro de entrada"}},
                }},
                "required": ["param"],
            }},
        }},
    )
]
'''


class SkillManager:
    def __init__(self, enabled_override: list[str] | None = None):
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        if enabled_override is not None:
            self._enabled: set[str] = set(enabled_override)
            _save_set(ENABLED_FILE, self._enabled)
        else:
            self._enabled = _load_set(ENABLED_FILE)

    def _find_skill_path(self, name: str) -> Path | None:
        """Busca una skill primero en ~/.oocode/skills/, luego en la instalación."""
        for d in (SKILLS_DIR, INSTALL_SKILLS_DIR):
            p = d / f"{name}.py"
            if p.exists():
                return p
        return None

    def all_skills(self) -> list[dict]:
        seen: set[str] = set()
        result = []
        for d in (SKILLS_DIR, INSTALL_SKILLS_DIR):
            for path in sorted(d.glob("*.py")):
                if path.name.startswith("_") or path.stem == "manager":
                    continue
                name = path.stem
                if name in seen:
                    continue
                seen.add(name)
                result.append({
                    "name":        name,
                    "path":        str(path),
                    "enabled":     name in self._enabled,
                    "description": _first_line(path),
                    "tool_count":  _count_tools(path),
                })
        return result

    def create(self, name: str, description: str = "") -> str:
        slug = _slugify(name)
        path = SKILLS_DIR / f"{slug}.py"
        if path.exists():
            return f"ya_existe:{path}"
        desc = description or f"Herramienta personalizada {name}"
        path.write_text(SKILL_TEMPLATE.format(name=name, slug=slug, description=desc))
        return str(path)

    def enable(self, name: str) -> bool:
        slug = _slugify(name)
        if self._find_skill_path(slug) is None:
            return False
        self._enabled.add(slug)
        _save_set(ENABLED_FILE, self._enabled)
        return True

    def disable(self, name: str) -> bool:
        slug = _slugify(name)
        if slug not in self._enabled:
            return False
        self._enabled.discard(slug)
        _save_set(ENABLED_FILE, self._enabled)
        return True

    def load_tools(self) -> list[tuple]:
        tools = []
        for name in sorted(self._enabled):
            path = self._find_skill_path(name)
            if path is None:
                continue
            try:
                mod = _import_file(path)
                for t in getattr(mod, "TOOLS", []):
                    if isinstance(t, (list, tuple)) and len(t) == 3:
                        tools.append(tuple(t))
            except Exception:
                pass
        return tools

    def create_workflow(self, name: str, tools: list[str], description: str = "") -> str:
        """Crea un workflow que agrupa múltiples herramientas.

        Los workflows son skills especiales que orquestan varias herramientas
        en una secuencia predefinida para tareas comunes.
        """
        slug = _slugify(name)
        path = SKILLS_DIR / f"{slug}.py"
        
        if path.exists():
            return f"ya_existe:{path}"
        
        # Generar código del workflow
        tool_defs = "\n".join(f'    "{t}"' for t in tools)
        
        workflow_code = f'''"""Skill: {name}

Workflow: {description}
Herramientas: {tool_defs}
"""


def {slug}_fn(param: str) -> str:
    """Ejecuta el workflow con el parámetro dado."""
    # Implementación del workflow
    return "Ejecutando workflow"


def _execute_workflow_workflow_fn(param: str) -> str:
    """Función interna para ejecutar workflows."""
    return "Ejecutando workflow"


TOOLS = [
    (
        "{slug}",
        {slug}_fn,
        {{
            "name": "{slug}",
            "description": "{description}",
            "parameters": {{
                "type": "object",
                "properties": {{
                    "param": {{"type": "string", "description": "Parámetro de entrada"}},
                }},
                "required": ["param"],
            }},
        }},
    )
]
'''
        path.write_text(workflow_code)
        return str(path)

    def list_workflows(self) -> list[dict]:
        """Lista todos los workflows definidos."""
        result = []
        for path in sorted(SKILLS_DIR.glob("*.py")):
            if path.name.startswith("_") or path.stem == "manager":
                continue
            try:
                content = path.read_text()
                # Detectar workflows por patrón
                if "Workflow:" in content:
                    name = path.stem
                    desc = ""
                    for line in content.splitlines()[:5]:
                        if "Workflow:" in line:
                            desc = line.split(":")[1].strip()
                            break
                    result.append({
                        "name": name,
                        "path": str(path),
                        "description": desc,
                    })
            except Exception:
                pass
        return result


class AgentSDK:
    """SDK para desarrollo de agentes personalizados con control total de orquestación.
    
    Permite crear agentes personalizados con:
    - Control total de la configuración
    - Definición de herramientas personalizadas
    - Plantillas para agentes comunes
    - Exportación de agentes empaquetados
    """
    
    def __init__(self, agent_config: dict | None = None):
        self.agent_config = agent_config or {}
        self.name = self.agent_config.get("name", "custom_agent")
        self.model = self.agent_config.get("model", "")
        self.workspace = self.agent_config.get("workspace", "")
        self.tools: list[dict[str, Any]] = []
        self.prompts: list[dict[str, str]] = []
        self.resources: list[dict[str, str]] = []
    
    def add_tool(self, name: str, description: str, parameters: dict[str, Any]) -> None:
        """Añade una herramienta personalizada al agente."""
        self.tools.append({
            "name": name,
            "description": description,
            "parameters": parameters,
        })
    
    def add_prompt(self, name: str, content: str) -> None:
        """Añade un prompt personalizado al agente."""
        self.prompts.append({
            "name": name,
            "content": content,
        })
    
    def add_resource(self, name: str, uri: str) -> None:
        """Añade un resource personalizado al agente."""
        self.resources.append({
            "name": name,
            "uri": uri,
        })
    
    def build_agent_spec(self) -> dict:
        """Genera la especificación del agente personalizado."""
        return {
            "name": self.name,
            "model": self.model,
            "workspace": self.workspace,
            "tools": self.tools,
            "prompts": self.prompts,
            "resources": self.resources,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    
    def export_to_file(self, path: Path) -> str:
        """Exporta la especificación del agente a un archivo JSON."""
        import json
        spec = self.build_agent_spec()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(spec, indent=2, ensure_ascii=False))
        return str(path)
    
    def create_from_template(self, template_name: str) -> "AgentSDK":
        """Crea un agente desde una plantilla."""
        templates = {
            "explorer": {
                "name": "explorer",
                "description": "Agente especializado en exploración de código read-only",
                "model": "batiai/qwen3.5-9b:latest",
                "tools": [
                    {"name": "tree", "description": "Muestra estructura de directorio", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Ruta del directorio"}}}},
                    {"name": "grep_code", "description": "Busca patrones en código", "parameters": {"type": "object", "properties": {"pattern": {"type": "string", "description": "Patrón regex"}, "directory": {"type": "string", "description": "Directorio a buscar"}, "extensions": {"type": "string", "description": "Extensiones"}, "max_matches": {"type": "integer", "description": "Máximo de resultados"}}}},
                    {"name": "find_files", "description": "Busca ficheros por patrón", "parameters": {"type": "object", "properties": {"directory": {"type": "string", "description": "Directorio raíz"}, "name": {"type": "string", "description": "Patrón glob"}, "max_results": {"type": "integer", "description": "Máximo de resultados"}}}},
                    {"name": "read_file", "description": "Lee un fichero", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Ruta al fichero"}, "offset": {"type": "integer", "description": "Primera línea (0-indexada)"}, "limit": {"type": "integer", "description": "Líneas a leer"}}}},
                    {"name": "find_symbol", "description": "Busca dónde está definida una función/clase/variable", "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "Nombre del símbolo"}, "kind": {"type": "string", "description": "Tipo: función, clase, método, variable"}, "path": {"type": "string", "description": "Directorio donde buscar"}}}},
                    {"name": "list_symbols", "description": "Lista símbolos en un fichero", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Ruta al fichero"}, "kinds": {"type": "string", "description": "Tipos a listar"}}}},
                ],
            },
            "refactor": {
                "name": "refactor",
                "description": "Agente especializado en refactorización de código",
                "model": "batiai/qwen3.5-9b:latest",
                "tools": [
                    {"name": "read_file", "description": "Lee un fichero", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Ruta al fichero"}, "offset": {"type": "integer", "description": "Primera línea (0-indexada)"}, "limit": {"type": "integer", "description": "Líneas a leer"}}}},
                    {"name": "write_file", "description": "Escribe o sobreescribe un fichero", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Ruta del fichero a escribir"}, "content": {"type": "string", "description": "Contenido completo del fichero"}}}},
                    {"name": "edit_file", "description": "Reemplaza una cadena exacta en un fichero", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Ruta del fichero a editar"}, "old_string": {"type": "string", "description": "Cadena exacta a reemplazar"}, "new_string": {"type": "string", "description": "Cadena sustituta"}}}},
                    {"name": "edit_files", "description": "Edición atómica de múltiples ficheros", "parameters": {"type": "object", "properties": {"edits": {"type": "array", "items": {"type": "object"}, "description": "Lista de ediciones"}}}},
                    {"name": "grep_code", "description": "Busca patrones en código", "parameters": {"type": "object", "properties": {"pattern": {"type": "string", "description": "Patrón regex"}, "directory": {"type": "string", "description": "Directorio a buscar"}, "extensions": {"type": "string", "description": "Extensiones"}, "max_matches": {"type": "integer", "description": "Máximo de resultados"}}}},
                    {"name": "multi_grep", "description": "Busca múltiples patrones a la vez", "parameters": {"type": "object", "properties": {"patterns": {"type": "array", "items": {"type": "string"}, "description": "Lista de patrones regex"}, "directory": {"type": "string", "description": "Directorio raíz"}, "extensions": {"type": "string", "description": "Extensiones"}, "max_per_pattern": {"type": "integer", "description": "Máximo de resultados por patrón"}}}},
                    {"name": "diff_files", "description": "Muestra el diff entre dos ficheros", "parameters": {"type": "object", "properties": {"file_a": {"type": "string", "description": "Ruta del primer fichero"}, "file_b": {"type": "string", "description": "Ruta del segundo fichero"}, "text_a": {"type": "string", "description": "Primer texto inline"}, "text_b": {"type": "string", "description": "Segundo texto inline"}, "context_lines": {"type": "integer", "description": "Líneas de contexto"}}}},
                    {"name": "code_compare", "description": "Compara una función entre dos ficheros", "parameters": {"type": "object", "properties": {"file_a": {"type": "string", "description": "Ruta del primer fichero"}, "file_b": {"type": "string", "description": "Ruta del segundo fichero"}, "symbol": {"type": "string", "description": "Nombre del símbolo a comparar"}}}},
                    {"name": "run_tests", "description": "Ejecuta los tests del proyecto", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directorio o fichero de test"}, "filter": {"type": "string", "description": "Filtro de tests"}}}},
                    {"name": "lint_file", "description": "Ejecuta linters sobre un fichero", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Ruta al fichero a analizar"}}}},
                    {"name": "lint_project", "description": "Ejecuta linters sobre todo el proyecto", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directorio a analizar"}}}},
                ],
            },
            "debug": {
                "name": "debug",
                "description": "Agente especializado en debugging y análisis de errores",
                "model": "batiai/qwen3.5-9b:latest",
                "tools": [
                    {"name": "read_file", "description": "Lee un fichero", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Ruta al fichero"}, "offset": {"type": "integer", "description": "Primera línea (0-indexada)"}, "limit": {"type": "integer", "description": "Líneas a leer"}}}},
                    {"name": "bash", "description": "Ejecuta un comando de shell", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Comando shell a ejecutar"}, "timeout": {"type": "integer", "description": "Timeout en segundos"}, "workdir": {"type": "string", "description": "Directorio de trabajo"}}}},
                    {"name": "strace_run", "description": "Ejecuta comando con strace", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Comando a ejecutar"}, "workdir": {"type": "string", "description": "Directorio de trabajo"}, "timeout": {"type": "integer", "description": "Timeout en segundos"}}}},
                    {"name": "gdb_run", "description": "Ejecuta comando con gdb", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Comando a ejecutar"}, "workdir": {"type": "string", "description": "Directorio de trabajo"}, "timeout": {"type": "integer", "description": "Timeout en segundos"}}}},
                    {"name": "pdb_run", "description": "Ejecuta comando con pdb", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Comando a ejecutar"}, "workdir": {"type": "string", "description": "Directorio de trabajo"}, "timeout": {"type": "integer", "description": "Timeout en segundos"}}}},
                    {"name": "valgrind_run", "description": "Ejecuta comando con valgrind", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Comando a ejecutar"}, "workdir": {"type": "string", "description": "Directorio de trabajo"}, "timeout": {"type": "integer", "description": "Timeout en segundos"}}}},
                ],
            },
            "iot": {
                "name": "iot",
                "description": "Agente especializado en control de dispositivos IoT",
                "model": "batiai/qwen3.5-9b:latest",
                "tools": [
                    {"name": "tapo_on_off", "description": "Enciende/apaga dispositivo Tapo", "parameters": {"type": "object", "properties": {"device_id": {"type": "string", "description": "ID del dispositivo"}, "state": {"type": "string", "description": "on/off"}}}},
                    {"name": "tapo_set", "description": "Configura dispositivo Tapo", "parameters": {"type": "object", "properties": {"device_id": {"type": "string", "description": "ID del dispositivo"}, "brightness": {"type": "integer", "description": "Brillo (0-255)"}, "color_temp": {"type": "integer", "description": "Temperatura de color (2000-6500)"}}}},
                    {"name": "blink_arm", "description": "Configura modo armado Blink", "parameters": {"type": "object", "properties": {"device_id": {"type": "string", "description": "ID del dispositivo"}, "armed": {"type": "boolean", "description": "Armar/desarmar"}}}},
                    {"name": "alexa_speak", "description": "Hace que Alexa hable", "parameters": {"type": "object", "properties": {"device_id": {"type": "string", "description": "ID del dispositivo"}, "text": {"type": "string", "description": "Texto a hablar"}}}},
                    {"name": "tuya_control", "description": "Controla dispositivo Tuya", "parameters": {"type": "object", "properties": {"device_id": {"type": "string", "description": "ID del dispositivo"}, "command": {"type": "string", "description": "Comando a enviar"}, "payload": {"type": "string", "description": "Payload JSON"}}}},
                ],
            },
        }
        
        if template_name in templates:
            template = templates[template_name]
            sdk = AgentSDK({
                "name": template["name"],
                "model": template["model"],
                "workspace": self.workspace,
            })
            for tool in template["tools"]:
                sdk.add_tool(tool["name"], tool["description"], tool["parameters"])
            return sdk
        return self


def _slugify(name: str) -> str:
    return re.sub(r"[^\w]", "_", name.lower().strip()) or "skill"


def _import_file(path: Path):
    key = f"_oocode_skill_{path.stem}"
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _first_line(path: Path) -> str:
    try:
        for line in path.read_text().splitlines()[:6]:
            s = line.strip().strip('"""').strip("'''").strip("#").strip()
            if s and "Skill:" not in s:
                return s[:80]
    except Exception:
        pass
    return ""


def _count_tools(path: Path) -> int:
    try:
        return path.read_text().count('"name":')
    except Exception:
        return 0


def _load_set(path: Path) -> set[str]:
    if path.exists():
        try:
            return set(json.loads(path.read_text()))
        except Exception:
            pass
    return set()


def _save_set(path: Path, s: set[str]) -> None:
    path.write_text(json.dumps(sorted(s), indent=2))
