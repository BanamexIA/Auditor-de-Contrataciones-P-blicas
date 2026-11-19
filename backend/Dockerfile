FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY llm ./llm
COPY telemetry ./telemetry
COPY agents ./agents
COPY agente_deteccion ./agente_deteccion
COPY agente_reporte/agente_reporte ./agente_reporte
COPY rag ./rag
COPY etl ./etl

EXPOSE 5000
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/db', timeout=3)"

CMD ["python", "-m", "backend.app"]
