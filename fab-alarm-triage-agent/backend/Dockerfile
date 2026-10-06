FROM python:3.13-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

FROM base AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

FROM base AS runtime
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv
COPY app ./app
COPY tools ./tools
# Eval reports are written by `python -m app.eval.run` and read by /api/metrics/eval,
# both from this image, so they need one writable directory they agree on.
ENV EVAL_REPORTS_DIR=/srv/eval-reports
RUN mkdir -p /srv/eval-reports \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /srv
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=2).status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
