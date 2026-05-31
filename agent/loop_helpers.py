"""Helpers, constantes y funciones puras del bucle del agente.

Extraído de agent/loop.py para mantener loop.py manejable.
Importar desde aquí directamente o a través de agent.loop (re-exporta todo).
"""
import json
import os
import re
import random
import time
import threading

_SPINNER_FRAMES    = ["○", "◌", "◎", "◉", "●", "◉", "◎", "◌"]
_POLL_INTERVAL     = 0.2    # segundos entre ticks del spinner normal (5 fps)
# spawn_subagent usa un intervalo más lento: la tool puede tardar minutos
_SUBAGENT_SPINNER_POLL = 0.5   # segundos entre ticks del spinner de spawn_subagent
# Spinner de compactación (se ejecuta en background thread mientras LLM resume)
_COMPACT_SPINNER_POLL  = 0.4   # segundos entre ticks del spinner de compactación
# Timeout de join del hilo de animación REPL tras terminar la tool
_ANIM_JOIN_TIMEOUT     = 0.5   # segundos máximos de espera para unirse al hilo

# Número máximo de tareas que _detect_tasks extrae de un plan y plan_create muestra
_MAX_PLAN_TASKS = 12

# Umbral de ratio bash/total para activar el aviso de sobreuso (>40% = problema)
_BASH_OVERUSE_RATIO = 0.4

# Animación del header de tool en modo REPL: ciclo verde→amarillo (120 ms/frame)
_HEADER_ANIM_CODES = ["\033[32m", "\033[92m", "\033[33m", "\033[93m"]
_ANSI_BOLD  = "\033[1m"
_ANSI_RESET = "\033[0m"
_TIMEOUT_SENTINEL  = "__oocode_timeout__"  # señal de timeout de _stream_response
_FALLBACK_MIN_CHARS = 50                   # chars mínimos para considerar respuesta iniciada

_THINKING_WORDS = [
    # Españolas reales
    "Cavilando", "Cogitando", "Ruminando", "Elucubrando",
    "Maquinando", "Ponderando", "Discurriendo", "Deliberando",
    # Inventadas tech
    "Neuroneando", "Sinaptizando", "Tokenizando", "Vectorizando",
    "Inferenciando", "Transformeando", "Embedizando", "Prompteando",
    "Tensorando", "Gradientando", "Sampliando", "Decodificando",
    "Atteneando", "Softmaxeando", "Backproneando", "Halucineando",
]

# Palabras de "pensamiento" específicas para modo multi-tarea
# Se usan cuando hay un plan activo y el agente está ejecutando tareas
_MULTITASK_WORDS = [
    "Planificando", "Organizando", "Orquestando", "Coordinando",
    "Secuenciando", "Estructurando", "Implementando", "Ejecutando",
]

# Frases naturales para el indicador pre-vuelo de tareas múltiples
# El placeholder {n} se reemplaza por el número de tareas detectadas.
_TASK_PREFLIGHT_PHRASES = [
    "Voy a trabajar en {n} tareas — déjame elaborar el plan primero…",
    "Recibido: {n} objetivos en cola — organizando la mejor estrategia ahora…",
    "He identificado {n} tareas — voy a prepararlas en el orden correcto…",
    "Entendido, {n} tareas en cola — estructurando el plan ahora mismo…",
    "Veo {n} cosas que hacer — diseñando la hoja de ruta antes de ejecutar…",
    "He apuntado tus {n} tareas — voy a abordarlas de forma ordenada…",
    "{n} objetivos identificados — preparando el plan de trabajo ahora…",
    "Voy a por ello: {n} tareas en el plan — empezando a prepararlas ya…",
    "Procesando tus {n} objetivos — ordenando la secuencia ahora mismo…",
    "Listo: {n} tareas — voy a organizarlas y empezar cuanto antes…",
]

# Colores para el ● pulsante del indicador de tareas múltiples
_TASK_ICON_COLORS = ["bold cyan", "bold magenta", "bold yellow", "bold blue", "bold green"]

# Saludos opcionales cuando se conoce el nombre del usuario (35% de probabilidad)
_PREFLIGHT_USER_GREETINGS = [
    "Claro, {user} —",
    "Entendido, {user} —",
    "{user},",
    "Voy a ello, {user} —",
    "Perfecto, {user} —",
]

# Frases genéricas de fallback (sin acción ni dominio reconocidos)
_SINGLE_PREFLIGHT_GENERIC = [
    "Voy a ello — dame un momento…",
    "Entendido, me pongo a trabajar ahora mismo…",
    "Déjame revisar esto y te respondo enseguida…",
    "Ahora mismo me pongo a ello — un segundo…",
    "Voy a trabajar en eso ahora mismo…",
    "Un momento — me pongo a ello ya…",
    "Recibido — voy a ello ahora mismo…",
    "Déjame pensar en esto y te respondo en un momento…",
]

# Regex para detectar saludos iniciales que no aportan intención de tarea.
# Se eliminan del texto antes de hacer matching para que "hola, arregla el bug"
# no quede reducido a "hola" y caiga en el genérico.
_PF_GREETING_RE = re.compile(
    r'^(hola|buenos?\s+d[ií]as?|buenas?\s+tardes?|buenas?\s+noches?|hey\b|hi\b'
    r'|gracias|de\s+nada|thanks|ok\b|okay|perfecto|genial|bien\b|claro|entendido'
    r'|hola\s+a\s+todos)[,!.\s]*',
    re.IGNORECASE,
)

# ── Patrones de ACCIÓN (qué va a hacer el agente) ────────────────────────────
# Lista ordenada de (clave, patrón). Se puntúan TODOS (findall); gana el de mayor score.
# Posición importa en empates: primero = mayor prioridad.
_PF_ACTIONS: list[tuple[str, str]] = [
    ("fix",      r'\b(fix|arregla|arreglar|corrige|corregir|bug|bugs|error|errors|excepci[oó]n|exception|fallo|fallos|traceback|no\s+funciona|broken|roto)\b'),
    ("explain",  r'\b(explica|explicar|qu[eé]\s+es|c[oó]mo\s+funciona|qu[eé]\s+hace|describe|resume|explain|enti[eé]nde|entender|qu[eé]\s+significa|para\s+qu[eé]\s+sirve)\b'),
    ("search",   r'\b(busca|buscar|encuentra|encontrar|grep|d[oó]nde\s+est[aá]|where|lista|listar|qu[eé]\s+fichero|qu[eé]\s+archivo|hay\s+alg[uú]n|muestra|mu[eé]strame)\b'),
    ("refactor", r'\b(refactori[zs]a|refactori[zs]ar|reescribe|reescribir|reestructura|reestructurar|limpia|limpiar|cleanup|renombra|renombrar|mueve|mover|migra|migrar|reorgani[zs]a|simplifica)\b'),
    ("review",   r'\b(revisa|revisar|audita|auditar|analiza|analizar|comprueba|comprobar|verifica|verificar|inspecciona|examina|examinar|mira\b|lee\b|leer\b|check\b)\b'),
    ("create",   r'\b(crea|crear|implementa|implementar|escribe|escribir|a[ñn]ade|a[ñn]adir|genera|generar|nueva|nuevo|build\b|construye|construir|dise[ñn]a|define|definir|haz\b|hacer\b)\b'),
    ("run",      r'\b(ejecuta|ejecutar|run\b|lanza|lanzar|levanta|levantar|inicia|iniciar|start\b|arranca|arrancar|pasa\b|pasar\b|corr[ei]|prueba\b|probar\b)\b'),
    ("update",   r'\b(actualiza|actualizar|modifica|modificar|edita|editar|cambia|cambiar|ajusta|ajustar|mejora|mejorar|update\b|upgrade\b|incorpora|configura|configurar)\b'),
]

# ── Patrones de DOMINIO (en qué área) ────────────────────────────────────────
# Dominios específicos van antes que el genérico "code" para ganar en empates.
_PF_DOMAINS: list[tuple[str, str]] = [
    ("security", r'\b(seguridad|security|nmap|vuln|cve|exploit|ctf|pentest|hash|crypto|xss|sql.?injection|firewall|certificado|ssl|tls|audit[oí])\b'),
    ("iot",      r'\b(iot\b|tapo|alexa|mqtt|home.?assistant|esphome|tuya|blink\b|sensor|luz\b|l[aá]mpara|dispositivo|zigbee|zwave|domotica)\b'),
    ("docker",   r'\b(docker|container|contenedor|imagen\s+docker|compose|dockerfile)\b'),
    ("git",      r'\b(git\b|commit|branch|rama\b|merge|diff\b|historial\s+git|stash|push\b|pull\b|rebase|tag\b)\b'),
    ("tests",    r'\b(test\b|tests\b|pytest|jest|mocha|cobertura|coverage|unit\s+test|suite\s+de\s+pruebas|pruebas?\b)\b'),
    ("docs",     r'\b(plantilla|template|documento|word\b|excel\b|pdf\b|informe|report\b|presentaci[oó]n|docx|xlsx|pptx|word\b)\b'),
    ("deploy",   r'\b(despliega|deploy|despliegue|kubernetes|k8s|nginx|aws|gcp|azure|ci\b|cd\b|pipeline|infraestructura)\b'),
    ("config",   r'\b(configuraci[oó]n|config\b|settings\b|oocode\.json|\.json\b|\.yaml\b|\.toml\b|\.ini\b|parámetro)\b'),
    ("lsp",      r'\b(lsp\b|s[ií]mbolo|symbol|diagn[oó]stico|diagnostic|definici[oó]n|referencia|autocompletado|clangd|pylsp|gopls)\b'),
    ("deps",     r'\b(dependencia|depend|requirements|package\.json|paquete|pip\b|npm\b|yarn\b|poetry\b|pipenv)\b'),
    ("code",     r'\b(c[oó]digo|code\b|funci[oó]n|func\b|clase\b|class\b|m[eé]todo|method\b|m[oó]dulo|module\b|implementaci[oó]n|algoritmo)\b'),
]

