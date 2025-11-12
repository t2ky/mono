# Multi-stage build for FastAPI application
FROM python:3.10-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Build stage
FROM base AS builder

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM base AS runner

WORKDIR /app

# Create non-root user
RUN useradd --system --uid 1001 appuser

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY main.py .
COPY models.py .
COPY state_manager.py .
COPY static/ static/

# Set ownership
RUN chown -R appuser:appuser /app

# Update PATH
ENV PATH=/home/appuser/.local/bin:$PATH

USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
