#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot Windows apply for quality-upgrade (Flux + hooks + dark wealth topic lock).

.DESCRIPTION
  Cloud cannot touch your local .env / Docker. Run this on the Windows machine that
  hosts C:\Projects\sosyal-medya-otomasyon (or any clone).

  Steps:
    1) Ensure repo present (clone if missing)
    2) Upsert .env keys (VISUAL_ENGINE, ALLOW_STOCK_FALLBACK, TOPICS_PATH)
    3) git apply store patch if upgrade markers missing
    4) docker compose build + recreate video-worker
    5) Health check, clear pending/jobs.db, POST /generate (Rolex topic override)
    6) Print curl equivalents

.PARAMETER RepoRoot
  Local clone path. Default: C:\Projects\sosyal-medya-otomasyon

.PARAMETER PatchPath
  Path to quality-upgrade-flux-hooks.patch (docs or internal copy in agent store).

.PARAMETER SkipGenerate
  Stop after recreate + health; do not POST /generate.

.PARAMETER SkipDocker
  Only patch + .env; skip compose/build (dry apply).
#>
[CmdletBinding()]
param(
  [string]$RepoRoot = "C:\Projects\sosyal-medya-otomasyon",
  [string]$PatchPath = "",
  [string]$AgentStore = "",
  [string]$RemoteUrl = "https://github.com/kadir3106/sosyal-medya-otomasyon.git",
  [string]$WorkerUrl = "http://127.0.0.1:8000",
  [switch]$SkipGenerate,
  [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"
$RolexTopic = "The Rolex Foundation Secret: How Rolex is owned 100% by a private Swiss trust with zero public shareholders"

function Write-Step([string]$msg) {
  Write-Host ""
  Write-Host "=== $msg ===" -ForegroundColor Cyan
}

function Set-DotEnvKey {
  param(
    [Parameter(Mandatory)][string]$EnvFile,
    [Parameter(Mandatory)][string]$Key,
    [Parameter(Mandatory)][string]$Value
  )
  $line = "$Key=$Value"
  if (-not (Test-Path -LiteralPath $EnvFile)) {
    @(
      "# Created by apply-quality-upgrade-local.ps1 — fill remaining secrets from .env.example"
      $line
    ) | Set-Content -LiteralPath $EnvFile -Encoding UTF8
    Write-Host "Created $EnvFile with $Key"
    return
  }
  $raw = Get-Content -LiteralPath $EnvFile -Raw
  if ($null -eq $raw) { $raw = "" }
  $pattern = "(?m)^\s*" + [regex]::Escape($Key) + "\s*=.*$"
  if ([regex]::IsMatch($raw, $pattern)) {
    $raw = [regex]::Replace($raw, $pattern, $line)
    Write-Host "Updated $Key in $EnvFile"
  } else {
    if ($raw.Length -gt 0 -and -not $raw.EndsWith("`n")) { $raw += "`r`n" }
    $raw += "$line`r`n"
    Write-Host "Appended $Key to $EnvFile"
  }
  Set-Content -LiteralPath $EnvFile -Value $raw -Encoding UTF8 -NoNewline
}

function Test-UpgradeApplied {
  param([string]$Root)
  $cfg = Join-Path $Root "video-worker\app\config.py"
  $ex = Join-Path $Root ".env.example"
  if (-not (Test-Path -LiteralPath $cfg)) { return $false }
  $c = Get-Content -LiteralPath $cfg -Raw
  $e = if (Test-Path -LiteralPath $ex) { Get-Content -LiteralPath $ex -Raw } else { "" }
  return (
    $c -match 'VISUAL_ENGINE\s*=\s*os\.environ\.get\("VISUAL_ENGINE",\s*"flux_kenburns"\)' -and
    $c -match 'ALLOW_STOCK_FALLBACK' -and
    $e -match 'VISUAL_ENGINE=flux_kenburns' -and
    $e -match 'ALLOW_STOCK_FALLBACK=false' -and
    $e -match 'TOPICS_PATH=/app/data/topics_dark_wealth\.json'
  )
}

function Resolve-PatchPath {
  param([string]$Explicit, [string]$Store)
  if ($Explicit -and (Test-Path -LiteralPath $Explicit)) { return (Resolve-Path $Explicit).Path }
  $candidates = @()
  if ($Store) {
    $candidates += @(
      (Join-Path $Store "docs\quality-upgrade-flux-hooks.patch"),
      (Join-Path $Store "internal\quality-upgrade-flux-hooks.patch")
    )
  }
  $candidates += @(
    ".\quality-upgrade-flux-hooks.patch",
    (Join-Path $PSScriptRoot "quality-upgrade-flux-hooks.patch"),
    (Join-Path $PSScriptRoot "..\internal\quality-upgrade-flux-hooks.patch")
  )
  foreach ($c in $candidates) {
    if ($c -and (Test-Path -LiteralPath $c)) { return (Resolve-Path $c).Path }
  }
  return $null
}

# --- 0) Paths ---
Write-Step "0) Resolve paths"
if (-not $AgentStore) {
  # Common Cursor agent-store mount / copy location; override with -AgentStore if different.
  $guess = "C:\Users\$env:USERNAME\.cursor\stores\bc-c7998f8c-7086-4e89-878b-e7acec78c791"
  if (Test-Path -LiteralPath $guess) { $AgentStore = $guess }
}
$resolvedPatch = Resolve-PatchPath -Explicit $PatchPath -Store $AgentStore
Write-Host "RepoRoot   : $RepoRoot"
Write-Host "PatchPath  : $(if ($resolvedPatch) { $resolvedPatch } else { '(none — will skip apply if already upgraded)' })"
Write-Host "WorkerUrl  : $WorkerUrl"

# --- 1) Clone / enter repo ---
Write-Step "1) Ensure repository"
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot ".git"))) {
  $parent = Split-Path -Parent $RepoRoot
  if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
  }
  Write-Host "Cloning $RemoteUrl -> $RepoRoot"
  git clone $RemoteUrl $RepoRoot
  if ($LASTEXITCODE -ne 0) { throw "git clone failed (exit $LASTEXITCODE)" }
} else {
  Write-Host "Repo already present."
}
Set-Location -LiteralPath $RepoRoot

