#!/usr/bin/env bash
# Weekly off-site backup of one Frappe site to Google Drive (via rclone).
#
# Produces, in a dated folder on the remote:
#   *-database.sql.gz            full DB dump
#   *-files.tar(.gz)             public files
#   *-private-files.tar(.gz)     private files
#   *-site_config_backup.json    site config (contains encryption_key + DB password)
#   manifest.txt                 bench/app versions + git remotes/commits needed to rebuild
#
# Runs as the bench user (haile) from cron. See README.md in this folder.

set -Eeuo pipefail
umask 077   # backups contain DB password + encryption key

# ---- settings (override via env or /home/haile/.memby-backup.env) ---------
ENV_FILE="${ENV_FILE:-$HOME/.memby-backup.env}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

BENCH_DIR="${BENCH_DIR:-/home/haile/frappe-bench}"
SITE="${SITE:-zedir.memby.et}"
BENCH_BIN="${BENCH_BIN:-/usr/local/bin/bench}"
RCLONE_BIN="${RCLONE_BIN:-$(command -v rclone || echo /usr/bin/rclone)}"
# "memby-crypt:" = encrypted remote wrapping Google Drive (recommended).
# Set to e.g. "gdrive:memby-backups" to upload unencrypted.
RCLONE_REMOTE="${RCLONE_REMOTE:-memby-crypt:}"
KEEP_WEEKS="${KEEP_WEEKS:-8}"            # remote folders to keep
LOCAL_DIR="${LOCAL_DIR:-$BENCH_DIR/offsite-backups/$SITE}"
KEEP_LOCAL="${KEEP_LOCAL:-2}"            # local folders to keep
LOG_FILE="${LOG_FILE:-$BENCH_DIR/logs/offsite-backup.log}"
# -----------------------------------------------------------------------------

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p "$(dirname "$LOG_FILE")" "$LOCAL_DIR"
exec >>"$LOG_FILE" 2>&1

log() { echo "[$(date '+%F %T %Z')] $*"; }
trap 'log "FAILED (line $LINENO, exit $?)"' ERR

# Never run two at once.
exec 9>"$LOCAL_DIR/.lock"
flock -n 9 || { log "another backup is running, skipping"; exit 1; }

STAMP="$(date +%Y-%m-%d_%H%M)"
OUT="$LOCAL_DIR/$STAMP"
mkdir -p "$OUT"
log "=== backup of $SITE -> $OUT ==="

cd "$BENCH_DIR"
"$BENCH_BIN" --site "$SITE" backup --with-files --compress --backup-path "$OUT"

# Sanity: all four parts must be present and the DB dump non-trivial.
for pat in '*-database.sql.gz' '*-private-files.t*' '*-site_config_backup.json'; do
	compgen -G "$OUT/$pat" >/dev/null || { log "missing $pat in $OUT"; exit 1; }
done
[ "$(compgen -G "$OUT/*files.t*" | wc -l)" -eq 2 ] || { log "public/private files archives missing"; exit 1; }
db_file="$(compgen -G "$OUT/*-database.sql.gz" | head -1)"
gzip -t "$db_file"
[ "$(stat -c %s "$db_file")" -gt 10240 ] || { log "DB dump suspiciously small"; exit 1; }

# Manifest: everything needed to rebuild a matching bench elsewhere.
{
	echo "site: $SITE"
	echo "taken: $(date '+%F %T %Z')"
	echo "host: $(hostname)"
	echo "os: $(. /etc/os-release && echo "$PRETTY_NAME")"
	echo "python: $("$BENCH_DIR/env/bin/python" --version 2>&1)"
	echo "node: $(node --version 2>/dev/null || echo n/a)"
	echo "mariadb: $(mariadb --version 2>/dev/null || echo n/a)"
	echo
	echo "## installed apps on site"
	"$BENCH_BIN" --site "$SITE" list-apps 2>&1 || true
	echo
	echo "## bench version"
	"$BENCH_BIN" version 2>&1 || true
	echo
	echo "## app sources (app | remote | branch | commit)"
	for a in "$BENCH_DIR"/apps/*/; do
		a="${a%/}"
		name="$(basename "$a")"
		remote="$(git -C "$a" remote get-url upstream 2>/dev/null || git -C "$a" remote get-url origin 2>/dev/null || echo '?')"
		remote="$(echo "$remote" | sed -E 's#(https?://)[^@/]+@#\1#')"   # strip tokens
		branch="$(git -C "$a" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
		commit="$(git -C "$a" rev-parse HEAD 2>/dev/null || echo '?')"
		echo "$name | $remote | $branch | $commit"
	done
} >"$OUT/manifest.txt"

# Ship the restore script with every set, so restoring never depends on GitHub.
cp "$(dirname "$(readlink -f "$0")")/restore.sh" "$OUT/restore.sh" 2>/dev/null || true

# Upload and verify.
base="$RCLONE_REMOTE"
case "$base" in *:) ;; *) base="${base%/}/" ;; esac
DEST="${base}$SITE/$STAMP"
log "uploading to $DEST"
"$RCLONE_BIN" copy "$OUT" "$DEST" --exclude '.lock'
# --download: crypt remotes have no hashes, so compare actual content.
"$RCLONE_BIN" check "$OUT" "$DEST" --one-way --download --exclude '.lock'
log "upload verified"

# Prune remote: keep newest KEEP_WEEKS folders.
SITE_REMOTE="${DEST%/*}"
mapfile -t remote_dirs < <("$RCLONE_BIN" lsf --dirs-only "$SITE_REMOTE" | sed 's#/$##' | sort)
if [ "${#remote_dirs[@]}" -gt "$KEEP_WEEKS" ]; then
	for d in "${remote_dirs[@]:0:${#remote_dirs[@]}-KEEP_WEEKS}"; do
		log "pruning remote $d"
		"$RCLONE_BIN" purge "$SITE_REMOTE/$d"
	done
fi

# Prune local: keep newest KEEP_LOCAL folders.
mapfile -t local_dirs < <(find "$LOCAL_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
if [ "${#local_dirs[@]}" -gt "$KEEP_LOCAL" ]; then
	for d in "${local_dirs[@]:0:${#local_dirs[@]}-KEEP_LOCAL}"; do
		rm -rf -- "${LOCAL_DIR:?}/$d"
	done
fi

log "=== done: $DEST ==="
