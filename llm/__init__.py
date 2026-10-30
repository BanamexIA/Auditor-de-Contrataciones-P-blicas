from llm.base import LLMClient, LLMResponse

__all__ = ["LLMClient", "LLMResponse", "OllamaClient", "CloudClient"]


def __getattr__(name: str):
    if name == "OllamaClient":
        from llm.ollama_client import OllamaClient

        return OllamaClient
    if name == "CloudClient":
        from llm.cloud_client import CloudClient

        return CloudClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
