#!/usr/bin/env bash
# Local personal V1. Owns and stops only the processes it starts.
set -euo pipefail
cd "$(dirname "$0")/.."
for tool in uv node npm curl; do
  if ! command -v "$tool" >/dev/null; then
    echo "Programmet $tool saknas. Följ macOS-guiden i README.md." >&2
    exit 1
  fi
done
if curl -fsS --max-time 3 http://127.0.0.1:3000/api/status 2>/dev/null | grep -q '"version":"1.0.0"'; then
  echo 'Fotbolls-AI V1 körs redan. Ingen ny process startades.'
  exit 0
fi
if [ ! -f .env ]; then
  if ! command -v openssl >/dev/null; then echo 'openssl behövs för lokalt databaslösenord.' >&2; exit 1; fi
  umask 077
  db_password=$(openssl rand -hex 24)
  printf 'POSTGRES_PASSWORD=%s\nDATABASE_URL=postgresql+psycopg://football:%s@127.0.0.1:5432/football\n' "$db_password" "$db_password" > .env
  unset db_password
fi
set -a
source .env
set +a
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
if [[ "${DATABASE_URL:-}" == postgresql*'@127.0.0.1:5432/football' || "${DATABASE_URL:-}" == postgresql*'@localhost:5432/football' ]]; then
  if ! command -v docker >/dev/null; then echo 'Installera och öppna Docker Desktop enligt README.md.' >&2; exit 1; fi
  docker compose up -d --wait db
fi
bash scripts/setup.sh
(
 cd backend
 ../.venv/bin/python -m app.backup --restore-if-empty
 if ! ../.venv/bin/python -m app.sync --bootstrap; then
   echo 'Datakällan kunde inte nås. Tidigare data bevaras; granska Källstatus i appen.' >&2
 fi
 if ! ../.venv/bin/python -m app.football_data; then
   echo 'Kompletterande resultat/odds kunde inte hämtas. Appen visar saknade data och avstår vid otillräckligt underlag.' >&2
 fi
 ../.venv/bin/python -m app.pipeline predict
 ../.venv/bin/python -m app.pipeline demo
 ../.venv/bin/python -m app.backup
)
(cd frontend && npm run build)
backend_pid='';frontend_pid='';worker_pid=''
cleanup() {
  for process_id in "$backend_pid" "$frontend_pid" "$worker_pid"; do
    if [ -n "$process_id" ]; then kill "$process_id" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT INT TERM
bash scripts/backend.sh &
backend_pid=$!
curl -fsS --retry 20 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/api/health >/dev/null 2>&1
(cd frontend && exec node node_modules/next/dist/bin/next start --hostname 127.0.0.1) &
frontend_pid=$!
(cd backend && exec ../.venv/bin/python -m app.worker --sync --interval 3600) &
worker_pid=$!
curl -fsS --retry 20 --retry-connrefused --retry-delay 1 http://127.0.0.1:3000/api/status >/dev/null 2>&1
if ! kill -0 "$backend_pid" "$frontend_pid" "$worker_pid" 2>/dev/null; then
 echo 'En tjänst kunde inte startas. Kontrollera meddelandena ovan och att port 3000/8000 är ledig.' >&2
 exit 1
fi
echo 'Fotbolls-AI V1 körs lokalt. Öppna localhost:3000 på din Mac. Stoppa med Ctrl+C.'
wait
