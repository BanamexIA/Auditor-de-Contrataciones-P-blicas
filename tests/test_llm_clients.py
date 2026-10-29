import json
import unittest
from unittest.mock import patch

from llm.base import LLMResponse
from llm.cloud_client import CloudClient
from llm.ollama_client import OllamaClient


class FakeHTTPResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class OllamaClientTests(unittest.TestCase):
    @patch("llm.base.urllib.request.urlopen")
    def test_sends_chat_and_returns_usage(self, urlopen):
        urlopen.return_value = FakeHTTPResponse(
            {
                "message": {"content": "respuesta local"},
                "prompt_eval_count": 12,
                "eval_count": 4,
                "total_duration": 500_000_000,
            }
        )
        client = OllamaClient(base_url="http://ollama.test/", model="local-model")

        result = client.generate("Eres auditor.", "Resume la evidencia.", temperature=0.2)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://ollama.test/api/chat")
        self.assertEqual(request.get_method(), "POST")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "local-model")
        self.assertEqual(payload["messages"], [
            {"role": "system", "content": "Eres auditor."},
            {"role": "user", "content": "Resume la evidencia."},
        ])
        self.assertEqual(payload["options"]["temperature"], 0.2)
        self.assertIsInstance(result, LLMResponse)
        self.assertEqual((result.text, result.input_tokens, result.output_tokens),
                         ("respuesta local", 12, 4))
        self.assertGreaterEqual(result.latency_ms, 0)

    @patch("llm.base.urllib.request.urlopen")
    def test_rejects_missing_token_usage(self, urlopen):
        urlopen.return_value = FakeHTTPResponse({"message": {"content": "respuesta"}})
        client = OllamaClient(base_url="http://ollama.test", model="local-model")

        with self.assertRaisesRegex(RuntimeError, "prompt_eval_count"):
            client.generate("system", "prompt")


class CloudClientTests(unittest.TestCase):
    def test_requires_api_key_and_model(self):
        with patch("llm.cloud_client.setting", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "CLOUD_API_KEY"):
                CloudClient()

        with patch("llm.cloud_client.setting", side_effect=lambda name, default="": (
            "test-key" if name == "CLOUD_API_KEY" else ""
        )):
            with self.assertRaisesRegex(RuntimeError, "CLOUD_MODEL"):
                CloudClient()

    @patch("llm.base.urllib.request.urlopen")
    def test_sends_openai_compatible_chat_and_returns_usage(self, urlopen):
        urlopen.return_value = FakeHTTPResponse(
            {
                "choices": [{"message": {"content": "respuesta de referencia"}}],
                "usage": {"prompt_tokens": 25, "completion_tokens": 9},
            }
        )
        client = CloudClient(
            api_key="test-key",
            model="comparison-model",
            base_url="https://provider.test/v1/chat/completions",
        )

        result = client.generate("Eres auditor.", "Evalúa este caso.")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://provider.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "comparison-model")
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(
            (result.text, result.input_tokens, result.output_tokens),
            ("respuesta de referencia", 25, 9),
        )


if __name__ == "__main__":
    unittest.main()
