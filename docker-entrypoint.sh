#!/bin/sh
set -e
PORT="${PORT:-5055}"
export STRATINDEX_DB_PATH="${STRATINDEX_DB_PATH:-/data/stratindex.db}"
export STRATINDEX_DATA_DIR="${STRATINDEX_DATA_DIR:-/data}"

mkdir -p "$(dirname "$STRATINDEX_DB_PATH")"
# Create schema / seed if empty (safe; does not wipe existing rows unless force)
python -c "import db; print('DB:', db.init_db())"

if [ "$1" = "gunicorn" ] || [ -z "$1" ]; then
  exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --threads "${WEB_THREADS:-4}" \
    --timeout "${WEB_TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile - \
    app:app
fi

exec "$@"
