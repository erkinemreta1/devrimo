#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_DIR="/opt/devrimo"
BACKUP_DIR="/opt/devrimo-backups"
RELEASE_ARCHIVE="${RELEASE_ARCHIVE:?RELEASE_ARCHIVE is required}"
DEPLOY_SHA="${DEPLOY_SHA:?DEPLOY_SHA is required}"
NODE_BIN="/opt/devrimo/node/bin"
LOCK_FILE="/var/lock/devrimo-deploy.lock"

exec 9>"$LOCK_FILE"
flock -n 9 || { echo "Another Devrimo deployment is already running"; exit 1; }

test -f "$RELEASE_ARCHIVE"
test -f "$DEPLOY_DIR/backend/.env"
test -f "$DEPLOY_DIR/frontend/.env.local"

stamp="$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Keep a compact source rollback snapshot. Runtime dependencies, caches,
# credentials, campus state, and databases are deliberately excluded.
tar -czf "$BACKUP_DIR/source-$stamp.tar.gz" \
  --exclude='./frontend/node_modules' \
  --exclude='./frontend/.next' \
  --exclude='./frontend/.env.local' \
  --exclude='./backend/.venv' \
  --exclude='./backend/.env' \
  --exclude='./backend/.campus-state' \
  --exclude='./backend/.agentos' \
  --exclude='./backend/devrimo.db*' \
  --exclude='./node' \
  --exclude='./.npm' \
  --exclude='./.local' \
  -C "$DEPLOY_DIR" .
chmod 600 "$BACKUP_DIR/source-$stamp.tar.gz"

# SQLite's backup API produces a consistent snapshot even while the old API
# process is still serving reads and writes.
runuser -u devrimo -- "$DEPLOY_DIR/backend/.venv/bin/python" - "$DEPLOY_DIR/backend/devrimo.db" "$BACKUP_DIR/devrimo.db-$stamp" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(sys.argv[1])
destination = sqlite3.connect(sys.argv[2])
with destination:
    source.backup(destination)
source.close()
destination.close()
PY
chmod 600 "$BACKUP_DIR/devrimo.db-$stamp"

tar -xzf "$RELEASE_ARCHIVE" -C "$DEPLOY_DIR"
chown -R devrimo:devrimo "$DEPLOY_DIR/backend" "$DEPLOY_DIR/frontend"

runuser -u devrimo -- bash -lc "
  set -e
  cd '$DEPLOY_DIR/backend'
  .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 || true
  .venv/bin/python -m pip install -r requirements.txt
"

runuser -u devrimo -- bash -lc "
  set -e
  export PATH='$NODE_BIN':\$PATH
  cd '$DEPLOY_DIR/frontend'
  npm ci
  npm run build
"

# Keep the migration/restart window short. Alembic migrations in this project
# are additive; the database snapshot above remains available for recovery.
systemctl stop devrimo-api
if ! runuser -u devrimo -- bash -lc "cd '$DEPLOY_DIR/backend' && .venv/bin/python -m alembic upgrade head"; then
  systemctl start devrimo-api
  exit 1
fi

systemctl restart devrimo-api devrimo-web

for attempt in {1..30}; do
  api_ok=false
  web_ok=false
  curl -fsS http://127.0.0.1:8000/health >/dev/null && api_ok=true
  curl -fsS -o /dev/null http://127.0.0.1:3000/ && web_ok=true
  if "$api_ok" && "$web_ok"; then
    printf '%s\n' "$DEPLOY_SHA" > "$DEPLOY_DIR/.deployed-sha"
    chown devrimo:devrimo "$DEPLOY_DIR/.deployed-sha"
    rm -f "$RELEASE_ARCHIVE"
    echo "Devrimo deployment $DEPLOY_SHA is healthy"
    exit 0
  fi
  sleep 2
done

systemctl status devrimo-api devrimo-web --no-pager || true
journalctl -u devrimo-api -u devrimo-web -n 100 --no-pager || true
exit 1
