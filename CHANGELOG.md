# Changelog — OOCode

## v0.5.0 (2026-06-12) — Estructura de conversación por pasos estilo Claude Code

Esta versión reescribe **cómo se agrupan los bloques de la conversación** para que el flujo se parezca al de Claude Code: cada paso del trabajo (su razonamiento, su acción y sus herramientas) forma su propio bloque visual en vez de fundirse todo en un único "Used N tools". También arregla la etiqueta del ● cuando el modelo no aporta texto. 3980 tests.

### Bloques por paso (el 💭 distinto separa el trabajo)

- **Un razonamiento (💭) nuevo abre un bloque nuevo.** Con el pensamiento activo, el modelo razona ANTES de cada acción pero a menudo reemite el mismo preámbulo (o ninguno), así que **todos los pasos se fundían bajo un solo `●` con "Used N tools"** — el usuario veía 9 herramientas juntas sin saber a qué tarea correspondía cada una. Ahora, cuando una iteración de continuación trae un razonamiento **distinto** del anterior y herramientas nuevas, se cierra el bloque previo, el 💭 sale **entre** bloques y se abre un `●` etiquetado por la acción (`Editing (db.c)…`). Resultado: la estructura `💭 razonamiento → ● acción → herramientas → ⎿ resumen` por cada paso, como en Claude Code.
- **Gated para no trocear de más.** El corte por razonamiento exige las cuatro condiciones a la vez: hay 💭, el bloque abierto ya acumuló herramientas, llegan herramientas nuevas y el 💭 es **distinto** del último (repetir el mismo pensamiento NO abre paso). Los modelos sin razonamiento conservan el comportamiento de agrupación anterior; el corte por cambio de asunto (comando↔fichero) sigue intacto. Revierte conscientemente la regla "razonar a solas nunca cierra el bloque" (`test_42`), que ahora era la causa de la fusión.

### Etiqueta del ● — muestra el fichero, no el nombre interno de la tool

- **`Editing Update` → `Editing (db.c)`.** Cuando el agente ejecutaba una edición sin aportar texto, el ● mostraba el verbo + el nombre INTERNO de display de la herramienta (`Editing Update`), que no dice nada. Ahora el ● resuelve y muestra el **fichero** que se edita (`Editing (db.c)…`), incluso cuando el modelo nombra el argumento de ruta con un alias (`edit_file(file=…)` en vez de `path=`). Si una herramienta no tiene verbo propio (p.ej. `docker_inspect`), se muestra `Using DockerInspect`; si lo tiene pero no hay contexto, solo el verbo (`Editing`), nunca el nombre de display colgando.

### Prompts de razonamiento — menos volcado al `<think>`, más texto visible