# Prefer remote upgrade branch if it exists; otherwise stay on current and apply patch.
$remoteBranch = "cursor/quality-upgrade-flux-hooks-f0dd"
git fetch origin 2>$null
$hasRemote = $false
git rev-parse --verify "origin/$remoteBranch" 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { $hasRemote = $true }
if ($hasRemote) {
  Write-Host "Checking out origin/$remoteBranch"
  git checkout -B $remoteBranch "origin/$remoteBranch"
  if ($LASTEXITCODE -ne 0) { throw "git checkout $remoteBranch failed" }
} else {
  Write-Host "Remote branch $remoteBranch not found — will use patch apply on current HEAD."
  $localBranch = "cursor/quality-upgrade-flux-hooks-local"
  git rev-parse --verify $localBranch 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) {
    git checkout -b $localBranch
  } else {
    git checkout $localBranch
  }
}

# --- 2) .env upsert ---
Write-Step "2) Upsert .env quality keys"
$envFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path -LiteralPath $envFile) -and (Test-Path -LiteralPath (Join-Path $RepoRoot ".env.example"))) {
  Copy-Item -LiteralPath (Join-Path $RepoRoot ".env.example") -Destination $envFile
  Write-Host "Copied .env.example -> .env (fill secrets if empty)"
}
Set-DotEnvKey -EnvFile $envFile -Key "VISUAL_ENGINE" -Value "flux_kenburns"
Set-DotEnvKey -EnvFile $envFile -Key "ALLOW_STOCK_FALLBACK" -Value "false"
Set-DotEnvKey -EnvFile $envFile -Key "TOPICS_PATH" -Value "/app/data/topics_dark_wealth.json"
Write-Host "Also ensure FAL_KEY / OPENROUTER_MODEL / OPENROUTER_API_KEY (or LLM_API_URL) are set for live Flux."

# --- 3) git apply if needed ---
Write-Step "3) Apply patch if upgrade not present"
if (Test-UpgradeApplied -Root $RepoRoot) {
  Write-Host "Upgrade markers already present — skipping git apply."
} else {
  if (-not $resolvedPatch) {
    throw "Upgrade not present and no patch file found. Pass -PatchPath to quality-upgrade-flux-hooks.patch"
  }
  $destPatch = Join-Path $RepoRoot "quality-upgrade-flux-hooks.patch"
  Copy-Item -LiteralPath $resolvedPatch -Destination $destPatch -Force
  Write-Host "Copied patch -> $destPatch"
  git apply --check $destPatch
  if ($LASTEXITCODE -ne 0) {
    Write-Host @"

PATCH CONFLICT — resolve manually:
  1) git apply --reject --whitespace=nowarn quality-upgrade-flux-hooks.patch
  2) Inspect *.rej next to failed files; merge by hand.
  3) Prefer keeping: VISUAL_ENGINE=flux_kenburns, ALLOW_STOCK_FALLBACK=false,
     TOPICS_PATH=/app/data/topics_dark_wealth.json, concrete_nouns → build_flux_prompt.
  4) git add -A && git commit -m "Quality upgrade: Flux default, hook A/B, dark wealth topic lock"
  5) Re-run this script with markers present (it will skip apply).

"@ -ForegroundColor Yellow
    throw "git apply --check failed (exit $LASTEXITCODE). See conflict hints above."
  }
  git apply $destPatch
  if ($LASTEXITCODE -ne 0) { throw "git apply failed (exit $LASTEXITCODE)" }
  git add -A
  git status -sb
  $pending = git status --porcelain
  if ($pending) {
    git commit -m "Quality upgrade: Flux default, hook A/B, dark wealth topic lock"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
  }
  if (-not (Test-UpgradeApplied -Root $RepoRoot)) {
    throw "Patch applied but verification markers still missing — inspect tree."
  }
  Write-Host "Patch applied and verified."
}

