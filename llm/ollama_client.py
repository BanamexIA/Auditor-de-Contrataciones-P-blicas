from __future__ import annotations

from llm.base import LLMClient, LLMResponse, post_json, setting, token_count


class OllamaClient(LLMClient):
    provider = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or setting(
            "AGENT_BASE_URL",
            "http://host.docker.internal:11434",
        )).rstrip("/")
        self.model = model or setting("AGENT_MODEL", "qwen2.5:7b")
        if not self.model.strip():
            raise ValueError("Ollama model is empty; set AGENT_MODEL.")

    def generate(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.0,
    ) -> LLMResponse:
        payload, latency_ms = post_json(
            f"{self.base_url}/api/chat",
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
        message = payload.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise RuntimeError("Ollama returned a response without message content.")
        return LLMResponse(
            text=message["content"],
            input_tokens=token_count(payload.get("prompt_eval_count"), "prompt_eval_count", self.provider),
            output_tokens=token_count(payload.get("eval_count"), "eval_count", self.provider),
            latency_ms=latency_ms,
        )