- **`think_injection` ya no refuerza el volcado al canal interno.** Con `reasoning` activo, el prompt añadía *"Muestra tu razonamiento paso a paso"* e inyectaba la cláusula de narración visible (`_THINK_VISIBLE`) **dos veces**. En modelos parcos (9B) ese refuerzo del razonamiento hacía que volcaran todo al `<think>` y dejaran la **respuesta visible vacía** (mucho uso de herramientas, pocos mensajes reales). Ahora el razonamiento ya está habilitado por el parámetro `think` del backend, así que el prompt solo pide **texto visible** una vez (sin reforzar el volcado; los niveles `high`/`full` conservan su énfasis intrínseco en mostrar el razonamiento).
- **`_THINK_VISIBLE` cubre la exploración.** El modelo narraba bien las **decisiones** pero encadenaba `grep`/`read` en silencio. La cláusula ahora pide explícitamente una frase visible **también al explorar** ("busco la definición de X en Y", "el error está en Z:línea"), no solo al decidir o editar.
- **El backstop (hint #15) nombra las herramientas mudas.** En vez de solo ejemplos genéricos, el aviso de turno silencioso ahora referencia las últimas herramientas usadas sin narrar ("Acabas de usar `grep_code`, `read_file`, `read_file` sin narrar nada") — un nudge concreto lanza mejor en modelos pequeños. *Persiste un techo de comportamiento con 9B; bajar `/think` desplaza más salida al texto visible.*

### Verificado

- **`/think` y `/reasoning` se aplican desde la configuración.** El nivel guardado por modelo (`models.configs.<modelo>.thinking`) se carga al arrancar y llega a la petición del backend (`think=`). El presupuesto de salida (`num_predict`) no trunca el texto visible.
- **Plantillas de workspace y personas alineadas.** Revisados `SOUL.md` de las plantillas y de los agentes desplegados (`main`, `coding`, `home_office`, `reasoning`, `webcrawler`): la persona empuja a narrar paso a paso, sin reglas que contradigan el flujo por pasos.

## v0.4.9 (2026-06-12) — Narración real estilo Claude Code + limpieza

Esta versión hace que el agente **comunique con texto real** (no solo razonamiento), acercando el flujo de la conversación al de Claude Code, y audita el conteo de tokens y la compactación. Incluye una limpieza de referencias de prueba/personales y un adelgazamiento de la suite de tests. 3976 tests.

### Más texto real del LLM (el 💭 no sustituye a la narración)

- **El razonamiento (💭) ya NO cuenta como narración visible.** Con el pensamiento activo, el modelo razonaba casi cada iteración y eso **desactivaba** el recordatorio interno que empuja a escribir una frase de texto al usuario (el `_turn_text_emitted` quedaba en `True` por el simple hecho de razonar). Resultado real medido en logs: el agente narraba **una vez** y encadenaba ~25 herramientas en silencio, incluido un **giro importante** del diagnóstico sin avisar. Ahora el indicador de narración mide **solo texto visible**: el 💭 se sigue mostrando (canal auxiliar), pero el agente recibe presión para narrar cada acción con texto normal.
- **`THINK_PROMPTS` reformulado.** La guía de razonamiento decía "razona en profundidad… muestra tu razonamiento" **sin pedir nunca narración visible**, así que los modelos locales volcaban toda su comunicación al canal `<think>` y devolvían una respuesta mínima. Se añade en todos los niveles (y en `/reasoning on`) la cláusula: *el razonamiento es un canal INTERNO; tras pensar, escribe SIEMPRE 1-2 frases visibles de qué haces y por qué*. Es un steer persistente que complementa el backstop reactivo.
- **Giros y descubrimientos = mensaje de texto nuevo.** Nueva regla de Comunicación: cuando un resultado cambia el plan o el diagnóstico, el agente para y escribe 1-2 frases ANTES de seguir — el giro abre su propio bloque en vez de quedar enterrado.
- *Nota:* con modelos pequeños (9B) hay un techo de comportamiento; bajar `/think` desplaza más salida al canal de texto visible.

### Conteo de tokens y compactación — auditados

- **El conteo de contexto es correcto.** Los contadores de coste (↑/↓, sesión y turno) incluyen el razonamiento (vía `eval_count` y la estimación en vivo). La **barra de contexto %** NO crece con `/think` **a propósito**: el razonamiento es efímero — no se almacena en el historial ni lo reenvía ningún backend (Ollama/OpenAI/Anthropic solo reenvían `content` + `tool_calls`), así que no consume ventana. Lo que llena el contexto son los **resultados de herramientas** (lecturas de fichero, `make`, `lint`), que es lo esperado.
- **Limpieza:** se elimina la rama muerta que "contaba" el razonamiento en la estimación de contexto (`_msg_tokens`/`_CPT_THINK`) — nunca se ejecutaba y contradecía el diseño efímero.
- **Compactación verificada segura tras los cambios de flujo:** ocurre en frontera de iteración (nunca a mitad de una herramienta → no deja ficheros a medio editar), el `min_keep` adaptativo conserva todos los mensajes de la tarea activa, no rompe pares tool-call/resultado y ancla la "Tarea original" en el resumen.

### Limpieza de referencias de prueba/personales

- Auditoría completa del código, prompts y documentación: sustituidas las referencias a proyectos de prueba por nombres genéricos (p.ej. `act_comm.c`/`act_wiz.c` → `handlers.c`, `mud.h` → `core.h`, `interp.c` → `parser.c`, programa de ejemplo → `myapp`) y rutas de ejemplo `src/` neutralizadas en los prompts. Las referencias a **Claude** que se conservan son funcionales (backend Anthropic real, IDs de modelo, comparativa intencional del README) y la identidad pública del proyecto (`github.com/burzumishi/oocode`) se mantiene.
- **Suite de tests adelgazada sin perder cobertura.** `test_18_permissions.py` parametrizaba 15 métodos sobre listas de ~60 tools (auto/ask), generando ~850 casos que verificaban la **misma** lógica de resolución de permisos por cada tool individual. Se convirtieron a un bucle interno por test (se sigue comprobando cada tool, pero en un solo caso): de 953 a 118 tests en ese fichero. Total de la suite: de 4812 a 3976, **sin** reducir comportamiento cubierto.

## v0.4.8 (2026-06-11) — Razonamiento visible + edición robusta multi-lenguaje

Esta versión hace que la conversación sea **clara y razonada paso a paso** (se muestra el razonamiento del modelo, las herramientas se agrupan por fichero, `ask_user` se respeta siempre) y mejora OOCode como **editor**: las herramientas de edición toleran diferencias de whitespace en cualquier lenguaje. 4778 tests.

### Razonamiento visible (💭)

- El **razonamiento del modelo** (canal `<think>`) ahora se **muestra como narración** atenuada (💭), renderizada en Markdown y alineada con la conversación. Antes se descartaba (solo se contaba para tokens), así que las herramientas se ejecutaban sin explicación del "porqué".
- **Coste cero si está desactivado**: solo aparece cuando habilitas el pensamiento del modelo (`/think low|medium…` o `thinking.think_level` en `models.configs`). Con modelos locales en modo herramientas, esta es la vía para tener el "porqué" de cada paso.
- **Fix crítico (2026-06-12): `/think` y `/reasoning` ahora llegan de verdad al modelo.** El nivel de pensamiento y el flag de razonamiento se guardaban en `oocode.json` por modelo y se cargaban a runtime, pero **nunca se enviaban en la petición LLM** — `OllamaBackend` solo pasaba `options`, jamás el parámetro `think`. Resultado: `/think high` y `/reasoning on` no producían razonamiento (el modelo usaba su default). Ahora el valor se mapea y se envía a los 3 backends (Ollama `think`, OpenAI `reasoning_effort`, Anthropic bloque `thinking` con `budget_tokens`). Verificado contra Ollama real. `/think off` envía `think=False` explícito (muchos modelos —qwen3.5— razonan por defecto si no se pasa el parámetro, así que omitirlo no los silenciaba). Los modelos sin soporte de thinking se manejan con un retry automático sin el parámetro (no se propaga el error).
- **El cap de visualización del 💭 escala con el nivel** (2026-06-12): con `/think high` se muestra el razonamiento prácticamente completo (antes un corte fijo de 1200 chars recortaba lo que pedías ver).
- **Nudge de narración visible (2026-06-12).** Con el pensamiento activo, los modelos de razonamiento tienden a poner la narración en el canal `<think>` y emitir poco texto, así que el razonamiento quedaba mayormente dentro de los bloques de tools en vez de fluir entre ellos. Se refuerza en las 3 capas (SYSTEM_RULES, persona de los agentes y backstop reactivo) que **el pensamiento interno no sustituye al texto visible**: antes de cada acción el agente deja una frase de texto normal → se forman fronteras naturales y el 💭 sale como narración entre bloques. No se tocó la lógica de agrupación de bloques (estilo Claude Code).
- **Match de configuración por modelo robusto**: la config de un modelo (thinking, contexto, timeout) ahora se aplica aunque el nombre lleve prefijo de registry o `:latest` — p.ej. una entrada `qwen3.5-9b` se aplica a `tu-registry/qwen3.5-9b:latest`.

### Bloques de herramientas por fichero/paso

- **Agrupación por fichero.** Las herramientas y razonamientos que trabajan sobre **el mismo fichero** (leer + buscar + razonar + editar `module.c`) quedan **juntos en un bloque**; el razonamiento intermedio aparece **dentro** (`│ 💭`) y, sin bloque abierto, fuera como narración Markdown. El bloque se cierra cuando el modelo emite un **mensaje nuevo** (cada texto del modelo conserva su `●`) o cuando una **edición toca otro fichero** (auto-split: bloque nuevo + su diff). Razonar por sí solo **nunca** rompe el bloque, y las búsquedas amplias (`grep_code`) y `bash` tampoco. Esto evita los dos extremos: el "Used N tools" gigante que soltaba todos los diffs al final, y el sobre-troceo (cada lectura/búsqueda del mismo fichero en su propio bloque).
- **Fix (2026-06-12): el auto-split también dispara con `smart_replace`/`regex_replace`.** Estas tools usan el parámetro `file` (no `path`) y la extracción del fichero destino no lo cubría, así que el auto-split **nunca** disparaba para ellas: tres `Replace` sobre tres ficheros distintos acababan en un solo bloque "Used 13 tools". Como el steering anti-fallos de edición empuja precisamente hacia `smart_replace`, era el caso común.
- **Las tools de memoria van FUERA de los bloques (2026-06-12).** `mem_save`/`workspace_remember` son acciones de continuidad del agente, no trabajo sobre ficheros: su `◐ ⬡` cierra el bloque en curso y se muestra al nivel de la conversación, en vez de quedar enterrado en el "Used N tools" de la edición en curso.
- **`/agent reset` con paridad de plantillas (2026-06-12).** El reset regeneraba los ficheros del workspace con los generadores Python (fallback) en vez de leer `workspace/templates/` como hace la creación — un agente reseteado quedaba con una persona divergente y sin las mejoras de las plantillas. Ahora usa el mismo camino (`WorkspaceManager.init(overwrite=True, preserve=("MEMORY.md",))`); MEMORY.md y `memory/` se siguen conservando.
- **Unidades visuales por edición (2026-06-12), estilo Claude Code.** Cada edición completada con éxito **cierra su bloque al momento** (exploración + razonamiento + edición + **su diff** pasan ya a la conversación) y la siguiente edición **reabre el suyo** ("● Continuing with handlers.c" si es el mismo fichero, "● Moving on to parser.c" si cambia). Antes, N ediciones del mismo fichero se apilaban en el live block y todos los diffs y razonamientos aparecían de golpe al final ("Used 16 tools"). Una edición **fallida** no cierra el bloque: su reintento se queda en la misma unidad. Paridad WebUI (`tool_done.is_modify` → el cliente cierra el bloque).
- **Fix (2026-06-12): el razonamiento que abre un paso nuevo queda ENTRE bloques.** Cuando la iteración trae texto nuevo (→ su propio `●`), el cierre del bloque anterior se adelanta a antes del 💭: el razonamiento del paso se ve al nivel de la conversación, en lugar de quedar enterrado como última línea `│ 💭` del bloque que se estaba cerrando. La frontera sigue siendo la del texto (misma condición que el `●`) — razonar por sí solo sigue sin cerrar nada. Paridad WebUI vía `reasoning.new_step`.
- **Frontera por cambio de ASUNTO (2026-06-12).** Un intento de compilación/ejecución (`bash`/`make_run`/`run_script`/`python_exec`…) y la edición de un fichero son **unidades visuales distintas**: cuando una iteración sin texto pasa de comandos a ediciones (o viceversa, o a otro fichero), el bloque abierto se cierra, el 💭 de esa iteración queda **entre bloques** y la tanda nueva abre su propio `●`. Antes, "autogen + make + razonar los errores + editar config.h" se encadenaban bajo un solo "Used N tools" con cinco 💭 enterrados. La decisión la toman las **tools entrantes** (no el razonamiento); las lecturas/búsquedas son neutrales y nunca rompen el bloque.
- **El live block muestra la COLA del bloque mientras corre una tool** (las 5 líneas más recientes: último 💭, output previo), no las primeras 5 — con bloques largos la ventana se quedaba congelada en el principio y nada parecía avanzar hasta el flush.
- **`task_done` es frontera visual (2026-06-12).** Al cerrar una tarea del plan, el bloque de tools de esa tarea se cierra ANTES y la narración del desenlace (`● Tarea N: …`) sale estática **entre bloques** — antes caía dentro del live block y quedaba enterrada como los 💭. Su resultado interno ("✔ Tarea N/M…") ya no cuenta como tool del bloque siguiente.
- **El razonamiento ya NO se pierde por el camino (2026-06-12).** Auditoría de todos los returns de `_stream_response`: (1) los **retries XML** (EOF/malformado) descartaban el thinking ya acumulado del intento fallido — y el retry va con `/no_think`, así que la iteración salía muda; (2) el **path sync** (subagentes) nunca propagaba `resp.thinking` → los subagentes no mostraban 💭 jamás; (3) `Response` ni siquiera tenía campo `thinking` (los `chat_sync` de los 3 backends lo tiraban); (4) el backend **OpenAI** ignoraba `reasoning_content` (llama.cpp/vLLM) en streaming y sync; (5) la rama REPL sin fallback no recolectaba `chunk.thinking`. Todos preservan ahora el razonamiento.
- **El thinking cuenta como actividad para el watchdog de timeout (2026-06-12).** Con think alto el modelo puede razonar minutos sin emitir texto; el watchdog de modo app solo contaba chars de TEXTO y mataba el stream a mitad de razonamiento (el path REPL ya lo contaba — paridad).
- **Avisos de bash conscientes de pipes (2026-06-12).** `make 2>&1 | grep error | tail -30` ya no genera los falsos "Usa grep_code/read_file en lugar de bash" — esos filtros consumen la SALIDA de otro comando, donde no hay tool nativa equivalente. El aviso se mantiene para uso directo sobre ficheros (`grep foo file.c`), y `sed -i` sigue prohibido esté donde esté.
- **Las ediciones nunca se paralelizan**: un lote con `edit_file`/`write_file`/`smart_replace`/… se ejecuta en secuencia para que cada edición tenga su propio bloque + diff a medida que ocurre (en paralelo se volcaban agrupadas al final). Las lecturas/búsquedas sí siguen en paralelo. Paridad TUI/WebUI.
- El **mensaje de `task_done`** (resumen de cada tarea) ahora **se muestra al usuario**. Los modelos locales suelen poner ahí su narración ("Tarea 3: eliminé X porque no se usa"); antes se descartaba.
- Un separador `---` que el modelo emita como texto ya **no se muestra como `● ---`** (se reconoce como regla horizontal).

### `ask_user` y aprobación de plan

- **`ask_user` se muestra SIEMPRE.** Es una pregunta genuina del agente; `/elevated` (que solo afecta a permisos de herramientas) ya **no la silencia**. Igual para la **aprobación de plan** (`/plan on`): si la activas, siempre te pregunta. *(Antes, en modo elevado el agente decidía por su cuenta sin mostrar la pregunta.)*
- La **aprobación de plan** muestra el plan **formateado** en la conversación y un formulario con una **pregunta corta** (antes metía el plan multilínea dentro de la pregunta, ilegible en la barra de estado).
- **Las preguntas de cierre sí/no van por `ask_user` (2026-06-12).** El agente cerraba una tarea con un resumen y una pregunta en texto plano ("…¿Deseas que continúe corrigiendo los errores?") y se detenía, dejando al usuario sin forma estructurada de responder. La regla de `ask_user` ya cubría preguntas "con opciones" pero el modelo local no veía una confirmación sí/no de continuación como "opciones". Ahora la regla cubre **explícitamente** las confirmaciones sí/no ("¿Sigo con X?", "¿Lo arreglo?", "¿Procedo?") y deja claro que **aplica aunque consideres la tarea completada**: el resumen se narra en texto y el siguiente paso se ofrece con `ask_user` (sí/no como opciones). Reforzado en las personas de los agentes. También se amplió el recordatorio de narración para cubrir la **exploración** (no encadenar 10 `grep`/`read` en silencio: decir qué se busca y resumir los hallazgos), no solo las ediciones.
- **Formulario `ask_user` rehecho y navegable (2026-06-12).** Antes era ilegible: las opciones no se podían navegar, reutilizaba el prompt de permisos ("¿Permitir? →"), el botón de la pregunta salía cortado a media palabra y **el formulario se recortaba** (altura fija de 3 líneas → las opciones quedaban invisibles). Ahora: fila de **chips-botón** con el resumen de cada pregunta (☐/☑), y debajo la pregunta completa con sus **opciones navegables con ↑/↓** (cursor `❯`), una fila de "✎ Otra respuesta" para texto libre y una línea de ayuda. Se elige con **Enter** (o número como atajo), se cambia de pregunta con ←/→, y el alto del formulario se ajusta al contenido. El input ya no muestra "¿Permitir?" durante una pregunta.

### Tono y narración

- El agente narra de forma **cálida, cercana y continua**, explicando qué hace y **por qué decide** lo que decide (veredicto + motivo + acción), sin trabajar en silencio ni cerrar tareas solo con su título. Personas de los agentes (plantillas y workspaces) alineadas.

### Edición robusta (menos fallos de `edit_file`), multi-lenguaje

- **`edit_file`/`edit_files` toleran diferencias de whitespace.** La causa nº1 de "PRE-EDIT FALLIDO" era el modelo equivocándose en espacios/tabs/indentación de un `old_string` multilínea. Ahora el match escala la tolerancia y **solo aplica si la coincidencia es única** (si es ambigua, no adivina): exacto → ignorando espacios finales (CRLF incluido) → ignorando indentación (reaplicando la del fichero) → **(2026-06-12) ignorando whitespace interior** (tabs de alineación dentro de la línea, invisibles para el modelo en el output numerado de `read_file`). Funciona en **cualquier lenguaje** (opera sobre líneas/whitespace). El resultado avisa cuando hubo que tolerar whitespace; el diff mostrado es la verdad.
- **Fix (2026-06-12): el precheck de `edit_file` usa el MISMO matcher tolerante.** El precheck del agente comprobaba `old_string` con match EXACTO y bloqueaba la llamada antes de que la tool corriera — toda la tolerancia anterior era código muerto en la práctica (causa real de la mayoría de "PRE-EDIT FALLIDO" en ficheros C indentados con tabs). Ahora deja pasar cuando hay match tolerante ÚNICO; si es ambiguo lo dice ("añade más contexto") y si de verdad no está, sugiere las **líneas más parecidas** del fichero por similitud real (antes sugería basura por substring, p.ej. ASCII-art al buscar `}`).
- **`smart_replace`/`regex_replace` con semántica de editor (2026-06-12):** `re.MULTILINE` **siempre activo** (`^`/`$` casan por línea — antes `^patrón$` solo casaba al inicio del fichero entero y el modelo recibía "NO encontrado" sistemático); si el patrón no casa y contiene espacios, **reintento tolerante a tabs** (`[ \t]+`, anotado en el resultado); y al fallar, el contexto muestra las **líneas relacionadas con el patrón** (fragmento literal más largo + similitud), no las primeras 40 líneas del fichero.
- **`read_file(skip_comment_banner=true)`**: colapsa una cabecera de comentario/licencia larga (logos, listas de autores) en un marcador, **conservando los números de línea** para no desalinear ediciones. Detección **multi-lenguaje** por extensión: C-family (`//`,`/* */`; `#include`/`#define` no se colapsan), `#` (Python/shell/Ruby/YAML… + docstrings `"""`), `--` (SQL/Lua/Haskell), `;` (Lisp), `!` (Fortran), `%` (LaTeX/Erlang), `<!-- -->` (HTML/XML/MD), `(* *)` (OCaml/Pascal)…
- **Fix (2026-06-12, de logs reales): `edit_file(file=…)` ya no revienta.** El modelo confunde el nombre del parámetro de ruta entre herramientas (`edit_file`/`read_file`/`write_file` usan `path`; `smart_replace`/`regex_replace` usan `file`), así que llamaba `edit_file(file=…)` y el filtro de kwargs descartaba `file` → `missing 1 required positional argument: 'path'` (era la causa nº1 de crashes de edición en los logs). Ahora un alias de ruta se **remapea automáticamente** al nombre que la herramienta acepta (bidireccional, conservador: no toca nada si ya viene el correcto). Aplicado en el dispatch nativo y en las tools MCP de edición (`smart_replace`/`regex_replace`/`context_before_edit`/`pre_edit_check`…).
- **Telemetría de tool calls más precisa** (`tool_calls.jsonl`): el flag `ok` clasificaba `⛔ PRE-EDIT FALLIDO` como éxito (no contenía la palabra exacta "fallida") y daba falsos negativos cuando el lint mencionaba "error". Ahora usa un clasificador robusto de los marcadores reales de fallo.

### Subagentes

- Los subagentes ya **no saludan al usuario** ("¡Hola!") al empezar cada tarea: reciben una instrucción de "trabajador interno" y empiezan directos por el trabajo y los resultados. (Verificado además que reciben el mismo conjunto de reglas/correcciones que el agente principal — no pierden contexto.)

### RAG del proyecto

- La indexación semántica del proyecto **ignora más artefactos de build/generados** (autotools `.deps`/`.libs`/`autom4te.cache`, CMake, IDE, `vendor`, `config.h`, `*_pb2.py`, `moc_*.cpp`…) para reducir re-embeds inútiles tras cada compilación. Ajustable con `rag.indexInterval`/`rag.maxFiles`/`rag.enabled`.

### Limpieza / release

- Auditoría de datos: eliminadas referencias de marca/estilo incidentales; plantilla `USER.md` saneada a placeholders genéricos; **nuevo `.gitignore`** para no publicar artefactos locales (tags, caché, config local con rutas/IPs de la máquina).

## v0.4.7 (2026-06-10) — Edición fiable + paridad del plugin Vim

Esta versión corrige la **causa raíz** del problema por el que las herramientas de edición "nunca acertaban y revertían", da **paridad de interacción** al plugin de Vim con TUI/WebUI y mejora cómo el plugin referencia el fichero abierto. 4684 tests.

### Edición fiable — invalidación de la caché de lecturas

- **Bug raíz corregido**: la caché de resultados de lectura (`read_file`, `grep_code`, `read_sections`…) solo se vaciaba una vez por turno, así que tras un `edit_file` exitoso un `read_file` posterior del **mismo fichero** devolvía el contenido **pre-edición** cacheado. El agente creía que el cambio no se había aplicado, reintentaba el mismo `old_string` y obtenía `PRE-EDIT FALLIDO` (ya estaba aplicado) → bucle de reintento/revert. Era un fallo de la herramienta, no del modelo.
- Ahora, tras cada operación de mutación, las lecturas afectadas se **invalidan automáticamente**: dirigida por ruta (fichero + directorio) para las tools con ruta concreta; vaciado completo para las que ejecutan comandos (`bash`, `python_exec`, `make`, git, docker…) y pueden tocar ficheros arbitrarios.
- Además, `smart_replace` y varias operaciones git mutadoras (`checkout`/`reset`/`merge`/`rebase`/`apply`) dejan de cachearse (antes, una segunda llamada idéntica devolvía el resultado cacheado **sin editar**).
- Reforzada la guía de edición: leer el fichero y copiar el texto literal antes del primer edit; no reintentar el mismo patrón al fallar, sino escalar a `smart_replace`/`regex_replace`.

### Plugin Vim 3.2 — paridad con TUI/WebUI

- El panel de Vim ya maneja los eventos interactivos del servidor que antes ignoraba: **`ask_user`** (preguntas con opciones → se responde con `inputlist`/texto libre y se envía la respuesta), **confirmación de permisos**, **resumen de respuestas**, **mensajes en cola** y **resultados de slash commands**. Antes, cualquier `ask_user` dejaba el turno colgado hasta el timeout.
- **Contexto del fichero/directorio abierto**: cada `:OOCode`/`:OOCodeAsk` antepone una referencia con la **ruta absoluta** del fichero que estás viendo (+ línea/columna del cursor) y el directorio de trabajo, para que el agente sepa a qué te refieres ("revisa esta función") y lo lea con `read_file`. En un explorador de directorios referencia el directorio. Configurable con `g:oocode_inject_file_hint`.

### TUI

- **Separadores `---` ya no aparecen como bullet**: cuando el modelo emitía una regla horizontal markdown (`---`, `***`, `___`) como separador —típicamente tras presentar un plan—, la TUI la mostraba como un inútil `● ---`. Ahora esas líneas se descartan del bullet (solo para el display; el texto sigue intacto en contexto/logs) y, si el turno no tiene más texto, el bullet etiqueta la primera herramienta (`Running make clean…`), indicando qué hizo el agente.

### Limpieza

- Eliminadas referencias de marca de terceros en los prompts del sistema, la ayuda al usuario y los comentarios de desarrollo (OOCode es su propio producto).

## v0.4.6 (2026-06-10) — Interacción con el usuario + robustez

Esta versión mejora la **interacción con el usuario** en el TUI y la WebUI: preguntas estructuradas, aprobación de planes y confirmación de permisos — además de una tanda de correcciones de robustez y precisión. 4679 tests.

### `ask_user` — preguntas estructuradas / encuestas (TUI + WebUI)

- Nueva tool **`ask_user`**: el agente puede plantear **una o varias preguntas** (hasta 4) con opciones, esperar la respuesta y continuar con la decisión del usuario — en vez de adivinar o soltar listas pasivas de "próximos pasos".
- Cada pregunta admite **multiSelect** (el orden de selección se conserva → sirve para fijar un orden de ejecución) y siempre una opción de **texto libre**.
- **TUI**: formulario en la barra de estado con chips de pregunta y **navegación libre con ←/→**; se responde por teclado. **WebUI**: tarjeta con secciones y botón Submit. Al cerrar, se vuelca un resumen `● User answered OOCode's questions: …` antes de seguir.
- El agente usa `ask_user` ante **ambigüedad real**, para **elegir enfoque/orden**, y al proponer **próximos pasos que dependen de tu decisión**. Los subagentes no preguntan (deciden solos).

### Plan-mode — aprobación de planes (`/plan`)

- Nuevo modo opt-in **`/plan on`** (config `context.planApproval`): antes de ejecutar un plan, el agente lo **presenta y espera tu aprobación** (Aprobar / Editar / Cancelar). Reutiliza `ask_user`; funciona en TUI y WebUI.

### WebUI — confirmación de permisos (opt-in)

- Nueva config **`webui.permissionPrompt`** (default off): cuando se activa, las herramientas que requieren permiso **preguntan en el navegador** (Sí/No/Siempre). Con **guarda de cliente conectado**: si no hay navegador abierto (VIM/`send_sync`/pestaña cerrada) auto-aprueba — no se cuelga el uso headless.

### Cola de entrada mientras el agente trabaja

- Ahora puedes **escribir mientras el agente ejecuta un turno**: los slash de display/control (`/help`, `/mcp`, `/steer`, `/kill`…) pasan al momento; los mensajes y los slash que mutan estado (`/new`, `/compact`, `/model`…) se **encolan (FIFO)** y se procesan al terminar. `/kill` descarta la cola. TUI y WebUI.

### Precisión y robustez

- **Edición**: ante fallos de `edit_file` por espacios/indentación, el agente es guiado a `smart_replace`/`regex_replace` (más robustas) y a `context_before_edit`, rompiendo los bucles de reintento. `edit_files` informa mejor del fallo atómico.
- **Retry XML**: los tool calls XML malformados se reintentan con `/no_think` (generación más corta y determinística).
- **Conteo de tokens**: los contadores y barras muestran el límite **efectivo del modelo** (no el fallback interno); las imágenes ahora cuentan en la estimación.
- **Turnos sin texto** (qwen3.x): el `●` etiqueta la herramienta (`● Running make`) en vez de `…`; re-anclaje correcto tras compactar a mitad de turno.
- **Esquemas de herramientas**: añadidos tipos a parámetros que faltaban; test de higiene de esquemas.
- **Limpieza**: claves huérfanas eliminadas de `oocode.json` (`context_window_*`, `prompt_cache_*`, `cache_dir`); defaults de docs/instalador alineados con el código (`compactThreshold` 0.80, `maxToolResultTokens` 800).

## v0.4.5 (2026-06-09) — Rediseño del prompt multitarea del TUI + alineación unificada

Pulido visual de la barra de estado del TUI mientras el agente trabaja, y limpieza de
referencias obsoletas en los workspaces tras el split de MCP de 0.4.4.

### TUI — prompt multitarea rediseñado

- **Frase principal en rojo**: el modo multitarea muestra el resumen del plan
  (`plan_create(summary=…)`, nuevo atributo `_plan_summary`) como frase principal en
  rojo, en lugar del antiguo `◈ Multitarea: [N/M] tarea`. Fallback al texto de la tarea
  activa si no hay summary.
- **Palabra de "pensamiento" idéntica al modo normal**: el indicador entre paréntesis
  (`Cavilando… · tiempo · tokens`) reutiliza exactamente las mismas palabras
  (`_THINKING_WORDS`/`_NEAR_FINISH_PHRASES`) y colores (`status-word`/`status-phrase`) que
  el spinner de turno simple.
- **Lista de tareas**:
  - Completadas → **verde tachado** (`task-done` con `strike`).
  - En curso → cuadrado **`◼` verde** (`task-active-mark`) + texto **blanco en negrita**
    (`task-active-text`), como dos segmentos separados.
  - Pendientes → `◻` atenuado. Se mantiene el contador `… +N pending, M completed`.
- La tarea activa ya **no** se duplica en la línea del spinner (solo aparece en la lista).

### TUI — alineación unificada del status window

- Patrón de columnas común para los tres prompts (normal, multitarea y compactación):
  icono/spinner animado en **col 2** + 1 espacio; conector `↳` en col 2; iconos de tarea
  no-primera, summary `…` y footer `⎿ Tip` en **col 4**.
- Todos los spinners de trabajo siguen animados (`_SPINNER_FRAMES`); no hay ningún spinner
  fijo durante la ejecución.

### Compactación — objetivo post-compactación (`compactTarget`)

- **Síntoma:** con modelos de contexto grande (9b q8_0) en proyectos con ficheros grandes,
  tras compactar el contexto se quedaba al 50–70% (a veces 70%), cerca de volver a compactar —
  justo lo que el contexto grande debía evitar.
- **Causa:** la 2ª pasada (la única que reduce el *tamaño* de los mensajes conservados,
  truncando tool results largos) solo se activaba por encima de `highWater` (0.70) y protegía
  las **4** tool results más recientes. Con lecturas grandes recientes, no llegaba a truncar y
  el contexto se quedaba alto.
- **Fix:** nuevo `context.compactTarget` (defecto **0.50**). Tras soltar mensajes antiguos, la
  2ª pasada trunca los tool results largos conservados hasta bajar de ese objetivo —
  protegiendo solo las **2** más recientes, y si aún sigue alto, solo la última. `highWater`
  pasa a usarse únicamente para el disparo de la pre-compactación en background.
- Recomendación añadida a `doc/02_configuration.md`: combinar `compactTarget` con un
  `maxToolResultTokens` moderado (4000–7000) para no inflar el contexto de trabajo entre
  compactaciones.

### Workspaces — limpieza tras el split de MCP (0.4.4)

- El workspace del agente `home_office` citaba el servidor muerto `home-office-assistant`
  (→ `word/excel/pptx/mail/cmdb-assistant`) y tools eliminadas en el split
  (`doc_insert_chart_native` → `insert_chart`; bloque `doc_insert_diagram` con PNG/matplotlib
  → gráficas OOXML nativas). Auditados system prompt, prompts MCP, plantillas y
  `_TOOL_LIVE_VERBS`: el resto estaba correcto.

### Documentación

- Configuraciones de ejemplo en `doc/examples/` para tres perfiles de VRAM
  (4b q4_0, 4b q8_0, 9b q8_0) con un README que explica los tradeoffs y que la cuantización
  se elige al hacer `ollama pull`.

4576 tests.

## v0.4.4 (2026-06-09) — División del MCP home-office en cinco servidores

El servidor MCP `home-office-assistant` había crecido demasiado (9854 líneas, 66 tools)
y mezclaba dominios dispares. Se divide en cinco servidores MCP autocontenidos, cada uno
activable por separado y arrancado al inicio como el resto de bundled. Primero por dominio
(mail, cmdb y un `office`); después ese `office` se subdividió por formato (word/excel/pptx)
porque seguía siendo demasiado grande.

### Cinco servidores nuevos (split de `home_office_assistant.py`)

- **`word-assistant`** (`mcp_servers/word_assistant.py`) — 29 tools: documentos Word
  (.docx) O365 nativos, la tool unificada **`doc_create`** (genera .docx/.xlsx/.pptx según
  extensión), gráficas OOXML DrawingML editables (`insert_chart`), plantillas docxtpl/Jinja2,
  estilos Calibri, y utilidades transversales (conversión pandoc, OCR `image_to_text`,
  `pdf_extract_text`, metadatos, comparación, gestión de proyecto). 13 prompts,
  8 resources (`office://…`).
- **`excel-assistant`** (`mcp_servers/excel_assistant.py`) — 16 tools: hojas `.xlsx`
  (openpyxl) — lectura/escritura, informes, tablas nativas, gráficas, formato condicional,
  validación, freeze panes, protección; y `csv_analyze`. 3 prompts.
- **`pptx-assistant`** (`mcp_servers/pptx_assistant.py`) — 7 tools: presentaciones `.pptx`
  (python-pptx) — crear, diapositivas, gráficas, notas, fondos, lectura. 1 prompt.
- **`mail-assistant`** (`mcp_servers/mail_assistant.py`) — 11 tools de comunicación/PIM:
  email IMAP/SMTP, calendario `.ics`, notas markdown, contactos vCard. 2 prompts,
  4 resources (`mail://…`).
- **`cmdb-assistant`** (`mcp_servers/cmdb_assistant.py`) — 3 tools de inventario IT:
  `cmdb_search`, `cmdb_update`, `asset_register_add` (CSV/XLSX/JSON). 1 resource
  (`cmdb://server_inventory`).

Sin pérdida de funcionalidad: las 66 tools, 19 prompts y 13 resources originales se
conservan, repartidos entre los cinco servidores. Total bundled: 12 servidores.

### Configuración y migración transparente

- Flags nuevos en `config/model.py` y `config/blocks/mcp.py`: `mcp.wordAssistant`,
  `mcp.excelAssistant`, `mcp.pptxAssistant`, `mcp.mailAssistant`, `mcp.cmdbAssistant`.
- **Fallback legacy en cadena:** word lee `~/.oocode/office.json`, mail `mail.json`, cmdb
  `cmdb.json`, todos con fallback a `~/.oocode/home_office.json`. Flags:
  `word/excel/pptx` ← `officeAssistant` ← `homeOfficeAssistant`; `mail/cmdb` ←
  `homeOfficeAssistant`. Quien tuviera `mcp.homeOfficeAssistant.enabled=true` ve los cinco
  activados en la primera carga (`OOConfig.load` los materializa en `save()`).
- Cableado actualizado: `agent/services.py` (`_BUNDLED_MCP`, ahora 12 servidores),
  `agent/mcp_manager.py` (`_BUNDLED_SERVER_MAP`), `ui/commands.py` (`/mcp`, `/doctor`,
  `/config`), `webui/api_config.py` + `webui/page_config.py`, hook
  `doc_validate_template_filled` (prefijo `mcp_word_assistant_…`).

### Tests y docs

- `tests/test_45_home_office_mcp.py` → `tests/test_45_office_mail_cmdb_mcp.py`: prueba los
  cinco servidores; los agregados se verifican como unión (66 tools / 19 prompts / 13 res).
- Actualizados `test_53`, `test_58`, `test_59`, `test_61`, `test_62`, `test_79`.
- `CLAUDE.md`, `README.md`, `doc/22_mcp_servers.md` reflejan los 12 servidores bundled.
- 4574 tests (sin LLM ni servidor externo).

## v0.4.3 (2026-06-04) — Robustez de subagentes, contexto y personalización de agentes

Bloque de robustez y visibilidad: confusión PDF/web corregida, compactación a mitad de
turno, delegación consciente de agentes, capa de personalización por-agente, timeout de
subagentes por inactividad, alineación del TUI, `/kill` instantáneo y VIM 3.1.

Tres correcciones derivadas de una sesión real (búsqueda + descarga de un PDF): el
agente confundía el contenido descargado con un mensaje nuevo del usuario, la
compactación a mitad de turno reimprimía un mensaje obsoleto, y el LLM no sabía qué
agentes especializados tenía disponibles para delegar.

### Búsqueda/descarga — el contenido externo ya no se confunde con el usuario

- **Resultados de tools tipo documento etiquetados.** `web_fetch`, `pdf_extract_text`,
  `doc_read` y `doc_extract_metadata` inyectaban su texto sin marca; un modelo débil,
  tras descargar p.ej. un PDF, respondía «¡Hola! Veo que has compartido un PDF…
  ¿en qué puedo ayudarte?» como si la conversación empezara de cero, y el turno
  terminaba. Ahora `_postprocess_tool_result` (`agent/loop.py`) antepone una cabecera
  («es SALIDA DE HERRAMIENTA, NO un mensaje nuevo del usuario — continúa la tarea»)
  con el origen (URL/fichero). Va al principio para sobrevivir a la truncación.
- **Hint reactivo de «arranque en frío».** Si el agente ya usó tools en el turno y su
  último texto es un saludo/petición de instrucciones de cero (`_COLD_START_RE` en
  `agent/loop_helpers.py`), `_turn_guidance` lo reorienta a la tarea en curso.

### TUI — Compactación a mitad de turno muestra el mensaje REAL más reciente

- **Corregido el «último mensaje del agente» obsoleto al compactar.** `_last_response`
  solo se fijaba en `_turn_finish` (fin de `run()`); con auto-continue, la compactación
  a mitad de turno mostraba el mensaje del `run()` *anterior* — y en la 2ª/3ª
  compactación de un mismo turno repetía el de la 1ª. Nuevo `_last_agent_msg`,
  actualizado por iteración con el último bloque de texto; `_show_compact_reset`
  (`ui/loop_tui.py`) lo usa (fallback a `_last_response`). Cumple «mostrar solo el
  último bloque». test_13 `TestShowCompactReset`, test_81.

### TUI — alineación del ● de texto de los subagentes

- **Corregida la desalineación del `●` de los subagentes.** Los subagentes no tienen
  live block (sus callbacks son `None`), así que su `●` de texto caía en la rama
  `console.print` directa de `_turn_display_bullet` → columna 0, desalineado respecto a
  sus propias líneas de tool (`  │  …`). Nuevo `_render_subagent_bullet` (`agent/loop.py`)
  renderiza el `●` y su continuación vía `self._print`, que añade el prefijo `│` y
  respeta el presupuesto `_MAX_SUB_LINES`. Ahora todo el bloque del subagente comparte
  la columna `│`.
- **Avisos de retry XML** (thinking agotado / XML malformado / parcial recuperado) pasan
  por el nuevo helper `_notice`, que indenta para el agente principal y añade `│` para
  subagentes — antes se imprimían en columna 0 dentro de un subagente. test_22
  `TestSubagentBulletAlignment`.

### Subagentes — bash ya no intenta ejecutar el workspace de identidad como cwd

- **Corregido el `workdir` de las tools del subagente.** El subagente construía su
  registry con `build_registry_fn(sub_config.workspace, …)`, es decir, fijaba como
  directorio de trabajo de `bash`/`python_exec`/`workspace_remember` su **workspace de
  identidad** (`~/.oocode/workspace/<id>`), que además llegaba con `~` literal sin
  expandir. Resultado: cada `bash` fallaba con
  `[Errno 2] No such file or directory: '~/.oocode/workspace/coding'`. Ahora usa el
  **`project_dir` del padre** (expandido), igual que el agente principal — el subagente
  trabaja en el mismo proyecto, no en su carpeta de identidad (`agent/subagent.py`).
- **Defensa en `bash_execute`** (`tools/bash.py`): el `workdir` se normaliza con
  `expanduser`/`expandvars` y, si la ruta no existe, cae a `None` (cwd del proceso) en
  vez de hacer crashear a `Popen`. Un `~` o ruta mal formada nunca vuelve a romper bash.
- `workspace.manager.agent_role` también expande `~` al leer `IDENTITY.md`.
  test_19 `TestBashWorkdirRobustness`/`TestSubagentToolWorkdir`.

### Workspaces — capa de personalización por-agente (TOOLS.md / AGENTS.md)

- **El usuario puede personalizar usos de herramientas y delegación sin tocar
  código.** Modelo en capas: el código mantiene la base invariable de disciplina y
  seguridad (`SYSTEM_RULES` + enforcement en `tools/bash.py`); encima, cada agente
  carga la sección **`## Notas`** de su `TOOLS.md` (preferencias de tools) y `AGENTS.md`
  (preferencias de delegación). `WorkspaceManager.load_mini_context()` las incluye en el
  system prompt vía el helper `_extract_section` (filtra los placeholders de plantilla y
  acota a 1500 chars), así que **no cuesta tokens hasta que el usuario personaliza**.
  Antes, editar esos ficheros no surtía efecto en el modo `mini` por defecto.
- Plantillas `workspace/templates/TOOLS.md` y `AGENTS.md` ganan una sección `## Notas`
  con guía de qué escribir. El roster de agentes sigue generándose dinámicamente en
  `_system_prompt` (lee el `Rol` de cada `IDENTITY.md`). test_81
  `TestWorkspaceCustomizationLayer`.
- **CLAUDE.md** documenta el flujo de arranque completo: agente por defecto `main`,
  los 7 ficheros del workspace, modos de contexto `mini` (default) vs `full`, los dos
  sistemas de memoria (workspace vs semántica) y el trust-check de `OOCODE.md`.

### Orquestación — el LLM sabe qué agentes hay y delega mejor

- **Especialidades de agentes expuestas al LLM.** Los schemas de `spawn_subagent`,
  `create_team` y `spawn_fanout` listaban solo IDs (`"main", "webcrawler"`) sin decir
  para qué sirve cada uno, así que el modelo no sabía, p.ej., que `webcrawler` es
  idóneo para búsquedas web. Ahora incluyen el **Rol** de cada agente, leído de su
  `IDENTITY.md` (helper público `workspace.manager.agent_role`, reutiliza
  `_extract_md_field`; `SubAgentRunner._agents_descr` cacheado). Además, el system
  prompt gana una sección **«Agentes disponibles para delegar»** (solo con >1 agente y
  no-subagente) para que el modelo evalúe la delegación de forma genérica, sin prompts
  específicos del backend. test_81.

### Subagentes — Timeout por paso/petición al LLM, no por tiempo total

- **El watchdog de timeout de subagentes ahora mide INACTIVIDAD, no tiempo total.**
  Antes, `subagents.defaultTimeout` (y `timeout_seconds`) disparaba un `kill_event`
  con `ev.wait(secs)` one-shot: mataba el subagente al alcanzar ese tiempo TOTAL,
  aunque estuviera progresando — una tarea larga y legítima se detenía «por acumular
  tiempo». Ahora el watchdog mata el subagente **solo si un paso pasa `secs` sin
  progreso**. El `AgentLoop` emite `sub.heartbeat()` (vía `_subagent_heartbeat`) al
  iniciar cada iteración, al recibir la respuesta del LLM y tras cada tool, así que
  el timeout es efectivamente **por petición al LLM / paso**: un subagente que avanza
  de forma sostenida no se detiene aunque la tarea completa dure mucho más; solo se
  mata si una sola petición o tool se cuelga más de `secs`.
- Mensaje de timeout actualizado: «subagente sin progreso» + texto que aclara que es
  por paso, no por tiempo total. `ActiveSubAgent.last_activity` + `heartbeat()` nuevos.
- Descripciones de config (`defaultTimeout`) y de los schemas `timeout_seconds`
  (`spawn_subagent`/`spawn_fanout`) reescritas. Sin cambios de formato del JSON.
  Tests: test_subagent_integration `TestInactivityWatchdog`.

### TUI — Recuperar el último mensaje tras compactar

- **El último mensaje del agente se re-muestra tras la compactación.** La
  compactación limpia el área visible del TUI; si saltaba justo después de que el
  agente terminara (p.ej. mostrando un resumen final que preguntaba si continuar),
  ese mensaje se perdía de vista y el usuario respondía a ciegas. Ahora
  `_show_compact_reset` (`ui/loop_tui.py`) re-imprime `_last_response` —que sigue
  vivo en contexto, la compactación no lo borra— renderizado igual que en el turno
  (Markdown, sangría 2), bajo el aviso «último mensaje del agente (antes de
  compactar)». Robusto si `_last_response` está vacío o sin inicializar. Solo TUI
  (el WebUI conserva la conversación en el DOM). test_13 `TestShowCompactReset`.

### Extensión VIM v3.1.0 — Streaming real y paridad con TUI/WebUI

La extensión de VIM/Neovim se conectaba mediante un flujo roto: mantenía un
stream SSE *y* enviaba los mensajes por `send_sync`, pero ambos acababan en
sesiones Flask distintas, así que el panel apenas mostraba el resultado final y
nunca el streaming en vivo. Esta versión lo arregla y lo alinea con el WebUI.

#### Arreglo central — sesión compartida SSE ↔ envío

- **Cookie de sesión establecida antes del stream** — un curl SSE persistente
  nunca vuelca el cookie jar (libcurl lo escribe al terminar la transferencia,
  y el stream no termina). Ahora el plugin hace primero una petición que
  COMPLETA (`GET /api/chat/status`) para fijar la cookie; luego el SSE y el
  `POST /api/chat/send` comparten `sid` y los eventos llegan a la cola correcta.
- **Envío vía `/api/chat/send` (fire-and-forget) en modo streaming** — en lugar
  de `send_sync`. Todos los eventos (text, tools, plan, subagentes, done) fluyen
  por el stream ya abierto, como en el navegador. `send_sync` queda solo como
  fallback (`g:oocode_stream=0` o VIM sin `+job`), sin un SSE compitiendo por la
  misma cola.

#### Paridad de eventos con el WebUI

- Nuevos handlers SSE: `status`, `preflight`, `plan_progress`, `subagent_start`,
  `subagent_done`, `embed_flash`, `inference_done`, además de los previos.
- **Subagentes** — cabecera del subagente y sus líneas (texto + tools) prefijadas
  con `│`, igual que el bloque dedicado del TUI/WebUI.
- **Texto intercalado en orden** — la prosa del agente se vuelca antes de cada
  evento estructurado (tool/plan/subagente), no acumulada al final del turno.

#### Control del turno (paridad con botones del WebUI)

- **`:OOCodeKill`** (`<Leader>oK`) — interrumpe el turno activo (`POST /api/chat/kill`).
- **`:OOCodeElevated [modo]`** (`<Leader>oe`) — cicla/establece `ask|off|on|full`.
- **Guard de turno** — no se solapan envíos; si el agente está ocupado avisa.
- **Watchdog** (`g:oocode_turn_timeout`, 360 s) — cierra el turno si el stream
  enmudece, para que el prompt no quede colgado en "Pensando…".

#### Config nueva

- `g:oocode_stream` (1) — streaming SSE vs `send_sync` bloqueante.
- `g:oocode_turn_timeout` (360) — timeout del watchdog del turno.

### TUI — Render de orquestación y contexto del subagente

- **El `task` de `spawn_subagent` y `explore` se renderiza como Markdown.** Cuando
  el agente principal delegaba con un `task` multilínea en markdown (contexto,
  listas numeradas, **negritas**…), el header lo volcaba en crudo vía `_esc()` —que
  escapa el markup Rich pero **no** interpreta markdown—, así que aparecía
  `**Contexto actual:**`, `- bullets`, etc. literales, escapando al formato de la
  conversación. Ahora la 1.ª línea del task va inline en el header (`● spawn_subagent
  💬 emoji nombre: …`) y el resto se renderiza como `Markdown` indentado. En
  `explore` además se **escapa** la 1.ª línea (antes iba sin escapar → el markup
  Rich del task se interpretaba). `agent/loop.py` (header spawn) + `agent/subagent.py`
  (header explore).
- **El `% ctx` del panel de subagentes refleja el contexto del SUBAGENTE activo,
  no el del agente principal.** El header del panel («⏵⏵ Subagentes Activos … N%
  ctx») derivaba el `%` de `self._agent_loop.context.stats()`, es decir el contexto
  del agente principal —que ya está en el toolbar de abajo—, no el del subagente en
  ejecución. Ahora toma `ctx_pct` del subagente `running` (o del último que reporte
  contexto); si ninguno ha completado aún su 1.ª petición al LLM, no muestra `%`.
  `ui/app.py:_get_subagent_panel_text`. Cada línea de subagente ya mostraba su
  `ctx_pct` propio; el bug era solo el valor del header.

### Backends — `/kill` aborta el LLM de inmediato (cierre forzado del socket)

- **`/kill` ahora interrumpe la generación del LLM al instante, también durante el
  prompt-eval o las pausas de generación.** El watchdog de kill cerraba el cliente
  HTTP (`httpx.Client.close()`), pero `close()` **no** desbloquea un `read()` colgado
  sobre una conexión en uso si el servidor está en silencio (p.ej. Ollama evaluando
  un prompt grande o pausando entre tokens). El hilo lector quedaba bloqueado en
  `recv()` y Ollama mantenía el request vivo (GPU ocupada) hasta que escribía o
  terminaba; el siguiente mensaje quedaba en cola tras esa generación «zombi». Ahora
  `kill_stream()` hace primero `shutdown(SHUT_RDWR)` del socket subyacente del stream
  activo (`api.base.force_close_httpx_sockets`): el `recv()` retorna de inmediato y
  el servidor detecta la desconexión y aborta la generación. Aplicado a los tres
  backends httpx: Ollama (`self._client._client`), OpenAI (`self._client`) y Anthropic
  (`self._client._client` del SDK). El helper es tolerante a la versión de httpx (si
  la estructura interna del pool cambia, no lanza). Tests: `TestForceCloseHttpxSockets`
  en `test_71_api_backends.py` (incl. integración con httpx real + servidor en silencio).

### `/kill` y `/kill all` — matar turno + subagentes + equipos al momento

- **`/kill` ahora mata también los subagentes y equipos activos, no solo el turno
  principal.** Antes solo ponía `_kill_requested` en el loop principal; si había un
  subagente corriendo (el padre bloqueado en `spawn_subagent`→`join`) o un equipo en
  marcha, `/kill` no surtía efecto hasta que terminaban. Nuevo `AgentLoop.request_kill()`
  centraliza el corte: marca `_kill_requested`, aborta el LLM en vuelo (socket, ver
  arriba) y dispara `subagent_runner.kill_all()`. Como los subagentes comparten el pool
  del cliente del padre, el cierre del socket también aborta sus `chat_sync` en vuelo;
  su bucle ve `_ext_kill` (nuevo check tras la llamada al LLM, además del de inicio de
  turno) y para al momento. Cableado en TUI (`/kill`, `Ctrl+C`), slash (`ui/commands.py`)
  y WebUI (`POST /api/chat/kill`, botón Kill) — paridad total.
- **Los miembros de un equipo (`run_team`) ya son matables.** `Team.execute` llamaba
  `runner.run()` **sin** `kill_event` ni registro, así que los miembros de equipo eran
  **inmatables** (no estaban en `_registry` y su `_ext_kill` era `None`). Ahora cada
  miembro se registra como `ActiveSubAgent` con su propia `kill_event`, por lo que
  `kill_all()` los alcanza y además aparecen en `/subagents` y en el panel de subagentes.
- **`/kill all`** = `/kill` + deshabilitar todos los jobs del scheduler + resetear las
  tareas `wip → todo`. El mensaje resume qué se detuvo (subagentes, jobs, tareas).
- **Mensaje correcto de kill manual vs timeout.** Cuando `kill_all` mataba un subagente
  de `spawn_subagent`, el closure lo reportaba como «Timeout». Ahora distingue: el
  watchdog marca `sub.error="Timeout: …"`; el kill manual no, así que muestra
  «Detenido por el usuario». Tests: `test_80_kill_all.py`.

### Tests

- 4482 tests (antes 4457): `TestInactivityWatchdog` (subagentes), `TestShowCompactReset`
  (recuperación de mensaje), `test_79_subagent_task_markdown` (render markdown del
  task de orquestación + ctx del panel), `TestForceCloseHttpxSockets` en
  `test_71_api_backends` (abort del LLM por cierre de socket, con integración httpx real)
  y `test_80_kill_all` (request_kill + miembros de equipo killables). La extensión VIM
  se validó end-to-end contra la WebUI.

## v0.4.2 (2026-06-03) — Flujo de conversación multidominio + paridad TUI/WebUI

OOCode es multi-agente: el usuario empieza con un agente `main` (asistente de código) pero puede crear agentes de cualquier dominio (oficina, seguridad, investigación web, IoT, datos…) con `/agent new` y los ficheros `.md` de su workspace. Esta versión hace que el flujo de conversación —preflight, planificación, anuncios de acción, narración de equipos— sea coherente para **cualquier dominio**, no solo programación, y alinea TUI y WebUI.

### Orquestación

- **Tools de orquestación fuerzan modo secuencial** — `spawn_subagent`, `spawn_fanout`, `create_team`, `run_team` y `explore` (`_ORCHESTRATION_TOOLS`) ya no se paralelizan en el `ThreadPoolExecutor`. Antes, al batchear `spawn_subagent` con `grep_code`/`read_file` en un mismo turno, la cabecera y el streaming `│` del subagente quedaban "encerrados" en el bloque anterior. Para paralelismo real se usa `spawn_fanout`/`create_team`.

### Flujo de conversación agnóstico de dominio

- **`SYSTEM_RULES` con núcleo neutral** — el ciclo de trabajo (Clasifica → Reúne contexto → Actúa → Verifica → Finaliza) ahora es aplicable a cualquier dominio; la disciplina de código (explorar con grep/lsp, `run_tests`, ficheros grandes, edición segura) vive en un bloque condicional **"Cuando trabajes con código"**.
- **Hints dinámicos sin asumir edición de código** — el aviso de "escrituras sin tests" solo se dispara si se tocó código real (detección por extensión, no por tipo de agente); los avisos de exploración sin acción usan lenguaje neutral. Un agente de ofimática que genera un `.docx` ya no recibe avisos de tests.
- **Frases de preflight neutras + nuevos dominios** — las frases genéricas ya no asumen "código"/"módulo"; añadidos dominios `web` (investigación/crawl) y `data` (análisis/SQL).
- **Verbos del live block para tools MCP** — el indicador "●" muestra verbos de dominio para tools de oficina/email/IoT/datos/web/seguridad ("Generating…", "Sending email to…", "Querying…", "Controlling…") en vez de un genérico.

### Agentes y equipos

- **`/agent new` personaliza la persona por dominio** — clasificación automática del dominio (código/oficina/seguridad/IoT/web/datos/DevOps); el prompt de personalización por LLM es consciente del dominio (no asume programación) y hay un fallback determinista (`SOUL.md` adaptado al dominio) cuando no hay LLM disponible.
- **Narración de equipos** — regla explícita para anunciar la composición del equipo antes de `create_team`/`run_team`/`spawn_fanout` y para sintetizar qué aportó cada agente antes de cerrar la tarea.

### WebUI

- **Página de configuración consciente del backend** — `/config` refleja el bloque `api` unificado (`type`/`key`/`host`/`extraHosts`/`embedHost`/`subagentRouting`/retry) y los campos de subagentes (`autoContMax`/`inferenceTimeout`/`defaultTimeout`).
- **Hooks de subagente visibles en su bloque** — en el dispatch paralelo, el canal de impresión de hooks (`threading.local`) se reinyecta en cada hilo worker, así los hallazgos de `interface_change_detector`/lint/verify de un subagente llegan a su bloque (antes caían al fallback de consola y se perdían).
- **Tarjetas de descarga solo para entregables** — aparecen para documentos ofimáticos/PDF (lo que el usuario pide producir), no para ediciones de código ni ficheros temporales.
- **Status bar única (paridad con el TUI)** — eliminada la barra de estado duplicada (arriba y abajo mostraban agente/modelo/ctx); ahora hay una sola barra, como el toolbar del TUI.

#### Refinamientos del flujo de conversación WebUI (2026-06-04)

Principio rector: **lo que es estado va en la barra de estado; lo que es contenido va en la conversación.**

- **Status bar reubicada bajo el prompt** — orden de arriba abajo: indicador "Pensando" → prompt → team-bar → status bar (agente/modelo/ctx/indicadores) → filas de detalle MCP/LSP. Antes la status bar quedaba al fondo, por debajo de MCP/LSP; ahora la línea principal va arriba y el detalle MCP/LSP debajo, igual que el toolbar del TUI.
- **Team-bar de una sola línea** — la cabecera de equipo muestra una línea compacta `📋 Agente principal 💬 💻 Subagente · N subagente(s)`. Se revirtió el detalle multilínea por subagente (tarea/elapsed/ctx%) que **desbordaba** la barra de estado (la tarea podía ocupar párrafos enteros). Ese detalle largo ahora vive en el **bloque del subagente dentro de la conversación**.
- **Tarea del subagente en su bloque** — al arrancar un subagente, su tarea encomendada se siembra al principio de su bloque en la conversación (no en el status), donde se acumulan también su plan, su texto y sus herramientas.
- **Eliminado el bloque de herramienta huérfano "◐ Subagent"** — `spawn_subagent` ya no emite un `tool_start` del agente principal en WebUI: se representa con `subagent_start` + su propio bloque. Antes se creaba un bloque de herramienta que nunca se cerraba (el `tool_done` se convierte en `subagent_done`), quedaba colgado y provocaba que textos del subagente se salieran de su bloque.
- **La barra "Pensando" ya no muestra títulos de herramientas** — es estado puro (palabras ciclantes + frases de preflight); el detalle de cada herramienta aparece en su bloque dentro de la conversación, no en el prompt.
- **Limpieza** — eliminada la rama muerta del evento `preflight` (referencias a IDs inexistentes) y corregido el chequeo de visibilidad del indicador "Pensando" al pausarse el streaming.

#### Historial de prompt y sesiones compartidos TUI ↔ WebUI (2026-06-04)

- **Mismo historial de input del prompt** — el WebUI escribe y **lee** el mismo `~/.oocode/history` que el TUI (formato `prompt_toolkit FileHistory`). El recall con flecha arriba ahora coincide entre ambos y sobrevive a recargas de página (antes el WebUI usaba un historial en memoria que se perdía al recargar). Helpers compartidos `append_input_history`/`load_input_history` en `agent/session.py`.
- **Formato compatible y sin contaminar** — los mensajes **multilínea** se guardan con prefijo `+` por línea (antes solo la primera línea lo llevaba, corrompiendo la entrada para el TUI) y **ya no se escribe la respuesta del agente** en el historial de input (solo lo que teclea el usuario). `send_sync` (vim/CLI) también alimenta el historial compartido.
- **Recuperación de sesiones en el WebUI** — el botón *Cargar* del panel 📚 Sesiones ahora **restaura de verdad** la sesión (nuevo `POST /api/chat/load_session`): reusa `AgentLoop.restore_session` (igual que el TUI) sobre el mismo JSONL y re-renderiza la conversación. El slash `/session <id>` también funciona en el WebUI (antes se enviaba al LLM como mensaje y el botón solo mostraba una instrucción que no hacía nada).

### Robustez de edición

- **Anti-bucle unificado en ediciones** — los fallos de modificación del mismo fichero en un turno (PRE-EDIT fallido de `edit_file`, regex sin coincidencias, llamada duplicada) ahora cuentan juntos y escalan: 1.º indica leer y copiar literal; 2.º **inyecta el contenido real del fichero** (ground truth) y avisa de que el cambio puede estar ya aplicado; 3.º para en seco. Corta el bucle típico `edit → regex → write` que no avanzaba tras una compactación (antes solo escalaban los `regex_replace` sin coincidencias; los `edit_file` y los duplicados no contaban).

#### Streaming del subagente en el TUI (2026-06-04)

- **Presupuesto de líneas `│` del subagente ahora es por turno (no por ejecución completa)** — el streaming `│` del subagente tiene un cap de líneas (`_MAX_SUB_LINES`, 12) pensado **por turno**, pero solo se reseteaba una vez al arrancar el subagente. Un subagente multi-turno (auto-continue) consumía su presupuesto en el primer turno, imprimía `… buffer lleno` y **congelaba** — el usuario veía las líneas más antiguas y dejaba de ver toda la actividad posterior. Ahora el contador se refresca al inicio de cada turno: cada turno muestra líneas nuevas y las antiguas hacen scroll hacia arriba en el buffer de salida, como era la intención original.

### Tests

4457 tests (sin LLM ni servidor externo).

---

## v0.4.1 (2026-06-03) — Consistencia multi-backend + correcciones

Versión de pulido que hace que los backends OpenAI-compatible y Anthropic (experimentales, introducidos en v0.4.0) funcionen de forma coherente en **todos** los comandos y diagnósticos, no solo en el bucle del agente.

### Correcciones

- **Bug: `doc_create` fallaba con `'str' object has no attribute 'get'`** (`mcp_servers/home_office_assistant.py`) — cuando el LLM pasaba `content_blocks` como string JSON, bloques individuales como strings sueltos, `metadata`/`sheets`/`slides` como JSON, o un dict único en vez de lista. Nuevos helpers `_coerce_json` y `_norm_blocks` normalizan la entrada antes de procesarla (envuelven strings sueltos como párrafos, parsean JSON, descartan tipos inválidos).
- **Bug: mensaje "Subagente detenido por el usuario" espurio** — el watchdog de timeout (`subagents.defaultTimeout` o `timeout_seconds` del LLM) disparaba `kill_event` y `_turn_loop_guard` imprimía siempre "detenido por el usuario" sin distinguir un timeout automático de un kill manual. Ahora el guard inspecciona el `ActiveSubAgent` y muestra el motivo real (timeout vs. usuario). El mensaje de retorno al LLM usa el timeout efectivo (`_eff_timeout`), no el argumento original.
- **Fuga de hilos watchdog** — en una finalización normal el `kill_event` nunca se seteaba, así que el hilo watchdog quedaba dormido el `secs` completo (acumulación con `defaultTimeout` alto). El worker ahora hace `kill_ev.set()` en el `finally` para liberarlo de inmediato.
- **Embeddings apuntaban al servidor equivocado con backend no-Ollama** — `effective_embed_host` devolvía la URL del servidor OpenAI/Anthropic (porque el campo unificado `api.host` alimenta `ollama_host`), pero las embeddings SIEMPRE usan el protocolo Ollama. Ahora cae al host local de Ollama (`localhost:11434`) cuando `api.type != "ollama"` y no hay `embedHost` dedicado.
- **`/switch` usaba `ollama_host` para embeddings** — único `EmbeddingClient` del repo que no usaba `effective_embed_host`; corregido. Con backend no-Ollama o `embedHost` dedicado, las embeddings del agente conmutado apuntaban al servidor equivocado.
- **`_personalize_workspace_with_llm` rompía con backend no-Ollama** — usaba `ollama.Client().chat()` directo; migrado a `build_client(config)` + `chat_sync()` (funciona con cualquier `api_type`).

### Mejoras

- **`/doctor`, `--doctor` y doctor WebUI conscientes del backend** — nuevo helper compartido `_doctor_llm_backend_checks` (elimina ~60 líneas duplicadas). Con backend Ollama: lista modelos, verifica modelo/fallback/hosts extra. Con OpenAI: reporta tipo/baseUrl/key + conectividad ligera a `/models`. Con Anthropic: reporta tipo/key (falla si falta) + paquete instalado. Las embeddings se verifican siempre contra `effective_embed_host` (protocolo Ollama). Antes daban un FALLO falso de Ollama con cualquier backend no nativo.
- **`/config`, `/settings` y `/model` conscientes del backend** — `/config show` añade sección "Backend (api)" (type/host/key enmascarada/baseUrl/embedHost según backend) y sección "Subagentes" (que no se mostraba); `/settings` muestra fila "Backend"; `/model` indica el backend; `/model <nombre>`, `/config edit` y `/models` ya no sondean Ollama inútilmente con backend no nativo.
- **`subagents.inferenceTimeout` ahora aplica siempre** — nuevo campo de runtime `inference_timeout_override` con máxima prioridad en `model_timeout` (override > per-model > fallback > 0). Antes solo surtía efecto si había un modelo de fallback configurado.

### Infraestructura

- **Instalador** — el `oocode.json` por defecto que escribe `install.sh` usa el bloque `api` unificado (no el legacy `ollama`) e incluye el bloque `subagents`.
- **`completion.phrase` despromocionado** — el bloque `completion` es un ajuste **interno** (señal de fin de turno + control de auto-continue), no una personalización de las respuestas del agente. Ya **no se materializa** en `oocode.json` (`save()` no lo escribe) ni se muestra en `/config`. `load()` lo sigue respetando si un agente multi-idioma lo añade a mano, como *escape hatch* para que la detección de fin de turno funcione en idiomas distintos de ES/EN.
- **Limpieza de código muerto y duplicaciones** — barrido tras los refactors de `api/`/`config/`:
  - Eliminados 3 ficheros `.tmp` huérfanos (escrituras atómicas interrumpidas) y la property muerta `OllamaBackend.raw_client`.
  - Eliminadas funciones muertas: `MemorySystem._auto_suggest_memories`, `RuntimeSettings.summary_line`, `AgentLoop._chat_kwargs` (resto del path `client.chat()` previo a la abstracción de backends), más 5 bloques de código comentado.
  - **Nuevo `api/ollama.py::ollama_model_names`/`list_ollama_models`** — fuente única para listar/parsear modelos Ollama; consolida 6 copias (`/doctor`, `/models`, `/fast`, `/config`, selector de modelo, gateway-status).
  - **Nuevo `agent/services.py`** (`build_workspace_manager`/`build_embedding_client`/`build_memory_system`) — factories del stack de agente que unifican el bootstrap del TUI, WebUI y `/switch`. Elimina la divergencia que había causado el bug de embeddings en `/switch`.
- **Tests** — 4374 tests (100% pasando, +16 en `tests/test_72_services_and_model_helpers.py`).

---

## v0.4.0 (2026-06-02) — Multi-backend API + HTTP Client MCP

### Nuevas características

- **Multi-backend LLM** (`api/`) — OOCode ya no está atado a Ollama. Nuevo módulo `api/` con tres backends intercambiables seleccionables en `oocode.json`:
  - `api/ollama.py` (`"type": "ollama"`) — comportamiento anterior, sin cambios
  - `api/openai.py` (`"type": "openai"`) — compatible con cualquier servidor OpenAI-API (llama.cpp, LM Studio, vLLM, koboldcpp, OpenAI cloud); usa `httpx` directo sin dependencia del paquete `openai`
  - `api/anthropic.py` (`"type": "anthropic"`) — API de Anthropic con conversión automática de mensajes y tool schemas; soporta streaming y thinking blocks
  - `api/base.py` — tipos normalizados `Chunk`, `ToolCall`, `Response`, `BackendClient` ABC; misma interfaz de atributos (`.function.name`, `.function.arguments`, `.model_dump()`) para compatibilidad con el código existente
  - `build_client(config)` factory en `api/__init__.py` — el tipo se lee de `oocode.json`: `{"api": {"type": "openai", "key": "...", "baseUrl": "http://localhost:8080/v1"}}`
  - Subagentes heredan automáticamente `api_type`, `api_key`, `api_base_url` del config padre
  - `ollama_client=` en `AgentLoop.__init__` sigue funcionando como alias deprecado

- **HTTP Client Assistant MCP** (`mcp_servers/http_client_assistant.py`) — nuevo servidor MCP con 17 herramientas para desarrollo y debugging de APIs REST:
  - `http_request` — GET/POST/PUT/PATCH/DELETE con headers, auth, body, timeouts
  - `http_get` — migrado desde oocode-assistant (oocode-assistant: 54→53 tools)
  - `http_headers`, `http_auth` (bearer/basic/oauth2), `http_upload` (multipart)
  - `response_diff` — compara dos respuestas HTTP campo a campo
  - `openapi_validate` — valida request/response contra schema OpenAPI (JSON Schema)
  - `curl_import` — convierte un comando curl a una llamada http_request
  - `websocket_send` — envía mensajes WebSocket (requiere `websocket-client`)
  - `sse_listen` — escucha un endpoint SSE y recoge N eventos
  - `mock_server_start` / `mock_server_stop` — servidor HTTP mock local en un thread daemon
  - `http_health_check` — verifica disponibilidad de endpoints con métricas de latencia
  - `graphql_query` — ejecuta queries GraphQL con soporte de variables
  - `jwt_decode` — decodifica JWT (sin verificación de firma, para debugging)
  - `http_batch` — ejecuta múltiples requests en paralelo
  - `http_history` — historial de requests de la sesión con estadísticas
  - Activar: `{"mcp": {"httpClientAssistant": {"enabled": true}}}`

- **`/mcp` muestra todos los bundled** — el comando `/mcp` ahora lista los 8 servidores MCP bundled aunque estén desactivados, con estado `●/○`, counts de tools/resources/prompts y flag `enabled/disabled`. Antes solo mostraba los servidores corriendo.

### Correcciones

- **Bug: devops-assistant mostraba 0 prompts y 0 resources** — `mcp_client.py` usaba `not self._capabilities.get("resources")` que evaluaba el dict vacío `{}` como falsy; corregido a `"resources" not in self._capabilities`; afectaba a todos los servidores con capabilities vacías

### Optimizaciones

- **SYSTEM_RULES −51% tokens** — reescritura de las reglas del sistema desde ~3795 a ~1840 tokens; secciones de planificación convertidas a tablas compactas; reglas de comunicación deduplicadas; todos los comportamientos críticos preservados

### Infraestructura

- `tools/registry.py`: nuevo método `tool_schemas()` (renombrado de `ollama_schemas()`); `ollama_schemas()` mantenido como alias de compatibilidad
- `agent/subagent.py`: usa `backend_client=` en lugar de `ollama_client=` al instanciar AgentLoop
- **Tests** — 4375 tests (100% pasando, +49 en `tests/test_71_api_backends.py`)

---

## v0.3.10 (2026-06-02) — Subagentes: auto-continues y timeout configurables

- **Bug: subagente para antes de terminar la tarea** — `auto_continue_max=8` del agente principal se aplicaba también a los subagentes; tareas complejas de 3-4 pasos agotaban los 8 turnos y devolvían resultado parcial; el agente principal interpretaba "herramienta ejecutada" como "tarea completada". Nuevo campo `subagents.autoContMax` (default: 16) en `oocode.json` — sobreescribe `auto_continue_max` solo para subagentes, sin tocar el límite del agente principal
- **Bug: timeout de inferencia de 120s no configurable desde el bloque de subagentes** — `fallback.timeoutSeconds=120` (segundos sin tokens antes de usar fallback) se aplicaba igual a subagentes; inferencias largas (razonamiento complejo) provocaban abort prematuro; no era configurable desde el bloque `subagents` de `oocode.json`. Nuevo campo `subagents.inferenceTimeout` (default: 0 = hereda de `fallback.timeoutSeconds`) — permite fijar un límite de inferencia más alto para subagentes
- **Nuevo campo `subagents.defaultTimeout`** — timeout de tarea máximo por subagente en segundos (0 = sin límite); cuando el LLM llama `spawn_subagent` sin especificar `timeout_seconds`, se aplica este default; aplica también a `spawn_fanout`; `timeout_seconds` explícito del LLM siempre tiene precedencia
- **Robustez: guards `isinstance(int)` en overrides de config** — los tres nuevos overrides usan `getattr + isinstance` para que tests con `MagicMock` sigan pasando sin modificar fixtures existentes
- **Tests** — 3999 tests (100% pasando, +15 tests nuevos en `TestSubagentsConfigNewFields`, `TestSubagentRunAppliesConfig`, `TestSpawnSubagentDefaultTimeout`)

## v0.3.9 (2026-06-02) — WebUI beta

- **WebUI promovido a beta** — 122 tests al 100%; paridad de características completa con el TUI; listo para uso en producción desde navegador y extensiones de editor
- **WebUI: evento SSE `inference_done`** — `loop_webui.py` emite `inference_done` al finalizar cada turno; el chat muestra "⚡ Inferencia completada." y limpia el indicador de pensando; replica el comportamiento del TUI
- **WebUI: tarjetas de archivo siempre visibles** — eliminada la dependencia de la clase `.expanded`; el botón de descarga es ahora visible independientemente del estado del bloque de tools (`display:flex !important`)
- **WebUI: escape correcto de guiones bajos en rutas** — rutas de fichero con `_` (p. ej. `report_2026_final.docx`) protegidas antes del escape HTML para evitar que sean interpretadas como cursiva en Markdown
- **WebUI: icono `◐` correcto durante ejecución** — `_updateToolBlockHeader` solo sobreescribe el header con el resumen cuando no hay tools en ejecución; mantiene `◐` visible mientras corren herramientas
- **WebUI: previsualización de imágenes adjuntas** — `appendUserMsg` acepta `images[]` con `previewUrl`; las imágenes adjuntas se muestran inline en el mensaje del usuario
- **WebUI: `api_chat_history` corregida** — eliminado import local incorrecto (`from webui.sessions import _get_or_create_sid`); revertida lógica errónea que leía `~/.oocode/history` (historial readline del TUI) como historial de conversación
- **Compactación de contexto mejorada** — estimación de tokens por tipo de mensaje (tool results 2.5 chars/tok, thinking 4.0, texto 3.5); `compact_threshold` bajado a 0.80; punto de corte busca hacia atrás hasta 5 mensajes para alinear en frontera `user`; tarea original anclada en el resumen (`**Tarea original:**`) para no perderla entre compactaciones; re-condensación LLM del resumen acumulado cuando supera `maxSummaryChars`
- **SYSTEM_RULES: árbol de decisión de planificación 4 niveles** — Nivel 1 (directo ≤2 pasos), Nivel 2 (texto breve sin plan), Nivel 3 (`plan_create` con checklist), Nivel 4 (paralelismo/subagentes/equipos); reemplaza la regla "≥3 pasos → siempre plan"; tabla de paralelismo universalizada para tareas complejas
- **Hint #13 mejorado** — tras ≥5 tool calls exploratorias sin escritura, distingue exploración de módulo único (empuja a ejecución directa Nivel 1/2) vs. multi-módulo ≥3 directorios (empuja a subagentes/spawn_fanout/create_team)
- **WebUI: salida idéntica al TUI** — conversación, bloques de tools y planes con los mismos símbolos (●/│/◐/⎿/◈/✔/◼/◻); fuente monoespaciada; palabras inventadas de pensamiento (`Cavilando…`, `Tokenizando…`, etc.) en la barra de estado superior (no en la conversación); bloque colapsable para tools; `appendPlan`/`updatePlanProgress` con CSS plano estilo TUI
- **WebUI: indicador "Pensando" en barra de estado** — las palabras inventadas del TUI ciclan en `sb-think` (barra superior) junto a la barra de contexto `▱▱▱▱▱▱▱▱▱▱`; eliminado el div en la conversación; durante tools muestra `◐ nombre_tool` en la barra
- **WebUI: página de configuración completa** — expuesta toda la `OOConfig` en 17 secciones: Ollama, Modelo global, WebUI, Contexto/Compactación, Límites de herramientas, RAG, Embeddings, SearXNG, MCP Servers (5 toggles), Hooks, Subagentes, Backups, Snapshots, Logging, Visión, Chat log, Fallback, Apariencia; API GET/POST actualizadas (~50 parámetros)
- **Tests** — 3984 tests (100% pasando, sin LLM ni servidor externo)

## v0.3.8 (2026-05-31)

- **Auditoría de código muerto y duplicados** — revisión integral del código buscando funciones duplicadas, imports muertos y conjuntos de nombres de tools inconsistentes entre módulos
- **Bug: `smart_replace` fuera del guard de dedup** — `self._WRITE_TOOLS` en `agent/loop.py` no incluía `smart_replace`; llamadas repetidas con los mismos args en el mismo turno no se bloqueaban; corregido
- **Bug: `lsp_rename`/`lsp_code_actions` sin hooks** — no estaban en `_ALL_MODIFY_TOOLS` de `tools/hooks.py`; los hooks `lint_after_write`, `lsp_after_write`, `interface_change_detector`, etc. no se disparaban después de un rename o code action de LSP; corregido
- **Refactor: `_fmt_sub_elapsed` eliminada** — duplicado de `_fmt_elapsed` (con formato incompatible) eliminado de `agent/subagent.py`; unificado con `_fmt_elapsed` de `loop_helpers.py`
- **Limpieza: imports muertos** — `_is_write_tool` (sin usar) eliminado de `agent/loop.py`; `sys`, `os`, `_TOOL_LIVE_VERBS`, `_COMPACT_LOCK` (sin usar) eliminados de `ui/loop_tui.py`
- **Refactor: `_write_tool_names` inline** — definición inline de frozenset en `_turn_display_bullet` reemplazada por `self._WRITE_TOOLS`; una sola fuente de verdad para los nombres de write tools
- **TUI: display de replace tools** — `_call_context` para `regex_replace`/`smart_replace`/`bulk_replace` trunca el patrón a la primera línea (55 chars + `…`); elimina la inundación multi-línea antes del diff
- **TUI: preview del live block para edit/replace** — `_make_tool_preview` corrige la clave del arg (`"file"` en lugar de `"path"` para `smart_replace`/`regex_replace`); elimina las líneas `- old`/`+ new` del preview pre-ejecución; el diff coloreado real ya aparece después de la ejecución
- **Tests** — 3984 tests (100% pasando)

## v0.3.7 (2026-05-31)

- **AgentTeam como tool LLM** — `create_team` + `run_team` como herramientas nativas; el agente puede descomponer tareas en subtasks paralelas asignadas a agentes especializados y sintetizar los resultados
- **Flujo de resultados de equipos** — `run_team` inyecta los resultados de cada subagente al agente líder para síntesis; fix de `loop._last_response` para capture_output=False
- **`spawn_fanout`** — nueva herramienta `spawn_fanout(chunks, agent_id)` para análisis paralelo divide-and-conquer; hereda semáforo de concurrencia y timeout
- **Plan ↔ TaskManager sync** — `_plan_tasks` persisten al reiniciar vía `TaskManager` con marcador `__plan__`; visibles en `/task list`; restauración automática al arrancar
- **Timeout por subagente** — `timeout_seconds` en `spawn_subagent`/`spawn_fanout`; watchdog thread con `kill_event.wait()` mata subagentes colgados automáticamente
- **TUI live block mejorado** — `◐ Tool: (path)` y `◐ Bash: $ cmd` inline; diff preview/`Running…` debajo; tools completadas muestran path/cmd; máx 8 líneas `│` antes de `⎿`
- **Limpieza: referencias personales** — eliminadas todas las referencias personales del código; IDs de agentes de ejemplo hardcodeados reemplazados por placeholders genéricos
- **Limpieza: identificadores mixtos** — identificadores mezcla español/inglés en tests (`tarea_rapida`, `tarea_SLOW`…) renombrados a inglés consistente
- **Tests** — 3984 tests (100% pasando)

## v0.3.6 (2026-05-31)

- **TUI refinements** — `_update_live_bullet_cb` muestra la acción de la herramienta activa en el `●` pulsante; `●display(ctx)` como encabezado de tool; `⎿` sin `◐`; resumen compacto normalizado ("Searched for", "lines" en inglés)
- **WebUI print pollution fix** — `_print()` TUI-específicos (preflight/auto-continue/plan/resume/retry) filtrados con `if not _webui_queue`; JS de `thinking` preserva el label preflight
- **WebUI/TUI callbacks** — TUI sin `invalidate()` en callbacks intermedios del live block (blink timer suficiente); status SSE emitido al inicio de turno; file cards unificadas a `.tui-file-card`
- **Tests** — 3932 tests (100% pasando)

## v0.3.5 (2026-05-31)

- **Configuración completa desde oocode.json** — todos los parámetros internos (chunking RAG, caché embeddings, highWater de contexto) son ahora configurables en `~/.oocode/oocode.json`; eliminados todos los valores hardcodeados
- **Display compacto mejorado** — cada fichero en una línea separada con `│` (U+2502) y `⎿` en el último elemento; símbolo correcto `↻` para compactación en la barra de estado
- **Limpieza de código** — eliminados duplicados funcionales (`_fmt_tokens`, `_progress_bar`, `chunk_with_metadata` standalone); eliminadas 5 entradas no-op en `_TOOL_ALIASES`; unificadas 6 sets de write-tools en `_is_modify_tool()`; eliminado tracking dual `_task_modified_files`
- **Correcciones de robustez** — sincronizado `_RICH_TAG_RE` entre `loop.py` y `app.py`; corregido prefijo `[caché]` visible al LLM; eliminado bloque unreachable en el dispatch de tools; eliminado segundo `keep_alive` pop en `_chat_kwargs`

## v0.3.4 (2026-05-30)

- TUI estilo bloques: `●` sin sangría, `⎿` sin `◐`, resumen compacto
- WebUI + TUI fixes: collapse via `.expanded`, file cards unificadas, status al inicio de turno
- Home Office v5: `doc_create` + `template_path`, checklist/callout/highlight/toc en Word
- Home Office OOXML refactor: gráficas OOXML nativas (sin PNG), diagramas bar/pie/line
- External MCP support: `mcp_manager.py` + `catalog.json`, hot-add sin reiniciar
- WebUI refactorizada en 13 módulos Blueprint
