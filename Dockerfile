# Build stage
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-install-project --no-dev

# Production stage
FROM python:3.12-slim

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY app.py epub_parser.py start.sh ./
COPY static/ ./static/

# Default EPUB path (can be overridden at runtime)
ENV EPUB_PATH=/data/book.epub

# Expose port
EXPOSE 8000

# Create data directory for mounting EPUBs
RUN mkdir -p /data

# Entrypoint script that parses EPUB if needed and starts the server
COPY <<'EOF' /app/docker-entrypoint.sh
#!/bin/bash
set -e

# Check if EPUB exists
if [ ! -e "$EPUB_PATH" ]; then
    echo "Error: EPUB file not found at $EPUB_PATH"
    echo "Mount your EPUB file using: -v /path/to/book.epub:/data/book.epub"
    echo "Or set EPUB_PATH environment variable to a different path"
    exit 1
fi

# Parse EPUB if content.json doesn't exist
if [ ! -f "/app/content.json" ]; then
    echo "Parsing EPUB: $EPUB_PATH"
    python epub_parser.py "$EPUB_PATH"
fi

# Start the server
echo "Starting server..."
exec python -m uvicorn app:app --host 0.0.0.0 --port 8000
EOF

RUN chmod +x /app/docker-entrypoint.sh

CMD ["/app/docker-entrypoint.sh"]
