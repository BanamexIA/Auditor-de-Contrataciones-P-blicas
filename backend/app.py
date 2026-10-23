import os

from flask import Flask, jsonify
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

app = Flask(__name__)
database_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ.get("DB_HOST", "db"),
    port=int(os.environ.get("DB_PORT", "5432")),
    database=os.environ["DB_NAME"],
)
engine = create_engine(database_url, pool_pre_ping=True)


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/health/db")
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        app.logger.exception("Database health check failed")
        return jsonify(status="error", database="unavailable"), 503
    return jsonify(status="ok", database="connected")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
