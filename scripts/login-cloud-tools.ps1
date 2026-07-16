param(
  [string]$AwsProfile = "mbop-admin",
  [switch]$AwsRootFallback,
  [switch]$SkipAws,
  [switch]$SkipSupabase,
  [string]$SupabaseAccessToken
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

function Invoke-SupabaseCli {
  param([string[]]$Arguments)

  & npx.cmd --yes supabase@latest @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Supabase CLI command failed: supabase $($Arguments -join ' ')"
  }
}

if (-not $SkipAws) {
  Write-Host "== AWS ==" -ForegroundColor Cyan
  $awsArgs = @{ Profile = $AwsProfile }
  if ($AwsRootFallback) {
    $awsArgs.RootFallback = $true
  }
  & (Join-Path $PSScriptRoot "aws-login.ps1") @awsArgs
  if ($LASTEXITCODE -ne 0) {
    throw "AWS login failed."
  }
}

if (-not $SkipSupabase) {
  Write-Host ""
  Write-Host "== Supabase CLI ==" -ForegroundColor Cyan

  if ($SupabaseAccessToken) {
    Invoke-SupabaseCli -Arguments @("login", "--token", $SupabaseAccessToken)
  } else {
    Invoke-SupabaseCli -Arguments @("login")
  }

  Write-Host ""
  Write-Host "Supabase login verified." -ForegroundColor Green
  Invoke-SupabaseCli -Arguments @("projects", "list")

  $projectRefPath = Join-Path $repoRoot "supabase\.temp\project-ref"
  if (Test-Path $projectRefPath) {
    $projectRef = (Get-Content $projectRefPath -Raw).Trim()
    if ($projectRef) {
      Write-Host ""
      Write-Host "Linked Supabase project: $projectRef" -ForegroundColor Green
    }
  }
}

Write-Host ""
Write-Host "Cloud tool login complete." -ForegroundColor Green
