param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$QueueName = "mbop-amazon-lwa-rotation"
)

$ErrorActionPreference = "Stop"

$queueUrl = aws sqs create-queue `
  --profile $Profile `
  --region $Region `
  --queue-name $QueueName `
  --attributes MessageRetentionPeriod=1209600,VisibilityTimeout=60,SqsManagedSseEnabled=true `
  --query "QueueUrl" `
  --output text

$queueArn = aws sqs get-queue-attributes `
  --profile $Profile `
  --region $Region `
  --queue-url $queueUrl `
  --attribute-names QueueArn `
  --query "Attributes.QueueArn" `
  --output text

$policy = @{
  Version = "2012-10-17"
  Statement = @(
    @{
      Sid = "AllowSPAPIApplicationManagementSecretDelivery"
      Effect = "Allow"
      Principal = @{
        AWS = "arn:aws:iam::437568002678:root"
      }
      Action = @(
        "sqs:GetQueueAttributes",
        "sqs:SendMessage"
      )
      Resource = $queueArn
    }
  )
} | ConvertTo-Json -Depth 10 -Compress

$attributes = @{ Policy = $policy } | ConvertTo-Json -Compress
$attributesFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-amazon-lwa-rotation-queue-attributes.json"
try {
  Set-Content -LiteralPath $attributesFile -Value $attributes -Encoding ascii
  aws sqs set-queue-attributes `
    --profile $Profile `
    --region $Region `
    --queue-url $queueUrl `
    --attributes "file://$attributesFile"
} finally {
  if (Test-Path -LiteralPath $attributesFile) {
    Remove-Item -LiteralPath $attributesFile -Force
  }
}

Write-Host "Amazon LWA rotation SQS queue ready." -ForegroundColor Green
Write-Host "Queue URL: $queueUrl"
Write-Host "Queue ARN: $queueArn"
Write-Host ""
Write-Host "Register this ARN in Amazon Developer Console -> Notification Preferences -> Application Client New Secret:"
Write-Host $queueArn -ForegroundColor Cyan
