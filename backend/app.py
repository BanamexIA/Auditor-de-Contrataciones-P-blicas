import os

from flask import Flask, jsonify
from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from backend.casos.api import bp as casos_bp
from backend.casos.repositorio import RepositorioCasos, RepositorioCasosSQL


def engine_desde_entorno() -> Engine:
    database_url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
    )
    return create_engine(database_url, pool_pre_ping=True)


def create_app(
    engine: Engine | None = None,
    repositorio: RepositorioCasos | None = None,
) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    if repositorio is None:
        engine = engine or engine_desde_entorno()
        repositorio = RepositorioCasosSQL(engine)
    app.extensions["repositorio_casos"] = repositorio

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/health/db")
    def database_health():
        if engine is None:
            return jsonify(status="error", database="not_configured"), 503
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            app.logger.exception("Database health check failed")
            return jsonify(status="error", database="unavailable"), 503
        return jsonify(status="ok", database="connected")

    app.register_blueprint(casos_bp)
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
