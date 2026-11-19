<#
.SYNOPSIS
  Pull a fresh backup of a Memby/Frappe site from the prod server to this Windows PC over SSH.

.DESCRIPTION
  1. SSHes to the server and runs backup.sh as the bench user with the cloud upload switched off
     (RCLONE_REMOTE=none). It makes a full set: DB, public/private files, site_config, manifest,
     restore.sh and SHA256SUMS.
  2. Copies that set here with scp and checks every file against SHA256SUMS.
  3. Keeps the newest -Keep sets and deletes older ones.

  Needs key-based (password-less) SSH to -Server. Meant to run weekly from Task Scheduler.
  The log is written to <Dest>\pull-backup.log.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File pull-backup.ps1 -Server root@203.0.113.10
#>
param(
	[Parameter(Mandatory = $true)][string]$Server,        # user@host; the user must be root or the bench user
	[string]$Site = "zedir.memby.et",
	[string]$BenchUser = "haile",
	[string]$BenchDir = "/home/haile/frappe-bench",
	[string]$Dest = (Join-Path $env:USERPROFILE "Documents\MembyBackups"),
	[int]$Keep = 12
)

$ErrorActionPreference = "Stop"
$siteDir = Join-Path $Dest $Site
New-Item -ItemType Directory -Force -Path $siteDir | Out-Null
$logFile = Join-Path $Dest "pull-backup.log"

function Write-Log([string]$msg) {
	$line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
	Add-Content -Path $logFile -Value $line -Encoding UTF8
	Write-Output $line
}

$sshOpts = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=30", "-o", "ServerAliveInterval=30")

try {
	Write-Log "=== pulling $Site from $Server ==="

	# 1. Make the backup on the server (as the bench user) and get its folder path.
	$script = "$BenchDir/apps/memby/deploy/backup/backup.sh"
	$run = "env SITE='$Site' RCLONE_REMOTE=none /bin/bash $script && cat $BenchDir/offsite-backups/$Site/LATEST"
	# No double quotes inside: Windows PowerShell 5.1 mangles them when calling ssh.exe.
	$remoteCmd = 'if [ $(id -un) = ' + $BenchUser + ' ]; then ' + $run + '; else sudo -u ' + $BenchUser + ' -H ' + $run + '; fi'
	$remotePath = (& ssh @sshOpts $Server $remoteCmd | Select-Object -Last 1)
	if ($LASTEXITCODE -ne 0 -or -not $remotePath) {
		throw "backup on server failed (exit $LASTEXITCODE); see $BenchDir/logs/offsite-backup.log on the server"
	}
	$remotePath = $remotePath.Trim()
	$setName = Split-Path $remotePath -Leaf
	Write-Log "server made $remotePath"

	# 2. Copy it here.
	$target = Join-Path $siteDir $setName
	if (Test-Path $target) { Remove-Item -Recurse -Force $target }
	& scp @sshOpts -q -r "${Server}:$remotePath" "$siteDir\"
	if ($LASTEXITCODE -ne 0) { throw "scp failed (exit $LASTEXITCODE)" }

	# 3. Check the checksums.
	$sums = Join-Path $target "SHA256SUMS"
	if (-not (Test-Path $sums)) { throw "SHA256SUMS missing in $target" }
	$count = 0
	foreach ($line in Get-Content $sums) {
		if ($line -notmatch '^([0-9a-f]{64})\s+\*?(.+)$') { continue }
		$file = Join-Path $target $Matches[2]
		if (-not (Test-Path $file)) { throw "missing $($Matches[2])" }
		$actual = (Get-FileHash -Algorithm SHA256 -Path $file).Hash.ToLower()
		if ($actual -ne $Matches[1]) { throw "checksum mismatch: $($Matches[2])" }
		$count++
	}
	if ($count -lt 6) { throw "only $count files verified, expected at least 6" }
	$size = "{0:N1} MB" -f ((Get-ChildItem $target | Measure-Object Length -Sum).Sum / 1MB)
	Write-Log "copied to $target ($count files, $size), checksums OK"

	# 4. Keep the newest $Keep sets.
	$sets = Get-ChildItem -Directory $siteDir | Sort-Object Name
	if ($sets.Count -gt $Keep) {
		$sets | Select-Object -First ($sets.Count - $Keep) | ForEach-Object {
			Write-Log "removing old set $($_.Name)"
			Remove-Item -Recurse -Force $_.FullName
		}
	}

	Write-Log "=== done ==="
	exit 0
}
catch {
	Write-Log "FAILED: $($_.Exception.Message)"
	exit 1
}
