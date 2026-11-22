ARG PYTHON_BASE_IMAGE=python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --no-create-home app \
    && mkdir -p /data \
    && chown -R app:app /data

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

RUN python -m pip install --upgrade pip \
    && python -m pip install .

USER app

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
