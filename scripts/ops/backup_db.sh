#!/usr/bin/env bash
# Nightly PostgreSQL backup for the JDS beta. Never prints DATABASE_URL.
# Required env: DATABASE_URL (postgresql:// or postgresql+psycopg://), BACKUP_PASSPHRASE
# Optional env: BACKUP_DIR (default ./backups), BACKUP_KEEP_DAYS (default 14),
#               BACKUP_RCLONE_REMOTE (e.g. "offsite:jds-backups/db") to copy off-site with rclone.
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is required (dumps contain customer data and are encrypted)}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
mkdir -p "$BACKUP_DIR"
umask 077
url="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$BACKUP_DIR/jds-db-$stamp.dump.gpg"
pg_dump --format=custom --no-owner --no-privileges --dbname="$url" \
  | gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase-fd 3 -o "$out" 3<<<"$BACKUP_PASSPHRASE"
test -s "$out"
echo "backup written: $(basename "$out") ($(du -h "$out" | cut -f1))"
find "$BACKUP_DIR" -name 'jds-db-*.dump.gpg' -mtime +"$KEEP_DAYS" -delete
if [[ -n "${BACKUP_RCLONE_REMOTE:-}" ]]; then
  rclone copy "$out" "$BACKUP_RCLONE_REMOTE" --quiet
  echo "copied off-site"
fi
# Restore: gpg -d FILE | pg_restore --clean --if-exists --no-owner -d "$TARGET_URL"
