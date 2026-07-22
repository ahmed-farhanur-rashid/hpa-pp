# ── Python base ──────────────────────────────────────────────
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── Working directory ────────────────────────────────────────
WORKDIR /app

# ── Install dependencies ─────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ────────────────────────────────────
COPY app/ ./app/

# ── Mount shared schemas (read-only at runtime) ──────────────
# The shared/ directory is mounted as a volume, not baked into
# the image, so schema changes don't require a rebuild.
#
# In development:
#   docker run -v $(pwd)/shared:/app/shared:ro hpa-pp-forecasting
#
# In docker-compose, the shared volume is defined in the top-level
# compose file alongside the other services.

# ── PYTHONPATH ───────────────────────────────────────────────
ENV PYTHONPATH="/app:/shared:${PYTHONPATH}"

# ── Expose port ──────────────────────────────────────────────
EXPOSE 8000

# ── Health check ─────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ── Start ────────────────────────────────────────────────────
CMD ["uvicorn", "app.main:create_app()", "--host", "0.0.0.0", "--port", "8000"]
