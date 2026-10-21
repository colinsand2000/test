#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then set -a; source .env; set +a; fi
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
cd backend
exec ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
