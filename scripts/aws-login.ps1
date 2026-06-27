param(
  [string]$Profile = "mbop-admin",
  [switch]$RootFallback
)

$ErrorActionPreference = "Stop"

if ($RootFallback) {
  $Profile = "root-console"
  Write-Host "Opening AWS console-login fallback profile '$Profile'. Use this only for break-glass/root account work." -ForegroundColor Yellow
  aws login --profile $Profile
} else {
  Write-Host "Opening AWS SSO login for daily MBOP admin profile '$Profile'." -ForegroundColor Cyan
  aws sso login --profile $Profile
}

$identityJson = aws sts get-caller-identity --profile $Profile --output json
$identity = $identityJson | ConvertFrom-Json

Write-Host ""
Write-Host "AWS login verified." -ForegroundColor Green
Write-Host "Profile: $Profile"
Write-Host "Account: $($identity.Account)"
Write-Host "ARN:     $($identity.Arn)"
Write-Host ""
Write-Host "Use this profile for deploy/status commands:"
Write-Host "  `$env:AWS_PROFILE = `"$Profile`""
