# 09 — Plugin SearXNG

SearXNG es un metabuscador open source autoalojado que agrega resultados de múltiples motores (Google, DuckDuckGo, Bing, Brave, Startpage…) sin tracking y sin API key.

## Instalación de SearXNG

### Con Docker (recomendado)

```bash
docker run -d \
  --name searxng \
  -p 8888:8080 \
  -e SEARXNG_SECRET_KEY=$(openssl rand -hex 32) \
  searxng/searxng:latest
```

### Con docker-compose

```yaml
services:
  searxng:
    image: searxng/searxng:latest
    ports:
      - "8888:8080"
    environment:
      SEARXNG_SECRET_KEY: "cambia-esto-por-algo-aleatorio"
    restart: unless-stopped
```

Verificar que está accesible:
```bash
curl "http://localhost:8888/search?q=test&format=json" | python3 -m json.tool
```

**Importante:** SearXNG debe tener el formato JSON habilitado. Edita `settings.yml`:
```yaml
search:
  formats:
    - html
    - json    # ← añadir esto
```

## Configuración en OOCode

Edita `~/.oocode/oocode.json` o usa `/config edit`:

```json
"searxng": {
  "url":        "http://192.168.1.33:8888",
  "enabled":    false,
  "maxResults": 5,
  "categories": "general",
  "language":   "auto",
  "safeSearch": 0,
  "timeout":    10
}
```

| Campo | Descripción |
|-------|-------------|
| `url` | URL de la instancia. Vacío = plugin desactivado |
| `enabled` | `true` sobreescribe `web_search` con SearXNG |
| `maxResults` | Resultados por búsqueda (1–20) |
| `categories` | Categoría por defecto |
| `language` | `auto`, `es`, `en`, `fr`, `de`… |
| `safeSearch` | 0=off, 1=moderate, 2=strict |
| `timeout` | Segundos de espera máximos |

## Activar el plugin

El plugin se instala en `~/.oocode/plugins/searxng.py` automáticamente. Para activarlo:

```
/plugins enable searxng
```

Esto añade `searxng` a `plugins.enabled` en `oocode.json` y registra la herramienta en el agente.

## Herramientas exportadas

### Modo normal (enabled = false)

Solo se expone `searxng_search`. El agente puede usarla explícitamente además de `web_search` (DuckDuckGo).

```
El agente puede usar:
  web_search      → DuckDuckGo
  searxng_search  → SearXNG local
```

### Modo override (enabled = true)

`searxng_search` + `web_search` (redirigida a SearXNG). El agente usa SearXNG para todas las búsquedas:

```
El agente puede usar:
  web_search      → SearXNG (sobreescrita)
  searxng_search  → SearXNG
```

## Herramienta `searxng_search`

**Parámetros:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `query` | string | Términos de búsqueda |
| `max_results` | integer | Resultados (0 = usar config) |
| `categories` | string | Categorías separadas por coma |

**Categorías disponibles:**
- `general` — resultados web generales
- `news` — noticias recientes
- `science` — artículos científicos
- `it` — tecnología e informática
- `images` — imágenes
- `videos` — vídeos
- `music` — música
- `files` — ficheros y descargas
- `social media` — redes sociales

**Ejemplo de uso del agente:**
```
buscar_searxng(query="python asyncio tutorial", categories="it,science", max_results=8)
```

## System prompt injection

Cuando el plugin está activo con URL configurada, inyecta en el system prompt:
```
Motor de búsqueda web activo: SearXNG en http://192.168.1.33:8888.
Categorías disponibles: general, news, science, it, images, videos.
```

## Diagnóstico

```
/doctor
```

El doctor comprueba la conectividad con SearXNG y muestra el modo activo.

```
/logs 20
```

Los errores de conexión se registran en el log con nivel ERROR.

## Ventajas frente a DuckDuckGo

| | DuckDuckGo (ddgs) | SearXNG local |
|-|-------------------|---------------|
| Privacidad | Media | Total (local) |
| Velocidad | Depende de red | Muy rápida en LAN |
| Categorías | No | Sí (news, science, it…) |
| Motores | Solo DuckDuckGo | Múltiples (configurable) |
| API key | No necesaria | No necesaria |
| Rate limiting | Sí (ocasional) | No |
