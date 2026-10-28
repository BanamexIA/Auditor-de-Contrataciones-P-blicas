from __future__ import annotations

import os
from pathlib import Path

import psycopg


def _read_dotenv(path: Path) -> dict[str, str]:
    values = {}
    if not path.is_file():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def database_settings() -> dict[str, str]:
    dotenv = _read_dotenv(Path(__file__).resolve().parents[1] / ".env")

    def setting(*names: str, default: str = "") -> str:
        for name in names:
            value = os.getenv(name) or dotenv.get(name)
            if value:
                return value
        return default

    in_container = Path("/.dockerenv").exists()
    host = setting("DB_HOST", default="localhost")
    if not in_container and host in {"db", "localhost"}:
        host = "127.0.0.1"

    port_names = ("DB_PORT", "DB_PORT_HOST") if in_container else ("DB_PORT_HOST", "DB_PORT")
    return {
        "dbname": setting("DB_NAME", "POSTGRES_DB", default="auditor_contrataciones"),
        "user": setting("DB_USER", "ETL_USER", "POSTGRES_USER", default="postgres"),
        "password": setting("DB_PASSWORD", "ETL_USER_PASSWORD", "POSTGRES_PASSWORD"),
        "host": host,
        "port": setting(*port_names, default="5432"),
    }


def load_database_environment() -> None:
    settings = database_settings()
    environment_names = {
        "DB_NAME": settings["dbname"],
        "DB_USER": settings["user"],
        "DB_PASSWORD": settings["password"],
        "DB_HOST": settings["host"],
        "DB_PORT": settings["port"],
    }
    for name, value in environment_names.items():
        if value:
            os.environ.setdefault(name, value)


def connect_database():
    settings = database_settings()
    if not settings["password"]:
        raise RuntimeError(
            "Database password is not configured. Set DB_PASSWORD or ETL_USER_PASSWORD in .env "
            "or in the process environment."
        )
    return psycopg.connect(**settings)


def connect_database_admin():
    dotenv = _read_dotenv(Path(__file__).resolve().parents[1] / ".env")
    settings = database_settings()
    settings["user"] = (
        os.getenv("DB_ADMIN_USER")
        or dotenv.get("DB_ADMIN_USER")
        or os.getenv("POSTGRES_USER")
        or dotenv.get("POSTGRES_USER")
        or ""
    )
    settings["password"] = (
        os.getenv("DB_ADMIN_PASSWORD")
        or dotenv.get("DB_ADMIN_PASSWORD")
        or os.getenv("POSTGRES_PASSWORD")
        or dotenv.get("POSTGRES_PASSWORD")
        or ""
    )
    if not settings["user"] or not settings["password"]:
        raise RuntimeError(
            "Database administrator credentials are not configured. Set DB_ADMIN_USER and "
            "DB_ADMIN_PASSWORD, or POSTGRES_USER and POSTGRES_PASSWORD in .env."
        )
    return psycopg.connect(**settings)
