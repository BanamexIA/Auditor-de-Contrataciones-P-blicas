from __future__ import annotations

from llm.base import LLMClient, LLMResponse, post_json, setting, token_count


class CloudClient(LLMClient):
    """OpenAI-compatible client reserved for benchmark comparison."""

    provider = "cloud"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else setting("CLOUD_API_KEY")
        self.model = model or setting("CLOUD_MODEL")
        self.base_url = (
            base_url or setting(
                "CLOUD_BASE_URL",
                "https://api.openai.com/v1/chat/completions",
            )
        ).rstrip("/")
        if not self.api_key:
            raise RuntimeError(
                "Cloud comparison is disabled: set CLOUD_API_KEY in .env or the process environment."
            )
        if not self.model:
            raise RuntimeError(
                "Cloud comparison model is not configured: set CLOUD_MODEL in .env or the process environment."
            )

    def generate(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.0,
    ) -> LLMResponse:
        payload, latency_ms = post_json(
            self.base_url,
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
            },
            {"Authorization": f"Bearer {self.api_key}"},
        )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise RuntimeError("Cloud provider returned no chat completion choices.")
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise RuntimeError("Cloud provider returned a completion without message content.")
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            raise RuntimeError("Cloud provider returned no token usage metadata.")
        return LLMResponse(
            text=message["content"],
            input_tokens=token_count(usage.get("prompt_tokens"), "prompt_tokens", self.provider),
            output_tokens=token_count(usage.get("completion_tokens"), "completion_tokens", self.provider),
            latency_ms=latency_ms,
        )
