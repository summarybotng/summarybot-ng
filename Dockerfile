# Summary Bot NG - Production Dockerfile
# Multi-stage build for optimized image size

# Stage 1: Frontend builder
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci

COPY src/frontend/ ./
RUN npm run build

# Stage 2: Python dependency builder
FROM python:3.11-slim AS builder

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Set working directory
WORKDIR /build

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Configure Poetry to not create virtual environment (we're in a container)
RUN poetry config virtualenvs.create false

# Install dependencies only (no dev dependencies, no root project)
RUN poetry install --only main --no-root --no-interaction --no-ansi

# Stage 3: Runtime
FROM python:3.11-slim

# Build arguments for versioning
ARG BUILD_NUMBER=dev
ARG BUILD_DATE=

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash botuser

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=botuser:botuser src/ ./src/
COPY --chown=botuser:botuser pyproject.toml poetry.lock ./

# Copy frontend build output
COPY --from=frontend-builder --chown=botuser:botuser /frontend/dist ./src/frontend/dist/

# Create necessary directories with correct permissions
RUN mkdir -p /app/data /app/logs && \
    chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Expose webhook port
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    BUILD_NUMBER=${BUILD_NUMBER} \
    BUILD_DATE=${BUILD_DATE}

# Run the application (uses src/__main__.py for resilient startup)
CMD ["python", "-m", "src"]
