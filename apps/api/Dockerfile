FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv HF_HOME=/opt/hf PATH="/opt/venv/bin:$PATH"
WORKDIR /app
RUN pip install --no-cache-dir uv
# Dependencies first, from the lockfile, so this layer is cached until they change.
COPY pyproject.toml uv.lock ./
ARG UV_EXTRAS=""  # e.g. "--extra observability" to include the Sentry SDK
RUN uv sync --frozen --no-dev --no-install-project $UV_EXTRAS
# Bake the embedding model into the image: otherwise the first user request downloads 130 MB.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
COPY . .
RUN chmod +x docker-entrypoint.sh && useradd --system --uid 10001 app && chown -R app /app /opt/hf
USER app
EXPOSE 5000
HEALTHCHECK --interval=15s --timeout=5s --start-period=240s --retries=4 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3).status == 200 else 1)"
ENTRYPOINT ["./docker-entrypoint.sh"]