# ── Frases por (acción, dominio) ─────────────────────────────────────────────
# Clave: (acción, dominio) — dominio None = frase genérica de esa acción.
_PF_PHRASES: dict[tuple[str, str | None], list[str]] = {
    # FIX ─────────────────────────────────────────────────────────────────────
    ("fix", None):       ["Voy a depurar eso — déjame reproducir el problema primero…",
                          "Déjame encontrar la causa raíz antes de tocar nada…",
                          "Voy a analizar el fallo con calma — ahora mismo me pongo…",
                          "Buscando la raíz del problema antes de corregir nada…"],
    ("fix", "code"):     ["Voy a depurar el código — déjame localizar el fallo primero…",
                          "Revisando el código para encontrar la causa raíz…",
                          "Voy a la raíz del error — déjame inspeccionarlo con calma…",
                          "Déjame leer el módulo antes de tocar nada — quiero entender qué falla…"],
    ("fix", "docker"):   ["Voy a revisar los logs del contenedor para encontrar el problema…",
                          "Depurando el entorno Docker — déjame ver qué está fallando…",
                          "Inspeccionando los contenedores — voy a la causa del fallo…"],
    ("fix", "tests"):    ["Voy a analizar los tests fallidos para encontrar qué los rompe…",
                          "Depurando los tests — déjame ver exactamente qué está fallando…",
                          "Revisando la suite para encontrar la causa de los fallos…"],
    ("fix", "git"):      ["Voy a revisar el historial para rastrear dónde entró el fallo…",
                          "Buscando en los commits recientes la causa del problema…"],
    ("fix", "config"):   ["Voy a revisar la configuración para localizar el problema…",
                          "Inspeccionando los ficheros de config — déjame localizar el fallo…"],
    ("fix", "deploy"):   ["Voy a revisar la configuración de despliegue para encontrar el fallo…",
                          "Depurando el pipeline — déjame ver qué está fallando…"],
    ("fix", "security"): ["Voy a analizar la vulnerabilidad — déjame reproducirla primero…",
                          "Revisando el fallo de seguridad con calma antes de parchear…"],
    ("fix", "deps"):     ["Voy a revisar las dependencias para encontrar el conflicto…",
                          "Inspeccionando los paquetes — déjame localizar el problema…"],

    # EXPLAIN ─────────────────────────────────────────────────────────────────
    ("explain", None):   ["Déjame leer el código para explicarte esto en detalle…",
                          "Voy a analizarlo bien para responderte con la mayor precisión…",
                          "Ahora mismo lo estudio para explicarte cómo funciona…",
                          "Leyendo el módulo — quiero entenderlo bien antes de explicarte…"],
    ("explain", "code"): ["Voy a leer el módulo para explicarte cómo funciona…",
                          "Déjame analizar ese código — luego te explico con detalle…",
                          "Estudiando la implementación para explicarte la lógica interna…"],
    ("explain", "docker"):["Voy a revisar la configuración Docker para explicarte qué hace…",
                           "Leyendo el Dockerfile y el compose — te lo explico en un momento…"],
    ("explain", "git"):  ["Voy a leer el historial para explicarte qué ha pasado…",
                          "Déjame revisar los commits — luego te cuento qué ha cambiado…"],
    ("explain", "config"):["Voy a leer la configuración para explicarte cómo funciona…",
                           "Déjame revisar los parámetros — te explico qué hace cada uno…"],
    ("explain", "lsp"):  ["Voy a consultar los símbolos del proyecto para explicarte esto…",
                          "Déjame buscar la definición y las referencias — te explico enseguida…"],
    ("explain", "security"):["Voy a analizar el vector de ataque para explicarte qué implica…",
                             "Leyendo el contexto de seguridad — te explico en detalle…"],
    ("explain", "iot"):  ["Voy a revisar la configuración del dispositivo para explicarte cómo funciona…"],

    # SEARCH ──────────────────────────────────────────────────────────────────
    ("search", None):    ["Voy a rastrear eso en el proyecto — enseguida te digo lo que encuentro…",
                          "Buscando ahora mismo — te cuento todo lo que encuentre…",
                          "Déjame explorar el código — ahora mismo te digo dónde está…",
                          "Voy a buscarlo — enseguida te tengo una respuesta…"],
    ("search", "code"):  ["Voy a rastrear ese símbolo en el código — dame un segundo…",
                          "Buscando en el repositorio — enseguida te digo dónde está…",
                          "Déjame explorar los ficheros — ahora mismo te digo lo que encuentro…"],
    ("search", "git"):   ["Voy a buscar eso en el historial de git — dame un momento…",
                          "Rastreando en los commits — enseguida te digo qué hay…"],
    ("search", "docs"):  ["Voy a buscar en la documentación — ahora mismo te digo lo que encuentro…"],
    ("search", "security"):["Voy a rastrear eso en el análisis de seguridad — dame un segundo…"],
    ("search", "lsp"):   ["Voy a buscar las referencias y definiciones — un momento…",
                          "Rastreando el símbolo con el LSP — enseguida te digo dónde está…"],

    # REFACTOR ────────────────────────────────────────────────────────────────
    ("refactor", None):  ["Voy a analizar el impacto antes de reorganizar nada…",
                          "Déjame estudiar la estructura antes de mover nada…",
                          "Planificando la refactorización — primero reviso qué puede romperse…",
                          "Voy a reorganizar esto con cuidado — analizando el impacto primero…"],
    ("refactor", "code"):["Voy a analizar el código antes de reorganizarlo — un momento…",
                          "Estudiando la estructura para refactorizarla correctamente…",
                          "Déjame leer el módulo antes de mover nada — quiero ver el impacto completo…"],
    ("refactor", "tests"):["Voy a revisar los tests antes de reorganizar — no quiero romper nada…"],
    ("refactor", "deps"): ["Voy a revisar las dependencias antes de reorganizar los paquetes…"],

    # REVIEW / AUDIT ──────────────────────────────────────────────────────────
    ("review", None):    ["Voy a revisarlo en detalle — dame un momento…",
                          "Déjame analizar esto con calma antes de responderte…",
                          "Voy a auditarlo — revisando todo el contexto primero…",
                          "Inspeccionando en detalle — ahora mismo me pongo…"],
    ("review", "code"):  ["Voy a revisar el código en detalle — dame un momento…",
                          "Analizando el código con calma — déjame leerlo todo primero…",
                          "Leyendo el módulo completo antes de darte mi análisis…"],
    ("review", "security"):["Voy a auditar eso desde el punto de vista de seguridad…",
                            "Revisando posibles vulnerabilidades — dame un momento…",
                            "Analizando la superficie de ataque — ahora mismo me pongo…"],
    ("review", "config"): ["Voy a revisar la configuración en detalle…",
                           "Inspeccionando los parámetros — déjame leerlos todos…"],
    ("review", "tests"):  ["Voy a revisar los tests — déjame leerlos antes de comentar…",
                           "Analizando la suite de tests — un momento…"],
    ("review", "git"):    ["Voy a revisar los cambios recientes en el repositorio…",
                           "Inspeccionando el historial — déjame leerlo con calma…"],
    ("review", "docker"): ["Voy a revisar la configuración Docker en detalle…",
                           "Inspeccionando los contenedores y el compose — dame un momento…"],
    ("review", "deploy"):  ["Voy a revisar la configuración de despliegue en detalle…"],
    ("review", "iot"):     ["Voy a revisar la configuración de los dispositivos IoT…"],

    # CREATE ──────────────────────────────────────────────────────────────────
    ("create", None):    ["Voy a implementar eso — déjame diseñar la solución primero…",
                          "Entendido, voy a construir eso ahora mismo…",
                          "Voy a desarrollar eso — dame un momento para planificarlo…",
                          "Me pongo a implementar — déjame estructurarlo bien primero…"],
    ("create", "code"):  ["Voy a implementar el código — déjame estructurarlo bien…",
                          "Voy a escribir eso — diseñando la solución antes de empezar…",
                          "Desarrollando la implementación ahora mismo…",
                          "Déjame diseñar la solución antes de escribir la primera línea…"],
    ("create", "tests"): ["Voy a escribir los tests — déjame analizar qué casos cubrir…",
                          "Construyendo la suite de tests — un momento para diseñarla bien…"],
    ("create", "docs"):  ["Voy a generar el documento con el formato correcto — dame un momento…",
                          "Construyendo el documento ahora mismo — procesando el contenido…",
                          "Preparando el documento — me pongo a generarlo enseguida…"],
    ("create", "config"):["Voy a generar la configuración — déjame estructurarla bien…",
                          "Construyendo el fichero de config — un momento para diseñarlo…"],
    ("create", "docker"):["Voy a construir la configuración Docker — déjame estructurarla bien…",
                          "Preparando el Dockerfile y el compose — ahora mismo me pongo…"],
    ("create", "deploy"):["Voy a preparar la configuración de despliegue — dame un momento…"],
    ("create", "security"):["Voy a preparar el análisis de seguridad — déjame estructurarlo bien…"],

    # RUN ─────────────────────────────────────────────────────────────────────
    ("run", None):       ["Voy a ejecutarlo — comprobando el entorno primero…",
                          "Iniciando la ejecución — dame un segundo para prepararlo…",
                          "Voy a lanzarlo ahora — un momento mientras lo arranco…"],
    ("run", "tests"):    ["Voy a ejecutar los tests — revisando el entorno primero…",
                          "Lanzando la suite de tests ahora mismo…",
                          "Corriendo los tests — dame un momento…"],
    ("run", "docker"):   ["Voy a arrancar el contenedor — comprobando la configuración primero…",
                          "Iniciando el entorno Docker — dame un segundo…"],
    ("run", "deploy"):   ["Voy a iniciar el despliegue — revisando la configuración primero…",
                          "Lanzando el proceso de deploy — dame un momento…"],
    ("run", "code"):     ["Voy a ejecutar el script — comprobando el entorno primero…",
                          "Lanzando la ejecución — dame un momento…"],

    # UPDATE ──────────────────────────────────────────────────────────────────
    ("update", None):    ["Voy a actualizar eso ahora mismo — déjame revisar el estado actual…",
                          "Déjame leer el estado actual antes de modificar nada…",
                          "Voy a hacer los cambios — primero reviso para no cometer errores…",
                          "Abriendo los ficheros relevantes — me pongo a actualizarlo ya…"],
    ("update", "code"):  ["Voy a actualizar el código — déjame leer el estado actual primero…",
                          "Modificando la implementación — revisando antes de tocar nada…"],
    ("update", "docs"):  ["Voy a actualizar el documento — déjame leer el estado actual…",
                          "Modificando el documento — revisando el contenido antes de editar…"],
    ("update", "config"):["Voy a actualizar la configuración — revisando los valores actuales…",
                          "Modificando los parámetros de config — déjame leerlos primero…"],
    ("update", "deps"):  ["Voy a actualizar las dependencias — comprobando las versiones actuales…",
                          "Actualizando los paquetes — déjame revisar qué hay instalado…"],
    ("update", "deploy"):["Voy a actualizar la configuración de despliegue…"],
    ("update", "git"):   ["Voy a actualizar la rama — revisando el estado actual del repositorio…"],
    ("update", "iot"):   ["Voy a actualizar la configuración del dispositivo — déjame revisarla…"],
}


