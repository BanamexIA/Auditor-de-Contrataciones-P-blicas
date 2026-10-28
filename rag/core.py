from __future__ import annotations

import csv
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from psycopg import sql

from etl.db_config import connect_database


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MIN_CHUNKS = 5
SAMPLE_MAX_CHUNKS = 10
MAX_VECTOR_DIMENSION = 2000


def setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value

    dotenv_path = ROOT / ".env"
    if not dotenv_path.is_file():
        return default
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, raw_value = stripped.partition("=")
        if separator and key.strip() == name:
            raw_value = raw_value.strip()
            if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
                raw_value = raw_value[1:-1]
            return raw_value or default
    return default


def ollama_settings() -> tuple[str, str]:
    base_url = setting("OLLAMA_EMBED_BASE_URL")
    if not base_url:
        base_url = setting("OLLAMA_BASE_URL") or setting("OLLAMA_URL", "http://localhost:11434")
        if not Path("/.dockerenv").exists():
            parsed = urllib.parse.urlsplit(base_url)
            if parsed.hostname in {"ollama", "host.docker.internal"}:
                base_url = f"{parsed.scheme or 'http'}://localhost:{parsed.port or 11434}"

    model = setting("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    return base_url.rstrip("/"), model


def parse_embeddings(payload: dict[str, Any], expected_count: int) -> list[list[float]]:
    raw_embeddings = payload.get("embeddings")
    if not isinstance(raw_embeddings, list) or len(raw_embeddings) != expected_count:
        raise RuntimeError(
            "Ollama returned an unexpected embedding response; expected one vector per input."
        )

    embeddings: list[list[float]] = []
    dimension: int | None = None
    for item in raw_embeddings:
        if not isinstance(item, list) or not item:
            raise RuntimeError("Ollama returned an empty or malformed embedding.")
        try:
            vector = [float(value) for value in item]
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Ollama returned a non-numeric embedding value.") from exc
        if not all(math.isfinite(value) for value in vector):
            raise RuntimeError("Ollama returned a non-finite embedding value.")
        if dimension is None:
            dimension = len(vector)
        elif len(vector) != dimension:
            raise RuntimeError("Ollama returned vectors with inconsistent dimensions.")
        if len(vector) > MAX_VECTOR_DIMENSION:
            raise RuntimeError(
                f"The embedding dimension ({len(vector)}) exceeds pgvector's indexed vector limit "
                f"of {MAX_VECTOR_DIMENSION}."
            )
        embeddings.append(vector)
    return embeddings


class OllamaEmbeddingClient:
    def __init__(self, base_url: str, model: str, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def embed(self, texts: Sequence[str]) -> tuple[list[list[float]], float]:
        if not texts:
            raise ValueError("At least one text is required to generate embeddings.")
        request_body = json.dumps({"model": self.model, "input": list(texts)}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama embedding request failed ({exc.code}). "
                f"Verify that '{self.model}' is pulled and that {self.base_url} is reachable. "
                f"Response: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.base_url}: {exc.reason}"
            ) from exc
        elapsed_ms = (time.perf_counter() - started) * 1000
        if not isinstance(payload, dict):
            raise RuntimeError("Ollama returned an invalid JSON response for embeddings.")
        return parse_embeddings(payload, len(texts)), elapsed_ms


def format_vector(vector: Sequence[float]) -> str:
    if not vector or len(vector) > MAX_VECTOR_DIMENSION:
        raise ValueError("Embedding vector has an unsupported dimension.")
    if not all(math.isfinite(float(value)) for value in vector):
        raise ValueError("Embedding vector contains a non-finite value.")
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def discover_dimension(client: OllamaEmbeddingClient) -> int:
    embeddings, _ = client.embed(["Embedding dimension verification probe."])
    return len(embeddings[0])


def configure_database(model: str, dimension: int, agent_role: str) -> None:
    if not 1 <= dimension <= MAX_VECTOR_DIMENSION:
        raise ValueError(f"Embedding dimension must be between 1 and {MAX_VECTOR_DIMENSION}.")

    with connect_database() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('rag.documentos'), to_regclass('rag.embedding_config')")
            if cursor.fetchone() != ("rag.documentos", "rag.embedding_config"):
                raise RuntimeError(
                    "RAG metadata tables are missing. Run .\\scripts\\init_db.ps1 first."
                )
            cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            if cursor.fetchone() is None:
                raise RuntimeError("pgvector is not enabled. Apply etl/sql/01_vector.sql first.")

            cursor.execute("SELECT to_regclass('rag.chunks')")
            chunks_exist = cursor.fetchone()[0] is not None
            if chunks_exist:
                cursor.execute(
                    """
                    SELECT format_type(a.atttypid, a.atttypmod)
                    FROM pg_attribute a
                    WHERE a.attrelid = 'rag.chunks'::regclass
                      AND a.attname = 'embedding'
                      AND NOT a.attisdropped
                    """
                )
                type_name = cursor.fetchone()
                if type_name is None:
                    raise RuntimeError("rag.chunks exists but has no embedding column.")
                match = re.fullmatch(r"vector(?:\((\d+)\))?", type_name[0])
                if match is None:
                    raise RuntimeError(
                        f"rag.chunks.embedding has unexpected type {type_name[0]!r}; expected vector."
                    )
                existing_dimension = int(match.group(1)) if match.group(1) else None
                cursor.execute("SELECT count(*) FROM rag.chunks")
                chunk_count = cursor.fetchone()[0]
                cursor.execute("SELECT modelo, dimension FROM rag.embedding_config WHERE id = 1")
                configured_model = cursor.fetchone()
                if chunk_count and configured_model is None:
                    raise RuntimeError(
                        "Existing chunks have no recorded embedding configuration. "
                        "Their model cannot be verified, so the database was not changed."
                    )
                if chunk_count and configured_model != (model, dimension):
                    raise RuntimeError(
                        f"The database contains {chunk_count} chunks configured for "
                        f"{configured_model[0]} at dimension {configured_model[1]}, but the "
                        f"selected model is {model} at dimension {dimension}. Existing vectors "
                        "were not changed."
                    )
                if existing_dimension != dimension:
                    cursor.execute("DROP INDEX IF EXISTS rag.idx_chunks_embedding_cosine")
                    cursor.execute(
                        sql.SQL(
                            "ALTER TABLE rag.chunks ALTER COLUMN embedding TYPE vector({}) "
                            "USING embedding::vector({})"
                        ).format(sql.Literal(dimension), sql.Literal(dimension))
                    )
            else:
                cursor.execute(
                    sql.SQL(
                        """
                        CREATE TABLE rag.chunks (
                            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                            documento_id BIGINT NOT NULL
                                REFERENCES rag.documentos(id) ON DELETE CASCADE,
                            contenido TEXT NOT NULL,
                            embedding vector({}) NOT NULL,
                            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            posicion INTEGER NOT NULL CHECK (posicion >= 0),
                            UNIQUE (documento_id, posicion)
                        )
                        """
                    ).format(sql.Literal(dimension))
                )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_embedding_cosine "
                "ON rag.chunks USING hnsw (embedding vector_cosine_ops)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_documento_posicion "
                "ON rag.chunks (documento_id, posicion)"
            )
            cursor.execute(
                """
                INSERT INTO rag.embedding_config (id, modelo, dimension)
                VALUES (1, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET modelo = EXCLUDED.modelo,
                    dimension = EXCLUDED.dimension,
                    configurado_en = NOW()
                """,
                (model, dimension),
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON rag.chunks TO {}").format(sql.Identifier(agent_role))
            )
            cursor.execute(
                sql.SQL("COMMENT ON TABLE rag.chunks IS {}").format(
                    sql.Literal(
                        "Fragmentos documentales con embeddings Ollama; dimension validada "
                        "contra rag.embedding_config."
                    )
                )
            )
            cursor.execute(
                sql.SQL("COMMENT ON COLUMN rag.chunks.embedding IS {}").format(
                    sql.Literal(f"Vector de dimensión {dimension} generado por el modelo {model}.")
                )
            )


def read_jsonl_chunks(path: Path, require_sample_size: bool = False) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    positions: set[tuple[str, str, str, int]] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, start=1):
            if not raw_line.strip():
                continue
            try:
                item = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_number}: each line must be a JSON object.")

            required = ("fuente", "tipo", "titulo", "url_o_ruta", "contenido", "posicion")
            missing = [key for key in required if key not in item]
            if missing:
                raise ValueError(f"{path}:{line_number}: missing fields: {', '.join(missing)}.")
            if item["tipo"] not in {"docs", "normas", "enterprise"}:
                raise ValueError(f"{path}:{line_number}: tipo must be docs, normas, or enterprise.")
            for key in ("fuente", "titulo", "url_o_ruta", "contenido"):
                if not isinstance(item[key], str) or not item[key].strip():
                    raise ValueError(f"{path}:{line_number}: {key} must be a non-empty string.")
            if not isinstance(item["posicion"], int) or isinstance(item["posicion"], bool) or item["posicion"] < 0:
                raise ValueError(f"{path}:{line_number}: posicion must be a non-negative integer.")
            metadata = item.get("metadata", {})
            document_metadata = item.get("document_metadata", {})
            if not isinstance(metadata, dict) or not isinstance(document_metadata, dict):
                raise ValueError(f"{path}:{line_number}: metadata fields must be JSON objects.")

            key = (item["tipo"], item["fuente"], item["url_o_ruta"], item["posicion"])
            if key in positions:
                raise ValueError(
                    f"{path}:{line_number}: duplicate document and chunk position {item['posicion']}."
                )
            positions.add(key)
            item["_line_number"] = line_number
            chunks.append(item)

    if not chunks:
        raise ValueError(f"{path} contains no chunks.")
    if require_sample_size:
        if not SAMPLE_MIN_CHUNKS <= len(chunks) <= SAMPLE_MAX_CHUNKS:
            raise ValueError(
                f"The phase 5B sample must contain {SAMPLE_MIN_CHUNKS} to "
                f"{SAMPLE_MAX_CHUNKS} chunks; found {len(chunks)}."
            )
        if any(item["tipo"] != "normas" for item in chunks):
            raise ValueError("The phase 5B sample must contain only tipo='normas' fragments.")
    return chunks


