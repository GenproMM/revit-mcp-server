# RevitMCP pilot: read-only diagnostic for "the extension holds no shared secret".
# Prints paths, times, True/False and status fields. Never prints the secret.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File "\\srv-dfs\BIM\06_RevitMCP_pilot\diag-secret.ps1"

$ini = "$env:APPDATA\pyRevit\pyRevit_config.ini"
$line = (Select-String -Path $ini -Pattern '^\s{0,}userextensions\s{0,}=' -Encoding UTF8).Line
$paths = foreach ($x in (($line -replace '^\s{0,}userextensions\s{0,}=\s{0,}', '') | ConvertFrom-Json)) { [string]$x }
$mine = @($paths | Where-Object { $_ -match '\\06_RevitMCP' })
'our paths: ' + $mine.Count
'local extension copy: ' + (Test-Path "$env:APPDATA\pyRevit\Extensions\revit-mcp-server.extension")
foreach ($r in @(Get-Process Revit -ErrorAction SilentlyContinue)) { 'Revit started: ' + $r.StartTime.ToString('s') }
$app = "$env:LOCALAPPDATA\RevitMCP\current\app\_bridge_secret"
$appHash = $null
try { $appHash = (Get-FileHash -LiteralPath $app -Algorithm SHA256 -ErrorAction Stop).Hash; 'payload secret: readable' }
catch { 'payload secret: NOT readable (' + $_.Exception.GetType().Name + ')' }
foreach ($p in $mine) {
  $s = [IO.Path]::GetFullPath([IO.Path]::Combine($p, 'revit-mcp-server.extension\revit_mcp\_bridge_secret'))
  'extension secret: ' + $s
  if (-not (Test-Path -LiteralPath $s)) { '  MISSING'; continue }
  $f = Get-Item -LiteralPath $s
  '  created: ' + $f.CreationTime.ToString('s') + ', modified: ' + $f.LastWriteTime.ToString('s')
  try { $h = (Get-FileHash -LiteralPath $s -Algorithm SHA256 -ErrorAction Stop).Hash; '  readable, same as payload: ' + ($h -eq $appHash) }
  catch { '  NOT readable (' + $_.Exception.GetType().Name + ')' }
}
$pyrevit = (Get-Command pyrevit -ErrorAction SilentlyContinue).Source
if (-not $pyrevit) { $pyrevit = @("$env:APPDATA\pyRevit-Master\bin\pyrevit.exe",
    "$env:ProgramFiles\pyRevit-Master\bin\pyrevit.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1 }
'pyrevit: ' + $pyrevit
if ($pyrevit) { $envl = @((& $pyrevit env) -match 'revit-mcp|Engine:'); if ($envl.Count) { $envl } else { 'pyrevit env: no revit-mcp or Engine lines' } }
try {
  $st = Invoke-RestMethod 'http://127.0.0.1:48884/genpro_revit_mcp/status/' -TimeoutSec 15
  'status: health=' + $st.health + ', secret.configured=' + $st.secret.configured +
    ', integrity=' + $st.integrity.state + '/' + $st.integrity.reason
  if ($st.failed_domains) { 'failed_domains: ' + ($st.failed_domains | ConvertTo-Json -Compress) }
} catch { 'status: no answer (' + $_.Exception.GetType().Name + ')' }
'done'