def _pick_preflight_phrase(msg: str, user_name: str = "") -> str:
    """Elige frase preflight según acción + dominio detectados (scoring multi-match).

    Detecta la ACCIÓN (fix/explain/search/…) y el DOMINIO (docker/git/tests/…) con
    mayor puntuación, elige la frase más específica disponible y opcionalmente añade
    un saludo con el nombre del usuario (~35%).
    """
    # Eliminar saludo inicial para que "hola, arregla el bug" no quede reducido a "hola"
    msg_clean  = _PF_GREETING_RE.sub("", msg.strip()).strip()
    msg_for_match = msg_clean.lower()

    # Si tras limpiar el saludo no queda intención real, usar genérico
    if len(msg_for_match) < 8:
        phrase = random.choice(_SINGLE_PREFLIGHT_GENERIC)
        if user_name and random.random() < 0.35:
            greeting = random.choice(_PREFLIGHT_USER_GREETINGS).format(user=user_name)
            phrase = f"{greeting} {phrase[0].lower()}{phrase[1:]}"
        return phrase

    # Puntuar todas las acciones (número de matches en el mensaje)
    action_scores: dict[str, int] = {}
    for key, pattern in _PF_ACTIONS:
        n = len(re.findall(pattern, msg_for_match))
        if n:
            action_scores[key] = n

    # Puntuar todos los dominios; en empate gana el primero de la lista (más específico)
    domain_scores: dict[str, int] = {}
    for key, pattern in _PF_DOMAINS:
        n = len(re.findall(pattern, msg_for_match))
        if n:
            domain_scores[key] = n

    best_action = max(action_scores, key=action_scores.__getitem__) if action_scores else None
    best_domain = max(domain_scores, key=domain_scores.__getitem__) if domain_scores else None

    # Lookup: (acción, dominio) → (acción, None) → genérico
    phrase = ""
    if best_action:
        candidates = _PF_PHRASES.get((best_action, best_domain)) or _PF_PHRASES.get((best_action, None))
        if candidates:
            phrase = random.choice(candidates)

    if not phrase:
        phrase = random.choice(_SINGLE_PREFLIGHT_GENERIC)

    if user_name and random.random() < 0.35:
        greeting = random.choice(_PREFLIGHT_USER_GREETINGS).format(user=user_name)
        phrase = f"{greeting} {phrase[0].lower()}{phrase[1:]}"

    return phrase


# Frases para el auto-split de fichero (cuando el agente cambia de fichero sin anunciarlo)
_FILE_SWITCH_PHRASES: list[str] = [
    "Now working on {file}",
    "Shifting focus to {file}",
    "Moving on to {file}",
    "Turning attention to {file}",
    "Pivoting to {file}",
    "Next up: {file}",
    "Over to {file} now",
    "Heading over to {file}",
    "Taking care of {file}",
    "Time to tend to {file}",
    "On to {file}",
    "Making changes in {file}",
    "Now touching {file}",
    "Switching over to {file}",
    "Jumping to {file}",
]


def _pick_file_switch_phrase(basename: str) -> str:
    """Elige una frase aleatoria para el auto-split de fichero."""
    return random.choice(_FILE_SWITCH_PHRASES).format(file=basename)


# Estilos _sfmt para el ◈ pulsante en modo Multitarea (se ciclan con fi)
_MULTI_ICON_STYLES = ["task-active", "status-phrase", "compact-bar", "status-bar-ok", "status-hint-near"]

# Bloqueo global de compactación: evita saturar el LLM con múltiples resúmenes simultáneos
_COMPACT_LOCK = threading.Lock()

_DONE_WORDS = [
    # Españolas reales
    "Cavilado", "Razonado", "Procesado", "Completado",
    # Inventadas tech
    "Cogitado", "Inferido", "Generado", "Decodificado",
    "Tokenizado", "Embedizado", "Neuroneado", "Transformado",
    "Vectorizado", "Sinaptizado", "Gradientado", "Sampliado",
    "Prompteado", "Atteneado", "Maquinado",
]

# Frases rotativas que aparecen en el spinner cuando el modelo lleva mucho tiempo
_NEAR_FINISH_PHRASES = [
    "casi sinaptizado…",
    "estamos sinaptizando…",
    "sinaptizando más…",
    "casi terminado…",
    "un momento más…",
    "inferenciando a fondo…",
    "tokenizando profundo…",
    "embedizando más…",
    "vectorizando…",
    "neuroneando duro…",
    "tokeninanzo más…",
    "casi decodificado…",
    "seguimos infiriendo…"
]


