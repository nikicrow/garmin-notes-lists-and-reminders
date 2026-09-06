# Stage 1: build the Python package
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY backend/uv.lock backend/pyproject.toml /build/
RUN pip install uv

# Sync dependencies
RUN uv sync --frozen --no-dev

# Stage 2: runtime image
FROM python:3.11-slim

# Install curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /build/.venv /app/.venv

# Copy application source
COPY backend/src/tuck_api /app/tuck_api
COPY backend/alembic.ini /app/alembic.ini
COPY backend/migrations /app/migrations

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose the API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Default command (overridden in compose for migrations + server)
CMD ["uvicorn", "tuck_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
