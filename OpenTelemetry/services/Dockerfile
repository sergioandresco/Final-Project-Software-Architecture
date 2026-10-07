# Imagen común para service-a y service-b.
# Build (contexto = OpenTelemetry/services):
#   docker build --build-arg SERVICE=service-a -t otel-lab/service-a .
FROM python:3.12-slim

ARG SERVICE
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /srv/service

COPY ${SERVICE}/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /srv/shared/
COPY ${SERVICE}/app/ ./app/

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
# Un solo worker: los providers de OTel (BatchSpanProcessor) no se comparten entre procesos forkeados.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --no-access-log"]
