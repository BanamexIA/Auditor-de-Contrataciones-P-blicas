# 1) El front (React + Vite) se compila aparte; la imagen final solo lleva los archivos estáticos.
FROM node:20-alpine AS front
WORKDIR /front
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) Backend Flask; sirve también el front compilado (backend/front.py, FRONT_DIR).
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
COPY eval ./eval
COPY --from=front /front/dist ./frontend_dist
ENV FRONT_DIR=/app/frontend_dist

EXPOSE 5000
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/db', timeout=3)"

CMD ["python", "-m", "backend.app"]
