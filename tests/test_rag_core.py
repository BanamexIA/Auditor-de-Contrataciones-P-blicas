import unittest

from rag.core import format_vector, parse_embeddings


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


if __name__ == "__main__":
    unittest.main()
