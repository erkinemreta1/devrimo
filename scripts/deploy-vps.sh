#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_DIR="/opt/devrimo"
BACKUP_DIR="$DEPLOY_DIR/.backups"
RELEASE_ARCHIVE="${RELEASE_ARCHIVE:?RELEASE_ARCHIVE is required}"
DEPLOY_SHA="${DEPLOY_SHA:?DEPLOY_SHA is required}"
NODE_BIN="/opt/devrimo/node/bin"
LOCK_FILE="$DEPLOY_DIR/.deploy.lock"

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
  --exclude='./.ssh' \
  --exclude='./.backups' \
  --exclude='./.deploy.lock' \
  --exclude='./.deployed-sha' \
  -C "$DEPLOY_DIR" .
chmod 600 "$BACKUP_DIR/source-$stamp.tar.gz"

# SQLite's backup API produces a consistent snapshot even while the old API
# process is still serving reads and writes.
"$DEPLOY_DIR/backend/.venv/bin/python" - "$DEPLOY_DIR/backend/devrimo.db" "$BACKUP_DIR/devrimo.db-$stamp" <<'PY'
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

stage_dir="$(mktemp -d "$DEPLOY_DIR/.release.XXXXXX")"
trap 'rm -rf "$stage_dir"' EXIT
tar -xzf "$RELEASE_ARCHIVE" -C "$stage_dir"

# Deploy an exact source tree instead of extracting over the previous release.
# Runtime state and secrets are preserved; stale source files are removed.
rsync -a --delete \
  --exclude='.env.local' \
  --exclude='node_modules/' \
  --exclude='.next/' \
  "$stage_dir/frontend/" "$DEPLOY_DIR/frontend/"
rsync -a --delete \
  --exclude='.env' \
  --exclude='.venv/' \
  --exclude='.campus-state/' \
  --exclude='.agentos/' \
  --exclude='devrimo.db*' \
  --exclude='secrets/' \
  "$stage_dir/backend/" "$DEPLOY_DIR/backend/"

bash -lc "
  set -e
  cd '$DEPLOY_DIR/backend'
  .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 || true
  .venv/bin/python -m pip install -r requirements.txt
"

bash -lc "
  set -e
  export PATH='$NODE_BIN':\$PATH
  cd '$DEPLOY_DIR/frontend'
  npm ci
  npm run build
"

# Keep the migration/restart window short. Alembic migrations in this project
# are additive; the database snapshot above remains available for recovery.
sudo /usr/bin/systemctl stop devrimo-api.service
if ! bash -lc "cd '$DEPLOY_DIR/backend' && .venv/bin/python -m alembic upgrade head"; then
  sudo /usr/bin/systemctl start devrimo-api.service
  exit 1
fi

sudo /usr/bin/systemctl restart devrimo-api.service
sudo /usr/bin/systemctl restart devrimo-web.service

for attempt in {1..30}; do
  api_ok=false
  web_ok=false
  curl -fsS http://127.0.0.1:8000/health >/dev/null && api_ok=true
  curl -fsS -o /dev/null http://127.0.0.1:3000/ && web_ok=true
  if "$api_ok" && "$web_ok"; then
    printf '%s\n' "$DEPLOY_SHA" > "$DEPLOY_DIR/.deployed-sha"
    rm -f "$RELEASE_ARCHIVE"
    echo "Devrimo deployment $DEPLOY_SHA is healthy"
    exit 0
  fi
  sleep 2
done

sudo /usr/bin/systemctl status devrimo-api.service --no-pager || true
sudo /usr/bin/systemctl status devrimo-web.service --no-pager || true
journalctl -u devrimo-api.service -u devrimo-web.service -n 100 --no-pager || true
exit 1
