# RevitMCP: per-user logon preparation for the 2.0 fleet rollout (Group Policy).
#
# Runs as the logged-on user from a GPO logon script:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File <path>\gpo-prep.ps1
#
# Only on a machine where RevitMCP is installed, and only while Revit is closed:
#   1. pyRevit attached with IronPython 2.7 (IPY2712, IPY2712PR) -> pyrevit attach <clone> 342 --attached.
#      Under IPY2712 the extension loads but never reads the shared secret, so every
#      model change is refused with 401 server_not_configured.
#   2. [routes] without host -> add host = "127.0.0.1" (and port = 48884 when absent),
#      after a timestamped backup. An existing host is never changed; a missing
#      [routes] section is only logged.
#   3. Runs <ShareRoot>\install\update.cmd, but only when OUR extension is registered
#      from that same share. A pilot user is never switched to the main payload.
#
# Everything is logged to %LOCALAPPDATA%\RevitMCP\gpo-prep.log. The script never
# throws: a failed step is logged and the next one still runs. -DryRun logs the
# decisions without changing anything. ASCII only: Windows PowerShell 5.1 reads a
# BOM-less script as ANSI.

param(
    [string]$ShareRoot = '\\srv-dfs\BIM\06_RevitMCP',
    [string]$PyRevit = '',
    [switch]$DryRun,
    [switch]$SkipUpdate
)

$dest = Join-Path $env:LOCALAPPDATA 'RevitMCP'
$logFile = Join-Path $dest 'gpo-prep.log'

function Write-Log([string]$message) {
    try {
        if (-not (Test-Path -LiteralPath $dest)) { return }
        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Add-Content -LiteralPath $logFile -Value ('[' + $stamp + '] ' + $message) -Encoding UTF8
    } catch {}
}

function Get-OurPaths([string]$ini) {
    $line = (Select-String -LiteralPath $ini -Pattern '^\s{0,}userextensions\s{0,}=' -Encoding UTF8 |
        Select-Object -First 1).Line
    if (-not $line) { return @() }
    $json = $line -replace '^\s{0,}userextensions\s{0,}=\s{0,}', ''
    $paths = foreach ($x in ($json | ConvertFrom-Json)) { [string]$x }
    return @($paths | Where-Object { $_ -match '\\06_RevitMCP' })
}

function Repair-Engine([string]$exe) {
    $lines = @(@(& $exe env) -match 'Engine:')
    if ($lines.Count -eq 0) { Write-Log 'engine: pyrevit env reported no attachments; nothing changed'; return }
    $old = @($lines | Where-Object { $_ -match 'Engine:\s{0,}IPY27' })
    if ($old.Count -eq 0) { Write-Log ('engine: ok (' + ($lines -join ' / ').Trim() + ')'); return }
    $clones = @($old | ForEach-Object { ($_ -split '\|')[0].Trim() } | Sort-Object -Unique)
    foreach ($clone in $clones) {
        if ($DryRun) { Write-Log ('engine: DRY RUN would attach ' + $clone + ' 342 --attached'); continue }
        & $exe attach $clone 342 --attached | Out-Null
        Write-Log ('engine: attach ' + $clone + ' 342 --attached, exit ' + $LASTEXITCODE)
    }
    if (-not $DryRun) {
        $after = @(@(& $exe env) -match 'Engine:\s{0,}IPY27')
        if ($after.Count) { Write-Log 'engine: STILL IPY2712 after attach; needs the maintainer' }
        else { Write-Log 'engine: now IPY342' }
    }
}

function Repair-RoutesHost([string]$ini) {
    $bytes = [IO.File]::ReadAllBytes($ini)
    $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    $text = (New-Object Text.UTF8Encoding($false)).GetString($bytes)
    if ($bom) { $text = $text.Substring(1) }
    $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $m = [regex]::Match($text, '(?ms)^\[routes\][ \t]{0,}\r?\n(.{0,}?)(?=^\[|\z)')
    if (-not $m.Success) { Write-Log 'routes: no [routes] section; not created (Routes is off on this machine)'; return }
    $body = $m.Groups[1].Value
    if ($body -match '(?im)^[ \t]{0,}host[ \t]{0,}=') { Write-Log 'routes: host already set; kept'; return }
    $add = 'host = "127.0.0.1"' + $nl
    if ($body -notmatch '(?im)^[ \t]{0,}port[ \t]{0,}=') { $add += 'port = 48884' + $nl }
    if ($DryRun) { Write-Log ('routes: DRY RUN would add ' + $add.Trim().Replace($nl, '; ')); return }
    $backup = Join-Path $dest ('pyRevit_config.before-gpo-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.ini')
    [IO.File]::WriteAllBytes($backup, $bytes)
    [IO.File]::WriteAllText($ini, $text.Insert($m.Groups[1].Index, $add), (New-Object Text.UTF8Encoding($bom)))
    Write-Log ('routes: added ' + $add.Trim().Replace($nl, '; ') + '; backup ' + $backup)
}

function Invoke-Update([string[]]$ourPaths) {
    $prefix = $ShareRoot.TrimEnd('\') + '\'
    $fromShare = @($ourPaths | Where-Object { $_.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) })
    if ($fromShare.Count -eq 0) {
        Write-Log ('update: skipped; our extension is not registered from ' + $ShareRoot + ' (' + ($ourPaths -join '; ') + ')')
        return
    }
    $update = Join-Path $ShareRoot 'install\update.cmd'
    if (-not (Test-Path -LiteralPath $update)) { Write-Log ('update: skipped; ' + $update + ' not reachable'); return }
    if ($DryRun) { Write-Log ('update: DRY RUN would run ' + $update); return }
    cmd /c ('"' + $update + '" < nul') | Out-Null
    Write-Log ('update: ran ' + $update + ', exit ' + $LASTEXITCODE)
}

try {
    $ini = Join-Path $env:APPDATA 'pyRevit\pyRevit_config.ini'
    $installed = Test-Path -LiteralPath (Join-Path $dest 'current-version.txt')
    if (-not $installed) { return }  # RevitMCP is not installed for this user: no log, no change
    Write-Log ('start: user ' + $env:USERNAME + ', share ' + $ShareRoot + $(if ($DryRun) { ', DRY RUN' } else { '' }))
    if (@(Get-Process Revit -ErrorAction SilentlyContinue).Count) { Write-Log 'stop: Revit is running; nothing changed'; return }
    if (-not (Test-Path -LiteralPath $ini)) { Write-Log 'stop: pyRevit_config.ini not found'; return }

    $exe = $PyRevit
    if (-not $exe) {
        $exe = @("$env:APPDATA\pyRevit-Master\bin\pyrevit.exe", "$env:ProgramFiles\pyRevit-Master\bin\pyrevit.exe") |
            Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if ($exe) {
        try { Repair-Engine $exe } catch { Write-Log ('engine: ERROR ' + $_.Exception.Message) }
    } else { Write-Log 'engine: pyrevit.exe not found; skipped' }

    try { Repair-RoutesHost $ini } catch { Write-Log ('routes: ERROR ' + $_.Exception.Message) }

    if ($SkipUpdate) { Write-Log 'update: skipped by -SkipUpdate' }
    else {
        try { Invoke-Update (Get-OurPaths $ini) } catch { Write-Log ('update: ERROR ' + $_.Exception.Message) }
    }
    Write-Log 'done'
} catch {
    Write-Log ('ERROR ' + $_.Exception.Message)
}
