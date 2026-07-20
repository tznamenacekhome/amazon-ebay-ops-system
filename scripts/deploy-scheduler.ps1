param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$RepositoryUri = "297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler",
  [string]$TaskDefinitionFamily = "mbop-scheduler-task",
  [string]$ContainerName = "mbop-scheduler",
  [string]$TaskRoleArn = "",
  [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"

function Remove-TaskDefinitionRuntimeFields($TaskDefinition) {
  foreach ($property in @(
    "taskDefinitionArn",
    "revision",
    "status",
    "requiresAttributes",
    "compatibilities",
    "registeredAt",
    "registeredBy",
    "deregisteredAt"
  )) {
    $TaskDefinition.PSObject.Properties.Remove($property)
  }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$gitSha = (git rev-parse --short=12 HEAD).Trim()
$gitStatus = (git status --short | Out-String).Trim()
if ($gitStatus -and -not $AllowDirty) {
  throw "Working tree is dirty. Commit or stash changes before deploying, or rerun with -AllowDirty."
}

$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$dirtySuffix = if ($gitStatus) { "-dirty-$timestamp" } else { "" }
$tag = "scheduler-$gitSha$dirtySuffix"
$localImage = "mbop-scheduler:$tag"
$remoteTaggedImage = "${RepositoryUri}:$tag"

Write-Host "Deploying MBOP scheduler" -ForegroundColor Cyan
Write-Host "Git SHA: $gitSha"
Write-Host "Tag:     $tag"
Write-Host "Profile: $Profile"
Write-Host ""

aws sts get-caller-identity --profile $Profile --output json | Out-Null

Write-Host "Logging Docker into ECR..." -ForegroundColor Cyan
$registryHost = $RepositoryUri.Split("/")[0]
cmd.exe /c "aws ecr get-login-password --profile `"$Profile`" --region `"$Region`" | docker login --username AWS --password-stdin $registryHost"
if ($LASTEXITCODE -ne 0) {
  throw "Docker login to ECR failed."
}

Write-Host "Building Docker image..." -ForegroundColor Cyan
docker build -f Dockerfile.scheduler -t $localImage .

Write-Host "Pushing Docker image to ECR..." -ForegroundColor Cyan
docker tag $localImage $remoteTaggedImage
docker push $remoteTaggedImage

$repositoryName = ($RepositoryUri.Split("/") | Select-Object -Last 1)
$imageDigest = (aws ecr describe-images `
  --profile $Profile `
  --region $Region `
  --repository-name $repositoryName `
  --image-ids imageTag=$tag `
  --query "imageDetails[0].imageDigest" `
  --output text).Trim()

if (-not $imageDigest -or $imageDigest -eq "None") {
  throw "Could not resolve ECR image digest for tag '$tag'."
}

$pinnedImage = "$RepositoryUri@$imageDigest"
Write-Host "Pinned image: $pinnedImage" -ForegroundColor Green

$taskDefinition = aws ecs describe-task-definition `
  --profile $Profile `
  --region $Region `
  --task-definition $TaskDefinitionFamily `
  --output json | ConvertFrom-Json

$newTaskDefinition = $taskDefinition.taskDefinition
Remove-TaskDefinitionRuntimeFields $newTaskDefinition
if ($TaskRoleArn) {
  if ($newTaskDefinition.PSObject.Properties.Name -contains "taskRoleArn") {
    $newTaskDefinition.taskRoleArn = $TaskRoleArn
  } else {
    $newTaskDefinition | Add-Member -NotePropertyName taskRoleArn -NotePropertyValue $TaskRoleArn
  }
}

$container = $newTaskDefinition.containerDefinitions |
  Where-Object { $_.name -eq $ContainerName } |
  Select-Object -First 1

if (-not $container) {
  throw "Could not find container '$ContainerName' in task definition '$TaskDefinitionFamily'."
}

$container.image = $pinnedImage

$taskFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-scheduler-task-$tag.json"
$newTaskDefinition | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $taskFile -Encoding ascii

Write-Host "Registering new ECS task definition..." -ForegroundColor Cyan
$registered = aws ecs register-task-definition `
  --profile $Profile `
  --region $Region `
  --cli-input-json "file://$taskFile" `
  --output json | ConvertFrom-Json

$newTaskDefinitionArn = $registered.taskDefinition.taskDefinitionArn

Write-Host ""
Write-Host "Scheduler deploy complete." -ForegroundColor Green
Write-Host "Task definition: $newTaskDefinitionArn"
Write-Host "Image:           $pinnedImage"
