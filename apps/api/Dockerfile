FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv sync --no-dev
COPY . .
CMD ["uv", "run", "gunicorn", "-b", "0.0.0.0:5000", "grantlens_api:create_app()"]
