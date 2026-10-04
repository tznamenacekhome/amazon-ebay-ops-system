param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [Parameter(Mandatory = $true)][string]$TaskDefinitionArn,
  [string]$TemplateSchedule = "mbop-keepa-catalog-priority",
  [string]$ScheduleName = "mbop-wholesale-email-ingestion",
  [ValidateSet("ENABLED", "DISABLED")][string]$State = "ENABLED"
)

$ErrorActionPreference = "Stop"
$template = aws scheduler get-schedule --profile $Profile --region $Region --name $TemplateSchedule --output json | ConvertFrom-Json
$target = $template.Target
$input = $target.Input | ConvertFrom-Json
$input.TaskDefinition = $TaskDefinitionArn
if (-not $input.Overrides) { $input | Add-Member Overrides ([pscustomobject]@{}) }
if (-not $input.Overrides.ContainerOverrides) {
  $input.Overrides | Add-Member ContainerOverrides @([pscustomobject]@{ Name = "mbop-scheduler"; Command = @() })
}
$container = $input.Overrides.ContainerOverrides | Select-Object -First 1
$container.Name = "mbop-scheduler"
$container.Command = @("python", "run_all_syncs.py", "--group", "wholesale-email-ingestion")
$target.Input = $input | ConvertTo-Json -Depth 100 -Compress
$targetFile = Join-Path ([System.IO.Path]::GetTempPath()) "$ScheduleName-target.json"
$windowFile = Join-Path ([System.IO.Path]::GetTempPath()) "$ScheduleName-window.json"
$target | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $targetFile -Encoding ascii
@{ Mode = "OFF" } | ConvertTo-Json | Set-Content -LiteralPath $windowFile -Encoding ascii

$exists = (aws scheduler list-schedules --profile $Profile --region $Region `
  --name-prefix $ScheduleName --query "Schedules[?Name=='$ScheduleName'].Name | [0]" --output text).Trim()
$common = @("--profile", $Profile, "--region", $Region, "--name", $ScheduleName,
  "--schedule-expression", "rate(15 minutes)", "--flexible-time-window", "file://$windowFile",
  "--target", "file://$targetFile", "--state", $State,
  "--description", "Poll scoped Royal Electronics price-list email and run bounded wholesale follow-up")
if ($exists -eq $ScheduleName) {
  aws scheduler update-schedule @common | Out-Null
} else {
  aws scheduler create-schedule @common | Out-Null
}
if ($LASTEXITCODE -ne 0) { throw "Royal wholesale schedule configuration failed." }
Write-Host "$ScheduleName configured: rate(15 minutes), $State, $TaskDefinitionArn" -ForegroundColor Green
