# 25 — Backends LLM (multi-backend)

> **Nuevo en v0.4.0.** OOCode soporta tres backends LLM intercambiables: Ollama (local), OpenAI-compatible (llama.cpp, LM Studio, vLLM…) y Anthropic (Claude cloud). El backend se configura en `oocode.json` y el agente funciona de forma idéntica con cualquiera de ellos.
>
> ⚠️ **Ollama es el backend estable y soportado.** Los backends **OpenAI-compatible y Anthropic son experimentales**: la integración funciona pero está menos probada (streaming, conteo de tokens y compactación están optimizados para Ollama). Úsalos con esa salvedad.

---

## Configuración rápida

El bloque `api` en `~/.oocode/oocode.json` controla qué backend se usa **y** todos los parámetros del servidor (un único bloque):

```json
{
  "api": {
    "type":             "ollama",                 // "ollama" | "openai" | "anthropic"
    "key":              "",                        // API key (OpenAI / Anthropic; vacío para Ollama)
    "host":             "http://localhost:11434",  // URL del servidor (Ollama host / OpenAI baseUrl)
    "extraHosts":       [],                        // hosts adicionales para subagentes (solo Ollama)
    "embedHost":        "",                         // host dedicado para embeddings (vacío = host principal)
    "subagentRouting":  "round-robin",             // "round-robin" | "primary-only" (solo Ollama)
    "ollamaRetryCount": 2,                          // reintentos en timeout (solo Ollama)
    "ollamaRetryDelay": 3.0                         // delay base entre reintentos en s (solo Ollama)
  }
}
```

> El campo `host` es único: con `type: "ollama"` actúa como host de Ollama; con `type: "openai"` actúa como `baseUrl`. Con `type: "anthropic"` se ignora (solo se usa `key`). Los campos `extraHosts`, `embedHost`, `subagentRouting`, `ollamaRetry*` solo aplican al backend Ollama.

---

## Backend Ollama (por defecto)

El comportamiento original de OOCode. Requiere Ollama instalado y corriendo.

```json
{
  "api": {
    "type":            "ollama",
    "host":            "http://localhost:11434",
    "extraHosts":      [],
    "embedHost":       "",
    "subagentRouting": "round-robin"
  }
}
```

Los campos `host`, `extraHosts`, `embedHost`, `subagentRouting` solo tienen efecto cuando `api.type == "ollama"`.

**Modelos recomendados:**
```bash
ollama pull qwen3.5:9b              # 16 GB VRAM — mejor equilibrio calidad/velocidad
ollama pull qwen2.5-coder:7b        # 8 GB VRAM — especializado en código
ollama pull qwen3:14b               # 24 GB VRAM — máxima calidad razonamiento
ollama pull nomic-embed-text-v2-moe # modelo de embeddings (memoria semántica RAG)
```

---

## Backend OpenAI-compatible

Compatible con cualquier servidor que implemente la API `/v1/chat/completions` de OpenAI:
- **llama.cpp** server (`llama-server --port 8080`)
- **LM Studio** (servidor local en el menu Server)
- **vLLM** (`vllm serve <modelo>`)
- **koboldcpp** (`koboldcpp --api`)
- **Ollama con wrapper OpenAI** (`OLLAMA_OPENAI=1`)
- **OpenAI cloud** (GPT-4o, GPT-4-turbo…)
- **Groq**, **Together AI**, **Fireworks**, **Perplexity** y otros proveedores compatibles

```json
{
  "api": {
    "type": "openai",
    "host": "http://localhost:8080/v1"
  },
  "agents": {
    "defaults": { "model": "llama-3.3-70b-instruct" }
  }
}
```

Para OpenAI cloud:
```json
{
  "api": {
    "type": "openai",
    "key":  "sk-...",
    "host": ""
  },
  "agents": {
    "defaults": { "model": "gpt-4o" }
  }
}
```

> Cuando `host` está vacío con `"type": "openai"`, se usa `https://api.openai.com/v1`. (El campo `host` actúa aquí como `baseUrl`.)

**Requisito:** `httpx` (incluido en `requirements.txt`).

**Parámetros de modelo:** los campos `temperature`, `top_p`, `num_predict` (→ `max_tokens`), `top_k` se adaptan automáticamente al formato OpenAI. Los parámetros específicos de Ollama (`num_ctx`, `keep_alive`, `seed`) se descartan silenciosamente. El límite de salida (`maxTokens` del modelo activo) se inyecta como `max_tokens` en cada petición; el streaming pide `stream_options.include_usage` para obtener el conteo real de tokens.

---

## Backend Anthropic

Conecta directamente con la API de Anthropic para usar los modelos Claude.

```json
{
  "api": {
    "type": "anthropic",
    "key":  "sk-ant-api03-..."
  },
  "agents": {
    "defaults": { "model": "claude-opus-4-8" }
  }
}
```

**Modelos disponibles** (junio 2026):
| ID | Descripción |
|----|-------------|
| `claude-opus-4-8` | Máxima capacidad de razonamiento y código |
| `claude-sonnet-4-6` | Equilibrio calidad/velocidad (recomendado) |
| `claude-haiku-4-5-20251001` | Respuestas rápidas, tareas sencillas |

**Requisito:** `pip install anthropic`.

