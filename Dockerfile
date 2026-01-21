# Polymarket HFT Bot - Multi-Stage Dockerfile
# Handles Rust (core) + Python (orchestration) build process

# =============================================================================
# STAGE 1: Builder - Compile Rust core with PyO3
# =============================================================================
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install maturin for PyO3 builds
RUN pip install --no-cache-dir maturin

# Copy Rust source
WORKDIR /app
COPY rust_core/ ./rust_core/

# Build Rust core as Python wheel
WORKDIR /app/rust_core
RUN maturin build --release --out /app/wheels

# =============================================================================
# STAGE 2: Runner - Lightweight production image
# =============================================================================
FROM python:3.11-slim AS runner

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libssl3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash botuser

# Set working directory
WORKDIR /app

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the compiled Rust wheel from builder stage
COPY --from=builder /app/wheels/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Copy application code
COPY main.py .
COPY config/ ./config/
COPY strategy_layer/ ./strategy_layer/
COPY utils/ ./utils/

# Create logs directory
RUN mkdir -p logs && chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Environment defaults
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('https://clob.polymarket.com/time', timeout=5)"

# Default command
ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "dry-run"]