def ingest_chunks(
    chunks: list[dict[str, Any]],
    vectors: list[list[float]],
    model: str,
) -> int:
    if len(chunks) != len(vectors):
        raise ValueError("The number of embeddings does not match the number of input chunks.")
    if not chunks:
        raise ValueError("No chunks were provided for ingestion.")

    with connect_database() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT modelo, dimension FROM rag.embedding_config WHERE id = 1")
            config = cursor.fetchone()
            if config is None:
                raise RuntimeError("RAG embeddings are not configured. Run `python -m rag.cli setup`.")
            if config[0] != model:
                raise RuntimeError(
                    f"Database expects model '{config[0]}', but this run uses '{model}'. "
                    "Re-run setup with the selected model before ingesting."
                )
            if any(len(vector) != config[1] for vector in vectors):
                raise RuntimeError(
                    f"An embedding dimension does not match the configured dimension {config[1]}."
                )

            document_ids: dict[tuple[str, str, str], int] = {}
            grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
            for chunk in chunks:
                key = (chunk["tipo"], chunk["fuente"], chunk["url_o_ruta"])
                grouped[key].append(chunk)

            for (tipo, fuente, url_o_ruta), document_chunks in grouped.items():
                first = document_chunks[0]
                document_metadata = first.get("document_metadata", {})
                if any(
                    item.get("document_metadata", {}) != document_metadata
                    or item["titulo"] != first["titulo"]
                    for item in document_chunks
                ):
                    raise ValueError(
                        f"Title or document metadata differs between chunks for {url_o_ruta!r}."
                    )
                cursor.execute(
                    """
                    INSERT INTO rag.documentos (fuente, tipo, titulo, url_o_ruta, metadata)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (tipo, fuente, url_o_ruta) DO UPDATE
                    SET titulo = EXCLUDED.titulo,
                        metadata = EXCLUDED.metadata
                    RETURNING id
                    """,
                    (
                        fuente,
                        tipo,
                        first["titulo"],
                        url_o_ruta,
                        json.dumps(document_metadata, ensure_ascii=False),
                    ),
                )
                document_ids[(tipo, fuente, url_o_ruta)] = cursor.fetchone()[0]

            cursor.executemany(
                "DELETE FROM rag.chunks WHERE documento_id = %s",
                [(document_id,) for document_id in document_ids.values()],
            )
            rows = []
            for chunk, vector in zip(chunks, vectors):
                document_key = (chunk["tipo"], chunk["fuente"], chunk["url_o_ruta"])
                rows.append(
                    (
                        document_ids[document_key],
                        chunk["contenido"],
                        format_vector(vector),
                        json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
                        chunk["posicion"],
                    )
                )
            cursor.executemany(
                """
                INSERT INTO rag.chunks
                    (documento_id, contenido, embedding, metadata, posicion)
                VALUES (%s, %s, %s::vector, %s::jsonb, %s)
                """,
                rows,
            )
    return len(chunks)


