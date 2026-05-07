#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv/bin/python. Create the virtualenv and install requirements first:" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  source .venv/bin/activate" >&2
  echo "  python -m pip install -r requirements.txt" >&2
  exit 1
fi

echo "Applying Django migrations..."
.venv/bin/python web/manage.py migrate

if [[ "${SYNC_ON_START:-1}" != "0" ]]; then
  echo
  echo "Syncing ShareFile mirror..."
  if ! PYTHONPATH=src .venv/bin/python scripts/update_sharefile_mirror.py; then
    echo "ShareFile sync failed; starting the app with the latest local state." >&2
  fi
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
START_PORT="$PORT"

while ! .venv/bin/python - "$HOST" "$PORT" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    try:
        sock.bind((host, port))
    except OSError:
        raise SystemExit(1)
PY
do
  PORT=$((PORT + 1))
done

echo
echo "Starting Testifize app:"
echo "  http://${HOST}:${PORT}/"
echo "  http://${HOST}:${PORT}/admin/"
if [[ "$PORT" != "$START_PORT" ]]; then
  echo "  port ${START_PORT} was busy, using ${PORT} instead"
fi
echo
echo "If you do not have an admin user yet, stop this server and run:"
echo "  .venv/bin/python web/manage.py createsuperuser"
echo

exec .venv/bin/python web/manage.py runserver "${HOST}:${PORT}"
