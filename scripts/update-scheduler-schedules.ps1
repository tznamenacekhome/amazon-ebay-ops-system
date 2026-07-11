param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$TaskDefinitionArn,
  [string]$ScheduleNamePrefix = "mbop-"
)

$ErrorActionPreference = "Stop"

if (-not $TaskDefinitionArn) {
  throw "TaskDefinitionArn is required."
}

function Add-OptionalArgument([string[]]$ArgList, [string]$Name, $Value) {
  if ($null -eq $Value) {
    return $ArgList
  }
  if ($Value -is [string] -and -not $Value.Trim()) {
    return $ArgList
  }
  return $ArgList + @($Name, [string]$Value)
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

aws sts get-caller-identity --profile $Profile --output json | Out-Null

$schedulesJson = aws scheduler list-schedules `
  --profile $Profile `
  --region $Region `
  --output json

$schedules = ($schedulesJson | ConvertFrom-Json).Schedules |
  Where-Object { $_.Name -like "$ScheduleNamePrefix*" } |
  Sort-Object Name

foreach ($scheduleSummary in $schedules) {
  $schedule = aws scheduler get-schedule `
    --profile $Profile `
    --region $Region `
    --name $scheduleSummary.Name `
    --group-name $scheduleSummary.GroupName `
    --output json | ConvertFrom-Json

  $target = $schedule.Target
  $targetInput = $target.Input | ConvertFrom-Json
  $previousTaskDefinition = $targetInput.TaskDefinition
  $targetInput.TaskDefinition = $TaskDefinitionArn
  $target.Input = $targetInput | ConvertTo-Json -Depth 100 -Compress

  $targetFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-schedule-target-$($schedule.Name).json"
  $windowFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-schedule-window-$($schedule.Name).json"
  $target | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $targetFile -Encoding ascii
  $schedule.FlexibleTimeWindow | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $windowFile -Encoding ascii

  [string[]]$cliArgs = @(
    "scheduler",
    "update-schedule",
    "--profile", $Profile,
    "--region", $Region,
    "--name", $schedule.Name,
    "--group-name", $schedule.GroupName,
    "--schedule-expression", $schedule.ScheduleExpression,
    "--flexible-time-window", "file://$windowFile",
    "--target", "file://$targetFile",
    "--state", $schedule.State
  )

  $cliArgs = Add-OptionalArgument $cliArgs "--schedule-expression-timezone" $schedule.ScheduleExpressionTimezone
  $cliArgs = Add-OptionalArgument $cliArgs "--description" $schedule.Description
  $cliArgs = Add-OptionalArgument $cliArgs "--start-date" $schedule.StartDate
  $cliArgs = Add-OptionalArgument $cliArgs "--end-date" $schedule.EndDate
  $cliArgs = Add-OptionalArgument $cliArgs "--kms-key-arn" $schedule.KmsKeyArn
  $cliArgs = Add-OptionalArgument $cliArgs "--action-after-completion" $schedule.ActionAfterCompletion

  Write-Host "Updating $($schedule.Name)" -ForegroundColor Cyan
  Write-Host "  $previousTaskDefinition -> $TaskDefinitionArn"
  & aws @cliArgs | Out-Null
}

Write-Host ""
Write-Host "Updated $($schedules.Count) schedule(s)." -ForegroundColor Green
