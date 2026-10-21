FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; npm ci --no-audit --no-fund
COPY frontend/ ./
ENV API_URL=http://127.0.0.1:8000 NEXT_TELEMETRY_DISABLED=1
RUN npm run build
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 NEXT_TELEMETRY_DISABLED=1 API_URL=http://127.0.0.1:8000 NODE_ENV=production
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates libgomp1 libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
WORKDIR /app/backend
COPY backend/requirements.lock ./
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; pip install --no-cache-dir -r requirements.lock
COPY backend/ ./
COPY --from=web /web /app/frontend
COPY deploy/render-start.sh /app/deploy/render-start.sh
RUN mkdir -p /var/data/artifacts && rm -rf /app/backend/artifacts && ln -s /var/data/artifacts /app/backend/artifacts
CMD ["bash", "/app/deploy/render-start.sh"]
