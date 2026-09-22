FROM python:3.13-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

FROM base AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml server.py ./
RUN pip install --upgrade pip && pip install .

FROM base AS runtime
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv
COPY server.py ./
RUN useradd --create-home --uid 10002 mcp && chown -R mcp:mcp /srv
USER mcp
EXPOSE 9000
CMD ["python", "server.py"]
