param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$ScheduleName = "mbop-sourcing-catalog",
  [string]$GroupName = "default",
  [string]$ScheduleExpression = "cron(10 0 ? * * *)",
  [string]$Timezone = "America/Los_Angeles"
)

$ErrorActionPreference = "Stop"

aws sts get-caller-identity --profile $Profile --output json | Out-Null

$schedule = aws scheduler get-schedule `
  --profile $Profile `
  --region $Region `
  --name $ScheduleName `
  --group-name $GroupName `
  --output json | ConvertFrom-Json

$targetFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-sourcing-catalog-target.json"
$windowFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-sourcing-catalog-window.json"

$schedule.Target | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $targetFile -Encoding ascii
$schedule.FlexibleTimeWindow | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $windowFile -Encoding ascii

aws scheduler update-schedule `
  --profile $Profile `
  --region $Region `
  --name $ScheduleName `
  --group-name $GroupName `
  --schedule-expression $ScheduleExpression `
  --schedule-expression-timezone $Timezone `
  --flexible-time-window "file://$windowFile" `
  --target "file://$targetFile" `
  --state $schedule.State `
  --output json | Out-Null

aws scheduler get-schedule `
  --profile $Profile `
  --region $Region `
  --name $ScheduleName `
  --group-name $GroupName `
  --query "{Name:Name,Expression:ScheduleExpression,Timezone:ScheduleExpressionTimezone,State:State,TargetInput:Target.Input}" `
  --output json
