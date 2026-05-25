# 05 — Sistema de memoria y embeddings

OOCode tiene dos niveles de memoria: el **contexto de conversación** (en RAM, sesión actual) y la **memoria persistente** (en disco, entre sesiones). Este documento cubre la memoria persistente.

## Arquitectura

```
~/.oocode/memory/<agent_id>/
├── MEMORY.md         # índice con nombre, descripción y fecha de cada memoria
├── *.md              # fichero por cada memoria (texto libre + frontmatter opcional)
└── *.emb.json        # vectores de embedding para búsqueda semántica
```

La memoria está separada por agente (`agent_id`), evitando mezcla entre agentes distintos.
La búsqueda semántica usa **embeddings vectoriales locales** generados con Ollama.

## Comandos de memoria

### Listar memorias
```
/mem list
/mem
```
Muestra una tabla con nombre, fecha de creación/actualización y tamaño.

### Búsqueda semántica
```
/mem search <consulta en lenguaje natural>
```
Calcula el embedding de la consulta y recupera las memorias más similares por coseno.
Devuelve los fragmentos relevantes (`snippetChars` chars por resultado, hasta `topK` resultados).

Requiere el modelo de embeddings configurado en Ollama y `memoryEmbedEnabled: true`.

### Ver una memoria
```
/mem show <nombre>
```

### Guardar una memoria
```
/mem save <nombre>
```
El siguiente mensaje que escribas se guarda como memoria con ese nombre.

También puedes pedir al agente directamente:
```
Guarda esto en memoria como "arquitectura-del-proyecto"
```

### Eliminar una memoria
```
/mem rm <nombre>
```
Pide confirmación antes de borrar.

### Reconstruir embeddings
```
/mem rebuild
```
Recalcula los embeddings de todas las memorias. Útil si cambias el modelo de embeddings o activas `memoryEmbedEnabled` después de haber guardado memorias.

### Eliminar todo
```
/mem clear
```
Elimina todas las memorias. Pide confirmación explícita.

## Memoria embebida por vectores

Cuando `memoryEmbedEnabled: true` (por defecto), cada memoria guardada genera automáticamente un fichero `.emb.json` con su vector de embedding. Este vector se usa para:

1. **Búsqueda semántica automática** — en cada turno, OOCode busca memorias relevantes y las inyecta en el system prompt
2. **`/mem search`** — búsqueda explícita en lenguaje natural
3. **Caché de vectores en RAM** — los embeddings se mantienen en memoria para búsquedas rápidas sin disco

El flujo en cada turno es:
1. Calcula el embedding del mensaje del usuario (cacheado si la query no cambia)
2. Compara por similitud coseno contra los `.emb.json` de todas las memorias
3. Recupera las `topK` memorias con similaridad > `similarityThreshold`
4. Inyecta los fragmentos relevantes en el system prompt

Si no hay modelo de embeddings disponible o `memoryEmbedEnabled: false`, la inyección se desactiva y `/mem search` no funciona. Las memorias siguen siendo accesibles vía `/mem list` y `/mem show`.

```
## Memorias relevantes
[memoria-nombre]
...fragmento del contenido...
```

Esto no consume tokens del historial de conversación, sino tokens del system prompt (que se renueva en cada turno).

## Configuración de embeddings

```json
"embeddings": {
  "model":               "nomic-embed-text-v2-moe:latest",
  "maxInputChars":       6000,
  "similarityThreshold": 0.30,
  "snippetChars":        400,
  "topK":                3,
  "memoryEmbedEnabled":  true
}
```

| Campo | Descripción |
|-------|-------------|
| `model` | Modelo de embeddings en Ollama |
| `maxInputChars` | Texto máximo a embedar por memoria |
| `similarityThreshold` | Score mínimo para incluir una memoria (0.0–1.0) |
| `snippetChars` | Caracteres del fragmento por resultado |
| `topK` | Número máximo de memorias recuperadas |
| `memoryEmbedEnabled` | Activar/desactivar búsqueda vectorial en memorias |

## Modelos de embeddings recomendados

```bash
# Multilingüe, buena calidad, 137M params
ollama pull nomic-embed-text-v2-moe:latest

# Rápido, ligero
ollama pull all-minilm

# Inglés, alta calidad
ollama pull mxbai-embed-large
```

## Formato de fichero de memoria

```markdown
# Nombre de la memoria

Contenido libre en Markdown.

Puede incluir código, listas, notas técnicas.
```

Los ficheros se pueden editar manualmente. El índice `MEMORY.md` se actualiza automáticamente.
Al guardar manualmente, ejecuta `/mem rebuild` para regenerar los embeddings.

## Diferencia con el contexto de conversación

| | Contexto | Memoria persistente |
|-|----------|---------------------|
| Duración | Una sesión | Permanente |
| Recuperación | Todo en RAM | Búsqueda semántica vectorial |
| Tokens consumidos | Historial de mensajes | System prompt (~50–400 tok) |
| Gestión | Auto-compactación | Manual con `/mem` |
| Alcance | Sesión y agente | Por agente (compartido entre proyectos) |

## Aislamiento entre agentes y proyectos

Las memorias son **globales al agente** (se comparten entre proyectos del mismo agente).
Para información específica de proyecto usa `workspace_remember` que escribe en `OOCODE.md` del workspace.

```
~/.oocode/workspace/<agent_id>/<proyecto>/OOCODE.md  — notas de proyecto
~/.oocode/memory/<agent_id>/                          — memorias del agente (cross-proyecto)
```
