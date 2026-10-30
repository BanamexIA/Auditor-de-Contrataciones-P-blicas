import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from llm.base import LLMResponse
from telemetry.gpu import GPUUsageSampler, read_gpu_metrics
from telemetry.tracking import (
    CSV_FIELDS,
    export_llm_calls_csv,
    record_llm_call,
    track_llm_call,
)


class FakeClient:
    provider = "fake"
    model = "test-model"

    @track_llm_call(agent="fake-agent")
    def generate(self, fail=False):
        if fail:
            raise ValueError("synthetic failure")
        return LLMResponse(
            text="respuesta",
            input_tokens=8,
            output_tokens=3,
            latency_ms=125,
            tokens_per_second=24,
            time_to_first_token_ms=40,
            model_quantization="Q4",
            ollama_version="1.0",
        )


class TrackingTests(unittest.TestCase):
    @patch("telemetry.tracking.record_llm_call")
    def test_decorator_records_success_and_returns_response(self, record):
        response = FakeClient().generate()

        self.assertEqual(response.text, "respuesta")
        row = record.call_args.args[0]
        self.assertEqual(row["agent"], "fake-agent")
        self.assertEqual(row["provider"], "fake")
        self.assertEqual(row["model"], "test-model")
        self.assertEqual(row["input_tokens"], 8)
        self.assertEqual(row["output_tokens"], 3)
        self.assertEqual(row["tokens_per_second"], 24)
        self.assertEqual(row["time_to_first_token_ms"], 40)
        self.assertEqual(row["ollama_version"], "1.0")
        self.assertEqual(row["model_quantization"], "Q4")
        self.assertTrue(row["equipment"])
        self.assertEqual(row["status"], "success")
        self.assertIsInstance(row["started_at"], datetime)
        self.assertEqual(row["started_at"].tzinfo, timezone.utc)

    @patch("telemetry.tracking.record_llm_call")
    def test_decorator_records_failure_and_reraises(self, record):
        with self.assertRaisesRegex(ValueError, "synthetic failure"):
            FakeClient().generate(fail=True)

        row = record.call_args.args[0]
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["error_type"], "ValueError")
        self.assertIsNone(row["input_tokens"])

    def test_csv_sink_and_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "calls.csv"
            exported = Path(temp_dir) / "export.csv"
            record = {
                "started_at": datetime(2026, 10, 29, tzinfo=timezone.utc),
                "agent": "fake",
                "provider": "ollama",
                "model": "qwen",
                "model_quantization": None,
                "ollama_version": "0.5.7",
                "equipment": "host",
                "input_tokens": 2,
                "output_tokens": 1,
                "latency_ms": 50.0,
                "tokens_per_second": 20.0,
                "time_to_first_token_ms": 25.0,
                "gpu_utilization_percent": None,
                "vram_used_mb": None,
                "status": "success",
                "error_type": None,
            }
            with patch.dict(
                "os.environ",
                {"TELEMETRY_SINK": "csv", "TELEMETRY_CSV_PATH": str(source)},
            ):
                record_llm_call(record)
                self.assertEqual(export_llm_calls_csv(exported), 1)

            with exported.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(list(rows[0]), list(CSV_FIELDS))
            self.assertEqual(rows[0]["model"], "qwen")
            self.assertEqual(rows[0]["gpu_utilization_percent"], "")

    def test_decorated_call_writes_csv_without_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "calls.csv"
            with patch.dict(
                "os.environ",
                {"TELEMETRY_SINK": "csv", "TELEMETRY_CSV_PATH": str(path)},
            ):
                FakeClient().generate()

            with path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["agent"], "fake-agent")
            self.assertEqual(rows[0]["status"], "success")

    @patch("telemetry.tracking._insert_database_record")
    def test_database_sink_persists_the_record(self, insert):
        record = {"model": "qwen", "status": "success"}
        with patch.dict("os.environ", {"TELEMETRY_SINK": "database"}):
            record_llm_call(record)
        insert.assert_called_once_with(record)

    @patch("telemetry.gpu.shutil.which", return_value=None)
    def test_missing_nvidia_tool_returns_null_metrics(self, _which):
        self.assertEqual(read_gpu_metrics(), (None, None))
        sampler = GPUUsageSampler()
        with sampler:
            pass
        self.assertIsNone(sampler.gpu_utilization_percent)
        self.assertIsNone(sampler.vram_used_mb)


if __name__ == "__main__":
    unittest.main()
