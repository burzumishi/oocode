import re
from pathlib import Path
from datetime import date
from typing import Optional


WORKSPACE_FILES = [
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "AGENTS.md",
    "HEARTBEAT.md",
    "TOOLS.md",
    "MEMORY.md",
]

REFERENCE_FILES = ["SOUL.md", "AGENTS.md", "TOOLS.md"]


# ── Generadores de ficheros del workspace ─────────────────────────────────────
# Todos los valores variables se pasan como parámetros — nada hardcodeado.

def _identity(agent_name: str, agent_emoji: str) -> str:
    return f"""\
# IDENTITY.md — {agent_emoji} {agent_name}

## Metadatos

- **Nombre:** {agent_name}
- **Proyecto:** OOCode — Open Code Assistant
- **Rol:** Asistente de programación 100% local
- **Vibe:** Directo y conciso, pero comunica cada paso
- **Emoji:** {agent_emoji}

## Principios

- Actúo con independencia y eficiencia.
- Tengo opiniones. No respondo "depende" sin dar una dirección clara.
- No pido permiso salvo:
    1. Riesgo de pérdida de datos.
    2. Acciones externas irreversibles (push, email, publicar).
- Siempre respondo en el idioma del usuario.
"""


def _soul(agent_name: str) -> str:
    return f"""\
# SOUL.md — Quién Eres

_Eres {agent_name}, el cerebro de OOCode. No un chatbot. Un compañero de trabajo._

## Core

- **Ayuda genuinamente, no performativamente.** Sin "¡Claro!", "¡Por supuesto!" — solo ayuda.
- **Sé proactivo.** Lee el contexto antes de preguntar. Busca antes de rendirte.
- **Gana confianza con competencia.** Tienes acceso al código y ficheros del usuario. Respétalo.
- **Comunica mientras trabajas.** Narra conciso qué haces y qué encuentras — el usuario te sigue por tu texto, no por las tools. Nunca trabajes en silencio.
- **Honesto > cortés.** Si algo es mala idea, dilo directamente.
- **Respeta su tiempo.** Frases breves y con contenido; ahorra en floritura, no en informar.
- **El contexto lo es todo.** Entiende antes de actuar.

## Límites

- Privado = privado siempre.
- Pregunta antes de acciones externas (push, envío de mensajes, publicar).
- Nunca envíes respuestas a medias.
- No hagas `rm -rf` ni operaciones destructivas sin confirmación explícita.
- `trash` > `rm` siempre que sea posible.

## Eficiencia

- Respuestas concisas y completas; nunca trabajes en silencio: comunica antes y después de cada paso.
- Consulta el historial y la memoria antes de preguntar algo obvio.
- No seas eco. Si ya se respondió, resume.

## Continuidad

Estos ficheros son tu memoria. Léelos al arrancar. Actualízalos cuando aprendas algo nuevo.

**Idioma:** Responde siempre en español a menos que el usuario escriba en otro idioma.
"""


def _user() -> str:
    return """\
# USER.md — Sobre Tu Usuario

_Actualiza este fichero a medida que conoces mejor a la persona que ayudas._

## Datos Básicos

- **Nombre:** (sin configurar)
- **Llamado:** (sin configurar)
- **Zona horaria:** (sin configurar)
- **Idioma:** (sin configurar)
- **Estilo:** (sin configurar)

## Proyectos Activos

_(Añade aquí los proyectos activos del usuario.)_

## Preferencias

_(Añade aquí tecnologías, herramientas y preferencias del usuario.)_

## Notas

_(Añade aquí lo que vayas aprendiendo sobre el usuario.)_
"""