# Quick code greps (evidence)
Write-Step "3b) Verify markers"
$checks = @(
  @{ File = ".env.example"; Pattern = "VISUAL_ENGINE=flux_kenburns" },
  @{ File = ".env.example"; Pattern = "ALLOW_STOCK_FALLBACK=false" },
  @{ File = ".env.example"; Pattern = "TOPICS_PATH=/app/data/topics_dark_wealth.json" },
  @{ File = "video-worker\app\config.py"; Pattern = '"flux_kenburns"' },
  @{ File = "video-worker\app\ai_visuals.py"; Pattern = "concrete_nouns" },
  @{ File = "video-worker\data\topics_dark_wealth.json"; Pattern = "Rolex" }
)
foreach ($c in $checks) {
  $p = Join-Path $RepoRoot $c.File
  if (-not (Test-Path -LiteralPath $p)) { throw "Missing file: $($c.File)" }
  $hit = Select-String -Path $p -Pattern $c.Pattern -SimpleMatch -Quiet
  if (-not $hit) { throw "Marker missing in $($c.File): $($c.Pattern)" }
  Write-Host "OK  $($c.File) :: $($c.Pattern)"
}

if ($SkipDocker) {
  Write-Host "SkipDocker set — done after patch/.env."
  exit 0
}

# --- 4) Docker rebuild ---
Write-Step "4) docker compose build + recreate video-worker"
docker compose build video-worker
if ($LASTEXITCODE -ne 0) { throw "docker compose build failed" }
docker compose up -d --force-recreate --no-deps video-worker
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

# --- 5) Health ---
Write-Step "5) Health check"
$healthy = $false
for ($i = 1; $i -le 30; $i++) {
  try {
    $h = Invoke-RestMethod -Method GET -Uri "$WorkerUrl/health" -TimeoutSec 3
    if ($h.status -eq "ok") {
      Write-Host "Health OK (attempt $i): $($h | ConvertTo-Json -Compress)"
      $healthy = $true
      break
    }
  } catch {
    Write-Host "Waiting for health... ($i/30)"
    Start-Sleep -Seconds 2
  }
}
if (-not $healthy) { throw "video-worker /health did not become ok" }

# Env inside container
docker compose exec -T video-worker python -c "import os; print(os.environ.get('VISUAL_ENGINE'), os.environ.get('ALLOW_STOCK_FALLBACK'), os.environ.get('TOPICS_PATH'))"

# --- 6) Clear pending / jobs.db ---
Write-Step "6) Clear pending.json + jobs.db"
$clearPy = @'
from pathlib import Path
media = Path("/data/media")
media.mkdir(parents=True, exist_ok=True)
for name in ("pending.json", "jobs.db"):
    p = media / name
    if p.exists():
        p.unlink()
        print(f"removed {p}")
    else:
        print(f"absent  {p}")
'@
$clearPy | docker compose exec -T video-worker python -
if ($LASTEXITCODE -ne 0) { throw "Failed clearing pending/jobs.db" }

if ($SkipGenerate) {
  Write-Host "SkipGenerate set — not POSTing /generate."
} else {
  # --- 7) Rolex generate ---
  Write-Step "7) POST /generate (Rolex topic override)"
  $bodyObj = @{ topic = $RolexTopic }
  $body = $bodyObj | ConvertTo-Json -Compress
  try {
    $resp = Invoke-RestMethod -Method POST -Uri "$WorkerUrl/generate" -ContentType "application/json" -Body $body -TimeoutSec 600
    Write-Host ($resp | ConvertTo-Json -Depth 8)
  } catch {
    Write-Host "POST /generate failed: $($_.Exception.Message)" -ForegroundColor Yellow
    if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message }
    Write-Host "If 409: pending still blocking — re-run step 6 or approve/reject via Telegram."
    throw
  }
}

# --- 8) Print curl commands ---
Write-Step "8) Equivalent curl commands (Git Bash / WSL)"
$rolexEscaped = $RolexTopic.Replace('"', '\"')
Write-Host @"

# Health
curl -sS $WorkerUrl/health

# Clear gate (inside container)
docker compose exec -T video-worker python -c "from pathlib import Path; p=Path('/data/media'); (p/'pending.json').unlink(missing_ok=True); (p/'jobs.db').unlink(missing_ok=True)"

# Rolex generate (topic override supported by GenerateRequest.topic)
curl -sS -X POST $WorkerUrl/generate -H "Content-Type: application/json" -d "{\"topic\":\"$rolexEscaped\"}"

# Default generate (pool pick)
curl -sS -X POST $WorkerUrl/generate -H "Content-Type: application/json" -d "{}"

"@

Write-Host "DONE. Approve/reject via Telegram when the job reaches awaiting_approval." -ForegroundColor Green
