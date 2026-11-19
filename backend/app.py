import os

from flask import Flask, jsonify
from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from backend.agentes.api import bp as agentes_bp
from backend.agentes.repositorio import RepositorioAgentes, RepositorioAgentesSQL
from backend.agentes.servicio import MonitorAgentes
from backend.agentes.verificacion import ClienteHttp
from backend.casos.api import bp as casos_bp
from backend.casos.repositorio import RepositorioCasos, RepositorioCasosSQL
from backend.reportes.almacen import AlmacenReportes, almacen_desde_entorno


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
    almacen: AlmacenReportes | None = None,
    repositorio_agentes: RepositorioAgentes | None = None,
    http_agentes: ClienteHttp | None = None,
) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    # Con charset explícito, PowerShell 5.1 no decodifica los acentos como Latin-1.
    app.json.mimetype = "application/json; charset=utf-8"
    if repositorio is None:
        engine = engine or engine_desde_entorno()
        repositorio = RepositorioCasosSQL(engine)
    if repositorio_agentes is None and engine is not None:
        repositorio_agentes = RepositorioAgentesSQL(engine)
    app.extensions["repositorio_casos"] = repositorio
    app.extensions["almacen_reportes"] = almacen or almacen_desde_entorno()
    app.extensions["repositorio_agentes"] = repositorio_agentes
    app.extensions["http_agentes"] = http_agentes

    intervalo = float(os.environ.get("AGENTES_VERIFICAR_CADA_S", "0") or 0)
    if intervalo > 0 and repositorio_agentes is not None:
        app.extensions["monitor_agentes"] = MonitorAgentes(
            repositorio_agentes, intervalo, **({"http": http_agentes} if http_agentes else {})
        ).iniciar()

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
    app.register_blueprint(agentes_bp)
    _errores_en_json(app)
    return app


_CODIGOS_HTTP = {
    400: "solicitud_invalida",
    404: "ruta_no_encontrada",
    405: "metodo_no_permitido",
    415: "solicitud_invalida",
}


def _errores_en_json(app: Flask) -> None:
    """Todos los errores con la forma del contrato: {"error": {"codigo", "mensaje"}}."""

    @app.errorhandler(HTTPException)
    def error_http(exc: HTTPException):
        codigo = _CODIGOS_HTTP.get(exc.code or 500, "error_http")
        return jsonify(error={"codigo": codigo, "mensaje": exc.description}), exc.code

    @app.errorhandler(Exception)
    def error_interno(exc: Exception):
        app.logger.exception("Error no controlado")
        return jsonify(error={"codigo": "error_interno",
                              "mensaje": "Error interno del servidor."}), 500


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
