#!/usr/bin/env bash
# Run from project root: bash start_backend.sh
set -e
cd "$(dirname "$0")"
echo "Starting FastAPI on http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
