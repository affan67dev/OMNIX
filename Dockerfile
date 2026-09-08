# Production-grade Dockerfile for OMNIX API
FROM python:3.12-slim

# Security: run as non-root
RUN addgroup --system omnix && adduser --system --ingroup omnix omnix

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Build frontend (if node available; otherwise pre-build outside)
# Frontend is expected to be pre-built into dist/ before docker build
# or handled by a separate build stage.

RUN chown -R omnix:omnix /app
USER omnix

EXPOSE 8000

# Uvicorn with 2 workers for production; adjust WEB_CONCURRENCY as needed
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info", \
     "--access-log", \
     "--no-server-header"]
