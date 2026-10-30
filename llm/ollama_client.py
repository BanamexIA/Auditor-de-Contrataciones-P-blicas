from __future__ import annotations

from llm.base import LLMClient, LLMResponse, get_json, post_json, setting, token_count
from telemetry.tracking import track_llm_call


class OllamaClient(LLMClient):
    provider = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or setting(
            "AGENT_BASE_URL",
            "http://localhost:11434",
        )).rstrip("/")
        self.model = model or setting("AGENT_MODEL", "qwen2.5:7b")
        self.model_quantization: str | None = None
        self.ollama_version: str | None = None
        if not self.model.strip():
            raise ValueError("Ollama model is empty; set AGENT_MODEL.")

    @track_llm_call
    def generate(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.0,
    ) -> LLMResponse:
        version_payload = get_json(f"{self.base_url}/api/version")
        ollama_version = version_payload.get("version")
        if not isinstance(ollama_version, str) or not ollama_version:
            raise RuntimeError("Ollama returned no version from /api/version.")
        self.ollama_version = ollama_version

        model_payload, _ = post_json(
            f"{self.base_url}/api/show",
            {"model": self.model},
        )
        details = model_payload.get("details")
        quantization = details.get("quantization_level") if isinstance(details, dict) else None
        if not isinstance(quantization, str) or not quantization:
            quantization = None
        self.model_quantization = quantization

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
        input_tokens = token_count(
            payload.get("prompt_eval_count"), "prompt_eval_count", self.provider
        )
        output_tokens = token_count(payload.get("eval_count"), "eval_count", self.provider)
        total_duration = payload.get("total_duration")
        eval_duration = payload.get("eval_duration")
        tokens_per_second = None
        time_to_first_token_ms = None
        if isinstance(eval_duration, int) and eval_duration > 0:
            tokens_per_second = output_tokens / (eval_duration / 1_000_000_000)
        if (
            isinstance(total_duration, int)
            and total_duration >= 0
            and isinstance(eval_duration, int)
            and 0 <= eval_duration <= total_duration
        ):
            time_to_first_token_ms = (total_duration - eval_duration) / 1_000_000
        return LLMResponse(
            text=message["content"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            tokens_per_second=tokens_per_second,
            time_to_first_token_ms=time_to_first_token_ms,
            model_quantization=quantization,
            ollama_version=ollama_version,
        )
