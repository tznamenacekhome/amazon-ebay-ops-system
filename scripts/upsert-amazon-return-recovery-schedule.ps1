param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$ScheduleName = "mbop-amazon-return-recovery-daily",
  [string]$TemplateScheduleName = "mbop-fba-inventory-daily",
  [string]$GroupName = "default",
  [string]$TaskDefinitionArn,
  [string]$ScheduleExpression = "cron(45 15 ? * * *)",
  [string]$Timezone = "America/Los_Angeles"
)

$ErrorActionPreference = "Stop"

if (-not $TaskDefinitionArn) {
  throw "TaskDefinitionArn is required."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

aws sts get-caller-identity --profile $Profile --output json | Out-Null

$template = aws scheduler get-schedule `
  --profile $Profile `
  --region $Region `
  --name $TemplateScheduleName `
  --group-name $GroupName `
  --output json | ConvertFrom-Json

$target = $template.Target
$targetInput = $target.Input | ConvertFrom-Json
$targetInput.TaskDefinition = $TaskDefinitionArn
$targetInput.Overrides.ContainerOverrides[0].Command = @(
  "python",
  "run_all_syncs.py",
  "--group",
  "amazon-return-recovery"
)
$targetInput.Overrides.ContainerOverrides[0].Environment = @(
  @{ Name = "EVENTBRIDGE_SCHEDULE_NAME"; Value = $ScheduleName },
  @{ Name = "SCHEDULER_TRIGGER_SOURCE"; Value = "eventbridge-scheduler" },
  @{ Name = "CONTAINER_CPU"; Value = "512" },
  @{ Name = "CONTAINER_MEMORY"; Value = "1024" }
)
$targetInput.Overrides.Cpu = "512"
$targetInput.Overrides.Memory = "1024"
$target.Input = $targetInput | ConvertTo-Json -Depth 100 -Compress

$targetFile = Join-Path ([System.IO.Path]::GetTempPath()) "$ScheduleName-target.json"
$windowFile = Join-Path ([System.IO.Path]::GetTempPath()) "$ScheduleName-window.json"
$target | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $targetFile -Encoding ascii
$template.FlexibleTimeWindow | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $windowFile -Encoding ascii

$scheduleList = aws scheduler list-schedules `
  --profile $Profile `
  --region $Region `
  --group-name $GroupName `
  --name-prefix $ScheduleName `
  --output json | ConvertFrom-Json
$exists = @($scheduleList.Schedules | Where-Object { $_.Name -eq $ScheduleName }).Count -gt 0

if ($exists) {
  Write-Host "Updating $ScheduleName" -ForegroundColor Cyan
  aws scheduler update-schedule `
    --profile $Profile `
    --region $Region `
    --name $ScheduleName `
    --group-name $GroupName `
    --schedule-expression $ScheduleExpression `
    --schedule-expression-timezone $Timezone `
    --flexible-time-window "file://$windowFile" `
    --target "file://$targetFile" `
    --state ENABLED `
    --description "Daily Amazon Return Recovery customer returns and reimbursement reports." | Out-Null
} else {
  Write-Host "Creating $ScheduleName" -ForegroundColor Cyan
  aws scheduler create-schedule `
    --profile $Profile `
    --region $Region `
    --name $ScheduleName `
    --group-name $GroupName `
    --schedule-expression $ScheduleExpression `
    --schedule-expression-timezone $Timezone `
    --flexible-time-window "file://$windowFile" `
    --target "file://$targetFile" `
    --state ENABLED `
    --description "Daily Amazon Return Recovery customer returns and reimbursement reports." | Out-Null
}

Write-Host "Schedule ready: $ScheduleName $ScheduleExpression $Timezone -> $TaskDefinitionArn" -ForegroundColor Green
