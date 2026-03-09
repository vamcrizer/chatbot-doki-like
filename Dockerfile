FROM python:3.11-slim

WORKDIR /app

# System deps for health check
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app.py cerebras_client.py conversation.py prompt_builder.py \
     character_generator.py character_prompt_template.py \
     emotion.py intimacy.py ./
COPY characters/ ./characters/
COPY memory/__init__.py memory/fact_extractor.py memory/mem0_store.py \
     memory/scene_tracker.py memory/summarizer.py ./memory/

# Create runtime directories
RUN mkdir -p custom_characters memory/sessions

# Streamlit config — headless, CORS disabled for reverse proxy
RUN mkdir -p /root/.streamlit && \
    printf '[server]\nheadless = true\nport = 8501\naddress = "0.0.0.0"\nenableCORS = false\nenableXsrfProtection = false\n\n[browser]\ngatherUsageStats = false\n' > /root/.streamlit/config.toml

# Environment defaults (override at runtime)
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV EMBED_MODEL=snowflake-arctic-embed2

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py"]
