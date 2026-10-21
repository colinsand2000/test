#!/usr/bin/env bash
set -euo pipefail
cd /app/backend
mkdir -p /var/data/artifacts
alembic upgrade head
# Network outages preserve the last data; policy gates suppress stale candidates.
python -m app.sync --bootstrap || true
python -m app.football_data || true
python -m app.pipeline predict
api_pid='';worker_pid='';web_pid=''
cleanup() {
 for process_id in "$api_pid" "$worker_pid" "$web_pid"; do
  if [ -n "$process_id" ]; then kill "$process_id" 2>/dev/null || true; fi
 done
}
trap cleanup EXIT INT TERM
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
python -m app.worker --sync --interval 3600 &
worker_pid=$!
(cd /app/frontend && exec node node_modules/next/dist/bin/next start --hostname 0.0.0.0 --port "${PORT:-10000}") &
web_pid=$!
# Restart the full service if any component exits, including a failed worker.
wait -n "$api_pid" "$worker_pid" "$web_pid" || true
exit 1
