# =============================================================================
# Claude Workflow Engine - Dockerfile
# Version: 1.4.1
# Description: LangGraph orchestration pipeline with RAG
# Base: python:3.10-slim (multi-stage build)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: dependency installer
# Installing dependencies in a separate stage keeps the final image lean
# and enables layer caching: requirements.txt changes less often than code.
# -----------------------------------------------------------------------------
FROM python:3.10-slim AS deps

# Install OS-level build dependencies required by some Python packages
# (e.g., sentence-transformers, TTS, psutil)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only the requirements file first.
# Docker caches this layer; it is only invalidated when requirements.txt changes.
COPY requirements.txt .

# Install all Python dependencies into a non-root prefix for easy copying
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: final runtime image
# Copies the pre-installed packages from the deps stage.
# No build tools are present in the final image (smaller attack surface).
# -----------------------------------------------------------------------------
FROM python:3.10-slim AS runtime

LABEL org.opencontainers.image.title="Claude Workflow Engine" \
      org.opencontainers.image.description="LangGraph 3-level orchestration pipeline with RAG" \
      org.opencontainers.image.version="1.4.1" \
      org.opencontainers.image.source="https://github.com/techdeveloper-org/claude-workflow-engine"

# Install minimal runtime OS libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --no-create-home --shell /bin/bash appuser

WORKDIR /app

# Copy pre-installed Python packages from the deps stage
COPY --from=deps /install /usr/local

# Copy application source code.
# .dockerignore excludes .env, .git, __pycache__, venv, docs, etc.
COPY --chown=appuser:appgroup . .

# Switch to non-root user
USER appuser

# Expose no ports - this is a CLI pipeline, not a web server.
# If MCP servers later need HTTP exposure, add EXPOSE here.

# Health check: verify Python environment is functional
# Runs a quick import of the core orchestration module
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import sys; sys.path.insert(0, '/app'); import scripts.langgraph_engine.flow_state" \
    || exit 1

# Entrypoint: always use the pipeline entry point
ENTRYPOINT ["python", "scripts/3-level-flow.py"]

# Default command: show help when no task is provided
CMD ["--help"]
