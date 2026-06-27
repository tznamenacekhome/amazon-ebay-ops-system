param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$Cluster = "mbop-cluster1",
  [string]$Service = "mbop-web-service",
  [string]$RepositoryUri = "297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web",
  [string]$ContainerName = "mbop-web",
  [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"

function Set-ContainerEnv($Container, [string]$Name, [string]$Value) {
  if (-not $Container.environment) {
    $Container | Add-Member -NotePropertyName environment -NotePropertyValue @()
  }

  $existing = $Container.environment | Where-Object { $_.name -eq $Name } | Select-Object -First 1
  if ($existing) {
    $existing.value = $Value
    return
  }

  $Container.environment += [pscustomobject]@{
    name = $Name
    value = $Value
  }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$webRoot = Join-Path $repoRoot "web"
Set-Location $repoRoot

$gitSha = (git rev-parse --short=12 HEAD).Trim()
$gitStatus = (git status --short).Trim()
if ($gitStatus -and -not $AllowDirty) {
  throw "Working tree is dirty. Commit or stash changes before deploying, or rerun with -AllowDirty."
}

$tag = "web-$gitSha"
$localImage = "mbop-web:$tag"
$remoteTaggedImage = "${RepositoryUri}:$tag"

Write-Host "Deploying MBOP web" -ForegroundColor Cyan
Write-Host "Git SHA: $gitSha"
Write-Host "Tag:     $tag"
Write-Host "Profile: $Profile"
Write-Host ""

aws sts get-caller-identity --profile $Profile --output json | Out-Null

Write-Host "Logging Docker into ECR..." -ForegroundColor Cyan
aws ecr get-login-password --profile $Profile --region $Region |
  docker login --username AWS --password-stdin ($RepositoryUri.Split("/")[0])

Write-Host "Building Docker image..." -ForegroundColor Cyan
docker build `
  --build-arg MBOP_BUILD_SHA=$gitSha `
  -t $localImage `
  $webRoot

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

$serviceResponse = aws ecs describe-services `
  --profile $Profile `
  --region $Region `
  --cluster $Cluster `
  --services $Service `
  --output json | ConvertFrom-Json

$currentTaskDefinitionArn = $serviceResponse.services[0].taskDefinition
if (-not $currentTaskDefinitionArn) {
  throw "Could not resolve current task definition for service '$Service'."
}

$taskDefinition = aws ecs describe-task-definition `
  --profile $Profile `
  --region $Region `
  --task-definition $currentTaskDefinitionArn `
  --output json | ConvertFrom-Json

$newTaskDefinition = $taskDefinition.taskDefinition

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
  $newTaskDefinition.PSObject.Properties.Remove($property)
}

$container = $newTaskDefinition.containerDefinitions |
  Where-Object { $_.name -eq $ContainerName } |
  Select-Object -First 1

if (-not $container) {
  throw "Could not find container '$ContainerName' in task definition '$currentTaskDefinitionArn'."
}

$container.image = $pinnedImage
Set-ContainerEnv $container "CLOUD_DEPLOYMENT" "true"
Set-ContainerEnv $container "LOCAL_SYNC_ENABLED" "false"
Set-ContainerEnv $container "MBOP_BUILD_SHA" $gitSha
Set-ContainerEnv $container "NEXT_PUBLIC_MBOP_BUILD_SHA" $gitSha

$taskFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-web-task-$gitSha.json"
$newTaskDefinition | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $taskFile -Encoding ascii

Write-Host "Registering new ECS task definition..." -ForegroundColor Cyan
$registered = aws ecs register-task-definition `
  --profile $Profile `
  --region $Region `
  --cli-input-json "file://$taskFile" `
  --output json | ConvertFrom-Json

$newTaskDefinitionArn = $registered.taskDefinition.taskDefinitionArn
Write-Host "New task definition: $newTaskDefinitionArn" -ForegroundColor Green

Write-Host "Updating ECS service..." -ForegroundColor Cyan
aws ecs update-service `
  --profile $Profile `
  --region $Region `
  --cluster $Cluster `
  --service $Service `
  --task-definition $newTaskDefinitionArn `
  --output json | Out-Null

Write-Host "Waiting for ECS service to stabilize..." -ForegroundColor Cyan
aws ecs wait services-stable `
  --profile $Profile `
  --region $Region `
  --cluster $Cluster `
  --services $Service

Write-Host ""
Write-Host "Deploy complete." -ForegroundColor Green
Write-Host "Live app: https://mbop.midnightblueenterprises.com"
Write-Host "Deployed SHA: $gitSha"