**Conversión automática:** OOCode convierte el formato interno de mensajes (OpenAI-style) al formato Anthropic antes de cada llamada:
- Mensajes `system` → parámetro `system` de la API
- Tool calls del asistente → content blocks `tool_use`
- Resultados de tools → content blocks `tool_result`
- Tool schemas `{"type":"function","function":{...}}` → `{"name":..., "input_schema":{...}}`

**`max_tokens`:** obligatorio en la API de Anthropic. OOCode usa el `maxTokens` del modelo activo (`models.configs[modelo].maxTokens`); si no está configurado, usa 8192 como fallback.

**Thinking blocks:** el backend procesa los `ThinkingDelta` que emita el modelo, pero el *extended thinking* de Anthropic requiere enviar el parámetro `thinking` (no habilitado por defecto en esta versión). Con thinking deshabilitado los modelos Claude responden de forma estándar sin bloques de razonamiento.

---

## Arquitectura interna

El módulo `api/` implementa una capa de abstracción con tipos normalizados:

```
api/
├── __init__.py      # build_client(config) — factory
├── base.py          # BackendClient ABC, Chunk, Response, ToolCall
├── ollama.py        # OllamaBackend
├── openai.py        # OpenAIBackend (httpx directo)
└── anthropic.py     # AnthropicBackend (SDK anthropic)
```

### Tipos normalizados

```python
@dataclass
class Chunk:
    text:          str   = ""       # texto generado en este fragmento
    tool_calls:    list  = []       # list[ToolCall] — normalizados de cualquier backend
    thinking:      str   = ""       # thinking block (Qwen3/Anthropic)
    done:          bool  = False    # True en el último chunk
    input_tokens:  int   = 0
    output_tokens: int   = 0

@dataclass
class ToolCall:
    function: _ToolFunction         # .name (str), .arguments (dict)

    def model_dump(self) -> dict:   # serialización para mensajes de contexto
        ...
```

`AgentLoop` trabaja exclusivamente con estos tipos — el código del bucle no tiene referencias a `ollama`, `openai` ni `anthropic`.

### Interfaz de BackendClient

```python
class BackendClient(ABC):
    def chat_stream(model, messages, tools, model_params) -> Iterator[Chunk]: ...
    def chat_sync(model, messages, tools, model_params, timeout) -> Response: ...
    def kill_stream() -> None: ...   # interrumpir streaming en curso
    def rebuild(config) -> None: ...  # reconstruir conexión tras kill
    def close() -> None: ...
```

### Añadir un nuevo backend

1. Crear `api/mibackend.py` heredando `BackendClient`
2. Implementar `chat_stream`, `chat_sync`, `kill_stream`, `rebuild`
3. Normalizar tool calls a `ToolCall(function=_ToolFunction(name, arguments))`
4. Añadir rama en `api/__init__.py::build_client()`
5. Añadir campo en `DEFAULT_CONFIG["api"]` de `config.py` si necesitas nuevos parámetros

---

## Subagentes y multi-backend

Los subagentes heredan automáticamente el backend del padre:

```python
sub_config.api_type     = self.config.api_type
sub_config.api_key      = self.config.api_key
sub_config.api_base_url = self.config.api_base_url
```

Si `_parent_client` está disponible (mismo host), el subagente reutiliza la conexión del padre para evitar overhead de reconexión. Si no, construye su propia instancia con `build_client(sub_config)`.

---

## Embeddings

Los embeddings para la memoria semántica (RAG) siguen usando **el protocolo Ollama** independientemente del backend LLM elegido (`EmbeddingClient` envuelve `ollama.Client`).

Resolución del host de embeddings (`config.effective_embed_host`):

| Situación | Host usado |
|-----------|------------|
| `embedHost` configurado | `embedHost` |
| `type: "ollama"` (sin embedHost) | `host` (con `primary-only`, siempre el principal) |
| `type: "openai"` / `"anthropic"` (sin embedHost) | `http://localhost:11434` *(no `host`, que apunta al servidor de chat)* |

> **Desde v0.4.1:** con backend no-Ollama y sin `embedHost`, OOCode cae al Ollama local en vez de apuntar el cliente de embeddings al servidor OpenAI/Anthropic. Si tu Ollama de embeddings está en otra máquina, configúralo explícitamente con `api.embedHost`:

```json
{
  "api": {
    "type":      "anthropic",
    "key":       "sk-ant-...",
    "embedHost": "http://192.168.1.50:11434"
  }
}
```

---

## Preguntas frecuentes

**¿Puedo usar Anthropic para el agente y Ollama para los embeddings?**  
Sí — `api.type` controla solo las llamadas de inferencia. Los embeddings usan `api.embedHost` si está configurado; si no, con backend no-Ollama caen al Ollama local (`http://localhost:11434`). Si tu Ollama está en otra dirección, fija `api.embedHost`.

**¿Los tool schemas funcionan igual con todos los backends?**  
Sí — OOCode usa el formato OpenAI/Ollama internamente. El backend Anthropic convierte los schemas automáticamente antes de cada llamada.

**¿El historial de contexto (compactación) funciona igual?**  
Sí — el contexto se gestiona en formato interno neutral. Cada backend convierte los mensajes a su propio formato antes de enviarlos.

**¿Puedo cambiar de backend sin reiniciar?**  
No directamente — el backend se instancia al arrancar. Edita `oocode.json` y reinicia el agente (o usa `/new` para una nueva sesión, aunque el cliente no se reinicia).
