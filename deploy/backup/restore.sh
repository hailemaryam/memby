#!/usr/bin/env bash
# Restore a site backed up by backup.sh onto a (new) machine.
#
# Prerequisites on the new machine (see README.md):
#   - a working bench created with the same Frappe branch as in manifest.txt
#     e.g.  bench init frappe-bench --frappe-branch version-16
#   - rclone configured with the same remotes (and crypt passwords) as prod
#
# Usage (as the bench user, from anywhere):
#   ./restore.sh                 # restore the newest backup
#   ./restore.sh 2026-11-22_0230 # restore a specific backup folder
#   ./restore.sh --list          # list available backups
#
# Env overrides: BENCH_DIR, SITE, RCLONE_REMOTE, DB_ROOT_PASSWORD, ADMIN_PASSWORD,
#                PIN_COMMITS=1 (checkout exact app commits from the manifest)
#                FORCE=1 (allow overwriting a site that already exists on this bench)

set -Eeuo pipefail

BENCH_DIR="${BENCH_DIR:-$HOME/frappe-bench}"
SITE="${SITE:-zedir.memby.et}"
RCLONE_REMOTE="${RCLONE_REMOTE:-memby-crypt:}"
PIN_COMMITS="${PIN_COMMITS:-1}"

base="$RCLONE_REMOTE"
case "$base" in *:) ;; *) base="${base%/}/" ;; esac
SITE_REMOTE="${base}$SITE"

if [ "${1:-}" = "--list" ]; then
	rclone lsf --dirs-only "$SITE_REMOTE" | sed 's#/$##' | sort
	exit 0
fi

WHICH="${1:-$(rclone lsf --dirs-only "$SITE_REMOTE" | sed 's#/$##' | sort | tail -1)}"
[ -n "$WHICH" ] || { echo "no backups found at $SITE_REMOTE" >&2; exit 1; }

if [ -d "$BENCH_DIR/sites/$SITE" ] && [ "${FORCE:-0}" != "1" ]; then
	echo "!! site $SITE already exists in $BENCH_DIR. Restoring backup $WHICH would OVERWRITE its data." >&2
	echo "   If that is really what you want, re-run with FORCE=1." >&2
	exit 1
fi

WORK="$BENCH_DIR/restore-tmp/$WHICH"
mkdir -p "$WORK"
echo ">> downloading $SITE_REMOTE/$WHICH -> $WORK"
rclone copy "$SITE_REMOTE/$WHICH" "$WORK"

db_file="$(compgen -G "$WORK/*-database.sql.gz" | head -1)"
pub_file="$(compgen -G "$WORK/*files.t*" | grep -v private-files | head -1)"
priv_file="$(compgen -G "$WORK/*-private-files.t*" | head -1)"
conf_file="$(compgen -G "$WORK/*-site_config_backup.json" | head -1)"
for f in "$db_file" "$pub_file" "$priv_file" "$conf_file"; do
	[ -n "$f" ] && [ -f "$f" ] || { echo "backup set incomplete in $WORK" >&2; exit 1; }
done
gzip -t "$db_file"

echo
cat "$WORK/manifest.txt"
echo

cd "$BENCH_DIR"

# 1. Make sure every app installed on the site is present (same branch/commit).
#    Other apps that only live in the prod bench (erpnext, lending...) are skipped.
site_apps="$(sed -n '/^## installed apps on site/,/^## bench version/p' "$WORK/manifest.txt" | awk 'NF && !/^##/ {print $1}')"
sed -n '/^## app sources/,$p' "$WORK/manifest.txt" | tail -n +2 | while IFS='|' read -r name remote branch commit; do
	name="$(echo "$name" | xargs)"; remote="$(echo "$remote" | xargs)"
	branch="$(echo "$branch" | xargs)"; commit="$(echo "$commit" | xargs)"
	[ -n "$name" ] || continue
	grep -qx "$name" <<<"$site_apps" || continue
	if [ ! -d "apps/$name" ]; then
		echo ">> getting app $name ($branch) from $remote"
		bench get-app --branch "$branch" "$remote" </dev/null
	fi
	current_branch="$(git -C "apps/$name" rev-parse --abbrev-ref HEAD)"
	[ "$current_branch" = "$branch" ] || echo "!! $name is on $current_branch, prod was on $branch"
	if [ "$PIN_COMMITS" = "1" ] && [ "$name" != "frappe" ] && [ "$commit" != "?" ]; then
		git -C "apps/$name" fetch --quiet origin "$branch" || true
		git -C "apps/$name" checkout --quiet "$commit" && echo ">> $name pinned to $commit" \
			|| echo "!! could not checkout $name@$commit, staying on $branch"
	fi
done
bench setup requirements
bench build

# 2. Create the site if it doesn't exist yet.
if [ ! -d "sites/$SITE" ]; then
	: "${DB_ROOT_PASSWORD:?set DB_ROOT_PASSWORD (MariaDB root password on this machine)}"
	: "${ADMIN_PASSWORD:=$(openssl rand -hex 12)}"
	echo ">> creating site $SITE"
	bench new-site "$SITE" --db-root-password "$DB_ROOT_PASSWORD" --admin-password "$ADMIN_PASSWORD"
fi

# 3. Restore DB + files.
echo ">> restoring database and files"
restore_args=(--with-public-files "$pub_file" --with-private-files "$priv_file")
[ -n "${DB_ROOT_PASSWORD:-}" ] && restore_args+=(--db-root-password "$DB_ROOT_PASSWORD")
bench --site "$SITE" restore "$db_file" "${restore_args[@]}"

# 4. Bring back the encryption key, otherwise saved passwords / API secrets
#    (email accounts, SMS gateway, integrations) cannot be decrypted.
enc_key="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("encryption_key",""))' "$conf_file")"
if [ -n "$enc_key" ]; then
	bench --site "$SITE" set-config encryption_key "$enc_key"
	echo ">> encryption_key restored"
else
	echo "!! no encryption_key in backed-up site_config"
fi

# 5. Migrate and finish.
bench --site "$SITE" migrate
bench --site "$SITE" clear-cache
# Keep the scheduler OFF so a restored copy doesn't send SMS reminders / apply
# penalties in parallel with prod. Enable it only once this machine is the real prod.
bench --site "$SITE" disable-scheduler

echo
echo ">> restore of $SITE from $WHICH complete."
echo "   Next: bench --site $SITE enable-scheduler, set up production (nginx/supervisor),"
echo "   SSL and point DNS (Cloudflare) at this machine. See README.md."
