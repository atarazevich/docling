# Multi-stage build for optimized production image
FROM python:3.12-slim-bookworm AS builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Clone and install docling with CPU-only torch
RUN git clone https://github.com/atarazevich/docling.git /tmp/docling && \
    cd /tmp/docling && \
    pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir . --extra-index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    fastapi==0.115.5 \
    uvicorn[standard]==0.32.1 \
    python-multipart==0.0.12 \
    httpx==0.27.2 \
    prometheus-client==0.21.0

# Production stage
FROM python:3.12-slim-bookworm

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    wget \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 docling && \
    mkdir -p /home/docling/.cache /home/docling/models && \
    chown -R docling:docling /home/docling

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Switch to non-root user
USER docling
WORKDIR /home/docling

# Set environment variables for model caching
ENV HF_HOME=/home/docling/.cache/huggingface
ENV TORCH_HOME=/home/docling/.cache/torch
ENV DOCLING_ARTIFACTS_PATH=/home/docling/models
ENV OMP_NUM_THREADS=4
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Pre-download models during build to avoid runtime delays
RUN python -c "from docling.document_converter import DocumentConverter; converter = DocumentConverter()" 2>/dev/null || true && \
    docling-tools models download || true

# Copy the FastAPI application
COPY --chown=docling:docling api.py /home/docling/api.py

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the FastAPI application
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]