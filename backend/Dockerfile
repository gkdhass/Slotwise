# Multi-stage build: dependencies are built once, runtime contains no compiler toolchain.
FROM python:3.11.18-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11.18-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

RUN groupadd --system --gid 10001 slotwise \
    && useradd --system --uid 10001 --gid slotwise --home /app --shell /usr/sbin/nologin slotwise

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=slotwise:slotwise app ./app
COPY --chown=slotwise:slotwise alembic ./alembic
COPY --chown=slotwise:slotwise alembic.ini pyproject.toml ./

USER slotwise
EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
