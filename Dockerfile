FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first: this layer is rebuilt only when the lock file changes
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .

RUN useradd --system --create-home --uid 1000 app \
    && mkdir -p media staticfiles \
    && chown -R app:app media staticfiles
USER app

EXPOSE 8000
ENTRYPOINT ["sh", "./docker/entrypoint.sh"]
# Long timeout: bulk uploads of originals are processed inside the request
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "300", "--access-logfile", "-"]
