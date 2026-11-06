FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 APP_DATA_DIR=/var/data
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY *.py ./
COPY web ./web
RUN mkdir -p /var/data
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "webapp.py", "serve", "--host", "0.0.0.0"]
