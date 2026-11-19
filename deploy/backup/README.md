# Weekly off-site backup — zedir.memby.et

Prod: VPS (Ubuntu 24.04, TZ Africa/Addis_Ababa), bench `/home/haile/frappe-bench`
(Frappe v16, user `haile`). The site uses apps `frappe` + `memby`.

The existing bench cron (`0 */6 * * *  bench --site all backup`) only keeps **local** DB dumps on the same
server. If the VPS is lost, they are lost with it. `backup.sh` makes a full set with everything needed to
rebuild the site somewhere else:

| file | why |
|---|---|
| `*-database.sql.gz` | all data |
| `*-files.tgz`, `*-private-files.tgz` | uploaded attachments, member photos |
| `*-site_config_backup.json` | **`encryption_key`**: without it, saved passwords/API secrets (SMS gateway, email) can't be decrypted |
| `manifest.txt` | Frappe/app branches + exact commits, Python/Node/MariaDB versions |
| `restore.sh`, `SHA256SUMS` | the restore script and checksums for every file |

There are two ways to get the set off the server:

- **A. Pull to a Windows PC over SSH** (current setup). `pull-backup.ps1` runs weekly from Task Scheduler.
- **B. Push to Google Drive with rclone**. The server's cron uploads it, encrypted.

The sets contain member personal data, bank data and DB credentials. Keep them only on machines and accounts you
control.

---

## A. Pull to a Windows PC (current setup)

Requirements: the PC has key-based SSH to the server as `root` (or `haile`). On prod, the scripts are in
`apps/memby` (get them with `git -C ~/frappe-bench/apps/memby pull`; don't use `bench update`, which updates and
migrates every app and site on this bench).

The PC script SSHes in and runs `backup.sh` with `RCLONE_REMOTE=none` as `haile`. It then copies the new set
with `scp` to `Documents\MembyBackups\zedir.memby.et\<date>` and checks every file against `SHA256SUMS`. The
newest 12 sets are kept on the PC and 2 on the server. The log is `Documents\MembyBackups\pull-backup.log`.

Run it by hand:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File deploy\backup\pull-backup.ps1 -Server root@<prod-server-ip>
```

Weekly task (Sunday 10:00; runs as soon as possible after the PC is back on if it was off at that time):

```powershell
$a = New-ScheduledTaskAction -Execute powershell.exe -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\path\to\memby\deploy\backup\pull-backup.ps1" -Server root@<prod-server-ip>'
$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 10am
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "Memby zedir backup" -Action $a -Trigger $t -Settings $s
```

The task runs as your Windows user while you are signed in, because it uses your SSH key in `~\.ssh`.
Test it with `Start-ScheduledTask "Memby zedir backup"`.

A single PC is a single point of failure too. Copy the `MembyBackups` folder to an external disk now and then,
or keep it in a synced folder.

---

## B. Push to Google Drive (alternative)

1. On the server: `apt-get install -y rclone`, then `su - haile`.
2. On your **PC**: `rclone authorize "drive"`, sign in, and copy the token. On the **server** run `rclone config`:
   create a remote `gdrive` (storage `drive`, scope **`drive.file`**, *use web browser?* **n**, paste the token).
3. Still in `rclone config`, create a remote `memby-crypt` (storage `crypt`, remote `gdrive:memby-backups`) and
   let rclone generate the password and salt. **Save both, and a copy of `~/.config/rclone/rclone.conf`, in a
   password manager outside the server.** Without them the backups can't be read.
4. Test it with `bash ~/frappe-bench/apps/memby/deploy/backup/backup.sh`, then `rclone lsf -R memby-crypt:`.
5. Add a cron line with `crontab -e`: `30 2 * * 0 /bin/bash /home/haile/frappe-bench/apps/memby/deploy/backup/backup.sh`

Optional overrides go in `/home/haile/.memby-backup.env`: `KEEP_WEEKS=12`, `RCLONE_REMOTE=...`, `SITE=...`.
Server log: `~/frappe-bench/logs/offsite-backup.log`. Each run ends with `=== done`, or `FAILED (line N)`.

---

## Restore on another machine

1. A fresh Ubuntu 24.04 server. Install the Frappe v16 prerequisites (MariaDB 10.11, Redis, the Python and Node
   versions in `manifest.txt`, yarn, wkhtmltopdf) and `pip install frappe-bench`.
2. As a non-root user: `bench init frappe-bench --frappe-branch version-16 && cd frappe-bench`
3. Copy the newest backup set from the PC to the new server, for example:
   ```powershell
   scp -r "$env:USERPROFILE\Documents\MembyBackups\zedir.memby.et\2026-11-22_1000" user@new-server:~/
   ```
4. On the new server:
   ```bash
   DB_ROOT_PASSWORD='<mariadb root pw>' bash ~/2026-11-22_1000/restore.sh ~/2026-11-22_1000
   ```
   (For a Google Drive setup, use `bash restore.sh --list`, then `bash restore.sh` with rclone configured.)

   The script checks the checksums and fetches `memby` at the exact prod commit. It creates the site, restores
   the DB and files, puts back the `encryption_key` and migrates. It leaves the **scheduler disabled** so the
   copy doesn't send SMS reminders or apply penalties alongside prod. It refuses to touch a site that already
   exists unless you pass `FORCE=1`.
5. To make it the live prod:
   ```bash
   bench --site zedir.memby.et enable-scheduler
   sudo bench setup production <user>
   ```
   Then point the `zedir.memby.et` A record in Cloudflare at the new IP and set up SSL (Cloudflare origin cert
   or `sudo bench setup lets-encrypt zedir.memby.et`). The old `ssl_certificate` paths in site_config may
   need updating.

### Do a trial restore

A backup that has never been restored is not proven. Restore one set on a throwaway VM (steps above), log in and
check members, payments and an attachment. Repeat every few months.
