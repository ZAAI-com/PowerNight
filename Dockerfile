# PowerNight Docker Container
# Multi-stage build for optimized image size

# Build stage - Install dependencies and build requirements
FROM python:3.11-slim AS builder

# Set environment variables for build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libc6-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Production stage - Runtime environment
FROM python:3.11-slim AS production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/opt/venv/bin:$PATH" \
    POWERNIGHT_DATA_PATH=/data \
    POWERNIGHT_LOGS_PATH=/data/logs \
    POWERNIGHT_STATIC_PATH=/app/dist

# Install runtime dependencies and create user/directories in single layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r powernight \
    && useradd -r -g powernight -d /app -s /bin/bash powernight \
    && mkdir -p /app/config /data /data/logs \
    && chown -R powernight:powernight /app /data

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR /app

# Copy application files
COPY --chown=powernight:powernight config/ ./config/
COPY --chown=powernight:powernight src/ ./src/
COPY --chown=powernight:powernight dist/ ./dist/
COPY --chown=powernight:powernight pyproject.toml requirements.txt ./

# Switch to non-root user
USER powernight

# Declare volume for persistent data (database, logs, tokens)
VOLUME ["/data"]

# Expose port for web interface
EXPOSE 8020

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${POWERNIGHT_WEB_PORT:-8020}/health || exit 1

# Run application directly
CMD ["python", "-m", "powernight.main"]

# Build arguments for metadata
ARG VERSION=1.0.0
ARG BUILD_DATE
ARG VCS_REF

# Metadata labels (OCI standard - essential only)
LABEL org.opencontainers.image.title="PowerNight" \
      org.opencontainers.image.description="Schedule Tesla Powerwall Grid-Charging during the night" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.url="https://github.com/ZAAI-com/PowerNight" \
      org.opencontainers.image.source="https://github.com/ZAAI-com/PowerNight" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.created="${BUILD_DATE}"
