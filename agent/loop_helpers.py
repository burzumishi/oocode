"""Helpers, constantes y funciones puras del bucle del agente.

Extraído de agent/loop.py para mantener loop.py manejable.
Importar desde aquí directamente o a través de agent.loop (re-exporta todo).
"""
import os
import re
import random
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

# Tools de orquestación de subagentes/equipos: tienen concurrencia interna propia
# (spawn_background + join) y rendering especial que solo funciona en la rama
# secuencial del dispatch (header ● [emoji nombre]: tarea, streaming │, spinner de
# color del subagente). NUNCA deben ejecutarse dentro del ThreadPoolExecutor
# paralelo: si se batchean con otras tools su output queda "encerrado" en el bloque
# anterior y colisiona en el live block del padre. Su presencia fuerza modo
# secuencial en _turn_dispatch_tools.
_ORCHESTRATION_TOOLS = frozenset({
    "spawn_subagent", "spawn_fanout", "create_team", "run_team", "explore",
})

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

# ── Patrón de ARRANQUE EN FRÍO (saludo/reinicio a mitad de tarea) ────────────
# Detecta cuando el agente, tras haber usado tools (p.ej. descargar un PDF),
# responde como si la conversación empezara de cero ("¡Hola! Veo que has
# compartido…", "¿en qué puedo ayudarte?"). Se usa para reorientarlo a la tarea.
_COLD_START_RE = re.compile(
    r'(^\s*(¡?\s*hola\b|hello\b|hi\b|buenas\b|saludos\b))'
    r'|veo que (?:has|me has) (?:compartido|enviado|subido|adjuntado|pasado)'
    r'|¿\s*en qu[eé] (?:puedo|te puedo) (?:ayud|asist)'
    r'|¿\s*qu[eé] (?:necesitas|deseas|quieres|te gustar[ií]a)'
    r'|¿\s*c[oó]mo (?:puedo|te) (?:ayud|asist)',
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
    ("docs",     r'\b(plantilla|template|documento|word\b|excel\b|pdf\b|informe|report\b|presentaci[oó]n|docx|xlsx|pptx|word\b|hoja\s+de\s+c[aá]lculo)\b'),
    ("web",      r'\b(web\b|crawl|crawler|scrap\w*|fetch|url\b|p[aá]gina\s+web|noticias?|feed\b|rss\b|sitio\s+web|navega\w*|investig\w*|research)\b'),
    ("data",     r'\b(datos|data\b|sql\b|consulta\s+sql|base\s+de\s+datos|database|csv\b|m[eé]trica|estad[ií]stic\w*|dataset|tabla\s+de\s+datos)\b'),
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
    ("explain", None):   ["Déjame revisarlo para explicarte esto en detalle…",
                          "Voy a analizarlo bien para responderte con la mayor precisión…",
                          "Ahora mismo lo estudio para explicarte cómo funciona…",
                          "Reuniendo el contexto — quiero entenderlo bien antes de explicarte…"],
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
    ("search", None):    ["Voy a rastrear eso — enseguida te digo lo que encuentro…",
                          "Buscando ahora mismo — te cuento todo lo que encuentre…",
                          "Déjame explorar — ahora mismo te digo dónde está…",
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

    # WEB / investigación ───────────────────────────────────────────────────────
    ("search", "web"):   ["Voy a rastrear eso en la web — enseguida te traigo lo que encuentre…",
                          "Buscando fuentes online — te resumo lo relevante en un momento…"],
    ("create", "web"):   ["Voy a recopilar la información de la web y estructurarla — dame un momento…",
                          "Preparando la extracción — me pongo a recoger los datos ya…"],
    ("explain", "web"):  ["Voy a consultar las fuentes para explicarte esto con precisión…"],
    ("review", "web"):   ["Voy a revisar las fuentes y contrastarlas — dame un momento…"],

    # DATA / análisis ─────────────────────────────────────────────────────────
    ("search", "data"):  ["Voy a consultar los datos — enseguida te digo qué encuentro…"],
    ("explain", "data"): ["Voy a explorar los datos y su esquema para explicártelo…"],
    ("review", "data"):  ["Voy a analizar los datos en detalle — dame un momento…",
                          "Revisando el conjunto de datos — te traigo las cifras enseguida…"],
    ("create", "data"):  ["Voy a preparar la consulta/transformación — déjame ver el esquema primero…"],

    # OFICINA / documentos (dominio 'docs') ──────────────────────────────────
    ("explain", "docs"): ["Voy a revisar el documento para explicarte su contenido…"],
    ("review", "docs"):  ["Voy a revisar el documento en detalle — dame un momento…",
                          "Inspeccionando el documento — déjame leerlo entero primero…"],
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

# H: Semáforo de compactación — permite hasta 2 compactaciones simultáneas.
# Con Lock() todos los subagentes se serializaban; Semaphore(2) permite que dos
# avancen en paralelo mientras los demás esperan, sin saturar el LLM con N llamadas.
_COMPACT_LOCK = threading.Semaphore(2)

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


# Header mínimo: SOLO datos factuales. La identidad y el rol del agente los
# aporta el bloque "## Agente" del workspace (resumen de IDENTITY.md/SOUL.md).
# No hardcodear aquí ningún rol ("asistente de programación", etc.).
SYSTEM_HEADER = """\
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
        # Email / calendario / notas / contactos
        "email_list", "email_read", "email_send", "email_search",
        "cal_list", "cal_add", "cal_search",
        "notes_list", "notes_search", "notes_save",
        "image_to_text", "contact_search",
        # Word — creación y edición nativa O365
        "doc_create", "doc_create_from_template", "doc_create_rfc",
        "doc_add_content_block", "doc_apply_style", "doc_set_table_style",
        "doc_set_page_layout", "doc_add_header_footer", "doc_add_toc",
        "set_paragraph_format", "apply_document_theme", "doc_embed_image",
        "insert_chart", "doc_read", "doc_update_section", "doc_version_bump",
        "doc_convert", "pdf_extract_text", "doc_word_count", "doc_compare",
        "doc_extract_metadata",
        # Plantillas corporativas
        "doc_read_template_fields", "doc_fill_template",
        "doc_fill_corporate_template", "doc_list_templates",
        # Excel nativo
        "xlsx_read", "xlsx_write", "xlsx_fill_range", "xlsx_append_row",
        "xlsx_create_report", "xlsx_create_table", "xlsx_insert_chart",
        "xlsx_apply_conditional_format", "apply_cell_formatting",
        "xlsx_freeze_panes", "xlsx_set_column_width", "xlsx_merge_cells",
        "xlsx_add_sheet", "xlsx_protect_sheet", "xlsx_add_data_validation",
        "csv_analyze",
        # PowerPoint nativo
        "pptx_create", "pptx_create_from_template", "pptx_add_slide",
        "pptx_insert_chart", "pptx_add_notes", "pptx_set_background", "pptx_read",
        # Proyecto / CMDB / activos
        "project_context_read", "project_init_office", "doc_project_save",
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
| Leer fichero | `read_file(path, offset=N, limit=M)` | `bash cat/head/tail` |
| Fichero >__LARGE_FILE_LINES__ líneas | `code_outline(path)` luego `read_sections(path, ['fn'])` | `read_file` sin offset |
| Comparar ficheros | `diff_files(a, b)` | `bash diff` |
| Tests | `run_tests(path)` | `bash pytest/npm test` |
| Buscar código | `grep_code` / `multi_grep(patterns=[…])` | `bash grep -rn` |
| Buscar símbolo | `lsp_workspace_symbols(q,path)` o `symbol_lookup` | `bash grep -rn` |
| Impacto cambio | `affected_files(symbol, dir)` | grep+leer×N |
| Callers/callees | `lsp_call_hierarchy(path, line)` | `bash grep -rn fn` |
| Comparar código | `code_compare(a, b, symbol)` | grep+read×2 |
| Buscar ficheros | `find_file` / `find_files` / `find_dir` | `bash find` |
| Listar dir | `ls_dir` | `bash ls -la` |
| Editar fichero | `edit_file` / `regex_replace` / `smart_replace` | `bash sed -i` |
| Editar varios | `bulk_replace` / `edit_files` | sed en bucle |
| Crear fichero | `write_file` | `bash cat > f <<'EOF'` |
| Python puntual | `python_exec(code=…)` | `bash python3 -c` |
| Git | `git_status/diff/add/commit/log/branch/stash` | `bash git …` |
| Docker/compose | `docker_ps/logs/exec/inspect` · `compose_up/down/logs/exec/…` | `bash docker …` |
| Compilar/linting | `make_run` · `lint_file` · `lint_project` | `bash make/ruff` |
| Paquetes | `pip_tool(action='install',packages=[…])` · `npm_tool(…)` | `bash pip/npm` |
| Debug | `strace_run` / `gdb_run` / `pdb_run` / `valgrind_run` | `bash strace/gdb` |

`bash` = ÚLTIMO RECURSO — solo si ninguna tool anterior lo cubre.

## Planificación

Clasifica antes de actuar:

| Nivel | Cuándo | Cómo |
|-------|--------|------|
| 1 — Directo | ≤2 ficheros, acción predecible | 1 frase + tools |
| 2 — Pasos | 3-5 pasos secuenciales, mismo dominio | Lista en texto antes de la 1ª tool |
| 3 — Panel | ≥3 módulos no relacionados · scope indefinido · refactor transversal · >1 auto-continue | Plan en texto → `plan_create` → `task_done()` por tarea |
| 4 — Paralelo | ≥2 partes independientes (Nivel 3) | `spawn_fanout` (mismo dominio) · `spawn_subagent` (tareas separadas) · `create_team` (dominios distintos) |

**Nivel 3 — flujo `plan_create`:**
1. Emite plan en texto (ANTES de tools): `Plan:\n1. [Acción] — ficheros: [rutas] — tools: [tools]\n2. …`
2. Llama `plan_create(tasks=[…], summary="…")` — ÚNICA tool del turno.
3. Por cada tarea: anuncia "Tarea N: descripción" → tools → `task_done()`.
4. Al terminar TODAS: primera frase = `"__DONE_PHRASE__"`
- Bloqueo: emite `⚠ REQUIERE REVISIÓN: [descripción]` → el sistema pausa.
- Replanificación: anuncia `"Replanificación:"` → `plan_create([…])` → `workspace_remember(note="Aprendizaje: …")`. No cambies de estrategia silenciosamente.

**Nivel 4 — cuándo usar cada herramienta:**
- `spawn_fanout`: mismo dominio, N chunks independientes del mismo agente (1 llamada → N en paralelo real).
- `spawn_subagent`: UNA tarea aislada con estado separado. Llámalo SOLO en su propio turno — nunca en el mismo lote que `read_file`/`grep_code`/otras tools (rompe el render del subagente). Para N tareas en paralelo usa `spawn_fanout` o `create_team`, no N×`spawn_subagent`.
- `create_team` + `run_team`: ≥2 dominios distintos con agentes especializados (paralelo real).
- ANTES de `create_team`/`run_team`/`spawn_fanout`: anuncia al usuario en 1 frase la composición y el reparto ("Monto un equipo: [agente A] → [parte], [agente B] → [parte]"). El usuario debe saber quién hace qué y por qué.
- DESPUÉS de `run_team`/`spawn_fanout`: SINTETIZA para el usuario qué aportó cada agente (combina hallazgos, destaca lo completado, menciona errores) ANTES de `task_done()`. Nunca cierres con `task_done()` silencioso saltándote la síntesis.
- `task_done()` (con plan activo) va DESPUÉS de la síntesis, no en lugar de ella.
- NO usar subagente para: editar ficheros, tests, implementación directa.

## Flujo de trabajo

Aplica el ciclo a tu dominio (programación, ofimática, seguridad, investigación, IoT, web…):

1. **Clasifica** — elige nivel 1/2/3/4; no crees plan donde basta una frase.
2. **Reúne contexto** — consulta lo necesario antes de actuar (lee ficheros, busca, usa las fuentes/herramientas de tu dominio). Errores o datos desconocidos → `web_search` primero.
3. **Actúa** — antes de cada acción que cambia algo (editar, crear, enviar, ejecutar, configurar): emite UNA frase con el objeto concreto ("Actualizando Y", "Generando el informe Z", "Enviando a …"). Después: describe qué cambió.
4. **Verifica** — comprueba el resultado con los medios de tu dominio y repórtalo de forma concreta (qué, dónde, con cifras: "N pasados, M fallidos", "3 filas escritas", `ruta:línea:msg`…).
5. **Finaliza** — qué se hizo · qué se produjo o cambió (referencias exactas) · resultado de la verificación · advertencias. `mem_save` para hallazgos; `workspace_remember` para instrucciones persistentes.

**Cuando trabajes con código:**
- Explora con `read_file`/`grep_code`/`lsp_symbols` antes de editar; al editar anuncia el fichero concreto (`"Actualizando Y.c:"`).
- Verifica con `run_tests`/`lint_file`/`lsp_diagnostics` y reporta "N pasados, M fallidos" o `ruta:línea:msg`.
- Ficheros >__LARGE_FILE_LINES__ líneas: `code_outline` → `read_sections` → `grep_code` (verificar old_string) → `edit_file`. NUNCA `read_file` sin offset en ficheros grandes.
- Edición segura: antes de `regex_replace` verifica con `grep_code`. Si falla: `read_file` → `edit_file` con literal exacto.

## Reglas

**Comunicación (el usuario NO ve tools ni resultados, SOLO tu texto — nunca trabajes en silencio):**
Mantén un hilo de diálogo conciso pero continuo. Norma: frases breves, alto contenido, cero relleno. Ahorra tokens en floritura, NO en informar.
- Al abrir el turno (antes de la 1ª tool): 1-2 frases con qué entendiste y cómo lo abordarás. Si son ≥3 pasos, el plan hace de resumen.
- Mientras exploras/consultas: di qué buscas y qué vas encontrando con datos concretos (rutas, `ruta:línea`, cifras). No solo antes de cambiar — también al leer/buscar.
- Antes de cada acción que cambia algo: 1 frase con el objeto concreto ("Actualizando Y", "Generando Z"). Después: qué cambió y su efecto.
- Nunca encadenes 2+ tools sin una frase entre medias: si lo haces, el usuario queda a ciegas.
- Al finalizar: resumen estructurado — qué se hizo · qué se produjo o cambió (referencias exactas) · verificación (cifras) · advertencias. No cierres con la frase de fin "a secas".
- Sin relleno ("Entendido, voy a…", "Como puedes ver…", "¡Claro!"). Código en ```language. Errores en ```text.

**`web_search` — escala antes de repetir:**
- Error HTTP/API/import desconocido → busca el error exacto + versión ANTES de probar nada.
- Símbolo no encontrado tras ≥3 búsquedas → puede ser externo o renombrado.
- ≥3 estrategias fallidas → busca antes de seguir adivinando.

**Docker:**
- `compose_down -v` DESTRUYE VOLÚMENES — PROHIBIDO salvo petición explícita. Usa `compose_stop`/`compose_restart`.
- Escribir en contenedor: `write_file` en host → `docker_cp(src='~/.oocode/tmp/f', dst='CONTAINER:/ruta/')`.
- Permission denied (Errno 13): escribe en `~/.oocode/tmp/` → `docker_cp`.

**PROHIBIDO** (el agente bloqueará): ficheros .py/.sh temporales · heredocs bash · `bash git/grep/find/ls/cat/sed -i/make/pytest/docker exec/docker compose/docker cp`.

**Anti-bucle:** tool falla 2 veces con el mismo arg → CAMBIA estrategia. Bash devuelve error → diagnostica (`ls_dir`/`find_files`) antes de reintentar.

**"__DONE_PHRASE__" — NUNCA emitas si:**
(1) hay tareas ◻ pendientes · (2) mencionas "Próximo paso"/"(PENDIENTE)"/"🔄 en curso" · (3) hay errores `❌`/`REQUIERE CORRECCIÓN` sin resolver · (4) editaste código y NO llamaste `run_tests`/`test_file`. El sistema detecta la contradicción y fuerza continuación.
- Error irresuelto: `workspace_remember(note="Aprendizaje: [problema] → [pendiente]")` → explica al usuario.
- Si editaste código: DEBES llamar `run_tests` o `test_file` antes de declarar completado. Excepción: tareas solo de lectura/análisis/docs.
- Nunca respuesta vacía: tras tools, continúa o responde. Si todo listo → "He completado todas las tareas."

## LSP — si hay servidor activo

| Tarea | Tool |
|-------|------|
| Estructura fichero | `lsp_symbols(path)` |
| Buscar en proyecto | `lsp_workspace_symbols(q, path)` |
| Callers/callees | `lsp_call_hierarchy(path, line)` |
| Tipo variable | `lsp_hover(path, line, col)` |
| Errores/warnings | `lsp_diagnostics(path)` |
| Renombrar | `lsp_rename(path, line, col, new_name, apply=true)` |

C/C++: `lsp_symbols`→`lsp_hover`→`lsp_call_hierarchy`→`edit_file`→`lsp_diagnostics`→`make_run`
Python: `lsp_diagnostics` tras editar · `lsp_references` antes de renombrar
JS/TS/Shell/Perl/YAML: `lsp_diagnostics` tras cada edición

## Memoria
- OOCODE.md + "## Instrucciones del proyecto" — máxima prioridad, SIEMPRE respetadas.
- Instrucciones persistentes → `workspace_remember(note)`.
- Hallazgos clave (arquitectura, bugs, decisiones) → `mem_save(nombre, contenido)`.
"""

def filter_system_rules(rules: str, has_tool) -> str:
    """Quita de SYSTEM_RULES las filas/bloques de dominios cuyas tools no están registradas.

    `has_tool(name)->bool` se consulta contra el registry del agente (incluye tools MCP
    activas). Así un agente personalizado sin git/docker/lsp/paquetes no recibe reglas que
    referencian tools de las que no dispone. Para el agente por defecto (todas las tools
    presentes) el resultado es idéntico a SYSTEM_RULES.
    """
    present = {
        "git":      has_tool("git_status"),
        "docker":   has_tool("docker_ps") or has_tool("compose_up"),
        "debug":    has_tool("strace_run") or has_tool("gdb_run"),
        "packages": has_tool("pip_tool") or has_tool("npm_tool"),
        "build":    has_tool("make_run") or has_tool("lint_file") or has_tool("lint_project"),
        "lsp":      has_tool("lsp_symbols") or has_tool("lsp_diagnostics"),
    }
    # Filas de la tabla HERRAMIENTAS (prefijo estable) → dominio que las habilita
    row_domain = {
        "| Git |":              "git",
        "| Docker/compose |":   "docker",
        "| Compilar/linting |": "build",
        "| Paquetes |":         "packages",
        "| Debug |":            "debug",
    }
    drop_rows = {row for row, dom in row_domain.items() if not present[dom]}

    out: list[str] = []
    skip_section = False   # dentro de un '## ' que se omite (LSP)
    skip_bold    = False   # dentro de un bloque '**X:**' que se omite (Docker)
    for line in rules.split("\n"):
        s = line.strip()
        if skip_section:
            if s.startswith("## "):
                skip_section = False   # fin del bloque; reprocesar esta cabecera
            else:
                continue
        if skip_bold:
            if s == "" or s.startswith("**") or s.startswith("## "):
                skip_bold = False      # fin del bloque; reprocesar esta línea
            else:
                continue
        # Sección LSP completa
        if not present["lsp"] and s.startswith("## LSP"):
            skip_section = True
            continue
        # Bloque '**Docker:**' dentro de ## Reglas
        if not present["docker"] and s.startswith("**Docker:**"):
            skip_bold = True
            continue
        # Filas de tabla de dominios ausentes
        if any(s.startswith(r) for r in drop_rows):
            continue
        out.append(line)
    return "\n".join(out)


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
    # ── Dominios no-código (MCP) — para que el ● live sea fluido en cualquier agente ──
    # Web / investigación
    "web_search":    "Searching the web for",
    "web_fetch":     "Fetching",
    "http_request":  "Requesting",
    "http_get":      "Fetching",
    "http_upload":   "Uploading",
    "graphql_query": "Querying",
    "websocket_send":"Sending",
    "sse_listen":    "Listening to",
    # Ofimática / documentos
    "doc_create":               "Generating",
    "doc_create_rfc":           "Generating",
    "doc_create_from_template": "Generating",
    "doc_fill_template":        "Filling",
    "doc_update_section":       "Updating",
    "doc_convert":              "Converting",
    "xlsx_create_report":       "Building",
    "xlsx_create_table":        "Building",
    "xlsx_fill_range":          "Filling",
    "pptx_create":              "Building",
    "insert_chart":             "Charting",
    # Correo / calendario
    "email_send":    "Sending email to",
    "email_list":    "Checking email",
    "email_read":    "Reading email",
    "email_search":  "Searching email for",
    # Datos / bases de datos
    "sqlite_query":  "Querying",
    "pg_query":      "Querying",
    "mysql_query":   "Querying",
    "db_query":      "Querying",
    # IoT / domótica
    "tapo_on_off":   "Controlling",
    "tapo_set":      "Configuring",
    "mqtt_publish":  "Publishing to",
    # Seguridad (análisis autorizado)
    "nmap_scan":     "Scanning",
    "port_scan":     "Scanning",
    "whois_lookup":  "Looking up",
    "dns_enum":      "Enumerating",
    "secret_scan":   "Scanning for secrets in",
}


def _make_tool_preview(name: str, args: dict) -> list[str]:
    """Returns 1-5 context lines for the live block while a tool runs.

    Element [0] is shown INLINE with the tool header: ◐ Tool: <first>.
    Elements [1:] are shown BELOW the tool line (diff, command, 'Running…').
    All lines disappear when the tool completes.
    """
    if name == "bash":
        cmd = (args.get("command") or "").strip()
        lines = cmd.splitlines()
        if not lines:
            return []
        preview = [f"$ {lines[0]}"]
        if len(lines) > 1:
            preview.append(f"  {lines[1][:70]}")
        preview.append("Running…")
        return preview[:3]
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
        return [f"({p}{suffix})"]
    if name == "read_files":
        ps = args.get("paths", [])
        if isinstance(ps, list):
            return [f"({x})" for x in ps[:4]]
        return [f"({ps})"] if ps else []
    if name == "write_file":
        p = args.get("path", "")
        content = (args.get("content") or "").strip()
        result: list[str] = [f"({p})"] if p else []
        for _l in content.splitlines()[:4]:
            result.append(f"  {_l[:70]}")
        return result[:5]
    if name in ("edit_file", "smart_replace", "regex_replace"):
        p = args.get("path", "") or args.get("file", "")
        return [f"({p})"] if p else []
    if name == "edit_files":
        edits = args.get("edits", [])
        if isinstance(edits, list):
            paths = [e.get("path", "") for e in edits[:3] if isinstance(e, dict) and e.get("path")]
            return [f"({p})" for p in paths]
        return []
    if name in ("bulk_replace", "patch_apply"):
        p = args.get("path", "")
        return [f"({p})"] if p else []
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
    if name in ("lsp_diagnostics", "lint_file", "mypy_check", "lsp_hover",
                "lsp_references", "lsp_implementation", "lsp_type_definition"):
        p = args.get("path", "")
        return [p] if p else []
    if name == "lsp_rename":
        p = args.get("path", "")
        base = p.rsplit("/", 1)[-1] if p else ""
        new_name = args.get("new_name", "")
        if base and new_name:
            return [f"{base} → {new_name}"]
        return [base] if base else []
    if name in ("git_diff", "git_log", "git_add", "git_commit"):
        msg = args.get("message") or args.get("path") or args.get("files", "")
        if isinstance(msg, list):
            msg = ", ".join(str(m) for m in msg)
        return [str(msg)] if msg else []
    if name == "ls_dir":
        p = (args.get("path") or ".").strip() or "."
        base = p.rsplit("/", 1)[-1] or p
        return [f"({base})"]
    if name in ("tree", "analyze_codebase"):
        d = (args.get("directory") or ".").strip() or "."
        base = d.rsplit("/", 1)[-1] or d
        return [f"({base})"]
    if name in ("code_outline", "read_sections"):
        p = args.get("path", "")
        base = p.rsplit("/", 1)[-1] if p else ""
        return [f"({base})"] if base else []
    if name in ("symbol_lookup", "affected_files"):
        sym = args.get("symbol", "")
        return [sym] if sym else []
    if name == "diff_files":
        a = args.get("file_a", "")
        b = args.get("file_b", "")
        ba = a.rsplit("/", 1)[-1] if a else ""
        bb = b.rsplit("/", 1)[-1] if b else ""
        if ba and bb:
            return [f"{ba} ↔ {bb}"]
        return [ba or bb] if (ba or bb) else []
    if name == "run_tests":
        p    = args.get("path", "")
        filt = args.get("filter", "")
        if p:
            return [f"({p.rsplit('/', 1)[-1]})"]
        if filt:
            return [f'-k "{filt}"']
        return []
    if name == "test_file":
        p = args.get("path", "")
        base = p.rsplit("/", 1)[-1] if p else ""
        return [f"({base})"] if base else []
    if name == "make_run":
        target = args.get("target", "")
        return [target] if target else []
    if name == "run_script":
        script = args.get("script", "")
        base = script.rsplit("/", 1)[-1] if script else ""
        return [base] if base else []
    if name == "web_search":
        q = args.get("query", "")
        return [f'"{q}"'] if q else []
    if name == "web_fetch":
        url = args.get("url", "")
        return [url[:70]] if url else []
    if name == "spawn_subagent":
        # El nombre del subagente ya va en la etiqueta coloreada del header live
        # (◐ spawn_subagent 💬 💻 coding); el preview solo añade la tarea.
        task  = (args.get("task") or "").strip()
        first = task.splitlines()[0][:60] if task else ""
        if first:
            return [first]
        agent_id = args.get("agent_id", "")
        return [f"[{agent_id}]"] if agent_id else []
    if name == "docker_ps":
        return ["all containers" if args.get("all") else "running"]
    if name in ("docker_logs", "docker_inspect"):
        c = args.get("container", "")
        return [c] if c else []
    if name == "docker_exec":
        c   = args.get("container", "")
        cmd = args.get("command", "")
        if c and cmd:
            return [f"{c}: {cmd[:50]}"]
        return [c] if c else []
    return []


def _make_compact_summary(blocks: list[tuple[str, dict, str, bool]]) -> str:
    """Genera resumen compacto estilo Claude Code para un batch de tool calls TUI con metadata.

    Ejemplo: "Searched for 3 patterns, read 2 files, wrote 1 file (ctrl+o to expand)"
    Para ediciones únicas: "Updated agent/loop.py"  (nombre de fichero, no contador genérico)
    Metadata: timestamp, tokens usados, estado LSP
    """
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
            if base_name == "read_files":
                # read_files recibe una lista en args["paths"]
                ps = args.get("paths", [])
                if isinstance(ps, list):
                    for p in ps:
                        bn = os.path.basename(str(p))
                        if bn:
                            read_files.append(bn)
                elif ps:
                    read_files.append(os.path.basename(str(ps)))
            else:
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
        # Lecturas: mostrar nombres de ficheros leídos (deduplicados)
        elif verb == "Read" and n >= 1 and read_files:
            unique = list(dict.fromkeys(read_files))
            shown = unique[:3]
            extra = len(unique) - len(shown)
            flist = ", ".join(shown) + (f" +{extra}" if extra > 0 else "")
            nu = len(unique)
            parts.append(f"Read {nu} file{'s' if nu != 1 else ''} ({flist})")
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





