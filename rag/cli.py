from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from etl.db_config import connect_database

from rag.core import (
    OllamaEmbeddingClient,
    configure_database,
    discover_dimension,
    ingest_chunks,
    ollama_settings,
    read_jsonl_chunks,
    retrieve,
    check_embedding_configuration,
    run_retrieval_benchmark,
    setting,
)


ROOT = Path(__file__).resolve().parents[1]


def build_client() -> OllamaEmbeddingClient:
    base_url, model = ollama_settings()
    return OllamaEmbeddingClient(base_url, model)


def command_setup() -> None:
    client = build_client()
    dimension = discover_dimension(client)
    configure_database(
        client.model,
        dimension,
        agent_role=setting("AGENT_RO_USER", "agent_ro"),
    )
    print(json.dumps(
        {"model": client.model, "dimension": dimension, "index": "HNSW cosine"},
        ensure_ascii=False,
        indent=2,
    ))


def command_ingest(jsonl_path: Path, sample: bool) -> None:
    try:
        chunks = read_jsonl_chunks(jsonl_path, require_sample_size=sample)
    except ValueError as exc:
        raise SystemExit(f"Invalid fragment file: {exc}") from exc
    client = build_client()
    vectors, elapsed_ms = client.embed([chunk["contenido"] for chunk in chunks])
    inserted = ingest_chunks(chunks, vectors, client.model)
    print(json.dumps(
        {
            "chunks_loaded": inserted,
            "model": client.model,
            "dimension": len(vectors[0]),
            "embedding_ms_total": round(elapsed_ms, 3),
            "embedding_ms_per_chunk": round(elapsed_ms / len(chunks), 3),
        },
        ensure_ascii=False,
        indent=2,
    ))


def command_search(query: str, contract_date: date, top_k: int) -> None:
    client = build_client()
    vectors, embedding_ms = client.embed([query])
    with connect_database() as conn:
        check_embedding_configuration(conn, client.model, len(vectors[0]))
        rows, database_ms = retrieve(conn, vectors[0], top_k, contract_date)
    print(json.dumps(
        {
            "query": query,
            "contract_date": contract_date.isoformat(),
            "embedding_ms": round(embedding_ms, 3),
            "database_ms": round(database_ms, 3),
            "results": rows,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure and test pgvector RAG retrieval.")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("setup", help="Measure the Ollama embedding dimension and configure pgvector.")

    ingest_parser = commands.add_parser("ingest", help="Embed and load JSONL source fragments.")
    ingest_parser.add_argument("--jsonl", type=Path, required=True)
    ingest_parser.add_argument(
        "--sample",
        action="store_true",
        help="Require 5-10 real normative fragments for the phase 5B evaluation.",
    )

    search_parser = commands.add_parser("search", help="Run one cosine-similarity query.")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument(
        "--fecha-contrato",
        type=date.fromisoformat,
        required=True,
        help="Fecha del contrato (YYYY-MM-DD) para filtrar normas vigentes.",
    )
    search_parser.add_argument("--top-k", type=int, default=3)

    benchmark_parser = commands.add_parser("benchmark", help="Run the five-query retrieval check.")
    benchmark_parser.add_argument("--queries", type=Path, default=ROOT / "rag" / "test_queries.json")
    benchmark_parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "rag" / "results" / "embedding_retrieval.csv",
    )
    benchmark_parser.add_argument("--top-k", type=int, default=3)

    args = parser.parse_args()
    if args.command == "setup":
        command_setup()
    elif args.command == "ingest":
        command_ingest(args.jsonl, args.sample)
    elif args.command == "search":
        command_search(args.query, args.fecha_contrato, args.top_k)
    elif args.command == "benchmark":
        client = build_client()
        results = run_retrieval_benchmark(client, args.queries, args.output, args.top_k)
        results["output"] = str(args.output.resolve())
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
