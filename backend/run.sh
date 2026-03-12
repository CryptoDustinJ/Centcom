#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Auto-load project env file when present.
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

# Use gunicorn if available (production), else fallback to Flask dev server (development)
if [[ "${USE_GUNICORN:-true}" == "true" ]] && python -c "import gunicorn" 2>/dev/null; then
  # Dynamic worker calculation: (2 * CPU cores) + 1
  CPU_COUNT=$(python -c "import os; print(os.cpu_count() or 1)")
  WORKERS=$((CPU_COUNT * 2 + 1))
  # Ensure at least 2 workers, at most 8
  if [[ $WORKERS -lt 2 ]]; then WORKERS=2; fi
  if [[ $WORKERS -gt 8 ]]; then WORKERS=8; fi

  export PORT="${PORT:-19000}"
  export WORKERS="${WORKERS:-$WORKERS}"
  export WORKER_CLASS="${WORKER_CLASS:-sync}"
  export TIMEOUT="${TIMEOUT:-120}"
  export WORKER_CONNECTIONS="${WORKER_CONNECTIONS:-1000}"

  echo "Starting gunicorn with $WORKERS workers on 0.0.0.0:$PORT"
  exec python -m gunicorn \
    --workers "$WORKERS" \
    --worker-class "$WORKER_CLASS" \
    --bind "0.0.0.0:$PORT" \
    --timeout "$TIMEOUT" \
    --worker-connections "$WORKER_CONNECTIONS" \
    --access-logfile - \
    --error-logfile - \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --preload \
    "backend.app:app"
else
  echo "Gunicorn not available or disabled, using Flask dev server"
  exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/backend/app.py"
fi
