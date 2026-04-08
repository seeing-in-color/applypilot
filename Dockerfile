FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Install the package
RUN pip install --no-cache-dir -e .

# Expose port
EXPOSE 8000

# Start the application (Railway sets PORT env var)
CMD ["sh", "-c", "uvicorn src.applypilot.webapp.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
