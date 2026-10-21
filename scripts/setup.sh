#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/fotbolls-uv-cache}"
uv venv --allow-existing .venv
uv pip sync --python .venv/bin/python backend/requirements.lock
if [ -f .env ]; then set -a; source .env; set +a; fi
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
(cd backend && ../.venv/bin/alembic upgrade head)
(cd frontend && npm ci --cache /tmp/fotbolls-npm-cache --no-audit --no-fund)
