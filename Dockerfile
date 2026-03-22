FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server/ ./server/
COPY config.yaml.example ./config.yaml.example

# Create necessary directories
RUN mkdir -p /app/data /app/memory/logs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8100/health || exit 1

# Expose port
EXPOSE 8100

# Start uvicorn server
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]