def check_embedding_configuration(conn, model: str, dimension: int) -> None:
    with conn.cursor() as cursor:
        cursor.execute("SELECT modelo, dimension FROM rag.embedding_config WHERE id = 1")
        config = cursor.fetchone()
    if config is None:
        raise RuntimeError("RAG embeddings are not configured. Run `python -m rag.cli setup`.")
    if config != (model, dimension):
        raise RuntimeError(
            f"Embedding config mismatch: database has model={config[0]!r}, dimension={config[1]}; "
            f"current model={model!r}, dimension={dimension}. Re-run setup."
        )


def retrieve(conn, vector: Sequence[float], top_k: int) -> tuple[list[dict[str, Any]], float]:
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    vector_text = format_vector(vector)
    started = time.perf_counter()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id, d.titulo, d.fuente, d.tipo, d.url_o_ruta,
                   c.posicion, c.contenido, c.metadata,
                   c.embedding <=> %s::vector AS distancia_coseno
            FROM rag.chunks AS c
            JOIN rag.documentos AS d ON d.id = c.documento_id
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            (vector_text, vector_text, top_k),
        )
        columns = [description.name for description in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    elapsed_ms = (time.perf_counter() - started) * 1000
    return rows, elapsed_ms


def run_retrieval_benchmark(
    client: OllamaEmbeddingClient,
    query_path: Path,
    output_path: Path,
    top_k: int,
) -> dict[str, float]:
    queries_data = json.loads(query_path.read_text(encoding="utf-8"))
    if (
        not isinstance(queries_data, list)
        or len(queries_data) != 5
        or any(not isinstance(query, str) or not query.strip() for query in queries_data)
    ):
        raise ValueError(f"{query_path} must be a JSON array containing exactly five query strings.")

    embeddings, total_embedding_ms = client.embed(queries_data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    embedding_times = total_embedding_ms / len(queries_data)
    database_times: list[float] = []
    result_count = 0
    with connect_database() as conn, output_path.open("w", encoding="utf-8-sig", newline="") as output:
        check_embedding_configuration(conn, client.model, len(embeddings[0]))
        fieldnames = [
            "consulta",
            "ranking",
            "chunk_id",
            "titulo",
            "fuente",
            "tipo",
            "url_o_ruta",
            "posicion",
            "distancia_coseno",
            "embedding_ms_promedio",
            "consulta_db_ms",
            "contenido",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for query, vector in zip(queries_data, embeddings):
            rows, database_ms = retrieve(conn, vector, top_k)
            database_times.append(database_ms)
            for ranking, row in enumerate(rows, start=1):
                writer.writerow(
                    {
                        "consulta": query,
                        "ranking": ranking,
                        "chunk_id": row["id"],
                        "titulo": row["titulo"],
                        "fuente": row["fuente"],
                        "tipo": row["tipo"],
                        "url_o_ruta": row["url_o_ruta"],
                        "posicion": row["posicion"],
                        "distancia_coseno": row["distancia_coseno"],
                        "embedding_ms_promedio": round(embedding_times, 3),
                        "consulta_db_ms": round(database_ms, 3),
                        "contenido": row["contenido"],
                    }
                )
                result_count += 1

    mean_db_ms = sum(database_times) / len(database_times) if database_times else 0.0
    return {
        "queries": float(len(queries_data)),
        "results": float(result_count),
        "embedding_ms_per_query": embedding_times,
        "database_ms_mean": mean_db_ms,
    }