def _agents(agent_name: str, workspace: str) -> str:
    return f"""\
# AGENTS.md — Workspace de {agent_name}

Este directorio es tu base de operaciones. Trátalo como tal.

## Arranque de Sesión

Lee al inicio (en orden):

1. `IDENTITY.md` — quién eres
2. `SOUL.md` — cómo actúas
3. `USER.md` — a quién ayudas
4. `TOOLS.md` — tu entorno específico
5. `MEMORY.md` — tu memoria a largo plazo (solo en sesión principal)

Memoria diaria reciente: `memory/YYYY-MM-DD.md`

No releas los ficheros de arranque salvo que el usuario lo pida o el contexto proporcionado esté incompleto.

## Memoria

Despiertas fresco en cada sesión. Estos ficheros son tu continuidad:

- **Diario:** `memory/YYYY-MM-DD.md` — logs crudos de lo que pasó hoy
- **Largo plazo:** `MEMORY.md` — recuerdos curados, decisiones importantes, lecciones

Escribe lo que importa. Decisiones, contexto, cosas a recordar.

### Regla de oro: Sin "notas mentales"

- La memoria es limitada. Si quieres recordar algo, **escríbelo en un fichero**.
- Las notas mentales no sobreviven al reinicio de sesión. Los ficheros sí.
- Cuando alguien diga "recuerda esto" → actualiza `memory/{date.today().isoformat()}.md`
- Cuando aprendas una lección → actualiza `AGENTS.md`, `TOOLS.md` o el fichero relevante

## Líneas Rojas

- No exfiltres datos privados. Nunca.
- No ejecutes comandos destructivos sin confirmar (`rm -rf`, `DROP TABLE`, `git reset --hard`).
- `trash` > `rm` (recuperable > borrado para siempre).
- Ante la duda, pregunta.

## Acciones Libres vs Requieren Confirmación

**Libres:**
- Leer ficheros, explorar, organizar, buscar en la web
- Trabajar dentro de este workspace

**Requieren confirmación:**
- Enviar emails, mensajes, publicar en internet
- Push a repositorios remotos
- Cualquier acción irreversible o externa

## Workspace

- **Ruta:** `{workspace}`
- **Git:** Se recomienda hacer backup semanal con `git add -A && git commit -m "workspace backup"`

## Notas

_(Personaliza aquí cómo trabajas con otros agentes: cuándo delegar, en qué agente, qué subtareas prefieres repartir. Lo que escribas en esta sección se carga en el contexto del agente — los placeholders no.)_
"""


def _heartbeat() -> str:
    return """\
# HEARTBEAT.md

```
# Deja este fichero vacío (o solo con comentarios) para saltarte el heartbeat.
# Añade tareas abajo cuando quieras que el agente compruebe algo periódicamente.
```

## Ejemplo de checklist

```markdown
- [ ] Revisar commits pendientes de push
- [ ] Comprobar tests fallidos
- [ ] Actualizar MEMORY.md si hay sesiones recientes sin procesar
```
"""


def _tools(agent_name: str, ollama_host: str, permissions: dict) -> str:
    perm_rows = "\n".join(
        f"| `{tool}` | {mode} | |"
        for tool, mode in permissions.items()
    )
    return f"""\
# TOOLS.md — Entorno Local de {agent_name}

Las skills definen _cómo_ funcionan las herramientas. Este fichero es para _tu_ entorno específico.

## Servidor LLM (backend)

- **Host:** {ollama_host}

## Herramientas OOCode

| Tool | Permiso por defecto | Descripción |
|------|--------------------|-|
{perm_rows}

## Debug

- **Limpiar historial REPL:** `rm ~/.oocode/history`
- **Config:** `~/.oocode/oocode.json`
- **Memoria:** `~/.oocode/workspace/<agente>/memory/`

## Notas

_(Añade aquí configuración específica de tu entorno: alias SSH, nombres de dispositivos, preferencias de herramientas.)_
"""


def _memory() -> str:
    return f"""\
# MEMORY.md — Memoria a Largo Plazo

_Última actualización: {date.today().isoformat()}_

## Usuario

_(Añade aquí datos del usuario una vez los conozcas.)_

## Proyecto

_(Añade aquí contexto del proyecto activo.)_

## Decisiones Técnicas

_(Añade aquí decisiones importantes tomadas durante el desarrollo.)_

## Lecciones Aprendidas

_(Añade aquí lecciones que no quieres repetir.)_
"""


# ── WorkspaceManager ──────────────────────────────────────────────────────────

