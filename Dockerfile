FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/ ./packages/
COPY migrations/ ./migrations/
COPY alembic.ini .
COPY scripts/ ./scripts/
COPY tests/ ./tests/

RUN mkdir -p /app/models
ENV PYTHONPATH=/app/packages
ENV PYTHONUNBUFFERED=1
