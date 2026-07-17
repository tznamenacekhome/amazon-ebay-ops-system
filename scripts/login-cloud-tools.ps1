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

function Test-AwsCliLogin {
  param([string]$Profile)

  $identity = aws sts get-caller-identity --profile $Profile --output json 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $identity) {
    return $null
  }
  return $identity | ConvertFrom-Json
}

function Test-SupabaseCliLogin {
  $output = npx.cmd --yes supabase@latest projects list 2>$null
  if ($LASTEXITCODE -ne 0) {
    return $false
  }
  return $true
}

if (-not $SkipAws) {
  Write-Host "== AWS ==" -ForegroundColor Cyan
  $identity = Test-AwsCliLogin -Profile $AwsProfile
  if ($identity) {
    Write-Host "AWS login already valid." -ForegroundColor Green
    Write-Host "Profile: $AwsProfile"
    Write-Host "Account: $($identity.Account)"
    Write-Host "ARN:     $($identity.Arn)"
    Write-Host ""
    Write-Host "Use this profile for deploy/status commands:"
    Write-Host "  `$env:AWS_PROFILE = `"$AwsProfile`""
  } else {
    $awsArgs = @{ Profile = $AwsProfile }
    if ($AwsRootFallback) {
      $awsArgs.RootFallback = $true
    }
    & (Join-Path $PSScriptRoot "aws-login.ps1") @awsArgs
    if ($LASTEXITCODE -ne 0) {
      throw "AWS login failed."
    }
  }
}

if (-not $SkipSupabase) {
  Write-Host ""
  Write-Host "== Supabase CLI ==" -ForegroundColor Cyan

  $supabaseLoggedIn = Test-SupabaseCliLogin
  if ($supabaseLoggedIn) {
    Write-Host "Supabase login already valid." -ForegroundColor Green
  } else {
    if ($SupabaseAccessToken) {
      Invoke-SupabaseCli -Arguments @("login", "--token", $SupabaseAccessToken)
    } else {
      Invoke-SupabaseCli -Arguments @("login")
    }

    Write-Host ""
    Write-Host "Supabase login verified." -ForegroundColor Green
  }

  Write-Host ""
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
