param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$Cluster = "mbop-cluster1",
  [string]$Service = "mbop-web-service"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking AWS identity..." -ForegroundColor Cyan
$identity = aws sts get-caller-identity --profile $Profile --output json | ConvertFrom-Json
Write-Host "Profile: $Profile"
Write-Host "Account: $($identity.Account)"
Write-Host "ARN:     $($identity.Arn)"
Write-Host ""

$serviceResponse = aws ecs describe-services `
  --profile $Profile `
  --region $Region `
  --cluster $Cluster `
  --services $Service `
  --output json | ConvertFrom-Json

$svc = $serviceResponse.services[0]
if (-not $svc) {
  throw "ECS service '$Service' was not found in cluster '$Cluster'."
}

Write-Host "ECS service" -ForegroundColor Cyan
Write-Host "Cluster:        $Cluster"
Write-Host "Service:        $Service"
Write-Host "Task definition:$($svc.taskDefinition)"
Write-Host "Desired:        $($svc.desiredCount)"
Write-Host "Running:        $($svc.runningCount)"
Write-Host "Pending:        $($svc.pendingCount)"
Write-Host ""

Write-Host "Deployments" -ForegroundColor Cyan
$svc.deployments |
  Select-Object status, rolloutState, taskDefinition, desiredCount, runningCount, pendingCount, createdAt, updatedAt |
  Format-Table -AutoSize

$taskDefinition = aws ecs describe-task-definition `
  --profile $Profile `
  --region $Region `
  --task-definition $svc.taskDefinition `
  --output json | ConvertFrom-Json

$container = $taskDefinition.taskDefinition.containerDefinitions |
  Where-Object { $_.name -eq "mbop-web" } |
  Select-Object -First 1

if ($container) {
  Write-Host ""
  Write-Host "Current web image" -ForegroundColor Cyan
  Write-Host $container.image

  $buildVars = $container.environment |
    Where-Object { $_.name -in @("MBOP_BUILD_SHA", "NEXT_PUBLIC_MBOP_BUILD_SHA") }

  if ($buildVars) {
    Write-Host ""
    Write-Host "Build variables" -ForegroundColor Cyan
    $buildVars | Select-Object name, value | Format-Table -AutoSize
  }
}

Write-Host ""
Write-Host "Recent service events" -ForegroundColor Cyan
$svc.events |
  Select-Object -First 8 createdAt, message |
  Format-Table -Wrap
