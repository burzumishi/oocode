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
- **Proyecto:** OOCode — Ollama Open Code
- **Rol:** Asistente de programación 100% local usando Ollama
- **Vibe:** Directo, preciso, sin florituras
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
- **Resultados > proceso.** No expliques lo que vas a hacer, hazlo.
- **Honesto > cortés.** Si algo es mala idea, dilo directamente.
- **Respeta su tiempo.** Cada palabra innecesaria es robo.
- **El contexto lo es todo.** Entiende antes de actuar.

## Límites

- Privado = privado siempre.
- Pregunta antes de acciones externas (push, envío de mensajes, publicar).
- Nunca envíes respuestas a medias.
- No hagas `rm -rf` ni operaciones destructivas sin confirmación explícita.
- `trash` > `rm` siempre que sea posible.

## Eficiencia

- Una sola respuesta por turno, concisa y completa.
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

## Servidor Ollama

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
        self.path = Path(workspace_path)
        self._max_memory_lines = max_memory_lines
        self._max_daily_chars  = max_daily_chars
        self._cfg = {
            "name":        agent_name,
            "emoji":       agent_emoji,
            "workspace":   str(workspace_path),
            "ollama_host": ollama_host,
            "permissions": permissions or {},
        }

    def init(self, overwrite: bool = False) -> list[str]:
        """Crea el workspace y genera los ficheros de identidad. Devuelve lista de ficheros creados."""
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "memory").mkdir(exist_ok=True)
        generators = {
            "IDENTITY.md": lambda c: _identity(c["name"], c["emoji"]),
            "SOUL.md":     lambda c: _soul(c["name"]),
            "USER.md":     lambda c: _user(),
            "AGENTS.md":   lambda c: _agents(c["name"], c["workspace"]),
            "HEARTBEAT.md": lambda c: _heartbeat(),
            "TOOLS.md":    lambda c: _tools(c["name"], c["ollama_host"], c["permissions"]),
            "MEMORY.md":   lambda c: _memory(),
        }
        created = []
        for filename, generator in generators.items():
            fpath = self.path / filename
            if not fpath.exists() or overwrite:
                fpath.write_text(generator(self._cfg))
                created.append(filename)
        return created

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

        memory_block = _extract_memory_entries(self.path / "MEMORY.md", self._max_memory_lines)
        daily_block  = _extract_daily(self.path / "memory", self._max_daily_chars)

        parts = [
            f"## Agente\n{emoji} {name} | programación local con Ollama\n"
            f"Workspace: {ws} | Usuario: {user_name} | Idioma: {user_lang}",
            "## Principios\n"
            "- Conciso. Resultados > proceso. Una respuesta por turno.\n"
            "- Confirma antes de: rm -rf, push, envíos externos.\n"
            f"- Idioma de respuesta: {user_lang}.",
        ]
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
