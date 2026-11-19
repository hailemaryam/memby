# Weekly off-site backup — zedir.memby.et

Prod: VPS (Ubuntu 24.04, TZ Africa/Addis_Ababa), bench `/home/haile/frappe-bench`
(Frappe v16, user `haile`). The site uses apps `frappe` + `memby`.

The existing bench cron (`0 */6 * * *  bench --site all backup`) only keeps **local** DB dumps on the same
server. If the VPS is lost, they are lost with it. `backup.sh` adds a weekly **off-site** copy to Google Drive
with everything needed to rebuild the site somewhere else:

| file | why |
|---|---|
| `*-database.sql.gz` | all data |
| `*-files.tgz`, `*-private-files.tgz` | uploaded attachments, member photos |
| `*-site_config_backup.json` | **`encryption_key`**: without it, saved passwords/API secrets (SMS gateway, email) can't be decrypted |
| `manifest.txt` | Frappe/app branches + exact commits, Python/Node/MariaDB versions |

Backups are encrypted with an rclone `crypt` remote before they reach Google Drive, because they contain member
personal data, bank data and DB credentials. The newest 8 weekly sets are kept on Drive and 2 on the server.

---

## 1. One-time setup on prod

```bash
ssh root@<prod-server-ip>
apt-get install -y rclone          # or: curl https://rclone.org/install.sh | bash  (newer version)
su - haile
```

### 1a. Google Drive remote (`gdrive`)

The server has no browser, so the Google sign-in happens on your PC:

1. On your **Windows PC**: install rclone (`winget install Rclone.Rclone`), then run `rclone authorize "drive"`.
   A browser opens. Sign in with the Google account that should hold the backups. Copy the token JSON it prints.
2. On the **server** as `haile`: `rclone config` → `n` (new) → name `gdrive` → storage `drive` →
   client_id/secret empty → scope **`drive.file`** (rclone can only see files it created, so a compromised
   server can't read the rest of your Drive) → defaults → *Use web browser?* **n** → paste the token → done.
3. Test it: `rclone lsd gdrive:`

### 1b. Encrypted remote (`memby-crypt`)

`rclone config` → `n` → name `memby-crypt` → storage `crypt` → remote `gdrive:memby-backups` →
filename encryption `standard` → directory encryption `true` → **let rclone generate a strong password**
for both password and salt.

> **Save both crypt passwords (and a copy of `~/.config/rclone/rclone.conf`) in a password manager,
> outside this server.** Without them the backups on Drive cannot be read. Nobody can recover them for you.

If you prefer no encryption, skip 1b and put `RCLONE_REMOTE=gdrive:memby-backups` in `~/.memby-backup.env`.

### 1c. Install the script + cron

The script ships with the app. Get it with `git -C ~/frappe-bench/apps/memby pull`. Don't use `bench update`,
which updates and migrates every app and site on this bench. The script is then at
`/home/haile/frappe-bench/apps/memby/deploy/backup/backup.sh`.

```bash
# first run by hand (~10 s) and check the log
bash ~/frappe-bench/apps/memby/deploy/backup/backup.sh; tail -20 ~/frappe-bench/logs/offsite-backup.log
rclone lsf -R memby-crypt:            # should show zedir.memby.et/<date>/...
crontab -e
```

Add this line (Sunday 02:30 Addis Ababa time, server TZ is EAT):

```cron
30 2 * * 0 /bin/bash /home/haile/frappe-bench/apps/memby/deploy/backup/backup.sh
```

Optional overrides in `/home/haile/.memby-backup.env`: `KEEP_WEEKS=12`, `RCLONE_REMOTE=...`, `SITE=...`.
For backups of the other sites on this bench, add more cron lines with `SITE=other.site /path/backup.sh`.

**Monitoring:** check `~/frappe-bench/logs/offsite-backup.log` now and then. Every run ends with `=== done`,
and a failed run logs `FAILED (line N)`.

---

## 2. Restore on another machine

1. A fresh Ubuntu 24.04 server. Install the Frappe v16 prerequisites (MariaDB 10.11, Redis, Python 3.14 /
   whatever `manifest.txt` says, Node, yarn, wkhtmltopdf) and `pip install frappe-bench`.
2. As a non-root user: `bench init frappe-bench --frappe-branch version-16 && cd frappe-bench`
3. Install rclone and copy your saved `rclone.conf` to `~/.config/rclone/rclone.conf`
   (or recreate `gdrive` + `memby-crypt` with **the same crypt passwords**).
4. Get the restore script and run it:
   ```bash
   curl -O https://raw.githubusercontent.com/hailemaryam/memby/develop/deploy/backup/restore.sh
   bash restore.sh --list                                    # available backups
   DB_ROOT_PASSWORD='<mariadb root pw>' bash restore.sh      # newest, or: bash restore.sh 2026-11-22_0230
   ```
   (`restore.sh` is also inside every backup set on Drive, in case GitHub isn't reachable.)
   It refuses to touch a site that already exists unless you pass `FORCE=1`, so it can't overwrite live
   prod by accident.
   ```
   ```
   It downloads the set and fetches `memby` at the exact prod commit. It then creates the site, restores the
   DB and files, puts back the `encryption_key`, migrates, and leaves the **scheduler disabled** so the copy
   doesn't send SMS reminders or apply penalties alongside prod.
5. To make it the live prod:
   ```bash
   bench --site zedir.memby.et enable-scheduler
   sudo bench setup production <user>
   bench setup nginx && sudo service nginx reload
   ```
   Then point the `zedir.memby.et` A record in Cloudflare at the new IP and set up SSL (Cloudflare origin cert
   or `sudo bench setup lets-encrypt zedir.memby.et`). The old `ssl_certificate` paths in site_config may
   need updating.

### Do a trial restore

A backup that has never been restored is not proven. Once the first weekly set is on Drive, restore it on a
throwaway VM (steps above), log in and check members, payments and an attachment. Repeat every few months.
