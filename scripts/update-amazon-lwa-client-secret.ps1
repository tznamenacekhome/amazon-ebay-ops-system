param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$SecretId = "/mbop/prod/amazon-spapi/client-secret",
  [string]$EnvFile = ".env.local",
  [switch]$SkipAws,
  [switch]$SkipLocal,
  [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"

function Convert-SecureStringToPlainText($SecureString) {
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
  try {
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  } finally {
    if ($ptr -ne [IntPtr]::Zero) {
      [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
  }
}

function Update-EnvValue($Path, $Name, $Value) {
  $resolvedPath = Join-Path (Get-Location) $Path
  $line = "$Name=$Value"

  if (Test-Path -LiteralPath $resolvedPath) {
    $lines = [System.Collections.Generic.List[string]]::new()
    [System.IO.File]::ReadAllLines($resolvedPath) | ForEach-Object {
      if ($_ -match "^$([Regex]::Escape($Name))=") {
        $lines.Add($line)
      } else {
        $lines.Add($_)
      }
    }
    if (-not ($lines | Where-Object { $_ -match "^$([Regex]::Escape($Name))=" })) {
      $lines.Add($line)
    }
    [System.IO.File]::WriteAllLines($resolvedPath, $lines)
  } else {
    [System.IO.File]::WriteAllLines($resolvedPath, @($line))
  }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

Write-Host "Amazon SP-API LWA Client Secret Update" -ForegroundColor Cyan
Write-Host "Secret value will not be printed."
Write-Host ""

$secureSecret = Read-Host "Enter the new LWA client secret" -AsSecureString
$clientSecret = Convert-SecureStringToPlainText $secureSecret
if (-not $clientSecret) {
  throw "Client secret was empty."
}

try {
  if (-not $SkipLocal) {
    Update-EnvValue -Path $EnvFile -Name "AMAZON_SP_API_CLIENT_SECRET" -Value $clientSecret
    Write-Host "Updated $EnvFile." -ForegroundColor Green
  }

  if (-not $SkipAws) {
    $tempFile = New-TemporaryFile
    try {
      [System.IO.File]::WriteAllText($tempFile.FullName, $clientSecret)
      aws secretsmanager put-secret-value `
        --profile $Profile `
        --region $Region `
        --secret-id $SecretId `
        --secret-string "file://$($tempFile.FullName)" | Out-Null
      Write-Host "Updated AWS Secrets Manager secret $SecretId." -ForegroundColor Green
    } finally {
      if (Test-Path -LiteralPath $tempFile.FullName) {
        Remove-Item -LiteralPath $tempFile.FullName -Force
      }
    }
  }

  if (-not $SkipSmokeTest) {
    Write-Host "Running Amazon auth smoke test..." -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe integrations\amazon_test_connection.py --auth-only
    if ($LASTEXITCODE -ne 0) {
      throw "Amazon auth smoke test failed."
    }
  }

  Write-Host ""
  Write-Host "Amazon LWA client secret update complete." -ForegroundColor Green
} finally {
  $clientSecret = $null
}
