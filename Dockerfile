FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# OS tuning: raise file descriptor limit (required for high concurrency)
RUN echo "* soft nofile 65535" >> /etc/security/limits.conf && \
    echo "* hard nofile 65535" >> /etc/security/limits.conf

# Install Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY config.py .
COPY api/ ./api/
COPY core/ ./core/
COPY characters/ ./characters/
COPY state/ ./state/
COPY db/ ./db/
COPY memory/ ./memory/
COPY services/ ./services/

# Environment defaults (override at runtime via RunPod env vars)
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

# Production: gunicorn + uvicorn workers
CMD ["gunicorn", "api.main:app", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30"]
