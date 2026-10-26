# AI Hub Campus — Credit Card Default Risk Prediction
# Baseline application image (Sprint 1). Python 3.12, pinned dependencies, non-root.
#
# Build:  docker compose build web
# Port:   2026 — the Cloudflare ingress targets http://web:2026 (docs/architecture.md §5)
#
# Nothing secret is baked in: .env / .env.cloudflared / SQLite / models are excluded by
# .dockerignore and only non-secret runtime config is copied.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/app

# Unprivileged runtime account; no shell, no home-directory writes outside /home/app.
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --home-dir /home/app --create-home app

WORKDIR /app

# Dependencies first so the layer caches independently of application code.
COPY requirements.txt ./
RUN pip install --no-cache-dir --no-compile -r requirements.txt

# Application code and Streamlit config only.
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY app.py ./
COPY src/ ./src/
# The data contract lives in ml/schema.py and src/validation.py imports it, so the
# package must ship with the image. No dataset is copied.
COPY ml/ ./ml/

# The shipped model artifacts (S5), read-only: the artifact, the manifest it is verified
# against and the evaluation record. They are root-owned and mode 644, and the container runs
# as `app`, so the runtime can read them and cannot rewrite them. src/inference.py verifies
# the checksum against the manifest before it unpickles anything.
COPY models/best_pipeline.joblib models/model_manifest.json models/metrics.json ./models/

# Writable storage for the SQLite database (mounted as a named volume in compose).
RUN mkdir -p /app/storage && chown -R app:app /app/storage

USER app

EXPOSE 2026

# Health probe with the Python standard library only — no curl in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2026/_stcore/health', timeout=3)"]

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=2026"]
