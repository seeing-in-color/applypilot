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

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Add src to Python path so applypilot module is found
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8000

# Start the application
ENTRYPOINT ["/app/entrypoint.sh"]
