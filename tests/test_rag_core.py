import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from rag.core import format_vector, parse_embeddings, read_jsonl_chunks, retrieve


class ParseEmbeddingsTests(unittest.TestCase):
    def test_accepts_embeddings_and_preserves_dimension(self):
        embeddings = parse_embeddings(
            {"embeddings": [[0.1, 0.2], [0.3, 0.4]]},
            expected_count=2,
        )
        self.assertEqual(embeddings, [[0.1, 0.2], [0.3, 0.4]])

    def test_rejects_mismatched_response_count(self):
        with self.assertRaisesRegex(RuntimeError, "one vector per input"):
            parse_embeddings({"embeddings": [[0.1]]}, expected_count=2)

    def test_rejects_inconsistent_dimensions(self):
        with self.assertRaisesRegex(RuntimeError, "inconsistent dimensions"):
            parse_embeddings({"embeddings": [[0.1], [0.2, 0.3]]}, expected_count=2)

    def test_rejects_non_finite_values(self):
        with self.assertRaisesRegex(RuntimeError, "non-finite"):
            parse_embeddings({"embeddings": [[float("inf")]]}, expected_count=1)


class FormatVectorTests(unittest.TestCase):
    def test_formats_pgvector_literal(self):
        self.assertEqual(format_vector([0.25, -0.5]), "[0.25,-0.5]")

    def test_rejects_invalid_vector(self):
        with self.assertRaisesRegex(ValueError, "non-finite"):
            format_vector([float("nan")])


class NormativeSampleTests(unittest.TestCase):
    def _sample(self):
        samples = []
        for index in range(5):
            is_current = index >= 2
            samples.append(
                {
                    "fuente": "Cámara de Diputados",
                    "tipo": "normas",
                    "titulo": "Fixture de prueba, no texto legal",
                    "url_o_ruta": (
                        "https://www.diputados.gob.mx/LeyesBiblio/pdf/LAASSP.pdf"
                        if is_current
                        else "https://www.diputados.gob.mx/LeyesBiblio/laassp/LAASSP_abrogada.pdf"
                    ),
                    "posicion": index if is_current else index,
                    "contenido": f"Texto sintético de prueba {index}",
                    "document_metadata": {
                        "ley": "LAASSP",
                        "version": "2025 vigente" if is_current else "2000 abrogada",
                        "fecha_publicacion_dof": (
                            "2025-04-16" if is_current else "2000-01-04"
                        ),
                        "fecha_entrada_vigor": (
                            "2025-04-17" if is_current else "2000-03-05"
                        ),
                        "fecha_abrogacion": None if is_current else "2025-04-17",
                        "sha256": "a" * 64,
                    },
                    "metadata": {
                        "articulo": f"Artículo {index + 1}",
                        "ley": "LAASSP",
                    },
                }
            )
        return samples

    def test_requires_official_metadata_and_both_law_versions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.jsonl"
            path.write_text(
                "\n".join(json.dumps(item) for item in self._sample()),
                encoding="utf-8",
            )
            chunks = read_jsonl_chunks(path, require_sample_size=True)
        self.assertEqual(len(chunks), 5)

    def test_rejects_missing_source_hash(self):
        sample = self._sample()
        del sample[0]["document_metadata"]["sha256"]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.jsonl"
            path.write_text(
                "\n".join(json.dumps(item) for item in sample),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "sha256"):
                read_jsonl_chunks(path, require_sample_size=True)

    def test_reads_pretty_printed_json_object(self):
        sample = self._sample()[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pretty.jsonl"
            path.write_text(json.dumps(sample, indent=2), encoding="utf-8")
            chunks = read_jsonl_chunks(path)
        self.assertEqual(len(chunks), 1)

    def test_reads_jsonl_records_and_json_array(self):
        samples = self._sample()[:2]
        with tempfile.TemporaryDirectory() as temp_dir:
            jsonl_path = Path(temp_dir) / "multiple.jsonl"
            jsonl_path.write_text(
                "\n".join(json.dumps(item) for item in samples),
                encoding="utf-8",
            )
            array_path = Path(temp_dir) / "array.json"
            array_path.write_text(json.dumps(samples, indent=2), encoding="utf-8")
            self.assertEqual(len(read_jsonl_chunks(jsonl_path)), 2)
            self.assertEqual(len(read_jsonl_chunks(array_path)), 2)

    def test_reports_line_and_column_for_malformed_pretty_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "malformed.jsonl"
            path.write_text('{\n  "fuente": "test",\n}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"malformed\.jsonl:\d+:\d+: invalid JSON"):
                read_jsonl_chunks(path)


class RetrievalVigencyTests(unittest.TestCase):
    class Cursor:
        description = []

        def __init__(self):
            self.query = ""
            self.parameters = ()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, parameters):
            self.query = query
            self.parameters = parameters

        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.active_cursor = RetrievalVigencyTests.Cursor()

        def cursor(self):
            return self.active_cursor

    def test_retrieval_passes_contract_date_to_inclusive_effective_filter(self):
        conn = self.Connection()
        retrieve(conn, [0.25, 0.5], top_k=3, contract_date=date(2024, 6, 1))

        query = conn.active_cursor.query
        self.assertIn("d.fecha_entrada_vigor <= %s::date", query)
        self.assertIn("%s::date < d.fecha_abrogacion", query)
        self.assertIn("d.metadata AS document_metadata", query)
        self.assertEqual(
            conn.active_cursor.parameters,
            ("[0.25,0.5]", date(2024, 6, 1), date(2024, 6, 1), date(2024, 6, 1), "[0.25,0.5]", 3),
        )

    def test_normative_retrieval_without_contract_date_passes_null_filter(self):
        conn = self.Connection()
        retrieve(conn, [0.25], top_k=1)
        self.assertEqual(conn.active_cursor.parameters[1:4], (None, None, None))


if __name__ == "__main__":
    unittest.main()
