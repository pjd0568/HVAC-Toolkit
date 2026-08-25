#!/bin/bash
# Double-click in Finder (or run: ./run-local.command) to start the local
# Flask app, wait until it is ready, and open it in the default browser.
#
# Always uses this repo’s Compose Postgres (user/db app) — never the Railway
# DATABASE_URL in .env. If another project already owns 5432, HVAC Postgres
# is published on 5433.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WEB="$ROOT/web"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5000}"
OPEN_PATH="${OPEN_PATH:-/login?preview=1}"
COMPOSE_FILE="$ROOT/docker-compose.yml"
HVAC_DB_NAME="hvac-toolkit-db-1"

cd "$ROOT"

if [ ! -x "$WEB/.venv/bin/python" ]; then
  echo "No venv at web/.venv."
  echo "Create it once:"
  echo "  cd web && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  echo
  read -r -p "Press Enter to close…" || true
  exit 1
fi

if [ ! -f "$ROOT/.env" ] && [ ! -f "$WEB/.env" ]; then
  echo "No .env found. Copying .env.example → .env (edit SECRET_KEY later)."
  cp "$ROOT/.env.example" "$ROOT/.env"
fi

tcp_open() {
  local port="$1"
  "$WEB/.venv/bin/python" -c "
import socket, sys
port = int(sys.argv[1])
s = socket.socket()
s.settimeout(0.4)
try:
    s.connect(('127.0.0.1', port))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
" "$port" 2>/dev/null
}

published_db_port() {
  docker inspect -f '{{range $p, $conf := .NetworkSettings.Ports}}{{if eq $p "5432/tcp"}}{{(index $conf 0).HostPort}}{{end}}{{end}}' "$HVAC_DB_NAME" 2>/dev/null || true
}

# Unlock the suite for local review. Force local Compose credentials so a
# Railway DATABASE_URL in .env cannot leak into this session.
export ACCESS_DEV_TIER="${ACCESS_DEV_TIER:-pro}"
export FLASK_APP="${FLASK_APP:-wsgi}"
export SECRET_KEY="${SECRET_KEY:-dev-only-change-me}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to start the HVAC Toolkit Postgres container."
  read -r -p "Press Enter to close…" || true
  exit 1
fi

DB_STATUS="$(docker inspect -f '{{.State.Status}}' "$HVAC_DB_NAME" 2>/dev/null || echo missing)"
PG_HOST_PORT="$(published_db_port)"

if [ "$DB_STATUS" = "running" ] && [ -n "$PG_HOST_PORT" ]; then
  echo "Using existing HVAC Postgres on 127.0.0.1:${PG_HOST_PORT}."
else
  if tcp_open 5432; then
    PG_HOST_PORT="${POSTGRES_HOST_PORT:-5433}"
    echo "Port 5432 is in use by another database. Publishing HVAC Postgres on ${PG_HOST_PORT}."
  else
    PG_HOST_PORT="${POSTGRES_HOST_PORT:-5432}"
  fi
  echo "Starting HVAC Postgres (docker compose up -d db)…"
  POSTGRES_HOST_PORT="$PG_HOST_PORT" docker compose -f "$COMPOSE_FILE" up -d db
  PG_HOST_PORT="$(published_db_port)"
  PG_HOST_PORT="${PG_HOST_PORT:-${POSTGRES_HOST_PORT:-5433}}"
fi

export DATABASE_URL="postgresql://app:app@127.0.0.1:${PG_HOST_PORT}/app"

echo "Waiting for HVAC Postgres on 127.0.0.1:${PG_HOST_PORT}…"
for i in $(seq 1 40); do
  if tcp_open "$PG_HOST_PORT"; then
    break
  fi
  if [ "$i" -eq 40 ]; then
    echo "HVAC Postgres did not become ready on 127.0.0.1:${PG_HOST_PORT}."
    read -r -p "Press Enter to close…" || true
    exit 1
  fi
  sleep 0.5
done

if tcp_open "$PORT"; then
  for try in 5002 5003 5004; do
    if ! tcp_open "$try"; then
      echo "Port ${PORT} is busy — using ${try} for Flask."
      PORT="$try"
      break
    fi
  done
fi

URL="http://${HOST}:${PORT}${OPEN_PATH}"

echo "Applying database migrations…"
(
  cd "$WEB"
  # shellcheck source=/dev/null
  source .venv/bin/activate
  flask --app wsgi db upgrade
)

echo "Starting Flask on ${URL%%\?*} …"
(
  cd "$WEB"
  # shellcheck source=/dev/null
  source .venv/bin/activate
  exec flask --app wsgi run --debug --host "$HOST" --port "$PORT"
) &
FLASK_PID=$!

cleanup() {
  if kill -0 "$FLASK_PID" 2>/dev/null; then
    kill "$FLASK_PID" 2>/dev/null || true
    wait "$FLASK_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "Waiting for the app…"
for i in $(seq 1 40); do
  if curl -fsS -o /dev/null --max-time 1 "http://${HOST}:${PORT}/health" \
    || curl -fsS -o /dev/null --max-time 1 "http://${HOST}:${PORT}/"; then
    break
  fi
  if ! kill -0 "$FLASK_PID" 2>/dev/null; then
    echo "Flask exited before it became ready."
    wait "$FLASK_PID" || true
    read -r -p "Press Enter to close…" || true
    exit 1
  fi
  if [ "$i" -eq 40 ]; then
    echo "App did not respond in time. Opening the browser anyway."
    break
  fi
  sleep 0.4
done

echo "Opening $URL"
open "$URL"

echo
echo "Server is running. Close this window or press Ctrl+C to stop."
wait "$FLASK_PID"