def _fmt_elapsed(secs: float) -> str:
    """Formatea segundos como '28s', '1m:32s' o '1h:02m:05s'."""
    if secs >= 3600:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = int(secs % 60)
        return f"{h}h:{m:02d}m:{s:02d}s"
    if secs >= 60:
        m = int(secs // 60)
        s = int(secs % 60)
        return f"{m}m:{s:02d}s"
    return f"{int(secs)}s"


def _fmt_tokens(n: int) -> str:
    """Formatea un conteo de tokens con sufijo K/M para legibilidad."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n // 1_000}K"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _rag_display(rag) -> str:
    """Genera la parte RAG del spinner: 'N rag' o 'N/M rag' si topK cortó resultados."""
    if rag is None:
        return ""
    hits      = getattr(rag, "last_hits", 0)
    available = getattr(rag, "last_available", 0)
    if hits <= 0:
        return ""
    if available > hits:
        # topK cortó más candidatos — mostrar cuántos había disponibles
        return f"  ·  ◈ {hits}/{available} rag"
    return f"  ·  ◈ {hits} rag"


def _is_complex_query(msg: str, min_chars: int) -> bool:
    """True si el mensaje sugiere una query compleja que se beneficia de más RAG.

    Criterios (OR):
    - Mensaje suficientemente largo (multi-paso, multi-fichero).
    - Menciona patrones de autoedición de OOCode (hooks, tools, loop, etc.).
    """
    if len(msg.strip()) >= min_chars:
        return True
    _OOCODE_KWS = (
        "hook", "tool", "loop", "agent", "mcp", "plugin",
        "registry", "config", "builtin", "oocode", "workspace_rag",
        "context_snippet", "permission", "slash", "repl",
    )
    lower = msg.lower()
    return sum(1 for kw in _OOCODE_KWS if kw in lower) >= 2


# Alias de nombres de herramientas: algunos modelos (qwen, deepseek, llama…)
# usan nombres distintos a los que registra OOCode, por sus datos de entrenamiento.
# Se normalizan aquí para evitar "herramienta no encontrada".
_TOOL_ALIASES: dict[str, str] = {
    "execute_bash":    "bash",
    "run_bash":        "bash",
    "run_code":        "bash",
    "execute_code":    "bash",
    "shell":           "bash",
    "terminal":        "bash",
    "execute_command": "bash",
    "create_file":     "write_file",
    "save_file":       "write_file",
    "modify_file":     "edit_file",
    "str_replace":     "edit_file",
    "str_replace_editor": "edit_file",
    "list_dir":        "ls_dir",
    "list_directory":  "ls_dir",
    "ls":              "ls_dir",
    "search_web":      "web_search",
    "fetch_url":       "web_fetch",
    "browse":          "web_fetch",
    # Aliases para búsqueda de ficheros
    "find":            "find_file",
    "search_files":    "find_file",
    "find_in_dir":     "find_file",
    # Aliases para búsqueda de código
    "grep":            "grep_code",
    "search_code":     "grep_code",
    "grep_search":     "grep_code",
    "code_search":     "grep_code",
    # Aliases para ejecución Python
    "run_python":      "python_exec",
    "execute_python":  "python_exec",
    "python":          "python_exec",
    # Aliases para wc/estadísticas
    "wc":              "file_stat",
    "stat":            "file_stat",
}


_IMG_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _load_images_b64(paths_or_b64: list[str]) -> list[str]:
    """Convierte rutas de imagen o strings raw en base64 para Ollama."""
    import base64
    result = []
    for item in paths_or_b64:
        item = item.strip()
        if not item:
            continue
        from pathlib import Path as _Path
        p = _Path(item).expanduser()
        if p.exists() and p.suffix.lower() in _IMG_EXTENSIONS:
            try:
                result.append(base64.b64encode(p.read_bytes()).decode())
            except Exception:
                pass
        elif len(item) > 100:
            # Asumir que ya es base64
            result.append(item)
    return result


def _ctx_bar(used: int, total: int, width: int = 10, plain: bool = False) -> str:
    """Barra de progreso del contexto con chars ▰▱ y color según nivel de llenado."""
    if total <= 0:
        return "─" * width
    pct = min(used / total, 1.0)
    filled = int(pct * width)
    bar = '▰' * filled + '▱' * (width - filled)
    if plain:
        return bar
    color = "green" if pct < 0.60 else "yellow" if pct < 0.85 else "bold red"
    return f"[{color}]{bar}[/{color}]"


_COMPACT_TEXT      = "↻ compactando"
_COMPACT_NEAR_TEXT = "↻ cerca compactación"


def _compact_hint(cpct: int, thresh_pct: int) -> str:
    if cpct >= thresh_pct:
        return f"  {_COMPACT_TEXT}"
    if cpct >= thresh_pct - 10:
        return f"  {_COMPACT_NEAR_TEXT}"
    return ""


def _pbar_thin_ratio(ratio: float, w: int = 20) -> str:
    """Igual que _pbar_thin pero con ratio 0.0–1.0 para animación."""
    filled = int(max(0.0, min(1.0, ratio)) * w)
    return "▰" * filled + "▱" * (w - filled)


def _sfmt(style: str, text: str) -> str:
    """Embede un segmento con estilo para el status window de la TUI.

    Usa marcadores de control \x01STYLE\x02TEXT\x03 que app.py:_parse_status_line()
    convierte en tuplas (class:STYLE, TEXT) para prompt_toolkit.
    Invisible en rutas no-TUI donde _status_cb es None.
    """
    return f"\x01{style}\x02{text}\x03"


def _bar_style(cpct: int, thresh_pct: int) -> str:
    """Devuelve el nombre de estilo para la barra de contexto según el porcentaje."""
    if cpct >= thresh_pct:
        return "status-bar-crit"
    if cpct >= thresh_pct - 10:
        return "status-bar-near"
    if cpct >= 60:
        return "status-bar-warn"
    return "status-bar-ok"


def _hint_styled(cpct: int, thresh_pct: int) -> str:
    """Devuelve el hint de compactación envuelto en _sfmt con el estilo adecuado."""
    if cpct >= thresh_pct:
        return _sfmt("status-hint-crit", f"  {_COMPACT_TEXT}")
    if cpct >= thresh_pct - 10:
        return _sfmt("status-hint-near", f"  {_COMPACT_NEAR_TEXT}")
    return ""


# Header mínimo: solo lo que no está en el mini-context del workspace
SYSTEM_HEADER = """\
Eres {agent_name}, asistente de programación local con Ollama.
Fecha: {today}
Directorio del proyecto (CWD): {project_dir}
IMPORTANTE: el código del proyecto está en el CWD. `~/.oocode/workspace/` contiene solo identidad/memoria del agente, NO código del proyecto.
"""

# ── Grupos de tools para filtrado de schemas ─────────────────────────────────
# Reduce el overhead de tokens (~11K) enviando solo los schemas relevantes.
# Estrategia conservadora: "core" + "lsp" + "memory" siempre presentes.
# Si no se detecta ningún grupo específico → se envían todos (modo seguro).
_TOOL_GROUPS: dict[str, frozenset] = {
    "core": frozenset({
        "read_file", "write_file", "edit_file", "edit_files",
        "grep_code", "multi_grep", "find_files", "find_file", "find_dir",
        "ls_dir", "ls_file", "code_outline", "read_sections", "code_search",
        "code_compare", "diff_files", "web_search", "web_fetch", "bash",
        "run_tests", "test_file", "mem_save", "workspace_remember",
        "plan_create", "task_done", "python_exec", "spawn_subagent",
        "analyze_codebase", "symbol_lookup", "affected_files",
        "lint_file", "lint_project", "regex_replace", "bulk_replace",
        "smart_replace", "patch_apply", "file_stat", "tree", "count_lines",
        "context_before_edit", "pre_edit_check", "read_files", "grep_file",
    }),
    "git": frozenset({
        "git_status", "git_diff", "git_log", "git_commit", "git_add",
        "git_push", "git_pull", "git_branch", "git_stash", "git_blame",
        "git_rebase", "git_tag", "git_cherry_pick", "git_worktree",
        "git_patch", "git_clone",
    }),
    "docker": frozenset({
        "docker_ps", "docker_logs", "docker_exec", "docker_inspect",
        "docker_images", "docker_stop", "docker_rm", "docker_cp",
        "compose_up", "compose_down", "compose_logs", "compose_exec",
        "compose_status", "compose_services", "compose_restart",
        "compose_build", "compose_config", "compose_run", "compose_version",
        "compose_stop", "compose_images", "compose_top", "compose_pull",
    }),
    "debug": frozenset({
        "strace_run", "gdb_run", "pdb_run", "valgrind_run",
        "make_run", "run_script", "format_code", "mypy_check",
    }),
    "system": frozenset({
        "systemctl_status", "systemctl_action", "journalctl",
        "net_interfaces", "net_connections", "net_ping", "net_dns",
        "disk_usage", "disk_inodes", "dir_size", "lsblk_info",
        "user_list", "user_info", "group_list", "who_logged",
        "ps_list", "top_snapshot", "kill_process",
        "fw_status", "fw_rules", "fw_allow", "fw_deny",
        "sys_info", "sys_updates", "sys_logs", "env_vars", "cron_list",
        "process_list",
    }),
    "packages": frozenset({
        "apt_update", "apt_upgrade", "apt_install", "apt_remove",
        "apt_search", "apt_info", "apt_list_installed",
        "dnf_update", "dnf_install", "dnf_remove", "dnf_search",
        "dnf_info", "rpm_query", "pip_tool", "npm_tool",
    }),
    "lsp": frozenset({
        "lsp_definition", "lsp_references", "lsp_hover", "lsp_symbols",
        "lsp_diagnostics", "lsp_completion", "lsp_rename", "lsp_format",
        "lsp_code_actions", "lsp_type_definition", "lsp_implementation",
        "lsp_workspace_symbols", "lsp_call_hierarchy", "lsp_restart",
    }),
    "data": frozenset({
        "json_format", "json_validate", "yaml_validate", "jq_query",
        "encode_base64", "decode_base64", "url_encode", "url_decode",
        "compute_hash", "to_base", "format_json", "escape_string",
        "hex_encode", "hex_decode", "calculate", "template_fill",
        "http_get", "port_check", "env_check", "hash_text", "get_datetime",
        "system_info",
    }),
    "fs": frozenset({
        "chmod_file", "chmod_dir", "chown_file", "chown_dir",
        "mv_file", "cp_file", "rm_file", "rm_dir", "mkdir_dir",
        "touch_file", "symlink_create", "readlink",
        "archive_extract", "archive_create", "archive_list",
    }),
    "memory": frozenset({
        "snippet_save", "snippet_get", "snippet_list", "snippet_delete",
        "vault_list", "vault_get", "todo_list", "todo_add", "todo_done",
        "todo_sync", "changelog_today", "changelog_session", "changelog_week",
        "clipboard_copy", "clipboard_paste",
        "index_workspace", "semantic_search",
        "extract_functions", "extract_classes", "extract_imports", "ast_summary",
        "build_symbol_index", "find_symbol", "list_symbols",
        "search_todos", "run_quick_check", "list_recent_files", "read_project_file",
    }),
    "office": frozenset({
        "email_list", "email_read", "email_send", "email_search",
        "doc_convert", "pdf_extract_text", "doc_word_count",
        "xlsx_read", "xlsx_write", "csv_analyze",
        "cal_list", "cal_add", "cal_search",
        "notes_list", "notes_search", "notes_save",
        "image_to_text", "contact_search", "markdown_to_html",
        "doc_read_template_fields", "doc_fill_template", "doc_list_templates",
        "doc_create_rfc", "xlsx_fill_range", "xlsx_append_row", "xlsx_create_report",
        "project_context_read", "project_init_office", "doc_project_save",
        "doc_read", "doc_update_section", "doc_version_bump",
        "cmdb_search", "cmdb_update", "asset_register_add",
    }),
    "security": frozenset({
        "nmap_scan", "port_scan", "ssl_check", "whois_lookup", "dns_enum",
        "http_headers", "nikto_scan", "gobuster_run", "curl_request",
        "encode_decode", "hash_crack", "jwt_decode", "cert_inspect",
        "log_analyze", "secret_scan", "cve_lookup",
        "xor_decode", "steganography_check", "base_convert", "hex_dump",
        "fw_audit", "ssh_key_audit", "sudoers_review", "file_integrity_check",
    }),
    "iot": frozenset({
        "tapo_list", "tapo_status", "tapo_on_off", "tapo_set",
        "blink_status", "blink_arm", "blink_snapshot", "blink_clips", "blink_verify",
        "alexa_devices", "alexa_speak", "alexa_command", "alexa_volume",
        "tuya_list", "tuya_status", "tuya_control",
        "ha_entities", "ha_state", "ha_control", "ha_automation",
        "mqtt_publish", "mqtt_subscribe",
        "esphome_list", "esphome_control",
        "iot_discover",
    }),
}

_TASK_KEYWORDS: dict[str, frozenset] = {
    "git": frozenset({
        "git", "commit", "branch", "merge", "rebase", "push", "pull",
        "stash", "blame", "tag", "cherry", "worktree", "repositorio", "repo",
    }),
    "docker": frozenset({
        "docker", "container", "compose", "imagen", "image", "dockerfile",
        "kubernetes", "k8s", "pod", "service", "volumen", "volume",
    }),
    "debug": frozenset({
        "debug", "debuggear", "gdb", "valgrind", "strace", "pdb",
        "breakpoint", "compilar", "compile", "build", "make", "cmake",
        "makefile",
    }),
    "system": frozenset({
        "systemctl", "service", "daemon", "proceso", "process", "red",
        "network", "firewall", "disco", "disk", "usuario", "user",
        "cpu", "cron", "journal", "syslog",
    }),
    "packages": frozenset({
        "instalar", "install", "apt", "dnf", "pip", "npm", "paquete",
        "package", "dependencia", "dependency", "upgrade", "actualizar",
        "requirements.txt", "package.json",
    }),
    "data": frozenset({
        "json", "yaml", "base64", "hash", "encode", "decode", "url",
        "hex", "template", "calcular", "calculate", "http", "api",
    }),
    "office": frozenset({
        "email", "correo", "mail", "imap", "smtp", "calendario",
        "calendar", "evento", "event", "reunión", "meeting",
        "documento", "document", "pdf", "excel", "xlsx", "csv",
        "hoja", "spreadsheet", "nota", "note", "notas", "notes",
        "contacto", "contact", "vcard", "vcf", "ocr", "pandoc",
        "word", "docx", "libreoffice", "markdown", "informe", "report",
        "rfc", "change request", "migración", "migration", "datacenter",
        "plantilla", "template", "formulario", "form", "informe it",
        "incidencia", "incident", "post-mortem", "rollback", "firewall",
        "servidor", "server", "infraestructura", "infrastructure",
        "cmdb", "inventario", "inventory", "activo", "asset",
        "business case", "resumen ejecutivo", "executive summary",
        "proyecto", "project", "version", "sección", "section",
        "oocode.md", "naming", "client", "cliente",
    }),
    "iot": frozenset({
        "tapo", "blink", "alexa", "echo", "tuya", "smart life", "smartlife",
        "esphome", "esp8266", "esp32", "mqtt", "zigbee", "z-wave",
        "luz", "light", "luces", "bombilla", "bulb", "enchufe", "plug",
        "camara", "camera", "cámara", "timbre", "doorbell", "ring",
        "casa inteligente", "smarthome", "home assistant", "homeassistant",
        "iot", "sensor", "interruptor", "switch", "ventilador", "fan",
        "termostato", "thermostat", "temperatura", "temperature",
        "automatización", "automation", "escena", "scene", "rutina",
    }),
    "security": frozenset({
        "pentest", "pentest", "hacking", "ctf", "seguridad", "security",
        "vulnerabilidad", "vulnerability", "cve", "exploit", "nmap",
        "nikto", "gobuster", "hashcat", "hash", "crack", "brute",
        "ssl", "tls", "certificado", "certificate", "whois", "dns",
        "puerto", "port", "scan", "escaneo", "firewall", "iptables",
        "jwt", "token", "cifrado", "encrypt", "decrypt", "crypto",
        "esteganografia", "steganography", "forense", "forensic",
        "log", "audit", "auditoria", "secret", "leak", "creds",
        "xor", "hex", "base64", "decode", "encode",
        "ssh", "sudoers", "integridad", "integrity",
    }),
    "fs": frozenset({
        "chmod", "chown", "mover", "move", "copiar", "copy", "eliminar",
        "delete", "symlink", "archive", "zip", "tar", "comprimir",
        "permisos", "permissions",
    }),
}

SYSTEM_RULES = """\
## HERRAMIENTAS — USA SIEMPRE LA COLUMNA ✅

| Necesidad | ✅ USA | ❌ NO |
|-----------|--------|-------|
| Leer fichero | `read_file(path, offset=N, limit=M)` | `bash cat/head/tail/sed -n` |
| Comparar ficheros | `diff_files(a, b)` | `bash diff` |
| Tests | `run_tests(path)` | `bash pytest / npm test` |
| Estructura fichero | `code_outline(path)` **— OBLIGATORIO antes de editar ficheros >1000 líneas** | `read_file` con múltiples offsets |
| Leer secciones | `read_sections(path, ['Clase.metodo', 'funcion'])` **— OBLIGATORIO para ficheros >1000 líneas** | `read_file(offset=N)` × N |
| Buscar en código | `grep_code` / `multi_grep(patterns=[…])` | `bash grep -rn` |
| Buscar símbolo | `lsp_workspace_symbols(q, path)` o `symbol_lookup` | `bash grep -rn` |
| Impacto de cambio | `affected_files(symbol, directory)` | `grep_code` + leer cada fichero |
| Callers/callees | `lsp_call_hierarchy(path, line)` | `bash grep -rn función` |
| Comparar código | `code_compare(a, b, symbol)` | grep+read×2 |
| grep con filtros | `grep_code(exclude_pattern=, count_only=, files_with_matches=, files_without_matches=)` | `bash grep|grep -v` |
| Buscar ficheros | `find_file` / `find_files` / `find_dir` | `bash find -name` |
| Listar directorio | `ls_dir` | `bash ls -la` |
| Info fichero | `file_stat` | `bash wc -l / stat` |
| Editar fichero | `edit_file` / `regex_replace` / `smart_replace` | `bash sed -i` |
| Editar múltiples | `bulk_replace` / `edit_files` | `bash sed -i` en bucle |
| Crear fichero | `write_file` | `bash cat > f <<'EOF'` |
| Python puntual | `python_exec(code=…, workdir=…)` | `bash python3 -c/<<'EOF'` |
| Índice símbolos | `find_symbol` / `list_symbols` / `extract_functions` | `bash ctags` |
| Git | `git_status/diff/add/commit/log/branch/stash` | `bash git …` |
| Docker/compose | `docker_ps/logs/exec/inspect` / `compose_up/down/logs/exec/…` | `bash docker …` |
| Copiar a container | `docker_cp(src=…, dst=…)` | `bash docker cp` |
| Compilar | `make_run` | `bash make/gcc/cc` |
| Linting | `lint_file` / `lint_project` | `bash ruff/mypy/…` |
| Paquetes Python | `pip_tool(action='install', packages=[…])` | `bash pip install` |
| Paquetes Node | `npm_tool(action='install', packages=[…])` | `bash npm install` |
| Debug | `strace_run` / `gdb_run` / `pdb_run` / `valgrind_run` | `bash strace/gdb` |

`bash` = ÚLTIMO RECURSO — solo si ninguna tool de la tabla lo cubre.

## Planificación autónoma — OBLIGATORIA para tareas complejas

**Para cualquier consulta que implique ≥3 pasos distintos** (exploración + implementación + verificación, o múltiples ficheros, o varias fases): ANTES de ejecutar NINGUNA herramienta, emite un plan detallado en texto para que el usuario pueda revisarlo.

**Formato del plan detallado (≥3 pasos o replanificación):**
```
Plan:
1. [Acción]: [qué harás exactamente] — ficheros: [rutas exactas] — tools: [tools que usarás]
2. [Acción]: [cambios concretos] — ficheros: [rutas] — riesgo: [si puede romper algo]
...
```
Si hay bloqueadores o decisiones no claras, añade al final:
`⚠ REQUIERE REVISIÓN: [descripción — decisión de diseño, dependencia faltante, riesgo alto]`
El sistema pausa y espera al usuario. Sin ese marcador, continúa automáticamente.
El usuario puede intervenir en cualquier momento con `/steer` o `/subagents steer`.

**Flujo de planificación con `plan_create`:**
1. Emite el plan en texto (formato arriba) — SIN llamar tools aún.
2. Llama `plan_create(tasks=["Tarea 1: …", "Tarea 2: …", ...], summary="Qué vas a hacer")`.
   ⚠ REGLA CRÍTICA: `plan_create` debe ser la ÚNICA herramienta en ese turno.
   NUNCA mezcles `plan_create` con herramientas de tarea (edit_file, read_file, etc.)
   en el mismo bloque de tool_calls. El panel visual se muestra limpio entre el
   resumen ⎿ del turno anterior y el siguiente ●.
3. En el siguiente mensaje anuncia "Tarea 1: descripción breve" como primera frase
   y llama las herramientas de esa tarea.
4. Llama `task_done()` al completar cada tarea — avanza el marcador ✔/◼/◻.
   ⚠ OBLIGATORIO: tras cada `spawn_subagent` o `explore` que complete una tarea,
   llama `task_done()` EN EL MISMO turno o en el inmediatamente siguiente.
5. Al terminar TODAS, di "He completado todas las tareas." como primera frase.

**Replanificación:** si durante la ejecución descubres que el plan original es incorrecto o incompleto:
1. Anuncia `"Replanificación:"` seguido del nuevo plan antes de cambiar de estrategia.
2. Llama `plan_create(tasks=[...])` para actualizar el panel visual con las nuevas tareas.
3. Llama `workspace_remember(note="Aprendizaje: [descripción del problema] → [solución adoptada]")` para documentar el problema en OOCODE.md y evitar repetirlo en futuras sesiones.
No cambies de estrategia silenciosamente.

**Alternativa ligera (solo texto, sin panel):** si la tarea tiene exactamente 2 pasos o es puramente exploratoria, una frase de anuncio basta.

**Evaluación de paralelismo — EVALÚA SIEMPRE antes de ejecutar:**
Cuando el usuario proporciona ≥2 tareas en una sola solicitud, evalúa su independencia:

| Situación | Estrategia |
|-----------|------------|
| Tareas sin dependencias entre sí | `spawn_subagent` × N en paralelo (cada una en su hilo) |
| Tareas en dominios distintos (código + docs + web) | `AgentTeam` con agentes especializados (`coding`, `home_office`, `webcrawler`) |
| Tarea principal + exploración intensiva | Subagente para exploración, hilo principal para implementación |
| Tareas con orden estricto (A→B→C) | Secuencial en el hilo principal, sin subagentes |
| Análisis read-only de múltiples ficheros | `spawn_subagent(explore=True)` × N simultáneos |

**Cuándo usar subagente (`spawn_subagent`):**
- Proyecto muy grande: exploración exhaustiva de codebase mientras el hilo principal prepara el plan.
- Tareas completamente independientes que no comparten estado (ej. explorar fichero A y explorar fichero B simultáneamente).
- Análisis read-only intensivo: `spawn_subagent(task="explorar…", explore=True)`.
- Si hay ≥3 tareas independientes, considera lanzar un equipo: `AgentTeam` con `spawn_background` × N.

**Cuándo NO usar subagente:** edición de ficheros, tests, implementación — hazlo directamente con las tools.

## Flujo de trabajo

1. **Analiza y planifica** — si la tarea es compleja (≥3 pasos), crea un plan numerado primero.
2. **Explora PRIMERO** — `read_file` + `grep_code` + `lsp_symbols` antes de editar.
   - Localiza ficheros con `find_files(directory=CWD, name="*.ext")` o `ls_dir(CWD)`.
   - NUNCA uses `edit_file` sin haber leído el fichero en este turno (el agente lo bloqueará).
   - Ante errores HTTP/API/herramienta desconocida → `web_search` primero.
3. **Implementa** — `edit_file` / `write_file` / `bulk_replace`.
   - **OBLIGATORIO antes de llamar a edit_file/smart_replace/write_file:** emite una frase corta que mencione el fichero concreto: `"Corrigiendo X en Y.c:"` o `"Actualizando Y.c — razón:"`. Esto aparece como cabecera `●` en el terminal.
   - Tras cada edición, describe en 1-2 frases qué cambió y qué efecto tiene.
4. **Verifica** — `run_tests` / `lint_file` / `lsp_diagnostics` / `make_run`. Reporta el resultado: "N tests pasados, M fallidos" o lista de errores con `ruta:línea:mensaje`.
5. **Finaliza y reporta** — informe estructurado: qué se hizo, ficheros cambiados (rutas exactas), resultado de tests/lint, advertencias, próximos pasos. Llama `mem_save` con hallazgos no obvios; `workspace_remember` para instrucciones persistentes.

## Reglas generales
- **Comunicación con el usuario (EL USUARIO NO VE LAS TOOLS NI SUS RESULTADOS, SOLO TU TEXTO):**
  - **Antes de actuar:** anuncia brevemente qué vas a hacer (1 frase para simple, plan detallado para ≥3 pasos).
  - **Tarea compleja (≥3 pasos) o replanificación:** emite un plan detallado en texto antes de la primera tool (ver "Planificación autónoma"). El sistema continúa automáticamente; el usuario puede redirigir con `/steer`.
  - **Bloqueo no resoluble:** añade "⚠ REQUIERE REVISIÓN: [descripción]" al plan — el sistema pausa y espera al usuario antes de continuar.
  - **Tras exploración:** describe qué encontraste — rutas de ficheros, funciones relevantes, causas identificadas, fragmentos de código con `ruta:línea`. No digas "encontré algo" sin mostrar el qué.
  - **Tras implementación:** describe el cambio — qué función/clase se modificó, qué hacía antes y qué hace ahora. Un antes/después breve si no es obvio.
  - **Al finalizar:** informe estructurado — qué se hizo, ficheros modificados (rutas exactas), resultado de tests (N pasados / M fallidos), advertencias activas, próximos pasos si procede.
- **Ficheros >1000 líneas** (cualquier lenguaje o formato): SIEMPRE empieza con `code_outline(path)` para ver la estructura y `read_sections(path, ['NombreFuncion'])` para leer solo la sección relevante. NUNCA `read_file` sin offset en ficheros grandes. Antes de editar: `read_sections` → `grep_code` para verificar old_string → `edit_file`.
- NUNCA inventes rutas, código ni resultados. NUNCA declares ✅ sin verificar con tools.
- **Verbosidad adaptada al contexto** — sin relleno ("Entendido, voy a...", "Como puedes ver...") pero SÍ con contenido cuando el contexto lo exige:
  - **Hallazgos y análisis:** detallado — fragmentos de código con `ruta:línea`, lista de ítems ordenada por severidad, causa raíz explicada. El usuario no ve los ficheros: necesita ver el contexto.
  - **Después de implementar:** describe qué cambió (fichero + función + qué y por qué). Muestra un antes/después si el cambio no es obvio.
  - **Informe de finalización:** resumen estructurado — qué se hizo, qué ficheros cambiaron (rutas exactas), resultado de tests (N pasados / M fallidos), advertencias, próximos pasos si procede.
  - Código en bloques ```language. Errores y logs en ```text.
- **El CWD es el directorio del proyecto.** Usa rutas absolutas al CWD para leer/editar código.
  `~/.oocode/workspace/` = identidad del agente (NO código del proyecto). NO busques código ahí.
- **`web_search` — escala antes de repetir estrategias que no funcionan:**
  - Error HTTP/API/import desconocido → busca el error exacto + versión + plataforma ANTES de probar nada más.
  - Símbolo, función o API no encontrada tras ≥3 búsquedas vacías en el proyecto → puede que el nombre sea externo o haya cambiado.
  - ≥3 estrategias distintas fallidas con el mismo problema → busca antes de seguir adivinando.
- **`compose_down -v` DESTRUYE VOLÚMENES (base de datos, datos persistentes)** — PROHIBIDO salvo que el usuario lo pida explícitamente. Usa `compose_stop` o `compose_restart` en su lugar.
- **Escribir ficheros DENTRO de un contenedor Docker:** `write_file` en el host → `docker_cp(src='~/.oocode/tmp/file', dst='CONTAINER:/ruta/')`. Para contenido pequeño: `docker_exec(command='printf \\'texto\\' > /ruta/fichero')`.
- **write_file Permission denied (Errno 13):** la ruta pertenece a un volumen Docker o directorio de sistema. Escribe en `~/.oocode/tmp/` y usa `docker_cp` para moverlo al contenedor.
- Si bash devuelve error: diagnostica antes de reintentar (`ls_dir(path)`/`find_files(directory=path)`); no repitas el mismo comando.
- **PROHIBIDO** (el agente bloqueará): ficheros .py/.sh temporales, heredocs bash, `bash git/grep/find/ls/cat/sed -i/make/pytest/docker exec/docker compose/docker cp`.
- Anti-bucle: si una tool falla 2 veces con el mismo argumento, CAMBIA estrategia.
- Antes de `regex_replace`: verifica con `grep_code` que el patrón existe exactamente.
- Si `regex_replace` falla: usa `read_file` para ver el texto REAL → `edit_file` con literal exacto.
- En planes multi-tarea: anuncia cada tarea con "Tarea N: descripción breve" al empezarla. Cuando hayas completado TODAS las tareas usando tools, tu primera frase debe ser "He completado todas las tareas." — el sistema lo detecta y detiene la ejecución.
- **PROHIBIDO — nunca emitas "He completado todas las tareas." si**: (1) hay tareas ◻ pendientes en el panel, (2) en la misma respuesta mencionas "Próximo paso", "fase pendiente", `(PENDIENTE)`, "🔄 en curso" u otro trabajo futuro, (3) hay errores sin resolver marcados con `❌`, `REQUIERE CORRECCIÓN` o `(PENDIENTE)`, (4) la tarea activa requería editar/crear ficheros y NO llamaste `edit_file`/`write_file`/`bulk_replace`. El sistema detecta la contradicción y fuerza la continuación.
- Cuando encuentres un error que no puedes resolver en este turno (indicado con `❌`, `REQUIERE CORRECCIÓN`, `(PENDIENTE)` u otro marcador similar): llama `workspace_remember(note="Aprendizaje: [descripción del problema encontrado] → [qué queda pendiente o cómo abordarlo]")` para documentarlo en OOCODE.md, luego explica al usuario qué falta — en lugar de declarar la tarea completada.
- **ANTES de "He completado todas las tareas."** — si la tarea modificó código (`edit_file`/`write_file`/`bulk_replace`/`patch_apply`), DEBES llamar `run_tests` o `test_file` en este mismo turno. No puedes declarar completado sin haber ejecutado los tests. Excepción única: tareas puramente de lectura/análisis/documentación sin ningún cambio de código.
- Nunca emitas una respuesta vacía. Tras recibir resultados de tools, continúa directamente con las siguientes tools o responde al usuario. Si ya has completado todo, di "He completado todas las tareas."

## LSP — usar si hay servidor activo

| Tarea | Tool |
|-------|------|
| Funciones/structs del fichero | `lsp_symbols(path)` |
| Buscar símbolo en proyecto | `lsp_workspace_symbols(query, path)` |
| Callers/callees | `lsp_call_hierarchy(path, line)` |
| Tipo de variable | `lsp_hover(path, line, col)` |
| Errores/warnings | `lsp_diagnostics(path)` |
| Renombrar en todo el código | `lsp_rename(path, line, col, new_name, apply=true)` |

**C/C++ (clangd):** `lsp_symbols` → `lsp_hover` → `lsp_call_hierarchy` → `edit_file` → `lsp_diagnostics` → `make_run`
**Python:** `lsp_diagnostics` tras editar · `lsp_references` antes de renombrar
**JS/TS/Shell/Perl/YAML:** `lsp_diagnostics` tras cada edición

## Instrucciones y memoria
- OOCODE.md + "## Instrucciones del proyecto" tienen máxima prioridad — SIEMPRE respetadas.
- Instrucciones persistentes del usuario → `workspace_remember(note)`.
- Hallazgos importantes (arquitectura, decisiones, bugs) → `mem_save(snake_case_name, content)`.
"""

_SUBAGENT_COLORS = ["cyan", "blue", "magenta", "green", "yellow", "bright_cyan"]

# Verbos en gerundio para el ● live del live block (mientras ejecuta la tool)
_TOOL_LIVE_VERBS: dict[str, str] = {
    "code_search":   "Searching for",
    "grep_code":     "Searching for",
    "grep_file":     "Searching for",
    "multi_grep":    "Searching for",
    "find_file":     "Finding",
    "find_files":    "Finding",
    "read_file":     "Reading",
    "read_files":    "Reading",
    "read_sections": "Reading",
    "ls_dir":        "Listing",
    "file_stat":     "Checking",
    "write_file":    "Writing",
    "edit_file":     "Editing",
    "edit_files":    "Editing",
    "regex_replace": "Replacing in",
    "smart_replace": "Replacing in",
    "bulk_replace":  "Replacing in",
    "patch_apply":   "Applying to",
    "bash":          "Running",
    "python_exec":   "Executing",
    "spawn_subagent":"Spawning",
}


def _make_tool_preview(name: str, args: dict) -> list[str]:
    """Returns 1-4 context lines to show in the live block preview while a tool runs.

    These are shown under '|  ◐ tool:' and hidden when the tool completes.
    """
    if name == "bash":
        cmd = (args.get("command") or "").strip()
        lines = cmd.splitlines()
        return [f"$ {l}" for l in lines[:4]] if lines else []
    if name == "read_file":
        p   = args.get("path", "")
        off = args.get("offset")
        lim = args.get("limit")
        if not p:
            return []
        suffix = ""
        if off:
            suffix += f":{off}"
        if lim:
            suffix += f"+{lim}"
        return [f"{p}{suffix}"]
    if name == "read_files":
        ps = args.get("paths", [])
        if isinstance(ps, list):
            return [str(x) for x in ps[:4]]
        return [str(ps)] if ps else []
    if name in ("grep_code", "grep_file"):
        pat  = args.get("pattern", "")
        d    = args.get("directory", args.get("path", ""))
        base = d.rsplit("/", 1)[-1] if d else d
        if pat and base:
            return [f'"{pat}"  in {base}']
        return [f'"{pat}"'] if pat else []
    if name == "multi_grep":
        pats = args.get("patterns", [])
        if isinstance(pats, list):
            return [f'"{p}"' for p in pats[:3]]
        return [str(pats)] if pats else []
    if name == "code_search":
        q = args.get("query", args.get("pattern", ""))
        return [f'"{q}"'] if q else []
    if name in ("find_file", "find_files", "find_dir"):
        n = args.get("name") or args.get("glob", "") or args.get("extension", "")
        d = args.get("directory", "")
        base = d.rsplit("/", 1)[-1] if d else d
        if n and base:
            return [f"{n}  in {base}"]
        return [str(n)] if n else []
    if name == "python_exec":
        code  = (args.get("code") or "").strip()
        lines = code.splitlines()
        return lines[:4] if lines else []
    if name in ("lsp_diagnostics", "lint_file", "mypy_check", "lsp_hover", "lsp_references"):
        p = args.get("path", "")
        return [p] if p else []
    if name in ("git_diff", "git_log", "git_add", "git_commit"):
        msg = args.get("message") or args.get("path") or args.get("files", "")
        if isinstance(msg, list):
            msg = ", ".join(str(m) for m in msg)
        return [str(msg)] if msg else []
    return []


def _make_compact_summary(blocks: list[tuple[str, dict, str, bool]]) -> str:
    """Genera resumen compacto estilo Claude Code para un batch de tool calls TUI con metadata.

    Ejemplo: "Searched for 3 patterns, read 2 files, wrote 1 file (ctrl+o to expand)"
    Para ediciones únicas: "Updated agent/loop.py"  (nombre de fichero, no contador genérico)
    Metadata: timestamp, tokens usados, estado LSP
    """
    import os
    # Mapeo tool → (verbo, unidad_singular, unidad_plural)
    _VERBS: dict[str, tuple[str, str, str]] = {
        # búsqueda
        "code_search":       ("Searched for", "pattern", "patterns"),
        "grep_code":         ("Searched for", "pattern", "patterns"),
        "grep_file":         ("Searched for", "pattern", "patterns"),
        "multi_grep":        ("Searched for", "pattern", "patterns"),
        "find_file":         ("Found", "file", "files"),
        "find_files":        ("Found", "file", "files"),
        "find_dir":          ("Found", "directory", "directories"),
        "symbol_lookup":     ("Looked up", "symbol", "symbols"),
        "code_compare":      ("Compared", "file", "files"),
        # lectura
        "read_file":         ("Read", "file", "files"),
        "read_files":        ("Read", "file", "files"),
        "ls_dir":            ("Listed", "directory", "directories"),
        "file_stat":         ("Checked", "file", "files"),
        # lectura extendida
        "read_sections":     ("Read", "section", "sections"),
        "code_outline":      ("Outlined", "file", "files"),
        "diff_files":        ("Compared", "file", "files"),
        "tree":              ("Listed", "tree", "trees"),
        "count_lines":       ("Counted", "file", "files"),
        # escritura
        "write_file":        ("Wrote", "file", "files"),
        "edit_file":         ("Updated", "file", "files"),
        "edit_files":        ("Updated", "file", "files"),
        "smart_replace":     ("Replaced", "pattern", "patterns"),
        "regex_replace":     ("Replaced", "pattern", "patterns"),
        "bulk_replace":      ("Replaced", "pattern", "patterns"),
        "patch_apply":       ("Applied", "patch", "patches"),
        # bash / ejecución
        "bash":              ("Ran", "command", "commands"),
        "run_script":        ("Ran", "script", "scripts"),
        "python_exec":       ("Executed", "script", "scripts"),
        # tests y lint
        "run_tests":         ("Ran", "test", "tests"),
        "test_file":         ("Ran", "test", "tests"),
        "lint_file":         ("Linted", "file", "files"),
        "lint_project":      ("Linted", "project", "projects"),
        # análisis / build
        "analyze_codebase":  ("Analyzed", "codebase", "codebases"),
        "affected_files":    ("Checked", "symbol", "symbols"),
        "make_run":          ("Built", "target", "targets"),
        "format_code":       ("Formatted", "file", "files"),
        "mypy_check":        ("TypeChecked", "file", "files"),
        "extract_functions": ("Extracted", "function", "functions"),
        "extract_classes":   ("Extracted", "class", "classes"),
        # git
        "git_status":        ("Checked", "git status", "git status"),
        "git_diff":          ("Diffed", "file", "files"),
        "git_log":           ("Listed", "commit", "commits"),
        "git_branch":        ("Listed", "branch", "branches"),
        "git_stash":         ("Stashed", "change", "changes"),
        "git_add":           ("Staged", "file", "files"),
        "git_commit":        ("Committed", "change", "changes"),
        "git_push":          ("Pushed", "commit", "commits"),
        "git_pull":          ("Pulled", "commit", "commits"),
        "git_blame":         ("Blamed", "file", "files"),
        # docker
        "docker_ps":         ("Listed", "container", "containers"),
        "docker_logs":       ("Read", "log", "logs"),
        "docker_exec":       ("Ran", "command", "commands"),
        "docker_inspect":    ("Inspected", "container", "containers"),
        # debug
        "strace_run":        ("Traced", "process", "processes"),
        "gdb_run":           ("Debugged", "program", "programs"),
        "valgrind_run":      ("Analyzed", "program", "programs"),
        # paquetes
        "pip_tool":          ("Ran", "pip command", "pip commands"),
        "npm_tool":          ("Ran", "npm command", "npm commands"),
        # LSP
        "lsp_definition":    ("Resolved", "definition", "definitions"),
        "lsp_references":    ("Found", "reference", "references"),
        "lsp_hover":         ("Checked", "hover", "hovers"),
        "lsp_symbols":       ("Listed", "symbol", "symbols"),
        "lsp_diagnostics":   ("Checked", "diagnostic", "diagnostics"),
        "lsp_completion":    ("Completed", "symbol", "symbols"),
        "lsp_rename":        ("Renamed", "symbol", "symbols"),
        "lsp_format":        ("Formatted", "file", "files"),
        "lsp_workspace_symbols": ("Searched for", "symbol", "symbols"),
        "lsp_call_hierarchy":("Built", "call tree", "call trees"),
        "lsp_type_definition":("Resolved", "type", "types"),
        "lsp_implementation":("Found", "implementation", "implementations"),
        # memoria
        "mem_save":          ("Saved", "memory", "memories"),
        "mem_search":        ("Searched for", "memory", "memories"),
        "mem_list":          ("Listed", "memory", "memories"),
        # MCP / misc
        "spawn_subagent":    ("Spawned", "subagent", "subagents"),
        "explore":           ("Explored", "path", "paths"),
    }

    # Herramientas que producen diff contable (+N -M líneas)
    _EDIT_TOOLS = frozenset({"edit_file", "edit_files", "write_file"})
    _REPLACE_TOOLS = frozenset({"regex_replace", "smart_replace", "bulk_replace", "patch_apply"})

    from collections import Counter
    import difflib

    counts: Counter = Counter()
    # Track ficheros editados/leídos y comandos bash para mostrar en resumen
    edited_files: list[str] = []
    read_files:   list[str] = []
    bash_cmds:    list[str] = []
    total_added = total_removed = 0
    _READ_TOOLS = frozenset({"read_file", "read_files"})
    _BASH_TOOLS = frozenset({"bash", "run_script"})

    for name, args, result, allowed in blocks:
        if not allowed:
            counts[("Denied", "call", "calls")] += 1
            continue
        # Nombre base para MCP tools (mcp_oocode_assistant_edit_file → edit_file)
        base_name = name
        for _write in ("_edit_file", "_edit_files", "_write_file",
                       "_regex_replace", "_smart_replace", "_bulk_replace", "_patch_apply"):
            if name.startswith("mcp_") and name.endswith(_write):
                base_name = _write[1:]
                break

        verb_info = _VERBS.get(base_name, _VERBS.get(name, ("Used", "tool", "tools")))
        counts[verb_info] += 1

        _res_str = str(result)
        _is_err  = _res_str.startswith("Error") or _res_str.startswith("⛔")

        # Ediciones: contar líneas y recoger nombre de fichero
        if base_name in _EDIT_TOOLS and not _is_err:
            path = args.get("path") or args.get("file_path", "")
            if path:
                edited_files.append(os.path.basename(str(path)))
            old_s = args.get("old_string", "")
            new_s = args.get("new_string", "")
            if old_s or new_s:
                diff = list(difflib.unified_diff(
                    old_s.splitlines(), new_s.splitlines(), n=0
                ))
                total_added   += sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
                total_removed += sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

        # Lecturas: recoger nombre de fichero para mostrar en resumen
        elif base_name in _READ_TOOLS and not _is_err:
            path = args.get("path") or args.get("file_path", "")
            if path:
                read_files.append(os.path.basename(str(path)))

        # Bash: recoger comando abreviado
        elif base_name in _BASH_TOOLS and not _is_err:
            cmd = (args.get("command", "") or args.get("script", "")).strip()
            if cmd:
                bash_cmds.append(cmd[:80])

    parts: list[str] = []
    # Construir partes del resumen
    for (verb, sing, plur), n in counts.most_common():
        # Edición única: mostrar nombre del fichero
        if verb == "Updated" and n == 1 and len(edited_files) == 1:
            entry = f"Updated {edited_files[0]}"
            if total_added or total_removed:
                entry += f" (+{total_added} -{total_removed})"
            parts.append(entry)
        elif verb == "Updated" and n > 1 and edited_files:
            entry = f"Updated {n} files"
            if total_added or total_removed:
                entry += f" (+{total_added} -{total_removed})"
            parts.append(entry)
        # Lecturas: mostrar nombres de ficheros leídos
        elif verb == "Read" and n >= 1 and read_files:
            shown = read_files[:3]
            extra = n - len(shown)
            flist = ", ".join(shown) + (f" +{extra}" if extra > 0 else "")
            parts.append(f"Read {n} file{'s' if n != 1 else ''} ({flist})")
        # Bash: mostrar comando abreviado
        elif verb == "Ran" and n >= 1 and bash_cmds:
            shown_cmd = bash_cmds[0]
            if len(shown_cmd) == 32:
                shown_cmd += "…"
            extra = n - 1
            suffix = f" +{extra} more" if extra > 0 else ""
            parts.append(f"Ran {n} command{'s' if n != 1 else ''} (`{shown_cmd}`{suffix})")
        else:
            unit = sing if n == 1 else plur
            parts.append(f"{verb} {n} {unit}")

    if not parts:
        return "(ctrl+o to expand)"
    return ", ".join(parts) + " (ctrl+o to expand)"