class WorkspaceManager:
    def __init__(
        self,
        workspace_path: str,
        agent_name: str = "OOCode",
        agent_emoji: str = "🤖",
        ollama_host: str = "http://localhost:11434",
        permissions: Optional[dict] = None,
        max_memory_lines: int = 12,
        max_daily_chars: int = 400,
    ):
        self.path = Path(workspace_path).expanduser()
        self._max_memory_lines = max_memory_lines
        self._max_daily_chars  = max_daily_chars
        self._cfg = {
            "name":        agent_name,
            "emoji":       agent_emoji,
            "workspace":   str(workspace_path),
            "ollama_host": ollama_host,
            "permissions": permissions or {},
        }

    def init(self, overwrite: bool = False, use_examples: bool = True) -> list[str]:  # noqa: ARG002
        """Crea el workspace y genera los ficheros de identidad. Devuelve lista de ficheros creados.

        Los ficheros se leen desde workspace/templates/ (empaquetados con el código).
        MEMORY.md se genera dinámicamente (contiene fecha de hoy).
        Fallback a generadores dinámicos si falta algún fichero en templates/.
        """
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "memory").mkdir(exist_ok=True)

        templates_dir = Path(__file__).parent / "templates"
        created = []

        for filename in WORKSPACE_FILES:
            fpath = self.path / filename
            tpl = templates_dir / filename

            if filename == "MEMORY.md":
                content = _memory()
            elif tpl.exists():
                content = tpl.read_text()
            else:
                # Fallback a generadores dinámicos
                if filename == "AGENTS.md":
                    content = _agents(self._cfg.get("name", "OOCode"), self._cfg.get("workspace", str(self.path.parent)))
                elif filename == "HEARTBEAT.md":
                    content = _heartbeat()
                elif filename == "TOOLS.md":
                    content = _tools(
                        self._cfg.get("name", "OOCode"),
                        self._cfg.get("ollama_host", "http://localhost:11434"),
                        self._cfg.get("permissions", {})
                    )
                elif filename == "IDENTITY.md":
                    content = _identity(self._cfg.get("name", "OOCode"), self._cfg.get("emoji", "🤖"))
                elif filename == "SOUL.md":
                    content = _soul(self._cfg.get("name", "OOCode"))
                elif filename == "USER.md":
                    content = _user()
                else:
                    content = ""

            if not fpath.exists() or overwrite:
                fpath.write_text(content)
                created.append(filename)
        return created

    @property
    def user_name(self) -> str:
        """Alias/nombre del usuario desde USER.md ('Llamado'), o '' si no está configurado."""
        user_md = self.path / "USER.md"
        if not user_md.exists():
            return ""
        for line in user_md.read_text().splitlines():
            if "**Llamado:**" in line:
                val = line.split("**Llamado:**")[-1].strip()
                if val and "(sin configurar)" not in val and "__" not in val:
                    return val
        return ""

    def load_context(self) -> str:
        """Delega al mini-context compacto (usado en system prompt)."""
        return self.load_mini_context()

    def load_mini_context(self) -> str:
        """
        Bloque de identidad compacto para el system prompt.
        Usa los límites configurados en max_memory_lines / max_daily_chars.
        """
        name  = self._cfg["name"]
        emoji = self._cfg["emoji"]
        ws    = self._cfg["workspace"]

        user_name, user_lang = "el usuario", "español"
        user_md = self.path / "USER.md"
        if user_md.exists():
            for line in user_md.read_text().splitlines():
                if "**Llamado:**" in line:
                    val = line.split("**Llamado:**")[-1].strip()
                    if val and "(sin configurar)" not in val:
                        user_name = val
                if "**Idioma:**" in line:
                    val = line.split("**Idioma:**")[-1].strip()
                    if val and "(sin configurar)" not in val:
                        user_lang = val

        # Identidad: resumen compacto extraído de IDENTITY.md y SOUL.md (fuente única).
        identity_md = ""
        soul_md     = ""
        _id_path = self.path / "IDENTITY.md"
        _soul_path = self.path / "SOUL.md"
        if _id_path.exists():
            identity_md = _id_path.read_text()
        if _soul_path.exists():
            soul_md = _soul_path.read_text()

        rol  = _extract_md_field(identity_md, "Rol")
        vibe = _extract_md_field(identity_md, "Vibe")
        agente_line = f"{emoji} {name}"
        if rol:
            agente_line += f" — {rol}"
        if vibe:
            agente_line += f" · {vibe}"

        principles = _extract_soul_principles(soul_md)
        if principles:
            behavior_block = "## Comportamiento\n" + "\n".join(f"- {p}" for p in principles)
        else:
            behavior_block = (
                "## Comportamiento\n"
                "- Narra tu trabajo conciso pero continuo: di qué haces antes de cada paso y qué encontraste después. Frases breves, sin relleno ni '¡Claro!'.\n"
                "- El usuario solo ve tu texto, no las tools: nunca trabajes en silencio.\n"
                "- Confirma antes de acciones destructivas o externas (rm -rf, push, envíos)."
            )

        memory_block = _extract_memory_entries(self.path / "MEMORY.md", self._max_memory_lines)
        daily_block  = _extract_daily(self.path / "memory", self._max_daily_chars)

        # Capa de personalización del usuario: secciones "## Notas" de TOOLS.md y
        # AGENTS.md. Permite personalizar usos de herramientas y delegación SIN
        # editar código ni SYSTEM_RULES. Solo se carga lo que el usuario escriba
        # (los placeholders de plantilla se filtran), así que es coste cero hasta
        # que personaliza. Los ficheros completos siguen disponibles en /ctx full.
        tools_md  = ""
        agents_md = ""
        _tools_path  = self.path / "TOOLS.md"
        _agents_path = self.path / "AGENTS.md"
        if _tools_path.exists():
            tools_md = _tools_path.read_text()
        if _agents_path.exists():
            agents_md = _agents_path.read_text()
        custom_tools  = _extract_section(tools_md, "Notas")
        custom_agents = _extract_section(agents_md, "Notas")

        parts = [
            f"## Agente\n{agente_line}\n"
            f"Workspace: {ws} | Usuario: {user_name} | Idioma de respuesta: {user_lang}",
            behavior_block,
        ]
        if custom_agents:
            parts.append(f"## Personalización de agentes\n{custom_agents}")
        if custom_tools:
            parts.append(f"## Preferencias de herramientas\n{custom_tools}")
        if memory_block:
            parts.append(f"## Memoria clave\n{memory_block}")
        if daily_block:
            parts.append(f"## Sesión de hoy\n{daily_block}")

        return "\n\n".join(parts)

    def load_full_context(self) -> str:
        """Contexto completo: todos los ficheros del workspace (para /ctx full)."""
        sections = []
        for filename in WORKSPACE_FILES:
            fpath = self.path / filename
            if fpath.exists():
                content = fpath.read_text().strip()
                if content:
                    sections.append(content)
        mem_dir = self.path / "memory"
        if mem_dir.exists():
            for df in sorted(mem_dir.glob("????-??-??.md"), reverse=True)[:2]:
                content = df.read_text().strip()
                if content:
                    sections.append(f"## Memoria reciente ({df.stem})\n\n{content}")
        return "\n\n---\n\n".join(sections)

    def exists(self) -> bool:
        return self.path.exists() and (self.path / "IDENTITY.md").exists()

    def write_daily_memory(self, content: str) -> Path:
        mem_dir = self.path / "memory"
        mem_dir.mkdir(exist_ok=True)
        today = date.today().isoformat()
        fpath = mem_dir / f"{today}.md"
        existing = fpath.read_text() if fpath.exists() else f"# {today}\n\n"
        fpath.write_text(existing + "\n" + content)
        return fpath

    def mark_new_session(self) -> None:
        """Escribe un separador en el diario del día para aislar la sesión nueva.
        _extract_daily solo leerá el bloque posterior al último separador."""
        mem_dir = self.path / "memory"
        mem_dir.mkdir(exist_ok=True)
        today = date.today().isoformat()
        fpath = mem_dir / f"{today}.md"
        if not fpath.exists():
            return
        existing = fpath.read_text().rstrip()
        # Solo añadir separador si hay contenido real (no solo el header)
        if existing and existing != f"# {today}" and not existing.endswith("\n---"):
            fpath.write_text(existing + "\n\n---\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_section(text: str, header: str, max_chars: int = 1500) -> str:
    """Cuerpo de una sección '## header' hasta el siguiente '## ' o '---'.

    Devuelve solo el contenido REAL escrito por el usuario: filtra las líneas
    placeholder de la plantilla (italic `_(...)_`, "Añade aquí…", "(sin configurar)").
    "" si la sección no existe o solo tiene placeholders. Acotado a max_chars para
    que la personalización del usuario no infle el contexto sin límite.

    Es la capa de personalización por-agente: lo que el usuario escriba en la
    sección "## Notas" de AGENTS.md / TOOLS.md se carga en el system prompt (mini),
    sin tocar SYSTEM_RULES (la base de disciplina/seguridad sigue en código).
    """
    if not text:
        return ""
    out: list[str] = []
    capturing = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## ") or s == "---":
            if capturing:
                break
            capturing = s.startswith("## ") and s[3:].strip().lower() == header.strip().lower()
            continue
        if capturing:
            out.append(line)
    kept = [
        ln for ln in out
        if ln.strip()
        and not re.fullmatch(r"_\(.*\)_", ln.strip())
        and "Añade aquí" not in ln
        and "(sin configurar)" not in ln
    ]
    body = "\n".join(kept).strip()
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + "\n… (truncado)"
    return body


def _extract_md_field(text: str, field: str) -> str:
    """Valor de un campo del .md. Acepta '- **Rol:** X', '**Rol:** X' o 'Rol: X'."""
    bold = f"**{field}:**"
    plain = f"{field}:"
    for line in text.splitlines():
        s = line.strip().lstrip("-").strip()
        if s.startswith(bold):
            return s.split(bold, 1)[-1].strip()
        if s.startswith(plain):
            val = s.split(plain, 1)[-1].strip()
            return re.sub(r"[*_`]", "", val).strip()
    return ""


def agent_role(workspace_path) -> str:
    """Rol/especialidad de un agente, leído del campo 'Rol' de su IDENTITY.md.

    Devuelve "" si no hay fichero o el campo no existe. Punto único usado tanto
    por los schemas de orquestación (spawn_subagent/create_team) como por la
    cabecera "Agentes disponibles para delegar" del system prompt — así el LLM
    sabe de forma genérica (sin prompts hardcodeados) qué agente encaja en cada
    tarea y puede delegar para ahorrar contexto y herramientas.
    """
    try:
        _id_path = Path(workspace_path).expanduser() / "IDENTITY.md"
        if not _id_path.exists():
            return ""
        return _extract_md_field(_id_path.read_text(encoding="utf-8"), "Rol")
    except Exception:
        return ""


def _extract_soul_principles(text: str, max_items: int = 6) -> list[str]:
    """Resumen compacto del comportamiento: titulares de la primera lista numerada de SOUL.md.

    De '1. **Ayuda genuinamente.** Sin "¡Claro!"...' devuelve 'Ayuda genuinamente'.
    Robusto frente a SOUL personalizados (no exige una sección concreta).
    """
    out: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^\d+\.\s+(.*)", line.strip())
        if not m:
            continue
        body = m.group(1)
        mb = re.search(r"\*\*(.*?)\*\*", body)
        headline = mb.group(1) if mb else body.split(".")[0]
        headline = re.sub(r"[*_`]", "", headline).strip().rstrip(".:")
        if len(headline) > 70:
            headline = headline[:67].rstrip() + "…"
        if headline:
            out.append(headline)
            if len(out) >= max_items:
                break
    return out


def _extract_memory_entries(mem_path: Path, max_lines: int) -> str:
    """Extrae líneas con contenido real de MEMORY.md (ignora headers y plantilla)."""
    if not mem_path.exists():
        return ""
    skip_patterns = ("_(Añade", "_(actualiza", "# ", "_Última", "## ")
    lines = []
    for line in mem_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(p) for p in skip_patterns):
            continue
        if stripped.startswith("-") or stripped.startswith("*"):
            lines.append(stripped)
    return "\n".join(lines[:max_lines]) if lines else ""


def _extract_daily(mem_dir: Path, max_chars: int) -> str:
    """Devuelve SOLO el bloque del diario de hoy correspondiente a la sesión actual.
    Los separadores '---' escritos por mark_new_session() delimitan sesiones;
    solo se devuelve el contenido posterior al último separador."""
    if not mem_dir.exists():
        return ""
    today_file = mem_dir / f"{date.today().isoformat()}.md"
    if not today_file.exists():
        return ""
    # Leer sin strip() para que el split funcione aunque el fichero no tenga
    # newline final (la condición de vacío se evalúa sobre .strip() aparte)
    raw = today_file.read_text()
    header = f"# {date.today().isoformat()}"
    if not raw.strip() or raw.strip() == header:
        return ""

    # Dividir por los separadores de sesión; tomar solo el bloque más reciente
    blocks = raw.split("\n---\n")
    current = blocks[-1].strip() if blocks else raw.strip()

    # Quitar el header del bloque si aparece al inicio
    if current.startswith(header):
        current = current[len(header):].lstrip("\n").strip()

    if not current:
        return ""
    if len(current) > max_chars:
        current = current[:max_chars] + "…"
    return current
