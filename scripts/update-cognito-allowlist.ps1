param(
  [Parameter(Mandatory = $true)]
  [string[]]$AllowedEmail,
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$UserPoolId = "us-west-2_IBxxtQ9xL",
  [string]$FunctionName = "mbop-cognito-pre-signup-allowlist",
  [string]$RoleName = "mbop-cognito-pre-signup-allowlist-role"
)

$ErrorActionPreference = "Stop"

function ConvertTo-JsonFile($Value, [string]$Path) {
  $Value | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $Path -Encoding ascii
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$sourceFile = Join-Path $repoRoot "aws\cognito_allowlist\pre_signup.py"
if (-not (Test-Path -LiteralPath $sourceFile)) {
  throw "Missing Lambda source file: $sourceFile"
}

$normalizedEmails = $AllowedEmail |
  ForEach-Object { $_.Trim().ToLowerInvariant() } |
  Where-Object { $_ } |
  Sort-Object -Unique

if (-not $normalizedEmails) {
  throw "At least one allowed email is required."
}

$allowedEmailValue = ($normalizedEmails -join ",")
$lambdaEnvironment = @{
  Variables = @{
    MBOP_ALLOWED_EMAILS = $allowedEmailValue
  }
}
$lambdaEnvironmentFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-cognito-allowlist-env.json"
ConvertTo-JsonFile $lambdaEnvironment $lambdaEnvironmentFile

Write-Host "Updating MBOP Cognito email allowlist" -ForegroundColor Cyan
Write-Host "User pool: $UserPoolId"
Write-Host "Lambda:    $FunctionName"
Write-Host "Emails:"
$normalizedEmails | ForEach-Object { Write-Host "  $_" }
Write-Host ""

$identity = aws sts get-caller-identity --profile $Profile --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) {
  throw "AWS identity check failed."
}
$accountId = $identity.Account
$userPoolArn = "arn:aws:cognito-idp:${Region}:${accountId}:userpool/${UserPoolId}"

$role = $null
try {
  $roleJson = aws iam get-role --profile $Profile --role-name $RoleName --output json 2>$null
  $roleExitCode = $LASTEXITCODE
} catch {
  $roleJson = $null
  $roleExitCode = 1
}
if ($roleExitCode -eq 0) {
  $role = $roleJson | ConvertFrom-Json
} else {
  $trustPolicy = @{
    Version = "2012-10-17"
    Statement = @(
      @{
        Effect = "Allow"
        Principal = @{ Service = "lambda.amazonaws.com" }
        Action = "sts:AssumeRole"
      }
    )
  }
  $trustFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-cognito-allowlist-trust.json"
  ConvertTo-JsonFile $trustPolicy $trustFile

  Write-Host "Creating IAM role $RoleName" -ForegroundColor Cyan
  $role = aws iam create-role `
    --profile $Profile `
    --role-name $RoleName `
    --assume-role-policy-document "file://$trustFile" `
    --output json | ConvertFrom-Json
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create IAM role $RoleName."
  }

  aws iam attach-role-policy `
    --profile $Profile `
    --role-name $RoleName `
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to attach Lambda basic execution policy to $RoleName."
  }

  Start-Sleep -Seconds 10
}

$roleArn = $role.Role.Arn
$packageRoot = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-cognito-allowlist"
$packageFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-cognito-allowlist.zip"

if (Test-Path -LiteralPath $packageRoot) {
  Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
if (Test-Path -LiteralPath $packageFile) {
  Remove-Item -LiteralPath $packageFile -Force
}

New-Item -ItemType Directory -Path $packageRoot | Out-Null
Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $packageRoot "pre_signup.py")
Compress-Archive -Path (Join-Path $packageRoot "*") -DestinationPath $packageFile -Force

$function = $null
try {
  $functionJson = aws lambda get-function `
    --profile $Profile `
    --region $Region `
    --function-name $FunctionName `
    --output json 2>$null
  $functionExitCode = $LASTEXITCODE
} catch {
  $functionJson = $null
  $functionExitCode = 1
}
if ($functionExitCode -eq 0) {
  $function = $functionJson | ConvertFrom-Json
} else {
  Write-Host "Creating Lambda $FunctionName" -ForegroundColor Cyan
  $function = aws lambda create-function `
    --profile $Profile `
    --region $Region `
    --function-name $FunctionName `
    --runtime python3.12 `
    --role $roleArn `
    --handler pre_signup.lambda_handler `
    --zip-file "fileb://$packageFile" `
    --environment "file://$lambdaEnvironmentFile" `
    --output json | ConvertFrom-Json
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create Lambda $FunctionName."
  }
}

if ($function.Configuration) {
  Write-Host "Updating Lambda code and configuration" -ForegroundColor Cyan
  aws lambda update-function-code `
    --profile $Profile `
    --region $Region `
    --function-name $FunctionName `
    --zip-file "fileb://$packageFile" | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to update Lambda code."
  }

  aws lambda wait function-updated `
    --profile $Profile `
    --region $Region `
    --function-name $FunctionName

  aws lambda update-function-configuration `
    --profile $Profile `
    --region $Region `
    --function-name $FunctionName `
    --runtime python3.12 `
    --handler pre_signup.lambda_handler `
    --role $roleArn `
    --environment "file://$lambdaEnvironmentFile" | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to update Lambda configuration."
  }
}

aws lambda wait function-active `
  --profile $Profile `
  --region $Region `
  --function-name $FunctionName

$functionArn = (aws lambda get-function `
  --profile $Profile `
  --region $Region `
  --function-name $FunctionName `
  --query "Configuration.FunctionArn" `
  --output text).Trim()

try {
  aws lambda add-permission `
    --profile $Profile `
    --region $Region `
    --function-name $FunctionName `
    --statement-id "AllowCognitoPreSignupInvoke" `
    --action "lambda:InvokeFunction" `
    --principal "cognito-idp.amazonaws.com" `
    --source-arn $userPoolArn | Out-Null
} catch {
  if ($_.Exception.Message -notmatch "ResourceConflictException|already exists") {
    throw
  }
}

$pool = aws cognito-idp describe-user-pool `
  --profile $Profile `
  --region $Region `
  --user-pool-id $UserPoolId `
  --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) {
  throw "Failed to describe Cognito user pool $UserPoolId."
}

$lambdaConfig = @{}
if ($pool.UserPool.LambdaConfig) {
  foreach ($property in $pool.UserPool.LambdaConfig.PSObject.Properties) {
    $lambdaConfig[$property.Name] = $property.Value
  }
}
$lambdaConfig.PreSignUp = $functionArn

$lambdaConfigFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-cognito-lambda-config.json"
ConvertTo-JsonFile $lambdaConfig $lambdaConfigFile

Write-Host "Attaching Lambda to Cognito pre-signup trigger" -ForegroundColor Cyan
aws cognito-idp update-user-pool `
  --profile $Profile `
  --region $Region `
  --user-pool-id $UserPoolId `
  --lambda-config "file://$lambdaConfigFile" | Out-Null

Write-Host ""
Write-Host "Allowlist update complete." -ForegroundColor Green
Write-Host "PreSignUp Lambda: $functionArn"
