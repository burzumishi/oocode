"""API backends para OOCode: Ollama, OpenAI-compatible, Anthropic."""
from api.base import BackendClient, Chunk, Response, ToolCall, _ToolFunction


def build_client(config) -> "BackendClient":
    """Instancia el backend correcto según config.api_type."""
    api_type = getattr(config, "api_type", "ollama") or "ollama"

    # Límite de salida configurado para el modelo activo (None = dejar que el backend decida).
    # AgentLoop no lo inyecta en model_params (diseño Ollama-céntrico), así que lo pasamos aquí.
    max_tokens = getattr(config, "effective_max_output_tokens", None)

    if api_type == "openai":
        from api.openai import OpenAIBackend
        base_url = getattr(config, "api_base_url", "") or "https://api.openai.com/v1"
        api_key  = getattr(config, "api_key", "")
        return OpenAIBackend(base_url=base_url, api_key=api_key, max_tokens=max_tokens)

    if api_type == "anthropic":
        from api.anthropic import AnthropicBackend
        api_key = getattr(config, "api_key", "")
        return AnthropicBackend(api_key=api_key, max_tokens=max_tokens)

    # Default: ollama
    from api.ollama import OllamaBackend
    host = getattr(config, "ollama_host", "http://localhost:11434")
    return OllamaBackend(host=host)


__all__ = ["build_client", "BackendClient", "Chunk", "Response", "ToolCall", "_ToolFunction"]
