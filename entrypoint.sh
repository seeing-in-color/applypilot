#!/bin/sh
# Get PORT from environment, default to 8000 if not set
PORT="${PORT:-8000}"
exec uvicorn src.applypilot.webapp.api:app --host 0.0.0.0 --port "$PORT"
